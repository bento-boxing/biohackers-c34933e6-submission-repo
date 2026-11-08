import json
from unittest.mock import Mock

import pytest

from devils_advocate.models import AICall, AIReport, Investigation, TargetInput
from devils_advocate.server import create_app
from devils_advocate.target_scout_adapter import flatten_scout_selection
from devils_advocate.workbench_demo import load_recorded

HEADERS = {'X-Research-Mode': 'offline'}
LIVE = {'X-Research-Mode': 'live'}
DECISION_TEXT = 'Offline test decision: explore evidence only; not a clinical approval.'


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('WORKBENCH_SECRET', 'test-secret')
    return create_app(tmp_path)


def scout(client):
    response = client.post('/api/scout', headers=HEADERS, json={'disease': 'Parkinson disease', 'n': 25})
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def investigate(client, run, **updates):
    body = {'run': run, 'symbol': 'LRRK2', **updates}
    return client.post('/api/investigations', json=body, headers=HEADERS)


def completed_job(app):
    client = app.test_client(); run = scout(client)
    response = investigate(client, run)
    assert response.status_code == 200, response.get_json()
    job = response.get_json(); assert job['state'] == 'completed', job['error']
    return client, run, job


def test_actual_nested_lrrk2_handoff_preserves_ids_scores_and_provenance(app):
    run = scout(app.test_client()); flat = flatten_scout_selection(run, 'LRRK2')
    assert flat['target_input']['target_id'] == 'ENSG00000188906'
    assert flat['target_input']['chembl_target_id'] == 'CHEMBL1075104'
    assert flat['target_input']['uniprot'] == 'Q5S007'
    assert flat['target_input']['disease_id'] == 'MONDO_0005180'
    assert flat['evidence_pmids'] and flat['cache_only']
    assert 'association_score' not in flat['target_input']


def test_offline_investigation_never_calls_live_retrieval_or_gemini(app):
    app.config['INVESTIGATOR'] = Mock(side_effect=AssertionError('live forbidden'))
    app.config['AI_REASONER'] = Mock(side_effect=AssertionError('paid forbidden'))
    client, run, job = completed_job(app)
    assert job['result']['investigation']['mode'] == 'offline'
    assert job['result']['investigation']['target']['target_symbol'] == 'LRRK2'
    assert not job['result']['recorded_ai'] and job['decisions'] == []
    assert job['selection']['run_id'] == run['run_id'] and 'weighted_score' in job['selection']
    assert len(job['job_id']) == 32


def test_bace1_playback_is_explicitly_recorded_and_never_validates_wrong_identity():
    result, recorded = load_recorded(TargetInput(disease_name="Alzheimer's disease", target_symbol='BACE1', chembl_target_id='CHEMBL4822'))
    assert result.mode == 'offline' and recorded and result.ai.status == 'completed'
    assert 'RECORDED AI PLAYBACK' in result.ai.warnings[0]
    with pytest.raises(ValueError): load_recorded(TargetInput(disease_name='Parkinson disease', target_symbol='LRRK2', chembl_target_id='CHEMBL203'))
    with pytest.raises(ValueError): load_recorded(TargetInput(disease_name='Other', target_symbol='EGFR'))


def decision_body(job, run, **updates):
    target = next(t for t in run['targets'] if t['symbol'] == 'LRRK2')
    return {'decision_id': 'decision-approval', 'job_id': job['job_id'], 'action': 'approve_screening',
            'rationale': DECISION_TEXT, 'report': job['result'], 'target': target, **updates}


