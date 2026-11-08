# Adaptive evidence discovery and verification — validation

Date: 8 November 2026. Branch: `feat/adaptive-evidence` (from `prod`). Scope: `backend/devils_advocate/`
and the Next.js panels that render its report. Target Scout ranking and the screening scorer are
untouched. No commits, pushes or deployments were made; no paid Gemini call was made by any test,
benchmark or demonstration in this work (`paid_calls: 0` in every report).

**Verdict in one line.** The challenger now plans what it must establish for *any* disease–target
pair, measures what it actually retrieved against that plan, searches again only where a need is
open, and records why it stopped. On the ten-case live benchmark through the real
Next.js → Flask → SQLite-cache path, follow-up rounds recovered evidence the single pass missed
(see §5), left the already-complete cases untouched (zero follow-up searches when coverage was
achieved), and the previously missed rare-disease reference record (PMID 25605922) is now retrieved.
Open needs after bounded search are reported as unverified, never as absence.

## 1. Existing root causes (audit of the prod pipeline)

| # | Audit symptom | Root cause found in code | Where |
|---|---|---|---|
| 1 | CCR5 missed MOTIVATE/MERIT until a hand fix | Retrieval was one fixed query family; nothing re-queried when the direct-clinical stratum came back empty. | `literature.py:retrieve_publications` |
| 2 | LRRK2 missed recent development outcomes | No publication or registry dates were parsed at all (`Publication`/`Trial` had no date fields), so "recent" could not be detected, ranked or searched; no compound-specific outcome search existed. | `models.py`, `literature.py`, `trial_retriever.py` |
| 3 | Scoliosis/BCL2 needed a different route | The clinical/preclinical pathway existed as a gate, but preclinical needs (genetic, cellular, model evidence) were never searched for explicitly; only incidental hits were scoped. | `coverage.py:check_coverage` |
| 4 | Experiments repeated documented work | `check_prior_art` searched the proposed *question* only; mechanism, readouts and competing hypotheses were not searched, so a study answering the same question with the same readout was not flagged as answering it. | `prior_art.py` |
| 5 | Retrieved publications omitted from Gemini's packet | `select_evidence` was a fixed 4-publication/6-trial stratified cutoff with no notion of a *material* record; a landmark trial past the cutoff was silently dropped unless a direction-signal facet happened to flag it. | `coverage.py:select_evidence` |
| 6 | Retrieval failure vs absence of evidence | Failed searches were audited, but the gate could not say *which* need was unverified because a source failed versus unmet because nothing was found; an Ensembl outage aborted the whole investigation as "target unavailable". | `devil_advocate.py`, `coverage.py` |
| 7 | Manual refresh unreachable | `run_investigation` honoured `refresh_evidence`, but neither the request model nor the UI exposed it. | `server.py`, `app/challenge/page.tsx` |
| 8 | Progress invisible | One synchronous request; the UI showed elapsed seconds only; timings existed per HTTP source but not per pipeline stage. | `investigation.py`, `components/workbench.tsx` |
| 9 | Adjudication checked citation presence only | `validate_ai_claim` verified identifier/field/excerpt and a few patterns; it did not check that the excerpt's direction matched the stance, that cited sources matched the disease, that causal wording exceeded an observed association, or that contradictory records existed outside the packet. | `ai_reasoning.py` |
| 10 | A malformed registry record crashed the run | `parse_trial` assumed `statusModule` is a dict; a string crashed the whole investigation (found by the new reliability test). | `trial_retriever.py` |

Existing functionality that was reused rather than duplicated: the shared rate-limited HTTP client
and SQLite verified-response cache, the ChEMBL/Ensembl/OLS identity checks, trial full-record
verification, `annotate`/`scope_publication` triage, `check_coverage`'s pathway gate and facets,
the three Gemini roles with deterministic objections, `check_prior_art`'s lexical ranking, and the
signed stateless request flow.

## 2. Architecture changes

```
identity → compounds → association/precedent → trials → literature
      → build_plan → assess_plan ─┬─ open needs? ──no──▶ coverage gate → packet → Gemini roles
                                  └─ yes: followup_searches (≤6/round) → ingest → reassess
                                        (≤ ADAPTIVE_MAX_ROUNDS, stop reason recorded)
```

