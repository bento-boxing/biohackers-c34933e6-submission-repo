# Final cross-disease scientific and technical audit

Audit date: 8 November 2026, Europe/London. Branch: `henri-testing`.

**Overall verdict: PARTIAL.** Suitable for a supervised demonstration of retrieval,
source verification, challenge/revision and human review, with visible abstention.
It is not validated as an autonomous cross-disease scientific decision system or
as a generator of demonstrably novel experiments.

**Safest measured live case: Alzheimer's disease / BACE1.** Its fresh investigation
completed in 132.81 seconds with five successful provider requests, correctly
identified documented efficacy/safety problems, and preserved uncertainty about
target-wide validity. The experimental proposal was withheld for prior-art review;
do not advertise that as a validated novel experiment. Rett/SLC12A5 is a useful
secondary demonstration of the limited preclinical pathway, with the scientific
qualification below. PCSK9 retrieval is convincing for explaining source
disagreement, but its paid final proposal failed exact citation validation.

No commits, pushes or deployments were made. Target Scout ranking was unchanged.
Credentials were ignored by Git and were not printed or added to audit artifacts.
The user's original runtime was not restarted or modified; isolated test servers
used ports 5051/3001 and the production Flask factory, worker and SQLite store.

## Scope and interpretation of verdicts

All 14 cases went through actual Next.js proxy → Flask → worker → SQLite → GET
report retrieval, with public-only authorization first. Real Ensembl, ChEMBL,
ClinicalTrials.gov, OLS, Europe PMC and available regulatory records were inspected.
Independent landmark PMID lookups were used as reference checks; their IDs were
not injected into tested retrieval queries or supplied to Gemini to force success.

PASS means the documented reference behavior passed within the tested scope,
not biological truth, exhaustive retrieval, or unperformed AI validation. PARTIAL
identifies incomplete mechanisms, source coverage, reasoning or experiment
validation. Software tests, retrieval correctness and scientific validity are
reported separately. Counts include retained indirect/other-indication context.

## Case matrix

| Case | Disease / requested target | Trials / papers | Pathway / coverage | Gemini evidence | Verdict |
|---|---|---:|---|---|---|
| CCR5 | HIV infection / CCR5 | 163 / 231 | clinical_precedent / BOUNDED REVIEW | Recorded earlier output reviewed | **PASS** |
| PCSK9 | Hypercholesterolemia / PCSK9 | 197 / 169 | clinical_precedent / BOUNDED REVIEW | Fresh, failed | **PARTIAL** |
| EGFR | EGFR-mutant non-small-cell lung cancer / EGFR | 179 / 370 | clinical_precedent / BOUNDED REVIEW | Not run; public/recorded checks only | **PASS** |
| BACE1 | Alzheimer's disease / BACE1 | 28 / 139 | clinical_precedent / BOUNDED REVIEW | Fresh, completed | **PARTIAL** |
| LRRK2 | Parkinson's disease / LRRK2 | 38 / 123 | clinical_precedent / BOUNDED REVIEW | Not run; public/recorded checks only | **PASS** |
| BCL2 | scoliosis / BCL2 | 0 / 47 | preclinical_validation / BOUNDED REVIEW | Not run; public/recorded checks only | **PARTIAL** |
| preclinical | Rett syndrome / SLC12A5 | 0 / 17 | preclinical_validation / BOUNDED REVIEW | Fresh, completed | **PARTIAL** |
| unsupported | achondroplasia / CCR5 | 0 / 46 | unresolved / INSUFFICIENT COVERAGE | Not run; public/recorded checks only | **PASS** |
| fabricated | HIV infection / AUDIT_FAKE_GENE_ZXQ987 | 0 / 0 | unresolved / INSUFFICIENT COVERAGE | Not run; public/recorded checks only | **PASS** |
| invalid_disease | HIV infection / CCR5 | 163 / 254 | clinical_precedent / INSUFFICIENT COVERAGE | Not run; public/recorded checks only | **PASS** |
| GLP1R | Type 2 diabetes mellitus / GLP1R | 634 / 296 | clinical_precedent / BOUNDED REVIEW | Not run; public/recorded checks only | **PASS** |
| CFTR | cystic fibrosis / CFTR | 259 / 253 | clinical_precedent / BOUNDED REVIEW | Not run; public/recorded checks only | **PASS** |
| SMN2 | spinal muscular atrophy / SMN2 | 34 / 149 | clinical_precedent / BOUNDED REVIEW | Not run; public/recorded checks only | **PARTIAL** |
| rare | NGLY1 deficiency / NGLY1 | 4 / 81 | preclinical_validation / BOUNDED REVIEW | Not run; public/recorded checks only | **PARTIAL** |

