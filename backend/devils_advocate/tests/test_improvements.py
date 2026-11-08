import json
from pathlib import Path
from unittest.mock import patch
import pytest
from streamlit.testing.v1 import AppTest
from devils_advocate import investigate_target
from devils_advocate.devil_advocate import analyze, assess_history, classify_concern
from devils_advocate.evidence_verifier import verify_claims
from devils_advocate.models import Claim, Compound, Investigation, Publication, TargetInput
from devils_advocate.target_scout_adapter import adapt_target_scout, validate_target_scout
from devils_advocate.ui_state import invalidate_results
from devils_advocate.http_client import RetrievalError
from .test_pipeline import FakeClient, record
from devils_advocate.trial_retriever import parse_trial

ROOT = Path(__file__).parents[1]
TARGET = TargetInput(disease_name="Alzheimer's disease", target_symbol='BACE1')

def test_invalid_target_does_not_retrieve_disease_only_evidence():
    result = investigate_target({'disease_name': "Alzheimer's disease", 'target_symbol': 'FAKEGENE123'},
                                client=FakeClient([{'targets': []}]))
    assert not result.trials and not result.publications and not result.retrieval_errors
    assert result.conclusion.startswith('INSUFFICIENT COVERAGE')

def test_failure_stays_live_and_never_loads_offline_fixture():
    result = investigate_target(TARGET, client=FakeClient([RetrievalError('https://example.org: Timeout')]))
    assert result.mode == 'live' and result.retrieval_errors
    assert not result.compounds and not result.trials and not result.publications

def test_offline_never_uses_network():
    with patch('devils_advocate.http_client.JsonClient.get', side_effect=AssertionError('network forbidden')):
        result = investigate_target(TARGET, offline=True)
    assert result.mode == 'offline'

@pytest.mark.parametrize('text', ['BACE1 reduced assay background in the methods.',
                                  'BACE1 inhibition improved a biomarker in mice.',
                                  'BACE1 was associated with no clinical benefit.'])
def test_unadjudicated_publication_is_neutral(text):
    pub = Publication(identifier='MED:1', title='Study methods', abstract=text, url='https://europepmc.org/article/MED/1')
    result = Investigation(target=TARGET, mode='live', publications=[pub])
    claims, _ = verify_claims(result, analyze(result))
    assert all(c.stance == 'context' for c in claims)
    assert all(c.uncertainty and c.source_url for c in claims)

def test_verifier_downgrades_injected_supporting_stance():
    pub = Publication(identifier='MED:1', title='Methods reduced background', url='https://europepmc.org/article/MED/1')
    claim = Claim(claim_id='a', text=pub.title, kind='fact', stance='supporting', source_id=pub.identifier,
                  source_field='title', excerpt=pub.title, relevance='test')
    accepted, objections = verify_claims(Investigation(target=TARGET, mode='live', publications=[pub]), [claim])
    assert accepted[0].stance == 'context' and objections

def test_missing_citation_is_rejected():
    claim = Claim(claim_id='a', text='No benefit', kind='fact', source_id='', source_field='abstract', excerpt='No benefit', relevance='test')
    accepted, objections = verify_claims(Investigation(target=TARGET, mode='live'), [claim])
    assert not accepted and objections

def test_each_compound_trial_link_retains_its_own_match_strength():
    first = Compound(chembl_id='CHEMBL1', name='Drugone', url='https://example.org/1')
    second = Compound(chembl_id='CHEMBL2', name='Drugtwo', url='https://example.org/2')
    data = record(intervention='Drugone')
    data['protocolSection']['armsInterventionsModule']['interventions'].append({'name': 'Drugtwo tablet'})
    trial = parse_trial(data, [first, second])
    assert trial.compound_matches == {'CHEMBL1': 'verified', 'CHEMBL2': 'probable'}

def test_publications_without_visible_target_and_disease_are_excluded():
    from devils_advocate.devil_advocate import retrieve_publications
    assert retrieve_publications(FakeClient([{'resultList': {'result': [
        {'source': 'MED', 'id': '1', 'title': 'Methods reduce assay background', 'abstractText': 'Unrelated text'}]}}]), TARGET) == []

