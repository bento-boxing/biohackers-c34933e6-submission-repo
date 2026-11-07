# Target Scout + Protein Screening pipeline: design

Date: 2026-11-07
Status: draft for review
Context: Agentverse 2026 hackathon submission (team uncle-bao-bao-fans)

## 1. Intent

A scientist types a disease name. The system pulls public evidence, ranks
candidate drug targets with a formula the scientist can see and adjust, and
explains each ranking using only the evidence it fetched. The scientist
approves one target with a written reason. That approval is logged and
hands off to a second stage that screens known compounds and fetches the
protein structure for the approved target.

The point is not "an AI picked a target". The point is: every number on
screen traces back to a database record, the weighting is the human's
choice, and nothing moves to the next stage without a human signature.

## 2. Goals, non-goals, anti-goals

Goals
- End-to-end demo in under two minutes: disease name -> ranked targets ->
  approve -> compound list and structure for the approved target.
- Every score decomposes into named components with visible weights.
- Every evidence claim links to its source (Open Targets page, PubMed ID,
  ChEMBL ID, AlphaFold entry).
- Human checkpoint between stages, with reason captured and persisted.
- Works offline from cached data so the live demo cannot be killed by a
  flaky API.

Non-goals
- Novel science. We rank public evidence; we do not predict new biology.
- Docking, molecular dynamics, or any compute-heavy chemistry.
- Multi-user accounts, auth, deployment. It runs on a laptop.
- A free-form chat agent that decides its own tool calls. The pipeline is
  deterministic code; the LLM only writes explanations.

Anti-goals (would make this a failure even if it "works")
- The LLM inventing evidence. Rationale must cite only fetched data and
  must say when evidence is thin.
- A hidden scoring step the judges cannot inspect.
- A demo that hangs on a network call.

## 3. Constraints

- Repo skeleton already committed (commit 9160737): Next.js 16.4.5 + React 19
  + Tailwind 4 + TypeScript at the repo root, Flask 3 under `backend/`, and
  `next.config.ts` rewrites `/api/*` to `http://localhost:5000/api/*`. The
  pipeline must fit this: Python 3.11+ under `backend/`, UI in the Next.js
  App Router. `AGENTS.md` warns this Next.js differs from training data:
  read `node_modules/next/dist/docs/` before writing any frontend code.
- Python deps: `flask`, `flask-cors`, `python-dotenv` (present), plus
  `requests`, `anthropic`, `pytest`. No heavy chemistry deps required;
  RDKit and py3Dmol-equivalent viewers are optional extras.
- Public APIs only, no keys needed except the optional Anthropic key:
  - Open Targets GraphQL v4: `https://api.platform.opentargets.org/api/v4/graphql`
  - Europe PMC REST: `https://www.ebi.ac.uk/europepmc/webservices/rest/search`
  - ChEMBL REST: `https://www.ebi.ac.uk/chembl/api/data/`
  - AlphaFold DB: `https://alphafold.ebi.ac.uk/api/prediction/{uniprot}`
- Verified on 2026-11-07 against the live Open Targets schema:
  - `search(queryString, entityNames:["disease"])` returns `hits{id name}`.
  - `disease(efoId).associatedTargets.rows` has `score`, `datatypeScores{id score}`,
    `datasourceScores`, and `target{id approvedSymbol approvedName tractability{label modality value} proteinIds{id source} safetyLiabilities{...} baselineExpression{count rows{...}}}`.
  - There is NO `expressions` field on `Target` any more. Baseline expression is
    `baselineExpression(page:{index:0,size:2000}).rows[]` with `datasourceId`
    (`gtex`, `tabula_sapiens`, `PRIDE`), `unit`, `median`,
    `tissueBiosampleFromSource` (GTEx labels such as "Liver", "Kidney - Cortex",
    "Heart - Left Ventricle"). Without the `page` argument only ~25 rows come
    back and the GTEx rows are missing. Any code that uses `expressions` will fail.
  - `datatypeScores.id` values seen: `genetic_association`, `genetic_literature`,
    `literature`, `affected_pathway`, `animal_model`, `known_drug`, `somatic_mutation`.
- Europe PMC `hitCount` and `resultList.result[].pmid` are available with
  `format=json&resultType=lite`.
