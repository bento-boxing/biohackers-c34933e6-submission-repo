"""Stateless Flask integration. Reuses Scout endpoints and both scientific pipelines.

Run from backend/: python -m devils_advocate.server --port 5050
Nothing is stored between requests: investigations run synchronously, the browser keeps the
scout run, report and decisions, and screening is gated by an HMAC-signed approval object.
This lets the same app run locally and as a Vercel Function.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import uuid
from typing import Literal

from flask import Flask, jsonify, request
from flask_cors import CORS
from pydantic import BaseModel, ConfigDict, Field, ValidationError

ROOT = Path(__file__).resolve().parents[1]  # backend/
sys.path.insert(0, str(ROOT))
from pipeline import audit
from pipeline.api import create_app as scout_app, screening_json
from pipeline.http import HttpClient
from pipeline.models import Approval, Weights
from pipeline.scout.scoring import weighted_total
from pipeline.screening.pipeline import run_screening
from pipeline.settings import data_dir
from .ai_config import load_ai_settings
from .ai_reasoning import run_ai_reasoning
from .approval_signing import sign, verify
from .devil_advocate import investigate_target
from .investigation import InvestigationFailed, run_investigation
from .models import TargetInput
from .target_scout_adapter import flatten_scout_selection

LOCAL_ORIGINS = ['http://127.0.0.1:3000', 'http://localhost:3000']
WEIGHT_KEYS = set(Weights().as_dict())


def allowed_origins() -> list[str]:
    origins = list(LOCAL_ORIGINS)
    origins += [o.strip() for o in os.environ.get('WORKBENCH_ORIGINS', '').split(',') if o.strip()]
    for name in ['VERCEL_URL', 'VERCEL_BRANCH_URL', 'VERCEL_PROJECT_PRODUCTION_URL']:
        host = os.environ.get(name, '').strip()
        if host:
            origins.append(host if host.startswith('http') else f'https://{host}')
    return origins


class ChallengeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    run: dict | None = None
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
    report: dict
    target: dict | None = None


class ScreenRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    approval: dict


def create_app(runtime: Path | None = None, *, investigator=investigate_target, ai_reasoner=run_ai_reasoning):
    runtime = runtime or data_dir('runtime')
    apps = {}
    for mode in ['live', 'offline']:
        http = HttpClient(write_dir=runtime / 'api_cache' if mode == 'live' else None,
            read_dirs=[runtime / 'api_cache'] if mode == 'live' else [ROOT / 'data/demo_cache'],
            cache_only=mode == 'offline')
        apps[mode] = scout_app(client=http, approvals_path=runtime / mode / 'approvals.jsonl',
                               shortlists_path=runtime / mode / 'shortlists.jsonl')
    app = Flask(__name__)
    origins = allowed_origins()
    CORS(app, origins=origins, allow_headers=['Content-Type', 'X-Research-Mode', 'Idempotency-Key'])
    app.config['MAX_CONTENT_LENGTH'] = 4_000_000  # reports and scout runs travel in request bodies
    app.config['SCOUT_APPS'] = apps
    app.config['INVESTIGATOR'] = investigator
    app.config['AI_REASONER'] = ai_reasoner
    app.config['ORIGINS'] = origins

    def mode():
        return request.headers.get('X-Research-Mode', 'offline')

    def child_dispatch():
        with apps[mode()].test_client() as client:
            return client.open(request.path, method=request.method, query_string=request.query_string,
                               data=request.get_data(cache=True), content_type=request.content_type)

    @app.before_request
    def validate_origin():
        if request.headers.get('Origin') and request.headers['Origin'] not in app.config['ORIGINS']:
            return jsonify(error='Origin is not allowed.'), 403
        if mode() not in ['live', 'offline']:
            return jsonify(error='Choose live or offline research mode.'), 400

    @app.errorhandler(ValidationError)
    def invalid_input(_):
        return jsonify(error='Invalid request fields. Check identifiers, weights, report and required confirmation.'), 400

    @app.errorhandler(Exception)
    def unexpected(exc):
        from werkzeug.exceptions import HTTPException
        status = exc.code if isinstance(exc, HTTPException) else 500
        return jsonify(error='Request could not complete. Check the inputs or backend availability.'), status

    @app.get('/api/workbench/config')
    def config():
        settings = load_ai_settings()
        return jsonify(ai={k: v for k, v in settings.model_dump(mode='json').items()
                           if k in ['enabled', 'provider', 'model', 'thinking_level', 'max_calls', 'timeout_seconds']},
                       demo_targets=['LRRK2', 'BACE1'], server='Flask (stateless)', modes=['live', 'offline'])

    @app.route('/api/<path:legacy>', methods=['GET', 'POST'])
    def legacy_api(legacy):
        if legacy not in ['health', 'scout', 'rationale', 'approvals']:
            return jsonify(error='Unknown endpoint.'), 404
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            return jsonify(error='JSON object required.'), 400
        if legacy == 'approvals' and request.method == 'POST':
            return jsonify(error='Use the Researcher Decision endpoint after reviewing an investigation.'), 403
        if legacy == 'scout' and (not isinstance(body.get('disease'), str) or not body['disease'].strip() or len(body['disease']) > 200):
            return jsonify(error='A disease name of 1–200 characters is required.'), 400
        response = child_dispatch()
        if response.status_code >= 400:
            return jsonify(error='Scout source unavailable or request invalid. No alternate mode was substituted.'), response.status_code
        return response

    def parse_weights(raw: dict) -> Weights:
        if set(raw) - WEIGHT_KEYS:
            raise ValueError('Unknown ranking weight.')
        weights = Weights(**raw)
        if any(not math.isfinite(v) or v < 0 for v in weights.as_dict().values()):
            raise ValueError('Weights must be finite, nonnegative numbers.')
        return weights

    @app.post('/api/investigations')
    def create_investigation():
        body = ChallengeRequest.model_validate(request.get_json(silent=True))
        try:
            weights = parse_weights(body.weights)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        if body.run is not None:
            if body.target_input is not None or not body.symbol:
                return jsonify(error='Send either a Scout run with a symbol or a manual target, not both.'), 400
            if body.run.get('cache_only') != (mode() == 'offline'):
                return jsonify(error='Scout run was produced in a different research mode.'), 400
            try:
                selection = flatten_scout_selection(body.run, body.symbol)
            except (ValueError, KeyError, TypeError):
                return jsonify(error='Selected target is not part of this Scout run.'), 400
            c = selection['components']
            selection['weighted_score'] = weighted_total(c['genetic'], c['association'], c['druggability'], c['literature'], weights)
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
        job_id = uuid.uuid4().hex
        try:
            report = run_investigation(payload, investigator=app.config['INVESTIGATOR'],
                                       ai_reasoner=app.config['AI_REASONER'])
        except InvestigationFailed as exc:
            return jsonify(job_id=job_id, state='failed', progress={'stage': 'Investigation stopped', 'calls': []},
                           result=None, error=str(exc), mode=mode(), selection=selection,
                           weights=payload['weights'], decisions=[])
        calls = report.pop('calls', [])
        return jsonify(job_id=job_id, state='completed',
                       progress={'stage': 'Report ready for researcher review', 'calls': calls, 'timings': report['timings']},
                       result=report, error=None, mode=mode(), selection=selection,
                       weights=payload['weights'], decisions=[])

    @app.post('/api/research-decisions')
    def decision():
        body = DecisionRequest.model_validate(request.get_json(silent=True))
        report = body.report
        if report.get('mode') != mode() or not isinstance(report.get('investigation'), dict) \
                or not isinstance(report.get('selection'), dict):
            return jsonify(error='Review a completed investigation in this mode before recording a decision.'), 400
        result = body.model_dump(mode='json', exclude={'report', 'target'})
        if body.action == 'approve_screening':
            selection = report['selection']
            if not body.confirmed or not selection.get('run_id') or body.target is None:
                return jsonify(error='Explicit confirmation and an originating Scout target are required for screening approval.'), 400
            target_input = selection.get('target_input') or {}
            if body.target.get('symbol') != target_input.get('target_symbol') \
                    or body.target.get('target_id') != target_input.get('target_id'):
                return jsonify(error='The approved target does not match the investigated target.'), 400
            try:
                weights = parse_weights(report.get('weights') or {})
                approval = audit.approval_from_components(target_input.get('disease_id') or '', target_input.get('disease_name') or '',
                                                          body.target, weights, body.rationale)
            except (ValueError, KeyError, TypeError):
                return jsonify(error='Scout target is missing the component scores needed for an approval.'), 400
            record = {**approval.__dict__}
            record['signature'] = sign(record)
            try:
                audit.append_jsonl(apps[mode()].config['APPROVALS_PATH'], record)
            except OSError:
                pass  # ephemeral audit log; the signed approval returned to the client is authoritative
            result['approval'] = record
        result['mode'] = mode()
        return jsonify(result)

    @app.post('/api/screen')
    def screen():
        body = ScreenRequest.model_validate(request.get_json(silent=True))
        if not verify(body.approval):
            return jsonify(error='Screening requires an approval issued by this server.'), 403
        fields = {k: v for k, v in body.approval.items() if k != 'signature'}
        try:
            approval = Approval(**fields)
        except TypeError:
            return jsonify(error='Approval object is malformed.'), 400
        http = apps[mode()].config['HTTP_CLIENT']
        return jsonify(screening_json(run_screening(approval, client=http)))

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5050)
    args = parser.parse_args()
    app = create_app()
    app.run(host='127.0.0.1', port=args.port, debug=False, use_reloader=False, threaded=True)


if __name__ == '__main__':
    main()
