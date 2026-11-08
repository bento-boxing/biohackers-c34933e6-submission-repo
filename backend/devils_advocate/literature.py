"""Bounded, direction-neutral Europe PMC search with inspectable attrition."""
import html
import re
from .disease_terms import terms, matches
from .http_client import JsonClient, RetrievalError
from .models import Publication, SearchAudit, TargetInput, Compound
from .relevance import mentions
from .evidence_context import directional
from .association import target_mentioned,aggregate_publication

ENDPOINT='https://www.ebi.ac.uk/europepmc/webservices/rest/search'

def quoted(value: str) -> str:
    value=value.replace('\u2019',"'")
    return '"'+re.sub(r"[^\w\s'-]", ' ', value).strip()+'"'

def disease_query_term(value: str) -> str:
    # Search engines index possessives inconsistently. Preserve the original
    # phrase and add a tightly bounded eponym prefix; visible-context filtering
    # still checks actual disease relevance after retrieval.
    possessive=re.fullmatch(r"([A-Za-z]{5,})['\u2019]s(?:\s+(?:disease|syndrome|disorder|dementia))?",value,re.I)
    exact='TITLE_ABS:'+quoted(value)
    return '('+exact+' OR TITLE_ABS:'+possessive[1]+'*)' if possessive else exact

def publication_from_record(record: dict, *, discovered_by: str = 'initial retrieval') -> Publication | None:
    """One Europe PMC search row → Publication with dates and study types; None when unidentifiable."""
    if not isinstance(record, dict) or not record.get('source') or not record.get('id'):
        return None
    date = record.get('firstPublicationDate') or record.get('pubYear')
    date = date if isinstance(date, str) and re.fullmatch(r'\d{4}(?:-\d{2}){0,2}', date) else None
    pub = Publication(identifier=f"{record['source']}:{record['id']}", title=record.get('title', ''),
        abstract=re.sub(r'</?[A-Za-z][^>]*>', ' ', html.unescape(record.get('abstractText') or '')).strip(),
        doi=record.get('doi'), url=f"https://europepmc.org/article/{record['source']}/{record['id']}",
        cited_by_count=int(record.get('citedByCount') or 0), publication_date=date, discovered_by=discovered_by)
    pub.study_types = [t for t in record.get('pubTypeList', {}).get('pubType', []) if isinstance(t, str)]
    pub.evidence_tier = 'peer_reviewed' if record.get('source') in ['MED', 'PMC'] and not re.search(r'preprint', ' '.join(pub.study_types), re.I) and record.get('source') != 'PPR' else 'unverified'
    return pub

def annotate(pub: Publication) -> Publication:
    text=pub.title+' '+pub.abstract
    if aggregate_publication(pub):
        pub.clinical_candidate=False;pub.direction_signals=[];pub.conclusion_excerpt=''
        return pub
    pub.clinical_candidate=bool(re.search(r'\b(randomi[sz]ed|patients|clinical trial|phase [123]|phase III)\b',text,re.I))
    # Triage signals ONLY; these are neither adjudicated outcomes nor efficacy proof.
    chunks=re.split(r'\bconclusions?\s*:?\s*',pub.abstract,flags=re.I)
    pub.conclusion_excerpt=chunks[-1].strip() if len(chunks)>1 else ''
    conclusion=pub.conclusion_excerpt
    pub.direction_signals=[]
    # A positive phrase inside a negation ("neither drug significantly reduced liver fat") is a null result.
    positive,negated_positive=directional(r'\b(significantly (?:reduced|improved)|greater (?:virologic|viral|reduction|suppression)|efficacy superior|significantly longer|resulted in .{0,30}(?:LDL|reduction)|(?:improved|reduced) .{0,90}(?:compared with|versus)|effective and)\b',conclusion)
    if negated_positive or re.search(r'\b(did not (?:significantly )?(?:improve|reduce)|not superior|not (?:shown to be )?noninferior|no (?:significant )?(?:benefit|difference)|failed to|not meet)\b',conclusion,re.I):
        pub.direction_signals.append('negative_candidate')
    if positive:
        pub.direction_signals.append('positive_candidate')
    if re.search(r'\b(adverse events|toxicity|safety concerns|hepatotoxicity)\b',conclusion,re.I):
        pub.direction_signals.append('safety_candidate')
    if re.search(r'\b(antidrug antibodies|immunogenicity|attenuation|resistance)\b',conclusion,re.I):
        pub.direction_signals.append('compound_limitation_candidate')
    return pub

