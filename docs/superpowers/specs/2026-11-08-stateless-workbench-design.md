# Stateless workbench on Vercel — design

Date: 2026-11-08. Branch: `merge/target-scout-and-henri`. Supersedes the hosting section of the README.

## Decision

Run the whole research workbench (Target Scout discovery + Target Challenger investigation,
experiment and decision) on Vercel alone. No SQLite, no job queue, no second host, no Postgres.

Agreed with the user:

- The create-investigation request runs the challenger to completion and returns the finished
  report in the response body instead of a job id.
- The frontend stops polling and shows an indeterminate "investigating" state for the duration of
  the one request.
- Runs, reports and decisions live in the browser's localStorage instead of SQLite. Refresh and
  restore work on the same browser. Server-side restore routes are removed.
- Cancel button and recent-jobs list are removed.
- Ranking, screening, rationale and the challenger pipeline itself are unchanged.

## Why the server must hold no state

Vercel runs the API as Fluid-compute functions. Two consecutive requests can land on two instances
with different memory and different `/tmp`. Therefore every request must carry what it needs:

| Server state today                           | Replacement                                                   |
| -------------------------------------------- | ------------------------------------------------------------- |
| `jobs` table + worker thread                 | synchronous `POST /api/investigations`                        |
| `scout_runs` table / in-memory `RUNS`        | client posts the saved scout run back (`run`) when needed     |
| `decisions` table                            | client keeps `job.decisions` in localStorage                  |
| `approvals.jsonl` lookup by `ts` for screen  | client posts the signed approval object; server verifies HMAC |

## Layout change

`devils_advocate/` moves to `backend/devils_advocate/`. Vercel bundles only files under a service's
`root`, and the API service root is `backend/`. One Python root, one `requirements.txt`. Internal
relative imports are untouched; the three absolute-path assumptions (`sys.path` insert, demo cache
path, `.env` location) are updated.

`backend/app.py` (the Vercel entrypoint `app:app`) becomes the workbench server, so every `/api/*`
route exists on Vercel. Locally the same app runs on :5050 via `python -m devils_advocate.server`
from `backend/`.

## API contract (what changes)

All routes keep the `X-Research-Mode: live|offline` header.

- `POST /api/scout` — unchanged shape, plus each target gains `evidence` (the raw
  `TargetEvidence` dataclass as a dict) so the client can post it back for rationale.
- `POST /api/rationale` — body `{run_id, run?, weights}`. Server uses in-memory `RUNS[run_id]` if
  present (warm instance), otherwise rebuilds the result from `run.targets[*].evidence`.
- `POST /api/investigations` — body
  `{run?: ScoutRun, symbol?: str, target_input?: TargetInput, use_ai, paid_authorized, weights}`.
  Runs synchronously. Returns **200** with the existing `Job` shape:
  `{job_id, state: 'completed'|'failed', progress:{stage, calls}, result: Report|null, error,
  mode, selection, weights, decisions: []}`. Validation errors stay 400. No Idempotency-Key.
- `POST /api/research-decisions` — body
  `{decision_id, job_id, action, rationale, confirmed, report_sig, target_sig?}` (revised after
  review: the server signs what it produced, scout targets get `sig` and investigation responses
  `report_sig`, and the client posts those tokens back instead of the full report). For
  `approve_screening` the server verifies both tokens, computes the weighted total from the signed
  components and weights, builds an `Approval`, appends it to the (ephemeral) approvals log, and
  returns the decision with `approval` carrying a signed token in `signature`.
- `POST /api/screen` — body `{approval}` (the signed object). Server verifies the signature
  (403 otherwise) and runs screening. Replaces the `approval_ts` lookup in the workbench.
- Removed: `GET /api/investigations`, `GET /api/investigations/<id>`,
  `POST /api/investigations/<id>/cancel`, `GET /api/workbench/runs/<id>`, `shortlists` forwarding.

Signing key: `WORKBENCH_SECRET` env var; if unset, a per-process random key (fine for one local
server). On Vercel (`VERCEL=1`) an unset secret makes approval issuance fail closed with a 503.
Tokens are `base64url(payload).hmac`, verified on the exact signed bytes so browser JSON
re-serialisation (1.0 → 1) cannot break them.

Allowed origins: `http://127.0.0.1:3000`, `http://localhost:3000`, every entry of
`WORKBENCH_ORIGINS` (comma-separated), and `https://` + each of `VERCEL_URL`,
`VERCEL_BRANCH_URL`, `VERCEL_PROJECT_PRODUCTION_URL` when set.

## Time budget

Vercel Hobby and Pro both default to 300 s per request. Retrieval budget drops from 300 s to
`RESEARCH_RETRIEVAL_BUDGET_SECONDS` (default 150); Gemini timeout stays ≤ 120 s. Worst case ≈ 270 s.
`frontend/next.config.ts` `proxyTimeout` rises to 300 s for local dev parity.

## Frontend

- localStorage key `agentverse-workbench-v2` holds `{mode, run, target_id, weights, job}` (full
  objects). Restore reads it synchronously; no backend calls on load except `/api/workbench/config`.
- `Workbench` context drops `cancel`, `refresh`, `resume`; adds `addDecision(decision)`.
- `Progress` shows a spinner and a static explanation; no stage/cancel.
- `RecentJobs` is deleted.
- Decision page posts `report` and `target`; screening posts `{approval}`.

## Out of scope

Durable audit trail, multi-device continuity, idempotent double-submit protection on the server
(the button is disabled while a request is in flight), Playwright run in this sandbox (spec is
updated but execution is left to the user).
