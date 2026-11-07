"""One HTTP helper for every external call: timeouts, retries, disk cache."""
from __future__ import annotations

import hashlib
import logging
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable

import requests

from pipeline.settings import BACKEND_DIR, data_dir

log = logging.getLogger(__name__)

RETRY_BACKOFF_SECONDS = (1, 2, 4)


class CacheMiss(Exception):
    pass


class UpstreamError(Exception):
    """A data source answered, but with an error we cannot use."""


class HttpClient:
    def __init__(
        self,
        write_dir: Path | None = None,
        read_dirs: Iterable[Path] = (),
        cache_only: bool = False,
        ttl_days: int = 7,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        self.write_dir = Path(write_dir) if write_dir else None
        self.read_dirs = [Path(d) for d in read_dirs]
        if self.write_dir and self.write_dir not in self.read_dirs:
            self.read_dirs.insert(0, self.write_dir)
        self.cache_only = cache_only
        self.ttl_seconds = ttl_days * 86400
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()

    @staticmethod
    def cache_key(method: str, url: str, params: dict | None, body: dict | None) -> str:
        raw = json.dumps([method, url, params, body], sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get_json(self, url: str, params: dict | None = None) -> Any:
        return self._request("GET", url, params=params, body=None)

    def post_json(self, url: str, body: dict) -> Any:
        return self._request("POST", url, params=None, body=body)

    # internals

    def _read_cache(self, key: str) -> tuple[bool, Any]:
        for d in self.read_dirs:
            f = d / f"{key}.json"
            if not f.exists():
                continue
            try:
                entry = json.loads(f.read_text())
            except (OSError, ValueError):
                continue  # unreadable or half-written entry: treat as a miss
            if d == self.write_dir and time.time() - entry["ts"] > self.ttl_seconds:
                continue
            return True, entry["data"]
        return False, None

    def _write_cache(self, key: str, method: str, url: str, params, body, data) -> None:
        if not self.write_dir:
            return
        try:
            self.write_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", dir=self.write_dir, suffix=".tmp", delete=False) as f:
                json.dump({"ts": time.time(), "method": method, "url": url,
                           "params": params, "body": body, "data": data}, f)
            Path(f.name).replace(self.write_dir / f"{key}.json")
        except OSError as e:
            # A cache is an optimisation: a read-only or full disk must never fail the request.
            log.warning("cache write skipped for %s: %s", url, e)

    def _request(self, method: str, url: str, params: dict | None, body: dict | None) -> Any:
        key = self.cache_key(method, url, params, body)
        hit, data = self._read_cache(key)
        if hit:
            return data
        if self.cache_only:
            raise CacheMiss(f"cache-only mode and no cached response for {method} {url}")
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = self.session.request(method, url, params=params, json=body, timeout=self.timeout)
                if resp.status_code >= 500:
                    raise requests.HTTPError(f"{resp.status_code} from {url}")
                resp.raise_for_status()
                data = resp.json()
                self._write_cache(key, method, url, params, body, data)
                return data
            except requests.HTTPError as e:
                if resp.status_code < 500:
                    raise
                last_exc = e
            except (requests.ConnectionError, requests.Timeout) as e:
                last_exc = e
            if attempt < self.max_retries - 1:
                time.sleep(RETRY_BACKOFF_SECONDS[min(attempt, len(RETRY_BACKOFF_SECONDS) - 1)])
        assert last_exc is not None
        raise last_exc


def default_client() -> HttpClient:
    write_dir = Path(os.environ["SCOUT_CACHE_DIR"]) if os.environ.get("SCOUT_CACHE_DIR") else data_dir("cache")
    demo = BACKEND_DIR / "data" / "demo_cache"
    return HttpClient(
        write_dir=write_dir,
        read_dirs=[write_dir, demo],
        cache_only=os.environ.get("SCOUT_CACHE_ONLY") == "1",
    )
