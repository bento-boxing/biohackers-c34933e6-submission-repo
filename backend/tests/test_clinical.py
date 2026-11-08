from pipeline.screening.clinical import qualify_clinical


def ind(efo_id, term, phase="4.0"):
    return {"efo_id": efo_id, "efo_term": term, "mesh_heading": term, "max_phase_for_ind": phase}


def test_phase_4_in_another_disease_is_other_indication_not_a_match():
    c = qualify_clinical("4.0", [ind("EFO:0003060", "non-small cell lung carcinoma")], "MONDO_0005180", "Parkinson disease")
    assert c["indication_status"] == "other_indications_only" and c["matched"] == []
    assert c["other_count"] == 1 and "non-small cell lung carcinoma" in c["other_examples"]
    assert "not evidence" in c["note"].lower()


def test_indication_matches_by_efo_id_or_by_disease_name():
    by_id = qualify_clinical("4.0", [ind("EFO:0003060", "NSCLC")], "EFO_0003060", "non-small cell lung carcinoma")
    by_name = qualify_clinical("2.0", [ind("MONDO:0000001", "Non-Small Cell Lung Carcinoma", "2.0")], "EFO_0003060",
                               "non-small cell lung carcinoma")
    assert by_id["indication_status"] == "matched" and by_id["matched"][0]["efo_id"] == "EFO:0003060"
    assert by_name["indication_status"] == "matched" and by_name["matched_max_phase"] == 2.0


def test_preclinical_and_unchecked_are_distinguished():
    assert qualify_clinical(None, [], "X", "x")["indication_status"] == "preclinical"
    assert qualify_clinical("0.5", [], "X", "x")["indication_status"] == "preclinical"
    checked = qualify_clinical("3.0", [], "X", "x")
    assert checked["indication_status"] == "no_indication_records"
    unchecked = qualify_clinical("3.0", None, "X", "x")
    assert unchecked["indication_status"] == "not_checked" and unchecked["phase"] == 3.0
