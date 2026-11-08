"""Flask JSON API over the pipeline. See spec section 4.1a for the contract."""
from __future__ import annotations

import os
import uuid
from dataclasses import asdict
from pathlib import Path

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

from pipeline import audit
from pipeline.clients.opentargets import DiseaseNotFound, suggest_diseases
from pipeline.http import CacheMiss, HttpClient, UpstreamError, default_client
from pipeline.models import ScoutResult, Weights
from pipeline.scout.pipeline import rescore, run_scout
from pipeline.scout.rationale import explain
from pipeline.scout.restore import result_from_run_json
from pipeline.screening.pipeline import run_screening
from pipeline.clients.chembl import chembl_molecule_url
from pipeline.models import Compound, ScreeningResult

RUNS: dict[str, ScoutResult] = {}
# Diseases the recorded demo cache can serve end to end; offline suggestions never leave this list.
RECORDED_DISEASES = [{"id": "MONDO_0005180", "name": "Parkinson disease"}]
SCORE_KEYS = ("genetic", "association", "druggability", "literature", "total")
SCORE_TOLERANCE = 0.0005


def scout_run_json(run_id: str, result: ScoutResult, cache_only: bool) -> dict:
    targets = []
    for t in result.targets:
        e, s = t.evidence, t.scores
        targets.append({
            "target_id": e.target_id, "symbol": e.symbol, "name": e.name, "uniprot": e.uniprot,
            "chembl_target_id": e.chembl_target_id,
            "components": {"genetic": s.genetic, "association": s.association,
                           "druggability": s.druggability, "literature": s.literature},
            "potent_count": e.potent_count, "has_approved_drug": e.has_approved_drug,
            "literature_hits": e.literature_hits, "pmids": e.pmids,
            "safety_flags": [{"kind": f.kind, "detail": f.detail} for f in e.safety_flags],
            "tractability_sm_labels": [x["label"] for x in e.tractability
                                       if x.get("modality") == "SM" and x.get("value")],
            "open_targets_url": f"https://platform.opentargets.org/target/{e.target_id}",
            # raw evidence so a stateless client can post the run back (see scout/restore.py)
            "evidence": asdict(e),
        })
    return {"run_id": run_id, "disease": {"id": result.disease.id, "name": result.disease.name},
            "cache_only": cache_only, "default_weights": Weights().as_dict(), "targets": targets}


def compound_json(c: Compound) -> dict:
    return {"chembl_id": c.chembl_id, "name": c.name, "best_pchembl": c.best_pchembl, "assay_type": c.assay_type,
            "max_phase": c.max_phase, "is_approved": c.is_approved, "mw": c.mw, "alogp": c.alogp,
            "hbd": c.hbd, "hba": c.hba, "psa": c.psa, "ro5_violations": c.ro5_violations,
            "lipinski_pass": c.lipinski_pass, "chembl_url": chembl_molecule_url(c.chembl_id),
            # four-factor evidence, shown separately; None means not available, never zero
            "qed": c.qed, "first_approval": c.first_approval, "potency": c.potency, "clinical": c.clinical,
            "selectivity": c.selectivity, "factors": c.factors, "priority_score": c.priority_score,
            "rank": c.rank, "baseline_rank": c.baseline_rank, "rank_reason": c.rank_reason, "missing_data": c.missing_data}


def screening_json(r: ScreeningResult) -> dict:
    return {"approval": r.approval.__dict__,
            "structure": r.structure.__dict__ if r.structure else None,
            "compounds": [compound_json(c) for c in r.compounds],
            "coverage": r.coverage, "rubric": r.rubric, "baseline": r.baseline, "notes": r.notes}


def rubric_from(body: dict):
    """Validated rubric request ({objective, weights}) or None for the default; BadInput when malformed."""
    from pipeline.screening.rubric import Rubric
    raw = body.get("rubric")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise BadInput("rubric must be an object with optional 'objective' and 'weights'")
    try:
        return Rubric(objective=raw.get("objective") or "balanced", weights=raw.get("weights") or {})
    except (TypeError, ValueError) as e:
        raise BadInput(f"invalid rubric: {e}")


class BadInput(ValueError):
    pass


def _weights_from(d: dict | None) -> Weights:
    d = d or {}
    try:
        w = Weights(float(d.get("genetic", 0.4)), float(d.get("association", 0.3)),
                    float(d.get("druggability", 0.2)), float(d.get("literature", 0.1)))
    except (TypeError, ValueError):
        raise BadInput("weights must be numbers")
    if min(w.as_dict().values()) < 0:
        raise BadInput("weights must not be negative")
    return w


