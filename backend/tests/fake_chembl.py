"""An in-memory stand-in for ChEMBL + AlphaFold so staged screening can be tested deterministically."""
from __future__ import annotations


def act(mid, pchembl, target="CHEMBL203", stype="IC50", rel="=", atype="B", aid=None, assay=None, doc="CHEMBL_DOC"):
    return {"activity_id": aid or hash((mid, pchembl, target, stype, aid)) % 10**8, "molecule_chembl_id": mid,
            "assay_chembl_id": assay or f"ASSAY_{target}_{stype}", "assay_type": atype, "assay_description": "d",
            "bao_label": "single protein format", "standard_type": stype, "standard_relation": rel,
            "standard_value": "1", "standard_units": "nM", "pchembl_value": None if pchembl is None else str(pchembl),
            "target_chembl_id": target, "document_chembl_id": doc, "data_validity_comment": None, "potential_duplicate": 0}


class FakeChembl:
    cache_only = False

    def __init__(self, activities, molecules, indications=None, targets=None, potent_filter=6):
        self.activities, self.molecules = activities, molecules
        self.indications, self.targets = indications or {}, targets or {}
        self.calls = []

    def _page(self, rows, params, key):
        limit, offset = int(params.get("limit", 20)), int(params.get("offset", 0))
        page = rows[offset:offset + limit]
        nxt = "more" if offset + limit < len(rows) else None
        return {key: page, "page_meta": {"total_count": len(rows), "limit": limit, "offset": offset, "next": nxt}}

    def get_json(self, url, params=None):
        params = params or {}
        self.calls.append((url.rsplit("/", 1)[-1], dict(params)))
        if url.endswith("activity.json"):
            rows = list(self.activities)
            if "target_chembl_id" in params:
                rows = [a for a in rows if a["target_chembl_id"] == params["target_chembl_id"]]
            if "molecule_chembl_id__in" in params:
                ids = set(params["molecule_chembl_id__in"].split(","))
                rows = [a for a in rows if a["molecule_chembl_id"] in ids]
            if "pchembl_value__gte" in params:
                rows = [a for a in rows if a["pchembl_value"] is not None and float(a["pchembl_value"]) >= params["pchembl_value__gte"]]
            if params.get("pchembl_value__isnull") == "false":
                rows = [a for a in rows if a["pchembl_value"] is not None]
            if params.get("order_by") == "-pchembl_value":
                rows.sort(key=lambda a: -float(a["pchembl_value"]))
            return self._page(rows, params, "activities")
        if url.endswith("molecule.json"):
            ids = params["molecule_chembl_id__in"].split(",")
            return {"molecules": [self.molecules[i] for i in ids if i in self.molecules]}
        if url.endswith("drug_indication.json"):
            ids = params["molecule_chembl_id__in"].split(",")
            rows = [r for i in ids for r in self.indications.get(i, [])]
            return self._page(rows, params, "drug_indications")
        if url.endswith("target.json"):
            ids = params["target_chembl_id__in"].split(",")
            return {"targets": [self.targets[i] for i in ids if i in self.targets]}
        raise AssertionError(f"unexpected url {url}")
