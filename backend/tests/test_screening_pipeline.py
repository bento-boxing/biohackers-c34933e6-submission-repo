from pipeline.models import Approval, Weights
from pipeline.screening.pipeline import run_screening


def approval(chembl_target_id="CHEMBL1075104", uniprot="Q5S007", approval_id="appr-lrrk2"):
    return Approval(approval_id=approval_id, ts="2026-11-07T00:00:00Z", disease_id="MONDO_0005180", disease_name="Parkinson disease",
                    target_id="ENSG00000188906", symbol="LRRK2", uniprot=uniprot,
                    chembl_target_id=chembl_target_id, weights=Weights().as_dict(), scores={},
                    safety_flags=[], reason="x", approved_by="t")


def test_run_screening_lrrk2_returns_the_candidate_pool_ranked_with_a_baseline(client):
    r = run_screening(approval(), top_n=50, client=client)
    assert 50 <= len(r.compounds) <= 100 and len(r.baseline) == len(r.compounds)
    scores = [c.priority_score for c in r.compounds if c.priority_score is not None]
    assert scores == sorted(scores, reverse=True) and [c.rank for c in r.compounds] == list(range(1, len(r.compounds) + 1))
    best = [c.best_pchembl for c in sorted(r.compounds, key=lambda c: c.baseline_rank)]
    assert best == sorted(best, reverse=True) and best[0] >= 9  # the potency-only baseline is preserved
    assert r.structure is not None and r.structure.uniprot == "Q5S007"
    assert any(c.name for c in r.compounds)
    assert r.coverage["stage1"]["total_count"] > 5000 and r.coverage["partial"] is True
    assert r.coverage["stage3"]["molecules_assessed"] == 10
    assert all(c.selectivity and c.potency and c.clinical for c in r.compounds)
    assert r.rubric["objective"] == "balanced"


def test_run_screening_without_chembl_target_gives_structure_only(client):
    r = run_screening(approval(chembl_target_id=None), client=client)
    assert r.compounds == [] and r.structure is not None


# ---- staged retrieval and four-factor evidence, against an in-memory ChEMBL ----
from tests.fake_chembl import FakeChembl, act  # noqa: E402


def mol(mid, name=None, phase=None, qed=0.6, ro5=0, props=True):
    return {"molecule_chembl_id": mid, "pref_name": name, "max_phase": phase, "first_approval": None,
            "molecule_properties": {"full_mwt": "400", "alogp": "2", "hbd": 1, "hba": 3, "psa": "70",
                                    "num_ro5_violations": ro5, "qed_weighted": qed} if props else None}


def egfr_approval():
    return approval(chembl_target_id="CHEMBL203", uniprot=None, approval_id="appr-egfr")


def test_ordered_retrieval_keeps_the_strongest_molecule_and_labels_partial_coverage():
    # 12 molecules; the strongest (M11) sits last in insertion order so an unordered cut would drop it
    acts = [act(f"M{i}", 6 + i * 0.25) for i in range(12)]
    fake = FakeChembl(acts, {f"M{i}": mol(f"M{i}") for i in range(12)})
    r = run_screening(egfr_approval(), top_n=3, client=fake, max_rows=5, selectivity_n=0)
    stage1 = r.coverage["stage1"]
    assert stage1["total_count"] == 12 and stage1["retrieved"] == 5 and stage1["complete"] is False
    assert stage1["cutoff_pchembl"] == 7.75 and "descending" in stage1["selection_method"]
    assert r.coverage["partial"] is True
    assert r.compounds[0].chembl_id == "M11"
    assert all(rec["activity_id"] and rec["assay_chembl_id"] and rec["target_chembl_id"] for c in r.compounds for rec in c.potency["records"])


def test_candidate_pool_is_the_union_of_baseline_top_and_aggregate_top():
    acts = [act("MAX", 9.5, aid=1), act("MAX", 6.0, aid=2, assay="A2"), act("MAX", 6.1, aid=3, assay="A3"),
            act("MED", 8.0, aid=4), act("MED", 8.1, aid=5, assay="A5"), act("MED", 8.2, aid=6, assay="A6"),
            act("LOW", 6.5, aid=7)]
    fake = FakeChembl(acts, {m: mol(m) for m in ("MAX", "MED", "LOW")})
    r = run_screening(egfr_approval(), top_n=1, client=fake, selectivity_n=0)
    ids = {c.chembl_id for c in r.compounds}
    assert ids == {"MAX", "MED"}  # top-1 by max (MAX) and top-1 by median (MED); LOW is in neither
    assert r.baseline[0] == "MAX" and r.compounds[0].chembl_id == "MED"
    by = {c.chembl_id: c for c in r.compounds}
    assert by["MAX"].baseline_rank == 1 and by["MAX"].rank == 2 and by["MAX"].potency["conflicting"]
    assert by["MED"].potency["aggregate_pchembl"] == 8.1 and by["MED"].potency["max_pchembl"] == 8.2
    assert by["MAX"].best_pchembl == 9.5  # baseline field untouched


