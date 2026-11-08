# Workbench validation — 7 November 2026

This file records executed checks, not inferred scientific performance.

- The existing 157 Python tests passed before adding integration regressions.
- New resolver checks exercised direct BACE1, exact symbol/component identity,
  wrong organism/taxon/type, conflicting IDs, cached resolutions, unknown targets,
  malformed source responses and temporary failures.
- Real identity requests resolved BACE1, LRRK2 and EGFR through their supplied
  ChEMBL IDs. The invalid symbol returned unknown. See `validation/chembl_identity_report.json`.
- The source-service diagnostic reproduced intermittent ChEMBL behavior: search
  HTTP 200 with five candidates and a direct-record HTTP 500/non-JSON response.
  The subsequent bounded-retry identity check succeeded; no recorded fallback was used.
- Five real-browser Playwright scenarios passed against the local offline
  backend, including discovery → LRRK2 → challenge → experiment → explicit
  approval → cached screening, page refresh, SNCA selection clearing, live
  consent UI, mobile layout, temporary-backend recovery and explicit recorded
  BACE1 Gemini playback. Screenshots were visually inspected.
- Frontend TypeScript checking, ESLint and optimized Next.js production build
  passed. Production-only npm audit reported zero known vulnerabilities; npm's
  initial full install reported eight moderate development dependency findings.
- No paid Gemini calls were made for this migration's validation. Genuine Gemini
  execution was validated in the earlier integration; here success, failure,
  timeout, cancellation and offline isolation are covered with mocks and the
  recorded, explicitly labelled BACE1 audit.

The full Python run finished with **182 tests passed** across both suites. The
browser suite finished with **5 tests passed**. TypeScript, ESLint and production
build all passed. Re-run commands and setup are in `../frontend/README.md`.

Remaining scope limits: local single-host SQLite worker, no remote-user auth,
development Flask server, cooperative (not in-flight provider) cancellation,
intermittent public APIs, bounded literature/trial retrieval, and scientific
interpretations/proposals requiring expert review. Streamlit and original Scout
entry points remain available. No ranking algorithm was overwritten.
