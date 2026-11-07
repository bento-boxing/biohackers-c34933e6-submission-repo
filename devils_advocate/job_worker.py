"""Local SQLite worker; model calls are isolated from frontend HTTP lifetime."""
import threading
from .ai_config import load_ai_settings
from .ai_reasoning import run_ai_reasoning
from .devil_advocate import investigate_target
from .experiment_designer import propose_experiment
from .http_client import JsonClient
from .job_store import JobStore
from .models import TargetInput
from .workbench_demo import load_recorded

class JobWorker:
    def __init__(self, store: JobStore, *, investigator=investigate_target, ai_reasoner=run_ai_reasoning):
        self.store = store
        self.investigator = investigator
        self.ai_reasoner = ai_reasoner
        self.stop = threading.Event()
        self.client = JsonClient()  # Reuse verified resolution + HTTP caches across jobs.

    def execute(self, job):
        identifier, payload = job['id'], job['payload']
        heartbeat_stop = threading.Event()
        def heartbeat():
            while not heartbeat_stop.wait(10):
                self.store.heartbeat(identifier)
        heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
        heartbeat_thread.start()
        try:
            self.store.progress(identifier, 'Retrieving recorded evidence' if payload['mode'] == 'offline' else 'Retrieving live biomedical evidence')
            target = TargetInput.model_validate(payload['selection']['target_input'])
            recorded_ai = False
            if payload['mode'] == 'offline':
                result, recorded_ai = load_recorded(target)
            else:
                result = self.investigator(target, client=self.client)
                if self.store.cancelled(identifier):
                    self.store.finish(identifier, 'cancelled')
                    return
                settings = load_ai_settings().model_copy(update={**payload.get('ai_policy', {}), 'enabled': payload['use_ai']})
                def progress(calls):
                    self.store.progress(identifier, calls[-1].role, [c.model_dump(mode='json') for c in calls])
                result.ai = self.ai_reasoner(result, settings=settings, on_progress=progress,
                    should_cancel=lambda: self.store.cancelled(identifier))
            if self.store.cancelled(identifier):
                self.store.finish(identifier, 'cancelled', error='Stopped before further calls. An in-flight provider request may still have been billed.')
                return
            report = {'investigation': result.model_dump(mode='json'),
                      'experiment': propose_experiment(result).model_dump(mode='json'),
                      'recorded_ai': recorded_ai, 'selection': payload['selection'],
                      'weights': payload['weights'], 'mode': payload['mode']}
            self.store.progress(identifier, 'Report ready for researcher review')
            self.store.finish(identifier, 'completed', result=report)
        except ValueError:
            self.store.finish(identifier, 'failed', error='Input identity or recorded-demo selection could not be validated. No alternate target was substituted.')
        except Exception:
            self.store.finish(identifier, 'failed', error='Investigation could not complete. Public sources or worker configuration may be unavailable; private exception details were withheld.')
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=1)

    def run(self):
        while not self.stop.is_set():
            job = self.store.claim()
            if job:
                self.execute(job)
            else:
                self.stop.wait(0.5)

    def start(self):
        thread = threading.Thread(target=self.run, daemon=True, name='research-worker')
        thread.start()
        return thread
