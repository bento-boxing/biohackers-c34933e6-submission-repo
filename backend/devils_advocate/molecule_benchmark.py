"""Scientific evaluation of the four-factor candidate ranking against the potency-only baseline.

Run from backend/ with live network access (no paid calls are made; ChEMBL only):
    python -m devils_advocate.molecule_benchmark [--targets EGFR,DRD2] [--out devils_advocate/validation/molecule_ranking]

For each target it measures candidate coverage (ordered vs the previous unordered 5,000-row cut),
whether the extra factors change the ranking, ranking stability under missing data, agreement with
manually reviewed known compounds, indication/assay interpretation, false confidence from thin
selectivity evidence, and per-factor ablations. Results are JSON; MOLECULE_RANKING_VALIDATION.md
summarises them. Nothing here claims to predict efficacy or clinical success.
"""
from __future__ import annotations

import argparse
import copy
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.clients import chembl  # noqa: E402
from pipeline.http import HttpClient  # noqa: E402
from pipeline.models import Approval, Weights  # noqa: E402
from pipeline.screening.pipeline import run_screening  # noqa: E402
from pipeline.screening.rubric import FACTORS, OBJECTIVES, Rubric, prioritise  # noqa: E402

# Manually reviewed reference compounds (ChEMBL preferred names): expectation about indication status
# for the disease named in the approval. These are checks of interpretation, not of "correct" ranking.
TARGETS = {
    "EGFR": {"chembl_target_id": "CHEMBL203", "uniprot": "P00533", "target_id": "ENSG00000146648",
             "disease_id": "EFO_0003060", "disease_name": "non-small cell lung carcinoma",
             "known": {"GEFITINIB": "matched", "ERLOTINIB": "matched", "OSIMERTINIB": "matched", "AFATINIB": "matched",
                       "DACOMITINIB": "matched", "LAPATINIB": "other_indications_only", "ICOTINIB": "matched"}},
    "DRD2": {"chembl_target_id": "CHEMBL217", "uniprot": "P14416", "target_id": "ENSG00000149295",
             "disease_id": "MONDO_0005180", "disease_name": "Parkinson disease",
             "known": {"ROPINIROLE": "matched", "PRAMIPEXOLE": "matched", "ROTIGOTINE": "matched", "APOMORPHINE": "matched",
                       "BROMOCRIPTINE": "matched", "CABERGOLINE": "matched", "HALOPERIDOL": "other_indications_only",
                       "RISPERIDONE": "other_indications_only", "ARIPIPRAZOLE": "other_indications_only"}},
}
TOP = 10


def approval_for(symbol: str, spec: dict) -> Approval:
    return Approval(approval_id=f"benchmark-{symbol.lower()}", ts="2026-11-08T00:00:00Z", disease_id=spec["disease_id"],
                    disease_name=spec["disease_name"], target_id=spec["target_id"], symbol=symbol, uniprot=None,
                    chembl_target_id=spec["chembl_target_id"], weights=Weights().as_dict(), scores={}, safety_flags=[],
                    reason="benchmark", approved_by="benchmark")


def legacy_unordered_retrieval(client: HttpClient, target: str, max_pages: int = 5) -> dict[str, float]:
    """The previous method: first 5,000 potent rows in ChEMBL's default order, max pChEMBL per molecule."""
    best: dict[str, float] = {}
    for page in range(max_pages):
        data = client.get_json(chembl.CHEMBL_BASE + "activity.json", {
            "target_chembl_id": target, "pchembl_value__gte": chembl.POTENT_PCHEMBL, "limit": 1000, "offset": page * 1000,
            "only": "molecule_chembl_id,pchembl_value"})
        for a in data.get("activities") or []:
            if a.get("pchembl_value") is not None:
                best[a["molecule_chembl_id"]] = max(best.get(a["molecule_chembl_id"], 0.0), float(a["pchembl_value"]))
        if not (data.get("page_meta") or {}).get("next"):
            break
    return best


def order(compounds, rubric: Rubric) -> list[str]:
    return [c.chembl_id for c in prioritise(copy.deepcopy(compounds), rubric)]


def overlap(a: list[str], b: list[str], n: int = TOP) -> float:
    return len(set(a[:n]) & set(b[:n])) / n


def spearman(a: list[str], b: list[str]) -> float | None:
    ids = [x for x in a if x in b]
    n = len(ids)
    if n < 3:
        return None
    ra = {x: i for i, x in enumerate(a)}
    rb = {x: i for i, x in enumerate(b)}
    d2 = sum((ra[x] - rb[x]) ** 2 for x in ids)
    return round(1 - 6 * d2 / (n * (n * n - 1)), 4)


