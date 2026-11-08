"""Clinical-development dimension: ChEMBL max_phase qualified by indication.

A development phase reached in another disease is human-exposure precedent, not efficacy evidence
for the approved disease; the two are reported as different statuses and never conflated.
"""
from __future__ import annotations

PHASE_LABELS = {0.5: "Early phase 1", 1.0: "Phase 1", 2.0: "Phase 2", 3.0: "Phase 3", 4.0: "Approved (phase 4)"}


def _phase(value) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _norm(identifier: str | None) -> str:
    return (identifier or "").replace(":", "_").strip().casefold()


def qualify_clinical(max_phase, indications: list[dict] | None, disease_id: str | None, disease_name: str | None) -> dict:
    phase = _phase(max_phase)
    out = {"phase": phase, "phase_label": PHASE_LABELS.get(phase, "No development record" if phase is None else f"Phase {phase:g}"),
           "matched": [], "matched_max_phase": None, "other_count": 0, "other_examples": [], "note": ""}
    if phase is None or phase < 1:
        out["indication_status"] = "preclinical"
        out["note"] = "No clinical development recorded in ChEMBL (preclinical or research compound)."
        return out
    if indications is None:
        out["indication_status"] = "not_checked"
        out["note"] = "Indications were not retrieved; the phase is not qualified against the approved disease."
        return out
    want_id, want_name = _norm(disease_id), (disease_name or "").strip().casefold()
    others: list[str] = []
    for row in indications:
        term = (row.get("efo_term") or "").strip()
        mesh = (row.get("mesh_heading") or "").strip()
        if (want_id and _norm(row.get("efo_id")) == want_id) or (want_name and want_name in (term.casefold(), mesh.casefold())):
            out["matched"].append({"efo_id": row.get("efo_id"), "efo_term": term, "mesh_heading": mesh,
                                   "max_phase_for_ind": _phase(row.get("max_phase_for_ind"))})
        elif term or mesh:
            others.append(term or mesh)
    out["other_count"] = len(others)
    out["other_examples"] = sorted(set(others), key=str.casefold)[:5]
    if out["matched"]:
        phases = [m["max_phase_for_ind"] for m in out["matched"] if m["max_phase_for_ind"] is not None]
        out["matched_max_phase"] = max(phases) if phases else None
        out["indication_status"] = "matched"
        out["note"] = (f"ChEMBL records development for the approved disease ({out['matched'][0]['efo_term']}"
                       f"{f', phase {out['matched_max_phase']:g}' if out['matched_max_phase'] is not None else ''}).")
    elif others:
        out["indication_status"] = "other_indications_only"
        out["note"] = (f"Development recorded only for other indications ({', '.join(out['other_examples'])}"
                       f"{'…' if len(others) > 5 else ''}); this is human-exposure precedent, not evidence of efficacy "
                       f"in the approved disease.")
    else:
        out["indication_status"] = "no_indication_records"
        out["note"] = "ChEMBL lists a development phase but no indication records; the phase cannot be qualified."
    return out
