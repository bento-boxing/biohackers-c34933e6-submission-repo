# Molecule Screening Fix and Upgrade — Implementation Plan

**Goal:** Make /api/screen safe (unique approval id), retrieve ChEMBL evidence without silently dropping strong molecules, and rank candidates on four separately displayed, heuristic factors with a preserved potency-only baseline.

**Branch:** feat/molecule-screening (from prod 4d2cca8). No commits/pushes without permission.

**Constraints:** Target Scout ranking untouched. Devil's Advocate / Gemini / adjudicator untouched. Recorded mode never hits the network (re-record LRRK2 ChEMBL responses into data/demo_cache). No paid Gemini calls. No SQLite job store exists on prod (stateless server; user accepted that earlier) — "SQLite jobs" is therefore preserved as-is (absent). Audit logs = approvals.jsonl / shortlists.jsonl + browser-held decisions.

## Tasks
- [x] T1 Approval identity: `approval_id` (uuid4 hex), `decision_id`, `action` on Approval; legacy /api/screen + /api/shortlists keyed by approval_id; stateless /api/screen requires approval_id + disease_id + target_id matching the signed payload and action == approve_screening; same-second regression test.
- [x] T2 Retrieval: ordered (`-pchembl_value`) stage-1 retrieval with coverage record (total, retrieved, cutoff, selection method, partial flag); stage-2 complete on-target records for the candidate pool; identifiers preserved on every record.
- [x] T3 Potency aggregation: comparable-measurement grouping (assay_type B, standard_type in IC50/Ki/Kd/EC50, relation '='), median aggregate, conflict/sparse flags, censored counts, baseline max preserved.
- [x] T4 Drug-likeness + clinical: QED retained; missing vs poor distinguished; drug_indication lookup qualifies phase against the approved disease.
- [x] T5 Selectivity: off-target records for the top N shortlisted molecules; targets/assays tested, comparable vs incomparable, window; absence never = selective.
- [x] T6 Rubric + ranking: configurable heuristic rubric (objective presets), composite over available factors only, rank_reason, baseline_rank; API returns coverage, rubric, method.
- [x] T7 Frontend: four-factor table, warnings, reason, baseline toggle, objective selector, coverage notice; types; screen() sends approval_id/disease_id/target_id.
- [x] T8 Re-record LRRK2 demo cache; Playwright flow passes offline.
- [x] T9 Benchmark script + devils_advocate/MOLECULE_RANKING_VALIDATION.md (EGFR + second target, ablations).
- [x] T10 Full suites: pytest (both), vitest, eslint, next build, playwright.
