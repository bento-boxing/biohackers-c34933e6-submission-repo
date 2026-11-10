# Target Challenger — Agentverse prototype

Independent Python pipeline: disease + protein → ChEMBL mechanisms/compounds →
ClinicalTrials.gov registry records + Europe PMC literature → conservative concern
classification → source-field verification → one proposed experiment → human decision.
No Target Scout dependency or patient records. Deterministic and offline modes
need no LLM key; optional genuine Claude reasoning uses the repository-root `.env`.
The existing backend and teammate files remain separate.

## Run locally (PowerShell, from `backend/`)

Python 3.11+ is required. A local `.venv` is ignored by Git.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r devils_advocate/requirements.txt
.\.venv\Scripts\python.exe -m streamlit run devils_advocate/demo_app.py
```

Open http://localhost:8501. Keep **Offline recorded BACE1 example** enabled for a
repeatable demo of BACE1 / Alzheimer's disease. Disable it for live retrieval.
Click **Challenge this target**, inspect records, evidence and uncertainty, review
the proposed experiment, select Investigate / Revise / Stop, and download JSON.
Changing disease, target or mode immediately clears the previous evidence,
experiment and decision. Click the button again to retrieve the new report.
Each attempt clears old results before retrieval, including unsuccessful attempts.
The interface displays LIVE or OFFLINE before and after retrieval. Live failures
are visible and never substitute recorded evidence. Decisions remain in this
browser session/export, not a database.

```powershell
.\.venv\Scripts\python.exe -m pytest devils_advocate/tests -q
```

## Integration contract

```python
from devils_advocate import investigate_target, propose_experiment, TargetInput

target = TargetInput(
    disease_name="Alzheimer's disease", disease_id=None,
    target_symbol="BACE1", target_id=None,
)
investigation = investigate_target(target)  # live by default
experiment = propose_experiment(investigation)
payload = {
    "investigation": investigation.model_dump(mode="json"),
    "experiment": experiment.model_dump(mode="json"),
}
```

`investigate_target` also accepts a dictionary and `offline=True`. The offline
fixture intentionally accepts only its labelled disease/target. Ensembl/UniProt
identifiers are preserved in input but not silently treated as ChEMBL IDs. The
resolved ChEMBL target is separate; resolution requires a unique exact human gene
symbol on a single-protein record. Ambiguity is reported rather than guessed.
Disease IDs are preserved for future integration; current queries use disease names.

## Optional genuine Claude reasoning

The application uses the official **anthropic** Python SDK (Messages API), not an
OpenAI compatibility shim. Configuration is loaded with `python-dotenv` from the
repository-root `.env`; existing process environment variables take precedence.
`.env` is ignored and untracked by Git. Never commit it or place credentials in
reports or prompts. See `ai.env.example` for non-secret configuration names.

```dotenv
ANTHROPIC_API_KEY=your_private_key
AI_MODEL=claude-opus-5-5
AI_ENABLED=true
AI_THINKING_LEVEL=medium
```

The model is read from `AI_MODEL` (default `claude-opus-5-5`). Each role is one
`messages.create` call: the role instruction is the `system` prompt, the evidence
packet is the single user message, and the reply is constrained to the role's
JSON schema with structured outputs (`output_config.format`). Thinking is
adaptive; `AI_THINKING_LEVEL` is sent as `output_config.effort`. No sampling
knobs or thinking budgets are used, and SDK retries are off so every attempt is
counted against the call budget. For models that support it, the server-side
refusal fallback (`fallbacks: "default"`) is requested, so a safety decline is
re-run on a fallback model inside the same call; the model that answered is the
one reported by the API.

Run the explicit short authentication/model-access check separately:

```powershell
.\.venv\Scripts\python.exe -m devils_advocate.claude_smoke
```

It sends only a request to reply OK and prints model, success/failure and fixed
safe diagnostics. It never prints the key, raw exceptions, headers or response
body. Authentication success does not guarantee future
quota or availability for larger requests. No smoke test runs automatically.

For the application, turn OFF **Offline recorded BACE1 example** and click
**Challenge this target**. If `AI_ENABLED=true`, this retrieves public evidence
then makes real, separately instructed model calls for:

1. **Devil's Advocate**: at most four source-linked factual objections, bounded
   interpretations or unresolved questions.
2. **Evidence Adjudicator**: one structured verdict per claim, reviewing actual
   source material and deterministic objections. Unknown sources, invalid fields,
   nonmatching excerpts, invented narrative IDs and unquoted direct facts are
   rejected deterministically even if Claude agrees with the challenger.
3. **Experimental Challenger**: a revised interpretation anchored to accepted
   claim IDs and ONE high-level, unvalidated experiment. Unsupported final anchors
   cause rejection. No wet-lab execution instructions or autonomous actions.

When a claim is not accepted, one challenger revision and one re-adjudication
are allowed if the remaining request budget permits. Remaining unsupported
claims are removed. Empty supported evidence yields `insufficient evidence`;
experimental hypotheses remain explicitly provisional. All audit rounds, initial
claims, exact evidence sent, objections, verdicts and final reassessment are
serializable in `Investigation.ai` and the downloaded research report. Model
agreement is never independent evidence; interpretations and final synthesis
still need researcher/expert review. A human review checkbox records approval
alongside the decision; the application executes no research action.

The existing `investigate_target(...)` interface remains deterministic. To opt
into configured AI reasoning from Python use:

```python
from devils_advocate import challenge_target, propose_experiment

