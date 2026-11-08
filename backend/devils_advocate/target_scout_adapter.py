"""Target Scout handoff; association score is metadata, never success probability."""
import re
from pydantic import BaseModel, Field, ConfigDict
from .models import TargetInput
from .http_client import JsonClient, RetrievalError
from .trial_retriever import resolve_target

class ScoutPayload(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    disease: str = Field(min_length=1, max_length=200)
    target: str = Field(min_length=1, max_length=80)
    disease_id: str | None = None
    target_id: str | None = None
    chembl_target_id: str | None = None
    uniprot: str | None = None
    association_score: float | None = Field(default=None, ge=0, le=1)
    evidence_pmids: list[str] = Field(default_factory=list)

class Handoff(BaseModel):
    target_input: TargetInput
    resolved_chembl_id: str | None = None
    association_score: float | None = None
    evidence_pmids: list[str] = Field(default_factory=list)
    validation_notes: list[str] = Field(default_factory=list)

def adapt_target_scout(payload: dict | ScoutPayload) -> TargetInput:
    scout = ScoutPayload.model_validate(payload)
    return TargetInput(disease_name=scout.disease, disease_id=scout.disease_id,
                       target_symbol=scout.target, target_id=scout.target_id,
                       chembl_target_id=scout.chembl_target_id, uniprot=scout.uniprot)

def flatten_scout_selection(run: dict, symbol: str) -> dict:
    """Map the actual nested Scout API response without losing provenance."""
    selected = next((t for t in run['targets'] if t['symbol'] == symbol), None)
    if selected is None:
        raise ValueError('Selected target is not present in the Scout run.')
    flat = {'disease': run['disease']['name'], 'disease_id': run['disease']['id'],
            'target': selected['symbol'], 'target_id': selected['target_id'],
            'chembl_target_id': selected.get('chembl_target_id'), 'uniprot': selected.get('uniprot'),
            'association_score': selected['components']['association'], 'evidence_pmids': selected.get('pmids', [])}
    return {'target_input': adapt_target_scout(flat).model_dump(mode='json'),
            'association_score': flat['association_score'], 'evidence_pmids': flat['evidence_pmids'],
            'components': selected['components'], 'safety_flags': selected.get('safety_flags', []),
            'run_id': run['run_id'], 'cache_only': run['cache_only']}

def validate_target_scout(payload: dict | ScoutPayload, *, client: JsonClient | None = None) -> Handoff:
    """Optional live validation; mismatched verified IDs are rejected, not replaced."""
    scout = ScoutPayload.model_validate(payload)
    target = adapt_target_scout(scout)
    client = client or JsonClient()
    notes = ['Association score retained as upstream ranking metadata, not a probability of therapeutic success.',
             'Upstream PMIDs are unverified leads, not independently verified evidence.',
             'Disease identifier preserved; disease ontology equivalence has not been verified.']
    identifier = target.target_id
    try:
        if identifier and identifier.startswith('ENSG'):
            if not re.fullmatch(r'ENSG\d{11}', identifier):
                raise ValueError('Malformed Ensembl gene identifier.')
            record = client.get(f'https://rest.ensembl.org/lookup/id/{identifier}', {'content-type': 'application/json'})
            if record.get('species') != 'homo_sapiens' or record.get('display_name', '').casefold() != target.target_symbol.casefold():
                raise ValueError('Target Scout identifier and human gene symbol disagree; handoff rejected.')
            notes.append('Ensembl human gene identifier and symbol agree.')
        elif identifier and not re.fullmatch(r'CHEMBL\d+', identifier):
            notes.append('Target identifier namespace not supported for validation; value preserved.')
        resolved = resolve_target(client, target)
        if identifier and identifier.startswith('CHEMBL') and resolved != identifier:
            raise ValueError('ChEMBL identifier does not resolve to the supplied human target symbol.')
        notes.append('Exact human ChEMBL target resolved.' if resolved else 'No unambiguous ChEMBL target resolution.')
    except RetrievalError as exc:
        resolved = None
        notes.append(f'Identifier validation unavailable: {exc}')
    return Handoff(target_input=target, resolved_chembl_id=resolved,
                   association_score=scout.association_score, evidence_pmids=scout.evidence_pmids,
                   validation_notes=notes)