def test_malformed_trial_does_not_hide_valid_records():
    from devils_advocate.trial_retriever import retrieve_trials
    notes = []
    trials = retrieve_trials(FakeClient([{'studies': [{}, record()]}, record()]), TARGET, [], notes)
    assert len(trials) == 1 and any('malformed' in n for n in notes)

@pytest.mark.parametrize('reason,expected', [('No safety concerns', 'unknown'), ('without toxicity', 'unknown'),
                                           ('failed to demonstrate target engagement', 'unknown'), ('not due to futility', 'unknown'),
                                           ('Sponsor decision, not related to safety concerns', 'unknown'),
                                           ('Slow Accrual', 'operational'), ('COVID-19 Pandemic Measures', 'operational')])
def test_negation_and_engagement_are_not_failure_efficacy(reason, expected):
    assert classify_concern(reason) == expected

def test_history_operational_retains_hypothesis_but_never_validates_target():
    trial = parse_trial(record('recruitment difficulties'), [])
    trial.relationship = 'verified'
    trial.disease_match = 'matched'
    assessment = assess_history(Investigation(target=TARGET, mode='live', trials=[trial]))[0]
    assert assessment.recommendation == 'retain' and assessment.source_ids == [trial.nct_id]
    assert 'Unknown' in assessment.target_engagement

def test_input_and_mode_changes_clear_decision_and_evidence():
    state = {'result': 'old', 'experiment': 'old', 'researcher_decision': 'Stop', 'decision_rationale': 'old'}
    invalidate_results(state, ('disease', 'BACE1', True))
    assert state == {'request_key': ('disease', 'BACE1', True)}
    state['result'] = 'new'
    invalidate_results(state, ('disease', 'BACE1', True))
    assert state['result'] == 'new'
    invalidate_results(state, ('disease', 'BACE1', False))
    assert 'result' not in state

def test_target_scout_fixture_preserves_ids_and_optional_fields():
    payload = json.loads((ROOT / 'fixtures/target_scout_lrrk2.json').read_text())
    result = adapt_target_scout(payload)
    assert result.target_id == 'ENSG00000188906' and result.disease_id == 'EFO_0002508'
    assert 'association_score' not in result.model_dump()
    assert adapt_target_scout({'disease': 'Example', 'target': 'TEST'}).target_id is None

def test_target_scout_rejects_verified_identifier_symbol_mismatch():
    with pytest.raises(ValueError, match='disagree'):
        validate_target_scout({'disease': 'Example', 'target': 'LRRK2', 'target_id': 'ENSG00000188906'},
                              client=FakeClient([{'species': 'homo_sapiens', 'display_name': 'EGFR'}]))

def test_target_scout_unavailable_validation_preserves_identifier():
    handoff = validate_target_scout({'disease': 'Example', 'target': 'LRRK2', 'target_id': 'ENSG00000188906'},
                                   client=FakeClient([RetrievalError('offline')]))
    assert handoff.target_input.target_id == 'ENSG00000188906'
    assert any('unavailable' in note for note in handoff.validation_notes)

def test_ui_clears_stale_results_and_formats_experiment():
    app = AppTest.from_file(str(ROOT / 'demo_app.py')).run()
    app.button[0].click().run(timeout=30)
    assert not app.exception
    assert any(s.value == 'Research question' for s in app.subheader)
    assert any(e.label == 'Raw experiment JSON' for e in app.expander)
    app.text_input[1].set_value('LRRK2').run()
    assert 'result' not in app.session_state
    app.button[0].click().run()
    assert app.error and 'result' not in app.session_state

def test_ui_live_error_cannot_display_offline_evidence():
    app = AppTest.from_file(str(ROOT / 'demo_app.py')).run()
    app.button[0].click().run(timeout=30)
    app.toggle[0].set_value(False).run()
    assert 'result' not in app.session_state
    with patch('devils_advocate.investigate_target', side_effect=ValueError('Network unavailable')):
        app.button[0].click().run()
    assert app.error and 'result' not in app.session_state

def test_recorded_benchmark_runs_without_live_response_bundles():
    from devils_advocate.benchmark import main
    with patch('sys.argv', ['benchmark']):
        main()
    report = json.loads((ROOT / 'validation/benchmark_report.json').read_text())
    assert report['pipeline']['cases'] == 9
    assert len(report['labels']) == 9
