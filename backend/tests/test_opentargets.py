import pytest

from pipeline.clients.opentargets import (
    DiseaseNotFound, associated_targets, resolve_disease, target_safety,
)


def test_resolve_parkinson_returns_mondo_0005180(client):
    d = resolve_disease(client, "Parkinson disease")
    assert (d.id, d.name) == ("MONDO_0005180", "Parkinson disease")


def test_resolve_unknown_raises_disease_not_found(client):
    with pytest.raises(DiseaseNotFound):
        resolve_disease(client, "zzqxv-not-a-disease")


def test_associated_targets_returns_25_with_lrrk2(client):
    rows = associated_targets(client, "MONDO_0005180", 25)
    assert len(rows) == 25
    lrrk2 = next(r for r in rows if r.symbol == "LRRK2")
    assert lrrk2.uniprot == "Q5S007"
    assert lrrk2.datatype_scores["genetic_association"] > 0.5
    assert lrrk2.target_id == "ENSG00000188906"


def test_target_safety_lrrk2_has_no_high_expression_flags(client):
    flags = target_safety(client, "ENSG00000188906")
    assert [f for f in flags if f.kind == "expression"] == []
