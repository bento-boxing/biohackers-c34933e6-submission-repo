# Evidence reliability audit — 8 November 2026

## Actual CCR5 failure, established before implementation

Read-only inspection of the saved HIV/CCR5 job found 12 curated compounds,
136 trial candidates, zero publications and no saved API errors. Its disease
label was `HIV infectious disease` (`MONDO_0005109`). Both original Europe PMC
queries required `TITLE_ABS:"HIV infectious disease"`. Replaying them returned
zero hits. A control using `(CCR5 OR maraviroc)` and `TITLE_ABS:"HIV"` returned
6,966 hits. The old post-filter also required the unrecognised display label.
It would reject common HIV/HIV-1 wording even if the search returned it.

The old sampler sorted by stop-reason presence, compound match, disease match,
then NCT ID, and took six records. It did not search exclusively terminated
trials, but all six sent in this saved case were terminated:
NCT00496782, NCT00981318, NCT00981773, NCT01049204, NCT01140412 and NCT01345630.
Several reasons were operational or referred elsewhere; one explicitly named
fosamprenavir-related rash, not demonstrated CCR5-mediated toxicity. Completion
and termination were not explicitly classified as efficacy in the deterministic
rules, but the input packet was materially biased towards stopped programmes.

Other observed weaknesses:

- ChEMBL molecule approval phase and indication records were discarded.
- Compounds were capped in identifier order, which could omit approved drugs.
- Literature searches used preferred names, no general ontology synonym lookup,
  challenge-oriented search vocabulary and hard 25+10 result caps.
- Publication truncation could omit conclusions near the abstract end.
- The designer's reduced context could omit counterbalancing evidence not cited
  by the challenger.
- No coverage gate distinguished search failure, no results, sampling omissions
  and unsearched approval sources before a model-level conclusion.
- The existing 15-minute cache was not shown to cause this saved case: no API
  errors were recorded, and the uncached query replay reproduced the zeros.
  Failed requests are not cached. New query keys do not reuse the old phrase query.

Compound–trial matching remains explicit: an exact normalized intervention name
or curated synonym is a verified *name link*, embedded aliases are probable,
and other candidates uncertain. This does not prove clinical target engagement.

## General changes

`disease_terms.py` uses exact MONDO/EFO ontology identifiers through EBI OLS when
available, preserving the original disease name/ID. It also uses explicit caller
aliases, existing spelling aliases, generic display-suffix removal and subtype
phrase handling. None of this contains a CCR5 outcome rule.

`literature.py` searches clinical and broad literature without an efficacy/safety
direction filter, plus citation-prioritized clinical studies of phase-4 compounds.
Each search returns at most 40 records (120 raw candidates for three queries).
Preferred names and curated synonyms are included. Visible disease and entity
matching remains conservative; compound-only evidence can be retained explicitly
as uncertain disease context rather than silently excluded or extrapolated.
Citation counts aid discovery, never establish study quality or efficacy.

ChEMBL phase, first-approval/withdrawal metadata, indication IDs/terms, per-
indication phase and original URLs are preserved. Molecules are ordered by
phase before the 15-compound cap. Official openFDA label submissions add
population, indication and study context for up to three phase-4 compounds.
Phase 4 and FDA listing alone are not current authorisation or efficacy proof.
An approval in another indication is not transferred to the requested disease.

Trial detail responses now preserve full outcome records and phase as well as
the lossless stop-reason state. Deterministic stratification considers verified
compound/disease links, approval precedent, posted results, stop-reason categories
and phase. Publication selection keeps positive, negative, safety and compound-
limitation conclusion candidates. All directions are explicitly unadjudicated
triage; no numerical endpoint is automatically interpreted as success/failure.
The full retrieved set remains in the investigation, with selected/omitted IDs
and reasons. This is a bounded stratified sample, not statistically representative
or exhaustive evidence.

`coverage.py` runs before any paid model call. Missing/failed critical sources,
missing clinical literature, unresolved registry disease applicability, missing
approval metadata, and omitted available direction/results strata produce
**INSUFFICIENT COVERAGE**, not a negative target verdict. Search logs distinguish
no results, not searched, failed, limit reached, visible attrition and packet
omission. Search limits remain visible even when a bounded review is possible.

