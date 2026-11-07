"""Bounded requests, retry/backoff and a process-local 15-minute cache."""
import copy
import time
from contextlib import contextmanager
from urllib.parse import urlsplit
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class RetrievalError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code

class RetrievalDeadlineExceeded(RuntimeError):
    pass

class JsonClient:
    def __init__(self, min_interval: float = 0.35):
        self.session = requests.Session()
        self.session.headers['User-Agent'] = 'Agentverse-Target-Challenger/0.1'
        self.session.mount('https://', HTTPAdapter(max_retries=Retry(
            total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=['GET'], respect_retry_after_header=False)))
        self.cache = {}
        self.min_interval = min_interval
        self.last_request = 0.0
        self._observer = None
        self._deadline = None
        self._should_cancel = None
        self._profile = None
        self._profile_start = None

    @contextmanager
    def tracking(self, observer=None, *, budget_seconds=300, should_cancel=None):
        previous = (self._observer, self._deadline, self._should_cancel, self._profile, self._profile_start)
        started = time.monotonic()
        self._profile_start = started
        self._observer, self._deadline, self._should_cancel = observer, started + budget_seconds, should_cancel
        self._profile = {'started_at': time.time(), 'total_seconds': 0., 'requests': 0, 'cache_hits': 0,
                         'completed_requests': 0, 'source_seconds': {}}
        profile = self._profile
        try:
            yield profile
        finally:
            profile['total_seconds'] = round(time.monotonic() - started, 6)
            self._observer, self._deadline, self._should_cancel, self._profile, self._profile_start = previous

    def _check_budget(self):
        if self._should_cancel and self._should_cancel():
            raise RetrievalDeadlineExceeded('Retrieval stopped before a further request after cancellation was observed.')
        if self._deadline is not None and time.monotonic() >= self._deadline:
            raise RetrievalDeadlineExceeded('Biomedical retrieval exceeded its time budget; no model calls were started.')

    def _emit(self, url, state, **values):
        parts = urlsplit(url)
        source = ('ClinicalTrials.gov' if parts.hostname == 'clinicaltrials.gov' else
                  'ChEMBL' if '/chembl/' in parts.path else
                  'Europe PMC' if 'europepmc' in parts.path else 'Public API')
        event = {'source': source, 'operation': parts.path, 'state': state, 'at': time.time(),
                 'retry_policy_max_attempts': 3, **values}
        if self._profile is not None:
            if state == 'request': self._profile['requests'] += 1
            if state == 'cache_hit': self._profile['cache_hits'] += 1
            if state == 'completed': self._profile['completed_requests'] += 1
            if state in ['completed', 'failed']:
                totals = self._profile['source_seconds']
                totals[source] = round(totals.get(source, 0.) + values.get('duration_seconds', 0.), 6)
            event['profile'] = copy.deepcopy(self._profile)
            event['profile']['total_seconds'] = round(time.monotonic() - self._profile_start, 6)
        if self._observer:
            self._observer(event)

    def get(self, url: str, params: dict | None = None) -> dict:
        self._check_budget()
        key = (url, tuple(sorted((params or {}).items())))
        cached = self.cache.get(key)
        if cached and time.monotonic() - cached[0] < 900:
            self._emit(url, 'cache_hit')
            return copy.deepcopy(cached[1])
        started = time.monotonic()
        self._emit(url, 'request', started_at=time.time())
        try:
            time.sleep(max(0, self.min_interval - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            response = self.session.get(url, params=params, timeout=(5, 20))
            response.raise_for_status()
            self._check_budget()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object from the API')
            self.cache[key] = (time.monotonic(), data)
            history = getattr(getattr(getattr(response, 'raw', None), 'retries', None), 'history', None)
            self._emit(url, 'completed', status_code=response.status_code,
                       retries_observed=len(history) if isinstance(history, (list,tuple)) else None,
                       duration_seconds=round(time.monotonic() - started, 6))
            return copy.deepcopy(data)
        except RetrievalDeadlineExceeded:
            self._emit(url, 'failed', duration_seconds=round(time.monotonic() - started, 6),
                       error_type='RetrievalDeadlineExceeded')
            raise
        except (requests.RequestException, ValueError) as exc:
            response = getattr(exc, 'response', None)
            self._emit(url, 'failed', status_code=response.status_code if response is not None else None,
                       duration_seconds=round(time.monotonic() - started, 6), error_type=type(exc).__name__)
            raise RetrievalError(f'{url}: {type(exc).__name__}: {exc}',
                                 status_code=response.status_code if response is not None else None) from exc
