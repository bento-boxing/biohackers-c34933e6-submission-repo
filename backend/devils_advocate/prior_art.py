"""Question-specific retrieval and conservative final checks, not novelty proof."""
import math,re,time
from contextlib import nullcontext
from collections import Counter
from .models import Experiment,Investigation,SearchAudit
from .literature import ENDPOINT,quoted,annotate
from .models import Publication
from .disease_terms import matches,terms
from .association import target_mentioned
from .http_client import RetrievalError,RetrievalDeadlineExceeded

STOP=set('a an the in on of to and or with without for by from is are was were does do can could whether which that this these those as at it its be been have has patients patient treatment study studies trial trials disease target proposed experiment question mechanism context effect effects model models compared versus primarily driven during having screened before after'.split())
# Background pharmacology and grammatical filler must not count as distinctive
# question overlap (e.g. a binding study does not answer a hepatotoxicity question).
STOP.update('human clinical compound compounds specific specifically associated mediated driven comparison pharmacological signal signals signaling inhibition inhibitor inhibitors blockade antagonist antagonists not while well against method methods type small molecule molecules scaffold'.split())

def tokens(text):
    def stem(word):
        for suffix in ['ation','ing','ed','es','s']:
            if word.endswith(suffix) and len(word)>len(suffix)+4:return word[:-len(suffix)]
        return word
    return {stem(w) for w in re.findall(r'[a-z][a-z0-9]{2,}',text.casefold()) if w not in STOP}

def extract_question(e: Experiment) -> dict:
    return {'scientific_claim':e.scientific_claim or e.unresolved_gap,'mechanism':e.mechanism or e.measurement,
            'context':e.context or e.model,'research_question':e.question}

