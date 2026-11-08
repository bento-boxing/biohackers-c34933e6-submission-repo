"""Retrieve curated mechanisms, compound synonyms, and registry records."""
import re
import time
from .http_client import JsonClient, RetrievalError
from .models import Compound, TargetInput, Trial, SearchAudit
from .disease_terms import matches
from .relevance import disease_matches
from .stop_reasons import fetch_stop_reason, inspect_stop_reason

CHEMBL = 'https://www.ebi.ac.uk/chembl/api/data'
CTG = 'https://clinicaltrials.gov/api/v2/studies'

def normalize(value: str) -> str:
    return re.sub(r'[^a-z0-9]', '', value.casefold())

class TargetIdentityError(ValueError):
    """A supplied database identifier disagrees with the requested human protein."""

def verify_supplied_gene(client,target: TargetInput,audit: list[SearchAudit]) -> None:
    identifier=target.target_id or ''
    if not identifier.startswith('ENSG'):return
    url='https://rest.ensembl.org/lookup/id/'+identifier
    if not re.fullmatch(r'ENSG\d{11}',identifier):raise TargetIdentityError('Malformed supplied Ensembl gene identifier.')
    try:record=client.get(url,{'content-type':'application/json'})
    except RetrievalError as exc:
        if exc.status_code==404:
            audit.append(SearchAudit(source='Ensembl',operation='gene identity',url=url,state='no_results',detail='Supplied gene identifier not found.'))
            raise TargetIdentityError('Supplied Ensembl gene identifier was not found.') from None
        raise
    valid=(record.get('id')==identifier and record.get('species')=='homo_sapiens'
        and record.get('display_name','').casefold()==target.target_symbol.casefold())
    audit.append(SearchAudit(source='Ensembl',operation='gene identity',url=url,
        state='found' if valid else 'failed',detail='Human gene identifier and symbol agree.' if valid else 'Supplied gene identifier, species and symbol disagree or record is malformed.'))
    if not valid:raise TargetIdentityError('Supplied Ensembl identifier does not verify the requested human gene symbol; downstream retrieval blocked.')

