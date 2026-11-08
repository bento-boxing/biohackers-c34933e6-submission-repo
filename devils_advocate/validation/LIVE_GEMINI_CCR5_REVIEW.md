# Live Gemini scientific validation — 8 November 2026

**Verdict: technical pass; scientific partial pass. Suitable for a supervised
evidence-review demonstration, but the proposed experiment does not pass the
requested novelty/unresolved-question check. Do not present it as a validated
novel experiment or an autonomous research decision.**

## Authorization and actual execution

The active backend on port 5050 reported `association-pathways-v1`, loaded source
hash `a76f7c958d96b4dbbf34`, matching files on disk. The configured model was
`gemini-4-argon`, Medium thinking, maximum five attempts. No ranking or production
reasoning code was changed during this validation.

The initial authorized job `6dbe27c05275411b8eff620316ae850b` stopped before any
Gemini call because ChEMBL target retrieval returned HTTP 500 after bounded
retries. The gate correctly abstained; the application marked the job completed
with AI skipped. It took **36.432632 seconds**, with **zero model attempts**.

After the public endpoint recovered, the user explicitly authorized **one
replacement, keeping five total attempts across both jobs**. The replacement
`398304dac2fd43ae9edcf3ad044e9a7d` used the normal paid-authorized Flask/SQLite
workflow and completed. Neither failed evidence nor its report was overwritten.
Durable idempotency manifests and both reports are retained locally.

| Stage | Actual elapsed |
|---|---:|
| Replacement public retrieval | 139.197922 s |
| Devil's Advocate | 39.264179 s |
| Evidence Adjudicator | 17.853941 s |
| Experimental Challenger | 35.829706 s |
| Total model-attempt time | 92.947826 s |
| Replacement submission → completed-report observation | 238.884471 s |

**Three attempts succeeded, zero retries, three of five aggregate authorized
attempts used.** All four initial claims were accepted by the adjudicator, so
the normal workflow correctly omitted its conditional revision round. The two
remaining attempts were not spent on an unrequested additional workflow.
The SDK was configured for one attempt per SDK request and no automatic
continuation; application attempts, including retries, are budgeted.

Coverage passed as **BOUNDED REVIEW / clinical_precedent**, before construction
of the model runner. Retrieval returned **12 compounds, 136 trials and 138
publications**, with one public-response cache hit. The packet included
MOTIVATE (MED:18832244), MERIT (MED:20151839), the PRO 140 fusion-inhibitor paper
(MED:40130879), CNS pharmacology context (MED:21987241), six trials, curated
compound records and two label submissions. It remained a selected bounded
packet, not an exhaustive review.

Provider-reported totals across the three calls: **99,990 input tokens, 4,689
output tokens, 1,047 thought tokens, 105,726 total tokens, zero cached tokens**.
These are recorded usage fields, not a cost estimate or a thinking-level speed
comparison. Individual payload bytes and usage remain in the JSON report.

## Scientific checks

### Established efficacy: pass, within the stated scope

The challenger and final reassessment explicitly recognized maraviroc benefit
in treatment-experienced R5 HIV-1 patients receiving optimized background therapy.
They retained the combination-treatment and CCR5-tropism restrictions instead of
concluding that CCR5 was invalid or that missing studies proved inefficacy.
The model also separated recruitment termination from efficacy failure and did
not claim that safety events establish an on-target class mechanism.

Supporting primary/official sources:

