from pipeline.screening.potency import summarise_potency
from pipeline.screening.selectivity import assess_selectivity
from tests.test_potency import rec


def on_target():
    return summarise_potency([rec(pchembl="8.0", aid=1), rec(pchembl="8.2", aid=2, assay="CHEMBL_A2")])


def off(target, pchembl, stype="IC50", atype="B", rel="=", aid=100, assay="CHEMBL_OFF1"):
    r = rec(pchembl=pchembl, stype=stype, atype=atype, rel=rel, aid=aid, assay=assay)
    r["target_chembl_id"] = target
    return r


def test_observed_window_uses_only_comparable_offtarget_records():
    records = [off("CHEMBL100", "6.0", aid=1), off("CHEMBL100", "6.4", aid=2, assay="CHEMBL_OFF2"),
               off("CHEMBL101", "9.0", stype="Ki", aid=3, assay="CHEMBL_OFF3"),
               off("CHEMBL102", "9.5", atype="F", aid=4, assay="CHEMBL_OFF4"),
               off("CHEMBL203", "8.0", aid=5)]  # the on-target record itself is ignored
    s = assess_selectivity("A", "CHEMBL203", on_target(), records, {"CHEMBL100": {"pref_name": "Kinase X", "organism": "Homo sapiens"}}, truncated=False)
    assert s["status"] == "assessed" and s["evidence"] == "observed_window"
    assert s["targets_tested"] == 3 and s["assays_tested"] == 4 and s["comparable_records"] == 2
    assert s["incomparable_records"] == 2
    assert s["window"] == round(8.1 - 6.2, 2) and s["most_potent_comparable_off_target"]["name"] == "Kinase X"
    # listed strongest-first regardless of comparability, and the incomparable ones say so
    assert [t["target_chembl_id"] for t in s["off_targets"]] == ["CHEMBL102", "CHEMBL101", "CHEMBL100"]
    assert [t["comparable"] for t in s["off_targets"]] == [False, False, True]


def test_no_offtarget_records_is_never_reported_as_selective():
    s = assess_selectivity("A", "CHEMBL203", on_target(), [off("CHEMBL203", "8.0")], {}, truncated=False)
    assert s["status"] == "assessed" and s["evidence"] == "no_off_target_records"
    assert s["window"] is None and s["targets_tested"] == 0
    assert "not evidence of selectivity" in s["caution"].lower()


def test_only_incomparable_records_gives_no_window_but_reports_coverage():
    s = assess_selectivity("A", "CHEMBL203", on_target(), [off("CHEMBL101", "9.0", stype="Ki")], {}, truncated=True)
    assert s["evidence"] == "no_comparable_off_target_records" and s["window"] is None
    assert s["targets_tested"] == 1 and s["partial"] is True


def test_not_assessed_is_explicit():
    s = assess_selectivity("A", "CHEMBL203", on_target(), None, {}, truncated=False)
    assert s["status"] == "not_assessed" and s["evidence"] == "not_assessed" and s["window"] is None
