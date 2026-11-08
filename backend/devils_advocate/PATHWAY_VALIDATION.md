# Clinical and preclinical assessment — 8 November 2026

## Why the saved CCR5 UI report showed zero publications

The original database was inspected through a read-only SQLite connection.
It contains an older CCR5 report (`4872335817bb4608ab3e57b826b27db8`, created
7 November at 23:54 UTC) without a coverage audit, and a newer report
(`9c8ab7845b7849c19b5d6503cd3e0502`, 8 November at 01:20 UTC) with the upgraded gate.
Both contain zero publications. The newer report records **three failed Europe
PMC queries**, not three successful zero-result searches. Retrieval event logs
confirm three `RetryError`s after approximately 3.27, 3.12 and 3.11 seconds.
Historical logs did not retain the final HTTP status; it is not reconstructed.
Two query strings were longer than 1,500 characters, but even the 374-character
query failed. Query length alone therefore does not explain all three failures.

The prior **99-publication result belonged to a separate diagnostic**, which
refreshed public literature and metadata but did not create or replace a saved
job. There is no evidence those 99 records were lost during SQLite persistence
or Next.js rendering. The saved newer job never retrieved them. Both an older
report and a newer failed report could be resumed by the browser; the exact
selected browser job cannot be determined from SQLite alone.

The running application backend started at 01:23 UTC, after the previous
literature source changes at 00:32. The newer saved report also demonstrates
that the reliability gate was active. These observations support an upstream
retrieval failure rather than only a pre-upgrade report. Historical loaded
source bytes were not fingerprinted, so an exact old code hash is not asserted.

## General implementation

- `association.py` scopes retrieved publications into disease-specific clinical
  candidates, disease-specific primary biological candidates, indirect mechanisms,
  other-condition target pharmacology and unrelated records. Clinical intervention
  screening uses publication types and intervention/trial language; the word
  “patients” alone does not establish a treatment trial.
- Exploratory eligibility requires at least two distinct primary source groups
  with genetic, functional cellular or disease-model evidence. Matching DOI/title
  versions are grouped. Co-mentions, control tissues, review text and unrelated
  pharmacology do not establish a disease-specific causal link. This is a
  conservative, inspectable lexical triage policy, not an expert quality score.
- Exact supplied disease/Ensembl pairs can be checked against the live Open
  Targets API with `enableIndirect=false`, validating returned gene identity.
  The descriptive score and datatype scores are retained with the source URL.
  They do not establish causality, therapeutic benefit or success probability.
  Missing identifiers/API failure are explicit; no association is guessed.
- The **clinical-precedent pathway** requires disease-specific interventional
  literature and target/compound-linked disease-matched trial context, with
  balanced outcome/stop-reason review. The **preclinical-validation pathway**
  requires adequate direct biology in both the retrieved set and selected packet,
  successful literature/registry searches and confirmed target identity, but
  requires neither trials nor approved drugs. Inadequate biology abstains with
  precise missing-evidence reasons; it does not reject the target as invalid.
- A zero-result registry search differs from failed/unsearched registry access.
  A failed optional query is retained in the audit but does not erase successful,
  independently retrieved relevant evidence. All-failed critical sources still
  block reasoning. Source limits remain visible.
- Literature queries are bounded/chunked, short disease terms are retained,
  registry-linked RESULT PMIDs are retrieved from actual full trial records,
  and one smaller target–disease fallback can recover a failed broad search.
  Exhausted status retries now preserve the actual final HTTP response code;
  failed responses are not cached as zero results.
- Biological association appears before approval context in the UI. Approval for
  a different condition is labelled **Target pharmacology only — no matched
  approved indication found**. Preclinical packets omit unrelated product labels;
  full records remain in the investigation. Drug mechanisms provide tractability
  context, not evidence that the disease should respond.
- The Gemini challenge/adjudication/revision workflow is unchanged in structure.
  New pathway instructions limit preclinical reasoning to competing biological
  explanations, causality, model suitability and decision-relevant uncertainties.
  Experiments require accepted direct biological anchors. Neither a drug approval
  nor an expression association licenses an assumed treatment effect.
- Coverage eligibility is separate from paid-call permission. The UI can request
  public evidence only. Paid reasoning still requires explicit authorization.
  Disabled/skipped reports display the reason; eligible coverage never starts a
  paid call by itself.
- New reports record source version, process load time, retrieval time, source
  counts and cache hits. Config reports whether loaded code matches files on disk.
  Old saved reports are identified as lacking current provenance, never silently
  recomputed. Target Scout ranking, approval gates and original jobs are unchanged.

## Actual end-to-end validation