- [MOTIVATE, PMID 18832244](https://pubmed.ncbi.nlm.nih.gov/18832244/): improved
  virologic suppression and CD4 outcomes in the studied R5 population with
  optimized background therapy.
- [Maraviroc label](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=09ec3e79-c0d3-4b8f-80d8-0a854c4ca339): indication, population limitations and warnings.
- [MERIT, PMID 20151839](https://pubmed.ncbi.nlm.nih.gov/20151839/): primary
  noninferiority limitations and retrospective analysis using more sensitive
  tropism screening. A failure on one endpoint does not invalidate the target.

### Citation verification: pass for provenance; not blanket entailment

All **four accepted claims / twelve citation references** resolve to actual
retrieved records; all excerpts exactly match their supplied packet fields.
Independent replay of deterministic citation checks produced zero objections.
No fabricated source identifier was found. Compound `approval_metadata` is
constructed source-linked metadata, not a verbatim prose field from a registry.

Manual source review nevertheless identified scope issues the adjudicator did
not request revisions for:

1. **Claim 2 needs tighter population and causal wording.** MERIT is treatment-
   naive, whereas the label's screening-to-baseline tropism result changes came
   from treatment-experienced subjects. The adjudicator noted the distinction,
   but accepted wording that combines them as a compounded vulnerability. These
   are related observations, not a same-cohort causal demonstration. A changed
   tropism assay result does not by itself prove a newly arising viral switch.
   The final reassessment correctly labels the treatment-experienced population
   for the percentage, which mitigates but does not remove the initial scope issue.
2. **Claim 3 is supported by the full supplied warning section**, including the
   renal/hypotension warning. The three selected quote snippets do not individually
   cover every subclaim; exact matching of a few snippets is not atomic verification
   of every clause. Observed cardiovascular events should remain an observation,
   without attributing causality to the target or compound beyond the source.
3. **Claim 4's recruitment observation does not establish why recruitment failed.**
   The registry says recruitment problem; eligibility is tropism-gated. It does
   not document tropism gating as the cause of the operational failure.

The model adjudicator rejected/revised **zero** claims. The human review above
is separate and does not alter the original model audit or scientific records.
No unsupported target-invalidity conclusion was found, but exact source support
does not validate all causal interpretations.

### Experimental novelty / decision relevance: fail as presented

The generated question asks whether apparent R5-screened virologic escape comes
from previously undetected non-R5 variants/tropism changes or incomplete inhibition
of R5 entry. Its model is an ex vivo comparison of clinical isolates, tropism
assays, selective blockade and a bispecific fusion construct.

Those mechanisms are not a genuinely new binary uncertainty as framed:

- [Westby et al., 2006, PMID 16641282](https://pubmed.ncbi.nlm.nih.gov/16641282/)
  documents outgrowth of a pre-existing CXCR4-using reservoir rather than a
  treatment-selected co-receptor switch in the studied cases. **This publication
  was among the 138 retrieved records, but omitted from the four-publication
  Gemini packet.** Thus the system retrieved relevant prior art but failed to use
  it when labelling the experimental gap unresolved.
- [Westby et al., 2007, PMID 17182681](https://pubmed.ncbi.nlm.nih.gov/17182681/)
  shows that resistant viruses can retain CCR5 use and exploit inhibitor-bound
  receptor. The two proposed mechanisms can coexist; they are not an adequate
  mutually exclusive explanation of all clinical failures.
- [NIH tropism guidance](https://clinicalinfo.hiv.gov/en/guidelines/hiv-clinical-guidelines-adult-and-adolescent-arv/co-receptor-tropism-assays)
  already discusses assay sensitivity, non-R5 populations and R5 resistance.
- [PRO 140 fusion paper, PMID 40130879](https://pubmed.ncbi.nlm.nih.gov/40130879/)
  already reports broadened preclinical activity after adding the fusion peptide;
  simply repeating broadened tropism coverage is not established novelty.

Additional proposal problems:

- Its first hypothesis says the variants can **only** be suppressed by pairing
  CCR5 targeting with a tropism-independent fusion inhibitor. The supplied
  sources do not establish that exclusivity. A study showing one construct works
  does not prove it is the only effective strategy.
- A possible result assumes that an assay verifies **zero** non-R5 minor variants.
  A finite detection limit cannot establish absolute absence.
- Ex vivo replication and receptor occupancy cannot alone establish the primary
  cause of clinical treatment failure or justify broad clinical-development
  decisions. Combination treatment, exposure, resistant variants and population
  context require more careful interpretation.

The proposal does state that it is unperformed/unvalidated and requires human
approval. These limitations are useful, but do not make the claimed knowledge gap
new. This review does not rule out a narrower unresolved resistance question;
identifying one requires targeted prior-art review, not a declaration that the
four selected abstracts failed to answer it.

## Demo suitability and specific remaining work

**Evidence-review demo: conditionally suitable with researcher commentary.** The
live system recognizes scoped efficacy, retrieves both positive and limiting
studies, preserves citations, separates operational concerns and stays within
paid authorization. It must retain the current warnings and human approval gate.

**Autonomous novel-experiment demo: not scientifically ready.** Before presenting
an experiment as novel, the pipeline needs question-specific prior-art retrieval
over the full retrieved set, retention of relevant known-mechanism papers, and a
final novelty/entailment check that can return insufficient evidence. Adjudication
also needs stronger population matching, clause-level support and checks against
exclusive causal assertions. No further paid call or production change was made
to conceal these findings.

## Artifacts

- `live_gemini_ccr5_manifest.json`: user authorization, version and replacement ID.
- `live_gemini_ccr5_report.json`: unchanged Gemini report, timing and coverage.
- `live_gemini_ccr5_verification.json`: offline source/citation recheck and call ledger.
- `live_gemini_ccr5_sources.json`: full result, local/ignored raw source bundle.
- `live_gemini_ccr5_initial_*`: preserved initial upstream-failed attempt.

No repository publication, commit, push, ranking change, additional investigation
or extra model call followed this review. No researcher decision or experiment
execution was authorized by the validation.
