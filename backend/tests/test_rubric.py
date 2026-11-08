from pipeline.models import Compound
from pipeline.screening.rubric import Rubric, factor_scores, prioritise


def compound(cid, agg=8.0, qed=0.6, ro5=0, phase=None, window=None, sel_evidence="observed_window",
             indication="preclinical", sparse=False, conflicting=False):
    potency = {"aggregate_pchembl": agg, "max_pchembl": agg, "sparse": sparse, "conflicting": conflicting,
               "primary_type": "IC50", "aggregate_n": 1 if sparse else 3, "flags": []}
    selectivity = None if sel_evidence is None else {"status": "assessed", "evidence": sel_evidence, "window": window,
                                                      "targets_tested": 0 if window is None else 3, "partial": False}
    clinical = {"phase": phase, "indication_status": indication}
    return Compound(chembl_id=cid, name=cid, best_pchembl=agg or 0, assay_type="B", max_phase=None if phase is None else str(phase),
                    mw=None, alogp=None, hbd=None, hba=None, psa=None, ro5_violations=ro5, qed=qed,
                    potency=potency, clinical=clinical, selectivity=selectivity)


def test_factor_scores_keep_missing_as_none_not_zero():
    f = factor_scores(compound("A", qed=None, ro5=None, sel_evidence="no_off_target_records"), Rubric())
    assert f["drug_likeness"] is None and f["selectivity"] is None and f["potency"] == 0.75
    assert f["clinical"] == 0.0  # preclinical is a known state, not missing data


def test_qed_is_used_when_present_and_ro5_only_as_fallback():
    assert factor_scores(compound("A", qed=0.3, ro5=3), Rubric())["drug_likeness"] == 0.3
    assert factor_scores(compound("A", qed=None, ro5=3), Rubric())["drug_likeness"] == 0.25


def test_missing_factor_is_excluded_from_the_composite_and_named_in_the_reason():
    a = compound("A", agg=8.0, qed=None, ro5=None, sel_evidence="no_off_target_records")
    b = compound("B", agg=8.0, qed=0.8, window=2.5)
    ranked = prioritise([a, b], Rubric(objective="novel_candidates"))
    by_id = {c.chembl_id: c for c in ranked}
    assert by_id["A"].factors["missing"] == ["drug_likeness", "selectivity"]
    assert "drug-likeness" in by_id["A"].rank_reason.lower() and "selectivity" in by_id["A"].rank_reason.lower()
    # A's composite is its potency alone (renormalised), so it is not silently zeroed
    assert by_id["A"].priority_score == 0.75 and by_id["B"].priority_score > by_id["A"].priority_score


def test_unquantified_potency_sorts_after_every_quantified_candidate():
    weak = compound("W", agg=6.2, qed=0.9, window=3.0)
    unknown = compound("U", agg=None, qed=0.9, window=3.0)
    unknown.potency["max_pchembl"] = 9.5
    ranked = prioritise([unknown, weak], Rubric())
    assert [c.chembl_id for c in ranked] == ["W", "U"] and ranked[1].rank == 2
    assert "no aggregate potency" in ranked[1].rank_reason.lower()


def test_objective_changes_how_clinical_stage_counts():
    other = compound("O", agg=8.0, phase=4, indication="other_indications_only")
    matched = compound("M", agg=8.0, phase=4, indication="matched")
    novel = compound("N", agg=8.0, phase=None)
    novel_rank = [c.chembl_id for c in prioritise([other, matched, novel], Rubric(objective="novel_candidates"))]
    assert novel_rank[0] == "M" or len({c.priority_score for c in prioritise([other, matched, novel], Rubric(objective="novel_candidates"))}) == 1
    repurpose = {c.chembl_id: c for c in prioritise([other, matched, novel], Rubric(objective="repurposing"))}
    assert repurpose["M"].priority_score > repurpose["O"].priority_score > repurpose["N"].priority_score
    assert repurpose["O"].factors["clinical"] < repurpose["M"].factors["clinical"]


def test_rubric_is_documented_as_heuristic_and_weights_are_configurable():
    r = Rubric(objective="balanced", weights={"potency": 0.7, "drug_likeness": 0.1, "selectivity": 0.1, "clinical": 0.1})
    d = r.describe()
    assert "heuristic" in d["caveat"].lower() and "clinical success" in d["caveat"].lower()
    assert d["weights"]["potency"] == 0.7 and d["objective"] == "balanced"
