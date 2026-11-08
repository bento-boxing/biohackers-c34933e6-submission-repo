# Adaptive evidence — implementation plan

Spec: `docs/superpowers/specs/2026-11-08-adaptive-evidence-design.md`. All tests offline; no paid calls.

1. **Dates and tiers** — parse Europe PMC `firstPublicationDate`/`pubYear` and ClinicalTrials.gov
   status-module dates into new optional model fields; derive `evidence_tier`. Tests: parser
   fixtures with and without dates; legacy fixtures still validate.
2. **Planner** — `evidence_planner.py`: `build_plan`, `assess_plan`, `followup_searches`,
   `ingest`, `resolve_loop`. Tests: clinical vs preclinical plans; unmet→search generation;
   failed search ⇒ `unverifiable`; loop stops on each reason; no search for satisfied needs;
   budget stop; new evidence deduplicated into the investigation.
3. **Pipeline integration** — `investigate_target` runs the loop after initial retrieval with
   `ADAPTIVE_MAX_ROUNDS`; stage timings recorded; identifier resolution for manual pairs
   (Open Targets symbol→Ensembl, OLS name→MONDO) when IDs are absent.
4. **Packet** — material records beyond cutoff with reasons; coverage facet and gap.
5. **Adjudicator rules** — stance direction, population applicability, causal wording,
   exclusivity, omitted contradiction with bounded bundle expansion in the revision round.
6. **Prior art** — three facet searches, facet overlap, "potentially informative and unvalidated".
7. **Optional Gemini planning call** — flag-gated, schema-bound, search terms only.
8. **Server + UI** — `refresh_evidence`, progress token endpoint, plan panel, refresh checkbox,
   progress stages, contracts; vitest/tsc/lint/build; Playwright fixture test for the plan panel.
9. **Benchmark** — `adaptive_benchmark.py` + rubric JSON under `validation/adaptive/`; run live
   baseline vs adaptive through Next → Flask; pick the held-out pair after step 8.
10. **Reliability tests** — transient failures, missing publications, incomplete trial records,
    stale cache, conflicting sources, unknown target, partial retrieval, search limits.
11. **Deliverable** — `devils_advocate/ADAPTIVE_EVIDENCE_VALIDATION.md`.