- ChEMBL target resolution: use the UniProt Swiss-Prot accession from Open
  Targets `proteinIds` (source `uniprot_swissprot`) and query
  `target.json?target_components__accession=<acc>&target_type=SINGLE%20PROTEIN`.
  Fall back to `target/search.json?q=<symbol>` filtered to
  `organism == "Homo sapiens"` and `target_type == "SINGLE PROTEIN"` only when
  no accession is present. If neither yields a target, `chembl_target_id` is
  null and `chembl_norm` is 0; stage 2 still shows the structure with an
  empty compound table. (Symbol search is ambiguous for short symbols such
  as APP, TH, PRKN.)
  `activity.json?target_chembl_id=...&pchembl_value__gte=6&limit=1` returns
  `page_meta.total_count`, which is the potent-activity count (pChEMBL 6 ==
  1 µM) in a single request; LRRK2 gives 5099. Stage 2 pages the same endpoint
  with `limit=1000&only=molecule_chembl_id,pchembl_value,assay_type,standard_type`,
  capped at 5 pages. `molecule.json?molecule_chembl_id__in=A,B,...&only=...`
  batches molecule lookups; `max_phase` is a STRING such as `"4.0"` (approved)
  or null, and `molecule_properties` holds `full_mwt`, `alogp`, `hbd`, `hba`,
  `psa`, `num_ro5_violations` (numbers as strings).
- All external calls go through one HTTP helper with timeouts, retry on 5xx,
  and a disk cache. Tests never hit the network.

## 4. Architecture

Two stages, one shared data layer behind a Flask JSON API, one Next.js UI.

```
 disease name
     |
     v
+-----------------------------+      approval record       +------------------------------+
|  Stage 1: Target Scout      | ------------------------>  |  Stage 2: Protein Screening  |
|  - resolve disease (OT)     |   runs/approvals.jsonl     |  - ChEMBL potent compounds   |
|  - top N targets (OT)       |                            |  - approved-drug flags       |
|  - literature count (EPMC)  |                            |  - AlphaFold structure+pLDDT |
|  - ChEMBL potent count      |                            |  - optional RDKit filters    |
|  - safety flags (OT)        |                            |  - second human checkpoint   |
|  - weighted score           |                            +------------------------------+
|  - LLM rationale (optional) |
+-----------------------------+
              ^
              |  all HTTP via clients/ with disk cache (backend/cache/*.json)

 Next.js (app/)  --fetch /api/*-->  Flask (backend/app.py)  -->  pipeline/
```

### 4.1 Package layout

```
backend/
 app.py             # Flask: routes below, calls pipeline.*; in-memory run store
 requirements.txt
 pipeline/
  __init__.py
  http.py            # get/post with timeout, retry, disk cache, cache-only mode
  models.py          # dataclasses: Disease, TargetEvidence, ScoredTarget, Weights,
                     #              Approval, Compound, Structure, ScreeningResult
  clients/
    opentargets.py   # resolve_disease, associated_targets, target_safety
    europepmc.py     # literature_hits(symbol, disease) -> (count, [pmids])
    chembl.py        # find_target(symbol) -> chembl_id; potent_activities(id)
                     # molecule_phase(chembl_id)
    alphafold.py     # prediction(uniprot) -> Structure
  scout/
    pipeline.py      # run_scout(disease_name, n=25, weights) -> ScoutResult
    scoring.py       # pure functions: component scores + weighted total
    rationale.py     # LLM explanation; returns None if no key
  screening/
    pipeline.py      # run_screening(approval) -> ScreeningResult
    ranking.py       # pure: rank compounds by potency, flag approved drugs
  audit.py           # append Approval to runs/approvals.jsonl
  cli.py             # python -m pipeline.cli scout "Parkinson disease"
 tests/              # pytest, offline against data/demo_cache
 data/demo_cache/    # committed response snapshot
 cache/              # gitignored runtime cache
 runs/               # gitignored approvals.jsonl, shortlists.jsonl
app/
  page.tsx           # Scout page
  screening/page.tsx # Screening page
  components/        # WeightSliders, TargetTable, ApprovalForm, CompoundTable, StructureCard
lib/
  api.ts             # typed fetch wrappers for /api/*
  score.ts           # pure: normalise weights, total from components
  types.ts           # TS mirrors of the JSON shapes below
```

Pure logic (scoring, ranking) has no I/O and is unit tested directly.
Clients are tested against the recorded snapshot by pointing the HTTP
helper at `data/demo_cache` in cache-only mode.

### 4.1a Flask API (the contract between backend and frontend)

All responses are JSON; errors are `{"error": "<message>"}` with 404 for
unknown disease or run, 400 for bad input, 502 for upstream API failures.

