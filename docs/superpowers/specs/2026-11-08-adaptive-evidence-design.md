# Adaptive evidence discovery and verification — design

Date: 2026-11-08. Branch: `feat/adaptive-evidence` (from `prod`). Scope: `backend/devils_advocate/`
(Target Challenger) plus the Next.js panels that render its report. Target Scout ranking and the
screening scorer are untouched.

## Intent

The cross-disease audit showed the challenger cannot tell whether what it retrieved is *enough*
for the conclusion it is about to draw. Every miss had the same shape: a fixed, single-pass
query set, a post-hoc coverage gate that can only say "insufficient", and a packet cutoff that
drops records the gate never looked at. The fix is a general loop, not per-disease patches:

```
initial retrieval → plan what must be established → assess each need against what was retrieved
→ targeted follow-up searches for unmet needs → reassess → stop (bounded) → build packet from the plan
```

## Root causes found in the audit (prod branch)

| # | Symptom in audit | Root cause in code |
|---|---|---|
| 1 | CCR5 missed MOTIVATE/MERIT until a hand fix | `literature.py` runs one fixed query family; nothing re-queries when the direct-clinical stratum is empty. |
| 2 | LRRK2 missed recent development outcomes | No publication or trial dates are parsed (`Publication`/`Trial` have no date fields), so nothing can prioritise or even detect "recent"; no compound-specific outcome search exists. |
| 3 | BCL2/scoliosis needed a different route | Pathway choice exists (`check_coverage`) but preclinical needs (genetic, cellular, model evidence) are never searched for explicitly; only incidental hits are scoped. |
| 4 | Experiments repeated documented work | `check_prior_art` searches the question only; mechanism and readout facets and competing hypotheses are not searched. |
| 5 | Retrieved publications omitted from the packet | `select_evidence` is a 4-publication/6-trial stratified cutoff with no notion of a *material* record; omissions beyond the cutoff are silent unless a direction-signal facet happens to flag them. |
| 6 | Retrieval failure vs absence | Mostly handled (failed searches are audited, not cached), but the gate cannot distinguish "unmet because the search failed" from "unmet because nothing exists". |
| 7 | Manual refresh unreachable | `run_investigation` honours `refresh_evidence`, but neither the request model nor the UI exposes it. |
| 8 | Progress invisible | Synchronous request; the UI shows elapsed seconds only; stage timings exist only for HTTP sources. |

## Goals

- A deterministic **Evidence Discovery Planner** that, for any pair, lists the needs an
  investigation must establish and tracks each need's status with evidence identifiers.
- A bounded **gap-resolution loop** (default two follow-up rounds, configurable) that issues
  targeted searches only for unmet needs, records every search, and stops with a stated reason.
- **Dated, tiered development evidence**: registry status, registry-posted results, peer-reviewed
  outcomes, regulatory decisions; sponsor announcements reported as *unavailable* rather than
  invented.
- **Packet audit**: planner-flagged material records enter the packet beyond the cutoff (bounded),
  with a stated reason for every inclusion and omission.
- **Adjudicator rules** that check stance direction, disease/population applicability,
  causal-vs-observed wording, exclusivity, and omitted contradictory evidence, and that can pull
  omitted material records into the revision round.
- **Prior-art check** over question, mechanism, readout and competing hypotheses, labelled
  "potentially informative and unvalidated".
- Performance preserved: bounded parallelism, per-source cache expiry, no transient failure cached,
  manual refresh exposed, per-stage timings recorded, backend progress visible locally.
- Zero paid calls in tests and in the offline demo; optional Gemini planning call behind an
  explicit flag and the existing call budget.

## Non-goals / anti-goals

- No hard-coded answers for the benchmark pairs anywhere in production code. Reference PMIDs live
  only in the benchmark rubric under `validation/`.
- No change to Target Scout ranking, screening scoring, the Gemini model, or the thinking level.
- No new hosting dependency: everything still runs inside one stateless request.
- Not a systematic review; the planner reports what it could not search.

## Architecture

New module `evidence_planner.py`:

