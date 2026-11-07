# Agentverse Research Workbench

Local Next.js + TypeScript dashboard over the existing Flask Target Scout and
Devil's Advocate pipelines. The root Next.js application, original backend
entry point and Streamlit backup are preserved. No ranking/scoring algorithm
was replaced. This workspace uses Next 16.4.5, React 19.3.1 and Tailwind 4.3.5.

## Evidence presentation and latency instrumentation

Readable scientific text uses labelled Evidence references. Each opens the
collapsible Evidence Trace, which retains accepted claim text, exact excerpts,
source identifiers and registry/publication links. Internal claim IDs remain in
the technical disclosures and structured audit; historical reports are rendered
without rewriting their scientific records. Hypotheses sharing the same claim
are explicitly marked as sharing motivating evidence rather than independent
confirmation. New synthesis requests map each hypothesis to accepted claim IDs.

`AI_THINKING_LEVEL=medium` is the demo default; `high` remains supported.
`AI_MODEL` remains configurable. Python loads the root `.env` with
`override=False`, so an existing process environment takes precedence. The
Google SDK receives the normalized level in `generation_config.thinking_level`.
An already running backend retains its environment until you choose to restart
it. No restart or paid model request is required to run the offline tests.

New jobs record retrieval and per-agent attempt durations with a monotonic
clock, plus serialized input bytes (not tokens). The UI displays the current
public source/API path, elapsed request time, completed requests, observed
retries where available, cache hits, and a durations table. Historical missing
timings display “Not recorded”. Safe retrieval diagnostics are also appended to
`devils_advocate/runtime/retrieval-events.jsonl`; query parameters and secrets
are excluded. Requests retain 5-second connection / 20-second read timeouts,
at most three attempts, and bounded backoff. A 300-second retrieval phase budget
is checked between requests and after a response: it does not interrupt an
in-flight request or guarantee a hard DNS/slow-stream wall-clock limit. Budget
exhaustion produces an explicit error and starts no Gemini call.

The existing 15-minute in-process public-response cache is reused by the worker.
Adjudication still receives the full selected evidence packet; the experiment
designer receives accepted claims and their supporting records. Revision input
no longer duplicates the preceding draft inside feedback. Fully accepted claims
proceed directly to design, retaining strict deterministic checks, adjudication,
the paid-call cap and researcher approval requirements.

Measured validation is recorded in
`../devils_advocate/validation/presentation_latency.json`. Reconstructed BACE1
request shapes shrink revision input from 43,107 to 35,272 bytes and designer
input from 32,328 to 25,186 bytes. A single public ChEMBL lookup took 1.281246 s
uncached and 0.005617 s cached; caching already existed. These measurements do
not establish an end-to-end speedup or a Medium-versus-High latency comparison.
No paid Gemini calls were made for this validation.

Reproduce the packet-size check without network/model calls:

```powershell
.\.venv\Scripts\python.exe -m devils_advocate.profile_latency
# Optional public ChEMBL request, never Gemini:
.\.venv\Scripts\python.exe -m devils_advocate.profile_latency --live-cache-check
```

Browser QA can use an isolated AI-disabled backend and temporary database:

```powershell
# Terminal 1, repository root
.\.venv\Scripts\python.exe scripts/qa_workbench_server.py
# Terminal 2, frontend directory
$env:RESEARCH_BUILD_DIR='.next-qa'
$env:RESEARCH_BACKEND_URL='http://127.0.0.1:5051'
npm.cmd exec -- next dev --hostname 127.0.0.1 --port 3001
# Terminal 3, frontend directory
$env:PLAYWRIGHT_BASE_URL='http://127.0.0.1:3001'
npm.cmd run test:e2e
```

## Windows setup and startup

Requirements: Python 3.11+, Node 20.9+ (tested with Python 3.13 / Node 24.13),
and npm. Run commands from the **repository root**, not from `backend/`.