def test_human_approval_gates_existing_screening(app):
    client, run, job = completed_job(app)
    assert client.post('/api/approvals', headers=HEADERS, json={}).status_code == 403
    assert client.post('/api/research-decisions', headers=HEADERS, json=decision_body(job, run)).status_code == 400
    approved = client.post('/api/research-decisions', headers=HEADERS, json=decision_body(job, run, confirmed=True))
    assert approved.status_code == 200, approved.get_json()
    approval = approved.get_json()['approval']
    assert approval['symbol'] == 'LRRK2' and approval['signature'] and approval['reason'] == DECISION_TEXT
    assert abs(approval['scores']['total'] - job['selection']['weighted_score']) < 1e-6
    screened = client.post('/api/screen', headers=HEADERS, json={'approval': approval})
    assert screened.status_code == 200, screened.get_json()
    assert screened.get_json()['compounds']


def test_screen_rejects_unsigned_or_tampered_approval(app):
    client, run, job = completed_job(app)
    approval = client.post('/api/research-decisions', headers=HEADERS, json=decision_body(job, run, confirmed=True)).get_json()['approval']
    assert client.post('/api/screen', headers=HEADERS, json={'approval_ts': 'forged'}).status_code in (400, 403)
    assert client.post('/api/screen', headers=HEADERS, json={'approval': {k: v for k, v in approval.items() if k != 'signature'}}).status_code == 403
    assert client.post('/api/screen', headers=HEADERS, json={'approval': {**approval, 'chembl_target_id': 'CHEMBL203'}}).status_code == 403


def test_non_approval_decision_is_echoed_without_approval(app):
    client, run, job = completed_job(app)
    body = decision_body(job, run, action='investigate', decision_id='decision-investigate')
    response = client.post('/api/research-decisions', headers=HEADERS, json=body)
    assert response.status_code == 200 and response.get_json()['action'] == 'investigate'
    assert 'approval' not in response.get_json() and response.get_json()['mode'] == 'offline'


def test_mode_origin_consent_and_input_validation(app):
    client = app.test_client(); run = scout(client)
    assert client.post('/api/scout', headers={**HEADERS, 'Origin': 'https://untrusted.example'}, json={'disease': 'Parkinson disease'}).status_code == 403
    assert client.post('/api/scout', headers={**HEADERS, 'Origin': 'http://localhost:3000'}, json={'disease': 'Parkinson disease'}).status_code == 200
    assert investigate(client, run, weights={'unknown': 1}).status_code == 400
    assert investigate(client, run, symbol='FAKEGENE123').status_code == 400
    assert client.post('/api/investigations', headers=HEADERS, json={'use_ai': False}).status_code == 400
    assert client.post('/api/investigations', headers=LIVE, json={'target_input': {'disease_name': 'Example', 'target_symbol': 'EGFR'}, 'use_ai': True, 'paid_authorized': False}).status_code == 400
    assert client.post('/api/scout', headers={'X-Research-Mode': 'weird'}, json={'disease': 'x'}).status_code == 400


def test_vercel_origin_is_allowed_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv('VERCEL_URL', 'my-app-abc123.vercel.app')
    monkeypatch.setenv('WORKBENCH_ORIGINS', 'https://workbench.example.org')
    client = create_app(tmp_path).test_client()
    for origin in ['https://my-app-abc123.vercel.app', 'https://workbench.example.org']:
        assert client.post('/api/scout', headers={**HEADERS, 'Origin': origin}, json={'disease': 'Parkinson disease'}).status_code == 200, origin


def test_removed_job_routes_are_gone(app):
    client = app.test_client()
    assert client.get('/api/investigations/abc', headers=HEADERS).status_code == 404
    assert client.get('/api/investigations', headers=HEADERS).status_code == 404
    assert client.get('/api/workbench/runs/abc', headers=HEADERS).status_code == 404
    assert client.post('/api/investigations/abc/cancel', headers=HEADERS).status_code == 404


def test_live_mode_does_not_read_recorded_scout_cache(app):
    live = app.config['SCOUT_APPS']['live'].config['HTTP_CLIENT']
    recorded = app.config['SCOUT_APPS']['offline'].config['HTTP_CLIENT']
    assert not live.cache_only
    assert all('demo_cache' not in str(path) for path in live.read_dirs)
    assert recorded.cache_only and recorded.write_dir is None
    assert any('demo_cache' in str(path) for path in recorded.read_dirs)
    cfg = app.test_client().get('/api/workbench/config', headers=HEADERS).get_json()
    assert 'api_key' not in json.dumps(cfg) and cfg['server'] == 'Flask (stateless)'


