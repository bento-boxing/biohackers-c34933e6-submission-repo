# Molecule ranking validation

Scope: the compound-screening stage (`POST /api/screen`) that follows a researcher's screening approval.
Target Scout's target ranking, the Devil's Advocate / Gemini reasoning, the evidence adjudicator and
the approval flow are unchanged. Nothing described here predicts efficacy or clinical success.

Evaluation data: `validation/molecule_ranking/EGFR.json` and `DRD2.json`, produced by
`python -m devils_advocate.molecule_benchmark` against live ChEMBL on 2026-11-08 (no paid calls).

## 1. What was wrong

| Finding (audit) | Before | Now |
|---|---|---|
| Approvals selected by timestamp | `/api/screen` and `/api/shortlists` looked up `approval_ts`; two approvals in one second resolved to the newest line | Every approval carries an immutable `approval_id` (uuid4). The legacy endpoints require it; the stateless `/api/screen` requires `approval_id`, `disease_id` and `target_id` and checks them against the HMAC-signed approval, whose payload also records the originating `decision_id` and `action == approve_screening`. Regression tests: `tests/test_api.py::test_screen_selects_the_exact_approval_when_two_were_created_in_the_same_second`, `devils_advocate/tests/test_workbench.py::test_screen_requires_the_exact_approval_id_disease_target_and_decision`. |
| 5,000-row cut in ChEMBL's default order | The first five pages of potent records, whatever order ChEMBL returned them in; EGFR has 16,683 such records | Stage 1 orders by `pchembl_value` descending, so truncation never drops a record stronger than any retrieved one; the cutoff and total are reported and the result is labelled partial |
| Max pChEMBL as "the" potency, assay context dropped | `best_per_molecule` kept the single highest value and the assay type | Median of exact (`=`) binding-assay measurements of one standard type (IC50, Ki, Kd, EC50); types never pooled; sparse/conflicting flags; censored and functional records counted separately; every retained record keeps activity, assay, target and document identifiers |
| QED discarded | Not requested from ChEMBL | `qed_weighted` retrieved and shown; missing ≠ zero |
| Phase not indication-qualified | `max_phase` shown as-is | ChEMBL `drug_indication` rows matched to the approved disease by EFO/MONDO id or name; statuses `matched`, `other_indications_only`, `no_indication_records`, `preclinical`, `not_checked` |
| No selectivity | — | Observed off-target records for ten shortlisted molecules; targets and assays actually tested are counted; windows only against comparable measurements; absence of records is labelled "untested", never "selective" |
| Missing Ro5 sorted last | `99` violations when absent | Missing factors are excluded from the composite and listed; they never score zero |
| No benchmark | — | This document and the JSON under `validation/molecule_ranking/` |

## 2. Implementation

Staged retrieval (`pipeline/screening/pipeline.py`):

1. **Ordered potent records** (`chembl.ranked_activities`): `pchembl_value >= 6`, `order_by=-pchembl_value`,
   at most 5,000 rows. Coverage record: `total_count`, `retrieved`, `complete`, `cutoff_pchembl`,
   `selection_method`. Molecules whose every measurement is weaker than the cutoff are not retrieved and
   the response says so.
2. **Candidate pool**: the top 50 molecules by maximum pChEMBL (the preserved baseline) united with the
   top 50 by preliminary median, so both rankings are reproducible from the same pool (50–100 molecules).
3. **Complete on-target records** for the pool (`chembl.molecule_activities` with the target), which adds
   measurements below the cutoff and censored records (`>`/`<`) so the aggregate is not biased by the cut.
4. **Molecule properties** (QED, Ro5, phase, first approval) and **drug indications** for phased molecules.
5. **Off-target records** for the ten candidates that lead under the default rubric before selectivity is
   known (fixed independently of the requested rubric, so recorded demos and objectives share one
   shortlist and a request cannot steer retrieval). Off-target names come from `target.json`.
6. **Prioritisation** under the requested rubric; baseline ranks assigned by the old ordering.

Potency (`pipeline/screening/potency.py`): primary type = comparable type with most exact binding
measurements (ties: IC50, Ki, Kd, EC50); aggregate = median; `sparse` when n = 1; `conflicting` when
exact values span ≥ 1 log unit; up to 25 strongest records kept with identifiers.

