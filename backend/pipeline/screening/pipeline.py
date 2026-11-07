"""Stage 2: approved target -> ranked known compounds + predicted structure."""
from __future__ import annotations

from pipeline.clients import alphafold, chembl
from pipeline.http import HttpClient, default_client
from pipeline.models import Approval, ScreeningResult
from pipeline.screening.ranking import best_per_molecule, build_compounds, rank_compounds


def run_screening(approval: Approval, top_n: int = 50, client: HttpClient | None = None) -> ScreeningResult:
    client = client or default_client()
    compounds = []
    if approval.chembl_target_id:
        acts = chembl.potent_activities(client, approval.chembl_target_id, max_pages=5)
        best = best_per_molecule(acts)
        top = sorted(best, key=lambda m: best[m][0], reverse=True)[:top_n]
        mols = chembl.molecules(client, top)
        compounds = rank_compounds(build_compounds({m: best[m] for m in top}, mols))
    structure = alphafold.prediction(client, approval.uniprot) if approval.uniprot else None
    return ScreeningResult(approval=approval, structure=structure, compounds=compounds)