- **`evidence_planner.py` (new).** `build_plan` derives the stage (clinical / preclinical /
  unresolved) from verified identifiers and scoped records and lists nine needs: target–disease
  association, genetic/mechanistic evidence, approved therapy and indication precedent, positive
  clinical studies, negative/safety findings, programme status, population/subtype, recent
  consequential developments, unresolved uncertainties. `assess_plan` assigns
  `satisfied | partial | unmet | not_applicable | unverifiable` per need from existing annotations
  (evidence scope, direction signals, approvals, trial dates/results, publication dates) and flags
  up to four *material* record ids per need. `followup_searches` builds targeted queries only for
  open needs from disease names and ontology synonyms, gene symbol and verified aliases, compound
  names, NCT ids and direction-neutral outcome/model/population vocabularies; round two varies the
  strategy (date-sorted) instead of repeating a query. `resolve_loop` runs the bounded loop with
  budget checks and records every search, response state, new record and the stop reason. Manual
  pairs without identifiers get an Open Targets symbol→Ensembl and OLS name→MONDO exact-match
  resolution (ambiguity guesses nothing).
- **Dates and tiers.** Europe PMC `firstPublicationDate` and ClinicalTrials.gov start / primary
  completion / last update / results-first-posted dates are parsed; `evidence_tier` distinguishes
  registry status, registry-posted results, peer-reviewed publications and FDA regulatory records.
  Sponsor announcements are not fetched (no permitted API) and the plan says so.
- **Packet audit.** Planner material records are admitted beyond the stratified cutoff (bounded by
  `AI_MAX_MATERIAL_EXTRA`) with a stated reason; a material record that cannot fit is a coverage
  gap. The bundle sent to Gemini now carries publication dates, tiers, discovery provenance, the
  plan with need statuses and a dated development timeline.
- **Evidence Coverage Agent behaviour in reasoning.** Before adjudication the deterministic layer
  names direct contradictory records missing from the packet and pulls them in for the revision
  round; an unverified consequential (efficacy/safety) claim triggers one targeted retrieval.
- **Adjudicator rules.** Stance/excerpt direction, disease/population applicability of cited
  sources, causal wording beyond an observed association, universal/exclusive claims.
- **Prior art.** Three facet searches (question, mechanism/readout, competing hypotheses); a record
  matching the question *and* a second facet is reported as substantially answering it, which
  withholds the proposal pending a refinement. Surviving proposals are labelled "potentially
  informative and unvalidated".
- **Optional Gemini planning call.** `AI_PLANNING_CALL=true` plus an authorised `use_ai` request
  allows one call whose output is search terms only; it is executed and audited like any other
  follow-up and counts against `AI_MAX_CALLS`. Off by default; exercised only with a scripted
  runner in tests.
- **Request path and UI.** `refresh_evidence`, `max_followup_rounds` and `progress_token` on the
  investigation request; `GET /api/investigations/progress/<token>` serves real backend stages
  while the request runs (reported as unavailable on a host instance that cannot serve it); the
  challenge page shows the plan panel, the refresh checkbox, live stage progress, per-stage timings,
  and dated/tiered records in the Publications and Compounds & trials tabs.
- **Transport.** Per-host policy: Ensembl gets two attempts with a 10 s read timeout (it answered
  503 after 20 s per attempt during validation and cost 15–62 s per investigation); an Ensembl
  outage is now a retrieval failure that continues to symbol-based ChEMBL resolution, with a
  coverage gap unless the Open Targets exact-pair lookup confirms id and symbol.

## 3. Search and coverage strategy

- Searches are selective: a need that is satisfied generates no search; CCR5, PCSK9 and EGFR ran
  zero follow-up searches in the benchmark because the initial pass already covered every need.
- Vocabulary is direction-neutral: outcome queries combine positive and negative words
  ("primary endpoint", efficacy, safety, discontinued, futility, phase terms), so follow-up cannot
  bias the packet towards one direction.
- Every follow-up record passes the same visibility rule as the initial retrieval (target or
  compound named *and* disease named) and the same scoping, so a follow-up cannot inject unrelated
  records.
- Failed searches are recorded as `failed` with "not a zero-result search", are not cached, and
  leave the need `unverifiable`; budget exhaustion stops the loop with that reason.
- Stop reasons: `coverage_achieved`, `no_actionable_gaps`, `no_new_evidence`, `round_limit`,
  `budget_exhausted`, `follow_up_disabled`, `target_unresolved`.

## 4. Cross-disease results (live, through Next.js → Flask → SQLite cache)

Modes: **baseline** = follow-up disabled (`max_followup_rounds=0`), caches bypassed; **adaptive cold** = default two rounds, caches bypassed; **adaptive warm** = default rounds with the per-instance SQLite cache primed by the cold run. "Loop s" is the measured `adaptive_rounds` stage (plan + follow-up searches + reassessment). Retrieval seconds include upstream variance (Ensembl answered 503/timeouts in several runs), so cold-versus-cold timings are not a controlled speed test; the loop column is the controlled cost of the new work.

