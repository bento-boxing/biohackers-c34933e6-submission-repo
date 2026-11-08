"""Human checkpoints: approvals and shortlists as append-only JSONL."""
from __future__ import annotations

import getpass
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from pipeline.models import Approval, ScoredTarget, ScoutResult
from pipeline.settings import data_dir

RUNS_DIR = data_dir("runs")  # /tmp on Vercel: ephemeral
APPROVALS_PATH = RUNS_DIR / "approvals.jsonl"
SHORTLISTS_PATH = RUNS_DIR / "shortlists.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _user() -> str:
    return os.environ.get("SCOUT_USER") or getpass.getuser()


def make_approval(result: ScoutResult, target: ScoredTarget, reason: str) -> Approval:
    e, s = target.evidence, target.scores
    return Approval(
        ts=_now(), disease_id=result.disease.id, disease_name=result.disease.name,
        target_id=e.target_id, symbol=e.symbol, uniprot=e.uniprot, chembl_target_id=e.chembl_target_id,
        weights=result.weights.normalised().as_dict(),
        scores={"genetic": s.genetic, "association": s.association, "druggability": s.druggability,
                "literature": s.literature, "total": s.total},
        safety_flags=[f.detail for f in e.safety_flags], reason=reason, approved_by=_user(),
    )


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def read_approvals(path: Path = APPROVALS_PATH) -> list[Approval]:
    if not path.exists():
        return []
    lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
    return [Approval.from_json(ln) for ln in reversed(lines)]


def append_shortlist(approval: Approval, chembl_ids: list[str], reason: str,
                     path: Path = SHORTLISTS_PATH) -> None:
    append_jsonl(path, {"ts": _now(), "approval_ts": approval.ts, "symbol": approval.symbol,
                        "chembl_ids": list(chembl_ids), "reason": reason, "shortlisted_by": _user()})
