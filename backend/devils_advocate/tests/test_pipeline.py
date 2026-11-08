import pytest
from devils_advocate import investigate_target, propose_experiment
from devils_advocate.devil_advocate import classify_concern, retrieve_publications
from devils_advocate.evidence_verifier import verify_claims
from devils_advocate.models import Claim, Compound, Investigation, TargetInput
from devils_advocate.trial_retriever import parse_trial, resolve_target, retrieve_compounds, retrieve_trials
from devils_advocate.http_client import RetrievalError

TARGET = TargetInput(disease_name="Alzheimer's disease", target_symbol='BACE1')

class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
    def get(self, url, params=None):
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response

def record(reason='', status='TERMINATED', intervention='MK-8931'):
    return {'protocolSection': {'identificationModule': {'nctId': 'NCT01739348'},
            'statusModule': {'overallStatus': status, 'whyStopped': reason},
            'armsInterventionsModule': {'interventions': [{'name': intervention}]}}}

@pytest.mark.parametrize('text,expected', [
    ('TERMINATED', 'unknown'), ('COMPLETED', 'unknown'), ('futility', 'efficacy'),
    ('safety concerns', 'safety'), ('recruitment difficulties', 'operational'),
    ('business decision', 'operational'), ('futility and safety concerns', 'other'),
    ('No reason supplied', 'unknown'),
    # Phrasing taken from live ClinicalTrials.gov records, including the registry's own misspelling.
    ('Poor enrollment', 'operational'), ('low enrollment', 'operational'), ('Sponsor decision', 'unknown'),
    ('The study was terminated due to hepatoxicity of compound', 'safety'), ('lack of clinical benefit', 'efficacy'),
    ('See termination reason in detailed description.', 'unknown')])
def test_classification(text, expected):
    assert classify_concern(text) == expected

def test_compound_alias_matching():
    c = Compound(chembl_id='CHEMBL1', name='VERUBECESTAT', synonyms=['MK-8931'], url='https://example.org')
    assert parse_trial(record(intervention='MK 8931'), [c]).relationship == 'verified'
    assert parse_trial(record(intervention='MK-8931 oral tablet'), [c]).relationship == 'probable'
    assert parse_trial(record(intervention='MK-89312'), [c]).relationship == 'uncertain'

def test_target_resolution_requires_exact_human_symbol():
    good = {'target_chembl_id': 'CHEMBL4822', 'organism': 'Homo sapiens', 'target_type': 'SINGLE PROTEIN',
            'target_components': [{'target_component_synonyms': [{'component_synonym': 'BACE1'}]}]}
    assert resolve_target(FakeClient([{'targets': [good]}]), TARGET) == 'CHEMBL4822'
    assert resolve_target(FakeClient([{'targets': [{**good, 'organism': 'Mus musculus'}]}]), TARGET) is None

def test_compounds_preserve_ids_synonyms_mechanism():
    client = FakeClient([{'mechanisms': [{'molecule_chembl_id': 'CHEMBL1', 'mechanism_of_action': 'Inhibitor'}]},
                         {'pref_name': 'Drug', 'molecule_synonyms': [{'molecule_synonym': 'Alias'}]}])
    result = retrieve_compounds(client, 'CHEMBL4822')
    assert result[0].synonyms == ['Alias']
    assert result[0].chembl_id == 'CHEMBL1'

def test_empty_and_failed_retrieval():
    result = investigate_target(TARGET, client=FakeClient([{'targets': []}, {'studies': []}, {'resultList': {}}]))
    assert result.conclusion.startswith('INSUFFICIENT COVERAGE')
    assert not result.claims
    notes = []
    assert retrieve_trials(FakeClient([RetrievalError('unavailable')]), TARGET, [], notes) == []
    assert notes == ['unavailable']

def test_trial_pagination_and_deduplication():
    trials = retrieve_trials(FakeClient([{'studies': [record()], 'nextPageToken': 'next'},
                                        {'studies': [record()]}, record()]), TARGET, [], [])
    assert len(trials) == 1
    assert trials[0].why_stopped == ''

def test_publication_identifiers():
    pubs = retrieve_publications(FakeClient([{'resultList': {'result': [
        {'source': 'MED', 'id': '123', 'title': "BACE1 in Alzheimer's disease", 'abstractText': '<p>Text</p>', 'doi': '10.1/test'}]}}]), TARGET)
    assert pubs[0].identifier == 'MED:123'
    assert pubs[0].abstract == 'Text'

def test_verifier_rejects_fabricated_source_and_revises_fact():
    trial = parse_trial(record('futility'), [])
    investigation = Investigation(target=TARGET, mode='live', trials=[trial])
    claim = Claim(claim_id='one', text='Target is invalid', kind='fact', source_id=trial.nct_id,
                  source_field='why_stopped', excerpt='futility', relevance='test')
    accepted, revisions = verify_claims(investigation, [claim, claim.model_copy(update={'source_id': 'NCT99999999'})])
    assert len(accepted) == 1 and accepted[0].text == 'futility'
    assert len(revisions) == 2

def test_offline_serialization_and_experiment():
    result = investigate_target(TARGET, offline=True)
    assert result.mode == 'offline'
    assert result.trials
    assert all(c.verified for c in result.claims)
    assert Investigation.model_validate_json(result.model_dump_json()) == result
    experiment = propose_experiment(result)
    assert len(experiment.competing_explanations) == 2
    assert 'not performed' in experiment.status
    with pytest.raises(ValueError):
        investigate_target({'disease_name': 'Other', 'target_symbol': 'OTHER'}, offline=True)

def test_evaluation_missing_predictions_count_as_wrong():
    from devils_advocate.evaluation import score
    labels = [{'id': 'a', 'concern': 'unknown', 'relevant_failure': False, 'unsupported': True}]
    assert score(labels, [])['concern_accuracy'] == 0

def test_evaluation_bundle_shares_sources_and_flags_unsupported_claim():
    from devils_advocate.evaluation import prepare_evaluation
    result = Investigation(target=TARGET, mode='live', trials=[parse_trial(record('futility'), [])])
    claim = Claim(claim_id='fake', text='Invented result', kind='fact', source_id='MED:000',
                  source_field='abstract', excerpt='Invented result', relevance='test')
    bundle = prepare_evaluation(result, [claim])
    assert bundle['system_predictions'][-1]['unsupported'] is True
    assert 'claims' not in bundle['sources']
    assert len(bundle['cases']) == 2
