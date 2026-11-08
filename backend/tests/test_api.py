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


def test_screen_endpoint_lrrk2(api, tmp_path):
    from pipeline.audit import append_jsonl
    from tests.test_screening_pipeline import approval
    a = approval()
    append_jsonl(tmp_path / "approvals.jsonl", a.__dict__)
    r = api.post("/api/screen", json={"approval_id": a.approval_id})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["approval"]["symbol"] == "LRRK2" and body["structure"]["mean_plddt"] > 0
    assert len(body["compounds"]) >= 50 and body["coverage"]["partial"] is True and body["notes"]
    c = body["compounds"][0]
    for k in ("chembl_id", "name", "best_pchembl", "assay_type", "max_phase", "is_approved", "mw", "alogp",
              "hbd", "hba", "psa", "ro5_violations", "lipinski_pass", "chembl_url"):
        assert k in c
    assert api.post("/api/screen", json={"approval_id": "nope"}).status_code == 404
    # timestamps are not identifiers: a body that only names a timestamp is refused
    assert api.post("/api/screen", json={"approval_ts": a.ts}).status_code == 400


def test_screen_selects_the_exact_approval_when_two_were_created_in_the_same_second(api, tmp_path):
    from pipeline.audit import append_jsonl
    from tests.test_screening_pipeline import approval
    first = approval()
    second = approval(chembl_target_id=None, uniprot=None)
    second.approval_id, second.symbol, second.target_id = "appr-second", "TP53", "ENSG00000141510"
    assert first.ts == second.ts and first.approval_id != second.approval_id
    append_jsonl(tmp_path / "approvals.jsonl", first.__dict__)
    append_jsonl(tmp_path / "approvals.jsonl", second.__dict__)
    r = api.post("/api/screen", json={"approval_id": first.approval_id})
    assert r.status_code == 200 and r.get_json()["approval"]["symbol"] == "LRRK2"
    assert r.get_json()["approval"]["approval_id"] == first.approval_id
    r = api.post("/api/screen", json={"approval_id": second.approval_id})
    assert r.status_code == 200 and r.get_json()["approval"]["symbol"] == "TP53"


def test_server_issued_approvals_get_distinct_ids_even_in_the_same_second(api):
    run = scout(api).get_json()
    t = run["targets"][0]
    body = {"run_id": run["run_id"], "symbol": t["symbol"], "reason": "x",
            "scores": {**t["components"], "total": None}}
    # recompute total the way the server does: default weights
    from pipeline.scout.scoring import weighted_total
    from pipeline.models import Weights
    c = t["components"]
    body["scores"]["total"] = weighted_total(c["genetic"], c["association"], c["druggability"], c["literature"], Weights())
    a = api.post("/api/approvals", json=body).get_json()
    b = api.post("/api/approvals", json=body).get_json()
    assert a["approval_id"] != b["approval_id"] and len(a["approval_id"]) == 32


def test_shortlist_endpoint_appends_line(api, tmp_path):
    from pipeline.audit import append_jsonl
    from tests.test_screening_pipeline import approval
    a = approval()
    append_jsonl(tmp_path / "approvals.jsonl", a.__dict__)
    r = api.post("/api/shortlists", json={"approval_id": a.approval_id, "chembl_ids": ["CHEMBL1", "CHEMBL2"], "reason": "potent"})
    assert r.status_code == 200 and r.get_json() == {"ok": True}
    line = (tmp_path / "shortlists.jsonl").read_text()
    assert '"CHEMBL2"' in line and a.approval_id in line


def test_scout_upstream_graphql_error_502_json(api, monkeypatch):
    from pipeline import api as api_mod
    from pipeline.http import UpstreamError

    def boom(*a, **k):
        raise UpstreamError("Open Targets error: Cannot query field 'expressions'")

    monkeypatch.setattr(api_mod, "run_scout", boom)
    r = scout(api)
    assert r.status_code == 502 and "Cannot query field" in r.get_json()["error"]


def test_scout_non_numeric_n_400(api):
    r = api.post("/api/scout", json={"disease": "Parkinson disease", "n": "lots"})
    assert r.status_code == 400 and "n" in r.get_json()["error"]


def test_approval_non_numeric_weights_400(api):
    run = scout(api).get_json()
    body = approval_body(run)
    body["weights"]["genetic"] = "high"
    assert api.post("/api/approvals", json=body).status_code == 400


def test_rationale_endpoint_explain_raising_gives_available_false(api, monkeypatch):
    from pipeline import api as api_mod

    def boom(result, **kw):
        raise ConnectionError("no route to host")

    monkeypatch.setattr(api_mod, "explain", boom)
    run = scout(api).get_json()
    r = api.post("/api/rationale", json={"run_id": run["run_id"], "weights": run["default_weights"]})
    assert r.status_code == 200
    body = r.get_json()
    assert body["available"] is False and "no route to host" in body["reason"]