Selectivity (`pipeline/screening/selectivity.py`): per off-target, the median of exact binding
measurements of the on-target primary type; window = on-target median − strongest comparable off-target
median; records of other types are listed as incomparable. `evidence` ∈ {`observed_window`,
`no_comparable_off_target_records`, `no_off_target_records`, `not_assessed`}.

Rubric (`pipeline/screening/rubric.py`), explicitly a heuristic:

| Factor | Score | Missing when |
|---|---|---|
| potency | (median − 5)/4 clamped to 0..1; −0.10 if a single measurement; −0.10 if conflicting | no exact binding measurement → the candidate sorts after every quantified one |
| drug_likeness | QED, else 1 − 0.25 × Ro5 violations | neither recorded |
| selectivity | (window + 1)/3 clamped | no comparable off-target record, or not assessed |
| clinical | max_phase/4 (preclinical = 0, a known state); under `repurposing`, other-indication development counts half | never (phase absence is a state) |

Objectives: `balanced` (0.45/0.20/0.25/0.10), `novel_candidates` (0.50/0.25/0.25/0, approved drugs not
preferred), `repurposing` (0.35/0.15/0.20/0.30). Weights are overridable per request. The composite is a
weighted mean over the factors a candidate has; `factors.missing` and `rank_reason` state what was excluded.

## 3. Scientific assumptions

* pChEMBL is comparable within one standard type and assay type; medians are robust to the stray
  high values that drove the old ranking. Different assay formats (cell-free vs cellular, mutant vs
  wild-type constructs) still differ: the assay descriptions are preserved so a reviewer can check.
* QED and Lipinski's rule of five are property heuristics for oral small molecules, not success
  predictors; they are shown as such.
* A development phase is human-exposure precedent. Only indications that ChEMBL records for the
  approved disease count as development "for" that disease; everything else is reported as other.
* Off-target evidence is whatever ChEMBL holds. Untested targets are unknown. The window is a
  descriptive summary of observed data and is not a selectivity index.

## 4. Baseline comparison (EGFR, DRD2)

Retrieval coverage:

| | EGFR (CHEMBL203, NSCLC) | DRD2 (CHEMBL217, Parkinson disease) |
|---|---|---|
| potent records (pChEMBL ≥ 6) | 16,683 | 11,896 |
| legacy: molecules in first 5,000 rows | 3,024 | 3,528 |
| ordered: molecules in first 5,000 rows | 2,868 | 2,972 |
| ordered cutoff pChEMBL | 8.15 | 7.27 |
| ordered baseline top-50 molecules absent from legacy retrieval | 35 / 50 | 34 / 50 |
| overlap of legacy top-50 with ordered top-50 | 28 % | 22 % |
| max pChEMBL range, legacy top-50 vs ordered top-50 | 9.60–11.00 vs 10.12–11.00 | 9.30–10.52 vs 9.92–11.00 |

The old cut silently omitted most of the strongest molecules on both targets.

Does the ranking change (rubric vs potency-only baseline, same pool of 69)?

| objective | EGFR top-10 overlap / Spearman / mean |Δrank| | DRD2 |
|---|---|---|
| balanced | 0.4 / 0.02 / 22.6 | 0.0 / −0.21 / 27.5 |
| novel_candidates | 0.4 / −0.03 / 22.9 | 0.0 / −0.36 / 29.3 |
| repurposing | 0.3 / 0.24 / 19.8 | 0.2 / −0.07 / 25.7 |

Yes: the additional factors reorder the pool almost completely. Most of the change comes from using the
median instead of the maximum (EGFR: 26 of 69 molecules have a maximum ≥ 1 log unit above their median;
33 are flagged conflicting, 17 rest on a single measurement; DRD2: 19, 21 and 22).

Ablations (balanced rubric with one factor removed, vs the full balanced ranking):

| removed factor | EGFR top-10 overlap / Spearman / mean |Δrank| | DRD2 |
|---|---|---|
| potency | 0.4 / 0.38 / 16.1 | 0.5 / 0.29 / 17.8 |
| drug_likeness | 0.7 / 0.86 / 7.7 | 0.3 / 0.54 / 14.7 |
| selectivity | 0.9 / 0.99 / 0.6 | 0.3 / 0.89 / 4.7 |
| clinical | 0.9 / 0.94 / 3.8 | 0.7 / 0.82 / 8.4 |

