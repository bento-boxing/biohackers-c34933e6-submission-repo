"""Stage 1: disease name -> ranked, evidence-backed targets."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from pipeline.clients import chembl, europepmc, opentargets
from pipeline.http import HttpClient, default_client
from pipeline.models import Disease, ScoutResult, TargetEvidence, Weights
from pipeline.scout.scoring import score_all


def _enrich(client: HttpClient, disease: Disease, ev: TargetEvidence) -> TargetEvidence:
    hits, pmids = europepmc.literature_hits(client, ev.symbol, disease.name)
    cid = chembl.find_target(client, ev.uniprot, ev.symbol)
    potent = chembl.potent_count(client, cid) if cid else 0
    flags = opentargets.target_safety(client, ev.target_id)
    return replace(ev, literature_hits=hits, pmids=pmids, chembl_target_id=cid,
                   potent_count=potent, safety_flags=flags)


def gather_evidence(client: HttpClient, disease: Disease, n: int, workers: int = 8) -> list[TargetEvidence]:
    base = opentargets.associated_targets(client, disease.id, n)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda ev: _enrich(client, disease, ev), base))


def run_scout(disease_name: str, n: int = 25, weights: Weights = Weights(),
              client: HttpClient | None = None) -> ScoutResult:
    client = client or default_client()
    disease = opentargets.resolve_disease(client, disease_name)
    evidence = gather_evidence(client, disease, n)
    return ScoutResult(disease=disease, weights=weights, targets=score_all(evidence, weights))


def rescore(result: ScoutResult, weights: Weights) -> ScoutResult:
    evidence = [t.evidence for t in result.targets]
    return ScoutResult(disease=result.disease, weights=weights, targets=score_all(evidence, weights))
