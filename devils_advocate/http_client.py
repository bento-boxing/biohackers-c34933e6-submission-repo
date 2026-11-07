"""Bounded requests, retry/backoff and a process-local 15-minute cache."""
import copy
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class RetrievalError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code

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

    def get(self, url: str, params: dict | None = None) -> dict:
        key = (url, tuple(sorted((params or {}).items())))
        cached = self.cache.get(key)
        if cached and time.monotonic() - cached[0] < 900:
            return copy.deepcopy(cached[1])
        try:
            time.sleep(max(0, self.min_interval - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            response = self.session.get(url, params=params, timeout=(5, 20))
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object from the API')
            self.cache[key] = (time.monotonic(), data)
            return copy.deepcopy(data)
        except (requests.RequestException, ValueError) as exc:
            response = getattr(exc, 'response', None)
            raise RetrievalError(f'{url}: {type(exc).__name__}: {exc}',
                                 status_code=response.status_code if response is not None else None) from exc
