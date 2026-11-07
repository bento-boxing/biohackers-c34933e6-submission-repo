"""Europe PMC literature counts."""
from __future__ import annotations

from pipeline.http import HttpClient

EPMC_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def literature_hits(client: HttpClient, symbol: str, disease_name: str, n_pmids: int = 3) -> tuple[int, list[str]]:
    params = {
        "query": f'"{symbol}" AND "{disease_name}"',
        "format": "json",
        "resultType": "lite",
        "pageSize": max(10, n_pmids),  # some hits are preprints without a PMID
    }
    data = client.get_json(EPMC_URL, params)
    results = (data.get("resultList") or {}).get("result") or []
    pmids = [r["pmid"] for r in results if r.get("pmid")][:n_pmids]
    return int(data.get("hitCount", 0)), pmids


def pubmed_url(pmid: str) -> str:
    return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
