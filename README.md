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
Safety flags are shown, never scored. An optional LLM rationale (Claude) is written from the fetched
evidence only, on an explicit button, and is cached per weight setting.

**Human checkpoint.** Approving a target records who, when, why, the weights and the scores shown to
`backend/runs/approvals.jsonl`. The server recomputes the scores and rejects a mismatch.

**Stage 2 · Protein Screening.** For an approved target: the AlphaFold structure (mean pLDDT, links)
and the 50 most potent ChEMBL compounds (pChEMBL ≥ 6, i.e. ≤ 1 µM) with phase, Lipinski data and
approved-drug flags. A second checkpoint writes a shortlist to `backend/runs/shortlists.jsonl`.

## Getting started

### Backend (Flask)
```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
pytest                          # 58 tests, fully offline
python app.py                   # live data, http://localhost:5000
```

For the offline demo (no network needed, instant):
```bash
SCOUT_CACHE_ONLY=1 python app.py
```

Optional LLM rationale: set `ANTHROPIC_API_KEY` (or put it in `backend/.env`). Without it the button
reports "LLM rationale off".

### Frontend (Next.js)
```bash
npm install
npm test                        # vitest: client-side scoring
npm run dev                     # http://localhost:3000, proxies /api/* to Flask on :5000
```

### One-shot demo
```bash
bash scripts/demo.sh            # runs both test suites, then both servers (cache-only)
```

### Command line
```bash
cd backend && source venv/bin/activate
python -m pipeline.cli scout "Parkinson disease"          # live
python -m pipeline.cli scout "Parkinson disease" --cache-only
python -m pipeline.cli screen --latest                     # newest approval
```

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
the network entirely.

Refresh the snapshot (live network, ~2 minutes):
```bash
cd backend && python scripts/record_demo.py                 # Parkinson disease, top 25
python scripts/record_demo.py --rationale                   # also cache the LLM rationale (needs a key)
```

Open Targets renames GraphQL fields occasionally. If you see `Open Targets error: Cannot query field
...`, paste the query from `backend/pipeline/clients/opentargets.py` into
https://api.platform.opentargets.org/api/v4/graphql/browser to find the new name. As of 2026-11-07
expression lives under `baselineExpression(page:{...})`, not `expressions`.
