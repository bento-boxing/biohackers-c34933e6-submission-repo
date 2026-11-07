from pipeline.models import Approval, Compound, Weights


def test_weights_normalised_sums_to_one():
    w = Weights(4, 3, 2, 1).normalised()
    assert abs(w.genetic + w.association + w.druggability + w.literature - 1) < 1e-9
    assert abs(w.genetic - 0.4) < 1e-9


def test_weights_all_zero_falls_back_to_defaults():
    assert Weights(0, 0, 0, 0).normalised() == Weights()


def test_approval_round_trips_json():
    a = Approval(
        ts="2026-11-07T18:02:11Z", disease_id="MONDO_0005180", disease_name="Parkinson disease",
        target_id="ENSG00000188906", symbol="LRRK2", uniprot="Q5S007",
        chembl_target_id="CHEMBL1075104", weights=Weights().as_dict(),
        scores={"genetic": 0.9, "association": 0.8, "druggability": 0.8, "literature": 1.0, "total": 0.9},
        safety_flags=[], reason="strong genetics", approved_by="ella",
    )
    assert Approval.from_json(a.to_json()) == a


def test_compound_is_approved_and_lipinski():
    c = Compound("CHEMBL1", None, 7.0, "B", "4.0", 400.0, 2.0, 1, 3, 80.0, 1)
    assert c.is_approved and c.lipinski_pass is True
    d = Compound("CHEMBL2", None, 6.0, None, None, None, None, None, None, None, None)
    assert not d.is_approved and d.lipinski_pass is None