def create_app(client: HttpClient | None = None,
               approvals_path: Path = audit.APPROVALS_PATH,
               shortlists_path: Path = audit.SHORTLISTS_PATH) -> Flask:
    app = Flask(__name__)
    CORS(app, origins=["http://localhost:3000"])
    http = client or default_client()

    def error(msg: str, status: int):
        return jsonify({"error": msg}), status

    @app.errorhandler(CacheMiss)
    @app.errorhandler(UpstreamError)
    @app.errorhandler(requests.RequestException)
    def upstream(e):
        return error(f"upstream failure: {e}", 502)

    @app.errorhandler(BadInput)
    def bad_input(e):
        return error(str(e), 400)

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok", "message": "Target Scout backend is running"})

    @app.post("/api/scout")
    def scout():
        body = request.get_json(silent=True) or {}
        name = (body.get("disease") or "").strip()
        if not name:
            return error("disease is required", 400)
        try:
            n = max(5, min(50, int(body.get("n") or 25)))
        except (TypeError, ValueError):
            raise BadInput("n must be an integer between 5 and 50")
        try:
            result = run_scout(name, n=n, client=http)
        except DiseaseNotFound:
            return error(f"no disease found for '{name}'", 404)
        run_id = uuid.uuid4().hex
        RUNS[run_id] = result
        return jsonify(scout_run_json(run_id, result, http.cache_only))

    @app.get("/api/diseases")
    def diseases():
        q = (request.args.get("q") or "").strip()
        if not q:
            return error("q is required", 400)
        if http.cache_only:
            found = [d for d in RECORDED_DISEASES if q.casefold() in d["name"].casefold()]
        else:
            found = [{"id": d.id, "name": d.name} for d in suggest_diseases(http, q)]
        return jsonify({"query": q, "diseases": found})

    @app.get("/api/approvals")
    def list_approvals():
        return jsonify([a.__dict__ for a in audit.read_approvals(approvals_path)])

    @app.post("/api/approvals")
    def approve():
        body = request.get_json(silent=True) or {}
        run = RUNS.get(body.get("run_id", ""))
        if run is None:
            return error(f"no run {body.get('run_id')} (runs expire on server restart: re-run the scout)", 404)
        weights = _weights_from(body.get("weights"))
        result = rescore(run, weights)
        target = next((t for t in result.targets if t.evidence.symbol == body.get("symbol")), None)
        if target is None:
            return error(f"no target {body.get('symbol')} in run", 400)
        posted = body.get("scores") or {}
        s = target.scores
        server = {"genetic": s.genetic, "association": s.association, "druggability": s.druggability,
                  "literature": s.literature, "total": s.total}
        try:
            mismatch = any(k not in posted or abs(float(posted[k]) - server[k]) > SCORE_TOLERANCE
                           for k in SCORE_KEYS)
        except (TypeError, ValueError):
            raise BadInput("scores must be numbers")
        if mismatch:
            return error("scores do not match server recomputation", 400)
        reason = (body.get("reason") or "").strip()
        if not reason:
            return error("reason is required", 400)
        approval = audit.make_approval(result, target, reason)
        audit.append_jsonl(approvals_path, approval.__dict__)
        return jsonify(approval.__dict__)

    def _run_from_body(body: dict) -> ScoutResult | None:
        run = RUNS.get(body.get("run_id", ""))
        if run is None and isinstance(body.get("run"), dict):
            try:
                run = result_from_run_json(body["run"])
            except ValueError as e:
                raise BadInput(str(e))
        return run

    @app.post("/api/rationale")
    def rationale():
        body = request.get_json(silent=True) or {}
        run = _run_from_body(body)
        if run is None:
            return error(f"no run {body.get('run_id')} (runs expire on server restart: re-run the scout)", 404)
        weights = _weights_from(body.get("weights"))
        try:
            # cache-only (offline / recorded) mode must never make a paid model call
            result = explain(rescore(run, weights), offline=http.cache_only)
        except Exception as e:  # LLM failures must never break the page
            app.logger.warning("rationale failed: %s", e)
            return jsonify({"available": False, "reason": f"LLM call failed: {e}"})
        if result is None:
            return jsonify({"available": False, "reason": "no API key, cache-only mode, or the model declined"})
        items = [{"symbol": t.evidence.symbol, "rationale": t.rationale, "evidence_strength": t.evidence_strength}
                 for t in result.targets if t.rationale]
        return jsonify({"run_id": body["run_id"], "weights": weights.normalised().as_dict(), "rationales": items})

    def _find_approval(body: dict):
        """The approval named by its unique id. Timestamps are never used: two approvals can share one."""
        approval_id = body.get("approval_id")
        if not isinstance(approval_id, str) or not approval_id:
            raise BadInput("approval_id is required (approval timestamps are not identifiers)")
        return next((a for a in audit.read_approvals(approvals_path) if a.approval_id == approval_id), None)

    @app.post("/api/screen")
    def screen():
        body = request.get_json(silent=True) or {}
        approval = _find_approval(body)
        if approval is None:
            return error(f"no approval with id {body.get('approval_id')}", 404)
        return jsonify(screening_json(run_screening(approval, client=http, rubric=rubric_from(body))))

    @app.post("/api/shortlists")
    def shortlist():
        body = request.get_json(silent=True) or {}
        approval = _find_approval(body)
        if approval is None:
            return error(f"no approval with id {body.get('approval_id')}", 404)
        ids = [str(x) for x in body.get("chembl_ids") or []]
        if not ids:
            return error("chembl_ids is required", 400)
        audit.append_shortlist(approval, ids, (body.get("reason") or "").strip(), path=shortlists_path)
        return jsonify({"ok": True})

    app.config["APPROVALS_PATH"] = approvals_path
    app.config["SHORTLISTS_PATH"] = shortlists_path
    app.config["HTTP_CLIENT"] = http
    return app
