"""ChEMBL REST client: target resolution, potency counts, molecule lookups."""
from __future__ import annotations

from pipeline.http import HttpClient

CHEMBL_BASE = "https://www.ebi.ac.uk/chembl/api/data/"
POTENT_PCHEMBL = 6  # pChEMBL 6 == 1 uM
ACTIVITY_FIELDS = "molecule_chembl_id,pchembl_value,assay_type,standard_type"
MOLECULE_FIELDS = "molecule_chembl_id,pref_name,max_phase,molecule_properties"


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


def potent_activities(client: HttpClient, chembl_target_id: str, max_pages: int = 5) -> list[dict]:
    out: list[dict] = []
    for page in range(max_pages):
        data = client.get_json(CHEMBL_BASE + "activity.json", {
            "target_chembl_id": chembl_target_id, "pchembl_value__gte": POTENT_PCHEMBL,
            "limit": 1000, "offset": page * 1000, "only": ACTIVITY_FIELDS})
        out.extend(data.get("activities") or [])
        if not data.get("page_meta", {}).get("next"):
            break
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