- `EvidenceNeed` (key, label, kind, status ∈ {satisfied, partial, unmet, not_applicable,
  unverifiable}, evidence_ids, searches, note). Keys: `target_disease_association`,
  `genetic_mechanistic`, `approved_therapy`, `positive_clinical`, `negative_or_safety`,
  `programme_status`, `population_subtype`, `recent_development`, `unresolved_uncertainty`.
- `build_plan(result)` → `EvidencePlan` with needs derived from verified identifiers and the
  clinical/preclinical stage (advanced compounds or disease-matched trials ⇒ clinical-stage).
- `assess_plan(result, plan)` → statuses from existing annotations (`evidence_scope`,
  `direction_signals`, approvals, trial dates/results, publication dates). Failed searches mark a
  need `unverifiable`, never `satisfied`/absent.
- `followup_searches(result, plan, round)` → bounded list of `(need_key, source, operation,
  params)` for unmet/partial needs only. Query vocabulary: disease terms and ontology aliases,
  gene symbol and verified aliases, compound names/synonyms, ChEMBL IDs, NCT IDs, outcome
  vocabulary (direction-neutral: efficacy/primary endpoint/safety/discontinued/futility), model
  vocabulary for preclinical needs (knockout/knockdown/mouse/iPSC/variant). Sources: Europe PMC,
  ClinicalTrials.gov, Open Targets (identifier resolution for manual pairs), ChEMBL.
- `resolve_loop(client, result, max_rounds)` runs assess → search → ingest → reassess, with
  `client.remaining_seconds()` checks; stop reasons: `coverage_achieved`, `no_actionable_gaps`,
  `no_new_evidence`, `round_limit`, `budget_exhausted`, `cancelled`.
- Optional Gemini planning: `AI_PLANNING_CALL=true` plus `use_ai` and an unused call in the
  budget; the model returns search terms only, which are executed and audited like any other
  follow-up. Never evidence.

Model additions (all optional fields, backward compatible with saved fixtures):
`Publication.publication_date`, `Publication.evidence_tier`; `Trial.start_date`,
`Trial.completion_date`, `Trial.last_update_date`, `Trial.results_posted_date`,
`Trial.evidence_tier`; `Investigation.evidence_plan`; `Investigation.stage_timings`.

Coverage/packet: `select_evidence` takes planner `material_ids`; they are appended beyond the
cutoff up to `AI_MAX_MATERIAL_EXTRA` (default 4) with the reason recorded. `check_coverage` adds
`facets['evidence_plan']` and a gap when a material record was retrieved but could not fit.

Adjudicator (`validate_ai_claim`): stance/excerpt direction check, population-applicability
check when cited sources are `disease_match=uncertain`, causal-wording check for interpretation
claims whose sources only report association, extended exclusivity/universal patterns, and an
omitted-contradiction objection when the full collection holds direct negative evidence the
packet lacks. `run_ai_reasoning` pulls those records into the revision bundle (bounded).

Prior art: `check_prior_art` runs up to three targeted searches (question, mechanism+readout,
competing hypotheses), computes facet overlap, and labels every surviving proposal
"potentially informative and unvalidated".

Server/UI: `ChallengeRequest.refresh_evidence`, `progress_token` with
`GET /api/investigations/progress/<token>` (file under the runtime dir; reported as unavailable
when the host cannot serve it), a refresh checkbox, a progress stage list, and an
"Evidence discovery plan" panel (needs, statuses, rounds, searches, stop reason, timings).

## Evaluation

`adaptive_benchmark.py` runs the nine spec cases plus one held-out pair through the real
Next → Flask → SQLite-cache path with rounds=0 (baseline) and rounds=2, and reports identity
checks, pathway routing, reference-record recall (rubric only), need statuses, packet
inclusion, abstention, retrieval seconds and upstream request counts. Results and limitations go
to `devils_advocate/ADAPTIVE_EVIDENCE_VALIDATION.md`.

## Builder's calls (not agreed with the user, made here)

- Follow-up rounds default to 2 (`ADAPTIVE_MAX_ROUNDS`), at most 6 searches per round.
- "Recent" means a publication or registry update within the last three years from the request
  date (`ADAPTIVE_RECENT_YEARS`).
- Sponsor press releases are not fetched (no permitted API); the need is marked unverifiable and
  the limitation is shown.
