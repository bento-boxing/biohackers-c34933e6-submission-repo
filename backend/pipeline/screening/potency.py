"""Potency summary per molecule from ChEMBL activity records.

Rules (see devils_advocate/MOLECULE_RANKING_VALIDATION.md):
* Only exact measurements (standard_relation '=') from binding assays (assay_type 'B') of one
  standard_type (IC50, Ki, Kd or EC50) are aggregated, and types are never pooled with each other.
* The aggregate is the median of that type's pChEMBL values; the type with the most exact
  measurements is the primary type (ties broken in the order IC50, Ki, Kd, EC50).
* The maximum pChEMBL is kept only as the potency-only baseline, never as "the" potency.
* Every retained record keeps its activity, assay, target and document identifiers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from statistics import median

COMPARABLE_TYPES = ("IC50", "Ki", "Kd", "EC50")
CONFLICT_LOG_UNITS = 1.0  # >= 10-fold disagreement between exact measurements of the primary type
RECORDS_KEPT = 25
RECORD_KEYS = ("activity_id", "molecule_chembl_id", "assay_chembl_id", "assay_type", "assay_description",
               "bao_label", "standard_type", "standard_relation", "standard_value", "standard_units",
               "pchembl_value", "target_chembl_id", "document_chembl_id", "data_validity_comment",
               "potential_duplicate")


@dataclass
class PotencySummary:
    n_records: int = 0
    n_assays: int = 0
    n_documents: int = 0
    n_exact: int = 0
    n_censored: int = 0
    n_functional: int = 0
    n_without_pchembl: int = 0
    by_type: dict = field(default_factory=dict)
    primary_type: str | None = None
    aggregate_pchembl: float | None = None
    aggregate_n: int = 0
    aggregate_method: str = ""
    range: list | None = None
    spread: float | None = None
    conflicting: bool = False
    sparse: bool = False
    max_pchembl: float | None = None
    max_record: dict | None = None
    flags: list = field(default_factory=list)
    records: list = field(default_factory=list)
    records_omitted: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def _p(value) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def normalise_record(raw: dict) -> dict:
    rec = {k: raw.get(k) for k in RECORD_KEYS}
    rec["pchembl_value"] = _p(raw.get("pchembl_value"))
    return rec


def summarise_potency(raw_records: list[dict]) -> PotencySummary:
    records = [normalise_record(r) for r in raw_records]
    s = PotencySummary(n_records=len(records))
    s.n_assays = len({r["assay_chembl_id"] for r in records if r["assay_chembl_id"]})
    s.n_documents = len({r["document_chembl_id"] for r in records if r["document_chembl_id"]})
    with_p = [r for r in records if r["pchembl_value"] is not None]
    s.n_without_pchembl = len(records) - len(with_p)
    s.n_censored = sum(1 for r in records if r["standard_relation"] not in (None, "="))
    s.n_functional = sum(1 for r in records if r["assay_type"] == "F")
    s.n_exact = sum(1 for r in with_p if r["standard_relation"] == "=")
    if with_p:
        best = max(with_p, key=lambda r: r["pchembl_value"])
        s.max_pchembl = best["pchembl_value"]
        s.max_record = {k: best[k] for k in ("activity_id", "assay_chembl_id", "assay_type", "standard_type",
                                               "document_chembl_id", "assay_description")}
    comparable = [r for r in with_p if r["assay_type"] == "B" and r["standard_relation"] == "="
                  and r["standard_type"] in COMPARABLE_TYPES]
    for t in COMPARABLE_TYPES:
        vals = sorted(r["pchembl_value"] for r in comparable if r["standard_type"] == t)
        if vals:
            s.by_type[t] = {"n": len(vals), "median": round(median(vals), 2), "min": vals[0], "max": vals[-1],
                            "assays": len({r["assay_chembl_id"] for r in comparable if r["standard_type"] == t})}
    if s.by_type:
        s.primary_type = max(COMPARABLE_TYPES, key=lambda t: (s.by_type.get(t, {}).get("n", 0), -COMPARABLE_TYPES.index(t)))
        info = s.by_type[s.primary_type]
        s.aggregate_pchembl, s.aggregate_n = info["median"], info["n"]
        s.range, s.spread = [info["min"], info["max"]], round(info["max"] - info["min"], 2)
        s.aggregate_method = (f"median pChEMBL of {info['n']} exact (relation '=') {s.primary_type} binding-assay "
                              f"(assay_type B) measurements across {info['assays']} assays; other measurement "
                              f"types are reported separately and never pooled")
        s.sparse = info["n"] < 2
        s.conflicting = info["n"] >= 2 and s.spread >= CONFLICT_LOG_UNITS
        if s.sparse:
            s.flags.append(f"Single exact {s.primary_type} measurement: potency rests on one assay and is not corroborated.")
        if s.conflicting:
            s.flags.append(f"Conflicting measurements: exact {s.primary_type} values span {s.spread:.1f} log units "
                           f"({info['min']}–{info['max']}); assay context differs and the median may hide this.")
        other = [t for t in s.by_type if t != s.primary_type]
        if other:
            s.flags.append(f"Additional measurement types not pooled: {', '.join(other)}.")
    else:
        s.flags.append("No exact binding-assay measurement of a comparable type (IC50/Ki/Kd/EC50); "
                       "no aggregate potency is assigned and only the strongest isolated record is shown.")
    if s.n_censored:
        s.flags.append(f"{s.n_censored} censored record(s) (relation other than '=') excluded from the aggregate.")
    if s.n_functional:
        s.flags.append(f"{s.n_functional} functional-assay record(s) counted but not pooled with binding data.")
    if any(r["data_validity_comment"] for r in records):
        s.flags.append("ChEMBL flagged a data-validity concern on at least one record.")
    ordered = sorted(records, key=lambda r: (-(r["pchembl_value"] if r["pchembl_value"] is not None else -1), r["activity_id"] or 0))
    s.records = ordered[:RECORDS_KEPT]
    s.records_omitted = max(0, len(ordered) - RECORDS_KEPT)
    return s