| Case | Mode | ChEMBL (status) | Pathway | Plan stage · stop | Rounds/searches/new | Open needs after | Ref recall (in packet) | Pubs/trials | Retrieval s | Loop s | Requests (cache hits) | Coverage |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ccr5_hiv | baseline | CHEMBL274 (resolved) | clinical_precedent | clinical · follow_up_disabled | 0/0/0 | none | 1.0 (2/2) | 231/163 | 74.1 | 1.15 | 70 (0) | BOUNDED REVIEW |
| ccr5_hiv | adaptive_cold | CHEMBL274 (resolved) | clinical_precedent | clinical · coverage_achieved | 0/0/0 | none | 1.0 (2/2) | 231/163 | 83.1 | 1.15 | 70 (0) | BOUNDED REVIEW |
| ccr5_hiv | adaptive_warm | CHEMBL274 (resolved) | clinical_precedent | clinical · coverage_achieved | 0/0/0 | none | 1.0 (2/2) | 231/163 | 7.8 | 1.20 | 5 (220) | BOUNDED REVIEW |
| pcsk9_hchol | baseline | CHEMBL2929 (resolved) | clinical_precedent | clinical · follow_up_disabled | 0/0/0 | target_disease_association | 1.0 (0/2) | 172/197 | 53.7 | 0.48 | 58 (0) | BOUNDED REVIEW |
| pcsk9_hchol | adaptive_cold | CHEMBL2929 (resolved) | clinical_precedent | clinical · round_limit | 2/4/37 | target_disease_association | 1.0 (0/2) | 208/197 | 41.9 | 1.76 | 62 (0) | BOUNDED REVIEW |
| pcsk9_hchol | adaptive_warm | CHEMBL2929 (resolved) | clinical_precedent | clinical · round_limit | 2/4/37 | target_disease_association | 1.0 (0/2) | 208/197 | 5.9 | 1.07 | 4 (247) | BOUNDED REVIEW |
| egfr_nsclc | baseline | CHEMBL203 (resolved) | clinical_precedent | clinical · follow_up_disabled | 0/0/0 | none | 1.0 (1/1) | 370/179 | 71.6 | 2.75 | 71 (0) | BOUNDED REVIEW |
| egfr_nsclc | adaptive_cold | CHEMBL203 (resolved) | clinical_precedent | clinical · coverage_achieved | 0/0/0 | none | 1.0 (1/1) | 370/179 | 62.5 | 2.67 | 71 (0) | BOUNDED REVIEW |
| egfr_nsclc | adaptive_warm | CHEMBL203 (resolved) | clinical_precedent | clinical · coverage_achieved | 0/0/0 | none | 1.0 (1/1) | 370/179 | 9.0 | 2.68 | 1 (241) | BOUNDED REVIEW |
| bace1_ad | baseline | CHEMBL4822 (resolved) | clinical_precedent | clinical · follow_up_disabled | 0/0/0 | approved_therapy, positive_clinical | 1.0 (2/2) | 139/28 | 20.3 | 0.49 | 32 (0) | BOUNDED REVIEW |
| bace1_ad | adaptive_cold | CHEMBL4822 (resolved) | clinical_precedent | clinical · round_limit | 2/7/44 | approved_therapy, positive_clinical | 1.0 (2/2) | 183/28 | 22.1 | 3.60 | 39 (0) | BOUNDED REVIEW |
| bace1_ad | adaptive_warm | CHEMBL4822 (resolved) | clinical_precedent | clinical · round_limit | 2/7/44 | approved_therapy, positive_clinical | 1.0 (2/2) | 183/28 | 3.8 | 1.34 | 3 (62) | BOUNDED REVIEW |
| lrrk2_pd | baseline | CHEMBL1075104 (resolved) | clinical_precedent | clinical · follow_up_disabled | 0/0/0 | approved_therapy, positive_clinical, negative_or_safety | 1.0 (2/2) | 124/41 | 12.7 | 0.15 | 13 (0) | BOUNDED REVIEW |
| lrrk2_pd | adaptive_cold | CHEMBL1075104 (resolved) | clinical_precedent | clinical · round_limit | 2/3/49 | approved_therapy, positive_clinical, negative_or_safety | 1.0 (2/2) | 173/41 | 29.3 | 1.47 | 16 (0) | BOUNDED REVIEW |
| lrrk2_pd | adaptive_warm | CHEMBL1075104 (resolved) | clinical_precedent | clinical · round_limit | 2/3/49 | approved_therapy, positive_clinical, negative_or_safety | 1.0 (2/2) | 173/41 | 0.8 | 0.38 | 0 (55) | BOUNDED REVIEW |
| bcl2_scoliosis | baseline | CHEMBL4860 (resolved) | preclinical_validation | preclinical · follow_up_disabled | 0/0/0 | recent_development | 1.0 (1/1) | 47/0 | 35.7 | 0.10 | 27 (0) | BOUNDED REVIEW |
| bcl2_scoliosis | adaptive_cold | CHEMBL4860 (resolved) | preclinical_validation | preclinical · no_new_evidence | 1/1/0 | recent_development | 1.0 (1/1) | 47/0 | 34.5 | 0.25 | 28 (0) | BOUNDED REVIEW |
| bcl2_scoliosis | adaptive_warm | CHEMBL4860 (resolved) | preclinical_validation | preclinical · no_new_evidence | 1/1/0 | recent_development | 1.0 (1/1) | 47/0 | 1.4 | 0.14 | 2 (26) | BOUNDED REVIEW |
| ngly1_rare | baseline | CHEMBL4523429 (resolved) | preclinical_validation | preclinical · follow_up_disabled | 0/0/0 | none | 1.0 (1/2) | 75/4 | 12.4 | 0.19 | 13 (0) | BOUNDED REVIEW |
| ngly1_rare | adaptive_cold | CHEMBL4523429 (resolved) | preclinical_validation | preclinical · coverage_achieved | 0/0/0 | none | 1.0 (1/2) | 75/4 | 17.3 | 0.18 | 13 (0) | BOUNDED REVIEW |
| ngly1_rare | adaptive_warm | CHEMBL4523429 (resolved) | preclinical_validation | preclinical · coverage_achieved | 0/0/0 | none | 1.0 (1/2) | 75/4 | 0.5 | 0.18 | 0 (15) | BOUNDED REVIEW |
| invalid_gene | baseline | none (unknown) | unresolved | unresolved · target_unresolved | 0/0/0 | target_disease_association, genetic_mechanistic, approved_therapy, positive_clinical, negative_or_safety, programme_status, population_subtype, recent_development | None (0/0) | 0/0 | 0.6 | – | 3 (0) | INSUFFICIENT COVERAGE |
| invalid_gene | adaptive_cold | none (unknown) | unresolved | unresolved · target_unresolved | 0/0/0 | target_disease_association, genetic_mechanistic, approved_therapy, positive_clinical, negative_or_safety, programme_status, population_subtype, recent_development | None (0/0) | 0/0 | 0.5 | – | 3 (0) | INSUFFICIENT COVERAGE |
| invalid_gene | adaptive_warm | none (unknown) | unresolved | unresolved · target_unresolved | 0/0/0 | target_disease_association, genetic_mechanistic, approved_therapy, positive_clinical, negative_or_safety, programme_status, population_subtype, recent_development | None (0/0) | 0/0 | 0.0 | – | 0 (3) | INSUFFICIENT COVERAGE |
| unsupported_pair | baseline | CHEMBL274 (resolved) | unresolved | preclinical · follow_up_disabled | 0/0/0 | target_disease_association, genetic_mechanistic, population_subtype, recent_development | None (0/0) | 46/0 | 42.0 | 0.20 | 58 (0) | INSUFFICIENT COVERAGE |
| unsupported_pair | adaptive_cold | CHEMBL274 (resolved) | unresolved | preclinical · no_new_evidence | 1/4/0 | target_disease_association, genetic_mechanistic, population_subtype, recent_development | None (0/0) | 46/0 | 36.8 | 1.49 | 62 (0) | INSUFFICIENT COVERAGE |
| unsupported_pair | adaptive_warm | CHEMBL274 (resolved) | unresolved | preclinical · no_new_evidence | 1/4/0 | target_disease_association, genetic_mechanistic, population_subtype, recent_development | None (0/0) | 46/0 | 2.5 | 0.29 | 4 (58) | INSUFFICIENT COVERAGE |
| htt_huntington (held-out) | baseline | CHEMBL5514 (resolved) | clinical_precedent | clinical · follow_up_disabled | 0/0/0 | approved_therapy, positive_clinical, negative_or_safety | 1.0 (1/1) | 118/29 | 9.4 | 0.15 | 13 (0) | BOUNDED REVIEW |
| htt_huntington (held-out) | adaptive_cold | CHEMBL5514 (resolved) | clinical_precedent | clinical · round_limit | 2/3/47 | approved_therapy, positive_clinical, negative_or_safety | 1.0 (1/1) | 165/29 | 8.0 | 1.42 | 16 (0) | BOUNDED REVIEW |
| htt_huntington (held-out) | adaptive_warm | CHEMBL5514 (resolved) | clinical_precedent | clinical · round_limit | 2/3/47 | approved_therapy, positive_clinical, negative_or_safety | 1.0 (1/1) | 165/29 | 0.8 | 0.40 | 0 (43) | BOUNDED REVIEW |

