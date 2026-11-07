from pipeline.screening.ranking import best_per_molecule, build_compounds, rank_compounds


def test_best_per_molecule_takes_max():
    acts = [{"molecule_chembl_id": "A", "pchembl_value": "6.5", "assay_type": "B"},
            {"molecule_chembl_id": "A", "pchembl_value": "8.1", "assay_type": "F"},
            {"molecule_chembl_id": "B", "pchembl_value": None, "assay_type": "B"},
            {"molecule_chembl_id": "B", "pchembl_value": "7.0", "assay_type": "B"}]
    assert best_per_molecule(acts) == {"A": (8.1, "F"), "B": (7.0, "B")}


def test_build_compounds_handles_null_phase_and_props():
    best = {"A": (8.1, "F"), "B": (7.0, None)}
    mols = {"A": {"pref_name": "DRUG-A", "max_phase": "4.0",
                  "molecule_properties": {"full_mwt": "442.49", "alogp": "1.69", "hbd": 4, "hba": 5,
                                          "psa": "106.69", "num_ro5_violations": 0}},
            "B": {"pref_name": None, "max_phase": None, "molecule_properties": None}}
    a, b = sorted(build_compounds(best, mols), key=lambda c: c.chembl_id)
    assert (a.name, a.max_phase, a.mw, a.hbd, a.ro5_violations, a.is_approved) == ("DRUG-A", "4.0", 442.49, 4, 0, True)
    assert (b.name, b.max_phase, b.mw, b.ro5_violations, b.lipinski_pass, b.best_pchembl) == (None, None, None, None, None, 7.0)


def test_rank_ties_broken_by_ro5_none_last():
    best = {"X": (7.0, "B"), "Y": (7.0, "B"), "Z": (7.0, "B"), "W": (9.0, "B")}
    mols = {"X": {"molecule_properties": {"num_ro5_violations": 2}},
            "Y": {"molecule_properties": None},
            "Z": {"molecule_properties": {"num_ro5_violations": 0}},
            "W": {"molecule_properties": {"num_ro5_violations": 3}}}
    ranked = rank_compounds(build_compounds(best, mols))
    assert [c.chembl_id for c in ranked] == ["W", "Z", "X", "Y"]