The existing challenge → adjudication → optional revision → experiment workflow
is retained for adequate bounded coverage. Prompts explicitly require scoped
therapeutic precedent and reject target invalidity from missing evidence or
individual programme failures. Deterministic scope checks supplement adjudication;
they are not a complete semantic verifier. The designer retains clinical and
approval counterevidence even when the challenger did not cite it.

New experiment synthesis must document existing knowledge and an unresolved gap.
Absent accepted anchors/knowledge review, a broad repeated benefit question in
the presence of approval precedent, or unavailable verified synthesis results in
**INSUFFICIENT EVIDENCE FOR EXPERIMENT**. This does not certify novelty; expert
review is still required. Archived demos remain unchanged and visibly historical.

## Measured validation and limits

See [reference sheet](SCIENTIFIC_REFERENCE.md),
[`scientific_coverage_report.json`](validation/scientific_coverage_report.json)
and [`coverage_live_ccr5.json`](validation/coverage_live_ccr5.json).

- Recorded checks: **30/30** across CCR5, PCSK9, EGFR, BACE1 and LRRK2, separate
  from software test counts. Approval metadata, both clinical directions where
  supplied, scoped context, status neutrality and missing-source abstention are
  checked. Cases/expectations were selected by the implementer, not blinded.
- Among three positive-precedent reference cases, the old disease phrase filter
  missed the positive publication in **2/3**; new filtering and packet selection
  missed **0/3** on this recorded replay. This measures evidence omission,
  **not Gemini scientific false-negative rates** or live recall across targets.
- The PCSK9 reference trial uses `Hyperlipidemia`; its match to the requested
  hypercholesterolemia population remains uncertain and coverage abstains. This
  is not a judgement against evolocumab. BACE1/LRRK2 source subsets do not prove
  absence of approvals or exhaust contemporary evidence. The BIIB122 preferred-
  name molecule search returned no exact match; no compound link was fabricated.
- Final targeted CCR5 diagnostic retrieved **99** publications and recognized
  maraviroc's phase-4 precedent. Its four-publication packet includes
  **MED:18832244 (MOTIVATE)** and **MED:20151839 (MERIT)**. The saved trial set was
  not refetched, so the diagnostic still abstains on overall registry coverage.
- In that diagnostic, ontology/indication/label retrieval took **3.244282 s**
  (14 public requests), and three publication searches took **9.352168 s**.
  Molecule metadata refresh happened outside those timers. These are measured
  phase times using `min_interval=0`, not an end-to-end improvement or a measured
  production latency delta. Production rate limiting, network availability and
  retrieval limits still apply. Recorded coverage-only timing is reported as a
  median/p95 over 500 runs in the benchmark JSON; it excludes network and Gemini.
- **213 Python tests** and **8 offline browser tests** passed, as did TypeScript,
  lint and the frontend production build. The coverage-only benchmark median was
  **0.077 ms**, p95 **0.1431 ms**, over 500 recorded runs. No paid Gemini call was
  made. Consequently, real-model compliance with
  the new balanced prompts, novel-question quality and semantic false-positive/
  false-negative rates remain unvalidated.

Existing jobs, scientific records, Target Scout ranking, audit logs and human
approval gates were not migrated or rewritten. No backend job was restarted,
cancelled or duplicated. Changes are uncommitted.

## Reproduction and rights

```powershell
.\.venv\Scripts\python.exe -m pytest devils_advocate/tests backend/tests -q
.\.venv\Scripts\python.exe -m devils_advocate.scientific_benchmark
# Optional public retrieval only; requires an existing saved CCR5 job:
.\.venv\Scripts\python.exe scripts/check_ccr5_coverage.py
# Opt-in source-fixture refresh, public requests only:
.\.venv\Scripts\python.exe scripts/capture_scientific_reference.py
```

Benchmark reference labels live only in evaluation scripts/fixtures, never in
production inference. ChEMBL data retain CC BY-SA 3.0 attribution and source IDs.
Ontology terms retain EBI/ontology provenance. Registry records are public,
sponsor-submitted aggregate records, not patient-level data. Abstract excerpts
retain publication-specific rights and original citations; no full article text
is redistributed. Label records are submitted product labeling, retain original
links/notices, and are not independently verified FDA approval declarations:
[openFDA label documentation](https://open.fda.gov/apis/drug/label/).
