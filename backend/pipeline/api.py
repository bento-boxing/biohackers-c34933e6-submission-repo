"""Flask JSON API over the pipeline. See spec section 4.1a for the contract."""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

from pipeline import audit
from pipeline.clients.opentargets import DiseaseNotFound
from pipeline.http import CacheMiss, HttpClient, default_client
from pipeline.models import ScoutResult, Weights
from pipeline.scout.pipeline import rescore, run_scout
from pipeline.scout.rationale import explain

RUNS: dict[str, ScoutResult] = {}
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
        })
    return {"run_id": run_id, "disease": {"id": result.disease.id, "name": result.disease.name},
            "cache_only": cache_only, "default_weights": Weights().as_dict(), "targets": targets}


def _weights_from(d: dict | None) -> Weights:
    d = d or {}
    return Weights(float(d.get("genetic", 0.4)), float(d.get("association", 0.3)),
                   float(d.get("druggability", 0.2)), float(d.get("literature", 0.1)))


def create_app(client: HttpClient | None = None,
               approvals_path: Path = audit.APPROVALS_PATH,
               shortlists_path: Path = audit.SHORTLISTS_PATH) -> Flask:
    app = Flask(__name__)
    CORS(app, origins=["http://localhost:3000"])
    http = client or default_client()

    def error(msg: str, status: int):
        return jsonify({"error": msg}), status

    @app.errorhandler(CacheMiss)
    @app.errorhandler(requests.RequestException)
    def upstream(e):
        return error(f"upstream failure: {e}", 502)

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok", "message": "Target Scout backend is running"})

    @app.post("/api/scout")
    def scout():
        body = request.get_json(silent=True) or {}
        name = (body.get("disease") or "").strip()
        if not name:
            return error("disease is required", 400)
        n = max(5, min(50, int(body.get("n") or 25)))
        try:
            result = run_scout(name, n=n, client=http)
        except DiseaseNotFound:
            return error(f"no disease found for '{name}'", 404)
        run_id = uuid.uuid4().hex
        RUNS[run_id] = result
        return jsonify(scout_run_json(run_id, result, http.cache_only))

    @app.get("/api/approvals")
    def list_approvals():
        return jsonify([a.__dict__ for a in audit.read_approvals(approvals_path)])

    @app.post("/api/approvals")
    def approve():
        body = request.get_json(silent=True) or {}
        run = RUNS.get(body.get("run_id", ""))
        if run is None:
            return error(f"no run {body.get('run_id')}", 404)
        weights = _weights_from(body.get("weights"))
        result = rescore(run, weights)
        target = next((t for t in result.targets if t.evidence.symbol == body.get("symbol")), None)
        if target is None:
            return error(f"no target {body.get('symbol')} in run", 400)
        posted = body.get("scores") or {}
        s = target.scores
        server = {"genetic": s.genetic, "association": s.association, "druggability": s.druggability,
                  "literature": s.literature, "total": s.total}
        for k in SCORE_KEYS:
            if k not in posted or abs(float(posted[k]) - server[k]) > SCORE_TOLERANCE:
                return error("scores do not match server recomputation", 400)
        reason = (body.get("reason") or "").strip()
        if not reason:
            return error("reason is required", 400)
        approval = audit.make_approval(result, target, reason)
        audit.append_jsonl(approvals_path, approval.__dict__)
        return jsonify(approval.__dict__)

    @app.post("/api/rationale")
    def rationale():
        body = request.get_json(silent=True) or {}
        run = RUNS.get(body.get("run_id", ""))
        if run is None:
            return error(f"no run {body.get('run_id')}", 404)
        weights = _weights_from(body.get("weights"))
        result = explain(rescore(run, weights))
        if result is None:
            return jsonify({"available": False, "reason": "no API key or the model declined"})
        items = [{"symbol": t.evidence.symbol, "rationale": t.rationale, "evidence_strength": t.evidence_strength}
                 for t in result.targets if t.rationale]
        return jsonify({"run_id": body["run_id"], "weights": weights.normalised().as_dict(), "rationales": items})

    app.config["APPROVALS_PATH"] = approvals_path
    app.config["SHORTLISTS_PATH"] = shortlists_path
    app.config["HTTP_CLIENT"] = http
    return app
