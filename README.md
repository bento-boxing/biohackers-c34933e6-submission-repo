# Target Scout

Evidence-ranked drug targets with a human checkpoint, then compound screening for the approved target.
A **Next.js + Flask** monorepo built for Agentverse 2026.

```
/frontend           ← Next.js 16 research workbench (TypeScript + Tailwind)
/backend            ← Flask API: Target Scout pipeline + Target Challenger (backend/devils_advocate/)
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
frontend/                   Next.js 16 research workbench (the only UI): discovery → challenge → experiment → decision
backend/app.py              The one Flask app (local :5050 and the Vercel Function): stateless workbench server
backend/pipeline/           Target Scout: evidence retrieval, transparent ranking, approvals, screening
backend/devils_advocate/    Target Challenger: evidence pipeline, Gemini reasoning, experiment designer, server.py
scripts/                    demo.sh (bash) and Windows .cmd launchers
```

## Getting started

### Backend
```bash
cd backend
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m pytest tests devils_advocate/tests -q      # Scout + Challenger + workbench tests, offline
python -m devils_advocate.server --port 5050         # the server the UI talks to (same app as app.py)
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
repository-root `.env` (see `backend/devils_advocate/ai.env.example`): `GEMINI_API_KEY`, `AI_MODEL`,
`AI_ENABLED=true`, `AI_THINKING_LEVEL`. No Anthropic key is used anywhere. In recorded/offline mode
no paid call is ever made.

## Deploying to Vercel

The whole workbench runs on Vercel alone (`vercel.json`, framework preset **Services**): the Next.js
app in `frontend/` and a Python Function built from `backend/` (`app:app`), with `/api/*` routed to
the Function. There is no database, queue or second host.

**How it stays stateless.** Vercel Functions keep nothing between requests, so the server holds no
state: an investigation runs to completion inside one request and returns the finished report; the
browser keeps the scout run, report and decisions in `localStorage`; a screening request carries the
HMAC-signed approval object the server issued. Audit logs written under `/tmp` are best-effort only.
The downloadable research report is the durable record.

- **Only the `prod` branch deploys.** `git.deploymentEnabled` allows `prod` and blocks every other
  branch (`**` also covers names with slashes such as `feat/x`). In the Vercel dashboard set
  *Settings → Git → Production Branch* to `prod`, otherwise pushes to `prod` become previews.
- **Environment variables** (Project Settings → Environment Variables):
  `WORKBENCH_SECRET` (any long random string; signs approvals so all instances agree),
  `GEMINI_API_KEY`, `AI_MODEL`, `AI_ENABLED=true`, `AI_THINKING_LEVEL` (optional, for Gemini
  rationale and challenger reasoning). Leave `SCOUT_CACHE_ONLY` unset so every disease runs live.
  Browser origins: the deployment's own `VERCEL_URL` / production URL are allowed automatically;
  add custom domains to `WORKBENCH_ORIGINS` (comma-separated).
- **Time budget.** Vercel's default function limit is 300 s (Hobby and Pro). Live retrieval is
  capped at `RESEARCH_RETRIEVAL_BUDGET_SECONDS` (default 240 s, or 150 s when Gemini reasoning is
  authorized). The whole request has a deadline of `RESEARCH_REQUEST_BUDGET_SECONDS` (default 280):
  each Gemini call is clamped to the time left and no new paid call starts within 5 s of it. When the budget runs short, the challenger verifies the full
  registry record of stopped trials first and labels the rest "not verified" instead of failing;
  only if even the searches cannot finish does the investigation fail with an explicit message.
  Measured: EGFR / NSCLC (501 trials, the worst case we found) completes in about 215 s; LRRK2 in
  under a minute. An uncached 25-target scout takes about 25 s, a screening about 12 s. Parkinson
  disease / LRRK2 are instant from the recorded snapshot.
- **Payload sizes.** Reports never travel back to the server: the investigation response carries a
  signed digest (`report_sig`) and each scout target a signed `sig`, and the decision request posts
  only those tokens. Trial outcome tables and eligibility text are dropped from responses (the UI
  never renders them), which brings the worst live case (EGFR, 501 trials) from 7.0 MB to about
  1.5 MB, under Vercel's 4.5 MB response limit. Request bodies are capped at 1 MB; a 25-target
  scout run with evidence is about 130 KB.
- **`WORKBENCH_SECRET` is required on Vercel.** Without it each instance would sign with its own
  random key and screening would fail at random, so the server refuses to issue approvals (503 with
  an explicit message) when `VERCEL=1` and the secret is unset.

## API

All JSON. Errors are `{"error": "..."}` with 404 (unknown disease / run / approval), 400 (bad input,
score mismatch) or 502 (upstream API failure).

| Method | Path             | Body                                  | Returns |
|--------|------------------|---------------------------------------|---------|
| GET    | /api/health      |                                       | `{status}` |
| GET    | /api/diseases    | `?q=partial name`                     | `{query, diseases: [{id, name}]}` from Open Targets search (recorded list offline) |
| POST   | /api/scout       | `{disease, n?}`                       | run_id, disease, cache_only, default_weights, targets[] with components |
| POST   | /api/rationale   | `{run_id, run?, weights}`             | `{rationales: [{symbol, rationale, evidence_strength}]}` or `{available: false}` |
| GET    | /api/approvals   |                                       | approvals, newest first |
| POST   | /api/approvals   | `{run_id, symbol, weights, scores, reason}` | the stored approval |
| POST   | /api/screen      | `{approval_ts}` (Scout app) · `{approval}` signed (workbench) | approval, structure, compounds[] |
| POST   | /api/shortlists  | `{approval_ts, chembl_ids, reason}`   | `{ok: true}` (Scout app only) |
| POST   | /api/investigations | `{run, symbol}` or `{target_input}`, `use_ai`, `paid_authorized`, `weights` | the finished job: `{job_id, state, result, error, selection, weights, report_sig}` |
| POST   | /api/research-decisions | `{decision_id, job_id, action, rationale, confirmed, report_sig, target_sig?}` | the decision; `approve_screening` adds a signed `approval` |
| GET    | /api/workbench/config | | public AI settings, modes |

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
