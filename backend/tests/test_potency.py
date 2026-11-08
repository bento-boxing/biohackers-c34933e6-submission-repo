from pipeline.screening.potency import summarise_potency


def rec(mid="A", pchembl="7.0", stype="IC50", rel="=", atype="B", assay="CHEMBL_A1", doc="CHEMBL_D1", aid=1,
        value="100", units="nM"):
    return {"activity_id": aid, "molecule_chembl_id": mid, "assay_chembl_id": assay, "assay_type": atype,
            "assay_description": "desc", "bao_label": "single protein format", "standard_type": stype,
            "standard_relation": rel, "standard_value": value, "standard_units": units, "pchembl_value": pchembl,
            "target_chembl_id": "CHEMBL203", "document_chembl_id": doc, "data_validity_comment": None,
            "potential_duplicate": 0}


def test_median_of_exact_binding_measurements_of_one_type_not_the_maximum():
    s = summarise_potency([rec(pchembl="6.0", aid=1), rec(pchembl="7.0", aid=2, assay="CHEMBL_A2"),
                           rec(pchembl="9.0", aid=3, assay="CHEMBL_A3")])
    assert s.aggregate_pchembl == 7.0 and s.max_pchembl == 9.0
    assert s.primary_type == "IC50" and s.aggregate_n == 3 and s.n_assays == 3
    assert "median" in s.aggregate_method and "IC50" in s.aggregate_method
    assert s.max_record["activity_id"] == 3 and s.max_record["assay_chembl_id"] == "CHEMBL_A3"


def test_types_are_never_pooled_and_the_most_measured_type_is_primary():
    s = summarise_potency([rec(stype="Ki", pchembl="9.0", aid=1), rec(stype="IC50", pchembl="6.0", aid=2),
                           rec(stype="IC50", pchembl="6.5", aid=3)])
    assert s.primary_type == "IC50" and s.aggregate_pchembl == 6.25
    assert s.by_type["Ki"]["median"] == 9.0 and s.by_type["IC50"]["n"] == 2


def test_conflicting_and_sparse_measurements_are_flagged():
    wide = summarise_potency([rec(pchembl="6.0", aid=1), rec(pchembl="8.5", aid=2)])
    assert wide.conflicting and wide.spread == 2.5 and any("conflict" in f.lower() for f in wide.flags)
    single = summarise_potency([rec(pchembl="8.0")])
    assert single.sparse and not single.conflicting and any("single" in f.lower() for f in single.flags)


def test_censored_functional_and_unitless_records_are_counted_but_not_aggregated():
    s = summarise_potency([rec(pchembl=None, rel=">", value="10000", aid=1),
                           rec(atype="F", pchembl="8.0", aid=2),
                           rec(pchembl="7.0", aid=3)])
    assert s.aggregate_pchembl == 7.0 and s.aggregate_n == 1
    assert s.n_censored == 1 and s.n_functional == 1 and s.n_records == 3


def test_no_exact_binding_measurement_means_no_aggregate_but_the_max_is_still_reported():
    s = summarise_potency([rec(atype="F", pchembl="8.0", aid=1), rec(pchembl=None, rel=">", aid=2)])
    assert s.aggregate_pchembl is None and s.max_pchembl == 8.0
    assert any("no exact binding" in f.lower() for f in s.flags)


def test_identifiers_are_preserved_on_every_retained_record():
    s = summarise_potency([rec(aid=i, assay=f"CHEMBL_A{i}") for i in range(1, 4)])
    assert {r["activity_id"] for r in s.records} == {1, 2, 3}
    assert all({"assay_chembl_id", "target_chembl_id", "document_chembl_id", "standard_type",
                "standard_relation", "standard_units"} <= set(r) for r in s.records)
