"""Retrieve curated mechanisms, compound synonyms, and registry records."""
import re
import time
from .http_client import JsonClient, RetrievalError
from .models import Compound, TargetInput, Trial
from .relevance import disease_matches
from .stop_reasons import fetch_stop_reason, inspect_stop_reason

CHEMBL = 'https://www.ebi.ac.uk/chembl/api/data'
CTG = 'https://clinicaltrials.gov/api/v2/studies'

def normalize(value: str) -> str:
    return re.sub(r'[^a-z0-9]', '', value.casefold())

class TargetIdentityError(ValueError):
    """A supplied database identifier disagrees with the requested human protein."""

def resolve_target(client: JsonClient, target: TargetInput) -> str | None:
    # External identifiers (e.g. Ensembl) are preserved but never used as ChEMBL IDs.
    supplied = target.chembl_target_id or (target.target_id if target.target_id and re.fullmatch(r'CHEMBL\d+', target.target_id) else None)
    if target.chembl_target_id and target.target_id and target.target_id.startswith('CHEMBL') and target.chembl_target_id != target.target_id:
        raise TargetIdentityError('Conflicting supplied ChEMBL target identifiers.')
    key = (supplied, target.target_symbol.casefold(), target.uniprot)
    cache = getattr(client, '_verified_resolutions', None) if isinstance(client, JsonClient) else None
    if cache is not None and key in cache and time.monotonic() - cache[key][0] < 900:
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
    for record in records:
        if not isinstance(record, dict):
            raise RetrievalError(f'{CHEMBL}/target/search.json: malformed target candidate.')
        symbols = [s.get('component_synonym', '')
                   for c in record.get('target_components', [])
                   for s in c.get('target_component_synonyms', [])]
        components = record.get('target_components', [])
        if (record.get('organism') == 'Homo sapiens'
                and record.get('target_type') == 'SINGLE PROTEIN'
                and len(components) == 1
                and record.get('tax_id', 9606) == 9606
                and (not target.uniprot or any(c.get('accession') == target.uniprot for c in components))
                and target.target_symbol.casefold() in [s.casefold() for s in symbols]):
            exact.append(record['target_chembl_id'])
    resolved = exact[0] if len(set(exact)) == 1 else None
    if supplied and not resolved:
        raise TargetIdentityError('Supplied ChEMBL ID does not match the exact human protein symbol and component accession.')
    if resolved and isinstance(client, JsonClient):
        if cache is None:
            client._verified_resolutions = {}
            cache = client._verified_resolutions
        cache[key] = (time.monotonic(), resolved)
    return resolved

def retrieve_compounds(client: JsonClient, target_id: str, notes: list[str] | None = None) -> list[Compound]:
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
    if len(grouped) > 15 and notes is not None:
        notes.append(f'Compound retrieval capped at 15 of {len(grouped)} curated mechanism compounds.')
    for identifier, actions in sorted(grouped.items())[:15]:
        try:
            molecule = client.get(f'{CHEMBL}/molecule/{identifier}.json')
        except RetrievalError as exc:
            if notes is None:
                raise
            notes.append(str(exc))
            continue
        compounds.append(Compound(chembl_id=identifier,
            name=molecule.get('pref_name') or identifier,
            synonyms=sorted({s['molecule_synonym'] for s in molecule.get('molecule_synonyms', [])
                             if s.get('molecule_synonym')}), mechanisms=actions,
            url=f'https://www.ebi.ac.uk/chembl/explore/compound/{identifier}'))
    return compounds

def parse_trial(record: dict, compounds: list[Compound]) -> Trial:
    protocol = record.get('protocolSection', {})
    identity = protocol.get('identificationModule', {})
    status = protocol.get('statusModule', {})
    interventions = [name for item in protocol.get('armsInterventionsModule', {}).get('interventions', [])
                     for name in [item.get('name', ''), *item.get('otherNames', [])] if name]
    exact, probable = [], []
    for compound in compounds:
        aliases = {normalize(s) for s in [compound.name, *compound.synonyms] if len(normalize(s)) >= 4}
        if any(normalize(i) in aliases for i in interventions):
            exact.append(compound.chembl_id)
        elif any(re.search(r'(?<!\w)' + re.escape(s) + r'(?!\w)', i, re.I)
                 for s in [compound.name, *compound.synonyms] if len(s) >= 5 for i in interventions):
            probable.append(compound.chembl_id)
    nct = identity['nctId']
    reason = inspect_stop_reason(record, nct)
    return Trial(nct_id=nct, title=identity.get('briefTitle', ''),
        status=status.get('overallStatus', 'UNKNOWN'), why_stopped=reason.value if reason.state == 'reported' else '',
        stop_reason=reason,
        conditions=protocol.get('conditionsModule', {}).get('conditions', []),
        interventions=interventions,
        population=protocol.get('eligibilityModule', {}).get('eligibilityCriteria', ''),
        has_results=record.get('hasResults', bool(record.get('resultsSection'))),
        compound_ids=list(dict.fromkeys(exact + probable)),
        compound_matches={**{identifier: 'probable' for identifier in probable},
                          **{identifier: 'verified' for identifier in exact}},
        outcome_records=record.get('resultsSection', {}).get('outcomeMeasuresModule', {}).get('outcomeMeasures', []),
        relationship='verified' if exact else 'probable' if probable else 'uncertain',
        match_reason='Exact normalized intervention alias' if exact else
                     'Alias within intervention text; review needed' if probable else 'No intervention alias match',
        url=f'https://clinicaltrials.gov/study/{nct}')

def retrieve_trials(client: JsonClient, target: TargetInput, compounds: list[Compound],
                    notes: list[str]) -> list[Trial]:
    found = {}
    # Separate queries avoid a long OR expression and retain per-compound provenance.
    terms = [target.target_symbol, *[c.name for c in compounds]]
    for term in dict.fromkeys(terms):
        params = {'query.cond': target.disease_name, 'query.intr': term, 'pageSize': 50, 'format': 'json'}
        try:
            for _ in range(2):
                page = client.get(CTG, params)
                for record in page.get('studies', []):
                    try:
                        trial = parse_trial(record, compounds)
                    except (KeyError, TypeError, ValueError) as exc:
                        notes.append(f'{CTG}: malformed study record skipped ({type(exc).__name__}).')
                        continue
                    trial.disease_match = 'matched' if disease_matches(' '.join(trial.conditions), target.disease_name) else 'uncertain'
                    found[trial.nct_id] = trial
                token = page.get('nextPageToken')
                if not token:
                    break
                params['pageToken'] = token
            else:
                notes.append(f'Trial search capped at 100 records for {term}.')
        except RetrievalError as exc:
            notes.append(str(exc))
    # Search results may omit fields. Fetch each unique trial's full record once
    # (the shared client caches it), then inspect actual field membership.
    for trial in found.values():
        reason = fetch_stop_reason(client, trial.nct_id)
        reason.search_value = trial.stop_reason.value
        reason.search_state = trial.stop_reason.state
        trial.stop_reason = reason
        trial.why_stopped = reason.value if reason.state == 'reported' else ''
        if reason.state in ['api_error', 'record_missing', 'invalid']:
            notes.append(f'{reason.source_url}: {reason.detail}')
    return list(found.values())
