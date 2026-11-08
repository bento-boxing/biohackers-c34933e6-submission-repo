from pipeline.clients.chembl import (
    chembl_molecule_url, chembl_target_url, find_target, molecules, potent_activities, potent_count,
)


def test_find_target_lrrk2_by_accession_is_chembl1075104(client):
    assert find_target(client, "Q5S007", "LRRK2") == "CHEMBL1075104"


def test_find_target_none_when_no_accession_and_no_symbol_hit(client):
    assert find_target(client, None, "ZZQXV1") is None


def test_potent_count_lrrk2_over_1000(client):
    assert potent_count(client, "CHEMBL1075104") > 1000


def test_potent_activities_capped_at_max_pages(client):
    acts = potent_activities(client, "CHEMBL1075104", max_pages=1)
    assert 0 < len(acts) <= 1000
    assert {"molecule_chembl_id", "pchembl_value"} <= set(acts[0])


def test_molecules_batch_returns_max_phase_string(client):
    m = molecules(client, ["CHEMBL1721885"])
    assert m["CHEMBL1721885"]["max_phase"] == "2.0"
    assert m["CHEMBL1721885"]["molecule_properties"]["num_ro5_violations"] == 0


def test_urls():
    assert chembl_target_url("CHEMBL1") == "https://www.ebi.ac.uk/chembl/target_report_card/CHEMBL1/"
    assert chembl_molecule_url("CHEMBL2") == "https://www.ebi.ac.uk/chembl/compound_report_card/CHEMBL2/"


class _Stub:
    def __init__(self):
        self.calls = []

    def get_json(self, url, params=None):
        self.calls.append((url, params))
        return {"targets": []}


def test_find_target_with_accession_but_no_hit_does_not_fall_back_to_symbol():
    stub = _Stub()
    assert find_target(stub, "P99999", "APP") is None
    assert len(stub.calls) == 1 and "target.json" in stub.calls[0][0]


class _Pager:
    """Answers activity queries with fixed pages so pagination logic can be checked without the network."""

    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get_json(self, url, params=None):
        self.calls.append((url, params))
        if "activity.json" in url:
            i = params.get("offset", 0) // params["limit"]
            return self.pages[i]
        return {"molecules": [], "drug_indications": [], "targets": []}


def test_ranked_activities_orders_by_potency_and_labels_partial_coverage():
    from pipeline.clients.chembl import ranked_activities
    rows = [{"molecule_chembl_id": f"M{i}", "pchembl_value": str(10 - i * 0.5), "activity_id": i} for i in range(4)]
    pages = [{"activities": rows[:2], "page_meta": {"total_count": 4, "next": "x"}},
             {"activities": rows[2:], "page_meta": {"total_count": 4, "next": None}}]
    pager = _Pager(pages)
    got = ranked_activities(pager, "CHEMBL203", max_rows=2, page_size=2)
    assert pager.calls[0][1]["order_by"] == "-pchembl_value" and pager.calls[0][1]["pchembl_value__gte"] == 6
    assert [a["activity_id"] for a in got["activities"]] == [0, 1]
    assert got["total_count"] == 4 and got["retrieved"] == 2 and got["complete"] is False
    assert got["cutoff_pchembl"] == 9.5 and "descending" in got["selection_method"]
    full = ranked_activities(_Pager(pages), "CHEMBL203", max_rows=10, page_size=2)
    assert full["complete"] is True and full["retrieved"] == 4 and full["cutoff_pchembl"] is None


def test_molecule_activities_batches_ids_and_reports_truncated_batches():
    from pipeline.clients.chembl import molecule_activities
    page = {"activities": [{"activity_id": 1}], "page_meta": {"total_count": 5000, "next": "more"}}
    pager = _Pager([page] * 3)
    records, truncated = molecule_activities(pager, [f"M{i}" for i in range(12)], target_chembl_id="CHEMBL203",
                                             batch_size=10, max_pages=2)
    assert len(pager.calls) == 4  # two batches x two pages, stopped by max_pages
    first = ",".join(sorted(f"M{i}" for i in range(12))[:10])
    assert pager.calls[0][1]["molecule_chembl_id__in"] == first
    assert pager.calls[0][1]["target_chembl_id"] == "CHEMBL203"
    assert len(records) == 4 and truncated == [first, "M8,M9"]
