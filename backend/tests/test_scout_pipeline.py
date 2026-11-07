import pytest
import requests

from pipeline.clients.opentargets import DiseaseNotFound
from pipeline.models import Weights
from pipeline.scout.pipeline import rescore, run_scout


def test_run_scout_parkinson_25_rows_components_in_unit_interval_sorted(client):
    r = run_scout("Parkinson disease", n=25, client=client)
    assert r.disease.id == "MONDO_0005180"
    assert len(r.targets) == 25
    totals = [t.scores.total for t in r.targets]
    assert totals == sorted(totals, reverse=True)
    for t in r.targets:
        for v in (t.scores.genetic, t.scores.association, t.scores.druggability, t.scores.literature):
            assert 0.0 <= v <= 1.0


def test_lrrk2_in_top_5(client):
    r = run_scout("Parkinson disease", n=25, client=client)
    assert "LRRK2" in [t.evidence.symbol for t in r.targets[:5]]


def test_rescore_changes_order_without_network(client, monkeypatch):
    r = run_scout("Parkinson disease", n=25, client=client)
    monkeypatch.setattr(requests.Session, "request", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network")))
    r2 = rescore(r, Weights(0, 0, 1, 0))
    assert r2.weights == Weights(0, 0, 1, 0)
    assert [t.evidence.symbol for t in r2.targets] != [t.evidence.symbol for t in r.targets]
    assert r2.targets[0].scores.total == pytest.approx(r2.targets[0].scores.druggability)


def test_unknown_disease_raises(client):
    with pytest.raises(DiseaseNotFound):
        run_scout("zzqxv-not-a-disease", client=client)
