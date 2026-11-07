"""Optional LLM rationale: explains the ranking using only the evidence we fetched."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from pipeline.models import ScoutResult

MODEL = "claude-opus-5-5"
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_CACHE_DIR = BACKEND_DIR / "cache" / "rationale"
DEMO_RATIONALE_DIR = BACKEND_DIR / "data" / "demo_cache" / "rationale"

SYSTEM_PROMPT = (
    "You write 2-3 sentence target rationales for a drug discovery scientist. "
    "Use only the numbers, labels and IDs in the provided JSON. Do not add facts that are not in it. "
    "If genetic evidence is below 0.3 or potent compounds are 0, say the evidence is weak on that axis. "
    "Return one entry per input symbol."
)

RATIONALE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "rationale": {"type": "string"},
                    "evidence_strength": {"type": "string", "enum": ["strong", "moderate", "weak"]},
                },
                "required": ["symbol", "rationale", "evidence_strength"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def evidence_payload(result: ScoutResult, top: int = 10) -> list[dict]:
    weights = result.weights.normalised().as_dict()
    rows = []
    for rank, t in enumerate(result.targets[:top], 1):
        e, s = t.evidence, t.scores
        rows.append({
            "symbol": e.symbol, "rank": rank,
            "components": {"genetic": round(s.genetic, 3), "association": round(s.association, 3),
                           "druggability": round(s.druggability, 3), "literature": round(s.literature, 3),
                           "total": round(s.total, 3)},
            "weights": weights,
            "datatype_scores": {k: round(v, 3) for k, v in e.datatype_scores.items()},
            "potent_count": e.potent_count, "has_approved_drug": e.has_approved_drug,
            "literature_hits": e.literature_hits, "pmids": e.pmids,
            "tractability_sm_labels": [x["label"] for x in e.tractability
                                       if x.get("modality") == "SM" and x.get("value")],
            "safety_flags": [f.detail for f in e.safety_flags],
        })
    return rows


def rationale_key(result: ScoutResult, top: int = 10) -> str:
    w = result.weights.normalised().as_dict()
    symbols = [t.evidence.symbol for t in result.targets[:top]]
    raw = json.dumps([result.disease.id, w, symbols], sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def _client():
    """Return an Anthropic client, or None when no credentials are configured."""
    try:
        import anthropic
        client = anthropic.Anthropic()
        if not getattr(client, "api_key", None) and not getattr(client, "auth_token", None):
            return None
        return client
    except Exception:
        return None


def _read_cached(key: str, dirs: Iterable[Path]) -> dict | None:
    for d in dirs:
        f = Path(d) / f"{key}.json"
        if f.exists():
            return json.loads(f.read_text())
    return None


def _apply(result: ScoutResult, items: list[dict]) -> ScoutResult:
    by_symbol = {i["symbol"]: i for i in items}
    targets = []
    for t in result.targets:
        i = by_symbol.get(t.evidence.symbol)
        targets.append(replace(t, rationale=i["rationale"], evidence_strength=i["evidence_strength"]) if i else t)
    return replace(result, targets=targets)


def explain(result: ScoutResult, top: int = 10, cache_dir: Path = DEFAULT_CACHE_DIR,
            read_dirs: Iterable[Path] = (DEMO_RATIONALE_DIR,)) -> ScoutResult | None:
    key = rationale_key(result, top)
    cached = _read_cached(key, [cache_dir, *read_dirs])
    if cached is not None:
        return _apply(result, cached["items"])
    client = _client()
    if client is None:
        return None
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(evidence_payload(result, top))}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": RATIONALE_SCHEMA}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        return None
    text = next((b.text for b in response.content if getattr(b, "type", "") == "text"), None)
    if not text:
        return None
    data = json.loads(text)
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    (Path(cache_dir) / f"{key}.json").write_text(json.dumps(data))
    return _apply(result, data["items"])
