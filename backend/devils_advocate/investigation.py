"""Synchronous investigation: runs the challenger to completion inside one request.

Replaces the SQLite JobStore + JobWorker pair so the workbench can run on a stateless host
(Vercel Fluid compute). Model calls still happen only when the payload says `use_ai`.
"""
import json
import os
import re
import time

from .ai_client import GeminiRunner
from .ai_config import load_ai_settings
from .ai_reasoning import plan_followups_with_gemini, run_ai_reasoning
from .devil_advocate import investigate_target
from .experiment_designer import propose_experiment
from .http_client import JsonClient, RetrievalDeadlineExceeded
from .models import TargetInput
from .workbench_demo import RecordedTargetUnavailable, load_recorded
from .build_info import runtime_info
from pipeline.settings import data_dir

GENERIC_FAILURE = ('Investigation could not complete. Public sources or backend configuration may be '
                   'unavailable; private exception details were withheld.')
IDENTITY_FAILURE = ('Input identity or recorded-demo selection could not be validated. '
                    'No alternate target was substituted.')


class InvestigationFailed(RuntimeError):
    """User-safe failure; str(exc) may be shown in the UI."""


def progress_path(token: str):
    if not token or not re.fullmatch(r'[a-f0-9]{8,64}', token):
        return None
    return data_dir('runtime') / 'progress' / f'{token}.json'


class ProgressWriter:
    """Best-effort stage progress for the browser to poll while the one request runs.

    Written under the runtime directory; on a multi-instance host the poller may hit another
    instance and sees 'unavailable', never invented progress."""
    def __init__(self, token: str | None):
        self.path = progress_path(token or '')
        self.stages: list[dict] = []
        self.started = time.time()

    def stage(self, name: str) -> None:
        now = time.time()
        if self.stages and self.stages[-1].get('finished_at') is None:
            self.stages[-1]['finished_at'] = now
            self.stages[-1]['seconds'] = round(now - self.stages[-1]['started_at'], 3)
        self.stages.append({'name': name, 'started_at': now, 'finished_at': None})
        self.write()

    def finish(self, state: str) -> None:
        if self.stages and self.stages[-1].get('finished_at') is None:
            now = time.time()
            self.stages[-1]['finished_at'] = now
            self.stages[-1]['seconds'] = round(now - self.stages[-1]['started_at'], 3)
        self.write(state)

    def write(self, state: str = 'running') -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({'state': state, 'started_at': self.started, 'updated_at': time.time(),
                                             'stage': self.stages[-1]['name'] if self.stages else 'Starting',
                                             'stages': self.stages}), encoding='utf-8')
        except OSError:
            self.path = None  # read-only host: progress simply becomes unavailable


def read_progress(token: str) -> dict | None:
    path = progress_path(token)
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def default_budget_seconds(use_ai: bool = False) -> int:
    """Fit one Vercel request (300 s): retrieval + up to 120 s of Gemini when AI is on."""
    override = os.getenv('RESEARCH_RETRIEVAL_BUDGET_SECONDS')
    if override:
        return int(override)
    return 150 if use_ai else 240


def default_request_budget_seconds() -> int:
    """Whole-request deadline; Vercel kills the function at 300 s."""
    return int(os.getenv('RESEARCH_REQUEST_BUDGET_SECONDS', '280'))


