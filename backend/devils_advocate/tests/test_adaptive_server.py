"""Request path for the adaptive loop: refresh flag, round override, progress polling, optional planning call. No paid calls."""
import json
from unittest.mock import Mock

from devils_advocate.ai_config import AISettings
from devils_advocate.ai_reasoning import PlannerSuggestions, plan_followups_with_claude
from devils_advocate.investigation import ProgressWriter, read_progress, run_investigation
from devils_advocate.models import EvidenceNeed, EvidencePlan, Investigation, TargetInput
from devils_advocate.server import create_app
from .test_ai import ScriptedRunner
from .test_investigation import EGFR, payload

LIVE = {'X-Research-Mode': 'live'}


def test_refresh_rounds_and_progress_token_reach_the_investigator(tmp_path, monkeypatch):
    monkeypatch.setenv('SCOUT_DATA_DIR', str(tmp_path))
    target = TargetInput.model_validate(EGFR)
    seen = {}

    def investigator(target_input, *, client, **kwargs):
        seen['refresh'] = client.refresh
        seen['kwargs'] = kwargs
        kwargs['on_stage']('Retrieving literature')
        result = Investigation(target=target_input, mode='live', resolved_target_id='CHEMBL203', resolution_status='resolved')
        result.stage_timings = {'literature': 1.5}
        return result
    body = {**payload(EGFR, 'live'), 'refresh_evidence': True, 'max_followup_rounds': 1, 'progress_token': 'abcdef1234567890'}
    report = run_investigation(body, investigator=investigator, ai_reasoner=Mock(return_value=None))
    assert seen['refresh'] is True and seen['kwargs']['max_followup_rounds'] == 1 and seen['kwargs']['planner_hook'] is None
    assert report['timings']['refresh_evidence'] is True and report['timings']['stages']['literature'] == 1.5
    progress = read_progress('abcdef1234567890')
    assert progress['state'] == 'completed' and [s['name'] for s in progress['stages']] == ['Retrieving literature']
    assert progress['stages'][0]['seconds'] >= 0


def test_investigator_without_adaptive_arguments_is_called_the_old_way():
    investigator = Mock(return_value=Investigation(target=TargetInput.model_validate(EGFR), mode='live', resolved_target_id='CHEMBL203', resolution_status='resolved'))
    run_investigation(payload(EGFR, 'live'), investigator=investigator, ai_reasoner=Mock(return_value=None))
    assert set(investigator.call_args.kwargs) == {'client'}


def test_progress_writer_tolerates_missing_token_and_bad_tokens(tmp_path, monkeypatch):
    monkeypatch.setenv('SCOUT_DATA_DIR', str(tmp_path))
    writer = ProgressWriter(None)
    writer.stage('x'); writer.finish('completed')  # no path, no error
    assert read_progress('not-a-token') is None and read_progress('abcdef1234567890') is None


def test_progress_endpoint_reports_unavailable_without_inventing_progress(tmp_path, monkeypatch):
    monkeypatch.setenv('WORKBENCH_SECRET', 'test-secret')
    monkeypatch.setenv('SCOUT_DATA_DIR', str(tmp_path))
    app = create_app(tmp_path)
    client = app.test_client()
    assert client.get('/api/investigations/progress/zzz', headers=LIVE).status_code == 400
    missing = client.get('/api/investigations/progress/abcdef1234567890', headers=LIVE).get_json()
    assert missing['available'] is False
    ProgressWriter('abcdef1234567890').stage('Retrieving registry trials')
    found = client.get('/api/investigations/progress/abcdef1234567890', headers=LIVE).get_json()
    assert found['available'] is True and found['stage'] == 'Retrieving registry trials' and found['state'] == 'running'
    import time
    assert abs(found['now'] - time.time()) < 5 and found['now'] >= found['stages'][0]['started_at']  # server clock for ageing the running stage