### Per-case checks (adaptive cold run)

| Case | Identity | Routing | Expected need statuses | Material records in packet | Abstained | Gaps |
|---|---|---|---|---|---|---|
| ccr5_hiv | ✓ CHEMBL274; Ensembl ENSG00000160791; disease MONDO_0005109 | ✓ clinical_precedent / clinical | approved_therapy: ✓, positive_clinical: ✓, negative_or_safety: ✓ | 8 in, 5 beyond limit | ✓ abstained | none |
| pcsk9_hchol | ✓ CHEMBL2929; Ensembl ENSG00000169174; disease name only | ✓ clinical_precedent / clinical | approved_therapy: ✓, positive_clinical: ✓ | 9 in, 5 beyond limit | ✓ abstained | none |
| egfr_nsclc | ✓ CHEMBL203; Ensembl ENSG00000146648; disease MONDO_0005233 | ✓ clinical_precedent / clinical | approved_therapy: ✓, population_subtype: ✓ | 8 in, 2 beyond limit | ✓ abstained | none |
| bace1_ad | ✓ CHEMBL4822; Ensembl ENSG00000186318; disease MONDO_0004975 | ✓ clinical_precedent / clinical | negative_or_safety: ✓, programme_status: ✓ | 9 in, 1 beyond limit | ✓ abstained | none |
| lrrk2_pd | ✓ CHEMBL1075104; Ensembl ENSG00000188906; disease MONDO_0005180 | ✓ clinical_precedent / clinical | recent_development: ✓, programme_status: ✓ | 7 in, 1 beyond limit | ✓ abstained | none |
| bcl2_scoliosis | ✓ CHEMBL4860; Ensembl ENSG00000171791; disease MONDO_0005392 | ✓ preclinical_validation / preclinical | approved_therapy: ✓, genetic_mechanistic: ✓, positive_clinical: ✓ | 3 in, 0 beyond limit | ✓ abstained | none |
| ngly1_rare | ✓ CHEMBL4523429; Ensembl ENSG00000151092; disease MONDO_0800044 | ✓ preclinical_validation / preclinical | genetic_mechanistic: ✓ | 6 in, 0 beyond limit | ✓ abstained | none |
| invalid_gene | ✓ unresolved; Ensembl –; disease MONDO_0005109 | ✓ unresolved / unresolved | positive_clinical: ✓ | 0 in, 0 beyond limit | ✓ abstained | Exact target identity unresolved.; ClinicalTrials.gov search missing or failed; cannot establish pathway coverage.; Europe PMC search missing or failed; cannot establish pathway coverage.; Insufficient disease-specific primary biological support: need multiple distinct primary study groups with gen |
| unsupported_pair | ✓ CHEMBL274; Ensembl ENSG00000160791; disease MONDO_0007037 | ✓ unresolved / preclinical | target_disease_association: ✓, approved_therapy: ✓ | 0 in, 0 beyond limit | ✓ abstained | Insufficient disease-specific primary biological support: need multiple distinct primary study groups with gen |
| htt_huntington | ✓ CHEMBL5514; Ensembl ENSG00000197386; disease MONDO_0007739 | ✓ clinical_precedent / clinical | open (held-out) | 7 in, 1 beyond limit | ✓ abstained | none |

