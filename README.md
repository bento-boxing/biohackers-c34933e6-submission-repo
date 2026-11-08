# Target Scout

Evidence-ranked drug targets with a human checkpoint, then compound screening for the approved target.
A **Next.js + Flask** monorepo built for Agentverse 2026.

```
/                   ← Next.js 16 frontend (TypeScript + Tailwind): app/, lib/
/backend            ← Flask API + the Python pipeline: backend/pipeline/
```

## What it does

**Stage 1 · Target Scout.** Type a disease. The backend resolves it in Open Targets, pulls the top N
associated proteins, and enriches each with Europe PMC paper counts, ChEMBL potent-compound counts,
and Open Targets safety liabilities plus heart/liver/kidney expression. Every target gets a score
from a formula you can see and change:

```
total = w_gen · genetic + w_assoc · association + w_drug · druggability + w_lit · literature
```

| component    | source                                                                  |
|--------------|-------------------------------------------------------------------------|
| genetic      | Open Targets `genetic_association` datatype score                       |
| association  | Open Targets overall association score                                  |
| druggability | ½ small-molecule tractability tier + ½ log-scaled ChEMBL potent count   |
| literature   | log-scaled Europe PMC hits for `"SYMBOL" AND "disease"`                 |

Default weights are 0.4 / 0.3 / 0.2 / 0.1. The sliders re-rank in the browser; nothing is hidden.
Safety flags are shown, never scored. An optional LLM rationale (Gemini) is written from the fetched
evidence only, on an explicit button, and is cached per weight setting.

**Human checkpoint.** Approving a target records who, when, why, the weights and the scores shown to
`backend/runs/approvals.jsonl`. The server recomputes the scores and rejects a mismatch.

**Stage 2 · Protein Screening.** For an approved target: the AlphaFold structure (mean pLDDT, links)
and the 50 most potent ChEMBL compounds (pChEMBL ≥ 6, i.e. ≤ 1 µM) with phase, Lipinski data and
approved-drug flags. A second checkpoint writes a shortlist to `backend/runs/shortlists.jsonl`.

## Repository layout

```
frontend/          Next.js 16 research workbench (the only UI): discovery → challenge → experiment → decision
devils_advocate/   Target Challenger: Flask server on :5050 that wraps the Scout API, plus the evidence pipeline
backend/           Target Scout pipeline + Flask API (library used by devils_advocate.server; runnable alone on :5000)
scripts/           demo.sh (bash) and Windows .cmd launchers
```

## Getting started

### Backend
```bash
cd backend
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt -r ../devils_advocate/requirements.txt
pytest                                               # Target Scout tests, offline
cd .. && python -m pytest devils_advocate/tests -q   # Challenger + workbench tests, offline
python -m devils_advocate.server --port 5050         # the server the UI talks to
```

### Frontend
```bash
cd frontend
npm install
npm test            # vitest: client-side scoring
npm run dev         # http://localhost:3000, proxies /api/* to :5050
```

`bash scripts/demo.sh` runs all of the above in one go.

### AI configuration (one set of keys for everything)
Both the Scout ranking rationale and the Challenger's reasoning use Gemini, configured in the
repository-root `.env` (see `devils_advocate/ai.env.example`): `GEMINI_API_KEY`, `AI_MODEL`,
`AI_ENABLED=true`, `AI_THINKING_LEVEL`. No Anthropic key is used anywhere. In recorded/offline mode
no paid call is ever made.

## Deploying to Vercel

The repo is a two-service Vercel project (`vercel.json`): the Next.js workbench in `frontend/` and a
Python API service, with `/api/*` routed to the API. **Current limitation:** the API service points
at the Target Scout Flask app in `backend/`, which works as a Vercel Function. The workbench's
challenge, experiment and decision pages need `devils_advocate.server`, which runs a background
worker and SQLite and therefore needs a long-lived host (Railway, Render, Fly). Until that is
deployed and `/api/*` is rewritten to it, only the discovery page works on Vercel.

- **Only the `prod` branch deploys.** `git.deploymentEnabled` allows `prod` and blocks every other
  branch (`**` also covers names with slashes such as `feat/x`). In the Vercel dashboard set
  *Settings → Git → Production Branch* to `prod`, otherwise pushes to `prod` become previews.
- Set the framework preset to **Services** (dashboard, or `vercel project update --framework services`).
- Environment variables: `GEMINI_API_KEY`, `AI_MODEL`, `AI_ENABLED` (optional, for rationales). Leave `SCOUT_CACHE_ONLY`
  unset so every disease runs live.
- Vercel Functions can only write to `/tmp`. When `VERCEL=1` the HTTP cache, approval log and
  shortlist log go to `/tmp/target-scout/`. That storage is per-instance and is wiped when an
  instance is recycled, so on Vercel the audit logs are **ephemeral** and a scout run can expire if
  the Approve click lands on a different instance (the page then asks you to re-run the scout).
- An uncached live scout of 25 targets takes about 25 s and a new screening about 12 s, well under
  Vercel's function time limit. Parkinson disease is instant because its responses ship in
  `backend/data/demo_cache/`. Repeat runs on a warm instance are instant too.

## API

All JSON. Errors are `{"error": "..."}` with 404 (unknown disease / run / approval), 400 (bad input,
score mismatch) or 502 (upstream API failure).

| Method | Path             | Body                                  | Returns |
|--------|------------------|---------------------------------------|---------|
| GET    | /api/health      |                                       | `{status}` |
| POST   | /api/scout       | `{disease, n?}`                       | run_id, disease, cache_only, default_weights, targets[] with components |
| POST   | /api/rationale   | `{run_id, weights}`                   | `{rationales: [{symbol, rationale, evidence_strength}]}` or `{available: false}` |
| GET    | /api/approvals   |                                       | approvals, newest first |
| POST   | /api/approvals   | `{run_id, symbol, weights, scores, reason}` | the stored approval |
| POST   | /api/screen      | `{approval_ts}`                       | approval, structure, compounds[] |
| POST   | /api/shortlists  | `{approval_ts, chembl_ids, reason}`   | `{ok: true}` |

## Data sources and caching

Open Targets GraphQL, Europe PMC REST, ChEMBL REST, AlphaFold DB. Every call goes through one cached
HTTP client (`backend/pipeline/http.py`): responses land in `backend/cache/` (7-day TTL) and the
committed snapshot `backend/data/demo_cache/` is read as a fallback. `SCOUT_CACHE_ONLY=1` disables
the network entirely. The committed snapshot covers Parkinson disease (top 25) for stage 1 and
LRRK2 only for stage 2, so in cache-only mode screening any other approval returns a 502.

Refresh the snapshot (live network, ~2 minutes):
```bash
cd backend && python scripts/record_demo.py                 # Parkinson disease, top 25
python scripts/record_demo.py --rationale                   # also cache the LLM rationale (needs a key)
```

Open Targets renames GraphQL fields occasionally. If you see `Open Targets error: Cannot query field
...`, paste the query from `backend/pipeline/clients/opentargets.py` into
https://api.platform.opentargets.org/api/v4/graphql/browser to find the new name. As of 2026-11-07
expression lives under `baselineExpression(page:{...})`, not `expressions`.
