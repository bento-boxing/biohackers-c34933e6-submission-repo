"""AlphaFold DB predicted structures."""
from __future__ import annotations

import requests

from pipeline.http import HttpClient
from pipeline.models import Structure

AF_URL = "https://alphafold.ebi.ac.uk/api/prediction/{uniprot}"


def prediction(client: HttpClient, uniprot: str) -> Structure | None:
    try:
        data = client.get_json(AF_URL.format(uniprot=uniprot))
    except requests.HTTPError as e:
        if "404" in str(e):
            return None
        raise
    if not data:
        return None
    d = data[0]
    return Structure(
        uniprot=uniprot, model_id=d["entryId"], pdb_url=d["pdbUrl"], cif_url=d["cifUrl"],
        mean_plddt=float(d["globalMetricValue"]),
        fraction_confident=float(d.get("fractionPlddtConfident", 0) + d.get("fractionPlddtVeryHigh", 0)),
    )


def alphafold_entry_url(uniprot: str) -> str:
    return f"https://alphafold.ebi.ac.uk/entry/{uniprot}"
