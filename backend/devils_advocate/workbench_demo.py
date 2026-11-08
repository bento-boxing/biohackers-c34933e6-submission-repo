"""Recorded public evidence playback for the workbench. Never calls an API."""
import json
from pathlib import Path
from .models import AIReport, Investigation, TargetInput
from .devil_advocate import analyze, assess_history
from .evidence_verifier import verify_claims
from .experiment_designer import propose_experiment

ROOT = Path(__file__).parent / 'fixtures'

class RecordedTargetUnavailable(ValueError):
    """The recorded demo has no investigation for this target/disease pair (user-safe message)."""


def load_recorded(target: TargetInput) -> tuple[Investigation, bool]:
    symbol = target.target_symbol.upper()
    accepted = {'BACE1': {"alzheimer's disease", 'alzheimer disease'},
                'LRRK2': {"parkinson's disease", 'parkinson disease'}}
    if symbol not in accepted or target.disease_name.casefold() not in accepted[symbol]:
        raise RecordedTargetUnavailable(
            f'The recorded demo only contains investigations for LRRK2 (Parkinson disease) and BACE1 '
            f"(Alzheimer's disease); there is no recording for {target.target_symbol} in {target.disease_name}. "
            'Switch the data source to Live APIs to investigate it. No recorded data was substituted.')
    path = ROOT / f'workbench_{symbol.lower()}.json'
    result = Investigation.model_validate_json(path.read_text(encoding='utf-8'))
    if target.chembl_target_id and target.chembl_target_id != result.resolved_target_id:
        raise ValueError('Supplied ChEMBL ID differs from the recorded target; no recorded substitution made.')
    known_accessions = {'LRRK2':'Q5S007','BACE1':'P56817'}
    if target.uniprot and target.uniprot != known_accessions[symbol]:
        raise ValueError('Supplied UniProt accession differs from the recorded target.')
    if target.target_id and target.target_id.startswith('ENSG'):
        known = {'LRRK2': 'ENSG00000188906', 'BACE1': 'ENSG00000186318'}
        if target.target_id != known[symbol]:
            raise ValueError('Supplied gene ID differs from the recorded target.')
    result.target = target
    result.mode = 'offline'
    result.resolution_status = 'resolved'
    result.claims, result.revisions = verify_claims(result, analyze(result))
    result.assessments = assess_history(result)
    recorded_ai = False
    if symbol == 'BACE1':
        report = json.loads((ROOT / 'workbench_bace1_ai.json').read_text(encoding='utf-8'))
        result.ai = AIReport.model_validate(report)
        result.ai.warnings.insert(0, 'RECORDED AI PLAYBACK: historical Gemini output. No new model calls were made for this job.')
        recorded_ai = True
    return result, recorded_ai