def ranked_matches(result: Investigation,text: str):
    query=tokens(text)-tokens(result.target.target_symbol+' '+result.target.disease_name)
    segments=[tokens(s)-tokens(result.target.target_symbol+' '+result.target.disease_name)
              for s in re.split(r'\bor\b|\bversus\b|\bvs\b',text,flags=re.I)]
    segments=[s for s in segments if len(s)>=4]+[query]
    corpus=[tokens(p.title+' '+p.abstract) for p in result.publications]
    counts=Counter(t for record in corpus for t in record)
    weights={t:math.log(1+len(corpus)/(1+counts[t]))+1 for t in query}
    total=sum(weights.values()) or 1
    ranked=[]
    for pub,words in zip(result.publications,corpus):
        shared=query&words
        score=max(sum(weights.get(t,1) for t in segment&words)/(sum(weights.get(t,1) for t in segment) or 1) for segment in segments)
        rare=[t for t in shared if counts[t]<=max(2,len(corpus)//8)]
        if len(shared)>=3 and score>=.12:
            ranked.append({'source_id':pub.identifier,'title':pub.title,'url':pub.url,
                'score':round(score,4),'shared_terms':sorted(shared),'specific_shared_terms':sorted(rare),
                'conclusion':pub.conclusion_excerpt or pub.abstract[-1000:],
                'disease_in_title':matches(pub.title,result.target),
                'caution':'Lexical question/mechanism overlap is a prior-art warning, not proof that every detail is answered.'})
    return sorted(ranked,key=lambda r:(-r['score'],r['source_id']))

def prior_art_context(result: Investigation,uncertainties: list[str],limit=4,exclude_ids=()):
    """Candidate existing work for the designer, selected from the full collection."""
    merged={}
    for text in uncertainties:
        for match in ranked_matches(result,text):
            if match['source_id'] not in exclude_ids and match['score']>merged.get(match['source_id'],{}).get('score',-1):merged[match['source_id']]=match
    ranked=sorted(merged.values(),key=lambda m:(not m['disease_in_title'],-m['score'],m['source_id']))
    ids=[r['source_id'] for r in ranked[:limit]]
    return [p for identifier in ids for p in result.publications if p.identifier==identifier]

def proposal_objections(e: Experiment) -> list[str]:
    text=' '.join([*e.competing_explanations,*e.possible_results,e.decision_impact])
    issues=[]
    if re.search(r'\b(?:only|exclusively)\b.{0,100}\b(?:suppress\w*|treat\w*|cur\w*|explain\w*)\b',text,re.I):
        issues.append('Unsupported exclusivity: supplied evidence must not be generalized to an only-effective mechanism or treatment.')
    if re.search(r'\b(?:zero|absence of all|complete absence)\b.{0,90}\b(?:variants|risk|toxicity|off.target)',text,re.I):
        issues.append('Assay sensitivity: finite detection cannot establish absolute absence; specify a detection bound and uncertainty.')
    return issues

def check_prior_art(result: Investigation,e: Experiment,*,client=None) -> dict:
    start=time.monotonic();question=extract_question(e);searches=[];additional=[]
    # Targeted retrieval uses domain terms from the actual proposed question,
    # never target-specific canned answers. Failed searches are not negative findings.
    if client is not None:
        ranked_terms=sorted(tokens(e.question)-tokens(result.target.disease_name+' '+result.target.target_symbol))
        keywords=[t for t in ranked_terms if len(t)>4][:8]
        if keywords:
            entities=[result.target.target_symbol,*result.target.target_aliases]
            query='('+' OR '.join('TITLE_ABS:'+quoted(n) for n in entities)+') AND ('+' OR '.join('TITLE_ABS:'+t+'*' for t in keywords)+')'
            params={'query':query,'format':'json','resultType':'core','pageSize':20}
            try:
                context=client.tracking(scope=result.target.model_dump(mode='json'),budget_seconds=60) if hasattr(client,'tracking') else nullcontext()
                with context:data=client.get(ENDPOINT,params)
                raw=data.get('resultList',{}).get('result')
                if not isinstance(raw,list):raise RetrievalError('Malformed targeted literature response')
                import html
                for r in raw:
                    if not r.get('source') or not r.get('id'):continue
                    abstract=re.sub(r'</?[A-Za-z][^>]*>',' ',html.unescape(r.get('abstractText') or '')).strip()
                    if not target_mentioned(r.get('title','')+' '+abstract,result.target):continue
                    p=annotate(Publication(identifier=f"{r['source']}:{r['id']}",title=r.get('title',''),abstract=abstract,
                        doi=r.get('doi'),url=f"https://europepmc.org/article/{r['source']}/{r['id']}"))
                    p.disease_match='matched' if matches(p.title+' '+p.abstract,result.target) else 'uncertain'
                    if p.identifier not in {x.identifier for x in result.publications}:result.publications.append(p);additional.append(p.identifier)
                audit=SearchAudit(source='Europe PMC',operation='question-specific prior art',url=ENDPOINT,query=params,
                    state='limit_reached' if data.get('hitCount',0)>len(raw) else 'found' if raw else 'no_results',returned=len(raw),total=data.get('hitCount'))
            except (RetrievalError,RetrievalDeadlineExceeded):
                audit=SearchAudit(source='Europe PMC',operation='question-specific prior art',url=ENDPOINT,query=params,state='failed',detail='Prior-art search failed; novelty cannot be established from absence.')
            result.search_audit.append(audit);searches.append(audit.model_dump(mode='json'))
    # The question controls blocking. Long generated gap/claim summaries often
    # repeat generic clinical context and must not inflate the overlap score.
    matches_=ranked_matches(result,e.question)
    close=[m for m in matches_ if m['score']>=.28 and len(m['specific_shared_terms'])>=2]
    issues=proposal_objections(e)
    status='PRIOR_ART_OVERLAP_REQUIRES_REVIEW' if close else 'NOVELTY_NOT_ESTABLISHED'
    if any(s['state']=='failed' for s in searches):issues.append('Question-specific literature lookup failed; prior-art coverage incomplete.')
    return {'status':status,'question':question,'matches':matches_[:12],'close_matches':[m['source_id'] for m in close],
        'additional_source_ids':additional,'searches':searches,'objections':issues,'duration_seconds':round(time.monotonic()-start,6),
        'decision':'abstain' if close or issues else 'unvalidated_proposal_requires_expert_review',
        'caution':'No-overlap is not proof of novelty; close overlap warrants review, not a categorical claim that all experimental details are solved.'}