def resolve_target(client: JsonClient, target: TargetInput) -> str | None:
    # External identifiers (e.g. Ensembl) are preserved but never used as ChEMBL IDs.
    supplied = target.chembl_target_id or (target.target_id if target.target_id and re.fullmatch(r'CHEMBL\d+', target.target_id) else None)
    if target.chembl_target_id and target.target_id and target.target_id.startswith('CHEMBL') and target.chembl_target_id != target.target_id:
        raise TargetIdentityError('Conflicting supplied ChEMBL target identifiers.')
    key = (supplied, target.target_symbol.casefold(), target.uniprot)
    cache = getattr(client, '_verified_resolutions', None) if isinstance(client, JsonClient) else None
    if cache is not None and not getattr(client,'refresh',False) and not getattr(client,'persistent_cache',None) and key in cache and time.monotonic() - cache[key][0] < 900:
        target.target_aliases=list(getattr(client,'_verified_target_aliases',{}).get(cache[key][1],[]))
        return cache[key][1]
    if supplied:
        try:
            record = client.get(f'{CHEMBL}/target/{supplied}.json')
        except RetrievalError as exc:
            if exc.status_code == 404:
                raise TargetIdentityError('Supplied ChEMBL target ID does not exist in the registry.') from None
            raise
        if not record.get('target_chembl_id'):
            raise RetrievalError(f'{CHEMBL}/target/{supplied}.json: malformed target record; identity unavailable.')
        if record.get('target_chembl_id') != supplied:
            raise TargetIdentityError('ChEMBL returned a different target identifier.')
        records = [record]
    else:
        page = client.get(f'{CHEMBL}/target/search.json', {'q': target.target_symbol, 'limit': 30})
        if not isinstance(page.get('targets'), list):
            raise RetrievalError(f'{CHEMBL}/target/search.json: malformed target search response; identity unavailable.')
        records = page['targets']
    exact = []
    primary = []  # matches on the component's current GENE_SYMBOL, not a historical alias
    for record in records:
        if not isinstance(record, dict):
            raise RetrievalError(f'{CHEMBL}/target/search.json: malformed target candidate.')
        synonyms = [s for c in record.get('target_components', []) for s in c.get('target_component_synonyms', [])]
        symbols = [s.get('component_synonym', '') for s in synonyms]
        components = record.get('target_components', [])
        if (record.get('organism') == 'Homo sapiens'
                and record.get('target_type') == 'SINGLE PROTEIN'
                and len(components) == 1
                and record.get('tax_id', 9606) == 9606
                and (not target.uniprot or any(c.get('accession') == target.uniprot for c in components))
                and target.target_symbol.casefold() in [s.casefold() for s in symbols]):
            exact.append(record['target_chembl_id'])
            if any(s.get('syn_type') == 'GENE_SYMBOL' and s.get('component_synonym', '').casefold() == target.target_symbol.casefold() for s in synonyms):
                primary.append(record['target_chembl_id'])
    # A symbol shared with another protein's historical alias (e.g. HTT for SLC6A4's 5-HTT) is
    # resolved by the current gene symbol; a residual tie stays unresolved rather than guessed.
    resolved = exact[0] if len(set(exact)) == 1 else primary[0] if len(set(primary)) == 1 else None
    if supplied and not resolved:
        raise TargetIdentityError('Supplied ChEMBL ID does not match the exact human protein symbol and component accession.')
    if resolved and isinstance(client, JsonClient):
        if cache is None:
            client._verified_resolutions = {}
            cache = client._verified_resolutions
        cache[key] = (time.monotonic(), resolved)
    if resolved:
        target.protein_gene_symbols=list(dict.fromkeys(s.get('component_synonym','') for r in records if r.get('target_chembl_id')==resolved
            for component in r.get('target_components',[]) for s in component.get('target_component_synonyms',[]) if s.get('syn_type')=='GENE_SYMBOL'))[:30]
        candidates=[s.get('component_synonym','') for r in records if r.get('target_chembl_id')==resolved
            for component in r.get('target_components',[]) for s in component.get('target_component_synonyms',[])
            if s.get('syn_type')=='GENE_SYMBOL_OTHER']
        target.target_aliases=list(dict.fromkeys(n for n in candidates if re.fullmatch(r'[A-Za-z][A-Za-z0-9-]{2,29}',n) and n.casefold()!=target.target_symbol.casefold()))[:8]
        if len(target.protein_gene_symbols)>1:target.target_aliases=[]
        if isinstance(client,JsonClient):
            if not hasattr(client,'_verified_target_aliases'):client._verified_target_aliases={}
            client._verified_target_aliases[resolved]=list(target.target_aliases)
    return resolved

def retrieve_compounds(client: JsonClient, target_id: str, notes: list[str] | None = None,
                       audit: list[SearchAudit] | None = None) -> list[Compound]:
    mechanisms = []
    for offset in range(0, 300, 100):
        page = client.get(f'{CHEMBL}/mechanism.json',
                          {'target_chembl_id': target_id, 'limit': 100, 'offset': offset})
        mechanisms.extend(page.get('mechanisms', []))
        if not page.get('page_meta', {}).get('next'):
            break
    else:
        if notes is not None:
            notes.append('ChEMBL mechanisms capped at 300 records.')
    grouped: dict[str, list[str]] = {}
    for item in mechanisms:
        grouped.setdefault(item['molecule_chembl_id'], []).append(item.get('mechanism_of_action') or '')
    compounds = []
    molecules = {}
    # Rank by actual molecule metadata before capping; identifier order can hide approved drugs.
    if len(grouped)>15:
        identifiers=sorted(grouped)
        for start in range(0,len(identifiers),100):
            page=client.get(f'{CHEMBL}/molecule.json',{'molecule_chembl_id__in':','.join(identifiers[start:start+100]),'limit':100})
            molecules.update({m['molecule_chembl_id']:m for m in page.get('molecules',[])})
        if audit is not None and len(molecules)<len(grouped):
            audit.append(SearchAudit(source='ChEMBL',operation='molecule metadata',url=f'{CHEMBL}/molecule.json',
                state='failed',returned=len(molecules),detail='Some candidate molecule metadata missing; approval coverage incomplete.'))
    if len(grouped) > 15 and notes is not None:
        notes.append(f'Compound retrieval capped at 15 of {len(grouped)} curated mechanism compounds.')
    def priority(item):
        phase=molecules.get(item[0],{}).get('max_phase')
        return (-(float(phase) if phase is not None else -1),item[0])
    for identifier, actions in sorted(grouped.items(),key=priority)[:15]:
        try:
            molecule = molecules.get(identifier) or client.get(f'{CHEMBL}/molecule/{identifier}.json')
        except RetrievalError as exc:
            if notes is None:
                raise
            notes.append(str(exc))
            if audit is not None:audit.append(SearchAudit(source='ChEMBL',operation='molecule metadata',
                url=f'{CHEMBL}/molecule/{identifier}.json',state='failed',detail='Candidate molecule metadata unavailable; approval status unresolved.'))
            continue
        compounds.append(Compound(chembl_id=identifier,
            name=molecule.get('pref_name') or identifier,
            synonyms=sorted({s['molecule_synonym'] for s in molecule.get('molecule_synonyms', [])
                             if s.get('molecule_synonym')}), mechanisms=actions,
            url=f'https://www.ebi.ac.uk/chembl/explore/compound/{identifier}',
            max_phase=molecule.get('max_phase'),withdrawn_flag=molecule.get('withdrawn_flag'),
            first_approval=molecule.get('first_approval'),approval_source_url=f'{CHEMBL}/molecule/{identifier}.json',
            molecule_type=molecule.get('molecule_type'),
            mechanism_records=[{k:r.get(k) for k in ['target_chembl_id','molecule_chembl_id','mechanism_of_action','action_type','direct_interaction','molecular_mechanism','mechanism_refs']} for r in mechanisms if r.get('molecule_chembl_id')==identifier]))
    if audit is not None:
        audit.append(SearchAudit(source='ChEMBL',operation='mechanism compounds',url=f'{CHEMBL}/mechanism.json',
            query={'target_chembl_id':target_id},state='limit_reached' if len(grouped)>15 or len(mechanisms)>=300 else 'found' if compounds else 'no_results',
            returned=len(compounds),relevant=len(compounds),total=len(grouped),
            detail='max_phase=4 is approval precedent for some indication, not proof for the requested disease.'))
    return compounds

