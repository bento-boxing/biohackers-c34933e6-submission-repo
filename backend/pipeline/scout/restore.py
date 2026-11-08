"""Rebuild a ScoutResult from the JSON that /api/scout returned.

Stateless deployments (Vercel) cannot rely on the in-memory RUNS table surviving between
requests, so clients post the run back and the server reconstructs it from the raw
`evidence` dict carried by every target.
"""
from __future__ import annotations

from pipeline.models import (ComponentScores, Disease, SafetyFlag, ScoredTarget, ScoutResult,
                             TargetEvidence, Weights)


def result_from_run_json(run: dict) -> ScoutResult:
    try:
        disease = Disease(id=run["disease"]["id"], name=run["disease"]["name"])
        targets = []
        for item in run["targets"]:
            ev = dict(item["evidence"])
            ev["safety_flags"] = [SafetyFlag(**flag) for flag in ev.get("safety_flags", [])]
            comps = item.get("components") or {}
            scores = ComponentScores(genetic=float(comps.get("genetic", 0.0)),
                                     association=float(comps.get("association", 0.0)),
                                     druggability=float(comps.get("druggability", 0.0)),
                                     literature=float(comps.get("literature", 0.0)),
                                     total=float(comps.get("total", 0.0)))
            targets.append(ScoredTarget(TargetEvidence(**ev), scores))
    except (KeyError, TypeError) as e:
        raise ValueError(f"scout run JSON is missing evidence: {e}") from e
    weights = Weights(**run["weights"]) if isinstance(run.get("weights"), dict) else Weights()
    return ScoutResult(disease=disease, weights=weights, targets=targets)
