"""Regression coverage for field presence, detail hydration and display semantics."""
import json
from pathlib import Path
from unittest.mock import Mock, patch
import pytest
import requests
from devils_advocate.http_client import JsonClient, RetrievalError
from devils_advocate.models import TargetInput
from devils_advocate.stop_reasons import fetch_stop_reason, inspect_stop_reason, stop_reason_label
from devils_advocate.trial_retriever import parse_trial, retrieve_trials
from devils_advocate.devil_advocate import assess_history, classify_concern
from devils_advocate.models import Investigation
from .test_pipeline import record, FakeClient

NCT = 'NCT01739348'
TARGET = TargetInput(disease_name="Alzheimer's disease", target_symbol='BACE1')

def with_value(value):
    response = record()
    response['protocolSection']['statusModule']['whyStopped'] = value
    return response

def absent_record():
    response = record()
    del response['protocolSection']['statusModule']['whyStopped']
    return response

@pytest.mark.parametrize('response,state,value', [
    (absent_record(), 'absent', None), (with_value(''), 'empty', ''),
    (with_value('  '), 'empty', '  '), (with_value(None), 'null', None),
    (with_value(42), 'invalid', None), (with_value('Stopped for futility.'), 'reported', 'Stopped for futility.')])
def test_field_presence_is_preserved(response, state, value):
    evidence = inspect_stop_reason(response, NCT, full_record=True)
    assert evidence.state == state and evidence.value == value
    trial = parse_trial(response, [])
    trial.stop_reason = evidence
    assert ('Not reported in registry' == stop_reason_label(trial)) == (state == 'absent')
    assert evidence.source_url.endswith('/' + NCT)

@pytest.mark.parametrize('status', ['TERMINATED', 'WITHDRAWN', 'COMPLETED', 'SUSPENDED'])
def test_status_alone_never_supplies_stop_reason(status):
    response = absent_record()
    response['protocolSection']['statusModule']['overallStatus'] = status
    trial = parse_trial(response, [])
    assert trial.why_stopped == '' and classify_concern(trial.why_stopped) == 'unknown'
    assert stop_reason_label(trial) != 'Not reported in registry'  # Search alone is not confirmation.

@pytest.mark.parametrize('response', [{}, {'protocolSection': {}},
    {'protocolSection': {'identificationModule': {'nctId': NCT}}},
    {'protocolSection': {'identificationModule': {'nctId': 'NCT99999999'}, 'statusModule': {}}}])
def test_missing_modules_or_wrong_identity_are_not_missing_fields(response):
    evidence = inspect_stop_reason(response, NCT, full_record=True)
    assert evidence.state == 'invalid' and not evidence.full_record_checked

@pytest.mark.parametrize('code,state', [(404, 'record_missing'), (403, 'api_error'), (500, 'api_error'), (None, 'api_error')])
def test_missing_record_and_request_errors_are_distinct(code, state):
    evidence = fetch_stop_reason(FakeClient([RetrievalError('request failed', status_code=code)]), NCT)
    assert evidence.state == state and not evidence.full_record_checked
    trial = parse_trial(absent_record(), [])
    trial.stop_reason = evidence
    assert stop_reason_label(trial) != 'Not reported in registry'

def test_full_record_restores_reason_omitted_from_search():
    client = Mock()
    client.get.side_effect = [{'studies': [absent_record()]}, with_value('Low recruitment')]
    notes = []
    trial = retrieve_trials(client, TARGET, [], notes)[0]
    assert trial.why_stopped == 'Low recruitment' and trial.stop_reason.state == 'reported'
    assert trial.stop_reason.search_state == 'absent'
    assert trial.stop_reason.full_record_checked and not notes
    assert client.get.call_args.args == ('https://clinicaltrials.gov/api/v2/studies/' + NCT,)
    assert not client.get.call_args.kwargs  # No fields projection.

def test_full_record_authoritative_reason_and_search_value_are_both_auditable():
    client = FakeClient([{'studies': [with_value('Old reason')]}, with_value('Updated reason')])
    trial = retrieve_trials(client, TARGET, [], [])[0]
    assert trial.why_stopped == 'Updated reason'
    assert trial.stop_reason.search_value == 'Old reason'

def test_full_record_is_fetched_once_per_deduplicated_trial():
    client = Mock()
    client.get.side_effect = [{'studies': [record(), record()], 'nextPageToken': 'next'},
                             {'studies': [record()]}, absent_record()]
    trials = retrieve_trials(client, TARGET, [], [])
    assert len(trials) == 1 and client.get.call_count == 3
    assert stop_reason_label(trials[0]) == 'Not reported in registry'

def test_failed_detail_fetch_is_never_displayed_as_registry_absence():
    notes = []
    client = FakeClient([{'studies': [record('Old search reason')]}, RetrievalError('timeout')])
    trial = retrieve_trials(client, TARGET, [], notes)[0]
    assert trial.stop_reason.state == 'api_error' and trial.why_stopped == ''
    assert trial.stop_reason.search_value == 'Old search reason'
    assert notes and 'failed' in stop_reason_label(trial)
    assessment = assess_history(Investigation(target=TARGET, mode='live', trials=[trial]))[0]
    assert assessment.concern == 'unknown' and 'Not reported in registry' not in assessment.historical_evidence

def test_old_fixture_without_presence_metadata_is_not_relabelled_absent():
    trial = parse_trial(absent_record(), [])
    data = trial.model_dump(exclude={'stop_reason'})
    from devils_advocate.models import Trial
    legacy = Trial.model_validate(data)
    assert legacy.stop_reason.state == 'unverified'
    assert stop_reason_label(legacy) != 'Not reported in registry'

def test_http_error_retains_404_even_when_requests_response_is_falsy():
    client = JsonClient(min_interval=0)
    response = requests.Response()
    response.status_code = 404
    client.session.get = Mock(side_effect=requests.HTTPError('Not found', response=response))
    with pytest.raises(RetrievalError) as error:
        client.get('https://example.org/NCT00000000')
    assert error.value.status_code == 404

def test_actual_nct02565511_audit_matches_display_and_parser():
    path = Path(__file__).parents[1] / 'validation/stop_reason_audit.json'
    audit = json.loads(path.read_text(encoding='utf-8'))
    row = next(r for r in audit['records'] if r['nct_id'] == 'NCT02565511')
    assert 'whyStopped' not in row['status_module']
    assert row['stop_reason']['state'] == 'absent'
    assert row['stop_reason']['full_record_checked']
    assert row['display'] == 'Not reported in registry'
    assert row['parsed_value'] == ''

@pytest.mark.parametrize('response,expected', [(absent_record(), 'Not reported in registry'),
                                             (with_value(''), 'Registry stop-reason field is an empty string')])
def test_streamlit_stop_reason_label_includes_full_record_source(response, expected):
    from streamlit.testing.v1 import AppTest
    from devils_advocate import investigate_target
    result = investigate_target(TARGET, offline=True)
    result.trials[0].stop_reason = inspect_stop_reason(response, NCT, full_record=True)
    result.assessments = assess_history(result)
    app = AppTest.from_file(str(Path(__file__).parents[1] / 'demo_app.py')).run()
    with patch('devils_advocate.investigate_target', return_value=result):
        app.button[0].click().run(timeout=30)
    assert not app.exception
    assert any(expected in text.value for text in app.markdown)
    assert any('https://clinicaltrials.gov/api/v2/studies/' + NCT in text.value for text in app.markdown)