def mean_abs_shift(a: list[str], b: list[str]) -> float:
    ra = {x: i for i, x in enumerate(a)}
    rb = {x: i for i, x in enumerate(b)}
    common = [x for x in a if x in rb]
    return round(sum(abs(ra[x] - rb[x]) for x in common) / max(1, len(common)), 2)


def evaluate(symbol: str, spec: dict, client: HttpClient, seeds: int = 5) -> dict:
    started = time.monotonic()
    result = run_screening(approval_for(symbol, spec), top_n=50, client=client, selectivity_n=10)
    compounds = result.compounds
    full = order(compounds, Rubric())
    baseline = list(result.baseline)
    report: dict = {"target": symbol, "chembl_target_id": spec["chembl_target_id"], "disease": spec["disease_name"],
                    "elapsed_seconds": round(time.monotonic() - started, 1), "coverage": result.coverage, "notes": result.notes,
                    "pool_size": len(compounds)}
    # 1. candidate coverage vs the previous unordered cut
    legacy = legacy_unordered_retrieval(client, spec["chembl_target_id"])
    legacy_top = sorted(legacy, key=lambda m: (-legacy[m], m))[:50]
    new_baseline_top = baseline[:50]
    report["coverage_comparison"] = {
        "total_potent_records": result.coverage["stage1"]["total_count"],
        "legacy_molecules_retrieved": len(legacy), "ordered_molecules_retrieved": result.coverage["candidate_pool"]["molecules_retrieved"],
        "ordered_cutoff_pchembl": result.coverage["stage1"]["cutoff_pchembl"],
        "baseline_top50_molecules_absent_from_legacy_retrieval": [m for m in new_baseline_top if m not in legacy],
        "legacy_top50_overlap_with_ordered_baseline_top50": round(len(set(legacy_top) & set(new_baseline_top)) / 50, 2),
        "legacy_top50_max_pchembl_range": [min(legacy[m] for m in legacy_top), max(legacy[m] for m in legacy_top)] if legacy_top else None,
        "ordered_top50_max_pchembl_range": [min(c.best_pchembl for c in compounds if c.chembl_id in new_baseline_top),
                                            max(c.best_pchembl for c in compounds if c.chembl_id in new_baseline_top)],
    }
    # 2. does the ranking change?
    report["ranking_change_vs_baseline"] = {obj: {"top10_overlap": overlap(order(compounds, Rubric(objective=obj)), baseline),
                                                   "spearman": spearman(order(compounds, Rubric(objective=obj)), baseline),
                                                   "mean_abs_rank_shift": mean_abs_shift(order(compounds, Rubric(objective=obj)), baseline)}
                                             for obj in OBJECTIVES}
    # 3. ablations: zero one factor at a time
    ablations = {}
    for f in FACTORS:
        weights = {**OBJECTIVES["balanced"], f: 0.0}
        if sum(weights.values()) == 0:
            continue
        without = order(compounds, Rubric(weights=weights))
        ablations[f] = {"top10_overlap_with_full": overlap(without, full), "spearman_with_full": spearman(without, full),
                        "mean_abs_rank_shift": mean_abs_shift(without, full), "top10": without[:TOP]}
    report["ablations"] = ablations
    # 4. stability under missing data: drop QED for 30% / drop selectivity for 30% of the pool
    stab = {"drop_qed_30pct": [], "drop_selectivity_30pct": [], "drop_both_30pct": []}
    for seed in range(seeds):
        rng = random.Random(seed)
        for key, drop_qed, drop_sel in (("drop_qed_30pct", True, False), ("drop_selectivity_30pct", False, True), ("drop_both_30pct", True, True)):
            degraded = copy.deepcopy(compounds)
            for c in degraded:
                if rng.random() < 0.3:
                    if drop_qed:
                        c.qed = None; c.ro5_violations = None
                    if drop_sel and c.selectivity:
                        c.selectivity = {**c.selectivity, "evidence": "not_assessed", "status": "not_assessed", "window": None}
            got = order(degraded, Rubric())
            stab[key].append({"top10_overlap": overlap(got, full), "spearman": spearman(got, full), "mean_abs_rank_shift": mean_abs_shift(got, full)})
    report["stability_under_missing_data"] = {k: {"mean_top10_overlap": round(sum(x["top10_overlap"] for x in v) / len(v), 3),
                                                  "mean_abs_rank_shift": round(sum(x["mean_abs_rank_shift"] for x in v) / len(v), 2),
                                                  "runs": v} for k, v in stab.items()}
    # 5. known compounds: presence, ranks, indication interpretation
    by_name = {(c.name or "").upper(): c for c in compounds}
    known = {}
    for name, expected in spec["known"].items():
        c = by_name.get(name)
        if c is None:
            known[name] = {"in_pool": False, "expected_indication_status": expected}
            continue
        known[name] = {"in_pool": True, "chembl_id": c.chembl_id, "baseline_rank": c.baseline_rank,
                       "rubric_rank": {obj: order(compounds, Rubric(objective=obj)).index(c.chembl_id) + 1 for obj in OBJECTIVES},
                       "aggregate_pchembl": c.potency["aggregate_pchembl"], "max_pchembl": c.potency["max_pchembl"],
                       "primary_type": c.potency["primary_type"], "aggregate_n": c.potency["aggregate_n"],
                       "phase": c.clinical["phase"], "indication_status": c.clinical["indication_status"],
                       "expected_indication_status": expected, "indication_correct": c.clinical["indication_status"] == expected,
                       "selectivity_evidence": c.selectivity["evidence"], "selectivity_window": c.selectivity["window"],
                       "targets_tested": c.selectivity["targets_tested"]}
    report["known_compounds"] = known
    checked = [k for k in known.values() if k.get("in_pool")]
    report["indication_interpretation"] = {"known_in_pool": len(checked),
                                           "correct": sum(1 for k in checked if k["indication_correct"]),
                                           "phased_molecules_in_pool": sum(1 for c in compounds if c.clinical["phase"] is not None),
                                           "status_counts": _counts(c.clinical["indication_status"] for c in compounds)}
    # 6. assay interpretation: measurement types, pooled-vs-max differences
    diffs = [round(c.potency["max_pchembl"] - c.potency["aggregate_pchembl"], 2) for c in compounds
             if c.potency["aggregate_pchembl"] is not None and c.potency["max_pchembl"] is not None]
    report["assay_interpretation"] = {"primary_type_counts": _counts(c.potency["primary_type"] for c in compounds),
                                      "no_aggregate": sum(1 for c in compounds if c.potency["aggregate_pchembl"] is None),
                                      "sparse": sum(1 for c in compounds if c.potency["sparse"]),
                                      "conflicting": sum(1 for c in compounds if c.potency["conflicting"]),
                                      "max_minus_median_mean": round(sum(diffs) / len(diffs), 2) if diffs else None,
                                      "max_minus_median_ge_1_log": sum(1 for d in diffs if d >= 1.0),
                                      "censored_records": sum(c.potency["n_censored"] for c in compounds)}
    # 7. false confidence: thin selectivity evidence in the top 10
    top10 = [c for c in prioritise(copy.deepcopy(compounds), Rubric())[:TOP]]
    report["selectivity_evidence_top10"] = {
        "evidence_counts": _counts(c.selectivity["evidence"] for c in top10),
        "scored_without_window": sum(1 for c in top10 if c.factors["selectivity"] is not None and c.selectivity["evidence"] != "observed_window"),
        "targets_tested": [c.selectivity["targets_tested"] for c in top10],
        "partial": sum(1 for c in top10 if c.selectivity["partial"]),
        "windows": [c.selectivity["window"] for c in top10],
        "missing_factor_lists": [c.factors["missing"] for c in top10]}
    report["top10"] = {"baseline": baseline[:TOP], "balanced": full[:TOP],
                       "novel_candidates": order(compounds, Rubric(objective="novel_candidates"))[:TOP],
                       "repurposing": order(compounds, Rubric(objective="repurposing"))[:TOP]}
    report["names"] = {c.chembl_id: c.name for c in compounds}
    return report


def _counts(items) -> dict:
    out: dict = {}
    for i in items:
        out[str(i)] = out.get(str(i), 0) + 1
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", default="EGFR,DRD2")
    ap.add_argument("--out", default=str(Path(__file__).parent / "validation" / "molecule_ranking"))
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    client = HttpClient(write_dir=out / "cache", ttl_days=30)
    for symbol in [s.strip() for s in args.targets.split(",") if s.strip()]:
        report = evaluate(symbol, TARGETS[symbol], client)
        (out / f"{symbol}.json").write_text(json.dumps(report, indent=1))
        print(symbol, "pool", report["pool_size"], "elapsed", report["elapsed_seconds"], "s",
              "absent from legacy:", len(report["coverage_comparison"]["baseline_top50_molecules_absent_from_legacy_retrieval"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
