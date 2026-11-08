"""ChEMBL REST client: target resolution, potency counts, molecule lookups."""
from __future__ import annotations

from pipeline.http import HttpClient

CHEMBL_BASE = "https://www.ebi.ac.uk/chembl/api/data/"
POTENT_PCHEMBL = 6  # pChEMBL 6 == 1 uM
# Every identifier and assay-context field is kept so potency can be interpreted, not just maximised.
ACTIVITY_FIELDS = ("activity_id,molecule_chembl_id,assay_chembl_id,assay_type,assay_description,bao_label,"
                   "standard_type,standard_relation,standard_value,standard_units,pchembl_value,target_chembl_id,"
                   "document_chembl_id,data_validity_comment,potential_duplicate")
MOLECULE_FIELDS = "molecule_chembl_id,pref_name,max_phase,first_approval,molecule_properties"
INDICATION_FIELDS = "molecule_chembl_id,efo_id,efo_term,mesh_heading,max_phase_for_ind"
TARGET_FIELDS = "target_chembl_id,pref_name,organism,target_type"
ORDER_BY_POTENCY = "-pchembl_value"


def _human_single_protein(targets: list[dict]) -> str | None:
    for t in targets:
        if t.get("organism") == "Homo sapiens" and t.get("target_type") == "SINGLE PROTEIN":
            return t["target_chembl_id"]
    return None


def find_target(client: HttpClient, uniprot: str | None, symbol: str) -> str | None:
    if uniprot:
        data = client.get_json(CHEMBL_BASE + "target.json", {
            "target_components__accession": uniprot, "target_type": "SINGLE PROTEIN", "limit": 5})
        # Accession lookup is authoritative: never fall back to the ambiguous symbol search.
        return _human_single_protein(data.get("targets") or [])
    data = client.get_json(CHEMBL_BASE + "target/search.json", {"q": symbol, "limit": 10})
    return _human_single_protein(data.get("targets") or [])


def potent_count(client: HttpClient, chembl_target_id: str) -> int:
    data = client.get_json(CHEMBL_BASE + "activity.json", {
        "target_chembl_id": chembl_target_id, "pchembl_value__gte": POTENT_PCHEMBL, "limit": 1})
    return int(data["page_meta"]["total_count"])


def ranked_activities(client: HttpClient, chembl_target_id: str, max_rows: int = 5000, page_size: int = 1000) -> dict:
    """Stage-1 retrieval: potent records ordered strongest first, with an explicit coverage record.

    Ordering means truncation never drops a record stronger than any retrieved one: every omitted
    record has pChEMBL <= `cutoff_pchembl` (the weakest retrieved value). The result says so.
    """
    out: list[dict] = []
    total = 0
    while len(out) < max_rows:
        limit = min(page_size, max_rows - len(out))
        data = client.get_json(CHEMBL_BASE + "activity.json", {
            "target_chembl_id": chembl_target_id, "pchembl_value__gte": POTENT_PCHEMBL, "order_by": ORDER_BY_POTENCY,
            "limit": limit, "offset": len(out), "only": ACTIVITY_FIELDS})
        rows = data.get("activities") or []
        total = int((data.get("page_meta") or {}).get("total_count") or 0)
        out.extend(rows)
        if not rows or not (data.get("page_meta") or {}).get("next"):
            break
    complete = len(out) >= total
    values = [float(a["pchembl_value"]) for a in out if a.get("pchembl_value") is not None]
    cutoff = None if complete or not values else min(values)
    method = (f"activity records with pChEMBL >= {POTENT_PCHEMBL} ordered by pChEMBL descending; "
              + (f"all {total} records retrieved" if complete else
                 f"retrieval stopped at {len(out)} of {total} records, so every omitted record has pChEMBL <= {cutoff}"))
    return {"activities": out, "total_count": total, "retrieved": len(out), "complete": complete,
            "cutoff_pchembl": cutoff, "order_by": ORDER_BY_POTENCY, "selection_method": method}


def potent_activities(client: HttpClient, chembl_target_id: str, max_pages: int = 5) -> list[dict]:
    return ranked_activities(client, chembl_target_id, max_rows=max_pages * 1000)["activities"]


def molecule_activities(client: HttpClient, molecule_ids: list[str], target_chembl_id: str | None = None,
                        batch_size: int = 10, max_pages: int = 3, page_size: int = 1000) -> tuple[list[dict], list[str]]:
    """All activity records for the given molecules (stage 2: on one target; stage 3: across targets).

    Returns (records, truncated_batches): a batch is listed as truncated when it had more pages than
    `max_pages`, so callers can label the evidence as partial instead of pretending it is complete.
    """
    ids = sorted(set(molecule_ids))
    records: list[dict] = []
    truncated: list[str] = []
    for i in range(0, len(ids), batch_size):
        batch = ",".join(ids[i:i + batch_size])
        params = {"molecule_chembl_id__in": batch, "limit": page_size, "only": ACTIVITY_FIELDS}
        if target_chembl_id:
            params["target_chembl_id"] = target_chembl_id
        else:
            params["pchembl_value__isnull"] = "false"
        for page in range(max_pages):
            data = client.get_json(CHEMBL_BASE + "activity.json", {**params, "offset": page * page_size})
            records.extend(data.get("activities") or [])
            if not (data.get("page_meta") or {}).get("next"):
                break
        else:
            truncated.append(batch)
    return records, truncated


def drug_indications(client: HttpClient, molecule_ids: list[str]) -> dict[str, list[dict]]:
    """ChEMBL drug_indication rows per molecule (EFO id/term, MeSH heading, phase for that indication)."""
    out: dict[str, list[dict]] = {}
    ids = sorted(set(molecule_ids))
    for i in range(0, len(ids), 25):
        batch = ids[i:i + 25]
        offset = 0
        while True:
            data = client.get_json(CHEMBL_BASE + "drug_indication.json", {
                "molecule_chembl_id__in": ",".join(batch), "only": INDICATION_FIELDS, "limit": 1000, "offset": offset})
            rows = data.get("drug_indications") or []
            for row in rows:
                out.setdefault(row["molecule_chembl_id"], []).append(row)
            if not rows or not (data.get("page_meta") or {}).get("next"):
                break
            offset += 1000
    return out


def targets(client: HttpClient, target_ids: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    ids = sorted(set(target_ids))
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        data = client.get_json(CHEMBL_BASE + "target.json", {
            "target_chembl_id__in": ",".join(batch), "only": TARGET_FIELDS, "limit": 50})
        for t in data.get("targets") or []:
            out[t["target_chembl_id"]] = t
    return out


def molecules(client: HttpClient, chembl_ids: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    ids = sorted(set(chembl_ids))
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        data = client.get_json(CHEMBL_BASE + "molecule.json", {
            "molecule_chembl_id__in": ",".join(batch), "only": MOLECULE_FIELDS, "limit": 50})
        for m in data.get("molecules") or []:
            out[m["molecule_chembl_id"]] = m
    return out


def chembl_target_url(chembl_id: str) -> str:
    return f"https://www.ebi.ac.uk/chembl/target_report_card/{chembl_id}/"


def chembl_molecule_url(chembl_id: str) -> str:
    return f"https://www.ebi.ac.uk/chembl/compound_report_card/{chembl_id}/"