An invalid disease ID can retain legitimate HIV publications while remaining
ineligible for reasoning: a correct disease label does not verify a bad ID. The
unsupported pair retains unrelated CCR5 pharmacology; this does not establish
achondroplasia biology. Neither situation is evidence that the target is invalid.

### Verified identifiers

Ensembl human gene records were checked independently, and supplied Ensembl IDs
are now verified in the investigator before downstream retrieval. ChEMBL requires
an exact human single-protein component; shared canonical genes are explicitly
preserved as ambiguous protein mappings rather than interchangeable aliases.

| Case | Ensembl gene | ChEMBL protein | Disease identifier |
|---|---|---|---|
| CCR5 | ENSG00000160791 | CHEMBL274 | MONDO_0005109 |
| PCSK9 | ENSG00000169174 | CHEMBL2929 | No disease ID assigned; phenotype/name retained |
| EGFR | ENSG00000146648 | CHEMBL203 | MONDO_0005233 |
| BACE1 | ENSG00000186318 | CHEMBL4822 | MONDO_0004975 |
| LRRK2 | ENSG00000188906 | CHEMBL1075104 | MONDO_0005180 |
| BCL2 | ENSG00000171791 | CHEMBL4860 | MONDO_0005392 |
| preclinical | ENSG00000124140 | CHEMBL1615384 | MONDO_0010726 |
| unsupported | ENSG00000160791 | CHEMBL274 | MONDO_0007037 |
| fabricated | None; fabricated control | Unresolved | MONDO_0005109 |
| invalid_disease | ENSG00000160791 | CHEMBL274 | MONDO_999999999 |
| GLP1R | ENSG00000112164 | CHEMBL1784 | MONDO_0005148 |
| CFTR | ENSG00000001626 | CHEMBL4051 | MONDO_0009061 |
| SMN2 | ENSG00000205571 | CHEMBL1293232 | MONDO_0001516 |
| rare | ENSG00000151092 | CHEMBL4523429 | MONDO_0800044 |

PCSK9/hypercholesterolemia uses the clinical phenotype name; HP:0003124 was found
as a phenotype reference, without assigning a narrower familial MONDO disorder.
EGFR retains the molecularly selected input while using the broader NSCLC ontology
entity; that ID does not itself establish an EGFR mutation or treatment population.
MONDO_999999999 is intentionally invalid, not a verified disease identifier.

## Source-level scientific findings