def compound_matcher(compounds: list[Compound]):
    return [(c.chembl_id,{normalize(s) for s in [c.name,*c.synonyms] if len(normalize(s))>=4},
             re.compile(r'(?<!\w)(?:'+'|'.join(re.escape(s) for s in [c.name,*c.synonyms] if len(s)>=5)+r')(?!\w)',re.I)
             if any(len(s)>=5 for s in [c.name,*c.synonyms]) else None) for c in compounds]

def parse_trial(record: dict, compounds: list[Compound], *, matcher=None) -> Trial:
    protocol = record.get('protocolSection', {})
    identity = protocol.get('identificationModule', {})
    status = protocol.get('statusModule', {})
    interventions = [name for item in protocol.get('armsInterventionsModule', {}).get('interventions', [])
                     for name in [item.get('name', ''), *item.get('otherNames', [])] if name]
    exact, probable = [], []
    for identifier,aliases,pattern in matcher if matcher is not None else compound_matcher(compounds):
        if any(normalize(i) in aliases for i in interventions):
            exact.append(identifier)
        elif pattern and any(pattern.search(i) for i in interventions):
            probable.append(identifier)
    nct = identity['nctId']
    reason = inspect_stop_reason(record, nct)
    if not isinstance(status, dict):
        status = {}  # malformed status module: the stop-reason evidence already records 'invalid'
    def date(key):
        value = status.get(key) if isinstance(status, dict) else None
        value = value.get('date') if isinstance(value, dict) else None
        return value if isinstance(value, str) and re.fullmatch(r'\d{4}(?:-\d{2}){0,2}', value) else None
    has_results = record.get('hasResults', bool(record.get('resultsSection')))
    return Trial(nct_id=nct, title=identity.get('briefTitle', ''),
        start_date=date('startDateStruct'), completion_date=date('primaryCompletionDateStruct') or date('completionDateStruct'),
        last_update_date=date('lastUpdatePostDateStruct'), results_posted_date=date('resultsFirstPostDateStruct'),
        evidence_tier='registry_results' if has_results else 'registry_status',
        status=status.get('overallStatus', 'UNKNOWN'), why_stopped=reason.value if reason.state == 'reported' else '',
        stop_reason=reason,
        conditions=protocol.get('conditionsModule', {}).get('conditions', []),
        interventions=interventions,
        population=protocol.get('eligibilityModule', {}).get('eligibilityCriteria', ''),
        has_results=has_results,
        compound_ids=list(dict.fromkeys(exact + probable)),
        compound_matches={**{identifier: 'probable' for identifier in probable},
                          **{identifier: 'verified' for identifier in exact}},
        outcome_records=record.get('resultsSection', {}).get('outcomeMeasuresModule', {}).get('outcomeMeasures', []),
        relationship='verified' if exact else 'probable' if probable else 'uncertain',
        match_reason='Exact normalized intervention alias' if exact else
                     'Alias within intervention text; review needed' if probable else 'No intervention alias match',
        url=f'https://clinicaltrials.gov/study/{nct}',
        phases=protocol.get('designModule',{}).get('phases',[]),
        publication_ids=list(dict.fromkeys(r['pmid'] for r in protocol.get('referencesModule',{}).get('references',[])
            if r.get('type')=='RESULT' and re.fullmatch(r'\d+',str(r.get('pmid',''))))))

