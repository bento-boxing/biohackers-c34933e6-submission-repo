"""Observed off-target activity for shortlisted molecules.

This is a *limited* analysis of what ChEMBL happens to record. It counts how many targets and assays
were actually tested, compares only measurements of the same type as the on-target aggregate, and
treats untested targets as unknown. Absence of off-target records is never evidence of selectivity.
"""
from __future__ import annotations

from statistics import median

from pipeline.screening.potency import COMPARABLE_TYPES, PotencySummary, normalise_record

CAUTION = ("Observed evidence only: untested targets are unknown, not clean, and a lack of off-target records "
           "is not evidence of selectivity. Windows compare the on-target median with each off-target median of "
           "the same measurement type; other types are listed but not compared.")
OFF_TARGETS_KEPT = 10


def assess_selectivity(molecule_id: str, on_target_id: str, on_target: PotencySummary, off_records: list[dict] | None,
                       target_names: dict[str, dict], truncated: bool) -> dict:
    base = {"molecule_chembl_id": molecule_id, "on_target_chembl_id": on_target_id, "caution": CAUTION,
            "window": None, "targets_tested": 0, "assays_tested": 0, "records": 0, "comparable_records": 0,
            "incomparable_records": 0, "off_targets": [], "most_potent_comparable_off_target": None,
            "comparison_type": on_target.primary_type, "partial": bool(truncated)}
    if off_records is None:
        return {**base, "status": "not_assessed", "evidence": "not_assessed",
                "note": "Off-target activity was not retrieved for this molecule (outside the shortlist or time budget)."}
    records = [normalise_record(r) for r in off_records if r.get("target_chembl_id") not in (None, on_target_id)]
    base.update(status="assessed", records=len(records),
                targets_tested=len({r["target_chembl_id"] for r in records}),
                assays_tested=len({r["assay_chembl_id"] for r in records if r["assay_chembl_id"]}))
    if not records:
        return {**base, "evidence": "no_off_target_records",
                "note": "ChEMBL holds no activity records for this molecule against any other target; "
                        "selectivity is untested, not demonstrated."}
    ptype = on_target.primary_type
    per_target: dict[str, list[dict]] = {}
    for r in records:
        per_target.setdefault(r["target_chembl_id"], []).append(r)
    rows = []
    for tid, recs in per_target.items():
        comparable = [r["pchembl_value"] for r in recs if r["pchembl_value"] is not None and r["assay_type"] == "B"
                      and r["standard_relation"] == "=" and r["standard_type"] == ptype]
        values = [r["pchembl_value"] for r in recs if r["pchembl_value"] is not None]
        info = target_names.get(tid) or {}
        rows.append({"target_chembl_id": tid, "name": info.get("pref_name") or tid, "organism": info.get("organism"),
                     "n": len(recs), "assays": len({r["assay_chembl_id"] for r in recs if r["assay_chembl_id"]}),
                     "max_pchembl": max(values) if values else None,
                     "comparable": bool(comparable), "comparable_n": len(comparable),
                     "comparable_median": round(median(comparable), 2) if comparable else None,
                     "types": sorted({r["standard_type"] for r in recs if r["standard_type"]})})
    base["comparable_records"] = sum(r["comparable_n"] for r in rows)
    base["incomparable_records"] = len(records) - base["comparable_records"]
    rows.sort(key=lambda r: (-(r["max_pchembl"] if r["max_pchembl"] is not None else -1), r["target_chembl_id"]))
    base["off_targets"] = rows[:OFF_TARGETS_KEPT]
    base["off_targets_omitted"] = max(0, len(rows) - OFF_TARGETS_KEPT)
    comparable_rows = [r for r in rows if r["comparable"]]
    if not comparable_rows or on_target.aggregate_pchembl is None:
        return {**base, "evidence": "no_comparable_off_target_records",
                "note": f"{len(records)} off-target record(s) across {base['targets_tested']} target(s) exist, but none is an "
                        f"exact {ptype or 'binding'} measurement comparable with the on-target aggregate; no window is computed."}
    strongest = max(comparable_rows, key=lambda r: r["comparable_median"])
    window = round(on_target.aggregate_pchembl - strongest["comparable_median"], 2)
    return {**base, "evidence": "observed_window", "window": window,
            "most_potent_comparable_off_target": {"target_chembl_id": strongest["target_chembl_id"], "name": strongest["name"],
                                                  "median_pchembl": strongest["comparable_median"], "n": strongest["comparable_n"]},
            "note": f"Observed window of {window:+.2f} log units versus {strongest['name']} ({ptype} medians) across "
                    f"{len(comparable_rows)} comparable target(s) of {base['targets_tested']} tested"
                    + ("; retrieval was truncated, so more off-target records may exist." if truncated else ".")}