### CCR5 — PASS
The MOTIVATE and MERIT papers are present after correction. They support scoped R5-tropic combination-treatment efficacy and nuanced assay/population limitations, not benefit in every HIV population. Prior Gemini outputs were reused only as RECORDED analysis, not new model validation; the earlier grouped-approval and population-inference weaknesses remain documented in the optimization review.
Authoritative reference checks: [MED:18832244](https://pubmed.ncbi.nlm.nih.gov/18832244/), [MED:20151839](https://pubmed.ncbi.nlm.nih.gov/20151839/).

### PCSK9 — PARTIAL
Alirocumab/evolocumab clinical precedent is supported. FOURIER and ODYSSEY concern specified ASCVD/post-ACS populations and background therapy; their cardiovascular results must not be generalized to all hypercholesterolemia. The fresh model accepted a historically bounded ChEMBL nonapproval statement about lerodalcibep. FDA documents a later approval, exposing a major regulatory-coverage gap; the generic lookup correction now retrieves FDA original approval independently while preserving ChEMBL phase 3. The final paid experiment was rejected for an unsupported exact prior-art citation.
Authoritative reference checks: [MED:28304224](https://pubmed.ncbi.nlm.nih.gov/28304224/), [MED:30403574](https://pubmed.ncbi.nlm.nih.gov/30403574/).

### EGFR — PASS
FLAURA was retrieved and selected. It supports first-line efficacy in EGFR mutation-positive advanced NSCLC, not every mutation, wild-type NSCLC or all disease stages. Unrelated HER2/cancer indications and multi-target pharmacology remain context. Molecular subtype and treatment-line equivalence still require source/population review; no fresh Gemini experiment was tested here.
Authoritative reference checks: [MED:29151359](https://pubmed.ncbi.nlm.nih.gov/29151359/).

### BACE1 — PARTIAL
The EPOCH and prodromal verubecestat papers were initially missed, then recovered by the general query corrections. They document lack of clinical benefit in their studied cohorts and relevant adverse outcomes. Registry stop reasons also document other programmes' futility/risk-benefit concerns. The fresh model correctly bounded these findings to compounds, exposure and symptomatic/prodromal populations rather than declaring BACE1 universally invalid.
Authoritative reference checks: [MED:29719179](https://pubmed.ncbi.nlm.nih.gov/29719179/), [MED:30970186](https://pubmed.ncbi.nlm.nih.gov/30970186/).

### LRRK2 — PASS
The DNL201 paper is now retrieved, alongside BIIB122 early clinical work (PMID 36807624). These establish early safety/engagement and developmental uncertainty, not proven disease modification or universal target failure. The previous false insufficient-coverage state was corrected. No curated mechanism compounds were returned; this is a ChEMBL coverage limitation, not evidence that LRRK2 inhibitors do not exist.
Authoritative reference checks: [MED:35675433](https://pubmed.ncbi.nlm.nih.gov/35675433/).

### BCL2 — PARTIAL
The scoliosis literature includes patient-cartilage/cellular pathway work, including the Suv39h1–miR-15a/BCL2 study. It justifies a limited exploratory hypothesis, not validated treatment. Venetoclax cancer approval is displayed as other-indication target pharmacology. The 47 retained papers include substantial unrelated cancer context; they are not 47 scoliosis efficacy studies. No Gemini calls were spent on this case.
Authoritative reference checks: [MED:31337422](https://pubmed.ncbi.nlm.nih.gov/31337422/).

### preclinical — PARTIAL
Rett/SLC12A5 was selected because distinct primary publications on human neurons and mice support KCC2 biology without disease-specific clinical trial precedent in this search. Both known rescue papers are now retrieved through verified aliases. Fresh Gemini recognized cellular/species/stage contradictions and proposed distinguishable causal-versus-developmental hypotheses. An accepted uncertainty nevertheless said an intervention remained untested; the current guard now flags such unqualified literature-absence wording. Its experiment was withheld for review, not declared novel or performed.
Authoritative reference checks: [MED:26733678](https://pubmed.ncbi.nlm.nih.gov/26733678/), [MED:31366578](https://pubmed.ncbi.nlm.nih.gov/31366578/).

### unsupported — PASS
CCR5 is a valid human target; the bounded achondroplasia search found no qualifying disease-specific primary biological support. Retained CCR5 drug papers do not validate this pairing. Correct abstention means no supported relationship found here, not proof that a relationship is impossible.
Authoritative reference checks: Negative control; source lookup/audit in inventory..

### fabricated — PASS
AUDIT_FAKE_GENE_ZXQ987 had no exact human ChEMBL resolution. Downstream disease-only retrieval and reasoning did not manufacture evidence or substitute another target. Unknown/unresolved is distinguished from source failure.
Authoritative reference checks: Negative control; source lookup/audit in inventory..

### invalid_disease — PASS
The actual OLS request returned HTTP 404. The old parser labelled it a generic outage and permitted label-based reasoning. It now records not-found separately from transport/server errors, preserves the queried ID, and blocks reasoning until the identifier is corrected/removed. Unavailable identifier validation is separately ineligible and is not labelled absent.
Authoritative reference checks: Negative control; source lookup/audit in inventory..

### GLP1R — PASS
Established agonist precedent and LEADER are retrieved. The cardiovascular evidence concerns the studied risk population and regimen, not every person with diabetes. Peptide/multi-receptor pharmacology and other approved indications require mechanism/indication qualification. Fifteen compounds and bounded query pages do not exhaust all therapeutic agents.
Authoritative reference checks: [MED:27295427](https://pubmed.ncbi.nlm.nih.gov/27295427/).

### CFTR — PASS
Ivacaftor G551D and elexacaftor/tezacaftor/ivacaftor Phe508del-minimal-function evidence is present. These support genotype-dependent treatment, not every CFTR variant. A separate fresh live Scout run selected CFTR; its nested disease, Ensembl, ChEMBL and UniProt values were preserved through the production investigation endpoint and SQLite.
Authoritative reference checks: [MED:22047557](https://pubmed.ncbi.nlm.nih.gov/22047557/), [MED:31697873](https://pubmed.ncbi.nlm.nih.gov/31697873/).

### SMN2 — PARTIAL
The gene is correctly identified, but ChEMBL maps SMN1 and SMN2 to a shared SMN protein. Ambiguous aliases no longer expand one canonical gene into the other. Curated onasemnogene gene-replacement evidence is not SMN2 splice modulation. Nusinersen landmark literature is retrieved, but the protein-only compound lookup does not comprehensively represent RNA/splicing modalities. FDA mechanism-of-action text and product-specific Zolgensma/Itvisma identities are now retained; their routes/age indications are not interchangeable. This case remains PARTIAL for gene-specific programme completeness.
Authoritative reference checks: [MED:29091570](https://pubmed.ncbi.nlm.nih.gov/29091570/).

### rare — PARTIAL
NGLY1 deficiency is a documented rare disorder with causal genetic evidence, but limited therapeutic outcome evidence. The original patient-series paper is retrieved. The independent ENGase rescue reference PMID 25605922 is still missed by disease-wording filtering; its absence is not sparse biology or evidence of inefficacy. Four registry records are retained with unresolved target/intervention mapping; the preclinical pathway does not prove no clinical programme exists. Gene-therapy programme linkage requires further curation.
Authoritative reference checks: [MED:24651605](https://pubmed.ncbi.nlm.nih.gov/24651605/), [MED:25605922](https://pubmed.ncbi.nlm.nih.gov/25605922/).


### Regulatory disagreement and current safety coverage

FDA's [LEROCHOL snapshot](https://www.fda.gov/drugs/drug-trials-snapshots/drug-trials-snapshots-lerochol)
documents approval on 12 December 2025. The corrected pipeline independently
retrieved original approval in application **BLA761427** and its disease-label
context while leaving the ChEMBL value **3.0** unchanged. Historical phase metadata
cannot establish current nonapproval. Label candidates now include a bounded set
of advanced compounds even when ChEMBL has not reached phase 4. Labels alone do
not prove approval: the additional application check requires an original AP record.
The existing UI displays the FDA record alongside the unchanged ChEMBL phase.

FDA biologic suffixes identify products. Curated brand plus generic-base matching
is distinguished from a probable suffix-variant relationship; original generic
names, label identities and product-specific restrictions are retained. An
onasemnogene label is not evidence for SMN2 splicing. The [FDA ITVISMA page](https://www.fda.gov/vaccines-blood-biologics/cellular-gene-therapy-products/itvisma)
and [approval announcement](https://www.fda.gov/news-events/press-announcements/fda-approves-gene-therapy-treatment-spinal-muscular-atrophy)
provide an independent product/SMN1 reference.

Important remaining safety limitation: FDA's [6 November 2026 safety update](https://www.fda.gov/vaccines-blood-biologics/safety-availability-biologics/fda-investigating-serious-risk-malignancy-linked-zolgensma-gene-therapy)
investigates insertional-oncogenesis risk and applies its risk assessment to both
onasemnogene products. It also states that benefits continue to outweigh risks
for approved uses. This external audit reference is not claimed to have been
automatically ingested by the label/publication pipeline. The app is not a complete
or real-time safety-alert surveillance system.

## Errors found, priorities and corrections

### P0 — unsafe identity eligibility, closed in tested paths

- A nonexistent disease ID was accepted via a correct disease name after OLS 404
  was misclassified. Confirmed missing, unavailable and unsupported IDs now have
  explicit, distinct coverage objections. Supplied Ensembl/species/symbol mismatches
  also stop downstream retrieval. Negative controls make no model calls.

### P1 — major retrieval/scientific/operational issues corrected

- Missing verified gene aliases lost KCC2 literature. Derived aliases now come from
  the exact human component; caller aliases are cleared. Shared canonical genes
  are preserved as ambiguity, not expanded into each other.
- Possessives were turned into a spurious separate `s` token. Exact `Alzheimer`
  returned zero for PMID 29719179 while the prefix query returned one. Possessives
  are preserved with a bounded eponym-prefix alternative, followed by visible
  disease checks. The subsequent real jobs recovered both BACE1 landmark trials.
- Recent/top-page bias missed early clinical programmes. Direction-neutral,
  citation-ranked and primary-interventional strata now accompany recent searches.
  Approved-target clinical context remains explicitly separate from direct
  indication-specific evidence.
- Bundled conference/session records could mix unrelated posters into a supposed
  study. They remain available as leads, but cannot ground coverage or enter model
  packets. Review/editorial/comment records do not count as primary biological
  support. Early human phase-1 reports are recognized without requiring randomization.
- FDA checks depended on pre-existing ChEMBL phase 4 and exact unsuffixed names.
  Advanced candidates, verified product identity and independent original-approval
  application checks now expose dataset disagreements without rewriting sources.
- Unqualified gaps such as `remains untested in vivo` could survive adjudication.
  Current deterministic objections demand source-bounded wording; model confidence
  cannot overrule them. Approval absence also requires authoritative qualification.
- Rejected final C drafts previously disappeared before the audit could inspect
  failed citation text. Future raw structured drafts and exact offending source/field
  diagnostics are retained as explicitly UNVERIFIED audit data; they are not proposals.
  The already-rejected PCSK9 draft cannot be retrospectively recovered (`store=False`).
- Job history selected/deserialized 100 complete scientific reports to return
  summary rows. The final browser run exposed stalls as the audit database grew.
  The endpoint now reads metadata columns only, preserving every scientific blob.

### P1 still open / not demonstrated

- No fresh case produced an accepted, scientifically validated novel experiment.
  One C response failed citation validation; two were withheld for prior-art review.
- Lexical prior-art overlap cannot prove that an entire specific question was
  answered. Related work and duplicated preprint/published versions can appear in
  the trace; expert/full-text review remains necessary. Abstention is not a target rejection.
- Final synthesis/design is not a separate independent scientific adjudication.
  Source/ID matching alone does not establish causal, population or novelty entailment.
- RNA, gene-replacement and shared-protein gene-specific programmes remain incompletely
  curated; rare-disease disease-wording recall is incomplete. Approval and safety
  sources are bounded and may lag current agency information across jurisdictions.
- Later fixes were checked with unit tests, offline replay and public-only jobs.
  They were not revalidated with additional paid model investigations. None of the
  failed/withheld model jobs was automatically repeated.

### P2

Large source collections, duplicate versions, bounded excerpts and reviewer
navigation still need care. Clinical eligibility text and abstracts can be truncated
in model packets; full stored records remain available. The four-publication sample
cannot be presented as the whole literature. A four-minute cold-network result is
not guaranteed by a 300-second retrieval deadline plus provider timeouts.

## Reference false-negative / false-positive findings

The independent, deliberately small reference set contains **17 PMID checks**. Initial retrieval contained **5/17**; the corrected 14-case checkpoint contained **16/17**. This is landmark recall on this hand-selected set, not overall biomedical accuracy. Missing PMID 25605922 remains explicitly open.
Rett and LRRK2 initially had false insufficient-coverage outcomes caused by
retrieval/scoping rather than an absence of relevant studies. These now use
appropriate pathways. The invalid disease ID was an eligibility false positive;
it now abstains. The unsupported pair and fabricated symbol abstained without
invented failures. Generic background-word overlap and bundled conference records
were additional false-positive risks. Prior-art flags are recorded as review flags,
not a gold-standard count of already-solved experiments.

## Fresh Gemini accounting and scientific review

Current audit authorization: three selected cases, maximum five attempts each,
maximum fifteen aggregate. **13 attempts, 13 provider successes, zero provider
failures, two unused attempts.** A provider success means parsed structured output,
not accepted scientific output. No additional paid calls were made after fixes.

All current requests used configured `gemini-4-argon`, `medium` thinking. High
remains optional; `.env` was not changed. SDK generation arguments and returned
token usage were inspected. Earlier CCR5/Medium/High outputs are RECORDED and do
not count as new calls in this audit.

| Case | Calls | Agent sequence | Provider seconds | Observed job wall s | AI scientific status |
|---|---:|---|---:|---:|---|
| PCSK9 | 5 | A → B → revision A → B → C | 146.682596 | 220.549942 | failed; experiment withheld |
| BACE1 | 5 | A → B → revision A → B → C | 122.281448 | 132.809228 | completed; experiment withheld |
| preclinical | 3 | A → B → C | 82.545490 | 87.414077 | completed; experiment withheld |

PCSK9's wall time includes waiting behind a public refresh job; it is not a
pure provider benchmark. A source-refresh/warm pair was also queued around this
workflow; queue time is separate from measured retrieval. BACE1's revision fixed
uncited registry identifiers and exact whitespace/field quotations. PCSK9's
revision narrowed grouped compound approval statements. Adjudication was never skipped.

| Case | Input tokens | Output tokens | Thought tokens | Total tokens | Provider cached tokens |
|---|---:|---:|---:|---:|---:|
| PCSK9 | 109142 | 7987 | 1468 | 118597 | 35119 |
| BACE1 | 74386 | 6702 | 663 | 81751 | 0 |
| preclinical | 15958 | 3854 | 998 | 20810 | 0 |

Cost in currency was not exposed by the API/billing system and was not estimated.
Provider cached-token usage is distinct from the application's public-evidence cache.

### Citation verification versus scientific meaning

- **PCSK9:** 4 accepted A/B claims; 11/11 citations have a retrieved record and exact field excerpt. Current replay objections: Approval absence requires current authoritative verification; ChEMBL phase or missing metadata cannot establish nonapproval. Explicitly state that current regulatory status is unknown when unverified..
- **BACE1:** 4 accepted A/B claims; 8/8 citations have a retrieved record and exact field excerpt. Current replay objections: .
- **preclinical:** 3 accepted A/B claims; 7/7 citations have a retrieved record and exact field excerpt. Current replay objections: Unqualified literature-absence claim: bounded evidence cannot establish that a question is untested; qualify the gap to the cited sources and retain prior-art uncertainty..

Those ratios do not prove semantic correctness. Manual review found:

- PCSK9 correctly recognized approved antibody/LDL-lowering precedent, treatment
  restrictions, historical economic estimates and operational stop reasons.
  It nevertheless relied on stale ChEMBL approval metadata for lerodalcibep.
  Hypersensitivity is documented; its attribution to anti-drug immunogenicity or
  target-specific toxicity is not established by the quoted warning. C failed an
  exact prior-art citation check; no experimental correctness is claimed.
- BACE1's accepted efficacy/safety statements match the clinical papers and registry
  stop reasons. It explicitly distinguished on-target from compound-specific risk
  and did not infer universal target invalidity. Its proposed on-target versus
  off-target cognitive-toxicity comparison overlaps relevant selective-inhibitor,
  spine-density and BACE2-selectivity literature; final review withheld it.
- Rett correctly distinguished observational CSF findings, human iPSC rescue and
  differing cellular/species/developmental models. Its two competing explanations
  were scientifically distinguishable and limitations acknowledged shared evidence.
  The accepted unqualified `remains untested` uncertainty was not justified by a
  bounded packet; the current guard objects to it. C considered staged selective
  restoration in female mosaic mice, but related prior work was flagged. This
  does not prove every proposed circuit/stage detail was already answered.

Experiments remain unperformed/unvalidated. No live screening was approved or run.

## Performance: actual measurements, with scope

The following compares the initial pre-fix retrieval against the later corrected,
cached 14-case checkpoint. Corpora/query policies changed, so this is **not** a
controlled speedup experiment. Times are backend monotonic retrieval seconds,
not provider time, browser polling time or guaranteed future performance.

| Case | Initial retrieval s | Corrected cached retrieval s | Cached hits / upstream logical requests |
|---|---:|---:|---:|
| CCR5 | 54.32 | 17.26 | 221 / 0 |
| PCSK9 | 42.64 | 17.52 | 243 / 1 |
| EGFR | 61.05 | 26.09 | 241 / 1 |
| BACE1 | 16.11 | 6.22 | 55 / 0 |
| LRRK2 | 10.97 | 3.62 | 49 / 0 |
| BCL2 | 21.63 | 1.87 | 25 / 0 |
| preclinical | 4.26 | 0.64 | 12 / 0 |
| unsupported | 35.95 | 3.63 | 54 / 0 |
| fabricated | 0.71 | 0.07 | 2 / 0 |
| invalid_disease | 48.48 | 23.52 | 220 / 1 |
| GLP1R | 103.49 | 49.71 | 696 / 1 |
| CFTR | 54.67 | 25.68 | 327 / 0 |
| SMN2 | 9.71 | 61.31 | 50 / 0 |
| rare | 5.50 | 3.66 | 15 / 0 |

The same-code, forced-public-refresh Rett pair measured **55.64 s cold / 0.60 s warm**; requests were 12 and 0. The refresh included a bounded Ensembl retry. The warm job's front-door wall time was 163.92 s because it waited behind PCSK9 reasoning; it must not be represented as fast end-to-end completion.
Public source timestamps, cache provenance, retries and logical/network request
counts remain in each saved report. Missing/error responses were not cached as
successful evidence. Later regulatory retests include new FDA requests and expired
one-hour trial-search entries; they are not pure warm-cache benchmarks.

### History scalability

The last 100 rows contained 315,430,031 scientific-result characters versus 79,863 payload characters. The new history query avoids loading those scientific blobs. Three real Next-proxy history GETs took 1.1511 s, 0.5927 s, 0.5636 s. The earlier browser run timed out; no fabricated numerical before latency is claimed.

## End-to-end controls and failure handling

- Fresh live Scout discovery of cystic fibrosis completed in 12.33 s and returned
  CFTR. The actual nested handoff preserved ENSG00000001626, CHEMBL4051 and
  UniProt **P13569**.
  Component/association metadata remained metadata, not therapeutic success odds.
- Real public jobs were persisted and retrieved through the Next proxy; API and
  SQLite report objects were checked for equality. Cached results were not replaced
  with recorded demonstrations.
- Recorded BACE1/LRRK2 demonstrations, changing target selection, stale-session
  protection, explicit paid consent and approval-gated screening were exercised
  in browser tests. Earlier live saved jobs were not represented as fresh model calls.
- Actual unauthorized `/api/screen` and legacy `/api/approvals` requests returned
  403. An unconfirmed researcher decision returned 400. Reusing an existing public
  idempotency key returned the same job with `created: false`, without a new run.
- During the isolated frontend production rebuild a public-only poller lost its
  connection. Its backend job completed and the manifest resumed that same job;
  no duplicate or cancellation occurred. This was a test-server interruption,
  not an interruption to the user's original application.
- Live source retries/outages occurred (including OLS 404 and transient Ensembl/
  Europe PMC errors); statuses and retries remained traceable. Controlled timeout,
  malformed response, partial-outage and SDK failure cases are automated test
  coverage, not invented live provider failures. The current 13 provider calls
  all succeeded at transport/schema level.
- Source/packet/audit IDs and complete records remain available. Positive clinical
  context, negative studies, operational reasons and missing outcome information
  are distinct. A terminated trial is never, by itself, an efficacy result.

## Final automated validation

Final results: **266 Python tests passed in 35.06 s; 24 browser tests passed; TypeScript checks, frontend lint and the production build passed.** No paid calls were made by these checks. Final browser wall duration was not retained. Commands and validation configuration are recorded in `validation/cross_disease/test_results.json`.
The initial baseline passed 248 Python and 18 browser tests. New regressions cover
aliases, invalid identifiers, historical phase/current approval disagreement,
product suffixes, shared genes, unqualified gaps, retained rejected drafts,
conference records and metadata-only history. Browser regressions read actual
saved cross-disease jobs through the production Next proxy and render the FDA /
ChEMBL disagreement. Initial failures were investigated rather than hidden.

Passing these checks establishes tested software behavior, not biological accuracy.

## Four-minute supervised demonstration

1. Prewarm the **exact** BACE1/disease selection through public-only mode shortly
   before the presentation. Verify expected papers, source dates, source coverage
   and that no other investigation is queued. Cache keys include supplied IDs;
   changing a manual selection to a Scout selection may use different cache keys.
2. Authorize at most five model attempts for the actual demonstration. Show real
   stage durations and source-linked objections/revisions. The measured fresh
   BACE1 job took 132.81 s; no promise is made that a later cold/provider run will.
3. Explain the documented failure/safety findings and why they do not establish
   global target invalidity. Show the prior-art warning/withheld proposal honestly.
4. End with researcher review/Revise, not an automatic stop or screening approval.
   If the network/model fails, show that fail-closed state or explicitly open a
   labelled saved result. Never claim a saved report is a new live model run.

For positive precedent, show the **current PCSK9 source evidence and FDA/ChEMBL
disagreement** rather than claiming its failed C output was validated. Rett is a
useful early-stage example, but its gap/proposal still needs expert novelty review.
Do not select SMN2 or a rare gene-therapy pair as the primary live demonstration
until gene-specific programme curation and current safety-source coverage improve.

## Reproduction and artifacts

`scripts/cross_disease_references.py` resolves public identity references;
`cross_disease_landmarks.py` independently verifies the landmark corpus;
`cross_disease_jobs.py` uses the actual Next/Flask job pathway with durable manifests;
`cross_disease_inventory.py` checks saved records offline. Full response bundles
ending `_sources.json` remain ignored locally. The inspectable inventory, reference
IDs, manifests, call ledger, controls, history measurements and final backend
configuration are in `validation/cross_disease/`.

`cross_disease_paid.py --authorized` was used under this task's explicit permission.
**Do not run it as an automatic new benchmark:** manifests only resume existing
jobs and the current audit budget is spent as recorded; failed jobs are not retried.
Any further paid investigation needs new authorization and a reviewed budget.

The final isolated backend was checked against its on-disk source hash with AI
disabled for unpaid validation. Paid jobs used checkpoint hash b16ff4f63df9ac9072fd;
later regulatory/guard/history fixes were tested without further paid calls. Full
metadata records those code boundaries. The final report is therefore candid
about which scientific outputs were generated before the final corrections.

Use the normal local backend restart to load the changes when convenient; this
audit did not restart the user's original application. No real patient-level data
were introduced, and existing dataset/licence caveats remain in README.
