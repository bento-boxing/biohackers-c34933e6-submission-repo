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
and a candidate pool of ChEMBL compounds (pChEMBL ≥ 6, retrieved strongest-first with the coverage
cutoff reported) ranked by a documented, heuristic four-factor rubric: potency (median of comparable
exact binding measurements, never the lone maximum), drug-likeness (QED, Lipinski), clinical stage
qualified by indication, and observed off-target evidence for the shortlist. Missing factors are listed,
not scored as zero; the potency-only baseline ranking is kept for comparison. The candidates have their
own page (05 / Compound candidates), unlocked by the approval, where each row shows the 2-D structure ChEMBL
renders for the molecule; clicking it opens the ChEMBL compound report card. See
`backend/devils_advocate/MOLECULE_RANKING_VALIDATION.md`. A second checkpoint writes a shortlist to
`backend/runs/shortlists.jsonl`.

## Repository layout

```
frontend/                   Next.js 16 research workbench (the only UI): discovery → challenge → experiment → decision → compound candidates
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
`AI_ENABLED=true`, `AI_THINKING_LEVEL`. No Anthropic key is used anywhere. The UI opens in Live APIs
mode; the recorded demo is selected from the Data source dropdown. In recorded/offline mode
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
- **Adaptive evidence discovery.** After the initial retrieval the challenger builds an evidence
  plan (association, genetic/mechanistic, approved therapy, positive clinical, negative/safety,
  programme status, population, recent developments), assesses each need against what was
  retrieved and runs targeted follow-up searches for open needs only: `ADAPTIVE_MAX_ROUNDS`
  (default 2), `ADAPTIVE_MAX_SEARCHES_PER_ROUND` (6), `ADAPTIVE_RECENT_YEARS` (3),
  `AI_MAX_MATERIAL_EXTRA` (6 planner-flagged records admitted beyond the packet cutoff).
  `AI_PLANNING_CALL=true` allows one extra Gemini call that proposes search terms only (off by
  default; counts against `AI_MAX_CALLS`). The UI's *Refresh public sources* checkbox bypasses
  caches for one request. See `backend/devils_advocate/ADAPTIVE_EVIDENCE_VALIDATION.md`.
- **Time budget.** Vercel's default function limit is 300 s (Hobby and Pro). Live retrieval is
  capped at `RESEARCH_RETRIEVAL_BUDGET_SECONDS` (default 240 s, or 150 s when Gemini reasoning is
  authorized). The whole request has a deadline of `RESEARCH_REQUEST_BUDGET_SECONDS` (default 280):
  each Gemini call is clamped to the time left (and refused with under 15 s left) so the function
  is never killed mid-call. Registry full records are fetched 50 per request with up to four
  parallel workers; when the budget still runs short, stopped trials are verified first and the
  rest are labelled "not verified" instead of failing. Verified public responses are cached in a
  per-instance SQLite file (`/tmp` on Vercel), so a retry of the same target is much faster.
  Measured retrieval only: EGFR / NSCLC (633 trials, the worst case we found) 134 s, CCR5 / HIV
  90 s, LRRK2 under 20 s; Gemini adds roughly 140 s for five calls. An uncached 25-target scout takes about 25 s, a screening about 12 s. Parkinson
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
| POST   | /api/screen      | `{approval_id, rubric?}` (Scout app) · `{approval, approval_id, disease_id, target_id, rubric?}` signed (workbench) | approval, structure, compounds[] (four factors, rank, baseline_rank, rank_reason), coverage, rubric, baseline, notes |
| POST   | /api/shortlists  | `{approval_id, chembl_ids, reason}`   | `{ok: true}` (Scout app only) |
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
