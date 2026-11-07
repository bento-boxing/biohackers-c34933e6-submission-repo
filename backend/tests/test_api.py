import json

import pytest

from pipeline.api import create_app
from pipeline.http import HttpClient
from tests.conftest import DEMO_CACHE


@pytest.fixture
def api(tmp_path):
    app = create_app(client=HttpClient(read_dirs=[DEMO_CACHE], cache_only=True),
                     approvals_path=tmp_path / "approvals.jsonl",
                     shortlists_path=tmp_path / "shortlists.jsonl")
    app.config["TESTING"] = True
    return app.test_client()


def scout(api, disease="Parkinson disease"):
    return api.post("/api/scout", json={"disease": disease})


def test_health(api):
    assert api.get("/api/health").get_json()["status"] == "ok"


def test_scout_returns_run_id_and_25_targets_with_components(api):
    r = scout(api)
    assert r.status_code == 200
    body = r.get_json()
    assert body["run_id"] and body["disease"]["id"] == "MONDO_0005180"
    assert body["cache_only"] is True
    assert body["default_weights"] == {"genetic": 0.4, "association": 0.3, "druggability": 0.2, "literature": 0.1}
    assert len(body["targets"]) == 25
    t = body["targets"][0]
    assert set(t["components"]) == {"genetic", "association", "druggability", "literature"}
    for k in ("target_id", "symbol", "name", "uniprot", "chembl_target_id", "potent_count",
              "has_approved_drug", "literature_hits", "pmids", "safety_flags", "tractability_sm_labels",
              "open_targets_url"):
        assert k in t
    assert t["open_targets_url"].startswith("https://platform.opentargets.org/target/ENSG")


def test_scout_unknown_disease_404(api):
    r = scout(api, "zzqxv-not-a-disease")
    assert r.status_code == 404 and "zzqxv-not-a-disease" in r.get_json()["error"]


def approval_body(run, symbol="LRRK2", weights=None):
    w = weights or run["default_weights"]
    t = next(x for x in run["targets"] if x["symbol"] == symbol)
    c = t["components"]
    total = sum(w[k] * c[k] for k in c) / sum(w.values())
    return {"run_id": run["run_id"], "symbol": symbol, "weights": w, "reason": "strong genetics",
            "scores": {**{k: round(c[k], 4) for k in c}, "total": round(total, 4)}}


def test_approval_round_trip_get_newest_first(api):
    run = scout(api).get_json()
    r1 = api.post("/api/approvals", json=approval_body(run, "LRRK2"))
    assert r1.status_code == 200, r1.get_json()
    assert r1.get_json()["symbol"] == "LRRK2" and r1.get_json()["chembl_target_id"] == "CHEMBL1075104"
    api.post("/api/approvals", json=approval_body(run, "SNCA"))
    got = api.get("/api/approvals").get_json()
    assert [a["symbol"] for a in got] == ["SNCA", "LRRK2"]


def test_approval_score_mismatch_400_writes_nothing(api, tmp_path):
    run = scout(api).get_json()
    body = approval_body(run)
    body["scores"]["total"] = 0.123
    r = api.post("/api/approvals", json=body)
    assert r.status_code == 400 and "do not match" in r.get_json()["error"]
    assert api.get("/api/approvals").get_json() == []


def test_approval_unknown_run_404(api):
    run = scout(api).get_json()
    body = approval_body(run)
    body["run_id"] = "nope"
    r = api.post("/api/approvals", json=body)
    assert r.status_code == 404 and "nope" in r.get_json()["error"]


def test_rationale_endpoint_unavailable_without_key(api, monkeypatch):
    from pipeline import api as api_mod
    monkeypatch.setattr(api_mod, "explain", lambda result, **kw: None)
    run = scout(api).get_json()
    r = api.post("/api/rationale", json={"run_id": run["run_id"], "weights": run["default_weights"]})
    assert r.status_code == 200 and r.get_json()["available"] is False


def test_rationale_endpoint_returns_items(api, monkeypatch):
    from dataclasses import replace
    from pipeline import api as api_mod

    def fake_explain(result, **kw):
        ts = [replace(t, rationale="r", evidence_strength="weak") for t in result.targets[:10]] + result.targets[10:]
        return replace(result, targets=ts)

    monkeypatch.setattr(api_mod, "explain", fake_explain)
    run = scout(api).get_json()
    w = {"genetic": 1, "association": 0, "druggability": 0, "literature": 0}
    r = api.post("/api/rationale", json={"run_id": run["run_id"], "weights": w}).get_json()
    assert len(r["rationales"]) == 10 and r["rationales"][0]["evidence_strength"] == "weak"
    assert r["weights"]["genetic"] == 1.0 and r["run_id"] == run["run_id"]