def retrieve_publications(client: JsonClient,target: TargetInput,compounds: list[Compound] | None=None,
                          audit: list[SearchAudit] | None=None,trial_publication_ids: list[str] | None=None,include_clinical: bool=False,
                          searches: bool=True) -> list[Publication]:
    """searches=False runs only the registry-linked PMID lookup, so the main searches can run alongside trial retrieval."""
    audit=audit if audit is not None else []
    names=list(dict.fromkeys([target.target_symbol,*target.target_aliases,*[c.name for c in compounds or []],
          *[s for c in compounds or [] for s in c.synonyms if 4<=len(s)<=60 and len(s.split())<=4]]))[:65]
    entity='('+' OR '.join('TITLE_ABS:'+quoted(n) for n in names)+')'
    all_disease_terms=terms(target)
    disease_names=[]
    for name in [target.disease_name,*sorted((n for n in all_disease_terms if n!=target.disease_name),key=len)]:
        candidate='('+' OR '.join(disease_query_term(n) for n in [*disease_names,name])+')'
        if len(candidate)<=500:disease_names.append(name)
    disease='('+' OR '.join(disease_query_term(n) for n in disease_names)+')'
    if len(disease_names)<len(all_disease_terms):
        audit.append(SearchAudit(source='Query preparation',operation='disease synonym budget',url=ENDPOINT,
            state='limit_reached',returned=len(disease_names),total=len(all_disease_terms),detail='Search vocabulary bounded to 500 characters; full aliases remain available to visible-context matching.'))
    broad=entity+' AND '+disease
    # Clinical query has no outcome-direction filter; broad query also retrieves mechanisms.
    queries=[('clinical literature',broad+' AND (randomized OR randomised OR "clinical trial" OR patients)'),('broad literature',broad)]
    # Pair recent retrieval with citation-ranked clinical work for every target,
    # including early programmes without curated compounds. Neither direction
    # of outcome is used as a retrieval filter.
    if include_clinical:
        queries.insert(0,('foundational clinical literature',broad+' AND (randomized OR randomised OR "clinical trial" OR patients) sort_cited:y'))
        queries.insert(0,('primary interventional clinical literature',broad+' AND (PUB_TYPE:"Clinical Trial" OR PUB_TYPE:"Randomized Controlled Trial" OR TITLE_ABS:"phase 1" OR TITLE_ABS:"phase 2" OR TITLE_ABS:"phase 3") sort_cited:y'))
    approved=[c.name for c in compounds or [] if c.max_phase==4]
    if approved:
        focused='('+' OR '.join('TITLE_ABS:'+quoted(n) for n in approved)+') AND '+disease
        queries.insert(0,('approved-compound clinical literature',focused+' AND (randomized OR randomised OR "clinical trial") sort_cited:y'))
        if include_clinical:
            queries.append(('target-level clinical context','('+' OR '.join('TITLE_ABS:'+quoted(n) for n in approved)+') AND (randomized OR randomised OR "clinical trial") sort_cited:y'))
    # Bound query grammar, splitting entity terms rather than dropping entire
    # sources when registry synonym lists exceed search-service limits.
    bounded=[]
    for operation,query in queries:
        if len(query)<=1200:bounded.append((operation,query));continue
        boundary=query.find(') AND ')
        suffix=query[boundary+1:] if boundary>=0 else ''
        query_names=approved if operation in ['approved-compound clinical literature','target-level clinical context'] else names
        chunk=[]
        for name in query_names:
            candidate='('+' OR '.join('TITLE_ABS:'+quoted(n) for n in [*chunk,name])+')'+suffix
            if len(candidate)>1200 and chunk:
                bounded.append((operation+' (query chunk)','('+' OR '.join('TITLE_ABS:'+quoted(n) for n in chunk)+')'+suffix));chunk=[]
            chunk.append(name)
        if chunk:bounded.append((operation+' (query chunk)','('+' OR '.join('TITLE_ABS:'+quoted(n) for n in chunk)+')'+suffix))
    queries=bounded if searches else []
    identifiers=list(dict.fromkeys(p for p in trial_publication_ids or [] if re.fullmatch(r'\d+',p)))[:60]
    if identifiers:
        queries.insert(0,('registry-linked result publications','SRC:MED AND ('+' OR '.join('EXT_ID:'+p for p in identifiers)+')'))
    records={}
    pending=[(operation,query,False) for operation,query in queries]
    for operation,query,is_fallback in pending:
        # Legacy direct helper calls without compounds retain a single broad search.
        if not compounds and not include_clinical and operation=='clinical literature':
            continue
        params={'query':query,'format':'json','resultType':'core','pageSize':40}
        try:
            data=client.get(ENDPOINT,params)
            raw=data.get('resultList',{}).get('result')
            if not isinstance(raw,list):
                raise RetrievalError(ENDPOINT+': malformed publication search')
            total=data.get('hitCount')
            if total is not None: total=int(total)
            retained=0
            for record in raw:
                pub=publication_from_record(record)
                if pub is None: continue
                text=pub.title+' '+pub.abstract
                disease_match=matches(text,target)
                named=target_mentioned(text,target) or any(mentions(text,n) for n in names)
                compound_named=any(mentions(text,n) for c in compounds or [] for n in [c.name,*c.synonyms])
                if not named or (not disease_match and not compound_named):continue
                pub.disease_match='matched' if disease_match else 'uncertain'
                pub.relevance=f'Visible entity match; disease match: {pub.disease_match}. Compound-only context must not be extrapolated to the requested disease/population.'
                records[pub.identifier]=annotate(pub);retained+=1
            limited=total is not None and total>len(raw)
            audit.append(SearchAudit(source='Europe PMC',operation=operation,
                url=ENDPOINT,query=params,state='limit_reached' if limited else 'found' if raw else 'no_results',
                returned=len(raw),relevant=retained,total=total,detail='Direction signals are unadjudicated triage, never outcome proof.'))
        except (RetrievalError,ValueError) as exc:
            audit.append(SearchAudit(source='Europe PMC',operation=operation,
                url=ENDPOINT,query=params,state='failed',detail=f'Publications could not be retrieved/validated; HTTP {getattr(exc,"status_code",None) or "unavailable"}; {type(exc).__name__}. Not a zero-result search.'))
            if not is_fallback and operation!='registry-linked result publications' and len(names)>1:
                # One smaller alternate query after bounded HTTP retries. Preserve
                # both the failure and fallback audit; never reinterpret it as zero.
                fallback='TITLE_ABS:'+quoted(target.target_symbol)+' AND '+disease
                if not any(q==fallback for _,q,_ in pending):pending.append(('minimal disease-target fallback',fallback,True))
    return list(records.values())
