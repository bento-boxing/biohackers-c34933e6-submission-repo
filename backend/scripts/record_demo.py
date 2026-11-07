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
    # stage-2 demo data for the first target that has a ChEMBL id (LRRK2 for Parkinson)
    chembl.find_target(client, None, "ZZQXV1")
    for t in targets:
        cid = chembl.find_target(client, t.uniprot, t.symbol)
        if cid:
            acts = chembl.potent_activities(client, cid, max_pages=5)
            chembl.potent_activities(client, cid, max_pages=1)
            best: dict[str, float] = {}
            for a in acts:
                v = a.get("pchembl_value")
                if v is not None:
                    best[a["molecule_chembl_id"]] = max(best.get(a["molecule_chembl_id"], 0), float(v))
            top = sorted(best, key=best.get, reverse=True)[:50]
            chembl.molecules(client, top)
            chembl.molecules(client, ["CHEMBL1721885"])
            if t.uniprot:
                alphafold.prediction(client, t.uniprot)
            print("stage2", t.symbol, cid, len(acts), len(top))
            break


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--disease", default="Parkinson disease")
    ap.add_argument("--n", type=int, default=25)
    ap.add_argument("--rationale", action="store_true",
                    help="also record the default-weights LLM rationale (needs ANTHROPIC_API_KEY)")
    a = ap.parse_args()
    record(a.disease, a.n)
    if a.rationale:
        from pipeline.scout.pipeline import run_scout
        from pipeline.scout.rationale import DEMO_RATIONALE_DIR, explain

        result = run_scout(a.disease, n=a.n, client=HttpClient(write_dir=DEMO_DIR, ttl_days=36500))
        out = explain(result, cache_dir=DEMO_RATIONALE_DIR, read_dirs=())
        print("rationale recorded" if out else "rationale NOT recorded (no key or refusal)")
