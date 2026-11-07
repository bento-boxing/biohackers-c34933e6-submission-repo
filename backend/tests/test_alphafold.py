from pipeline.clients.alphafold import prediction


def test_prediction_q5s007_has_plddt_and_urls(client):
    s = prediction(client, "Q5S007")
    assert s is not None
    assert s.uniprot == "Q5S007" and s.model_id.startswith("AF-Q5S007")
    assert s.pdb_url.endswith(".pdb") and s.cif_url.endswith(".cif")
    assert 0 < s.mean_plddt <= 100 and 0 < s.fraction_confident <= 1