investigation = challenge_target({"disease_name": "Alzheimer's disease", "target_symbol": "BACE1"})
experiment = propose_experiment(investigation)
print(investigation.ai.status)  # completed / failed / skipped / disabled
```

`propose_experiment` uses Claude's proposal only for a completed AI report.
Otherwise the deterministic proposal remains available, explicitly labelled in
the UI. AI errors never erase retrieved evidence or silently present rules as
Claude output. Disabling AI also preserves the existing workflow.

### Cost, latency and privacy controls

Optional settings (defaults): `AI_MAX_CALLS=7` (allowed 3–10; one retry of a malformed response is billed),
`AI_MAX_PUBLICATIONS=4` (1–10), `AI_MAX_TRIALS=6` (1–20),
`AI_EXCERPT_CHARS=2400` (500–4000), `AI_MAX_OUTPUT_TOKENS=8192` (512–16384),
`AI_TIMEOUT_SECONDS=120` (5–120), `AI_RETRIES=1` (0–1).
Each SDK request attempt, including a transient retry, consumes the investigation
budget. SDK automatic retries and continuation are disabled, preventing hidden
extra model requests. A normal successful investigation needs three requests;
one revision uses five. If retries consume the remaining budget, AI reasoning
fails safely rather than issuing another request. No paid calls occur merely
from opening the app, editing inputs or exporting a report.

Offline fixture mode **always makes zero Claude calls**, regardless of
`AI_ENABLED`. Invalid/unresolved targets or no retrieved public evidence also
skip paid reasoning. Source excerpts are selected and truncated explicitly;
publications are bounded, so this is not a systematic literature assessment.
Only public, non-patient-level records enter the model. All source text and
prior model output are marked untrusted data in system instructions; no model
tools, browsing, shell access or environment access are provided. This reduces
prompt-injection exposure but does not prove semantic correctness or immunity.

The UI distinguishes data mode, configured AI provider/model, reasoning status,
validated calls versus attempts, safe token-usage metadata, unsupported claims,
and the **Scientific Challenge & Revision** audit. Token counts are shown when
returned by the API; no monetary cost is invented. Requests that fail or time out
can still incur provider charges. Raw SDK error bodies and credentials are never
included in application diagnostics.

The explicit end-to-end test below can incur up to the configured paid-call cap:

```powershell
.\.venv\Scripts\python.exe -m devils_advocate.claude_validation
```

Its actual outcome and audit are saved in `validation/claude_report.json`.
Unit and Streamlit tests mock AI responses and never run this paid test.

### Actual Gemini validation (historical)

This section records the paid validation run made when the workflow used Gemini. It has not been
repeated with Claude; `claude_validation` writes `validation/claude_report.json` when it is.

The short authentication/model test succeeded. Two initial end-to-end attempts
failed while using the initial 60-second request timeout; the safe diagnostic
identified `APITimeoutError`. After reducing the default evidence packet and
raising the timeout to 120 seconds, a live BACE1 investigation completed all
**five model calls**, including one revision and re-adjudication. Four final
claims passed exact-citation checks and Gemini's adjudicator review.
The final regression suite passed **64 offline tests**, including the real saved
audit's citation checks, mocked three-role calls and revision loops, hard budgets,
sanitized failures, no-call offline mode, stale approval clearing, and the
Streamlit AI report. The running server at http://127.0.0.1:8510 returned `ok`
from its health endpoint. `.env` remained ignored and untracked.

The adjudicator requested removal of an unverified CNP520 trial-to-target link
and an unsupported cross-secretase mechanism from an initial objection. The
challenger revised that objection and the adjudicator reviewed it again. The
saved report includes both versions and their findings, plus the actual token
usage returned by Google. The experiment is a high-level proposal, not a performed
or validated study. The final synthesis is not independently adjudicated; its
interpretations still require expert review. This single demonstration does not
measure scientific accuracy, superiority or probability of target success.

Live reasoning can take several minutes at medium thinking effort. A configured
timeout, token limit, quota error or exhausted call budget can still prevent a
completed report. The UI preserves the deterministic evidence and marks that
failure explicitly. Future paid tests append safe status summaries to
`validation/gemini_validation_history.json`.

### Target Scout JSON handoff

`fixtures/target_scout_lrrk2.json` uses the exact agreed schema. Its 0.82 score is
illustrative upstream metadata, not a verified association or success probability.
Missing optional fields receive defaults. The pure adapter needs no network;
the optional validation step checks Ensembl human gene ID/symbol agreement and
resolves an exact human ChEMBL target. Verified mismatches are rejected. Unsupported
namespaces and unavailable validation are explicit, never silently replaced.
Disease IDs are preserved; ontology equivalence is not verified.

```python
import json
from pathlib import Path
from devils_advocate import adapt_target_scout, validate_target_scout

