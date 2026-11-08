"""Traceable ontology synonyms plus conservative, explicitly lexical fallbacks."""
import re
from .http_client import RetrievalError
from .models import SearchAudit, TargetInput
from .relevance import ALIASES, mentions

def gene_defined_terms(target: TargetInput) -> list[str]:
    """Lexical forms for a disorder that is named after the target gene itself (e.g. "NGLY1 deficiency",
    "CDKL5 deficiency disorder"): a record about mutation, loss or ablation of that gene is a record
    about the disease. Not applied to "<GENE>-mutant <tissue cancer>" names, where the gene is a
    biomarker of a broader disease and the same wording appears in unrelated cancers."""
    symbol = re.escape(target.target_symbol)
    gene_named = any(re.match(r'^' + symbol + r'[- ](?:deficiency|deficient|disorder|syndrome|related|associated|encephalopathy)\b', name, re.I)
                     or re.search(r'\b(?:deficiency|loss) of ' + symbol + r'\b', name, re.I)
                     for name in [target.disease_name, *target.disease_aliases])
    if not gene_named:
        return []
    s = target.target_symbol
    return [f'{s} deficient', f'{s}-deficient', f'{s}-defective', f'{s} knockout', f'{s}-/-', f'{s}(-/-)', f'{s} mutation', f'{s} mutations', f'human {s} gene', f'{s} null']

def terms(target: TargetInput) -> list[str]:
    original = target.disease_name
    candidates = [original, *target.disease_aliases, *ALIASES.get(original.casefold(), []), *gene_defined_terms(target)]
    # Ontology display labels often add a generic suffix absent from abstracts.
    shortened = re.sub(r'\s+(?:infectious disease|disease|disorder)$', '', original, flags=re.I)
    if shortened != original and len(shortened) >= 3:
        candidates.append(shortened)
    acronym=re.fullmatch(r'([A-Z][A-Z0-9-]{1,9})\s+(?:infection|disease)',original)
    if acronym:candidates.append(acronym[1])
    # Preserve the clinical noun phrase, not a gene-name-only query.
    base = re.sub(r'^\S+[- ](?:mutant|mutated|positive)\s+', '', original, flags=re.I)
    if base != original:
        candidates.extend([base, *ALIASES.get(base.casefold(), [])])
    return list(dict.fromkeys(s.strip() for s in candidates if len(s.strip()) >= 3))[:30]

def matches(text: str, target: TargetInput) -> bool:
    return any(mentions(text, term) for term in terms(target))

def resolve_disease_terms(client, target: TargetInput, audit: list[SearchAudit]) -> TargetInput:
    identifier = (target.disease_id or '').replace('_', ':')
    ontology = identifier.split(':')[0].lower()
    if ontology not in {'mondo', 'efo'} or ':' not in identifier:
        audit.append(SearchAudit(source='OLS',operation='disease synonyms',url='https://www.ebi.ac.uk/ols4/',
                                 state='not_searched',detail='No supported disease ID; explicit lexical fallbacks retained.'))
        return target
    url=f'https://www.ebi.ac.uk/ols4/api/ontologies/{ontology}/terms'
    try:
        data=client.get(url,{'obo_id':identifier})
        found=data.get('_embedded',{}).get('terms',[])
        exact=[t for t in found if t.get('obo_id')==identifier]
        aliases=[value for t in exact for value in [t.get('label',''),*(t.get('synonyms') or [])] if isinstance(value,str)]
        audit.append(SearchAudit(source='OLS',operation='disease synonyms',url=url,query={'obo_id':identifier},
                                 state='found' if aliases else 'no_results',returned=len(exact),relevant=len(exact)))
        return target.model_copy(update={'disease_aliases':list(dict.fromkeys([*target.disease_aliases,*aliases]))[:30]})
    except RetrievalError as exc:
        missing=exc.status_code==404
        audit.append(SearchAudit(source='OLS',operation='disease synonyms',url=url,query={'obo_id':identifier},
            state='no_results' if missing else 'failed',
            detail='Ontology returned HTTP 404 for the supplied identifier; not found.' if missing else
                f'Ontology lookup failed (HTTP {exc.status_code or "unavailable"}); identifier unverified, not established absent.'))
        return target
