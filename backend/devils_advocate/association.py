"""Conservative evidence-scoping for bounded biological hypothesis assessment.

These reproducible lexical screens validate source scope, not causal biology or
therapeutic benefit. Association scores are descriptive, never success odds.
"""
import re
from .disease_terms import matches
from .relevance import mentions
from .models import BiologicalAssociation, Investigation, Publication, SearchAudit
from .http_client import RetrievalError

OT='https://api.platform.opentargets.org/api/v4/graphql'
PAIR_QUERY='''query($d:String!,$t:String!){ disease(efoId:$d){id name
 associatedTargets(Bs:[$t],enableIndirect:false,page:{index:0,size:1}){
 rows{score datatypeScores{id score} target{id approvedSymbol}}}}
 target(ensemblId:$t){id approvedSymbol} }'''

def retrieve_association(client,result: Investigation) -> None:
    t=result.target
    if not (t.disease_id and (t.target_id or '').startswith('ENSG') and callable(getattr(client,'post_json',None))):
        result.ontology_association={'state':'not_searched','reason':'Exact disease and Ensembl IDs were not both supplied; no association guessed.'}
        return
    variables={'d':t.disease_id,'t':t.target_id}
    try:
        data=client.post_json(OT,{'query':PAIR_QUERY,'variables':variables})
        if data.get('errors'):raise RetrievalError('Open Targets returned a GraphQL error.')
        body=data.get('data') or {};target=body.get('target') or {};disease=body.get('disease') or {}
        if target.get('id')!=t.target_id or target.get('approvedSymbol','').casefold()!=t.target_symbol.casefold() or disease.get('id')!=t.disease_id:
            raise RetrievalError('Association identity mismatch.')
        rows=disease.get('associatedTargets',{}).get('rows',[])
        exact=[r for r in rows if r.get('target',{}).get('id')==t.target_id]
        result.ontology_association={'state':'found' if exact else 'no_results',
            'url':f'https://platform.opentargets.org/evidence/{t.target_id}/{t.disease_id}',
            'target_id':t.target_id,'disease_id':t.disease_id,'enableIndirect':False,
            'score':exact[0]['score'] if exact else None,'datatype_scores':exact[0].get('datatypeScores',[]) if exact else [],
            'caution':'An exact-pair descriptive evidence score is not causal validation, a confidence score or treatment efficacy.'}
    except RetrievalError:
        result.ontology_association={'state':'failed','reason':'Exact-pair association service unavailable/identity unverified; literature must stand on its own.'}
    result.search_audit.append(SearchAudit(source='Open Targets',operation='direct disease-target association',url=OT,
        query=variables,state=result.ontology_association['state'],detail=result.ontology_association.get('caution',result.ontology_association.get('reason',''))))

def target_mentioned(text: str,symbol) -> bool:
    # General symbol punctuation normalization (e.g. BCL2 / Bcl-2), not a target table.
    if hasattr(symbol,'target_symbol'):
        return any(target_mentioned(text,n) for n in [symbol.target_symbol,*symbol.target_aliases])
    pattern=r'[-\s]?'.join(re.escape(c) for c in symbol)
    return bool(re.search(r'(?<!\w)'+pattern+r'(?!\w)',text,re.I))

def interventional(pub: Publication) -> bool:
    types=' '.join(pub.study_types)
    early_human_trial=(re.search(r'\bphase\s+(?:[123][ab]?|[IVX]+)\b.{0,90}\b(?:trials?|studies|study)\b',pub.abstract,re.I)
        and re.search(r'\bin\s+\d+\s+(?:healthy\s+)?(?:patients|participants|volunteers|subjects)\b',pub.abstract,re.I))
    return bool(re.search(r'randomi[sz]ed|controlled clinical trial|clinical trial, phase',types,re.I) or
        early_human_trial or
        re.search(r'\b(randomi[sz]ed|phase (?:[123]|[IVX]+))\b.{0,90}\b(trial|study)\b',pub.title,re.I) or
        re.search(r'\b(randomi[sz]ed|placebo-controlled|double-blind)\b',pub.abstract,re.I))

def aggregate_publication(pub: Publication) -> bool:
    return bool(re.search(r'^\s*(?:(?:poster|oral)\s+session|abstracts\b|proceedings\b)',pub.title,re.I)
        or ('abstract' in {s.casefold() for s in pub.study_types} and len(pub.abstract)>20000))