def run_investigation(payload: dict, *, investigator=investigate_target, ai_reasoner=run_ai_reasoning,
                      client: JsonClient | None = None, budget_seconds: int | None = None,
                      request_budget_seconds: int | None = None) -> dict:
    calls: list[dict] = []
    owned_client = None
    started = time.monotonic()
    request_budget = request_budget_seconds if request_budget_seconds is not None else default_request_budget_seconds()
    deadline = started + request_budget
    progress_writer = ProgressWriter(payload.get('progress_token'))
    try:
        target = TargetInput.model_validate(payload['selection']['target_input'])
        recorded_ai = False
        if payload['mode'] == 'offline':
            progress_writer.stage('Loading recorded evidence')
            result, recorded_ai = load_recorded(target)
            timings = {'recorded_playback_seconds': round(time.monotonic() - started, 6)}
        else:
            if client is None:
                # Verified public responses persist in a per-instance SQLite cache (/tmp on Vercel);
                # up to four workers fetch registry records in parallel.
                client = owned_client = JsonClient(cache_path=data_dir('runtime') / 'public-evidence-cache.sqlite3', max_workers=4)
            budget = budget_seconds if budget_seconds is not None else default_budget_seconds(payload['use_ai'])
            # Gemini must finish inside the same request: clamp each call to the time left and
            # refuse to start a new (billed) call once the deadline is within reach.
            settings = load_ai_settings().model_copy(update={**payload.get('ai_policy', {}), 'enabled': payload['use_ai']})

            def progress(ai_calls):
                calls[:] = [c.model_dump(mode='json') for c in ai_calls]
                if ai_calls:
                    progress_writer.stage('Gemini: ' + ai_calls[-1].role)

            def past_deadline():
                return time.monotonic() > deadline - 5

            # Optional, explicitly authorised evidence-planning call: shares the paid-call budget with
            # the reasoning roles and only ever yields search terms. Off by default.
            runner = None
            planner_hook = None
            if payload['use_ai'] and settings.planning_call:
                runner = GeminiRunner(settings, on_progress=progress, should_cancel=past_deadline, deadline=deadline)
                planner_hook = lambda result, plan: plan_followups_with_gemini(runner, result, plan)
            rounds = payload.get('max_followup_rounds')
            investigator_kwargs = {}
            if rounds is not None or planner_hook is not None or payload.get('progress_token'):
                investigator_kwargs = {'max_followup_rounds': rounds, 'planner_hook': planner_hook, 'on_stage': progress_writer.stage}
            with client.tracking(None, budget_seconds=budget, scope=target.model_dump(mode='json'),
                                 refresh=payload.get('refresh_evidence', False)) as measured:
                result = investigator(target, client=client, **investigator_kwargs)
            timings = {'retrieval': measured, 'stages': dict(getattr(result, 'stage_timings', {}) or {}),
                       'refresh_evidence': bool(payload.get('refresh_evidence', False))}
            remaining = max(0, int(deadline - time.monotonic()))
            settings = settings.model_copy(update={'timeout_seconds': max(5, min(settings.timeout_seconds, remaining))})
            if runner is not None:
                runner.settings = settings
            reasoner_kwargs = {'runner': runner} if runner is not None else {}
            # Each Gemini call is also clamped inside the runner to the time left before `deadline`.
            result.ai = ai_reasoner(result, settings=settings, on_progress=progress, should_cancel=past_deadline,
                                    prior_art_client=client, deadline=deadline, **reasoner_kwargs)
            if runner is not None:
                try:
                    runner.close()
                except Exception:
                    pass
            if result.ai is not None and not calls:
                calls[:] = [c.model_dump(mode='json') for c in result.ai.calls]
            if result.ai is not None:
                timings['stages'].update({'gemini_' + re.sub(r'\W+', '_', c.role.lower()): c.duration_seconds for c in result.ai.calls if c.duration_seconds is not None})
                if result.ai.prior_art_check.get('duration_seconds') is not None:
                    timings['stages']['prior_art_checks'] = result.ai.prior_art_check['duration_seconds']
        progress_writer.finish('completed')
        return {'investigation': result.model_dump(mode='json'),
                'experiment': propose_experiment(result).model_dump(mode='json'),
                'recorded_ai': recorded_ai, 'selection': payload['selection'], 'timings': timings,
                'provenance': {**runtime_info(), 'retrieved_at': time.time(),
                               'source_mode': 'recorded' if payload['mode'] == 'offline' else 'live_public_api',
                               'source_counts': {'trials': len(result.trials), 'publications': len(result.publications),
                                                 'compounds': len(result.compounds)},
                               'cache_hits': timings.get('retrieval', {}).get('cache_hits', 0)},
                'weights': payload['weights'], 'mode': payload['mode'], 'calls': calls}
    except (RetrievalDeadlineExceeded, RecordedTargetUnavailable) as exc:
        progress_writer.finish('failed')
        raise InvestigationFailed(str(exc)) from exc
    except ValueError as exc:
        progress_writer.finish('failed')
        raise InvestigationFailed(IDENTITY_FAILURE) from exc
    except Exception as exc:
        progress_writer.finish('failed')
        raise InvestigationFailed(GENERIC_FAILURE) from exc
    finally:
        if owned_client is not None:
            owned_client.close()