STOPPED_STATUSES = {'TERMINATED', 'WITHDRAWN', 'SUSPENDED'}
FULL_RECORD_RESERVE_SECONDS = 30  # keep time for literature retrieval after trials


def _remaining_seconds(client) -> float | None:
    getter = getattr(client, 'remaining_seconds', None)
    value = getter() if callable(getter) else None
    return value if isinstance(value, (int, float)) else None


def retrieve_trials(client: JsonClient, target: TargetInput, compounds: list[Compound],
                    notes: list[str], audit: list[SearchAudit] | None = None) -> list[Trial]:
    found = {}
    matcher=compound_matcher(compounds)
    raw_records={}
    hits: dict[str, list[str]] = {}
    # Separate queries avoid a long OR expression and retain per-compound provenance.
    terms = [target.target_symbol, *target.target_aliases, *[c.name for c in compounds]]
    for term in dict.fromkeys(terms):
        params = {'query.cond': target.disease_name, 'query.intr': term, 'pageSize': 50, 'format': 'json'}
        count=0;relevant=0
        try:
            for _ in range(2):
                page = client.get(CTG, params)
                if not isinstance(page.get('studies'),list):
                    raise RetrievalError(CTG+': malformed trial search')
                count+=len(page['studies'])
                for record in page.get('studies', []):
                    try:
                        protocol=record['protocolSection'];nct=protocol['identificationModule']['nctId']
                        if not re.fullmatch(r'NCT\d{8}',nct):raise ValueError('Invalid NCT ID')
                        conditions=protocol.get('conditionsModule',{}).get('conditions',[])
                    except (KeyError, TypeError, ValueError) as exc:
                        notes.append(f'{CTG}: malformed study record skipped ({type(exc).__name__}).')
                        continue
                    relevant+=matches(' '.join(conditions),target)
                    raw_records[nct]=record
                    hits.setdefault(nct,[]).append(term)
                token = page.get('nextPageToken')
                if not token:
                    break
                params['pageToken'] = token
            else:
                notes.append(f'Trial search capped at 100 records for {term}.')
            if audit is not None:
                audit.append(SearchAudit(source='ClinicalTrials.gov',operation='trial search',url=CTG,
                    query={'condition':target.disease_name,'intervention':term},state='limit_reached' if token else 'found' if count else 'no_results',returned=count,relevant=relevant))
        except RetrievalError as exc:
            notes.append(str(exc))
            if audit is not None:audit.append(SearchAudit(source='ClinicalTrials.gov',operation='trial search',url=CTG,state='failed',detail='Trial query failed; not a zero-result query.'))
    return complete_trial_records(client, target, compounds, raw_records, notes, audit, matcher=matcher, search_terms=hits)