def test_server_accepts_refresh_rounds_and_token_and_exposes_adaptive_config(tmp_path, monkeypatch):
    monkeypatch.setenv('WORKBENCH_SECRET', 'test-secret')
    monkeypatch.setenv('ADAPTIVE_MAX_ROUNDS', '3')
    seen = {}

    def investigator(target_input, *, client, **kwargs):
        seen.update(kwargs, refresh=client.refresh)
        return Investigation(target=target_input, mode='live', resolved_target_id='CHEMBL203', resolution_status='resolved')
    app = create_app(tmp_path, investigator=investigator, ai_reasoner=Mock(return_value=None))
    client = app.test_client()
    config = client.get('/api/workbench/config', headers=LIVE).get_json()
    assert config['adaptive']['max_rounds'] == 3 and config['adaptive']['planning_call'] is False
    response = client.post('/api/investigations', headers=LIVE, json={'target_input': EGFR, 'refresh_evidence': True, 'max_followup_rounds': 0, 'progress_token': '0123456789abcdef'})
    assert response.status_code == 200, response.get_json()
    assert seen['refresh'] is True and seen['max_followup_rounds'] == 0
    assert response.get_json()['progress']['timings']['refresh_evidence'] is True
    assert client.post('/api/investigations', headers=LIVE, json={'target_input': EGFR, 'max_followup_rounds': 9}).status_code == 400
    assert client.post('/api/investigations', headers=LIVE, json={'target_input': EGFR, 'progress_token': 'BAD TOKEN'}).status_code == 400


def test_planning_call_is_off_by_default_and_yields_queries_only_when_authorized():
    settings = AISettings(enabled=True, model='m', planning_call=False)
    assert settings.planning_call is False
    result = Investigation(target=TargetInput.model_validate(EGFR), mode='live', resolved_target_id='CHEMBL203', resolution_status='resolved')
    plan = EvidencePlan(stage='clinical', needs=[EvidenceNeed(key='positive_clinical', label='x', status='unmet'), EvidenceNeed(key='approved_therapy', label='y', status='satisfied')])
    runner = ScriptedRunner([PlannerSuggestions.model_validate({'suggestions': [
        {'need_key': 'positive_clinical', 'terms': ['FLAURA', 'osimertinib first-line'], 'rationale': 'named study'},
        {'need_key': 'approved_therapy', 'terms': ['ignored because satisfied']},
        {'need_key': 'positive_clinical', 'terms': ['osimertinib was approved in 2018 and works']}]})])
    suggestions = plan_followups_with_claude(runner, result, plan)
    assert [s['need_key'] for s in suggestions] == ['positive_clinical', 'positive_clinical']
    assert suggestions[0]['terms'] == ['FLAURA', 'osimertinib first-line'] and suggestions[0]['origin'].endswith('queries only')
    assert runner.calls[0].role == 'Evidence Planner' and 'QUERIES ONLY' in runner.payloads[0][0]
    # Nothing in the investigation changed: a suggestion is not evidence.
    assert result.publications == [] and result.trials == []


def test_planning_hook_is_wired_only_with_use_ai_and_flag(monkeypatch):
    seen = {}

    def investigator(target_input, *, client, **kwargs):
        seen.update(kwargs)
        return Investigation(target=target_input, mode='live', resolved_target_id='CHEMBL203', resolution_status='resolved')
    body = {**payload(EGFR, 'live', use_ai=True), 'ai_policy': {'planning_call': True, 'model': 'm', 'enabled': True}}
    reasoner = Mock(return_value=None)
    run_investigation(body, investigator=investigator, ai_reasoner=reasoner)
    assert callable(seen['planner_hook']) and reasoner.call_args.kwargs['runner'] is not None
    seen.clear()
    run_investigation({**payload(EGFR, 'live', use_ai=False), 'ai_policy': {'planning_call': True}}, investigator=investigator, ai_reasoner=Mock(return_value=None))
    assert seen == {}  # no planner hook, no extra kwargs: deterministic path unchanged
