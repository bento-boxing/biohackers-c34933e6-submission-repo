# Target Scout + Protein Screening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A laptop-run Next.js + Flask app that ranks drug targets for a disease from public evidence with a visible, adjustable formula, logs a human approval, and screens ChEMBL compounds plus the AlphaFold structure for the approved target.

**Architecture:** Python package `backend/pipeline/` with one cached HTTP helper, thin API clients, pure scoring/ranking functions, and two entry functions `run_scout` and `run_screening`. `backend/app.py` (Flask) exposes them as JSON under `/api/*`; the Next.js app at the repo root renders tables and sliders and recomputes totals client-side in `lib/score.ts`. All backend tests run offline against a committed response snapshot in `backend/data/demo_cache/`.

**Tech Stack:** Python 3.11+, Flask 3, requests, anthropic, pytest; Next.js 16.4.5, React 19, TypeScript 5, Tailwind 4, vitest.

**Spec:** `docs/superpowers/specs/2026-11-07-target-scout-design.md`

## Global Constraints

- Backend lives in `backend/`; all Python paths below are relative to `backend/` unless they start with `app/` or `lib/` (frontend, repo root). Run pytest from `backend/`.
- Python 3.11+; `backend/requirements.txt` adds `requests`, `anthropic`, `pytest` to the existing flask, flask-cors, python-dotenv lines. Optional extras documented, not installed.
- Frontend: existing Next.js 16.4.5 skeleton. Before writing any `.tsx`, read `node_modules/next/dist/docs/` as `AGENTS.md` instructs (run `npm install` first). Add `vitest` as a devDependency for `lib/` tests only.
- Every HTTP call goes through `pipeline.http.HttpClient`; no `requests.get` elsewhere.
- No backend test touches the network: tests construct `HttpClient(read_dirs=[DEMO_CACHE], cache_only=True)`. Flask tests use `app.test_client()` with that same client injected.
- API error shape `{"error": "<message>"}`: 404 unknown disease or run, 400 bad input or score mismatch, 502 upstream failure.
- Endpoints (verbatim): Open Targets `https://api.platform.opentargets.org/api/v4/graphql`; Europe PMC `https://www.ebi.ac.uk/europepmc/webservices/rest/search`; ChEMBL `https://www.ebi.ac.uk/chembl/api/data/`; AlphaFold `https://alphafold.ebi.ac.uk/api/prediction/{uniprot}`.
- Default weights 0.4 / 0.3 / 0.2 / 0.1 (genetic / association / druggability / literature); weights normalised to sum 1 before use.
- Potent compound == `pchembl_value >= 6`. Approved drug == Open Targets tractability label `Approved Drug`, modality `SM`, value true (stage 1) or ChEMBL `max_phase == "4.0"` (stage 2).
- Safety flags never change the score.
- LLM: model `claude-opus-5-5`, `output_config={"effort": "low", "format": {...}}`, `betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"`, no `thinking` param, check `stop_reason == "refusal"`.
- Approval log `backend/runs/approvals.jsonl`; shortlist log `backend/runs/shortlists.jsonl`. `backend/runs/` and `backend/cache/` are gitignored; `backend/data/demo_cache/` is committed.
- Scoring formula is implemented twice (`pipeline/scout/scoring.py`, `lib/score.ts`); both test suites pin the same example: genetic 0.5, association 0.8, druggability 0.6, literature 0.5, default weights → total 0.61.
- Commit after every task with the attribution line `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## Review Focus

1. Disease name with no Open Targets hit (e.g. "asdfgh"): `run_scout` raises `DiseaseNotFound`; `/api/scout` returns 404 with the query in `error`; the page shows it inline. Tests in Tasks 3 and 9.
2. Target with no Swiss-Prot accession or no ChEMBL target: druggability still computes (chembl_norm 0), stage 2 shows structure with an empty compound table. Tests in Tasks 6 and 13.
3. All four sliders at 0: normalisation would divide by zero; `Weights.normalised()` and `normaliseWeights()` both fall back to defaults. Tests in Tasks 4 and 10.
4. Cache-only mode with a missing entry: `CacheMiss` names the URL so the demo operator knows what to snapshot. Test in Task 2.
5. ChEMBL `max_phase` null and property strings null for some molecules: `Compound` fields are `Optional` and ranking treats None Ro5 violations as worst. Test in Task 12.
6. Approval posted with totals that do not match the server's recomputation (tampered or stale client): 400, nothing written. Test in Task 9.

---

### Task 1: Project scaffold

**Files:**
- Create: `backend/pyproject.toml` (pytest config only), `backend/pipeline/__init__.py`, `backend/pipeline/clients/__init__.py`, `backend/pipeline/scout/__init__.py`, `backend/pipeline/screening/__init__.py`, `backend/tests/__init__.py`, `backend/tests/conftest.py`, `backend/data/demo_cache/.gitkeep`
- Modify: `backend/requirements.txt` (append `requests>=2.31`, `anthropic>=1.0`, `pytest>=8`), `.gitignore` (append `backend/cache/`, `backend/runs/`), `package.json` (add devDependency `vitest` and script `"test": "vitest run"`)

**Interfaces:**
- Produces: `backend/tests/conftest.py` defines `DEMO_CACHE = Path(__file__).parent.parent / "data" / "demo_cache"` and a fixture `client` returning `HttpClient(read_dirs=[DEMO_CACHE], cache_only=True)` (import lands in Task 2; write the fixture now).

- [ ] **Step 1: Create the files above.** `pyproject.toml` holds only `[tool.pytest.ini_options] testpaths = ["tests"]`.
- [ ] **Step 2: Verify** in `backend/`: `python -m venv venv && source venv/bin/activate && pip install -r requirements.txt` then `pytest` exits 0 or 5. At repo root: `npm install` completes and `node_modules/next/dist/docs/` exists.
- [ ] **Step 3: Commit** `chore: scaffold pipeline package and test config`

---

### Task 2: Cached HTTP client

**Files:**
- Create: `pipeline/http.py`
- Test: `tests/test_http.py`

**Interfaces:**
- Produces:
  - `class CacheMiss(Exception)` with message `f"cache-only mode and no cached response for {method} {url}"`.
  - `class HttpClient:`
    - `__init__(self, write_dir: Path | None = None, read_dirs: list[Path] = (), cache_only: bool = False, ttl_days: int = 7, timeout: float = 30.0, max_retries: int = 3)`
    - `get_json(self, url: str, params: dict | None = None) -> Any`
    - `post_json(self, url: str, body: dict) -> Any`
    - `cache_key(method: str, url: str, params: dict | None, body: dict | None) -> str` (static; sha256 hex of `json.dumps([method, url, params, body], sort_keys=True)`)
  - `default_client() -> HttpClient`: `write_dir` from env `SCOUT_CACHE_DIR` (default `cache/`), `read_dirs = [write_dir, Path("data/demo_cache")]`, `cache_only = os.environ.get("SCOUT_CACHE_ONLY") == "1"`.
- Cache file format: `<key>.json` containing `{"ts": <unix float>, "method", "url", "params", "body", "data"}`. Read order: `read_dirs` in order, first hit wins; TTL applies only to `write_dir` entries, `read_dirs` beyond it are treated as never expiring.
- Retry on status >= 500 and connection errors with backoff 1s, 2s, 4s; raise `requests.HTTPError` on 4xx without retry.

- [ ] **Step 1: Write failing tests** in `tests/test_http.py` using `tmp_path` and `monkeypatch` on `requests.Session.request`:
  - `test_get_json_writes_cache_then_reads_without_network` (second call with the session patched to raise must return same data).
  - `test_cache_only_miss_raises_cache_miss_with_url` (assert url substring in message).
  - `test_read_dirs_order_first_hit_wins`.
  - `test_expired_write_dir_entry_is_refetched` (write a file with `ts` 8 days old, patch session to return new data, assert new data).
  - `test_retries_on_500_then_succeeds` (patch returns 500, 500, 200; assert 3 calls).
- [ ] **Step 2: Run** `pytest tests/test_http.py -v` → FAIL, `ModuleNotFoundError: pipeline.http`.
- [ ] **Step 3: Implement `pipeline/http.py`** per Interfaces. Use one `requests.Session` per client. Use `time.sleep` for backoff (tests patch it).
- [ ] **Step 4: Run** `pytest tests/test_http.py -v` → PASS.
- [ ] **Step 5: Commit** `feat: cached http client with cache-only mode`

---

### Task 3: Models and Open Targets client

**Files:**
- Create: `pipeline/models.py`, `pipeline/clients/opentargets.py`, `scripts/record_demo.py`
- Test: `tests/test_models.py`, `tests/test_opentargets.py`

**Interfaces:**
- Produces in `pipeline/models.py` (all `@dataclass`, `Weights` frozen):
  - `Weights(genetic=0.4, association=0.3, druggability=0.2, literature=0.1)` with `normalised() -> Weights` and `as_dict() -> dict[str, float]`.
  - `Disease(id: str, name: str)`
  - `SafetyFlag(kind: Literal["liability", "expression"], detail: str)`
  - `TargetEvidence(target_id: str, symbol: str, name: str, uniprot: str | None, ot_score: float, datatype_scores: dict[str, float], tractability: list[dict], has_approved_drug: bool, literature_hits: int = 0, pmids: list[str] = field(default_factory=list), chembl_target_id: str | None = None, potent_count: int = 0, safety_flags: list[SafetyFlag] = field(default_factory=list))`
  - `ComponentScores(genetic: float, association: float, druggability: float, literature: float, total: float)`
  - `ScoredTarget(evidence: TargetEvidence, scores: ComponentScores, rationale: str | None = None, evidence_strength: str | None = None)`
  - `ScoutResult(disease: Disease, weights: Weights, targets: list[ScoredTarget])`
  - `Approval(ts: str, disease_id: str, disease_name: str, target_id: str, symbol: str, uniprot: str | None, chembl_target_id: str | None, weights: dict, scores: dict, safety_flags: list[str], reason: str, approved_by: str)` with `to_json() -> str` and `@classmethod from_json(line: str) -> Approval`.
  - `Compound(chembl_id: str, name: str | None, best_pchembl: float, assay_type: str | None, max_phase: str | None, mw: float | None, alogp: float | None, hbd: int | None, hba: int | None, psa: float | None, ro5_violations: int | None)` with property `is_approved -> bool` (`max_phase == "4.0"`) and `lipinski_pass -> bool | None` (`ro5_violations <= 1`, None if unknown).
  - `Structure(uniprot: str, model_id: str, pdb_url: str, cif_url: str, mean_plddt: float, fraction_confident: float)`
  - `ScreeningResult(approval: Approval, structure: Structure | None, compounds: list[Compound])`
- Produces in `pipeline/clients/opentargets.py`:
  - `OT_URL = "https://api.platform.opentargets.org/api/v4/graphql"`
  - `class DiseaseNotFound(Exception)`
  - `resolve_disease(client: HttpClient, name: str) -> Disease`: query `query($q:String!){ search(queryString:$q, entityNames:["disease"], page:{index:0,size:5}){ hits{ id name entity } } }`; first hit with `entity == "disease"`, else raise `DiseaseNotFound(name)`.
  - `associated_targets(client, disease_id: str, n: int) -> list[TargetEvidence]`: query `query($id:String!,$n:Int!){ disease(efoId:$id){ associatedTargets(page:{index:0,size:$n}){ rows{ score datatypeScores{ id score } target{ id approvedSymbol approvedName tractability{ label modality value } proteinIds{ id source } } } } } }`. `uniprot` = first `proteinIds` entry with `source == "uniprot_swissprot"` else None. `has_approved_drug` per Global Constraints. `datatype_scores` = `{id: score}`.
  - `target_safety(client, target_id: str) -> list[SafetyFlag]`: query `query($id:String!){ target(ensemblId:$id){ safetyLiabilities{ event effects{ direction dosing } biosamples{ tissueLabel } } baselineExpression(page:{index:0,size:2000}){ rows{ datasourceId median tissueBiosampleFromSource } } } }`. One `liability` flag per `safetyLiabilities` entry, detail `f"{event} ({', '.join(tissueLabels)})"`. One `expression` flag per gtex row whose `tissueBiosampleFromSource` lower-cased contains `heart`, `liver` or `kidney` and `median >= EXPRESSION_TPM_THRESHOLD` (module constant, 50.0), detail `f"{tissue}: {median:.0f} TPM"`.
  - `graphql(client, query: str, variables: dict) -> dict` helper that posts `{"query","variables"}` and raises `RuntimeError("Open Targets error: " + first message)` when `errors` is present.
- Produces `scripts/record_demo.py`: runs every client call for "Parkinson disease", N=25, with `HttpClient(write_dir=Path("data/demo_cache"))` so the snapshot is written. Extended in later tasks as clients are added.

- [ ] **Step 1: Write failing tests**
  - `tests/test_models.py`: `test_weights_normalised_sums_to_one`, `test_weights_all_zero_falls_back_to_defaults`, `test_approval_round_trips_json`, `test_compound_is_approved_and_lipinski`.
  - `tests/test_opentargets.py` (uses `client` fixture): `test_resolve_parkinson_returns_mondo_0005180` (assert id `MONDO_0005180`, name `Parkinson disease`), `test_resolve_unknown_raises_disease_not_found` (query `"zzqxv-not-a-disease"`), `test_associated_targets_returns_25_with_lrrk2` (assert 25 rows, one with symbol `LRRK2`, uniprot `Q5S007`, `datatype_scores["genetic_association"] > 0.5`), `test_target_safety_lrrk2_has_no_high_expression_flags` (LRRK2 GTEx heart/liver/kidney medians are all < 10 TPM, so zero `expression` flags).
- [ ] **Step 2: Run** `pytest tests/test_models.py tests/test_opentargets.py -v` → FAIL (import errors).
- [ ] **Step 3: Implement `pipeline/models.py`** per Interfaces.
- [ ] **Step 4: Implement `pipeline/clients/opentargets.py`** per Interfaces.
- [ ] **Step 5: Write `scripts/record_demo.py`** calling `resolve_disease`, `associated_targets(…, 25)`, `target_safety` for each target, and also `resolve_disease` for `"zzqxv-not-a-disease"` (so the not-found test has a cached response). Run it: `python scripts/record_demo.py` (network). Confirm `ls data/demo_cache | wc -l` ≥ 28.
- [ ] **Step 6: Run** `pytest tests/test_models.py tests/test_opentargets.py -v` → PASS.
- [ ] **Step 7: Commit** `feat: models, Open Targets client, demo snapshot recorder` (include `data/demo_cache/*.json`).

---

### Task 4: Scoring

**Files:**
- Create: `pipeline/scout/scoring.py`
- Test: `tests/test_scoring.py`

**Interfaces:**
- Produces:
  - `TRACTABILITY_TIERS: list[tuple[set[str], float]] = [({"Approved Drug","Advanced Clinical","Phase 1 Clinical"}, 1.0), ({"Structure with Ligand","High-Quality Ligand"}, 0.7), ({"High-Quality Pocket","Med-Quality Pocket","Druggable Family"}, 0.4)]`
  - `tractability_sm(tractability: list[dict]) -> float`: highest tier whose label set intersects labels with `modality == "SM"` and `value is True`; else 0.0.
  - `log_norm(value: int, max_value: int) -> float`: `log10(value+1)/log10(max_value+1)`, 0.0 if `max_value == 0`.
  - `component_scores(ev: TargetEvidence, weights: Weights, max_hits: int, max_potent: int) -> ComponentScores` implementing spec 4.3 with `weights.normalised()`.
  - `score_all(evidence: list[TargetEvidence], weights: Weights) -> list[ScoredTarget]`: computes maxes over the set, scores, sorts by `total` descending.

- [ ] **Step 1: Write failing tests**: `test_tractability_sm_tiers` (three label fixtures → 1.0, 0.7, 0.4; AB-only labels → 0.0), `test_log_norm_zero_max`, `test_missing_genetic_datatype_scores_zero`, `test_component_total_with_default_weights` (hand input: genetic 0.5, ot 0.8, tractability tier 0.7, potent 99 of max 999, hits 9 of max 99 → assert each component and total to 3 dp), `test_shared_example_total_0_61` (components 0.5/0.8/0.6/0.5 injected directly into the weighted sum → 0.61; same case as `lib/score.test.ts`), `test_score_all_sorted_desc`, `test_weights_unnormalised_same_ranking` (weights 4/3/2/1 give same totals as 0.4/0.3/0.2/0.1).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement `pipeline/scout/scoring.py`.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: transparent weighted target scoring`

---

### Task 5: Europe PMC client

**Files:**
- Create: `pipeline/clients/europepmc.py`
- Modify: `scripts/record_demo.py`
- Test: `tests/test_europepmc.py`

**Interfaces:**
- Produces: `EPMC_URL`, `literature_hits(client: HttpClient, symbol: str, disease_name: str, n_pmids: int = 3) -> tuple[int, list[str]]`; params `{"query": f'"{symbol}" AND "{disease_name}"', "format": "json", "resultType": "lite", "pageSize": n_pmids}`; returns `hitCount` and the `pmid` of each result that has one. `pubmed_url(pmid) -> str` = `https://pubmed.ncbi.nlm.nih.gov/{pmid}/`.

- [ ] **Step 1: Write failing tests**: `test_lrrk2_parkinson_hits_over_1000_with_3_pmids`, `test_pubmed_url`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Extend `record_demo.py` to call `literature_hits` for all 25 symbols; re-run it.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: Europe PMC literature counts`

---

### Task 6: ChEMBL client

**Files:**
- Create: `pipeline/clients/chembl.py`
- Modify: `scripts/record_demo.py`
- Test: `tests/test_chembl.py`

**Interfaces:**
- Produces:
  - `CHEMBL_BASE = "https://www.ebi.ac.uk/chembl/api/data/"`
  - `find_target(client, uniprot: str | None, symbol: str) -> str | None`: if `uniprot`, GET `target.json` params `{"target_components__accession": uniprot, "target_type": "SINGLE PROTEIN", "limit": 5}` and return first `target_chembl_id` with `organism == "Homo sapiens"`; else (or on empty) GET `target/search.json` params `{"q": symbol, "limit": 10}` filtered to Homo sapiens + SINGLE PROTEIN, first hit; else None.
  - `potent_count(client, chembl_target_id: str) -> int`: GET `activity.json` params `{"target_chembl_id": id, "pchembl_value__gte": 6, "limit": 1}` → `page_meta.total_count`.
  - `potent_activities(client, chembl_target_id: str, max_pages: int = 5) -> list[dict]`: pages `activity.json` with `limit=1000`, `offset`, `only=molecule_chembl_id,pchembl_value,assay_type,standard_type`; stops when `page_meta.next` is null or `max_pages` reached.
  - `molecules(client, chembl_ids: list[str]) -> dict[str, dict]`: batches of 50 via `molecule.json` params `{"molecule_chembl_id__in": ",".join(batch), "only": "molecule_chembl_id,pref_name,max_phase,molecule_properties", "limit": 50}`; keyed by id.
  - `chembl_target_url(id) -> str` = `https://www.ebi.ac.uk/chembl/target_report_card/{id}/`, `chembl_molecule_url(id)` likewise with `compound_report_card`.

- [ ] **Step 1: Write failing tests**: `test_find_target_lrrk2_by_accession_is_chembl1075104`, `test_find_target_none_when_no_accession_and_no_symbol_hit` (symbol `"ZZQXV1"`), `test_potent_count_lrrk2_over_1000`, `test_potent_activities_capped_at_max_pages` (max_pages=1 → len ≤ 1000), `test_molecules_batch_returns_max_phase_string` (ids `["CHEMBL1721885"]` → `max_phase == "2.0"`, `molecule_properties["num_ro5_violations"] == 0`).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Extend `record_demo.py`: `find_target` + `potent_count` for all 25; `potent_activities(…, max_pages=5)` and `molecules` for the top-50 molecules of LRRK2 only (stage 2 demo); the `ZZQXV1` search; re-run.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: ChEMBL target resolution and potency lookups`

---

### Task 7: Scout pipeline and CLI

**Files:**
- Create: `pipeline/scout/pipeline.py`, `pipeline/cli.py`
- Test: `tests/test_scout_pipeline.py`

**Interfaces:**
- Consumes: Tasks 3–6 functions.
- Produces:
  - `gather_evidence(client, disease: Disease, n: int, workers: int = 8) -> list[TargetEvidence]`: `associated_targets` then `ThreadPoolExecutor(workers)` to fill literature, chembl and safety per target.
  - `run_scout(disease_name: str, n: int = 25, weights: Weights = Weights(), client: HttpClient | None = None) -> ScoutResult` (client defaults to `default_client()`).
  - `rescore(result: ScoutResult, weights: Weights) -> ScoutResult` (no I/O; used by the sliders).
  - CLI: `python -m pipeline.cli scout "Parkinson disease" [--n 25] [--cache-only]` prints a fixed-width text table of rank, symbol, total, four components, potent, hits, flags.

- [ ] **Step 1: Write failing tests** (cache-only client): `test_run_scout_parkinson_25_rows_components_in_unit_interval_sorted`, `test_lrrk2_in_top_5`, `test_rescore_changes_order_without_network` (weights druggability=1, others 0; assert client session patched to raise is never called), `test_unknown_disease_raises` (expects `DiseaseNotFound`).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement pipeline and CLI.**
- [ ] **Step 4: Run** → PASS. Then run `SCOUT_CACHE_ONLY=1 python -m pipeline.cli scout "Parkinson disease"` and confirm a 25-row table prints in under 5 s.
- [ ] **Step 5: Commit** `feat: scout pipeline and CLI`

---

### Task 8: Approval audit log

**Files:**
- Create: `pipeline/audit.py`
- Test: `tests/test_audit.py`

**Interfaces:**
- Produces: `APPROVALS_PATH = Path("runs/approvals.jsonl")`, `SHORTLISTS_PATH = Path("runs/shortlists.jsonl")`; `make_approval(result: ScoutResult, target: ScoredTarget, reason: str) -> Approval` (ts = UTC ISO 8601 with `Z`, `approved_by` = env `SCOUT_USER` or `getpass.getuser()`); `append_jsonl(path: Path, record: dict) -> None` (creates parent dir); `read_approvals(path=APPROVALS_PATH) -> list[Approval]` (newest first); `append_shortlist(approval: Approval, chembl_ids: list[str], reason: str, path=SHORTLISTS_PATH) -> None`.

- [ ] **Step 1: Write failing tests** with `tmp_path`: `test_make_approval_fields_match_spec_example_keys` (exact key set from spec 4.5), `test_append_then_read_newest_first`, `test_read_missing_file_returns_empty`.
- [ ] **Step 2: Run** → FAIL.  **Step 3: Implement.**  **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: approval and shortlist audit log`

---

### Task 9: Flask API for scout and approvals

**Files:**
- Modify: `backend/app.py`
- Create: `backend/pipeline/api.py`, `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `run_scout`, `rescore`, `make_approval`, `append_jsonl`, `read_approvals`, `DiseaseNotFound`, `CacheMiss`.
- Produces in `pipeline/api.py`:
  - `create_app(client: HttpClient | None = None, approvals_path: Path = APPROVALS_PATH) -> Flask` (app factory; `backend/app.py` becomes `app = create_app()` plus the `__main__` runner, keeping CORS for `http://localhost:3000`).
  - `RUNS: dict[str, ScoutResult]` module-level store; `run_id = uuid4().hex`.
  - `scout_run_json(run_id: str, result: ScoutResult, cache_only: bool) -> dict` producing the `ScoutRun` shape in spec 4.1a (`tractability_sm_labels` = SM labels with value true; `open_targets_url` = `https://platform.opentargets.org/target/{target_id}`).
  - Routes exactly as the spec table: `POST /api/scout` (`n` default 25, clamp 5–50), `GET/POST /api/approvals`, with `POST /api/approvals` recomputing totals via `rescore(RUNS[run_id], Weights(**weights))` and returning 400 `{"error": "scores do not match server recomputation"}` if any of the five posted `scores` differ by more than 0.0005; 404 `{"error": f"no run {run_id}"}`; `DiseaseNotFound` → 404 `{"error": f"no disease found for '{name}'"}`; `CacheMiss`/`requests.HTTPError` → 502.
  - `/api/rationale`, `/api/screen`, `/api/shortlists` are added in Tasks 11 and 13.

- [ ] **Step 1: Write failing tests** in `tests/test_api.py` using `create_app(client=<cache-only client>, approvals_path=tmp_path/"a.jsonl").test_client()`: `test_health`, `test_scout_returns_run_id_and_25_targets_with_components`, `test_scout_unknown_disease_404`, `test_approval_round_trip_get_newest_first`, `test_approval_score_mismatch_400_writes_nothing`, `test_approval_unknown_run_404`.
- [ ] **Step 2: Run** `pytest tests/test_api.py -v` → FAIL.
- [ ] **Step 3: Implement `pipeline/api.py`; rewrite `backend/app.py` to use the factory.**
- [ ] **Step 4: Run** → PASS. Then `SCOUT_CACHE_ONLY=1 python app.py` and `curl -X POST localhost:5000/api/scout -H 'Content-Type: application/json' -d '{"disease":"Parkinson disease"}' | head -c 400` shows a run_id.
- [ ] **Step 5: Commit** `feat: Flask API for scout runs and approvals`

---

### Task 10: Next.js Scout page

**Files:**
- Create: `lib/types.ts`, `lib/score.ts`, `lib/score.test.ts`, `lib/api.ts`, `app/components/WeightSliders.tsx`, `app/components/TargetTable.tsx`, `app/components/ApprovalForm.tsx`
- Modify: `app/page.tsx`, `app/layout.tsx` (title "Target Scout", nav links to `/` and `/screening`)

**Interfaces:**
- Consumes: the `ScoutRun` and `Approval` JSON shapes from Task 9 (mirror them in `lib/types.ts` as `ScoutRun`, `ScoutTarget`, `Components`, `Weights`, `Approval`).
- Produces in `lib/score.ts`: `DEFAULT_WEIGHTS: Weights = {genetic: 0.4, association: 0.3, druggability: 0.2, literature: 0.1}`; `normaliseWeights(w: Weights): Weights` (sum ≤ 0 → defaults); `total(c: Components, w: Weights): number`; `rankTargets(targets: ScoutTarget[], w: Weights): (ScoutTarget & {total: number, rank: number})[]` sorted desc, rank from 1.
- Produces in `lib/api.ts`: `postScout(disease: string, n: number): Promise<ScoutRun>`, `postApproval(body): Promise<Approval>`, `getApprovals(): Promise<Approval[]>`; each throws `Error(json.error)` on non-2xx.
- Page behaviour per spec 4.8 "Page /". Components are client components (`"use client"`). State: `run`, `weights`, `rationaleStale`. Approval posts `scores` = the five numbers shown for the chosen target, rounded to 4 dp.

- [ ] **Step 1: Read** `node_modules/next/dist/docs/` entries on App Router pages, client components and `fetch` before writing anything.
- [ ] **Step 2: Write failing test** `lib/score.test.ts`: `normaliseWeights sums to 1`, `all-zero weights fall back to defaults`, `total matches Python example (0.5,0.8,0.6,0.5 → 0.61)`, `rankTargets sorts desc and numbers ranks`.
- [ ] **Step 3: Run** `npm test` → FAIL.
- [ ] **Step 4: Implement `lib/score.ts`.**  **Step 5: Run** `npm test` → PASS.
- [ ] **Step 6: Implement `lib/types.ts`, `lib/api.ts`, the three components and `app/page.tsx`.** Rationale column renders "LLM rationale off" until Task 11.
- [ ] **Step 7: Manual verify** with Flask running in cache-only mode and `npm run dev`: run Parkinson disease, move druggability to 1.0 and confirm re-sort with no network request in the browser devtools, approve LRRK2 and confirm a line in `backend/runs/approvals.jsonl`. `npm run lint` clean.
- [ ] **Step 8: Commit** `feat: scout page with client-side weighting and approval`

---

### Task 11: LLM rationale

**Files:**
- Create: `pipeline/scout/rationale.py`
- Modify: `pipeline/api.py`, `scripts/record_demo.py`, `app/page.tsx`, `lib/api.ts`
- Test: `tests/test_rationale.py`, `tests/test_api.py`

**Interfaces:**
- Produces:
  - `RATIONALE_SCHEMA` (JSON schema): object with `items: array` of `{symbol: string, rationale: string, evidence_strength: enum[strong, moderate, weak]}`, `additionalProperties: false`, all required.
  - `evidence_payload(result: ScoutResult, top: int = 10) -> list[dict]`: per target the symbol, component scores, weights, `datatype_scores`, `potent_count`, `has_approved_drug`, `literature_hits`, `pmids`, SM tractability labels that are true, safety flag details. Nothing else.
  - `rationale_key(result: ScoutResult, top: int = 10) -> str`: sha256 of `(disease.id, weights.normalised().as_dict(), top symbols)`.
  - `explain(result: ScoutResult, top: int = 10, cache_dir: Path = Path("cache/rationale"), read_dirs=(Path("data/demo_cache/rationale"),)  # relative to backend/) -> ScoutResult | None`: returns None if no credentials (`anthropic.Anthropic()` raises on missing key and `ant auth status` is not a concern here: catch `anthropic.AuthenticationError`/missing-key error and return None). Reads `<key>.json` from read dirs first. Otherwise calls `client.messages.create(model="claude-opus-5-5", max_tokens=4000, system=SYSTEM_PROMPT, messages=[{"role":"user","content": json.dumps(payload)}], output_config={"effort":"low","format":{"type":"json_schema","schema":RATIONALE_SCHEMA}}, betas=["server-side-fallback-2026-07-01"], fallbacks="default")` via `client.beta.messages.create`; if `stop_reason == "refusal"` return None; parse JSON from the first text block; write cache; return a copy of `result` with `rationale`/`evidence_strength` filled on matching symbols.
  - `SYSTEM_PROMPT` (exact copy): "You write 2-3 sentence target rationales for a drug discovery scientist. Use only the numbers, labels and IDs in the provided JSON. Do not add facts that are not in it. If genetic evidence is below 0.3 or potent compounds are 0, say the evidence is weak on that axis. Return one entry per input symbol."
- API: `POST /api/rationale` body `{run_id, weights}` → `rescore` then `explain`; returns `{run_id, weights, rationales: [{symbol, rationale, evidence_strength}]}` or `{available: false, reason: "no API key or refused"}` with 200.
- UI: "Explain ranking (LLM)" button calls `postRationale(run_id, weights)` from `lib/api.ts`; stores rationales keyed by symbol; any weight change sets `rationaleStale` and blanks the column until the button is pressed again. Column header reads `rationale (weights g/a/d/l = …)`. `available: false` shows an inline note.

- [ ] **Step 1: Write failing tests**: `test_evidence_payload_has_only_allowed_keys` (set equality on keys), `test_rationale_key_changes_with_weights`, `test_explain_uses_cached_file_without_api` (write a fake `<key>.json` in a tmp read dir, patch `anthropic.Anthropic` to raise, assert rationale filled), `test_explain_returns_none_on_refusal` (patch the client to return an object with `stop_reason="refusal"`).
- [ ] **Step 2: Run** → FAIL.  **Step 3: Implement** per the Python Anthropic SDK (consult the `claude-api` skill's `python/claude-api/README.md` for the exact `beta.messages.create` signature before writing). Add the route and a test `test_rationale_endpoint_unavailable_without_key` (patch `explain` to return None → `available: false`). Wire the button.  **Step 4: Run** → PASS.
- [ ] **Step 5: Record** the default-weights rationale into `data/demo_cache/rationale/` by running `python scripts/record_demo.py --rationale` once with a key; commit that file.
- [ ] **Step 6: Commit** `feat: evidence-only LLM rationale with cache`

---

### Task 12: Compound ranking

**Files:**
- Create: `pipeline/screening/ranking.py`
- Test: `tests/test_ranking.py`

**Interfaces:**
- Produces:
  - `best_per_molecule(activities: list[dict]) -> dict[str, tuple[float, str | None]]`: max `pchembl_value` (parsed float) per `molecule_chembl_id` with the `assay_type` of that record.
  - `build_compounds(best: dict[str, tuple[float, str | None]], mols: dict[str, dict]) -> list[Compound]`: parse `molecule_properties` strings to floats/ints, None when missing.
  - `rank_compounds(compounds: list[Compound]) -> list[Compound]`: sort by `best_pchembl` desc, then `ro5_violations` asc with None last.

- [ ] **Step 1: Write failing tests**: `test_best_per_molecule_takes_max`, `test_build_compounds_handles_null_phase_and_props`, `test_rank_ties_broken_by_ro5_none_last`.
- [ ] **Step 2–4: FAIL → implement → PASS.**
- [ ] **Step 5: Commit** `feat: compound ranking`

---

### Task 13: AlphaFold client and screening pipeline

**Files:**
- Create: `pipeline/clients/alphafold.py`, `pipeline/screening/pipeline.py`
- Modify: `scripts/record_demo.py`, `pipeline/cli.py`, `pipeline/api.py`
- Test: `tests/test_alphafold.py`, `tests/test_screening_pipeline.py`

**Interfaces:**
- Produces:
  - `alphafold.prediction(client, uniprot: str) -> Structure | None`: GET `https://alphafold.ebi.ac.uk/api/prediction/{uniprot}`; list response, take `[0]`; fields `entryId`→`model_id`, `pdbUrl`, `cifUrl`, `globalMetricValue`→`mean_plddt`, `fractionPlddtConfident + fractionPlddtVeryHigh`→`fraction_confident`; None on 404 or empty list.
  - `run_screening(approval: Approval, top_n: int = 50, client: HttpClient | None = None) -> ScreeningResult`: if `chembl_target_id` is None → empty compounds; else `potent_activities` → `best_per_molecule` → top `top_n` by pchembl → `molecules` → `build_compounds` → `rank_compounds`. Structure via `prediction` if `uniprot` else None.
  - CLI subcommand `screen --latest` runs on the newest approval and prints the compound table.
  - Routes in `pipeline/api.py`: `POST /api/screen` body `{approval_ts}` → finds the approval by `ts` in `read_approvals()` (404 if absent) → `run_screening` → JSON `{approval, structure, compounds: [{chembl_id, name, best_pchembl, assay_type, max_phase, is_approved, mw, alogp, hbd, hba, psa, ro5_violations, lipinski_pass, chembl_url}]}`; `POST /api/shortlists` body `{approval_ts, chembl_ids, reason}` → `append_shortlist` → `{ok: true}`.

- [ ] **Step 1: Write failing tests**: `test_prediction_q5s007_has_plddt_and_urls`, `test_run_screening_lrrk2_returns_50_compounds_sorted` (build an `Approval` for LRRK2 by hand with `CHEMBL1075104` / `Q5S007`), `test_run_screening_without_chembl_target_gives_structure_only`; in `tests/test_api.py`: `test_screen_endpoint_lrrk2` (append a hand-built approval to the tmp log first) and `test_shortlist_endpoint_appends_line`.
- [ ] **Step 2: Run** → FAIL.  **Step 3: Implement**; extend `record_demo.py` with `prediction("Q5S007")`; re-run.  **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: AlphaFold structure and screening pipeline`

---

### Task 14: Next.js Screening page

**Files:**
- Create: `app/screening/page.tsx`, `app/components/StructureCard.tsx`, `app/components/CompoundTable.tsx`, `app/components/ShortlistForm.tsx`
- Modify: `lib/types.ts` (`ScreeningResult`, `Compound`, `Structure`), `lib/api.ts` (`postScreen(approval_ts)`, `postShortlist(body)`)

**Interfaces:**
- Consumes: Task 13 JSON shapes.
- Behaviour per spec 4.8 "Page /screening": approvals select, Run screening button, structure card (mean pLDDT 1 dp, confident fraction as %, link `https://alphafold.ebi.ac.uk/entry/{uniprot}`), compound table with approved badge, checkbox column, reason, Shortlist button; empty approvals → inline note "Approve a target on the Scout page first".

- [ ] **Step 1: Implement types, api wrappers, components, page.**
- [ ] **Step 2: Manual verify** full demo in cache-only mode: Scout → approve LRRK2 → Screening → shortlist two compounds → `backend/runs/shortlists.jsonl` has a line. `npm run lint` and `npm run build` clean.
- [ ] **Step 3: Commit** `feat: screening page with structure and shortlist`

---

### Task 15: README and demo script

**Files:**
- Modify: `README.md`
- Create: `scripts/demo.sh`

- [ ] **Step 1: Rewrite README** keeping the existing frontend/backend run instructions and adding: what it does (two stages, the formula with weights), backend deps, `SCOUT_CACHE_ONLY=1 python app.py` for the demo and plain `python app.py` for live data, optional `ANTHROPIC_API_KEY`, the API table from spec 4.1a, how the audit logs work, how to refresh the snapshot (`python scripts/record_demo.py` from `backend/`), and a note that Open Targets field names change and `graphql()` surfaces the server message.
- [ ] **Step 2: Write `scripts/demo.sh`**: runs `pytest -q` in `backend/` and `npm test`, then starts Flask with `SCOUT_CACHE_ONLY=1` in the background and `npm run dev` in the foreground.
- [ ] **Step 3: Verify** `bash scripts/demo.sh` passes both test suites and both servers come up.
- [ ] **Step 4: Commit** `docs: README and demo script`
