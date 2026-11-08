# Stateless Workbench on Vercel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the whole research workbench deployable on Vercel alone by removing SQLite and the worker thread, running investigations synchronously, and keeping runs/reports/decisions in the browser.

**Architecture:** `devils_advocate/` moves under `backend/` so one Python service root bundles everything; `backend/app.py` exposes the workbench Flask app. The server becomes stateless: investigations run inside the request, the client echoes back the scout run / report / signed approval that each later step needs. The frontend persists full objects in localStorage and no longer polls.

**Tech Stack:** Flask 3, pydantic 2, requests, google-genai; Next.js 16.4.5 App Router, vitest 3; Vercel Services (Fluid compute, 300 s default).

**Spec:** `docs/superpowers/specs/2026-11-08-stateless-workbench-design.md`

## Global Constraints

- No new hosted dependency (no SQLite file relied upon, no Postgres, no queue, no second host).
- Recorded (`offline`) mode never performs network or paid model calls.
- Request budget: retrieval ≤ `RESEARCH_RETRIEVAL_BUDGET_SECONDS` (default 150), Gemini ≤ 120 s.
- Error bodies never include exception text from upstream libraries (keep Henri's sanitized copy).
- `X-Research-Mode` header semantics unchanged; unknown value → 400.
- Local dev stays: backend on :5050 (`python -m devils_advocate.server` from `backend/`), Next on :3000.
- Commits after each task; run the three suites (backend pytest, challenger pytest, vitest) before each commit that touches them.

## Review Focus

1. A same-origin POST from the Vercel domain sends an `Origin` header → must be accepted (Task 4 test `test_vercel_origin_is_allowed_from_env`).
2. A rationale request landing on a cold instance (no `RUNS` entry) → must succeed from the posted `run` (Task 2 test `test_rationale_rebuilds_result_from_posted_run`).
3. A forged approval object posted to `/api/screen` → 403, never screened (Task 4 test `test_screen_rejects_unsigned_or_tampered_approval`).
4. An investigation that raises inside the pipeline → 200 with `state: failed` and a sanitized `error`, not a 500 stack (Task 3 test `test_pipeline_exception_becomes_sanitized_failure`).
5. Reload with a saved v2 state whose target is not in the saved run → restore the run, drop the target and job (Task 6 test `restores run but drops a target that is no longer in it`).

---

### Task 1: Move `devils_advocate` under `backend/` and fix path assumptions

**Files:**
- Move: `devils_advocate/` → `backend/devils_advocate/` (`git mv`)
- Modify: `backend/devils_advocate/server.py:21-23` (`ROOT`, `sys.path`, demo cache path), `backend/devils_advocate/ai_config.py:23` (`.env` path → repo root = `parents[2]`), `backend/devils_advocate/tests/*` only where they reference `ROOT / 'backend'` or repo-root paths, `scripts/qa_workbench_server.py`, `scripts/demo.sh`
- Modify: `backend/requirements.txt` (add `pydantic>=2.8,<3`), `.gitignore` (add `backend/runtime/`, drop nothing)
- Delete: `backend/devils_advocate/requirements.txt`, `backend/devils_advocate/requirements-lock.txt` (superseded by `backend/requirements.txt`; keep `demo_app.py` but note streamlit is not installed by default)

**Interfaces:**
- Produces: importable `devils_advocate` package when `cwd=backend/` or `backend/` on `sys.path`; `ROOT` in `server.py` now means `backend/`.

- [ ] **Step 1: Move and grep for stale absolute assumptions**

```bash
git mv devils_advocate backend/devils_advocate
grep -rn "parents\[1\]\|ROOT / 'backend\|backend/data/demo_cache\|devils_advocate/" backend/devils_advocate scripts README.md frontend/README.md
```

- [ ] **Step 2: Fix `server.py`**: `ROOT = Path(__file__).resolve().parents[1]` (= `backend/`); `sys.path.insert(0, str(ROOT))`; demo cache `ROOT / 'data/demo_cache'`. Fix `ai_config.py`: `.env` at `Path(__file__).resolve().parents[2] / '.env'`. Check `rationale.py` loads `.env` from repo root already (it does: `REPO_ROOT`).

- [ ] **Step 3: Run the challenger suite from `backend/`**

Run: `cd backend && . venv/bin/activate && pip install "pydantic>=2.8,<3" && python -m pytest devils_advocate/tests -q`
Expected: 129 passed (same count as before the move).

- [ ] **Step 4: Run the backend suite**: `python -m pytest tests -q` → 74 passed.

- [ ] **Step 5: Update `scripts/demo.sh` and `scripts/qa_workbench_server.py`** to `cd backend && python -m devils_advocate.server --port 5050` / imports from `backend/`.

- [ ] **Step 6: Commit** `refactor: move devils_advocate under backend/ for a single Python service root`

---

### Task 2: Scout response carries evidence; rationale rebuilds from a posted run

**Files:**
- Modify: `backend/pipeline/api.py` (`scout_run_json`, `rationale`)
- Create: `backend/pipeline/scout/restore.py`
- Test: `backend/tests/test_api.py`, `backend/tests/test_restore.py`

**Interfaces:**
- Produces: `pipeline.scout.restore.result_from_run_json(run: dict) -> ScoutResult` — rebuilds `Disease`, `Weights(**run['weights'])` if present else defaults, and each target from `target['evidence']` (`TargetEvidence(**ev)` with `safety_flags` → `SafetyFlag`). Raises `ValueError` when `evidence` is missing.
- Produces: scout JSON target field `evidence: dict` = `dataclasses.asdict(TargetEvidence)`.
- Rationale body: `{run_id, run?, weights}`; lookup order `RUNS.get(run_id)` then `result_from_run_json(body['run'])`; neither → 404 (existing message).

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_restore.py
def test_round_trip_scout_json_rebuilds_identical_scores(api):
    run = api.post('/api/scout', json={'disease': 'Parkinson disease'}).get_json()
    result = result_from_run_json(run)
    rescored = rescore(result, Weights())
    assert [t.evidence.symbol for t in rescored.targets] == [t['symbol'] for t in run['targets']]
    assert abs(rescored.targets[0].scores.total - run['targets'][0]['components_total']) < 1e-6  # see note

def test_missing_evidence_raises():
    with pytest.raises(ValueError): result_from_run_json({'disease': {...}, 'targets': [{'symbol': 'X'}]})

# backend/tests/test_api.py
def test_scout_targets_include_raw_evidence(api): ...assert 'datatype_scores' in run['targets'][0]['evidence']
def test_rationale_rebuilds_result_from_posted_run(api, monkeypatch):
    # clear RUNS, post {run_id:'gone', run:run, weights}, monkeypatch explain to return rescored input → 200 with rationales
```
Note: the scout JSON has no `components_total`; assert instead that each rebuilt target's components equal `run['targets'][i]['components']` within 1e-6 (components are weight-independent).

- [ ] **Step 2: Run** `python -m pytest tests/test_restore.py tests/test_api.py -q` → FAIL (ImportError / KeyError).
- [ ] **Step 3: Implement** `restore.py` and the two `api.py` changes.
- [ ] **Step 4: Run** full backend suite → all pass (74 + 4).
- [ ] **Step 5: Commit** `feat(scout): echo raw evidence and rebuild runs for stateless rationale`

---

### Task 3: Synchronous investigation module replaces JobStore + JobWorker

**Files:**
- Create: `backend/devils_advocate/investigation.py`
- Delete: `backend/devils_advocate/job_store.py`, `backend/devils_advocate/job_worker.py`
- Test: `backend/devils_advocate/tests/test_investigation.py`

**Interfaces:**
- Produces:
  ```python
  class InvestigationFailed(RuntimeError): ...  # .message is user-safe
  def run_investigation(payload: dict, *, investigator=investigate_target, ai_reasoner=run_ai_reasoning,
                        client: JsonClient | None = None, budget_seconds: int | None = None) -> dict
  ```
  `payload` = `{'selection': {'target_input': {...}, ...}, 'mode': 'live'|'offline', 'use_ai': bool, 'weights': dict, 'ai_policy': dict}` (same dict the server built before). Returns the `report` dict exactly as `JobWorker.execute` built it (`investigation`, `experiment`, `recorded_ai`, `selection`, `timings`, `weights`, `mode`) plus `'calls': [...]` (AI call dicts, `[]` when none). `budget_seconds` default = `int(os.getenv('RESEARCH_RETRIEVAL_BUDGET_SECONDS', '150'))`. Failures: `RetrievalDeadlineExceeded` → `InvestigationFailed(str(exc))`; `ValueError` and any other `Exception` → `InvestigationFailed(<the two existing sanitized sentences>)`.

- [ ] **Step 1: Failing tests**
```python
def test_offline_lrrk2_playback_builds_report_without_live_calls():
    payload = {...offline LRRK2 selection...}
    report = run_investigation(payload, investigator=Mock(side_effect=AssertionError), ai_reasoner=Mock(side_effect=AssertionError))
    assert report['investigation']['target']['target_symbol'] == 'LRRK2' and report['mode'] == 'offline' and report['calls'] == []
def test_live_report_keeps_failed_ai_and_resolution(): # investigator Mock → Investigation(resolved CHEMBL203); ai_reasoner Mock → AIReport(status='failed') → report['investigation']['ai']['status']=='failed'
def test_pipeline_exception_becomes_sanitized_failure(): # investigator raises RuntimeError('boom') → InvestigationFailed, 'boom' not in str(exc)
def test_deadline_exceeded_message_is_surfaced(): # investigator raises RetrievalDeadlineExceeded('budget') → InvestigationFailed with 'budget'
```
- [ ] **Step 2: Run** → FAIL (module missing).
- [ ] **Step 3: Implement** `investigation.py` by lifting `JobWorker.execute` without store/heartbeat/cancel; `with client.tracking(None, budget_seconds=budget) as measured` for live; AI `on_progress` collects `calls`.
- [ ] **Step 4: Delete** `job_store.py`, `job_worker.py`; remove their imports from `server.py` (temporarily breaks server tests—Task 4 fixes them; do not commit between 3 and 4 unless the server import is stubbed).
- [ ] **Step 5: Run** `python -m pytest devils_advocate/tests/test_investigation.py -q` → 4 passed.

---

### Task 4: Stateless server routes

**Files:**
- Modify: `backend/devils_advocate/server.py` (rewrite route section)
- Create: `backend/devils_advocate/approval_signing.py`
- Test: `backend/devils_advocate/tests/test_workbench.py` (rewrite), `backend/devils_advocate/tests/test_signing.py`

**Interfaces:**
- Consumes: `run_investigation`, `InvestigationFailed` (Task 3); `result_from_run_json` not needed here (child app handles rationale).
- Produces (`approval_signing.py`):
  ```python
  def signing_key() -> bytes          # WORKBENCH_SECRET env or module-level random token
  def sign(approval: dict) -> str     # hmac-sha256 hex over json.dumps(approval minus 'signature', sort_keys=True)
  def verify(approval: dict) -> bool  # hmac.compare_digest
  ```
- Produces (`server.py`):
  - `allowed_origins() -> list[str]` per spec (`WORKBENCH_ORIGINS`, `VERCEL_URL`, `VERCEL_BRANCH_URL`, `VERCEL_PROJECT_PRODUCTION_URL`).
  - `create_app(runtime: Path | None = None, *, investigator=investigate_target, ai_reasoner=run_ai_reasoning) -> Flask`; default `runtime = data_dir('runtime')` (from `pipeline.settings`). `app.config['INVESTIGATOR']`/`['AI_REASONER']` so tests can swap via config (read at request time).
  - `ChallengeRequest` gains `run: dict | None`; loses nothing else. Response of `POST /api/investigations` = Job shape (spec).
  - `DecisionRequest` gains `report: dict`, `target: dict | None`.
  - `POST /api/screen` body `{approval: dict}`; `POST /api/research-decisions` builds `Approval` via `pipeline.audit` helpers: new helper `audit.approval_from_components(disease_id, disease_name, target: dict, weights: Weights, reason) -> Approval` computing `total` with `pipeline.scout.scoring.weighted_total`.
  - Legacy allow-list: `['health', 'scout', 'rationale', 'approvals']` (`approvals` POST still 403; `screen` and `shortlists` are no longer forwarded—`screen` is an explicit route).
  - `GET /api/workbench/config` → `server='Flask (stateless)'`.

- [ ] **Step 1: Rewrite `test_workbench.py`** keeping these tests (adapted): LRRK2 handoff; offline job never calls live/Gemini (now asserts response `state=='completed'`); BACE1 playback; human approval gates screening (forged approval → 403, decision without `confirmed` → 400, with → 200 + `approval.signature`, then `/api/screen` with that approval → 200 with compounds); mode/origin/input validation (drop the `workbench/runs` 404 line; add unknown weight → 400, missing run and target_input → 400); live mode cache isolation; live job preserves failed AI (via `app.config['INVESTIGATOR']` mocks, response `state=='completed'`); unrelated/invalid live targets; rationale forwarded. Add: `test_vercel_origin_is_allowed_from_env` (monkeypatch `VERCEL_URL=my-app.vercel.app` → Origin `https://my-app.vercel.app` → 200); `test_screen_rejects_unsigned_or_tampered_approval`; `test_failed_investigation_returns_state_failed_with_sanitized_error` (investigator raises → 200, `state=='failed'`, `'boom' not in error`); `test_removed_job_routes_are_gone` (GET `/api/investigations/x` → 404, GET `/api/workbench/runs/x` → 404).
  Delete: dedupe/idempotency test, cancelled/lease test, restarts test.
- [ ] **Step 2: Write `test_signing.py`**: sign/verify round trip; tampering a field fails; `WORKBENCH_SECRET` env changes the signature.
- [ ] **Step 3: Run** → FAIL.
- [ ] **Step 4: Implement** `approval_signing.py`, `audit.approval_from_components`, and the server rewrite.
- [ ] **Step 5: Run** both suites from `backend/`: `python -m pytest tests devils_advocate/tests -q` → all pass.
- [ ] **Step 6: Commit** `feat(server): stateless workbench — synchronous investigations, signed approvals, no SQLite`

---

### Task 5: Vercel entrypoint, config, docs

**Files:**
- Modify: `backend/app.py` (expose workbench app), `vercel.json` (unchanged keys; verify), `frontend/next.config.ts` (`proxyTimeout: 300_000`), `README.md` (layout, run, Vercel sections), `frontend/README.md` (SQLite/idempotency paragraphs → localStorage + stateless), `backend/devils_advocate/README.md` (run path), `scripts/demo.sh`
- Test: `backend/tests/test_entrypoint.py`

- [ ] **Step 1: Failing test** `test_app_module_exposes_workbench_routes`: import `app` from `backend/app.py` with `SCOUT_DATA_DIR=tmp`; `app.url_map` contains `/api/investigations` and `/api/scout`.
- [ ] **Step 2: Implement** `backend/app.py`:
  ```python
  from dotenv import load_dotenv; load_dotenv()
  from devils_advocate.server import create_app
  app = create_app()
  ```
  with `__main__` running on port 5050.
- [ ] **Step 3: Docs**: README "Deploying to Vercel" → everything runs on Vercel; required env (`GEMINI_API_KEY`, `AI_MODEL`, `AI_ENABLED`, `WORKBENCH_SECRET`); 300 s budget note; audit trail is browser-side + downloadable report. Remove Railway/Render paragraph.
- [ ] **Step 4: Run** backend + challenger suites → pass.
- [ ] **Step 5: Commit** `chore: workbench app is the Vercel entrypoint; docs for stateless deployment`

---

### Task 6: Frontend persistence helper

**Files:**
- Create: `frontend/lib/workbench-storage.ts`
- Modify: `frontend/lib/contracts.ts` (Job.decisions stays; add `SavedState` export), `frontend/lib/scout-types.ts` (`evidence?: Record<string, unknown>` on `ScoutTarget`)
- Test: `frontend/lib/workbench-storage.test.ts`

**Interfaces:**
```ts
export const STORAGE_KEY = 'agentverse-workbench-v2';
export type SavedState = { mode: Mode; run: ScoutRun | null; target_id: string | null; weights: Weights; job: Job | null };
export function loadState(storage: Pick<Storage,'getItem'>): SavedState | null;   // null on missing/corrupt; drops target_id and job when target not in run; drops run when run.cache_only !== (mode==='offline')
export function saveState(storage: Pick<Storage,'setItem'>, state: SavedState): void; // swallow quota errors
export function withDecision(job: Job, decision: Decision): Job;  // appends, replacing same decision_id
```
- [ ] **Step 1: Failing tests** (vitest, node env, in-memory Map-backed storage): round trip; corrupt JSON → null; `restores run but drops a target that is no longer in it`; mode/cache_only mismatch drops run; `withDecision` replaces duplicate id.
- [ ] **Step 2: Run** `npm test` → FAIL. **Step 3: Implement.** **Step 4: Run** → pass. **Step 5: Commit** `feat(frontend): localStorage state helper for the stateless workbench`

---

### Task 7: Workbench shell and pages without polling

**Files:**
- Modify: `frontend/components/workbench.tsx`, `frontend/app/challenge/page.tsx`, `frontend/app/decision/page.tsx`, `frontend/app/experiment/page.tsx` (no change expected beyond `Progress`), `frontend/app/page.tsx` (rationale body gets `run`)

**Interfaces:**
- Context `State` becomes: `{mode,setMode,run,setRun,weights,setWeights,target,select,job,config,error,setError,busy,challenge,addDecision,refreshConfig,reset}`.
- `challenge(useAI, manual?)` posts `{run, symbol, use_ai, paid_authorized, weights}` or `{target_input, ...}` to `/api/investigations`, sets `job` from the response (200 for both completed and failed).
- `Progress` renders only while `busy`: spinner + "Investigating {symbol}. Retrieving public evidence{ai ? ' and running Gemini' : ''}. This usually takes one to three minutes; keep this page open."
- Decision page: `save()` posts `{decision_id, job_id, action, rationale, confirmed, report: job.result, target}` then `addDecision(result)`. `screen()` posts `{approval}`. Replace the SQLite notice text with "Decisions are kept in this browser and in the downloadable report."
- Challenge page: remove `RecentJobs`; failed-state notice keeps working with `state==='failed'`.

- [ ] **Step 1: Implement** the above (no unit test harness for components; verification is typecheck + lint + build + manual smoke in Task 8).
- [ ] **Step 2: Run** `npm run typecheck && npm run lint && npm run build` → clean.
- [ ] **Step 3: Commit** `feat(frontend): synchronous investigations, browser-held state, no cancel/recent jobs`

---

### Task 8: End-to-end smoke, Playwright spec update, final checks

**Files:**
- Modify: `frontend/tests/workbench.spec.ts` (replace the "temporary backend failure" test with "reload restores from localStorage without backend restore calls"; remove cancel expectations if any)
- Modify: `frontend/README.md` API section if route list is stale

- [ ] **Step 1: Smoke offline via curl against `python -m devils_advocate.server`** (from `backend/`): scout → investigations (LRRK2) → research-decisions approve → screen; assert HTTP 200 chain and `compounds` non-empty.
- [ ] **Step 2: Smoke live** (if network allowed): investigations for manual `EGFR` target without AI; expect `state: completed` within budget.
- [ ] **Step 3: Update Playwright spec**; do not claim it ran unless it does.
- [ ] **Step 4: Full verification**: `python -m pytest tests devils_advocate/tests -q`; `npm test`; `npm run typecheck && npm run lint && npm run build`.
- [ ] **Step 5: Commit** `test: e2e spec for stateless flow; smoke results in README`