| Method | Path                | Body                                   | Returns |
|--------|---------------------|----------------------------------------|---------|
| GET    | /api/health         |                                        | `{status}` |
| POST   | /api/scout          | `{disease: str, n?: int}`              | `ScoutRun` |
| POST   | /api/rationale      | `{run_id, weights}`                    | `{run_id, weights, rationales: [{symbol, rationale, evidence_strength}]}` or `{available: false, reason}` |
| GET    | /api/approvals      |                                        | `Approval[]` newest first |
| POST   | /api/approvals      | `{run_id, symbol, weights, reason}`    | `Approval` |
| POST   | /api/screen         | `{approval_ts}`                        | `ScreeningResult` |
| POST   | /api/shortlists     | `{approval_ts, chembl_ids, reason}`    | `{ok: true}` |

`ScoutRun` = `{run_id, disease: {id, name}, cache_only: bool, default_weights,
targets: [{target_id, symbol, name, uniprot, chembl_target_id, components:
{genetic, association, druggability, literature}, potent_count,
has_approved_drug, literature_hits, pmids, safety_flags: [{kind, detail}],
tractability_sm_labels: [str], open_targets_url}]}`. Targets are returned in
default-weight order; the browser computes totals and re-sorts from the
four components, so slider moves never hit the server. `lib/score.ts` and
`pipeline/scout/scoring.py` implement the same formula and a test on each
side pins the same hand-computed example.

The server keeps `ScoutRun`s in a dict keyed by `run_id` (uuid4) for the
process lifetime; a restart means re-running scout, which is acceptable for
a laptop demo.

### 4.2 Stage 1: Target Scout

Input: disease name string, N (default 25), Weights.

Steps
1. `resolve_disease`: Open Targets `search`, take the first hit whose entity
   is `disease`. Show the chosen ID and name in the UI so a wrong match is
   visible.
2. `associated_targets`: one GraphQL query for the top N by overall score,
   fetching `score`, `datatypeScores`, `target{id approvedSymbol approvedName
   tractability proteinIds}`.
3. For each target, in a thread pool (max 8 workers, each call cached):
   - Europe PMC: query `"<SYMBOL>" AND "<disease name>"`, keep `hitCount` and
     the first 3 PMIDs.
   - ChEMBL: resolve human single-protein target, read the potent-activity
     count from `page_meta.total_count` (one request). "Has approved drug" is
     taken from Open Targets tractability (`Approved Drug`, modality SM, value
     true), not from ChEMBL, so stage 1 stays at one ChEMBL call per target.
   - Open Targets safety: `safetyLiabilities` list (event, effects,
     biosamples) and `baselineExpression` rows where `datasourceId == "gtex"`,
     restricted to rows whose `tissueBiosampleFromSource` contains heart,
     liver or kidney (case-insensitive). Flag "high expression" when median
     TPM >= 50 (builder may tune).
4. `scoring.score_target`: see 4.3.
5. Sort by total score. Return `ScoutResult{disease, weights, targets[]}`.
6. Optional: `rationale.explain(scout_result)` produces one 2-3 sentence
   rationale per target in the top 10. It runs only when the user clicks
   "Explain ranking", never automatically on slider change. The result is
   cached under a key of (disease_id, normalised weights, top-10 symbols) and
   the column header states the weights it was generated with. Moving a
   slider clears the column until the button is clicked again, so a
   rationale never cites numbers that are no longer on screen. The demo
   snapshot includes the rationale for the default weights.

### 4.3 Scoring (the checkable formula)

Four components, each in [0, 1]:

| Component    | Source                                                                 |
|--------------|------------------------------------------------------------------------|
| genetic      | `datatypeScores` where id == `genetic_association` (0 if absent)       |
| association  | overall `score` from Open Targets                                      |
| druggability | 0.5 * tractability_sm + 0.5 * chembl_norm                              |
| literature   | log10(hits + 1) / log10(max_hits_in_set + 1)                           |

- `tractability_sm`: 1.0 if any SM (small molecule) tractability label with
  value true among {Approved Drug, Advanced Clinical, Phase 1 Clinical}, else
  0.7 if {Structure with Ligand, High-Quality Ligand}, else 0.4 if
  {High-Quality Pocket, Med-Quality Pocket, Druggable Family}, else 0.
- `chembl_norm`: log10(potent_count + 1) / log10(max_potent_in_set + 1)
  (0 when max is 0).

Total = w_gen * genetic + w_assoc * association + w_drug * druggability +
w_lit * literature, with weights normalised to sum to 1 before use.
Default weights 0.4 / 0.3 / 0.2 / 0.1.

Safety flags do not change the score. They are shown as a warning column so
the human sees them and decides. (Design call: silently penalising would
hide a judgement from the reviewer, which is the anti-goal.)