def complete_trial_records(client, target: TargetInput, compounds: list[Compound], raw_records: dict,
                           notes: list[str], audit: list[SearchAudit] | None = None, *, matcher=None,
                           search_terms: dict[str, list[str]] | None = None) -> list[Trial]:
    """Parse search rows, then verify each unique trial against its full registry record (batched, cached)."""
    found = {}
    matcher = matcher if matcher is not None else compound_matcher(compounds)
    # Search results may omit fields. Fetch each unique trial's full record once
    # (the shared client caches it), then inspect actual field membership.
    for nct,raw in raw_records.items():
        try:
            trial=parse_trial(raw,compounds,matcher=matcher)
            trial.disease_match='matched' if matches(' '.join(trial.conditions),target) else 'uncertain'
            trial.search_terms=list(dict.fromkeys((search_terms or {}).get(nct,[])))
            found[nct]=trial
        except (KeyError,TypeError,ValueError):notes.append(f'{CTG}: malformed study record skipped.')
    def fetch_detail(trial):
        full=[]
        reason = fetch_stop_reason(client, trial.nct_id,on_record=full.append)
        return trial,reason,full
    cached={}
    if isinstance(client,JsonClient):
        missing=[]
        for trial in found.values():
            record=client.cached_response(f'{CTG}/{trial.nct_id}')
            if record is None:missing.append(trial.nct_id)
            else:cached[trial.nct_id]=record
        def batch_fetch(ids):
            try:
                page=client.get(CTG,{'filter.ids':','.join(ids),'pageSize':50,'format':'json'})
                records={r.get('protocolSection',{}).get('identificationModule',{}).get('nctId'):r for r in page.get('studies',[])}
                # Verify a full detail response per batch: if bulk fields differ,
                # use individual detail fetches rather than trusting omitted data.
                sample=next((identifier for identifier in ids if identifier in records),None)
                if sample:
                    detail=client.get(f'{CTG}/{sample}')
                    if any(records[sample].get(key)!=detail.get(key) for key in ['protocolSection','resultsSection']):
                        return {sample:detail}
                for identifier in ids:
                    if identifier in records:
                        reason=inspect_stop_reason(records[identifier],identifier,full_record=True)
                        if reason.state!='invalid':client.prime_verified_record(f'{CTG}/{identifier}',records[identifier],origin=CTG+'?filter.ids='+','.join(ids))
                return {identifier:records[identifier] for identifier in ids if identifier in records}
            except RetrievalError:return {}
        for records in client.map(batch_fetch,[missing[i:i+50] for i in range(0,len(missing),50)]):cached.update(records)
        if audit is not None:audit.append(SearchAudit(source='ClinicalTrials.gov',operation='full record batch verification',url=CTG,
            state='found' if cached else 'no_results',returned=len(cached),detail='No field projection; exact NCT identities checked; protocol/results compared with individual detail sample per batch. Missing records fall back to individual details.'))
    details=[(t,inspect_stop_reason(cached[t.nct_id],t.nct_id,full_record=True),[cached[t.nct_id]]) for t in found.values() if t.nct_id in cached]
    # Trials the batch did not return are fetched one by one, stopped trials first; when the
    # retrieval budget runs short the rest keep their search-response stop reason, labelled unverified.
    pending=sorted((t for t in found.values() if t.nct_id not in cached),key=lambda t:t.status not in STOPPED_STATUSES)
    workers=client.max_workers if isinstance(client,JsonClient) else 1
    for start in range(0,len(pending),max(1,workers)*2):
        remaining=_remaining_seconds(client)
        if remaining is not None and remaining<FULL_RECORD_RESERVE_SECONDS:
            notes.append(f'Full registry record checks stopped after {start} of {len(pending)} unbatched trials: '
                         'retrieval time budget nearly exhausted. Unchecked trials are labelled as not verified.')
            break
        chunk=pending[start:start+max(1,workers)*2]
        details.extend(client.map(fetch_detail,chunk) if isinstance(client,JsonClient) else [fetch_detail(t) for t in chunk])
    for trial,reason,full in details:
        reason.search_value = trial.stop_reason.value
        reason.search_state = trial.stop_reason.state
        if full:
            try:
                detailed=parse_trial(full[0],compounds,matcher=matcher)
                detailed.disease_match='matched' if matches(' '.join(detailed.conditions),target) else 'uncertain'
                detailed.search_terms=trial.search_terms
                found[trial.nct_id]=detailed
                trial=detailed
            except (KeyError,TypeError,ValueError):
                notes.append(f'{CTG}/{trial.nct_id}: full record has malformed non-status fields; search record retained.')
                if audit is not None:audit.append(SearchAudit(source='ClinicalTrials.gov',operation='full record results',
                    url=f'{CTG}/{trial.nct_id}',state='failed',detail='Non-status fields malformed; do not infer missing results.'))
        trial.stop_reason = reason
        trial.why_stopped = reason.value if reason.state == 'reported' else ''
        if reason.state in ['api_error', 'record_missing', 'invalid']:
            notes.append(f'{reason.source_url}: {reason.detail}')
    return list(found.values())