def test_live_investigation_preserves_failed_ai_report_without_discarding_retrieval(app, monkeypatch):
    from devils_advocate.ai_config import AISettings
    from pydantic import SecretStr
    config = AISettings(enabled=True, model='test-model', api_key=SecretStr('SECRET-TEST-ONLY'))
    monkeypatch.setattr('devils_advocate.server.load_ai_settings', lambda: config)
    monkeypatch.setattr('devils_advocate.investigation.load_ai_settings', lambda: config)
    payload = {'target_input': {'disease_name': 'Non-small-cell lung cancer', 'target_symbol': 'EGFR', 'chembl_target_id': 'CHEMBL203'}, 'use_ai': True, 'paid_authorized': True}
    app.config['INVESTIGATOR'] = Mock(return_value=Investigation(target=TargetInput.model_validate(payload['target_input']), mode='live', resolved_target_id='CHEMBL203', resolution_status='resolved'))
    app.config['AI_REASONER'] = Mock(return_value=AIReport(enabled=True, model='test-model', status='failed', calls=[AICall(role='Devils Advocate', success=False, error='Gemini response timed out.')], warnings=['Gemini response timed out.']))
    response = app.test_client().post('/api/investigations', headers=LIVE, json=payload)
    finished = response.get_json()
    assert response.status_code == 200 and finished['state'] == 'completed', finished
    assert finished['result']['investigation']['ai']['status'] == 'failed'
    assert finished['result']['investigation']['resolved_target_id'] == 'CHEMBL203'
    assert finished['progress']['calls'][0]['role'] == 'Devils Advocate'
    assert 'AI-generated' not in finished['result']['experiment']['status']
    assert 'SECRET-TEST-ONLY' not in json.dumps(finished)


def test_failed_investigation_returns_state_failed_with_sanitized_error(app):
    app.config['INVESTIGATOR'] = Mock(side_effect=RuntimeError('boom secret'))
    response = app.test_client().post('/api/investigations', headers=LIVE, json={'target_input': {'disease_name': 'Example', 'target_symbol': 'EGFR'}})
    job = response.get_json()
    assert response.status_code == 200 and job['state'] == 'failed' and job['result'] is None
    assert 'boom' not in job['error'] and job['error']


def test_unrelated_or_invalid_live_targets_use_given_identifiers(app):
    client = app.test_client()
    for symbol, identifier, status in [('EGFR', 'CHEMBL203', 'resolved'), ('FAKEGENE123', None, 'unknown')]:
        value = {'disease_name': 'Example', 'target_symbol': symbol, 'chembl_target_id': identifier}
        investigator = Mock(return_value=Investigation(target=TargetInput.model_validate(value), mode='live', resolved_target_id=identifier, resolution_status=status))
        app.config['INVESTIGATOR'] = investigator; app.config['AI_REASONER'] = Mock(return_value=None)
        response = client.post('/api/investigations', headers=LIVE, json={'target_input': value})
        assert response.status_code == 200 and response.get_json()['state'] == 'completed'
        assert investigator.call_args.args[0].chembl_target_id == identifier


def test_rationale_route_is_forwarded_to_scout_backend(app, monkeypatch):
    import pipeline.api as scout_api
    monkeypatch.setattr(scout_api, 'explain', lambda result, **kw: None)
    client = app.test_client(); run = scout(client)
    response = client.post('/api/rationale', headers=HEADERS, json={'run_id': run['run_id'], 'run': run, 'weights': run['default_weights']})
    assert response.status_code == 200, response.get_json()
    assert response.get_json()['available'] is False
