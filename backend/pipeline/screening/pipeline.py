"""Stage 2: approved target -> staged ChEMBL retrieval, four-factor evidence, heuristic prioritisation.

Stages (each recorded in `ScreeningResult.coverage`):
  1. potent on-target records ordered strongest first (ordered truncation: nothing omitted is stronger
     than anything retrieved; the cutoff is reported);
  2. the complete on-target record set for the candidate pool (top-N by aggregate potency united with
     top-N by maximum potency, so the potency-only baseline is reproducible);
  3. observed off-target records for the shortlisted molecules (limited, labelled);
  plus molecule properties (QED, Ro5, phase) and ChEMBL drug indications for phased molecules.
"""
from __future__ import annotations

import copy
import time

from pipeline.clients import alphafold, chembl
from pipeline.http import HttpClient, default_client
from pipeline.models import Approval, Compound, ScreeningResult
from pipeline.screening.clinical import qualify_clinical
from pipeline.screening.potency import summarise_potency
from pipeline.screening.ranking import rank_compounds
from pipeline.screening.rubric import Rubric, prioritise
from pipeline.screening.selectivity import assess_selectivity

DEFAULT_MAX_ROWS = 5000
DEFAULT_SELECTIVITY_N = 10
DEFAULT_BUDGET_SECONDS = 200.0


def _f(x) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def _i(x) -> int | None:
    try:
        return None if x is None else int(x)
    except (TypeError, ValueError):
        return None


def _rubric(rubric) -> Rubric:
    if isinstance(rubric, Rubric):
        return rubric
    rubric = rubric or {}
    return Rubric(objective=rubric.get("objective") or "balanced", weights=rubric.get("weights") or {})


def _compound(mid: str, summary, mol: dict) -> Compound:
    props = mol.get("molecule_properties") or {}
    max_rec = summary.max_record or {}
    missing = []
    if not props:
        missing.append("ChEMBL molecule properties (QED, Lipinski) not recorded")
    elif props.get("qed_weighted") is None:
        missing.append("QED not recorded")
    if mol.get("max_phase") is None:
        missing.append("no development phase recorded (preclinical/research compound)")
    return Compound(
        chembl_id=mid, name=mol.get("pref_name"), best_pchembl=summary.max_pchembl or 0.0,
        assay_type=max_rec.get("assay_type"), max_phase=mol.get("max_phase"),
        mw=_f(props.get("full_mwt")), alogp=_f(props.get("alogp")), hbd=_i(props.get("hbd")), hba=_i(props.get("hba")),
        psa=_f(props.get("psa")), ro5_violations=_i(props.get("num_ro5_violations")), qed=_f(props.get("qed_weighted")),
        first_approval=_i(mol.get("first_approval")), potency=summary.as_dict(), missing_data=missing,
    )