Potency dominates, drug-likeness is second, clinical matters at 10 % weight, and selectivity moves few
molecules because few have comparable off-target data (below).

Stability under missing data (30 % of the pool stripped, five seeds, vs the full balanced ranking):

| perturbation | EGFR mean top-10 overlap / mean |Δrank| | DRD2 |
|---|---|---|
| drop QED and Ro5 | 0.70 / 6.2 | 0.54 / 5.6 |
| drop selectivity | 0.98 / 0.2 | 0.80 / 2.0 |
| drop both | 0.62 / 8.8 | 0.30 / 8.2 |

Removing a factor from a candidate renormalises its remaining weights, so missing drug-likeness can move
a candidate either way. That is visible (the warnings column) rather than hidden, but it means the
ranking is sensitive to missing property data; a reviewer should compare the baseline view before acting.

Agreement with manually reviewed compounds (presence in the 69-molecule pool, ranks):

| compound | baseline | balanced | novel | repurposing | median (n) / max | indication | off-target |
|---|---|---|---|---|---|---|---|
| afatinib (EGFR) | 38 | 22 | 53 | 1 | 8.96 (105) / 10.21 | matched | 638 targets tested, window −0.04 |
| osimertinib | 6 | 48 | 64 | 3 | 7.92 (221) / 10.70 | matched | not shortlisted |
| erlotinib | 15 | 56 | 65 | 5 | 7.52 (180) / 10.54 | matched | not shortlisted |
| lapatinib | 33 | 55 | 66 | 4 | 7.97 (74) / 10.22 | matched (NSCLC trials recorded) | not shortlisted |
| gefitinib, dacomitinib, icotinib | not in pool (their maxima fall below the ordered top-50) |
| rotigotine (DRD2) | 30 | 1 | 2 | 1 | 10.22 (3) / 10.22 | matched | 26 targets, window +1.82 |
| pramipexole | 2 | 57 | 64 | 4 | 7.31 (14) / 10.83 | matched | not shortlisted |
| haloperidol | 48 | 45 | 60 | 12 | 8.81 (102) / 9.92 | other indications only | 128 targets, window −0.49 |
| ropinirole, apomorphine, bromocriptine, cabergoline, risperidone, aripiprazole | not in pool |

Interpretation checks: indication status matched the manual expectation for 3/4 EGFR and 3/3 DRD2 known
compounds; the one disagreement (lapatinib) is ChEMBL recording NSCLC clinical trials, which the code
reports faithfully as "matched" at the recorded phase — the manual expectation was the stricter one.
Afatinib's window of −0.04 across 638 tested targets is the correct reading of a pan-ErbB inhibitor;
haloperidol's −0.49 across 128 targets is correct for a promiscuous antipsychotic. The approved EGFR drugs
rank low under `balanced` because their medians over 100–220 measurements (7.5–9.0) are honest, whereas
the unnamed compounds above them rest on one to three measurements at 10–11; the `repurposing` objective
surfaces the approved drugs, and the sparse flag marks the others.

False confidence from thin selectivity evidence (balanced top-10): EGFR 8/10 have no off-target records
at all and 1 is outside the shortlist; DRD2 7/10 are outside the shortlist. In every case the selectivity
factor is `None`, listed as missing, and the label reads "untested, not selective"; no candidate was
scored on selectivity without an observed window (`scored_without_window = 0` on both targets).

## 5. Remaining limitations

* Stage 1 is still capped at 5,000 rows (EGFR cutoff 8.15): molecules whose strongest measurement is
  weaker than the cutoff are never seen. The cutoff is reported; raising the cap costs one request per
  1,000 rows.
* Single-measurement and conflicting entries are common at the top of the ordered list. The rubric
  penalises them lightly and flags them; it does not try to judge assay quality.
* Selectivity is retrieved for ten molecules and, for a molecule with thousands of records, up to 3,000
  rows; truncation is labelled `partial`. Off-target comparison uses the on-target primary type only.
* Indication matching relies on ChEMBL's EFO/MeSH terms and exact id/name matches; a child or parent
  disease term is reported as "other".
* QED/Ro5 are absent for some ChEMBL entries; those candidates are ranked on fewer factors and say so.
* The recorded demo (LRRK2) replays one shortlist; objectives change the ranking but not retrieval.
* No claim is made that any ranking predicts efficacy, safety or clinical success.
