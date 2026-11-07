"""The checkable formula. Pure functions, no I/O."""
from __future__ import annotations

import math

from pipeline.models import ComponentScores, ScoredTarget, TargetEvidence, Weights

TRACTABILITY_TIERS: list[tuple[set[str], float]] = [
    ({"Approved Drug", "Advanced Clinical", "Phase 1 Clinical"}, 1.0),
    ({"Structure with Ligand", "High-Quality Ligand"}, 0.7),
    ({"High-Quality Pocket", "Med-Quality Pocket", "Druggable Family"}, 0.4),
]


def tractability_sm(tractability: list[dict]) -> float:
    labels = {t["label"] for t in tractability if t.get("modality") == "SM" and t.get("value")}
    for tier, value in TRACTABILITY_TIERS:
        if labels & tier:
            return value
    return 0.0


def log_norm(value: int, max_value: int) -> float:
    if max_value <= 0:
        return 0.0
    return math.log10(value + 1) / math.log10(max_value + 1)


def weighted_total(genetic: float, association: float, druggability: float,
                   literature: float, weights: Weights) -> float:
    w = weights.normalised()
    return (w.genetic * genetic + w.association * association
            + w.druggability * druggability + w.literature * literature)


def component_scores(ev: TargetEvidence, weights: Weights, max_hits: int, max_potent: int) -> ComponentScores:
    genetic = float(ev.datatype_scores.get("genetic_association", 0.0))
    association = float(ev.ot_score)
    druggability = 0.5 * tractability_sm(ev.tractability) + 0.5 * log_norm(ev.potent_count, max_potent)
    literature = log_norm(ev.literature_hits, max_hits)
    return ComponentScores(genetic, association, druggability, literature,
                           weighted_total(genetic, association, druggability, literature, weights))


def score_all(evidence: list[TargetEvidence], weights: Weights) -> list[ScoredTarget]:
    max_hits = max((e.literature_hits for e in evidence), default=0)
    max_potent = max((e.potent_count for e in evidence), default=0)
    scored = [ScoredTarget(e, component_scores(e, weights, max_hits, max_potent)) for e in evidence]
    return sorted(scored, key=lambda s: s.scores.total, reverse=True)