Validation used a separate local Next.js/Flask instance to avoid interrupting the
user's running application. It used the **production Next rewrite, Flask job
creation endpoint, worker, real public HTTP client and SQLite job store**; source
retrieval was not mocked. Existing Scout selection context was copied read-only
into the isolated store and passed through the normal `run_id`/symbol handler.
No previous completed investigation was copied as the fresh result.

`AI_ENABLED=false`, `use_ai=false` and `paid_authorized=false` were enforced.
New idempotency keys created fresh jobs. Saved results were re-read through both
SQLite and the Next.js API proxy, compared for equality, then rendered in Chrome.

| Pair | Trials | Publications | Result | End-to-end time |
|---|---:|---:|---|---:|
| HIV infectious disease / CCR5 | 136 | 138 | Clinical precedent; reasoning eligible | 103.345060 s |
| Scoliosis / BCL2 | 0 | 7 | Exploratory preclinical validation; reasoning eligible | 12.433231 s |
| Invented unsupported condition / BCL2 | 0 | 0 | Insufficient coverage; no reasoning eligibility | 16.425755 s |

These are observed public-only job times including API submission/polling, not
estimated runtimes, averages, Gemini latency or scientific efficacy measurements.
The final jobs all report source hash `a76f7c958d96b4dbbf34`, matching the validation
process's loaded files. Clinical and exploratory jobs had zero cache hits; the
unsupported control reused 11 public responses and still abstained. Full results
are retained locally in the isolated runtime database; compact measurements and
IDs are in [`validation/pathway_end_to_end.json`](validation/pathway_end_to_end.json).

The CCR5 packet includes **MED:18832244 (MOTIVATE)** and **MED:20151839 (MERIT)**,
preserving supportive efficacy evidence and endpoint/population-specific
limitations. See the [clinical reference sheet](SCIENTIFIC_REFERENCE.md) for source
links and restrictions; not every HIV population is an eligible maraviroc population.

For BCL2, the exact-pair Open Targets descriptive score was approximately
**0.0014783**, with literature evidence only in that response. The primary biology
includes the reported scoliosis genetic association (MED:32030084), cellular
pathway study (MED:31337422), and other explicitly scoped research. The IDD study
using scoliosis tissue (MED:33209193) and environmental zebrafish toxicity study
(MED:38750761) are indirect context. Preprint/published versions are not counted
twice. This permits a **limited challenge of the hypothesis**; it does not validate
BCL2 causality, the direction of modulation, safety or venetoclax use in scoliosis.

Software validation: **225 Python tests and 15 browser tests passed**. The browser suite includes
the existing offline workflows, recorded clinical/preclinical/unsupported
rendering, public-only permission controls, and three actual saved-live-job
renders. TypeScript, lint and a production frontend build also passed.
Actual Gemini behavior remains unvalidated because **zero paid calls** were made.
Automatic scope classification, subtype matching and study-group independence
remain conservative heuristics requiring expert review.

## Reproduction

```powershell
# All offline Python checks
.\.venv\Scripts\python.exe -m pytest devils_advocate/tests backend/tests -q

# Terminal 1: isolated production Flask factory + public client; never paid AI
.\.venv\Scripts\python.exe scripts/pathway_validation_server.py

# Terminal 2: frontend directory; isolated Next API proxy
$env:RESEARCH_BUILD_DIR='.next-qa'
$env:RESEARCH_BACKEND_URL='http://127.0.0.1:5051'
npm.cmd exec -- next dev --hostname 127.0.0.1 --port 3001

# Terminal 3: repository root, opt-in real public requests / fresh jobs
.\.venv\Scripts\python.exe scripts/validate_pathway_jobs.py

# Frontend directory: offline regressions plus previously saved real-job rendering
$env:PLAYWRIGHT_BASE_URL='http://127.0.0.1:3001'
$env:PATHWAY_LIVE_VALIDATION='1'
npm.cmd run test:e2e
```

Without `PATHWAY_LIVE_VALIDATION=1`, the three real-job rendering checks are
explicitly skipped; the recorded regressions remain network-independent.
The validation scripts require the existing local Scout context for both pairs.
They do not authorize Gemini or replace any original report. To use new logic in
the normal app, restart its backend when safe; the validation process does not
restart the user's backend on port 5050. Resume a new report rather than expecting
a historical zero-publication report to change itself.

Source rights remain unchanged: ChEMBL attribution/share-alike terms, Open Targets
and underlying-source notices, public aggregate registry records, and individual
publication/label rights. New fixtures are labelled source-derived regression
snapshots; frontend snapshots omit abstract text/large raw fields and are not
scientific evidence packets. Original scientific records are not rewritten.