The UI shows the four component values and the weights next to every
total, and recomputes on slider change without re-fetching.

### 4.4 LLM rationale

- Model `claude-opus-5-5`, adaptive thinking (omit `thinking` or pass
  `{type: "adaptive"}`), `output_config.effort: "low"`, server-side
  `fallbacks: "default"` with beta `server-side-fallback-2026-07-01`.
- One call for the top 10, structured output (`output_config.format`) with a
  JSON schema: `[{symbol, rationale, evidence_strength: "strong"|"moderate"|"weak"}]`.
- The user message contains ONLY the fetched evidence serialised as JSON
  (components, counts, PMIDs, safety flags, tractability labels). System
  prompt: write for a drug discovery scientist; cite only the provided
  numbers and IDs; if evidence is weak say so; never add facts not in the
  input.
- If `ANTHROPIC_API_KEY` is unset (and `ant auth status` has no profile) the
  rationale column reads "LLM rationale off (no API key)". The pipeline is
  fully functional without it.
- Check `stop_reason == "refusal"` before reading content; on refusal show
  "rationale unavailable" rather than crashing.

### 4.5 Human checkpoint and audit

The Scout page has a target selector plus a reason box. Submitting posts to
`/api/approvals`, which writes one line to `backend/runs/approvals.jsonl`:

```json
{"ts": "2026-11-07T18:02:11Z", "disease_id": "MONDO_0005180",
 "disease_name": "Parkinson disease", "target_id": "ENSG00000188906",
 "symbol": "LRRK2", "uniprot": "Q5S007", "chembl_target_id": "CHEMBL1075104",
 "weights": {"genetic":0.4,"association":0.3,"druggability":0.2,"literature":0.1},
 "scores": {"genetic":0.93,"association":0.88,"druggability":0.85,"literature":1.0,"total":0.90},
 "safety_flags": [], "reason": "Strong genetics, kinase, many tool compounds.",
 "approved_by": "ella"}
```

`approved_by` comes from an env var `SCOUT_USER` or defaults to the OS
username. `scores` are the totals the browser showed at approval time, so
the server recomputes them from the posted weights and the stored components
and rejects the request (400) if they do not match to 3 dp. The Screening
page lists approvals from this file and runs on the selected one. This file
is the contract between the two stages.

### 4.6 Stage 2: Protein Screening

Input: one Approval.

Steps
1. ChEMBL: fetch activities for `chembl_target_id` with `pchembl_value >= 6`
   (same cached call as stage 1, so it is instant for the approved target).
   Group by `molecule_chembl_id`; take best (max) pChEMBL per molecule and
   the assay type.
2. For the top 50 molecules by pChEMBL, fetch `molecule/{id}.json` for
   `max_phase`, `pref_name`, `molecule_properties` (MW, ALogP, HBD, HBA,
   PSA, `num_ro5_violations`). Flag `max_phase == 4` as repurposing
   candidates.
3. Rank: pChEMBL descending, tie-break by fewer Ro5 violations. Lipinski
   pass/fail uses ChEMBL's `num_ro5_violations <= 1`. RDKit is not required
   for this; if installed, add a PAINS flag (optional extra).
4. AlphaFold: `prediction/{uniprot}` -> model URL (`pdbUrl`/`cifUrl`),
   `globalMetricValue` (mean pLDDT), `fractionPlddtConfident`. Show as a
   confidence line and a download link. If `py3Dmol` is installed, render
   the structure inline; otherwise show the link only.
5. Second checkpoint: "Shortlist" with reason, appended to
   `backend/runs/shortlists.jsonl` with the chosen molecule IDs.

### 4.7 Caching and demo mode

- `pipeline/http.py` hashes (method, url, params, body) to a filename under
  `cache/`. Reads before network; writes after success. TTL 7 days by
  default; `SCOUT_CACHE_ONLY=1` disables network entirely and raises a clear
  error on a miss.
- A committed snapshot `backend/data/demo_cache/` holds every response for
  "Parkinson disease" top 25 so the demo runs with no network.
  `python scripts/record_demo.py` regenerates it.

### 4.8 UI (Next.js App Router, Tailwind)

Page `/` (Target Scout):
- Form: disease text input (default "Parkinson disease"), N (5–50, default
  25), Run button. While running, a progress line; on 404 an inline error.
- Sidebar card: four range inputs 0–1 step 0.05 with spec defaults, showing
  the normalised weight next to each; a "Reset" link.
- Status line: resolved disease ID and name, and a "cache-only" badge when
  the server reports it.
