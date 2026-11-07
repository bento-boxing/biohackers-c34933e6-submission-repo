from pipeline.clients.europepmc import literature_hits, pubmed_url


def test_lrrk2_parkinson_hits_over_1000_with_3_pmids(client):
    count, pmids = literature_hits(client, "LRRK2", "Parkinson disease")
    assert count > 1000
    assert len(pmids) == 3 and all(p.isdigit() for p in pmids)


def test_pubmed_url():
    assert pubmed_url("123") == "https://pubmed.ncbi.nlm.nih.gov/123/"
