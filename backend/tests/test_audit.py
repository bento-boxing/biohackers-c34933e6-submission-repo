from pipeline.audit import append_jsonl, append_shortlist, make_approval, read_approvals
from pipeline.models import Weights
from pipeline.scout.pipeline import run_scout

SPEC_KEYS = {"ts", "disease_id", "disease_name", "target_id", "symbol", "uniprot", "chembl_target_id",
             "weights", "scores", "safety_flags", "reason", "approved_by"}


def test_make_approval_fields_match_spec_example_keys(client, monkeypatch):
    monkeypatch.setenv("SCOUT_USER", "tester")
    r = run_scout("Parkinson disease", client=client)
    a = make_approval(r, r.targets[0], "strong genetics")
    assert set(a.__dict__) == SPEC_KEYS
    assert a.ts.endswith("Z") and a.approved_by == "tester" and a.symbol == "LRRK2"
    assert set(a.scores) == {"genetic", "association", "druggability", "literature", "total"}
    assert a.weights == Weights().as_dict()


def test_append_then_read_newest_first(client, tmp_path):
    r = run_scout("Parkinson disease", client=client)
    p = tmp_path / "a.jsonl"
    for t in r.targets[:2]:
        append_jsonl(p, make_approval(r, t, "x").__dict__)
    got = read_approvals(p)
    assert [a.symbol for a in got] == [r.targets[1].evidence.symbol, r.targets[0].evidence.symbol]


def test_read_missing_file_returns_empty(tmp_path):
    assert read_approvals(tmp_path / "nope.jsonl") == []


def test_append_shortlist_writes_ids(client, tmp_path):
    r = run_scout("Parkinson disease", client=client)
    a = make_approval(r, r.targets[0], "x")
    p = tmp_path / "s.jsonl"
    append_shortlist(a, ["CHEMBL1", "CHEMBL2"], "potent", path=p)
    line = p.read_text().strip()
    assert '"CHEMBL1"' in line and a.ts in line and '"potent"' in line