```powershell
# One-time install (the .cmd wrappers avoid PowerShell npm.ps1 policy issues)
.\scripts\setup-workbench.cmd
```

Two terminals:

```powershell
# Terminal 1: Flask + persistent local job worker
.\scripts\workbench-backend.cmd
# Equivalent: .\.venv\Scripts\python.exe -m devils_advocate.server --port 5050
```

```powershell
# Terminal 2: new Next.js workspace
.\scripts\workbench-frontend.cmd
# Equivalent: npm.cmd --prefix frontend run dev
```

- Frontend: **http://127.0.0.1:3000**
- Backend: **http://127.0.0.1:5050/api/health**
- Streamlit backup: `.\.venv\Scripts\python.exe -m streamlit run devils_advocate/demo_app.py`
  (default http://localhost:8501; an existing session may use 8510).

Keep the repository-root `.env` private. The Python process loads the existing
`GEMINI_API_KEY`, `AI_PROVIDER`, `AI_MODEL`, `AI_ENABLED`, `AI_THINKING_LEVEL`
and bounded-call settings. Never put keys in frontend files or `NEXT_PUBLIC_`
variables. `RESEARCH_BACKEND_URL` optionally changes Next's server-side API proxy
destination; it defaults to http://127.0.0.1:5050. There are no browser-side keys.

## Recorded demonstration without Wi-Fi

The frontend starts in **Recorded demo** mode. API requests include
`X-Research-Mode: offline`; this is independently enforced by the backend.

1. Enter **Parkinson disease**, then **Discover targets**. The existing Scout
   pipeline reads its bundled public-response cache and ranks 25 targets.
2. Select **LRRK2**. The selected Ensembl ID, ChEMBL ID, UniProt, disease ID,
   PMIDs, safety flags, scores and run/cache provenance are passed server-side.
3. Click **Challenge this target**. Recorded LRRK2 evidence is loaded with **zero
   retrieval/model calls**. No Gemini output is invented for this example.
4. Inspect historical evidence, applicability, missing stop reasons and citations.
   The experiment is a clearly labelled deterministic, unvalidated proposal.
5. Open **Researcher decision**, choose a decision and enter a rationale.
6. To screen, choose **Approve for protein screening**, check explicit
   confirmation and save. Then click the separate **Run approved screening**
   button. Existing Scout approval validation and cached AlphaFold/ChEMBL
   screening are reused. Challenging never approves or screens automatically.

For recorded Gemini output, open Devil's Advocate without a Scout selection
(or change mode to clear selection), expand **Investigate a target directly**,
and use **Alzheimer's disease / BACE1 / CHEMBL4822**. The saved BACE1 source
snapshot and prior actual five-call Gemini audit are replayed with a
**RECORDED AI** badge and **0 new paid calls**. This is historical output,
not a new model result. All source IDs/URLs and the original audit remain intact.
Manual targets require an originating Scout run before screening approval.

The source fixtures are `devils_advocate/fixtures/workbench_bace1.json`,
`workbench_lrrk2.json` and `workbench_bace1_ai.json`. Their notes retain original
capture context. LRRK2 has no curated ChEMBL mechanism compounds in the recorded
retrieval; its trials remain uncertain candidates, not demonstrated failures.
The original smaller BACE1 fixture and all existing tests are retained.

## Live workflow and explicit paid authorization

Choose **Live APIs**, run discovery, select a target and review the displayed
model/call cap. Live Scout clients do **not** read the recorded demo cache.
Successful live responses may use the normal server API cache, labelled
**LIVE / API CACHE**; no recorded evidence is silently substituted on failures.

The paid checkbox and **Challenge this target** button authorize the specific
investigation. The backend independently requires `paid_authorized=true` and
enabled AI configuration. Maximum paid request attempts are frozen server-side
at submission (default five), with medium thinking and a 120-second request
timeout. Source retrieval remains deterministic; the existing three Gemini
roles, one revision round and citation checks are reused. No new paid test was
required to validate this UI migration; network/AI failures are tested with mocks.

Jobs return quickly, then the frontend polls their actual backend stage and
completed/attempted call counts. No invented percentage is displayed. Model
calls are not held open through a frontend proxy request. Failed AI reasoning
preserves retrieved evidence and a labelled deterministic fallback proposal.

**Stop after current call** prevents subsequent calls once cancellation is
observed. An in-flight provider request cannot reliably be recalled and may
finish/be billed. Refreshing or navigating does not terminate a job. Recent
investigations can be resumed from the Challenge page. Mode/target changes clear
the visible report, experiment, approval and decision form; old asynchronous
responses cannot overwrite the newly selected target.

## ChEMBL fix and measured diagnostics

`TargetInput` now accepts separate `chembl_target_id` and `uniprot` fields while
preserving the original Ensembl `target_id`. Supplied ChEMBL IDs use the direct
`/target/CHEMBL....json` endpoint and must match the returned ID, human organism,
taxon, SINGLE PROTEIN type, exactly one protein component, exact gene symbol and
supplied UniProt accession. Mismatched or conflicting IDs are rejected rather
than replaced by a fuzzy name hit. With no supplied ChEMBL ID, exact symbol-based
search remains available. Verified resolutions are cached for 15 minutes on the
shared worker client, across disease investigations; only verified positives are
cached. Restarting the process requires fresh verification.

The HTTP client uses connection/read timeouts, two bounded retries with backoff
for transient 429/5xx responses, and a 15-minute successful-response cache.
`resolution_status` distinguishes resolved, unknown, temporarily unavailable and
invalid supplied identifiers. Malformed/non-JSON responses are source failures,
not proof that a target is unknown.

Actual diagnostics in `devils_advocate/validation/chembl_diagnostic.json`:
the BACE1 search returned **HTTP 200 with five candidates**, while the direct
lookup returned a **temporary HTTP 500 HTML response** in that sample. This
confirms intermittent service behavior; the originally reported search failure
did not persist in that sample. A subsequent run through the real bounded-retry
resolver verified BACE1/CHEMBL4822, LRRK2/CHEMBL1075104 and EGFR/CHEMBL203,
including their UniProt components. Cached rechecks succeeded. FAKEGENE123
returned unknown. See `validation/chembl_identity_report.json` for exact outcomes.

## Architecture and endpoints

- `backend/app.py` and `backend/pipeline/api.py`: original Flask service and
  Scout, approvals and screen contracts. Scientific ranking functions are intact.
- `devils_advocate/server.py`: thin Flask integration, source-mode boundaries,
  nested Scout adapter, durable runs and researcher decisions; no FastAPI duplicate.
- `devils_advocate/job_store.py`: SQLite jobs, idempotency keys, worker leases,
  persisted Scout runs and decision audit.
- `devils_advocate/job_worker.py`: background deterministic retrieval + existing
  Gemini workflow, cancellation between paid requests and recorded playback.
- `frontend/`: App Router pages, accessible native controls and reusable report
  components. Ranking calls the existing `lib/score.ts` helpers unchanged.

| Endpoint | Purpose |
|---|---|
| POST `/api/scout` | Existing nested Scout response, persisted run and cache provenance |
| GET `/api/approvals` | Existing mode-specific researcher approvals |
| POST `/api/screen` | Existing pipeline, only after an actual researcher approval |
| POST `/api/shortlists` | Existing approved-target shortlist API |
| GET `/api/workbench/config` | Public model/provider/call-cap settings; no key |
| GET `/api/workbench/runs/:id` | Restore a persisted Scout response |
| POST `/api/investigations` | Validate source selection/consent, enqueue once |
| GET `/api/investigations/:id` | Status, progress, result and decision history |
| GET `/api/investigations` | Recent mode-specific jobs for recovery |
| POST `/api/investigations/:id/cancel` | Cooperative cancellation |
| POST `/api/research-decisions` | Rationale, decision and explicit screening confirmation |

The nested Scout response is flattened by the existing adapter module:
`flatten_scout_selection(run, symbol)`. Target identity is server-authoritative;
the browser cannot silently substitute a different ID for a selected Scout row.
Original association, weighted score, components, safety flags, PMIDs,
Ensembl/ChEMBL/UniProt IDs and run/cache provenance are retained separately.
Association and ranking scores are never treated as success probabilities.

POST investigations requires a stable `Idempotency-Key`. SQLite transactionally
deduplicates retries and active matching target investigations. Keys cannot be
reused for a different request. Duplicate UI clicks are also blocked. Browser
refresh restores the job ID and original Scout run, while recent jobs provide a
second recovery path. Server restart recovers queued jobs; an expired running
lease becomes **interrupted** and is never automatically replayed, because a
previous provider request may already have completed. A new paid attempt requires
fresh researcher action. Decisions persist across restarts and are idempotent.

Runtime data stay under ignored `devils_advocate/runtime/`: SQLite plus separate
live/offline approval and shortlist JSONL files. The existing Scout approval
handler recomputes weighted scores before approval. Direct approval creation
through this integration is gated through Researcher Decision; the original
standalone Scout API remains unchanged.

## Validation commands

```powershell
.\.venv\Scripts\python.exe -m pytest devils_advocate/tests backend/tests -q
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
# Both local servers must be running; Chrome must already be installed.
npm.cmd --prefix frontend run test:e2e
# Optional real identity checks only; no model calls
.\.venv\Scripts\python.exe -m devils_advocate.validate_chembl_identity
```

Playwright covers the recorded Parkinson/LRRK2 path, refresh recovery, experiment
navigation, required rationale/confirmation, approved cached screening, clearing
evidence after selecting SNCA, explicit live authorization, and mobile navigation.
Tests use installed Chrome and do not download a browser or call Gemini.
TypeScript, ESLint and optimized Next.js build are separate checks.
The final validation passed **182 Python tests** and **5 browser scenarios**,
plus TypeScript, ESLint and the production build. The browser suite also verifies
recovery after a temporary backend outage and explicit historical BACE1 AI labels.

## Security, licences and limits

The local service binds **127.0.0.1**, disables Flask debug/reloader, restricts
browser origins to localhost/127.0.0.1:3000, validates request sizes and schemas,
and sanitizes public API errors. Keys remain in the Python process and are
excluded from job payloads, reports, Git and browser responses. The new frontend
does not invoke Scout's optional Anthropic rationale endpoint. All decisions and
experiments still require researcher review; no experiment executes automatically.

SQLite is durable, not an in-memory job store. This is a **single-machine local
MVP**, not a production deployment: add authentication/authorization, protected
storage, a production WSGI host, retention policies and a managed worker system
before exposing it to others or scaling to multiple machines. Approval JSONL
and SQLite writes do not form a distributed transaction; local serialized
decision handling is suitable for the hackathon, not a multi-host service.
Long source retrievals and in-flight model calls can remain slow or fail.

Recorded/lexically matched evidence is not proof of scientific applicability.
Full-record trial checks, exact citation checks and an LLM adjudicator do not
establish target validity, causality, study quality or therapeutic efficacy.
The final AI synthesis is not separately adjudicated. These limits are displayed
in the reports, and original source links remain available.

Source rights and attribution remain those of the original datasets: ChEMBL
CC BY-SA 3.0 with original source/version attribution, Open Targets attribution,
ClinicalTrials.gov terms and sponsor-submitted records, Europe PMC item-specific
publication rights, and AlphaFold data terms. See `../devils_advocate/README.md`
and the root README for primary licence/source links. Public API availability
does not blanket-license article abstracts. Preserve notices and review source
rights before redistributing the recorded fixtures. No patient-level data are used.