### Evidence recovered by follow-up (adaptive cold run)

- **pcsk9_hchol** — 37 new records (8 scoped as direct disease-specific, 0 registry). Searches: association follow-up → limit_reached, 13 new; gene identifier resolution → found, 1 new; disease identifier resolution → no_results, 0 new; association follow-up → limit_reached, 23 new. Most-cited direct records: MED:15654334 (2005, direct biological) “Low LDL cholesterol in individuals of African descent resulting from frequent nonsense mut”; MED:17452316 (2007, direct biological) “Binding of proprotein convertase subtilisin/kexin type 9 to epidermal growth factor-like r”; MED:17080197 (2006, direct biological) “Secreted PCSK9 decreases the number of LDL receptors in hepatocytes and in livers of parab”; MED:15805190 (2005, direct biological) “Decreased plasma cholesterol and hypersensitivity to statins in mice lacking Pcsk9.”.
- **bace1_ad** — 44 new records (15 scoped as direct disease-specific, 0 registry). Searches: clinical outcome follow-up → limit_reached, 14 new; compound outcome follow-up → found, 8 new; compound outcome follow-up → found, 2 new; registry-linked outcome publications → limit_reached, 5 new; clinical outcome follow-up → limit_reached, 15 new; compound outcome follow-up → found, 0 new; compound outcome follow-up → found, 0 new. Most-cited direct records: MED:25621019 (2014, direct biological) “BACE1 inhibitor drugs in clinical trials for Alzheimer's disease.”; MED:21900882 (2011, direct biological) “7,8-dihydroxyflavone, a small-molecule TrkB agonist, reverses memory deficits and BACE1 el”; MED:27001618 (2016, direct biological) “Novel osmotin inhibits SREBP2 via the AdipoR1/AMPK/SIRT1 pathway to improve Alzheimer's di”; MED:33622188 (2021, direct biological) “Electroacupuncture ameliorates beta-amyloid pathology and cognitive impairment in Alzheime”.
- **lrrk2_pd** — 49 new records (14 scoped as direct disease-specific, 0 registry). Searches: clinical outcome follow-up → limit_reached, 22 new; registry-linked outcome publications → limit_reached, 11 new; clinical outcome follow-up → limit_reached, 16 new. Most-cited direct records: MED:26407721 (2015, direct biological) “MLi-2, a Potent, Selective, and Centrally Active Compound for Exploring the Therapeutic Po”; MED:25353650 (2014, direct biological) “Discovery and preclinical profiling of 3-[4-(morpholin-4-yl)-7H-pyrrolo[2,3-d]pyrimidin-5-”; MED:31906147 (2019, direct biological) “Celastrol Inhibits Dopaminergic Neuronal Death of Parkinson's Disease through Activating M”; MED:28096185 (2017, direct biological) “Transcriptomic profiling of purified patient-derived dopamine neurons identifies convergen”.
- **htt_huntington** — 47 new records (20 scoped as direct disease-specific, 0 registry). Searches: clinical outcome follow-up → limit_reached, 21 new; registry-linked outcome publications → limit_reached, 7 new; clinical outcome follow-up → limit_reached, 19 new. Most-cited direct records: MED:19240687 (2009, direct biological) “Nonallele-specific silencing of mutant and wild-type huntingtin demonstrates therapeutic e”; MED:22031240 (2011, direct biological) “Preclinical safety of RNAi-mediated HTT suppression in the rhesus macaque as a potential t”; MED:23349832 (2013, direct biological) “MicroRNA-22 (miR-22) overexpression is neuroprotective via general anti-apoptotic effects ”; MED:30007561 (2018, direct biological) “AAV5-miHTT Gene Therapy Demonstrates Broad Distribution and Strong Human Mutant Huntingtin”.

### Independent reference checks (rubric only)

| Case | PMID | Exists | Title | Retrieved (baseline → adaptive) | In packet (adaptive) |
|---|---|---|---|---|---|
| ccr5_hiv | 18832244 | None |  | ✓ → ✓ | ✓ |
| ccr5_hiv | 20151839 | None |  | ✓ → ✓ | ✓ |
| pcsk9_hchol | 28304224 | True | Evolocumab and Clinical Outcomes in Patients with Cardiovascular Disease. | ✓ → ✓ | ✗ |
| pcsk9_hchol | 30403574 | True | Alirocumab and Cardiovascular Outcomes after Acute Coronary Syndrome. | ✓ → ✓ | ✗ |
| egfr_nsclc | 29151359 | True | Osimertinib in Untreated EGFR-Mutated Advanced Non-Small-Cell Lung Cancer. | ✓ → ✓ | ✓ |
| bace1_ad | 29719179 | True | Randomized Trial of Verubecestat for Mild-to-Moderate Alzheimer's Disease. | ✓ → ✓ | ✓ |
| bace1_ad | 30970186 | True | Randomized Trial of Verubecestat for Prodromal Alzheimer's Disease. | ✓ → ✓ | ✓ |
| lrrk2_pd | 35675433 | True | Preclinical and clinical evaluation of the LRRK2 inhibitor DNL201 for Parkinson' | ✓ → ✓ | ✓ |
| lrrk2_pd | 36807624 | True | LRRK2 Inhibition by BIIB122 in Healthy Participants and Patients with Parkinson' | ✓ → ✓ | ✓ |
| bcl2_scoliosis | 31337422 | True | Suv39h1 promotes facet joint chondrocyte proliferation by targeting miR-15a/Bcl2 | ✓ → ✓ | ✓ |
| ngly1_rare | 24651605 | True | Mutations in NGLY1 cause an inherited disorder of the endoplasmic reticulum-asso | ✓ → ✓ | ✗ |
| ngly1_rare | 25605922 | True | Endo-β-N-acetylglucosaminidase forms N-GlcNAc protein aggregates during ER-assoc | ✓ → ✓ | ✓ |
| htt_huntington | 31059641 | True | Targeting Huntingtin Expression in Patients with Huntington's Disease. | ✓ → ✓ | ✓ |


## 5. Missing evidence identified and recovered

- **Rare / gene-named disorder (NGLY1 deficiency).** The previous audit's open miss, PMID 25605922
  (ENGase knockout rescue in Ngly1-defective cells), was excluded because the abstract names the
  gene, not the disease. The general fix is `gene_defined_terms`: for a disorder named after its
  own gene ("<GENE> deficiency/disorder/syndrome/related"), loss-of-function wording about that gene
  ("Ngly1-defective", "mutation of the human NGLY1 gene", knockout, −/−) counts as a disease
  mention. It is deliberately *not* applied to "<GENE>-mutant <tissue cancer>" names, where the
  same wording appears in unrelated cancers. The record is now retrieved in the initial pass and the
  need statuses show NGLY1 as a preclinical pair with coverage achieved and no follow-up needed.
- **Held-out pair (Huntington disease / HTT, chosen after implementation).** The first run resolved
  nothing: ChEMBL's search for "HTT" returns both huntingtin (CHEMBL5514, gene symbol HTT) and the
  serotonin transporter (CHEMBL228, whose historical alias is 5-HTT), and the resolver refused the
  tie. Two general corrections came out of it: (1) a tie between exact candidates is broken by the
  component's *current* `GENE_SYMBOL` synonym type, never by a historical alias, and a residual tie
  still resolves nothing; (2) a gene verified by Ensembl or by an exact Open Targets symbol match but
  absent from ChEMBL's single-protein targets gets `resolution_status = gene_verified`, so registry
  and literature retrieval proceed by gene symbol with the ChEMBL gap stated explicitly instead of
  the whole investigation being skipped. This is the RNA/gene-modality blind spot the earlier audit
  listed as open (SMN2, gene therapy programmes). On the fixed code the held-out pair resolves
  CHEMBL5514, is routed to the clinical pathway, retrieves the reference tominersen phase 1/2a
  record (PMID 31059641), and follow-up adds dozens of direct records including the registry
  programme status.
- **Recent developments (LRRK2, BACE1, PCSK9, HTT).** Dated retrieval plus the recent-development
  follow-up now surface 2024–2026 direct records for each clinical pair (see the *recent_direct*
  lists in the per-case JSON). For LRRK2 the planner reports `recent_development` as satisfied only
  when a dated record carries consequential wording; otherwise it stays *partial* with the note that
  a recent outcome may still be unretrieved — it does not assert that no development happened.
- **Beyond-cutoff omissions.** For every clinical pair the planner flags material records (landmark
  positive and negative trials, the most recent dated direct record, stopped trials) and the packet
  admits them beyond the stratified cutoff; records a bounded packet still cannot carry are listed
  per need, and a need with no representative record becomes a coverage gap instead of a silent
  omission.
- **Retrieval failure vs absence.** Ensembl outages (frequent during validation) no longer abort an
  investigation; the gap is stated and resolved by the Open Targets exact-pair identity check.
  Failed follow-up searches are recorded as failed, never cached, and leave the need
  `unverifiable`.

## 6. Remaining omissions

- `approved_therapy` stays *unmet* for BACE1, LRRK2 and HTT because ChEMBL curates no phase-4
  compound for those targets in this disease; that is correct today but the bounded compound set
  (15 of N mechanism compounds) is not exhaustive, and non-ChEMBL modalities are not represented.
- `positive_clinical` stays *partial* for BACE1/LRRK2/HTT: interventional records exist but no
  conclusion carries a positive triage signal. The triage regexes are deliberately narrow; a
  positive outcome phrased differently would need reading, which is what the "partial" label asks
  the reviewer to do.
- PCSK9's `target_disease_association` stays *partial*: "hypercholesterolemia" has no exact MONDO or
  EFO label (OLS returns the HP phenotype and familial subtypes), so no disease identifier is
  guessed and the Open Targets exact-pair query cannot run. Literature association is present.
- **Retrieved but not in the packet.** PCSK9's FOURIER (28304224) and ODYSSEY OUTCOMES (30403574)
  and NGLY1's original patient series (24651605) are retrieved in every mode but do not reach the
  bounded packet: the positive-clinical material slots go to records whose *conclusion section* carries
  a positive triage signal, and these abstracts are not split into a "Conclusions" section, so they
  carry none. The planner's packet audit lists them under the need's evidence ids and the omission
  reasons; a reviewer sees them, but Gemini would not. Material selection should also weigh
  citation rank among direct clinical records without a conclusion split — left open rather than
  tuned to these two titles.
- Two CCR5 rubric lookups show `exists: None` in the final report: the independent Europe PMC
  reference check itself timed out during that pass (it returned `True` with titles in the first
  pass). Both records were retrieved and placed in the packet in every run.
- Sponsor announcements and non-FDA regulators are not searched (no permitted API); the plan says so
  on every report. Registry-posted results are indexed by endpoint title only; numbers are not
  interpreted.
- Follow-up rounds ingest some general reviews that mention the gene and disease (scoped as
  indirect context); they never ground coverage or enter the packet, but they inflate publication
  counts.
- Europe PMC `limit_reached` is reported for most follow-up queries (25 of N hits); deeper paging
  is a budget decision left to the operator.

## 7. Scientific interpretation errors found and guarded

No paid Gemini call was made, so no new model interpretation was produced. The deterministic
adjudicator layer was extended for the error classes the earlier audits recorded (grouped approval
statements, unqualified "untested" claims, cross-population causality) with four new checks, each
unit-tested against the recorded BACE1 Gemini audit so that previously accepted, correctly bounded
claims still pass: stance/excerpt direction, disease applicability of cited sources (a source that
visibly names the disease is accepted even when its lexical scope flag is uncertain), causal wording
over an observed association, and universal/exclusive claims. The omitted-contradiction check names
direct opposite-direction records missing from the packet and adds them for the revision round; an
unverified efficacy/safety claim gets one targeted retrieval. The prior-art check now withholds a
proposal whose question *and* mechanism/readout or hypotheses are both matched by an existing record
("substantially answered"), and labels every surviving proposal potentially informative and
unvalidated.

## 8. Before/after retrieval times

See the table in §4 (`Retrieval s`, `Loop s`, requests and cache hits). The controlled cost of the
new work is the loop column: between 0.1 s (nothing open, or a single no-result query) and 3.6 s
(BACE1: two rounds, seven searches, 44 new records; an earlier pass with slower Europe PMC
responses measured up to 11 s), against initial cold retrievals of 8–83 s in the final run (up to
196 s in an earlier pass while Ensembl was degraded) that are dominated by registry full-record
fetches. The per-host Ensembl policy (two attempts, 10 s read timeout) bounds that cost. Warm runs
reuse the cached follow-up responses as well (6–9 s for the three largest pairs, under 4 s for the
rest), so a retry of the same pair is not penalised by the loop. Extra upstream requests per cold
case attributable to follow-up: 0 (CCR5, EGFR, NGLY1, invalid gene) to 7 (BACE1).

## 9. Additional API calls and model usage

- Public APIs: at most `ADAPTIVE_MAX_SEARCHES_PER_ROUND` (6) × `ADAPTIVE_MAX_ROUNDS` (2) extra
  requests per investigation, plus full-record verification for newly found trials (batched, 50 per
  request) and up to two identifier lookups for manual pairs. Measured: 0–7 extra upstream requests
  per cold case (requests column, baseline vs adaptive cold). Rate limits are the shared client's
  (350 ms per host, 1.25 s for ClinicalTrials.gov); publication follow-ups run through the bounded
  pool (4 workers).
- Gemini: unchanged model and thinking level; the normal investigation still uses three to five
  calls. The optional planning call (`AI_PLANNING_CALL=true`, off by default) is a sixth role that
  shares the same `AI_MAX_CALLS` budget and must be explicitly authorised with `use_ai`; its output
  is search terms only. No paid call was made in this work; zero-paid-call offline playback is
  unchanged (the recorded demo shows "no evidence discovery plan recorded").

## 10. Reliability tests (real Flask app, scripted public sources)

`tests/test_adaptive_reliability.py` drives `POST /api/investigations` through the production
Flask app, the real investigator, planner loop and SQLite source cache, with only the HTTP transport
scripted: end-to-end follow-up with cache reuse and manual refresh; transient 503s retried, never
cached, reported as *failed*/unverifiable and recovered on the next request; stale cache entries
refetched after expiry; incomplete/malformed trial records degrade to explicit stop-reason states
(and no longer crash the run); unknown targets abstain without disease-only evidence; a gene-registry
outage continues as a retrieval failure; search limits and budget exhaustion are recorded. Approval
and screening restrictions are untouched (the existing workbench tests still pass).

## 11. Verification run

- Python: `pytest tests devils_advocate/tests` — 358 passed (ten new test modules/cases cover the
  planner, loop, adjudicator rules, prior-art facets, request path and reliability).
- TypeScript: `tsc --noEmit` clean; `eslint .` clean (generated `.next-*` build dirs ignored).
- Production build: `next build` succeeds.
- Browser: Playwright 12/12 (new `adaptive.spec.ts` renders the plan panel, follow-up provenance,
  stage timings and the refresh control; existing recorded-flow, pathway and evidence specs pass).
- Live benchmark: `validation/adaptive/benchmark_report.json`, `benchmark_summary.md`, rubric in
  `rubric.json`; per-case job responses are reproducible and gitignored.

## 12. Remaining limitations

- Need statuses are deterministic retrieval-coverage labels built from lexical triage; "satisfied"
  means records of that kind were retrieved and scoped, not that the science is settled.
- The reference rubric is small and implementer-selected (12 PMIDs across 8 pairs); recall on it is
  landmark recall, not literature recall.
- Only one held-out pair was tested; it exposed two identity defects, which suggests more unfamiliar
  pairs would expose more. The planner itself did not need pair-specific changes for it.
- Timings are single live runs on a shared network with visibly degraded Ensembl service; they are
  not a controlled benchmark.
- The Gemini planning role and the revision-round packet expansion were exercised with scripted
  runners only; their effect on real model output is unmeasured until paid calls are authorised.
- Progress polling works on a single-instance host; on multi-instance hosting the poller may land on
  another instance and reports "unavailable", by design.
