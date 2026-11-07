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
