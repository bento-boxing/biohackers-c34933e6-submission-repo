"""Local Flask integration. Reuses Scout endpoints and both scientific pipelines.

Run: python -m devils_advocate.server --port 5050
SQLite persists jobs/runs/decisions. Use one local server and a protected local
runtime directory; authentication/remote deployment are deliberately not implied.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import threading
import uuid
from typing import Literal

from flask import Flask, jsonify, request
from flask_cors import CORS
from pydantic import BaseModel, ConfigDict, Field, ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from pipeline.api import RUNS, create_app as scout_app
from pipeline.http import HttpClient
from pipeline.models import (ComponentScores, Disease, SafetyFlag, ScoredTarget,
                             ScoutResult, TargetEvidence, Weights)
from pipeline.scout.pipeline import rescore
from .ai_config import load_ai_settings
from .job_store import JobStore
from .job_worker import JobWorker
from .models import TargetInput
from .target_scout_adapter import flatten_scout_selection

ORIGINS = ['http://127.0.0.1:3000', 'http://localhost:3000']

class ChallengeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    run_id: str | None = Field(default=None, max_length=100)
    symbol: str | None = Field(default=None, max_length=80)
    target_input: TargetInput | None = None
    use_ai: bool = False
    paid_authorized: bool = False
    weights: dict[str, float] = Field(default_factory=lambda: Weights().as_dict())

class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    decision_id: str = Field(pattern=r'^[a-zA-Z0-9-]{8,100}$')
    job_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    action: Literal['investigate', 'revise', 'stop', 'approve_screening']
    rationale: str = Field(min_length=5, max_length=4000)
    confirmed: bool = False

def restore_run(data):
    targets = []
    for item in data['targets']:
        ev = dict(item['evidence'])
        ev['safety_flags'] = [SafetyFlag(**flag) for flag in ev['safety_flags']]
        targets.append(ScoredTarget(TargetEvidence(**ev), ComponentScores(**item['scores']),
                                    item.get('rationale'), item.get('evidence_strength')))
    return ScoutResult(Disease(**data['disease']), Weights(**data['weights']), targets)

def create_app(runtime: Path | None = None, *, start_worker: bool = True):
    runtime = runtime or Path(__file__).parent / 'runtime'
    store = JobStore(runtime / 'workbench.sqlite3')
    apps = {}
    for mode in ['live', 'offline']:
        http = HttpClient(write_dir=runtime / 'api_cache' if mode == 'live' else None,
            read_dirs=[runtime / 'api_cache'] if mode == 'live' else [ROOT / 'backend/data/demo_cache'],
            cache_only=mode == 'offline')
        apps[mode] = scout_app(client=http, approvals_path=runtime / mode / 'approvals.jsonl',
                               shortlists_path=runtime / mode / 'shortlists.jsonl')
    app = Flask(__name__)
    CORS(app, origins=ORIGINS, allow_headers=['Content-Type', 'X-Research-Mode', 'Idempotency-Key'])
    app.config['MAX_CONTENT_LENGTH'] = 100_000
    app.config['STORE'] = store
    app.config['SCOUT_APPS'] = apps
    worker = JobWorker(store)
    app.config['WORKER'] = worker
    decision_lock = threading.Lock()

    def mode():
        return request.headers.get('X-Research-Mode', 'offline')

    def child_dispatch(path=None, body=None):
        child = apps[mode()]
        if path:
            with child.test_client() as client:
                return client.post(path, json=body)
        with child.test_client() as client:
            return client.open(request.path, method=request.method, query_string=request.query_string,
                               data=request.get_data(cache=True), content_type=request.content_type)

    @app.before_request
    def validate_origin():
        if request.headers.get('Origin') and request.headers['Origin'] not in ORIGINS:
            return jsonify(error='Origin is not allowed.'), 403
        if mode() not in ['live', 'offline']:
            return jsonify(error='Choose live or offline research mode.'), 400

    @app.errorhandler(ValidationError)
    def invalid_input(_):
        return jsonify(error='Invalid request fields. Check identifiers, weights and required confirmation.'), 400

    @app.errorhandler(Exception)
    def unexpected(exc):
        from werkzeug.exceptions import HTTPException
        status = exc.code if isinstance(exc, HTTPException) else 500
        return jsonify(error='Request could not complete. Check the inputs or backend availability.'), status

    @app.get('/api/workbench/config')
    def config():
        settings = load_ai_settings()
        return jsonify(ai={k: v for k,v in settings.model_dump(mode='json').items()
                           if k in ['enabled', 'provider', 'model', 'thinking_level', 'max_calls', 'timeout_seconds']},
                       demo_targets=['LRRK2', 'BACE1'], server='Flask + SQLite', modes=['live','offline'])

    @app.route('/api/<path:legacy>', methods=['GET', 'POST'])
    def legacy_api(legacy):
        if legacy not in ['health', 'scout', 'approvals', 'screen', 'shortlists']:
            return jsonify(error='Unknown endpoint.'), 404
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            return jsonify(error='JSON object required.'), 400
        if legacy == 'approvals' and request.method == 'POST':
            return jsonify(error='Use the Researcher Decision endpoint after reviewing an investigation.'), 403
        if legacy == 'scout' and (not isinstance(body.get('disease'), str) or not body['disease'].strip() or len(body['disease']) > 200):
            return jsonify(error='A disease name of 1–200 characters is required.'), 400
        if legacy in ['screen', 'shortlists']:
            approvals = apps[mode()].config['APPROVALS_PATH']
            from pipeline.audit import read_approvals
            if not any(a.ts == body.get('approval_ts') for a in read_approvals(approvals)):
                return jsonify(error='An explicit researcher approval is required before screening.'), 403
        response = child_dispatch()
        if response.status_code >= 400:
            return jsonify(error='Scout source unavailable or request invalid. No alternate mode was substituted.'), response.status_code
        if legacy == 'scout':
            result = response.get_json()
            run_id = result['run_id']
            store.save_run(run_id, mode(), {'raw': asdict(RUNS[run_id]), 'response': result})
        return response

    @app.get('/api/workbench/runs/<identifier>')
    def get_run(identifier):
        saved = store.get_run(identifier)
        if not saved or saved['mode'] != mode():
            return jsonify(error='Scout run not found for this mode.'), 404
        return jsonify(saved['data']['response'])

    @app.post('/api/investigations')
    def create_investigation():
        body = ChallengeRequest.model_validate(request.get_json(silent=True))
        idem = request.headers.get('Idempotency-Key', '')
        import re
        if not re.fullmatch(r'[a-zA-Z0-9-]{8,100}', idem):
            return jsonify(error='A stable Idempotency-Key is required.'), 400
        if set(body.weights) - set(Weights().as_dict()):
            return jsonify(error='Unknown ranking weight.'), 400
        weights = Weights(**body.weights)
        import math
        if any(not math.isfinite(v) or v < 0 for v in weights.as_dict().values()):
            return jsonify(error='Weights must be finite, nonnegative numbers.'), 400
        if body.run_id:
            saved = store.get_run(body.run_id)
            if not saved or saved['mode'] != mode() or body.target_input is not None:
                return jsonify(error='Scout run unavailable or inconsistent with this request.'), 400
            try:
                selection = flatten_scout_selection(saved['data']['response'], body.symbol)
            except ValueError:
                return jsonify(error='Selected target is not part of this Scout run.'), 400
            ranked = rescore(restore_run(saved['data']['raw']), weights)
            selected = next(t for t in ranked.targets if t.evidence.symbol == body.symbol)
            selection['weighted_score'] = selected.scores.total
        else:
            if body.target_input is None:
                return jsonify(error='Choose a Scout target or supply a validated manual target.'), 400
            selection = {'target_input': body.target_input.model_dump(mode='json'), 'run_id': None,
                         'cache_only': mode() == 'offline', 'origin': 'manual'}
        settings = load_ai_settings()
        if body.use_ai and mode() == 'live' and (not body.paid_authorized or not settings.enabled):
            return jsonify(error='Paid AI requires explicit authorization and enabled backend configuration.'), 400
        payload = {'selection': selection, 'mode': mode(), 'use_ai': body.use_ai and mode() == 'live',
                   'weights': weights.normalised().as_dict(), 'ai_policy': settings.model_dump(mode='json')}
        fingerprint = hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
        key_data = [mode(), selection['target_input'], body.use_ai and mode() == 'live']
        selection_key = hashlib.sha256(json.dumps(key_data,sort_keys=True).encode()).hexdigest()
        try:
            job, created = store.create(idem, fingerprint, selection_key, payload)
        except ValueError:
            return jsonify(error='Idempotency key was already used for another selection.'), 409
        return jsonify(job_id=job['id'], state=job['state'], created=created), 202

    @app.get('/api/investigations/<identifier>')
    def get_investigation(identifier):
        job = store.get(identifier)
        if not job or job['payload']['mode'] != mode():
            return jsonify(error='Investigation not found for this mode.'), 404
        return jsonify(job_id=identifier, state=job['state'], progress=job['progress'], result=job['result'],
                       error=job['error'], mode=mode(), selection=job['payload']['selection'],
                       weights=job['payload']['weights'],
                       decisions=store.decisions(identifier), updated=job['updated'])

    @app.get('/api/investigations')
    def recent_investigations():
        with store.connect() as db:
            rows = db.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 100').fetchall()
        jobs = [store.decode(row) for row in rows]
        return jsonify([{'job_id':job['id'], 'state':job['state'],
                         'target':job['payload']['selection']['target_input'], 'updated':job['updated']}
                        for job in jobs if job['payload']['mode']==mode()][:25])

    @app.post('/api/investigations/<identifier>/cancel')
    def cancel(identifier):
        job = store.get(identifier)
        if not job or job['payload']['mode'] != mode():
            return jsonify(error='Investigation not found.'), 404
        store.cancel(identifier)
        return jsonify(state=store.get(identifier)['state'],
            message='No new calls after cancellation is observed. An in-flight request may finish and be billed.')

    @app.post('/api/research-decisions')
    def decision():
        body = DecisionRequest.model_validate(request.get_json(silent=True))
        job = store.get(body.job_id)
        if not job or job['state'] != 'completed' or job['payload']['mode'] != mode():
            return jsonify(error='Review a completed investigation before recording a decision.'), 400
        with decision_lock:
            prior = next((d for d in store.decisions(body.job_id) if d['decision_id'] == body.decision_id), None)
            if prior:
                if any(prior[key] != getattr(body, key) for key in ['action','rationale','confirmed']):
                    return jsonify(error='Decision ID was already used for a different decision.'), 409
                return jsonify(prior)
            result = body.model_dump(mode='json')
            if body.action == 'approve_screening':
                if not body.confirmed or not job['payload']['selection'].get('run_id'):
                    return jsonify(error='Explicit confirmation and an originating Scout run are required for screening approval.'), 400
                run_id = job['payload']['selection']['run_id']
                saved = store.get_run(run_id)
                run = restore_run(saved['data']['raw'])
                RUNS[run_id] = run
                weights = Weights(**job['payload']['weights'])
                ranked = rescore(run, weights)
                symbol = job['payload']['selection']['target_input']['target_symbol']
                target = next(t for t in ranked.targets if t.evidence.symbol == symbol)
                response = child_dispatch('/api/approvals', {'run_id': run_id, 'symbol': symbol,
                    'weights': weights.as_dict(), 'scores': asdict(target.scores), 'reason': body.rationale})
                if response.status_code != 200:
                    return jsonify(error='Existing Scout approval validation did not accept this decision.'), 400
                result['approval'] = response.get_json()
            result['mode'] = mode()
            store.decision(body.decision_id, body.job_id, result)
            return jsonify(result)

    if start_worker:
        worker.start()
    return app

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5050)
    args = parser.parse_args()
    app = create_app()
    app.run(host='127.0.0.1', port=args.port, debug=False, use_reloader=False, threaded=True)

if __name__ == '__main__':
    main()
