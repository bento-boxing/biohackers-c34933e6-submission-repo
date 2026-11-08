import json
from types import SimpleNamespace

import pytest

from pipeline.models import Weights
from pipeline.scout import rationale as R
from pipeline.scout.pipeline import rescore, run_scout

ALLOWED = {"symbol", "rank", "components", "weights", "datatype_scores", "potent_count",
           "has_approved_drug", "literature_hits", "pmids", "tractability_sm_labels", "safety_flags"}


@pytest.fixture
def result(client):
    return run_scout("Parkinson disease", client=client)


def test_evidence_payload_has_only_allowed_keys(result):
    payload = R.evidence_payload(result, top=10)
    assert len(payload) == 10
    for row in payload:
        assert set(row) == ALLOWED


def test_rationale_key_changes_with_weights(result):
    assert R.rationale_key(result) != R.rationale_key(rescore(result, Weights(1, 0, 0, 0)))
    assert R.rationale_key(result) == R.rationale_key(rescore(result, Weights(4, 3, 2, 1)))


def test_explain_uses_cached_file_without_api(result, tmp_path, monkeypatch):
    key = R.rationale_key(result)
    (tmp_path / f"{key}.json").write_text(json.dumps({"items": [
        {"symbol": "LRRK2", "rationale": "cached text", "evidence_strength": "strong"}]}))
    monkeypatch.setattr(R, "_client", lambda: (_ for _ in ()).throw(AssertionError("api called")))
    out = R.explain(result, cache_dir=tmp_path / "w", read_dirs=(tmp_path,))
    assert out is not None
    lrrk2 = next(t for t in out.targets if t.evidence.symbol == "LRRK2")
    assert (lrrk2.rationale, lrrk2.evidence_strength) == ("cached text", "strong")


def test_explain_returns_none_without_credentials(result, tmp_path, monkeypatch):
    for k in ("AI_ENABLED", "AI_MODEL", "GEMINI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(R, "load_dotenv", lambda *a, **k: None)
    assert R._client() is None
    assert R.explain(result, cache_dir=tmp_path, read_dirs=()) is None


def test_explain_returns_none_when_gemini_incomplete(result, tmp_path, monkeypatch):
    class FakeInteractions:
        def create(self, **kw):
            return SimpleNamespace(status="incomplete", output_text="")

    monkeypatch.setattr(R, "_client", lambda: SimpleNamespace(interactions=FakeInteractions()))
    assert R.explain(result, cache_dir=tmp_path, read_dirs=()) is None
    assert list(tmp_path.glob("*.json")) == []


def test_explain_offline_never_calls_gemini(result, tmp_path, monkeypatch):
    monkeypatch.setattr(R, "_client", lambda: (_ for _ in ()).throw(AssertionError("api called")))
    assert R.explain(result, cache_dir=tmp_path, read_dirs=(), offline=True) is None


def test_explain_parses_and_caches_gemini_response(result, tmp_path, monkeypatch):
    captured = {}

    class FakeInteractions:
        def create(self, **kw):
            captured.update(kw)
            rows = json.loads(kw["input"])
            items = [{"symbol": r["symbol"], "rationale": f"because {r['symbol']}", "evidence_strength": "moderate"}
                     for r in rows]
            return SimpleNamespace(status="completed", output_text=json.dumps({"items": items}))

    monkeypatch.setenv("AI_ENABLED", "true"); monkeypatch.setenv("AI_MODEL", "gemini-test"); monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(R, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(R, "_client", lambda: SimpleNamespace(interactions=FakeInteractions()))
    out = R.explain(result, cache_dir=tmp_path, read_dirs=())
    assert out.targets[0].rationale == f"because {out.targets[0].evidence.symbol}"
    assert captured["model"] == "gemini-test" and captured["store"] is False
    assert captured["response_format"][0]["schema"] == R.RATIONALE_SCHEMA
    assert captured["system_instruction"] == R.SYSTEM_PROMPT
    assert (tmp_path / f"{R.rationale_key(result)}.json").exists()


def test_explain_skips_api_in_cache_only_mode(result, tmp_path, monkeypatch):
    monkeypatch.setenv("SCOUT_CACHE_ONLY", "1")
    monkeypatch.setattr(R, "_client", lambda: (_ for _ in ()).throw(AssertionError("api called")))
    assert R.explain(result, cache_dir=tmp_path, read_dirs=()) is None


def test_rationale_key_changes_when_evidence_changes(result):
    from dataclasses import replace
    t0 = result.targets[0]
    changed = replace(result, targets=[replace(t0, evidence=replace(t0.evidence, potent_count=t0.evidence.potent_count + 1))]
                      + result.targets[1:])
    assert R.rationale_key(result) != R.rationale_key(changed)
