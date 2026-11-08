"""Record every API response needed for the offline demo into data/demo_cache.

Run from backend/: python scripts/record_demo.py [--disease "Parkinson disease"] [--n 25]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.clients import alphafold, chembl  # noqa: E402
from pipeline.clients import europepmc as epmc  # noqa: E402
from pipeline.clients import opentargets as ot  # noqa: E402
from pipeline.http import HttpClient  # noqa: E402

DEMO_DIR = Path(__file__).resolve().parent.parent / "data" / "demo_cache"


def record(disease_name: str, n: int) -> None:
    client = HttpClient(write_dir=DEMO_DIR, ttl_days=36500)
    disease = ot.resolve_disease(client, disease_name)
    print("disease", disease)
    try:
        ot.resolve_disease(client, "zzqxv-not-a-disease")
    except ot.DiseaseNotFound:
        print("recorded not-found search")
    targets = ot.associated_targets(client, disease.id, n)
    print("targets", len(targets))
    for t in targets:
        ot.target_safety(client, t.target_id)
        count, _ = epmc.literature_hits(client, t.symbol, disease.name)
        cid = chembl.find_target(client, t.uniprot, t.symbol)
        potent = chembl.potent_count(client, cid) if cid else 0
        print("safety+lit+chembl", t.symbol, count, cid, potent)
    record_screening(client, disease, targets)


def record_screening(client: HttpClient, disease, targets) -> None:
    """Stage-2 demo data for the first target that has a ChEMBL id (LRRK2 for Parkinson): the staged
    screening pipeline is run against the recording client so every query it makes is captured."""
    from pipeline.models import Approval, Weights
    from pipeline.screening.pipeline import run_screening

    chembl.find_target(client, None, "ZZQXV1")
    for t in targets:
        cid = chembl.find_target(client, t.uniprot, t.symbol)
        if cid:
            approval = Approval(approval_id="demo-recording", ts="2026-11-07T00:00:00Z", disease_id=disease.id,
                                disease_name=disease.name, target_id=t.target_id, symbol=t.symbol, uniprot=t.uniprot,
                                chembl_target_id=cid, weights=Weights().as_dict(), scores={}, safety_flags=[],
                                reason="demo recording", approved_by="recorder")
            result = run_screening(approval, top_n=50, client=client)
            chembl.potent_activities(client, cid, max_pages=1)
            chembl.molecules(client, ["CHEMBL1721885"])
            print("stage2", t.symbol, cid, len(result.compounds), result.coverage)
            break


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--disease", default="Parkinson disease")
    ap.add_argument("--n", type=int, default=25)
    ap.add_argument("--screening-only", action="store_true",
                    help="only re-record the compound-screening responses (scout responses already recorded)")
    ap.add_argument("--rationale", action="store_true",
                    help="also record the default-weights LLM rationale (needs GEMINI_API_KEY, AI_MODEL and AI_ENABLED=true in the root .env)")
    a = ap.parse_args()
    if a.screening_only:
        client = HttpClient(write_dir=DEMO_DIR, ttl_days=36500)
        disease = ot.resolve_disease(client, a.disease)
        record_screening(client, disease, ot.associated_targets(client, disease.id, a.n))
        raise SystemExit(0)
    record(a.disease, a.n)
    if a.rationale:
        from pipeline.scout.pipeline import run_scout
        from pipeline.scout.rationale import DEMO_RATIONALE_DIR, explain

        result = run_scout(a.disease, n=a.n, client=HttpClient(write_dir=DEMO_DIR, ttl_days=36500))
        out = explain(result, cache_dir=DEMO_RATIONALE_DIR, read_dirs=())
        print("rationale recorded" if out else "rationale NOT recorded (no key or refusal)")