scout_json = json.loads(Path("devils_advocate/fixtures/target_scout_lrrk2.json").read_text())
target_input = adapt_target_scout(scout_json)  # pure conversion, no claims verified
handoff = validate_target_scout(scout_json)   # optional live identifier checks
# Inspect validation_notes, particularly unavailable validation, before proceeding.
investigation = investigate_target(handoff.target_input)
experiment = propose_experiment(investigation)
```

The adapter preserves the original Ensembl ID and disease ID; resolved ChEMBL ID
is a separate field. `evidence_pmids` are unverified leads and association_score
stays outside the investigation input. Neither is treated as independent proof.

Modules:

- `models.py`: Pydantic request, record, claim, audit, investigation and experiment contracts.
- `trial_retriever.py`: human target resolution, curated mechanism compounds, aliases and registry matching.
- `devil_advocate.py`: independent publication retrieval, deterministic analysis and orchestration.
- `evidence_verifier.py`: rejects unknown source identifiers and nonmatching excerpts; revises factual wording to the retrieved excerpt and records objections.
- `experiment_designer.py`: one high-level orthogonal perturbation experiment, adapted to registry concern and BACE1 readouts.
- `http_client.py`: connection/read timeouts, two retries with backoff, process-local 15-minute cache and explicit retrieval errors.
- `capture_example.py`: optional explicit regeneration of the recorded example from live endpoints.

## Evidence semantics and limits

**Verified** means the identifier and excerpt match a retrieved record, not that a
claim is scientifically true. Registry status and `whyStopped` are separate facts.
TERMINATED, WITHDRAWN, COMPLETED, and absence of posted results do not establish
efficacy or toxicity. Posted numerical results are not automatically interpreted.
Reasons explicitly mentioning futility, safety or recruitment are triaged as
efficacy, safety or operational concerns. Mixed concerns are `other`; otherwise
`unknown`. No target is declared invalid.

Compound links are **verified** for exact normalized intervention aliases,
**probable** for bounded alias text within an intervention, and **uncertain** when
no alias matches. A verified name link does not establish target engagement or
compound selectivity. Titles and registry conditions are retained; eligibility
criteria supply population context. Mechanism, exposure and population differences
must be reviewed by the researcher before extrapolating a failure to another disease.

Literature snippets are verbatim author-reported context, not automatically
established scientific claims. All automatically extracted publication passages
and titles are **Neutral / Insufficient**, with explicit uncertainty and source
URLs. No keyword can promote methods, background or biomarker language to
therapeutic support. This conservative prototype does not automate publication
outcome adjudication; a researcher must review full study context. Consequently
the Supporting category may be empty, even when the literature contains benefits.

A registry stop reason can flag a contradictory **programme concern** only when
its compound link is exact and the recorded disease matches. This does not prove
target invalidity or compound causality. Missing reasons remain unknown; negated
safety reasons and dependent feeder-study closures receive conservative handling.
Source-field verification also downgrades unsupported stances and records the
revision. Every claim carries source URL, fact/interpretation, relevance and
uncertainty. Interpretations can be source-linked but are never certified true.

Historical assessments list the source record, documented concern, relevance,
population/mechanism limitations, compound specificity and engagement uncertainty.
Recommendations are retain (operational evidence alone), revise (documented
applicable programme concern), or escalate (insufficient/uncertain evidence),
with a rationale and NCT evidence anchors. None is an autonomous stop decision.
These deterministic labels remain separate from optional Claude interpretations.
Claude adds the explicit challenge/adjudication/revision stages above; model
findings do not overwrite the recorded facts or certify biological causality.

Search is bounded and reports truncation; it is not a systematic review. Some
mechanisms/compounds may be absent, aliases incomplete, disease-name queries may
miss relevant populations, and abstracts may be unavailable. The experiment is a
research proposal with model-specific limitations, not a validated protocol.
The shared HTTP client spaces requests by at least 350 ms, retries transient
errors twice with backoff, caches successful responses for 15 minutes, and uses
connection/read timeouts. Limits are notes, not request errors. Publication
retrieval requires visible target/compound and disease mentions; matching these
words still does not establish population or mechanistic applicability. Trials
with broader disease descriptions remain available but explicitly uncertain.
`Trial.compound_matches` retains verified/probable status for each compound,
separately from the trial's best overall name match. Posted registry outcome
measure records are retained for inspection; their statistics are not interpreted.

### Stop-reason presence and full-record verification

Live trial retrieval now fetches each unique NCT ID's **full API v2 study record**
after deduplicating search hits. The detail request uses no `fields` projection.
`whyStopped` is inspected with a field-membership check rather than
`status.get('whyStopped', '')`. The shared HTTP cache/rate limiting still applies;
large trial searches can take longer because they require one detail request per
unique trial. Detail failures are reported without inventing reasons or erasing
the fact that a search candidate was retrieved.

`Trial.stop_reason` preserves state, raw string value, full-record verification,
source API URL, check timestamp, diagnostics and the original search state/value.
`why_stopped` remains a compatibility string for existing classification/citation
code. Only a reported nonempty reason is passed into that string after a live
detail lookup. A failed detail lookup retains the original search value in audit
metadata and classifies the current reason as unknown.

| Actual condition | Display |
|---|---|
| `whyStopped` absent from a valid, identity-checked full record | Not reported in registry |
| Field present as `""` or whitespace | Registry stop-reason field is an empty string |
| Field present as JSON `null` | Registry stop-reason field is null |
| Full-record endpoint returns HTTP 404 | Registry record not found (HTTP 404) |
| Timeout, API/JSON error or another unsuccessful request | Full-record API request failed |
| Missing/invalid status module, mismatched identity, wrong value type | Record/stop-reason format could not be validated |
| Legacy fixture without field-presence metadata | Full registry record not verified |

The trial card links both the registry study and the full API record. Historical
assessments use the same presence-aware wording and retain their registry source
link. Report-version invalidation clears old browser reports that used the
ambiguous `not supplied` label. Offline fixtures are not silently rechecked over
the network, and old empty strings are not retroactively asserted to be absent.
No trial status, model output or inferred outcome is substituted for a reason.

The real full-record audit in `validation/stop_reason_audit.json` checked all 27
previously retrieved BACE1 trial IDs on 7 November 2026: 21 records genuinely
lacked `whyStopped`; six supplied nonempty reasons. Every supplied reason was
preserved exactly by our parser and agreed with the stored parsed value. No
missing records, empty/null values or API errors occurred in that successful
audit; these alternatives are covered by mocked regression tests.
For [NCT02565511](https://clinicaltrials.gov/study/NCT02565511), the
[full API record](https://clinicaltrials.gov/api/v2/studies/NCT02565511) contains a
status module with `overallStatus=TERMINATED` but no `whyStopped` key. The cause of
the displayed empty value is registry absence, not a dropped nonempty reason.

```powershell
# Direct full-record check; no Claude calls or Target Scout modifications
.\.venv\Scripts\python.exe -m devils_advocate.stop_reason_audit NCT02565511
# Also audit recorded BACE1 trial IDs if the local source bundle is available
.\.venv\Scripts\python.exe -m devils_advocate.stop_reason_audit NCT02565511 --include-recorded-bace1
```

The full regression suite passed **91 tests** after this change. It covers actual
recorded NCT02565511 absence, empty/null strings, HTTP 404, API failures, malformed
records, authoritative detail values, exact parser preservation, deduplication,
legacy fixtures and status-independent classification.

## Offline provenance

`fixtures/bace1.json` contains recorded API fields with capture time and source
URLs. It is a selected example, not a current or exhaustive clinical assessment.
Regenerate only when network access is available:

```powershell
.\.venv\Scripts\python.exe -m devils_advocate.capture_example
```

The capture command fails instead of fabricating records if a required source is
unavailable. Offline unit tests otherwise use small synthetic API responses to
exercise edge cases; they are not biomedical findings.

## Evaluation against a single-LLM baseline

`evaluation.py` scores documented concern classification, relevant failure detection
and unsupported-claim detection on the same human-labelled cases. Use the export
helper below to prepare a frozen bundle and predictions from this pipeline. Have
an independent reviewer label the cases using the original sources. Give a single
LLM `BASELINE_PROMPT` plus the **same** bundle and case IDs, with browsing disabled.
Save its actual JSON `items` list as a prediction file; record provider, model,
prompt, date and settings alongside it. No API integration is required and no
performance results are invented. Synthetic unit tests do not measure scientific
accuracy. Small case sets are demonstration evaluations, not general benchmarks.
`relevant_failure` here means a potentially relevant compound-linked clinical
concern, never proof of target invalidity. In outcome cases, `unsupported` means
no explicit stop reason supports an outcome interpretation; in claim cases it
means the submitted claim is rejected or requires factual revision.

```python
import json
from pathlib import Path
from devils_advocate import investigate_target
from devils_advocate.evaluation import prepare_evaluation

