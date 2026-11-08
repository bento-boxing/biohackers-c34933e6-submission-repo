# Optimization validation — 8 November 2026

Branch: `henri-testing`. No ranking changes, commits, pushes or `.env` edits.
Isolated test servers used ports 5051/3001 and a separate SQLite runtime; they
were stopped afterward. No original application job was restarted or cancelled.

## Baseline and changes

Earlier live CCR5 job `398304dac2fd43ae9edcf3ad044e9a7d`: 238.884471 seconds
end-to-end, including 139.197922 retrieval and 92.947826 across three Gemini
calls. There were 185 logical public requests and one cache hit: 151
ClinicalTrials.gov, 26 ChEMBL, six Europe PMC and two other requests. Their
aggregate request durations were 64.4617, 15.9823, 18.6232 and 4.3233 seconds.
These aggregates are not source wall times; parsing and observer overhead also
matter. The slowest observed Europe PMC request took 12.475789 seconds without
retries. Repeated URL paths had different parameters, so were not necessarily
duplicate requests.

Implemented:

- Persistent SQLite cache keyed by method, source, URL, query, disease and supplied
  target identifiers, with timestamps, expiry, SHA-256 and origin. Derived disease
  aliases appear in actual search parameters rather than creating redundant scope
  keys. Verified Scout identifiers are reused without changing ranking.
- ChEMBL target/molecule/mechanism TTL seven days, indications one day;
  ClinicalTrials.gov search one hour, individual records six hours; Europe PMC six
  hours; other verified public sources one day. Failed, malformed, contradictory
  empty-count and corrupt responses are not reused. Bounded valid pages retain
  coverage limits: structural verification does not certify an exhaustive search.
- UI/API manual refresh (`refresh_evidence: true`), explicit LIVE, CACHED_MEMORY,
  CACHED_PERSISTENT and existing recorded-demo provenance.
- At most four HTTP workers, thread-local sessions, host pacing (minimum 0.35 s,
  ClinicalTrials.gov 1.25 s), connect/read timeouts 5/20 s, maximum three GET attempts
  and one read-only POST attempt. Numeric and HTTP-date Retry-After are respected;
  long requested waits fail rather than retrying early. Retrieval retains its
  300-second deadline; targeted prior-art lookup has 60 seconds.
- Raw trial deduplication before parsing and compiled compound matchers reused
  across records. Bounded full-record trial batches are sampled against individual
  records; mismatches fall back to individual retrieval. This is a sample consistency
  check, not independent verification of every registry datum. Full outcomes,
  stop-reason states, individual IDs and batch origin remain available.
- Compact model packets with full selected/omitted/per-agent audit IDs. Complete
  records remain in Investigation. Formerly truncated outcome JSON is replaced
  by a complete endpoint-title index explicitly insufficient for numerical
  efficacy/safety conclusions; full numerical results remain in the saved report.
  Numeric outcome claims require further source detail.
- Question-specific prior-art context before design and final full-corpus plus
  targeted Europe PMC checks in normal live jobs. Generic background vocabulary
  cannot alone block a distinct question. No overlap is not proof of novelty.
- Guards for unsupported exclusivity, absolute assay absence, cross-population
  causal attribution and grouped approval statements missing compound-specific
  citations. Original proposals and source-linked objections remain auditable.
- A/B/optional revision+B/C, strict adjudication and human gates remain. Five model
  attempts are allowed by default; more requires separate paid authorization and
  `extra_calls_authorized: true`. High remains configurable. No environment setting
  or output budget was silently changed.

## Five-case public retrieval benchmark

Each pair used separate clients sharing a newly created persistent cache. No
model calls. Scientific record digests matched between every cold/warm pair,
excluding only the timestamp of the full stop-reason check.

| Disease / target | Cold s | Warm s | Cold requests | Warm requests | Warm hit rate | Trials / papers | Pathway |
|---|---:|---:|---:|---:|---:|---|---|
| HIV / CCR5 | 113.735514 | 6.267286 | 56 | 0 | 100% | 136 / 138 | Clinical precedent |
| Hypercholesterolemia / PCSK9 | 70.478066 | 6.641078 | 49 | 1 | 99.58% | 197 / 104 | Clinical precedent |
| Alzheimer's / BACE1 | 15.186723 | 1.356644 | 19 | 0 | 100% | 27 / 59 | Clinical precedent |
| Parkinson's / LRRK2 | 8.916563 | 0.432760 | 7 | 0 | 100% | 38 / 52 | Clinical precedent |
| Scoliosis / BCL2 | 14.234754 | 0.214233 | 21 | 0 | 100% | 0 / 7 | Limited preclinical |

All five were BOUNDED REVIEW, not exhaustive evidence reviews. BCL2 eligibility
does not establish target validity or scoliosis efficacy. PCSK9's openFDA 404 was
deliberately not cached. CCR5 had two cold retries: 58 network attempts for 56
logical requests. Single measurements are subject to substantial network variation.

LRRK2 also exposed a general recall bug: clinical literature was previously
searched only when curated compound records existed. Clinical search now runs
without those compounds; explicit target-directed interventional evidence can
qualify, while biomarkers/co-mentions alone cannot.

The recorded initial 24-source packet decreased from 91,571 to 65,699 UTF-8 bytes
(28.25%). This is payload size, not token count or measured model acceleration.
The thinking benchmark added four recorded prior-art records: its 28-source
initial payload was 76,033 bytes at both thinking levels.

## Actual Next.js / Flask / SQLite path

Fresh public-only jobs used the Next proxy, production factory/worker, SQLite and
result endpoint. AI was disabled. The initial persistent cache had zero entries.

