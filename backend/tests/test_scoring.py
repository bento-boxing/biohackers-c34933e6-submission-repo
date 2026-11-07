from pipeline.models import TargetEvidence, Weights
from pipeline.scout.scoring import component_scores, log_norm, score_all, tractability_sm

SM = lambda label, value=True: {"label": label, "modality": "SM", "value": value}  # noqa: E731


def ev(symbol="X", genetic=None, ot=0.5, tract=(), potent=0, hits=0):
    ds = {} if genetic is None else {"genetic_association": genetic}
    return TargetEvidence(target_id=symbol, symbol=symbol, name=symbol, uniprot=None, ot_score=ot,
                          datatype_scores=ds, tractability=list(tract), has_approved_drug=False,
                          literature_hits=hits, potent_count=potent)


def test_tractability_sm_tiers():
    assert tractability_sm([SM("Approved Drug")]) == 1.0
    assert tractability_sm([SM("High-Quality Ligand"), SM("Druggable Family")]) == 0.7
    assert tractability_sm([SM("Druggable Family")]) == 0.4
    assert tractability_sm([{"label": "Approved Drug", "modality": "AB", "value": True}]) == 0.0
    assert tractability_sm([SM("Approved Drug", False)]) == 0.0


def test_log_norm_zero_max():
    assert log_norm(0, 0) == 0.0
    assert log_norm(9, 99) == 0.5


def test_missing_genetic_datatype_scores_zero():
    s = component_scores(ev(), Weights(), max_hits=10, max_potent=10)
    assert s.genetic == 0.0


def test_component_total_with_default_weights():
    e = ev(genetic=0.5, ot=0.8, tract=[SM("High-Quality Ligand")], potent=99, hits=9)
    s = component_scores(e, Weights(), max_hits=99, max_potent=999)
    assert round(s.genetic, 3) == 0.5
    assert round(s.association, 3) == 0.8
    assert round(s.druggability, 3) == round(0.5 * 0.7 + 0.5 * (2 / 3), 3)
    assert round(s.literature, 3) == 0.5
    assert round(s.total, 3) == round(0.4 * 0.5 + 0.3 * 0.8 + 0.2 * s.druggability + 0.1 * 0.5, 3)


def test_shared_example_total_0_61():
    from pipeline.scout.scoring import weighted_total
    assert round(weighted_total(0.5, 0.8, 0.6, 0.5, Weights()), 3) == 0.61


def test_score_all_sorted_desc():
    ranked = score_all([ev("A", genetic=0.1), ev("B", genetic=0.9), ev("C", genetic=0.5)], Weights())
    assert [r.evidence.symbol for r in ranked] == ["B", "C", "A"]
    assert ranked[0].scores.total >= ranked[1].scores.total >= ranked[2].scores.total


def test_weights_unnormalised_same_ranking():
    es = [ev("A", genetic=0.1, hits=50), ev("B", genetic=0.9)]
    a = score_all(es, Weights(4, 3, 2, 1))
    b = score_all(es, Weights())
    assert [round(r.scores.total, 6) for r in a] == [round(r.scores.total, 6) for r in b]