def test_stage_two_completes_on_target_records_beyond_the_cutoff():
    acts = [act("A", 9.0, aid=1), act("B", 8.9, aid=2), act("A", 5.5, aid=3, assay="A3"), act("A", None, rel=">", aid=4, assay="A4")]
    fake = FakeChembl(acts, {"A": mol("A"), "B": mol("B")})
    r = run_screening(egfr_approval(), top_n=2, client=fake, max_rows=2, selectivity_n=0)
    a = next(c for c in r.compounds if c.chembl_id == "A")
    assert a.potency["n_records"] == 3 and a.potency["n_censored"] == 1 and a.potency["aggregate_pchembl"] == 7.25
    assert r.coverage["stage2"]["molecules"] == 2 and r.coverage["stage2"]["records"] == 4


def test_phase_4_elsewhere_qed_and_offtarget_evidence_are_reported_separately():
    acts = [act("DRUG", 8.0, aid=1), act("DRUG", 8.2, aid=2, assay="A2"),
            act("DRUG", 7.9, target="CHEMBL1862", aid=3), act("DRUG", 5.0, target="CHEMBL1862", stype="Ki", aid=4),
            act("NOVEL", 8.5, aid=5), act("NOVEL", 8.4, aid=6, assay="A6"),
            act("BARE", 8.3, aid=7), act("BARE", 8.1, aid=8, assay="A8")]
    fake = FakeChembl(acts, {"DRUG": mol("DRUG", "GEFITINIB", "4.0", qed=0.5), "NOVEL": mol("NOVEL", qed=0.8),
                             "BARE": mol("BARE", qed=None, ro5=None, props=False)},
                      indications={"DRUG": [{"molecule_chembl_id": "DRUG", "efo_id": "EFO:0003060", "efo_term": "non-small cell lung carcinoma",
                                             "mesh_heading": "Carcinoma, Non-Small-Cell Lung", "max_phase_for_ind": "4.0"}]},
                      targets={"CHEMBL1862": {"target_chembl_id": "CHEMBL1862", "pref_name": "Tyrosine-protein kinase ABL", "organism": "Homo sapiens"}})
    r = run_screening(egfr_approval(), top_n=3, client=fake, selectivity_n=3)
    by = {c.chembl_id: c for c in r.compounds}
    drug = by["DRUG"]
    assert drug.clinical["indication_status"] == "other_indications_only" and drug.clinical["phase"] == 4.0
    assert drug.qed == 0.5 and drug.selectivity["evidence"] == "observed_window"
    assert drug.selectivity["targets_tested"] == 1 and drug.selectivity["comparable_records"] == 1
    assert drug.selectivity["window"] == round(8.1 - 7.9, 2) and drug.selectivity["off_targets"][0]["name"] == "Tyrosine-protein kinase ABL"
    novel = by["NOVEL"]
    assert novel.selectivity["evidence"] == "no_off_target_records" and novel.factors["selectivity"] is None
    assert "factor:selectivity" in novel.missing_data
    bare = by["BARE"]
    assert bare.qed is None and bare.ro5_violations is None and bare.factors["drug_likeness"] is None
    assert "factor:drug_likeness" in bare.missing_data and bare.priority_score is not None
    assert r.rubric["objective"] == "balanced" and "heuristic" in r.rubric["caveat"].lower()
    assert r.coverage["stage3"]["molecules_assessed"] == 3 and r.coverage["indications"]["molecules_checked"] == 1


def test_rubric_objective_and_weights_are_honoured():
    acts = [act("A", 8.0, aid=1), act("A", 8.0, aid=2, assay="A2"), act("B", 8.0, aid=3), act("B", 8.0, aid=4, assay="A4")]
    fake = FakeChembl(acts, {"A": mol("A", "OLD DRUG", "4.0", qed=0.4), "B": mol("B", qed=0.4)},
                      indications={"A": [{"molecule_chembl_id": "A", "efo_id": "MONDO:0005180", "efo_term": "Parkinson disease",
                                          "mesh_heading": "Parkinson Disease", "max_phase_for_ind": "4.0"}]})
    repurpose = run_screening(egfr_approval(), client=fake, selectivity_n=0, rubric={"objective": "repurposing"})
    assert repurpose.compounds[0].chembl_id == "A" and repurpose.compounds[0].clinical["indication_status"] == "matched"
    novel = run_screening(egfr_approval(), client=fake, selectivity_n=0, rubric={"objective": "novel_candidates"})
    assert novel.compounds[0].priority_score == novel.compounds[1].priority_score  # clinical carries no weight
    assert novel.rubric["weights"]["clinical"] == 0.0
