"""Optional LLM rationale: explains the ranking using only the evidence we fetched.

Uses the same Gemini configuration as the Target Challenger (devils_advocate):
GEMINI_API_KEY, AI_MODEL, AI_ENABLED, AI_THINKING_LEVEL, loaded from the repository-root .env.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

from pipeline.models import ScoutResult
from pipeline.settings import data_dir

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_CACHE_DIR = data_dir("cache") / "rationale"
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
            },
        }
    },
    "required": ["items"],
}


def gemini_settings() -> dict:
    """Same environment contract as devils_advocate.ai_config, without importing that package."""
    load_dotenv(REPO_ROOT / ".env", override=False)
    return {
        "enabled": os.getenv("AI_ENABLED", "false").lower() == "true",
        "model": os.getenv("AI_MODEL", "").strip(),
        "api_key": os.getenv("GEMINI_API_KEY", ""),
        "thinking_level": os.getenv("AI_THINKING_LEVEL", "medium").lower(),
        "timeout_seconds": int(os.getenv("AI_TIMEOUT_SECONDS", "120")),
        "max_output_tokens": int(os.getenv("AI_MAX_OUTPUT_TOKENS", "8192")),
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
    """Hash of exactly what the model would be shown, so cached text never cites stale numbers."""
    raw = json.dumps([result.disease.id, evidence_payload(result, top)], sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def _client():
    """Return a configured Gemini client, or None when AI is disabled or unconfigured."""
    s = gemini_settings()
    if not (s["enabled"] and s["model"] and s["api_key"]):
        return None
    from google import genai
    return genai.Client(api_key=s["api_key"],
                        http_options={"timeout": s["timeout_seconds"] * 1000, "retry_options": {"attempts": 1}})


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
            read_dirs: Iterable[Path] = (DEMO_RATIONALE_DIR,), offline: bool = False) -> ScoutResult | None:
    """Fill rationales from cache or Gemini. Returns None when no rationale is available.

    offline=True (or SCOUT_CACHE_ONLY=1) means cache only: no paid call is ever made.
    """
    key = rationale_key(result, top)
    cached = _read_cached(key, [cache_dir, *read_dirs])
    if cached is not None:
        return _apply(result, cached["items"])
    if offline or os.environ.get("SCOUT_CACHE_ONLY") == "1":
        return None
    client = _client()
    if client is None:
        return None
    s = gemini_settings()
    response = client.interactions.create(
        model=s["model"],
        system_instruction=SYSTEM_PROMPT,
        input=json.dumps(evidence_payload(result, top), ensure_ascii=False, separators=(",", ":")),
        store=False,
        automatic_continuation=False,
        timeout=s["timeout_seconds"],
        generation_config={"thinking_level": s["thinking_level"], "max_output_tokens": s["max_output_tokens"]},
        response_format=[{"type": "text", "mime_type": "application/json", "schema": RATIONALE_SCHEMA}],
    )
    if getattr(response, "status", "completed") != "completed":
        return None
    try:
        data = json.loads(response.output_text)
        items = data["items"]
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    (Path(cache_dir) / f"{key}.json").write_text(json.dumps({"items": items}))
    return _apply(result, items)
