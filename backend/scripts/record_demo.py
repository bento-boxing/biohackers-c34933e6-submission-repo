"""Record every API response needed for the offline demo into data/demo_cache.

Run from backend/: python scripts/record_demo.py [--disease "Parkinson disease"] [--n 25]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
        print("safety", t.symbol)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--disease", default="Parkinson disease")
    ap.add_argument("--n", type=int, default=25)
    a = ap.parse_args()
    record(a.disease, a.n)
