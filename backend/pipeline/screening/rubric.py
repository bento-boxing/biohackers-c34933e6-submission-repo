"""Candidate-prioritisation rubric: a configurable, documented heuristic over four separate factors.

Nothing here predicts efficacy or clinical success. The composite is a weighted mean over the factors
that are *available* for a candidate; missing factors are listed, never scored as zero, and a candidate
without an aggregate potency sorts after every candidate that has one.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pipeline.models import Compound

FACTORS = ("potency", "drug_likeness", "selectivity", "clinical")
OBJECTIVES = {
    "balanced": {"potency": 0.45, "drug_likeness": 0.20, "selectivity": 0.25, "clinical": 0.10},
    "novel_candidates": {"potency": 0.50, "drug_likeness": 0.25, "selectivity": 0.25, "clinical": 0.0},
    "repurposing": {"potency": 0.35, "drug_likeness": 0.15, "selectivity": 0.20, "clinical": 0.30},
}
POTENCY_FLOOR, POTENCY_CEILING = 5.0, 9.0  # pChEMBL mapped linearly onto 0..1
SPARSE_PENALTY, CONFLICT_PENALTY = 0.10, 0.10  # a single measurement is an isolated value, not a potency
WINDOW_FLOOR, WINDOW_CEILING = -1.0, 2.0  # log units mapped onto 0..1
CAVEAT = ("Heuristic prioritisation for choosing what to test next. The score weighs observed potency, "
          "computed drug-likeness heuristics (QED, Lipinski rule of five), observed off-target evidence and "
          "development precedent; it does not predict efficacy or clinical success and QED/Ro5 are not "
          "clinical-success predictors. Missing factors are excluded from the composite and listed.")


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


@dataclass
class Rubric:
    objective: str = "balanced"
    weights: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.objective not in OBJECTIVES:
            raise ValueError(f"unknown objective {self.objective!r}; choose one of {', '.join(OBJECTIVES)}")
        merged = {**OBJECTIVES[self.objective], **{k: float(v) for k, v in (self.weights or {}).items() if k in FACTORS}}
        if any(v < 0 for v in merged.values()) or sum(merged.values()) <= 0:
            raise ValueError("rubric weights must be nonnegative and not all zero")
        self.weights = merged

    def describe(self) -> dict:
        return {"objective": self.objective, "weights": dict(self.weights), "caveat": CAVEAT, "objectives": list(OBJECTIVES),
                "factors": {
                    "potency": f"median exact pChEMBL of the primary measurement type mapped from {POTENCY_FLOOR:g} (0) to "
                               f"{POTENCY_CEILING:g} (1); -{SPARSE_PENALTY} if a single measurement, -{CONFLICT_PENALTY} if measurements "
                               f"conflict by >= 1 log unit; missing when no exact binding measurement exists (candidate sorts last)",
                    "drug_likeness": "ChEMBL QED (0..1) when present, otherwise 1 - 0.25 x Lipinski violations; missing when neither "
                                     "is recorded. Heuristics, not success predictors.",
                    "selectivity": f"observed window (on-target median minus strongest comparable off-target median, same measurement "
                                   f"type) mapped from {WINDOW_FLOOR:g} (0) to {WINDOW_CEILING:g} (1); missing when nothing comparable "
                                   f"was tested. Untested targets are unknown, not clean.",
                    "clinical": "development maturity = ChEMBL max_phase / 4 (preclinical = 0, a known state). Under the "
                                "'repurposing' objective development for other indications counts half (exposure precedent, "
                                "not efficacy); under 'novel_candidates' the factor is shown but carries no weight."}}


def factor_scores(c: Compound, rubric: Rubric) -> dict:
    potency = c.potency or {}
    agg = potency.get("aggregate_pchembl")
    p = None
    if agg is not None:
        p = _clamp((agg - POTENCY_FLOOR) / (POTENCY_CEILING - POTENCY_FLOOR))
        if potency.get("sparse"):
            p = _clamp(p - SPARSE_PENALTY)
        if potency.get("conflicting"):
            p = _clamp(p - CONFLICT_PENALTY)
    if c.qed is not None:
        d = _clamp(float(c.qed))
    elif c.ro5_violations is not None:
        d = _clamp(1 - 0.25 * c.ro5_violations)
    else:
        d = None
    sel = c.selectivity or {}
    s = None
    if sel.get("evidence") == "observed_window" and sel.get("window") is not None:
        s = _clamp((sel["window"] - WINDOW_FLOOR) / (WINDOW_CEILING - WINDOW_FLOOR))
    clinical = c.clinical or {}
    phase = clinical.get("phase")
    k = 0.0 if phase is None else _clamp(float(phase) / 4)
    if rubric.objective == "repurposing" and clinical.get("indication_status") in ("other_indications_only", "no_indication_records", "not_checked"):
        k = k / 2
    return {"potency": None if p is None else round(p, 4), "drug_likeness": None if d is None else round(d, 4),
            "selectivity": None if s is None else round(s, 4), "clinical": round(k, 4)}


def _reason(c: Compound, scores: dict, rubric: Rubric, missing: list[str]) -> str:
    parts = []
    pot = c.potency or {}
    if scores["potency"] is None:
        parts.append(f"no aggregate potency (no exact binding measurement; strongest isolated record pChEMBL "
                     f"{pot.get('max_pchembl')}), so it is placed after every candidate with one")
    else:
        parts.append(f"potency {pot.get('aggregate_pchembl')} ({pot.get('primary_type')} median of {pot.get('aggregate_n')}"
                     f"{', single measurement' if pot.get('sparse') else ''}{', conflicting' if pot.get('conflicting') else ''})")
    if scores["drug_likeness"] is not None:
        parts.append(f"drug-likeness {'QED ' + format(c.qed, '.2f') if c.qed is not None else 'Ro5 violations ' + str(c.ro5_violations)}")
    sel = c.selectivity or {}
    if scores["selectivity"] is not None:
        parts.append(f"observed selectivity window {sel.get('window'):+.2f} over {sel.get('targets_tested')} tested target(s)")
    cl = c.clinical or {}
    if rubric.weights.get("clinical", 0) > 0:
        parts.append(f"clinical: {cl.get('phase_label', 'unknown')} ({(cl.get('indication_status') or 'unknown').replace('_', ' ')})")
    if missing:
        labels = {"drug_likeness": "drug-likeness", "selectivity": "selectivity", "potency": "potency"}
        parts.append("missing and excluded from the composite: " + ", ".join(labels.get(m, m) for m in missing))
    return "; ".join(parts)


def prioritise(compounds: list[Compound], rubric: Rubric) -> list[Compound]:
    for c in compounds:
        scores = factor_scores(c, rubric)
        weighted = {f: rubric.weights[f] for f in FACTORS if scores[f] is not None and rubric.weights[f] > 0}
        missing = [f for f in FACTORS if scores[f] is None and f != "clinical"]
        total = sum(weighted.values())
        composite = round(sum(scores[f] * w for f, w in weighted.items()) / total, 4) if total and scores["potency"] is not None else None
        c.factors = {**scores, "weights_used": {f: round(w / total, 4) for f, w in weighted.items()} if total else {},
                     "missing": missing, "objective": rubric.objective}
        c.priority_score = composite
        c.rank_reason = _reason(c, scores, rubric, missing)
        c.missing_data = [m for m in c.missing_data if not m.startswith("factor:")] + [f"factor:{m}" for m in missing]
    ranked = sorted(compounds, key=lambda c: (c.priority_score is None, -(c.priority_score or 0),
                                              -((c.potency or {}).get("aggregate_pchembl") or 0), -c.best_pchembl, c.chembl_id))
    for i, c in enumerate(ranked, 1):
        c.rank = i
    return ranked