def test_rationale_endpoint_passes_offline_flag_for_cache_only_client(api, monkeypatch):
    from pipeline import api as api_mod
    seen = {}

    def fake_explain(result, **kw):
        seen.update(kw)
        return None

    monkeypatch.setattr(api_mod, "explain", fake_explain)
    run = scout(api).get_json()
    api.post("/api/rationale", json={"run_id": run["run_id"], "weights": run["default_weights"]})
    assert seen["offline"] is True  # the test fixture's client is cache-only


def test_scout_targets_include_raw_evidence(api):
    target = scout(api).get_json()["targets"][0]
    assert "datatype_scores" in target["evidence"] and target["evidence"]["symbol"] == target["symbol"]


def test_rationale_rebuilds_result_from_posted_run(api, monkeypatch):
    from dataclasses import replace
    from pipeline import api as api_mod

    def fake_explain(result, **kw):
        return replace(result, targets=[replace(t, rationale="r", evidence_strength="weak") for t in result.targets])

    monkeypatch.setattr(api_mod, "explain", fake_explain)
    run = scout(api).get_json()
    api_mod.RUNS.clear()  # simulate a different (cold) server instance
    r = api.post("/api/rationale", json={"run_id": run["run_id"], "run": run, "weights": run["default_weights"]})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["rationales"][0]["symbol"] == run["targets"][0]["symbol"]


def test_disease_suggestions_require_query(api):
    assert api.get("/api/diseases").status_code == 400
    assert api.get("/api/diseases?q=%20").status_code == 400


def test_disease_suggestions_offline_list_recorded_diseases_only(api):
    body = api.get("/api/diseases?q=Parkinson").get_json()
    assert body["query"] == "Parkinson"
    assert body["diseases"] == [{"id": "MONDO_0005180", "name": "Parkinson disease"}]


def test_disease_suggestions_live_use_open_targets_search(tmp_path):
    class FakeClient:
        cache_only = False

        def post_json(self, url, body):
            assert body["variables"] == {"q": "diabetes", "n": 8}
            return {"data": {"search": {"hits": [
                {"id": "MONDO_0005015", "name": "diabetes mellitus", "entity": "disease"},
                {"id": "MONDO_0005147", "name": "type 1 diabetes mellitus", "entity": "disease"},
                {"id": "ENSG1", "name": "INS", "entity": "target"}]}}}

    app = create_app(client=FakeClient(), approvals_path=tmp_path / "a.jsonl", shortlists_path=tmp_path / "s.jsonl")
    body = app.test_client().get("/api/diseases?q=diabetes").get_json()
    assert [d["name"] for d in body["diseases"]] == ["diabetes mellitus", "type 1 diabetes mellitus"]


def test_screen_json_exposes_the_four_factors_coverage_and_baseline(tmp_path):
    from pipeline.audit import append_jsonl
    from tests.fake_chembl import FakeChembl, act
    from tests.test_screening_pipeline import approval, mol
    acts = [act("A", 8.0, aid=1), act("A", 8.2, aid=2, assay="A2"), act("B", 9.0, aid=3), act("B", 6.0, aid=4, assay="A4")]
    fake = FakeChembl(acts, {"A": mol("A", "ALPHA", "2.0"), "B": mol("B")})
    app = create_app(client=fake, approvals_path=tmp_path / "a.jsonl", shortlists_path=tmp_path / "s.jsonl")
    a = approval(chembl_target_id="CHEMBL203", uniprot=None, approval_id="appr-fake")
    append_jsonl(tmp_path / "a.jsonl", a.__dict__)
    r = app.test_client().post("/api/screen", json={"approval_id": a.approval_id, "rubric": {"objective": "novel_candidates"}})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["rubric"]["objective"] == "novel_candidates" and body["coverage"]["stage1"]["complete"] is True
    assert body["baseline"] == ["B", "A"] and [c["chembl_id"] for c in body["compounds"]] == ["A", "B"]
    c = body["compounds"][0]
    for k in ("rank", "baseline_rank", "rank_reason", "priority_score", "factors", "potency", "clinical", "selectivity",
              "qed", "missing_data", "best_pchembl", "lipinski_pass", "chembl_url"):
        assert k in c, k
    assert c["potency"]["aggregate_method"].startswith("median") and c["clinical"]["phase_label"] == "Phase 2"
    assert c["selectivity"]["status"] == "assessed" and c["factors"]["missing"] == ["selectivity"]
    assert app.test_client().post("/api/screen", json={"approval_id": a.approval_id, "rubric": {"objective": "nope"}}).status_code == 400
