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
from .workbench_demo import load_recorded

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


def run_investigation(payload: dict, *, investigator=investigate_target, ai_reasoner=run_ai_reasoning,
                      client: JsonClient | None = None, budget_seconds: int | None = None) -> dict:
    calls: list[dict] = []
    try:
        target = TargetInput.model_validate(payload['selection']['target_input'])
        recorded_ai = False
        started = time.monotonic()
        if payload['mode'] == 'offline':
            result, recorded_ai = load_recorded(target)
            timings = {'recorded_playback_seconds': round(time.monotonic() - started, 6)}
        else:
            client = client or JsonClient()
            budget = budget_seconds if budget_seconds is not None else default_budget_seconds(payload['use_ai'])
            with client.tracking(None, budget_seconds=budget) as measured:
                result = investigator(target, client=client)
            timings = {'retrieval': measured}
            settings = load_ai_settings().model_copy(update={**payload.get('ai_policy', {}), 'enabled': payload['use_ai']})

            def progress(ai_calls):
                calls[:] = [c.model_dump(mode='json') for c in ai_calls]

            result.ai = ai_reasoner(result, settings=settings, on_progress=progress, should_cancel=lambda: False)
            if result.ai is not None and not calls:
                calls[:] = [c.model_dump(mode='json') for c in result.ai.calls]
        return {'investigation': result.model_dump(mode='json'),
                'experiment': propose_experiment(result).model_dump(mode='json'),
                'recorded_ai': recorded_ai, 'selection': payload['selection'], 'timings': timings,
                'weights': payload['weights'], 'mode': payload['mode'], 'calls': calls}
    except RetrievalDeadlineExceeded as exc:
        raise InvestigationFailed(str(exc)) from exc
    except ValueError as exc:
        raise InvestigationFailed(IDENTITY_FAILURE) from exc
    except Exception as exc:
        raise InvestigationFailed(GENERIC_FAILURE) from exc