| Job | Retrieval s | End-to-end s | Upstream requests | Cache hits |
|---|---:|---:|---:|---:|
| `424dcd2b2cac439c920105c431ca077c` cold | 54.628748 | 56.305937 | 56 | 0 |
| `2e641624c6b4442f87b4b03ea435485b` warm | 8.848113 | 10.655687 | 0 | 186 |

Both retained 136 trials and 138 publications, sufficient bounded clinical
coverage, zero model calls and exact API/SQLite equality. Browser tests rendered
the warm report and source timestamps through the actual Next proxy.
End-to-end includes polling. Cold network variation and observer/persistence
overhead explain differences from the separate benchmark.

These are public-only end-to-end times. No combined optimized live-retrieval-plus-
Gemini investigation was timed; adding separate timings would not measure one.

## Authorized Medium versus High

Authorization: maximum five attempts per arm, ten total. Used eight: two initial
restricted-network connection failures, then three provider calls per arm with
network access. Failures remain in the ledger and count toward the cap. The two
unused attempts were not spent; no paid calls remain running.

All agent source hashes equal the frozen packet SHA-256
`9d72975aeaa0993f2e4c7bbcccb4a72eefd35000f3e0f11c3c1762357b853647`.
Sources were identical; generated claims/later prompts naturally differed. After
connection failures, neither arm had room for revision + re-adjudication + design,
so unaccepted claims were removed. Adjudication still ran. This constrained run
is not an unconstrained five-successful-call comparison.

| Stage | Medium s | High s |
|---|---:|---:|
| Devil's Advocate | 55.759799 | 84.778134 |
| Adjudicator | 26.226558 | 51.202320 |
| Experimental Challenger | 40.350243 | 107.444990, incomplete |
| Provider-attempt total | 122.336600 | 243.425444 |
| Retry-run orchestration wall time | 124.442255 | 245.474444 |

Medium technically completed. High's final response was incomplete: 8,189 thought
tokens and three output tokens consumed the 8,192-token budget. The response was
rejected. No automatic output-budget increase or paid repair was attempted.
**No Gemini speed improvement over the earlier 92.947826-second baseline was
demonstrated.** This is one sample per level with changed/enriched inputs relative
to that earlier baseline.

Scientific assessment, distinct from technical status:

- Both recognised the recorded population-scoped maraviroc efficacy precedent.
- Medium had 9/9 exact source excerpts across three accepted claims; High had 6/6
  across two. Every cited record existed. Exact matching is not semantic entailment.
- Medium's adjudicator caught a population conflation. An accepted grouped approval
  claim still lacked individual citations for vicriviroc/cenicriviroc. The added
  current guard flags both omissions in offline replay. That paid output must not
  be relabelled fully verified.
- High accepted cross-population explanatory evidence and overstated absence of
  activity in mixed-tropic virus. Current replay flags the causal attribution;
  expert entailment review remains necessary. No experimental hypotheses or final
  prior-art awareness can be scored successfully because its response was incomplete.
- Medium moved away from the established tropism question toward plausible
  off-target versus on-target toxicity hypotheses, with model limitations. Primary
  mechanistic support and expert model review remain necessary.
- The initial lexical checker falsely blocked that distinct question based on
  generic binding/clinical context. Corrected offline replay removes those blocks
  while retaining NOVELTY_NOT_ESTABLISHED. Paid reports remain unchanged. The old
  repeated escape proposal is still blocked, including PMID 16641282 overlap,
  unsupported exclusivity and absolute assay-absence wording. No HIV-specific
  conclusions were hard-coded.

Medium remains the user's existing default; this sample does not establish a
statistical quality advantage or a fully validated novel experiment at either
level. The retrieval/review workflow is suitable for a clearly labelled research
prototype demo with visible abstention and human gates, not independent validation.

## Tests and reproduction

Final Python: 248 passed. TypeScript and lint passed. Browser: all 18 passed,
including opt-in real saved-job rendering and new refresh/prior-art/cache tests.
Later backend-only guard refinements were checked by the final Python suite and
offline paid-output replay; no additional paid validation was run.

From repo root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
# Public APIs only, fresh local cold/warm caches, no model calls:
.\.venv\Scripts\python.exe scripts/benchmark_optimization.py
# Offline review of completed paid outputs, zero new calls:
.\.venv\Scripts\python.exe scripts/review_optimization.py
cd frontend
npm.cmd run typecheck
npm.cmd run lint
```

Isolated browser reproduction: run `scripts/pathway_validation_server.py` on 5051
and Next on 3001 with `RESEARCH_BACKEND_URL=http://127.0.0.1:5051` and
`RESEARCH_BUILD_DIR=.next-optimization-qa`. Run
`scripts/validate_optimization_jobs.py` from repo root for public-only jobs.
Run Playwright with `PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001` and
`OPTIMIZATION_LIVE_VALIDATION=1`. `PATHWAY_LIVE_VALIDATION=1` also requires the
earlier saved pathway jobs. Otherwise saved-live tests explicitly skip; recorded
tests run normally.

`scripts/benchmark_thinking.py --prepare` makes a new packet without calls;
do not overwrite the frozen packet when preserving this completed benchmark.
Paid execution needs separate authorization. An existing ledger blocks automatic
repetition. Explicit reviewed connection-failure resume preserves all attempts
and cannot increase the cap.

Artifacts: `validation/optimization/retrieval_report.json`, `job_end_to_end.json`,
`thinking_packet.json`, `thinking_paid_ledger.json`, both `thinking_*_report.json`,
connection-failure reports and `scientific_review.json`. Full live-response bundles
and caches stay ignored locally. The offline regression fixture is
`fixtures/optimization_reference.json`; its intentionally rejected proposal is
not a recommendation. Original public URLs and README licence caveats apply;
no patient-level records were introduced.

The user's existing application was not restarted. A normal backend restart is
needed to load the latest Python code when convenient.