def run_screening(approval: Approval, top_n: int = 50, client: HttpClient | None = None, *, rubric=None,
                  max_rows: int = DEFAULT_MAX_ROWS, selectivity_n: int = DEFAULT_SELECTIVITY_N,
                  budget_seconds: float = DEFAULT_BUDGET_SECONDS) -> ScreeningResult:
    client = client or default_client()
    rubric = _rubric(rubric)
    started = time.monotonic()
    notes: list[str] = []
    coverage: dict = {"partial": False}
    compounds: list[Compound] = []
    baseline: list[str] = []
    target = approval.chembl_target_id
    if target:
        # stage 1: ordered potent records
        stage1 = chembl.ranked_activities(client, target, max_rows=max_rows)
        acts = stage1.pop("activities")
        coverage["stage1"] = stage1
        if not stage1["complete"]:
            coverage["partial"] = True
            notes.append(f"Partial retrieval: {stage1['selection_method']}. Molecules whose every measurement is weaker "
                         f"than pChEMBL {stage1['cutoff_pchembl']} were not retrieved.")
        by_mol: dict[str, list[dict]] = {}
        for a in acts:
            by_mol.setdefault(a["molecule_chembl_id"], []).append(a)
        prelim = {mid: summarise_potency(rows) for mid, rows in by_mol.items()}
        by_max = sorted(prelim, key=lambda m: (-(prelim[m].max_pchembl or 0), m))
        by_agg = sorted((m for m in prelim if prelim[m].aggregate_pchembl is not None),
                        key=lambda m: (-prelim[m].aggregate_pchembl, m))
        pool = list(dict.fromkeys(by_max[:top_n] + by_agg[:top_n]))
        coverage["candidate_pool"] = {"size": len(pool), "molecules_retrieved": len(prelim),
                                      "method": f"union of the top {top_n} molecules by maximum pChEMBL (baseline) and the top "
                                                f"{top_n} by preliminary median pChEMBL"}
        # stage 2: complete on-target records for the pool (adds measurements below the cutoff and censored records)
        on_records, truncated = chembl.molecule_activities(client, pool, target_chembl_id=target)
        complete: dict[str, list[dict]] = {m: [] for m in pool}
        for a in on_records:
            if a["molecule_chembl_id"] in complete:
                complete[a["molecule_chembl_id"]].append(a)
        for m in pool:
            if not complete[m]:
                complete[m] = by_mol[m]
        coverage["stage2"] = {"molecules": len(pool), "records": len(on_records), "truncated_batches": len(truncated)}
        if truncated:
            coverage["partial"] = True
            notes.append(f"On-target record sets for {len(truncated)} batch(es) were truncated; aggregates for those molecules rest on a subset.")
        summaries = {m: summarise_potency(complete[m]) for m in pool}
        mols = chembl.molecules(client, pool)
        compounds = [_compound(m, summaries[m], mols.get(m) or {}) for m in pool]
        # baseline: the pre-existing potency-only ordering (max pChEMBL, then Ro5, then id)
        baseline = [c.chembl_id for c in rank_compounds(list(compounds))]
        for c in compounds:
            c.baseline_rank = baseline.index(c.chembl_id) + 1
        # clinical: indications for phased molecules
        phased = [c.chembl_id for c in compounds if _f(c.max_phase) is not None and _f(c.max_phase) >= 1]
        indications = chembl.drug_indications(client, phased) if phased else {}
        coverage["indications"] = {"molecules_checked": len(phased), "molecules_with_records": len(indications)}
        for c in compounds:
            c.clinical = qualify_clinical(c.max_phase, indications.get(c.chembl_id, []) if c.chembl_id in phased else [],
                                          approval.disease_id, approval.disease_name)
        # stage 3: observed off-target activity for the shortlist. The shortlist is fixed by the default
        # (balanced) rubric before selectivity is known, independent of the requested rubric, so every
        # objective and the recorded demo share one shortlist and the request cannot steer retrieval.
        preliminary = prioritise([copy.copy(c) for c in compounds], Rubric())
        shortlist = [c.chembl_id for c in preliminary[:max(0, selectivity_n)]]
        assessed, truncated3, skipped = [], [], []
        off_by_mol: dict[str, list[dict]] = {}
        for i in range(0, len(shortlist), 5):
            batch = shortlist[i:i + 5]
            if time.monotonic() - started > budget_seconds:
                skipped.extend(shortlist[i:])
                break
            records, trunc = chembl.molecule_activities(client, batch, target_chembl_id=None, batch_size=5)
            for a in records:
                off_by_mol.setdefault(a["molecule_chembl_id"], []).append(a)
            assessed.extend(batch)
            truncated3.extend(trunc)
        off_target_ids = {a["target_chembl_id"] for rows in off_by_mol.values() for a in rows
                          if a.get("target_chembl_id") and a["target_chembl_id"] != target}
        names = chembl.targets(client, sorted(off_target_ids)[:200]) if off_target_ids else {}
        truncated_mols = {m for batch in truncated3 for m in batch.split(",")}
        for c in compounds:
            if c.chembl_id in assessed:
                c.selectivity = assess_selectivity(c.chembl_id, target, summaries[c.chembl_id], off_by_mol.get(c.chembl_id, []),
                                                   names, truncated=c.chembl_id in truncated_mols)
            else:
                c.selectivity = assess_selectivity(c.chembl_id, target, summaries[c.chembl_id], None, names, truncated=False)
        coverage["stage3"] = {"molecules_assessed": len(assessed), "shortlist": shortlist, "truncated_batches": len(truncated3),
                              "skipped_for_budget": skipped,
                              "method": f"all ChEMBL activity records with a pChEMBL value for the top {selectivity_n} candidates; "
                                        f"only exact binding measurements of the on-target primary type are compared"}
        if skipped or truncated3:
            coverage["partial"] = True
        if skipped:
            notes.append(f"Off-target retrieval skipped for {len(skipped)} shortlisted molecule(s) because the time budget ran out.")
        compounds = prioritise(compounds, rubric)
    structure = alphafold.prediction(client, approval.uniprot) if approval.uniprot else None
    coverage["elapsed_seconds"] = round(time.monotonic() - started, 2)
    return ScreeningResult(approval=approval, structure=structure, compounds=compounds, coverage=coverage,
                           rubric=rubric.describe(), baseline=baseline, notes=notes)
