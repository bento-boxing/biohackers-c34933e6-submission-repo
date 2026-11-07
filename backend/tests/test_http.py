import json
import time
from pathlib import Path

import pytest
import requests

from pipeline.http import CacheMiss, HttpClient


class FakeResponse:
    def __init__(self, status, data):
        self.status_code = status
        self._data = data

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


def patch_session(monkeypatch, responses):
    calls = []

    def fake_request(self, method, url, **kw):
        calls.append((method, url, kw))
        r = responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(requests.Session, "request", fake_request)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    return calls


def test_get_json_writes_cache_then_reads_without_network(tmp_path, monkeypatch):
    calls = patch_session(monkeypatch, [FakeResponse(200, {"a": 1})])
    c = HttpClient(write_dir=tmp_path)
    assert c.get_json("https://x/y", {"q": 1}) == {"a": 1}
    patch_session(monkeypatch, [RuntimeError("network used")])
    assert c.get_json("https://x/y", {"q": 1}) == {"a": 1}
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_cache_only_miss_raises_cache_miss_with_url(tmp_path):
    c = HttpClient(read_dirs=[tmp_path], cache_only=True)
    with pytest.raises(CacheMiss) as e:
        c.get_json("https://example.org/missing")
    assert "https://example.org/missing" in str(e.value)


def test_read_dirs_order_first_hit_wins(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    key = HttpClient.cache_key("GET", "https://x/z", None, None)
    for d, v in ((a, "first"), (b, "second")):
        (d / f"{key}.json").write_text(json.dumps({"ts": time.time(), "data": v}))
    c = HttpClient(read_dirs=[a, b], cache_only=True)
    assert c.get_json("https://x/z") == "first"


def test_expired_write_dir_entry_is_refetched(tmp_path, monkeypatch):
    key = HttpClient.cache_key("GET", "https://x/old", None, None)
    (tmp_path / f"{key}.json").write_text(
        json.dumps({"ts": time.time() - 8 * 86400, "data": "stale"})
    )
    calls = patch_session(monkeypatch, [FakeResponse(200, "fresh")])
    c = HttpClient(write_dir=tmp_path, ttl_days=7)
    assert c.get_json("https://x/old") == "fresh"
    assert len(calls) == 1


def test_retries_on_500_then_succeeds(tmp_path, monkeypatch):
    calls = patch_session(
        monkeypatch,
        [FakeResponse(500, None), FakeResponse(500, None), FakeResponse(200, {"ok": 1})],
    )
    c = HttpClient(write_dir=tmp_path)
    assert c.post_json("https://x/p", {"b": 1}) == {"ok": 1}
    assert len(calls) == 3


def test_cache_write_failure_is_not_fatal(tmp_path, monkeypatch):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")  # mkdir under a file raises OSError, like a read-only filesystem
    patch_session(monkeypatch, [FakeResponse(200, {"ok": 1})])
    c = HttpClient(write_dir=blocker / "cache")
    assert c.get_json("https://x/ro") == {"ok": 1}


def test_corrupt_cache_entry_is_treated_as_miss(tmp_path, monkeypatch):
    key = HttpClient.cache_key("GET", "https://x/bad", None, None)
    (tmp_path / f"{key}.json").write_text("{truncated")
    patch_session(monkeypatch, [FakeResponse(200, "fresh")])
    c = HttpClient(write_dir=tmp_path)
    assert c.get_json("https://x/bad") == "fresh"