result = investigate_target({"disease_name": "Alzheimer's disease", "target_symbol": "BACE1"}, offline=True)
bundle = prepare_evaluation(result)  # optional candidate_claims includes unsupported claims
predictions = bundle.pop("system_predictions")  # hide these from baseline and reviewer
Path("evaluation_bundle.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")
Path("system_predictions.json").write_text(json.dumps(predictions, indent=2), encoding="utf-8")
```

```powershell
.\.venv\Scripts\python.exe -m devils_advocate.evaluation labels.json system_predictions.json baseline_predictions.json
```

Files are JSON arrays with rows like:

```json
[{"id":"case-1","concern":"unknown","relevant_failure":false,"unsupported":true}]
```

Missing predictions count as wrong. Report the number of cases and review errors;
do not equate classification accuracy with validation of the biological target.

## Sources and licence notes

- [ChEMBL web services](https://chembl.gitbook.io/chembl-interface-documentation/web-services/chembl-data-web-services): curated targets, mechanisms and compounds. ChEMBL data are distributed under [CC BY-SA 3.0](https://www.ebi.ac.uk/chembl/); retain attribution and applicable share-alike terms for redistributed data. Code and source-data rights are separate.
- [ClinicalTrials.gov API v2](https://clinicaltrials.gov/data-api/api): registry records submitted by sponsors/investigators; see [terms and conditions](https://clinicaltrials.gov/about-site/terms-conditions). Attribution is retained; registration is not government endorsement or verification of outcomes.
- [Europe PMC REST service](https://europepmc.org/RestfulWebService): publication metadata and abstracts. [Copyright and reuse](https://europepmc.org/Copyright): article/abstract rights vary; API availability does not grant blanket full-text reuse. Keep original identifiers and links, and review item-specific rights before redistributing fixture abstracts.

No real patient-level data are collected. Biomedical retrieval needs no API key.
Optional Claude reasoning loads its key from environment variables; the key is
excluded from Git, model inputs, logs and downloaded reports.

## Presentation and profiling

See [clinical/preclinical pathway validation](PATHWAY_VALIDATION.md) for the
generalized biological association gate, unrelated-approval separation, fresh
Next.js → Flask → SQLite HIV/CCR5 and scoliosis/BCL2 results, provenance, and
zero-paid-call reproduction commands. Adequate early-stage biology no longer
requires clinical trials; insufficient biology still abstains.

The [scientific reliability audit](RELIABILITY_AUDIT.md) documents the reproduced
CCR5 retrieval failure, balanced source selection, approval/indication coverage,
pre-model abstention gate, five-case recorded benchmark and measured limitations.
Run `.\.venv\Scripts\python.exe -m devils_advocate.scientific_benchmark` from the
repository root for deterministic public-fixture checks with zero model calls.

The Next.js Evidence Trace, Medium/High configuration, measured timings,
bounded retrieval budget, isolated browser QA and reproducible packet-size
comparison are documented in [the workbench README](../frontend/README.md).
Historical source fixtures and scientific evidence records remain unchanged.

## Implementation validation

Validated on Python 3.13 on 7 November 2026. See `validation/live_report.json`
for actual counts, sample citations, limitations and the validated LRRK2 handoff.
`validation/source_metadata.json` records the live **ChEMBL_37** release/status.
ChEMBL data attribution: https://www.ebi.ac.uk/chembl/, version ChEMBL_37 for this
live validation. The older BACE1 fixture retains its own original capture time;
its source release was not recorded and is not retrospectively asserted.

| Disease / target | Resolved ChEMBL ID | Compounds | Trials | Publications | Exact compound + disease trial matches |
|---|---|---:|---:|---:|---:|
| Alzheimer's / BACE1 | CHEMBL4822 | 4 | 27 | 34 | 12 |
| Parkinson's / LRRK2 | CHEMBL1075104 | 0 | 38 | 25 | 0 |
| Hypercholesterolemia / PCSK9 | CHEMBL2929 | 9 | 197 | 30 | 88 |
| Non-small-cell lung cancer / EGFR | CHEMBL203 | 15 | 501 | 30 | 207 |
| Alzheimer's / FAKEGENE123 | unresolved | 0 | 0 | 0 | 0 |

All returned publications pass visible target/compound + disease lexical checks;
this is an applicability screen, not expert proof of scientific relevance.
LRRK2 has no curated mechanism compounds in this retrieval, so its 38 trials
are unverified candidates, not demonstrated LRRK2 programme failures. PCSK9's
gene-query search hit the 100-record limit; EGFR has 76 mechanism compounds but
only the configured 15 were retrieved, and four trial queries reached their
100-record limit. No request errors occurred in the final five-case run. Invalid
target resolution correctly skipped downstream retrieval, with explicit warnings.

- Before LLM integration, 47 offline tests passed, including API mocks, malformed records, individual
  compound links, neutral evidence, missing citations, negated stop reasons,
  stale-result prevention, JSON adapter, benchmark and Streamlit report formatting.
- The preserved offline BACE1 fixture contains two TERMINATED records with no
  recorded stop reason; both remain unknown. Its demo makes no live calls.
- Updated Streamlit launched at http://127.0.0.1:8510 for local validation.
- The nine-case inspectable benchmark used the same frozen registry extracts
  for this pipeline and an extract-only summary baseline. Correct classifications
  were 9/9 versus 4/9; relevant-compound-concern flags 9/9 versus 7/9; unsupported
  outcome/claim flags 9/9 versus 8/9. These are selected regression cases with
  implementer-specified labels, not blinded independent scientific validation.
  The baseline abstains on concern/relevance and accepts nonempty citations
  without content checks; its limitations are explicit in `benchmark.py`.
- No single-LLM benchmark was run. Neither scientific superiority nor target
  validation is claimed from these small checks.

```powershell
# Reproduce the offline nine-case comparison; no live response cache required
.\.venv\Scripts\python.exe -m devils_advocate.benchmark
# Repeat all five live requests and the Ensembl handoff (internet required)
.\.venv\Scripts\python.exe -m devils_advocate.live_validation
```

Large raw live response bundles stay local in `validation/*_sources.json` and
are ignored by Git. The compact `fixtures/benchmark_sources.json` and benchmark
report retain the inspectable excerpts and original registry URLs. Source-data
rights remain separate from code; retain ChEMBL attribution/share-alike terms,
ClinicalTrials.gov notices, and item-specific publication rights. Full abstracts
are not blanket-licensed by the Europe PMC API; review their original rights
before redistributing recorded fixtures. No patient-level data are introduced.

Repeat the optional full live smoke check with:

```powershell
.\.venv\Scripts\python.exe -m devils_advocate.capture_example --check-search
```

## Retrieval caching, prior-art checks and measured optimization

See [OPTIMIZATION_VALIDATION.md](OPTIMIZATION_VALIDATION.md) for the five-case
cold/warm measurements, actual Next.js/Flask/SQLite runs, authorized Medium/High
comparison, scientific limitations and reproduction commands. Source timestamps
and cache provenance appear in the UI; **Force refresh public sources** bypasses
both memory and persistent caches. A cached public record is not a validated
scientific conclusion. Full source records and selected/omitted packet IDs remain
auditable. The five-attempt default and separate extra-call authorization retain
the full adjudication workflow and human gates.

## Adaptive evidence discovery and verification

`evidence_planner.py` turns the single-pass pipeline into a bounded loop: build a plan of what the
pair must establish → assess each need from the scoped records → targeted follow-up searches for
open needs only (Europe PMC, ClinicalTrials.gov, Open Targets/OLS identifier resolution, ChEMBL
retry) → reassess → stop with a recorded reason (`coverage_achieved`, `no_actionable_gaps`,
`no_new_evidence`, `round_limit`, `budget_exhausted`). Every search, response state and new record
is kept in `Investigation.evidence_plan`; failed searches are never cached or read as absence.
Publications and trials now carry dates and an evidence tier (registry status, registry results,
peer-reviewed, regulatory decision); sponsor announcements are reported as not searchable.
Planner-flagged material records enter the Claude packet beyond the stratified cutoff with a stated
reason, the adjudicator checks stance/excerpt direction, disease applicability, causal wording,
universal claims and omitted contradictions (pulling omitted records into the revision packet), and
the prior-art check searches the question, mechanism/readout and competing hypotheses. Results,
measurements and limitations: [ADAPTIVE_EVIDENCE_VALIDATION.md](ADAPTIVE_EVIDENCE_VALIDATION.md).
Reproduce the cross-disease benchmark with `python -m devils_advocate.adaptive_benchmark --base <next-url>`
(public sources only; zero paid calls).
