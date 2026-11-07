from pipeline.models import Approval, Weights
from pipeline.screening.pipeline import run_screening


def approval(chembl_target_id="CHEMBL1075104", uniprot="Q5S007"):
    return Approval(ts="2026-11-07T00:00:00Z", disease_id="MONDO_0005180", disease_name="Parkinson disease",
                    target_id="ENSG00000188906", symbol="LRRK2", uniprot=uniprot,
                    chembl_target_id=chembl_target_id, weights=Weights().as_dict(), scores={},
                    safety_flags=[], reason="x", approved_by="t")


def test_run_screening_lrrk2_returns_50_compounds_sorted(client):
    r = run_screening(approval(), top_n=50, client=client)
    assert len(r.compounds) == 50
    p = [c.best_pchembl for c in r.compounds]
    assert p == sorted(p, reverse=True) and p[0] >= 9
    assert r.structure is not None and r.structure.uniprot == "Q5S007"
    assert any(c.name for c in r.compounds)


def test_run_screening_without_chembl_target_gives_structure_only(client):
    r = run_screening(approval(chembl_target_id=None), client=client)
    assert r.compounds == [] and r.structure is not None