def scope_publication(pub: Publication,result: Investigation) -> tuple[str,list[str],str]:
    text=pub.title+' '+pub.abstract;t=result.target
    if aggregate_publication(pub):
        return 'indirect_mechanistic',[],'Bundled conference/session record: retain as a literature lead, not an independent primary study or coherent claim source.'
    entity=target_mentioned(text,t)
    compound=any(mentions(text,n) for c in result.compounds for n in [c.name,*c.synonyms] if len(n)>=4)
    disease=matches(text,t)
    signals=[]
    for name,pattern in [('human_genetic_association',r'\b(GWAS|genotyp\w*|risk loci|risk variants|susceptib\w* variants|genetic variants|genome-wide)\b'),
        ('cellular_mechanistic',r'\b(knockdown|knockout|silenc\w*|overexpress\w*|rescue|reporter assay|chondrocytes?|cultured|perturb\w*)\b'),
        ('expression_only',r'\b(expression|differentially expressed|upregulated|downregulated|biomarkers?)\b'),
        ('animal_model',r'\b(mouse|mice|murine|zebrafish|Danio rerio|animal model)\b')]:
        if re.search(pattern,pub.abstract,re.I):signals.append(name)
    # Environmental developmental toxicity and incidental control tissues do not
    # establish the requested disease's pathogenesis or a causal target link.
    incidental=bool(re.search(r'\b(environmental\w*|aquatic|malformations|control tissues?|controls?)\b',pub.title,re.I))
    disease_title=matches(pub.title,t)
    target_disease_sentences=[s for s in re.split(r'(?<=[.!?])\s+',pub.abstract)
        if matches(s,t) and target_mentioned(s,t) and
        re.search(r'\b(associat\w*|risk|caus\w*|contribut\w*|mediat\w*|regulat\w*|promot\w*|pathogen\w*|progression|susceptib\w*)\b',s,re.I) and
        not re.search(r'\b(control|compared (?:with|to)|detect the expression|measured in)\b',s,re.I)]
    reviewed=bool(re.search(r'\b(review|meta-analysis|systematic review|editorial|comment|news)\b',' '.join(pub.study_types)+' '+pub.title,re.I))
    target_intervention=target_mentioned(pub.title,t) and re.search(r'\b(inhibit\w*|antagoni\w*|silenc\w*|target\w*|activat\w*|modulat\w*|antisense)\b',pub.title,re.I)
    if disease and (compound or target_intervention) and interventional(pub) and not reviewed:
        return 'direct_clinical',signals,'Disease-matched interventional compound study; target engagement and population remain subject to review.'
    if entity and disease and signals and not incidental and not reviewed and (disease_title or target_disease_sentences):
        return 'direct_biological',signals,'Disease-specific primary biological candidate; association/perturbation does not prove therapeutic validity. Locus-to-gene assignment needs review.'
    if entity or compound:
        return ('indirect_mechanistic' if disease else 'target_pharmacology'),signals,'Context only: incidental disease mention, control tissue, different condition/species, review or uncertain target-specific causal relevance.'
    return 'unrelated',signals,'No visible target or curated compound relationship.'

def assess_association(result: Investigation) -> BiologicalAssociation:
    direct=[];indirect=[];unrelated=[];groups=[];kinds=set();clinical=False
    for pub in result.publications:
        scope,signals,reason=scope_publication(pub,result)
        pub.evidence_scope=scope;pub.biological_signals=signals;pub.scope_reason=reason
        if scope in ['direct_clinical','direct_biological'] and pub.abstract:
            direct.append(pub.identifier);kinds.update(signals);clinical|=scope=='direct_clinical'
            # Versions sharing a DOI/title count once, not independent replication.
            keys={'title:'+re.sub(r'[^a-z0-9]','',pub.title.casefold())}
            if pub.doi:keys.add('doi:'+pub.doi.casefold())
            overlapping=[g for g in groups if g&keys]
            for group in overlapping:keys.update(group);groups.remove(group)
            groups.append(keys)
        elif scope in ['indirect_mechanistic','target_pharmacology']:indirect.append(pub.identifier)
        else:unrelated.append(pub.identifier)
    adequate_biology=len(groups)>=2 and bool(kinds&{'human_genetic_association','cellular_mechanistic','animal_model'})
    strength='clinical_context' if clinical else 'exploratory' if adequate_biology else 'insufficient'
    return BiologicalAssociation(strength=strength,direct_source_ids=direct,indirect_source_ids=indirect,
        unrelated_source_ids=unrelated,independent_groups=len(groups),evidence_types=sorted(kinds),
        explanation='Disease-specific clinical context retrieved; inspect actual indication/population and target mechanism.' if clinical else
            'Multiple primary biological source groups support a limited hypothesis assessment; causality, direction and therapeutic value remain unresolved.' if adequate_biology else
            'Insufficient disease-specific primary biological support: need multiple distinct primary study groups with genetic, functional cellular or disease-model evidence; compound pharmacology and co-mentions do not qualify.',
        limitations=['Deterministic source-scope triage, not expert quality assessment or causal verification.',
            'Distinct source groups are not proof of independent cohorts; reviews and duplicated versions must not count as replication.',
            'Biomarker changes, GWAS loci and druggability do not establish a valid therapeutic target.'],
        ontology_association=result.ontology_association)