- Ranked table: rank, symbol, name, total, four components, potent
  compounds, approved drug, papers (hit count, 3 PMID links), safety flags,
  rationale, link to Open Targets. Totals re-sort instantly on slider
  change (client-side).
- Row expand: tractability labels, safety details, PMID list.
- "Explain ranking (LLM)" button posts current weights; rationale column is
  blanked whenever weights change after the last explain.
- Approval form: target select, reason textarea, "Approve and send to
  protein screening" button; success toast names the symbol.

Page `/screening` (Protein Screening):
- Select over approvals (symbol, disease, timestamp, approver).
- Structure card: AlphaFold ID, mean pLDDT, confident fraction, link to the
  AlphaFold entry. An embedded 3D viewer is an optional extra.
- Compound table: rank, ChEMBL ID, name, best pChEMBL, assay type, max
  phase, approved badge, MW, ALogP, Ro5 violations, Lipinski, ChEMBL link.
- Checkbox column + reason + "Shortlist" button.

Layout, colours and component structure are left to the builder, within
Tailwind and the existing `app/layout.tsx` fonts.

## 5. Testing

- Unit: `scoring.py` and `ranking.py` with hand-built inputs (weights
  normalisation, missing datatype, log scaling, capped counts, ties).
- Client parsing: each client against a recorded fixture; asserts the
  mapped dataclass fields. Fixtures recorded once with a `record_fixtures.py`
  script.
- API: Flask test client against the demo snapshot: `/api/scout` returns
  25 targets and a `run_id`; `/api/approvals` round-trips; `/api/screen`
  returns compounds for LRRK2; mismatched scores give 400.
- Frontend: `lib/score.ts` unit-tested with vitest on the same hand example
  as the Python scoring test. No end-to-end browser tests.
- Integration: `run_scout("Parkinson disease")` in cache-only mode against
  the demo snapshot returns 25 rows, every component in [0, 1], totals sorted
  descending, and LRRK2 present in the top 5. No other rank assertions: the
  formula is not tuned to produce a predetermined answer. If LRRK2 drops out
  of the top 5 under default weights, report it rather than tune.
- No test touches the network. `pytest` must pass offline.

## 6. Delivery order

1. Data layer: `http.py` with cache, `models.py`, Open Targets client,
   `scoring.py`, CLI printing a ranked table. First network run on day 1.
2. Europe PMC and ChEMBL clients, safety flags, demo snapshot, tests.
3. Flask API for scout and approvals; Next.js Scout page with sliders and
   approval form.
4. LLM rationale (API + button).
5. Screening stage: ChEMBL ranking, AlphaFold, API, Screening page,
   shortlist log.
6. Polish: README, demo script, optional 3D viewer / RDKit extras.

Each step leaves a runnable program.

## 7. Left to the builder

- Exact thresholds (expression TPM cutoff, potent-count cap) within the
  stated defaults.
- Page layout, colours, column order, component split.
- Thread pool size and retry/backoff numbers.
- Whether the frontend caches runs in `sessionStorage`.

## 8. Design calls made without the user (check these)

- Next.js + Flask, because that is the skeleton the team committed. The
  earlier Streamlit draft is not reused; this is a clean build.
- Slider re-weighting is computed in the browser from server-supplied
  components; the server verifies posted totals on approval.
- Scout runs live in server memory keyed by run_id, not in a database.
- Rationale is generated on an explicit button, keyed to the current
  weights (see 4.2 step 6).
- ChEMBL targets are resolved by UniProt accession, not symbol search.
- The pipeline is plain Python behind `run_scout` / `run_screening`
  functions so a hackathon-required agent wrapper (for example a Fetch.ai
  uAgent or chat-protocol handler) can be added as a thin layer without
  touching the pipeline. Whether such a wrapper is required is an open
  question for the user (see 9).
- Safety flags are shown, not scored.
- Druggability blends Open Targets tractability (prediction) with ChEMBL
  potent-compound count (experiment) 50/50.
- The LLM is explanation-only; it does not choose tools or rank.
- Approvals are a JSONL file, not a database.
- Stage 2 scope is "rank known ChEMBL compounds + structure", not docking.
- Default model `claude-opus-5-5` at low effort for cost; fallbacks on.

## 9. Open question for the user

- What does the Agentverse 2026 brief actually require of the submission
  (hosted agent, specific agent framework, demo video vs judges running the
  code, deadline)? The architecture keeps the pipeline framework-agnostic,
  but a required agent wrapper or hosted demo would add a delivery step and
  may change whether stage 2 is in scope.

