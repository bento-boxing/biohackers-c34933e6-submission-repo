"""Terminal entry points. Run from backend/: python -m pipeline.cli scout "Parkinson disease" """
from __future__ import annotations

import argparse
import os
import sys

from pipeline.models import ScoutResult


def print_scout(result: ScoutResult) -> None:
    print(f"Disease: {result.disease.name} ({result.disease.id})  weights={ {k: round(v, 3) for k, v in result.weights.normalised().as_dict().items()} }")
    hdr = f"{'#':>2} {'symbol':<10}{'total':>6}{'gen':>6}{'assoc':>6}{'drug':>6}{'lit':>6}{'potent':>8}{'papers':>8}  flags"
    print(hdr)
    for i, t in enumerate(result.targets, 1):
        e, s = t.evidence, t.scores
        flags = "; ".join(f.detail for f in e.safety_flags)
        print(f"{i:>2} {e.symbol:<10}{s.total:>6.3f}{s.genetic:>6.2f}{s.association:>6.2f}"
              f"{s.druggability:>6.2f}{s.literature:>6.2f}{e.potent_count:>8}{e.literature_hits:>8}  {flags}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pipeline.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scout")
    s.add_argument("disease")
    s.add_argument("--n", type=int, default=25)
    s.add_argument("--cache-only", action="store_true")
    args = ap.parse_args(argv)
    if args.cache_only:
        os.environ["SCOUT_CACHE_ONLY"] = "1"
    if args.cmd == "scout":
        from pipeline.scout.pipeline import run_scout
        print_scout(run_scout(args.disease, n=args.n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
