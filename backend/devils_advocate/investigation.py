"""Synchronous investigation: runs the challenger to completion inside one request.

Replaces the SQLite JobStore + JobWorker pair so the workbench can run on a stateless host
(Vercel Fluid compute). Model calls still happen only when the payload says `use_ai`.
"""
import os
import time

from .ai_config import load_ai_settings
from .ai_reasoning import run_ai_reasoning
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
    try:
        target = TargetInput.model_validate(payload['selection']['target_input'])
        recorded_ai = False
        if payload['mode'] == 'offline':
            result, recorded_ai = load_recorded(target)
            timings = {'recorded_playback_seconds': round(time.monotonic() - started, 6)}
        else:
            if client is None:
                # Verified public responses persist in a per-instance SQLite cache (/tmp on Vercel);
                # up to four workers fetch registry records in parallel.
                client = owned_client = JsonClient(cache_path=data_dir('runtime') / 'public-evidence-cache.sqlite3', max_workers=4)
            budget = budget_seconds if budget_seconds is not None else default_budget_seconds(payload['use_ai'])
            with client.tracking(None, budget_seconds=budget, scope=target.model_dump(mode='json'),
                                 refresh=payload.get('refresh_evidence', False)) as measured:
                result = investigator(target, client=client)
            timings = {'retrieval': measured}
            # Gemini must finish inside the same request: clamp each call to the time left and
            # refuse to start a new (billed) call once the deadline is within reach.
            remaining = max(0, int(deadline - time.monotonic()))
            settings = load_ai_settings().model_copy(update={**payload.get('ai_policy', {}), 'enabled': payload['use_ai']})
            settings = settings.model_copy(update={'timeout_seconds': max(5, min(settings.timeout_seconds, remaining))})

            def progress(ai_calls):
                calls[:] = [c.model_dump(mode='json') for c in ai_calls]

            def past_deadline():
                return time.monotonic() > deadline - 5

            # Each Gemini call is also clamped inside the runner to the time left before `deadline`.
            result.ai = ai_reasoner(result, settings=settings, on_progress=progress, should_cancel=past_deadline,
                                    prior_art_client=client, deadline=deadline)
            if result.ai is not None and not calls:
                calls[:] = [c.model_dump(mode='json') for c in result.ai.calls]
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
        raise InvestigationFailed(str(exc)) from exc
    except ValueError as exc:
        raise InvestigationFailed(IDENTITY_FAILURE) from exc
    except Exception as exc:
        raise InvestigationFailed(GENERIC_FAILURE) from exc
    finally:
        if owned_client is not None:
            owned_client.close()
