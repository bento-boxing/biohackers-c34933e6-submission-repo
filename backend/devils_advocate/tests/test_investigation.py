from unittest.mock import Mock

import pytest

from devils_advocate.http_client import RetrievalDeadlineExceeded
from devils_advocate.investigation import InvestigationFailed, run_investigation
from devils_advocate.models import AICall, AIReport, Investigation, TargetInput

LRRK2 = {'disease_name': 'Parkinson disease', 'disease_id': 'MONDO_0005180', 'target_symbol': 'LRRK2',
         'target_id': 'ENSG00000188906', 'chembl_target_id': 'CHEMBL1075104', 'uniprot': 'Q5S007'}
EGFR = {'disease_name': 'Non-small-cell lung cancer', 'target_symbol': 'EGFR', 'chembl_target_id': 'CHEMBL203'}


def payload(target, mode, use_ai=False):
    return {'selection': {'target_input': target, 'run_id': None, 'cache_only': mode == 'offline', 'origin': 'manual'},
            'mode': mode, 'use_ai': use_ai, 'weights': {'genetic': 0.4, 'association': 0.3, 'druggability': 0.2, 'literature': 0.1},
            'ai_policy': {}}


def test_offline_lrrk2_playback_builds_report_without_live_calls():
    report = run_investigation(payload(LRRK2, 'offline'),
                               investigator=Mock(side_effect=AssertionError('live forbidden')),
                               ai_reasoner=Mock(side_effect=AssertionError('paid forbidden')))
    assert report['investigation']['target']['target_symbol'] == 'LRRK2'
    assert report['mode'] == 'offline' and report['calls'] == [] and not report['recorded_ai']
    assert report['experiment']['question'] and 'recorded_playback_seconds' in report['timings']


def test_live_report_keeps_failed_ai_and_resolution():
    target = TargetInput.model_validate(EGFR)
    investigator = Mock(return_value=Investigation(target=target, mode='live', resolved_target_id='CHEMBL203', resolution_status='resolved'))
    failed = AIReport(enabled=True, model='test-model', status='failed',
                      calls=[AICall(role='Devils Advocate', success=False, error='timed out')], warnings=['timed out'])
    report = run_investigation(payload(EGFR, 'live', use_ai=True), investigator=investigator, ai_reasoner=Mock(return_value=failed))
    assert report['investigation']['ai']['status'] == 'failed'
    assert report['investigation']['resolved_target_id'] == 'CHEMBL203'
    assert 'retrieval' in report['timings']


def test_pipeline_exception_becomes_sanitized_failure():
    with pytest.raises(InvestigationFailed) as exc:
        run_investigation(payload(EGFR, 'live'), investigator=Mock(side_effect=RuntimeError('boom secret')), ai_reasoner=Mock())
    assert 'boom' not in str(exc.value) and 'could not complete' in str(exc.value)


def test_deadline_exceeded_message_is_surfaced():
    with pytest.raises(InvestigationFailed) as exc:
        run_investigation(payload(EGFR, 'live'), investigator=Mock(side_effect=RetrievalDeadlineExceeded('budget exhausted')), ai_reasoner=Mock())
    assert 'budget exhausted' in str(exc.value)


def test_gemini_phase_is_cancelled_and_clamped_when_the_request_deadline_is_near():
    target = TargetInput.model_validate(EGFR)
    investigator = Mock(return_value=Investigation(target=target, mode='live', resolved_target_id='CHEMBL203', resolution_status='resolved'))
    reasoner = Mock(return_value=None)
    run_investigation(payload(EGFR, 'live', use_ai=True), investigator=investigator, ai_reasoner=reasoner,
                      budget_seconds=5, request_budget_seconds=0)
    kwargs = reasoner.call_args.kwargs
    assert kwargs['should_cancel']() is True  # deadline already passed: no paid call may start
    assert kwargs['settings'].timeout_seconds == 5  # clamped to the floor, never 120 s past the deadline
