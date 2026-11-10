"""Serializable contract for Target Scout and the standalone application."""
from typing import Literal
from pydantic import BaseModel, Field

Concern = Literal['efficacy', 'safety', 'operational', 'unknown', 'other']

class TargetInput(BaseModel):
    disease_name: str = Field(min_length=1, max_length=200)
    disease_id: str | None = None
    target_symbol: str = Field(min_length=1, max_length=80)
    target_id: str | None = None
    chembl_target_id: str | None = Field(default=None, pattern=r'^CHEMBL\d+$')
    uniprot: str | None = Field(default=None, max_length=30)
    disease_aliases: list[str] = Field(default_factory=list, max_length=30)
    target_aliases: list[str] = Field(default_factory=list, max_length=30,description='Derived from the resolved human ChEMBL component; supplied values are cleared before live investigation.')
    protein_gene_symbols: list[str] = Field(default_factory=list,max_length=30,description='Canonical genes sharing the curated protein component; not interchangeable therapeutic gene targets.')

class Compound(BaseModel):
    chembl_id: str
    name: str
    synonyms: list[str] = Field(default_factory=list)
    mechanisms: list[str] = Field(default_factory=list)
    url: str
    max_phase: float | None = None
    approval_source_url: str = ''
    indications: list[dict] = Field(default_factory=list)
    indication_search_state: str = 'not_searched'
    withdrawn_flag: bool | None = None
    first_approval: int | None = None
    molecule_type: str | None = None
    mechanism_records: list[dict] = Field(default_factory=list)
    regulatory_approvals: list[dict] = Field(default_factory=list)

class StopReasonEvidence(BaseModel):
    state: Literal['reported', 'absent', 'empty', 'null', 'invalid', 'unverified', 'record_missing', 'api_error'] = 'unverified'
    value: str | None = None
    full_record_checked: bool = False
    source_url: str = ''
    checked_at_utc: str | None = None
    detail: str = ''
    search_value: str | None = None
    search_state: str | None = None

class Trial(BaseModel):
    nct_id: str = Field(pattern=r'^NCT\d{8}$')
    title: str
    status: str
    why_stopped: str = ''
    stop_reason: StopReasonEvidence = Field(default_factory=StopReasonEvidence)
    conditions: list[str] = Field(default_factory=list)
    interventions: list[str] = Field(default_factory=list)
    population: str = ''
    has_results: bool = False
    compound_ids: list[str] = Field(default_factory=list)
    compound_matches: dict[str, Literal['verified', 'probable']] = Field(default_factory=dict)
    relationship: Literal['verified', 'probable', 'uncertain'] = 'uncertain'
    match_reason: str = ''
    disease_match: Literal['matched', 'uncertain'] = 'uncertain'

    outcome_records: list[dict] = Field(default_factory=list)
    url: str
    phases: list[str] = Field(default_factory=list)
    publication_ids: list[str] = Field(default_factory=list)
    start_date: str | None = None
    completion_date: str | None = None
    last_update_date: str | None = None
    results_posted_date: str | None = None
    evidence_tier: str = 'registry_status'
    search_terms: list[str] = Field(default_factory=list, description='Intervention/full-text query terms that returned this record; registry indexing, not a verified compound link.')

class Publication(BaseModel):
    identifier: str
    title: str
    abstract: str = ''
    doi: str | None = None
    relevance: str = 'Search candidate; target and disease applicability require review.'
    url: str
    clinical_candidate: bool = False
    direction_signals: list[str] = Field(default_factory=list)
    conclusion_excerpt: str = ''
    disease_match: Literal['matched', 'uncertain'] = 'uncertain'
    cited_by_count: int = 0
    study_types: list[str] = Field(default_factory=list)
    evidence_scope: str = 'unassessed'
    biological_signals: list[str] = Field(default_factory=list)
    scope_reason: str = ''
    publication_date: str | None = None
    evidence_tier: str = 'unverified'
    discovered_by: str = 'initial retrieval'

class SearchAudit(BaseModel):
    source: str
    operation: str
    url: str
    query: dict = Field(default_factory=dict)
    state: Literal['found', 'no_results', 'failed', 'not_searched', 'limit_reached']
    returned: int = 0
    relevant: int = 0
    total: int | None = None
    detail: str = ''

class EvidenceCoverage(BaseModel):
    status: Literal['INSUFFICIENT COVERAGE', 'BOUNDED REVIEW']
    gaps: list[str] = Field(default_factory=list)
    facets: dict = Field(default_factory=dict)
    selected_source_ids: list[str] = Field(default_factory=list)
    omitted_source_ids: list[str] = Field(default_factory=list)
    selection_reasons: dict[str, list[str]] = Field(default_factory=dict)
    duration_seconds: float = 0.
    caution: str = 'Bounded retrieval is not a systematic review; missing evidence is not evidence of inefficacy.'
    pathway: Literal['clinical_precedent', 'preclinical_validation', 'unresolved'] = 'unresolved'
    reasoning_permitted: bool = False
    criteria_version: str = 'pathways-v1'

class BiologicalAssociation(BaseModel):
    strength: Literal['clinical_context', 'exploratory', 'insufficient']
    direct_source_ids: list[str] = Field(default_factory=list)
    indirect_source_ids: list[str] = Field(default_factory=list)
    unrelated_source_ids: list[str] = Field(default_factory=list)
    independent_groups: int = 0
    evidence_types: list[str] = Field(default_factory=list)
    explanation: str
    limitations: list[str] = Field(default_factory=list)
    ontology_association: dict = Field(default_factory=dict)

NeedStatus = Literal['satisfied', 'partial', 'unmet', 'not_applicable', 'unverifiable']

class EvidenceNeed(BaseModel):
    key: str
    label: str
    status: NeedStatus = 'unmet'
    evidence_ids: list[str] = Field(default_factory=list)
    material_ids: list[str] = Field(default_factory=list, description='Records the packet must not drop; selected by deterministic rules.')
    searches: list[str] = Field(default_factory=list, description='Operation names of follow-up searches issued for this need.')
    note: str = ''
    applies_to: Literal['clinical', 'preclinical', 'both'] = 'both'

class EvidenceSearch(BaseModel):
    need_key: str
    source: str
    operation: str
    query: dict = Field(default_factory=dict)
    state: Literal['found', 'no_results', 'failed', 'not_searched', 'limit_reached', 'skipped']
    returned: int = 0
    new_evidence_ids: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.
    detail: str = ''

class EvidenceRound(BaseModel):
    round_number: int
    unmet_before: list[str] = Field(default_factory=list)
    searches: list[EvidenceSearch] = Field(default_factory=list)
    new_evidence_ids: list[str] = Field(default_factory=list)
    unmet_after: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.

class EvidencePlan(BaseModel):
    stage: Literal['clinical', 'preclinical', 'unresolved'] = 'unresolved'
    stage_reason: str = ''
    identifiers: dict = Field(default_factory=dict)
    needs: list[EvidenceNeed] = Field(default_factory=list)
    rounds: list[EvidenceRound] = Field(default_factory=list)
    max_rounds: int = 2
    stop_reason: str = 'not_run'
    planner: str = 'deterministic'
    planner_suggestions: list[dict] = Field(default_factory=list, description='Optional model-suggested searches; suggestions are never evidence.')
    limitations: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.
    caution: str = 'A satisfied need means source records were retrieved and scoped, not that the science is settled. Unmet needs after bounded search are not evidence of absence.'

class Claim(BaseModel):
    claim_id: str
    text: str
    kind: Literal['fact', 'interpretation']
    concern: Concern = 'unknown'
    stance: Literal['supporting', 'contradictory', 'context'] = 'context'
    source_id: str
    source_field: str
    excerpt: str
    relevance: str
    source_url: str = ''
    uncertainty: str = 'Insufficient evidence for a therapeutic conclusion.'
    verified: bool = False

class Revision(BaseModel):
    claim_id: str
    objection: str
    action: str

class Assessment(BaseModel):
    source_ids: list[str]
    historical_evidence: str
    concern: Concern
    relevance: str
    limitations: list[str]
    recommendation: Literal['retain', 'revise', 'escalate']
    rationale: str
    compound_specificity: str = 'Unknown; compound-specific and target-mediated effects are not distinguished.'
    target_engagement: str = 'Unknown; an intervention name is not proof of engagement.'

class Investigation(BaseModel):
    target: TargetInput
    mode: Literal['live', 'offline']
    resolved_target_id: str | None = None
    resolution_status: Literal['resolved', 'gene_verified', 'unknown', 'unavailable', 'invalid_identifier'] = 'unknown'
    compounds: list[Compound] = Field(default_factory=list)
    trials: list[Trial] = Field(default_factory=list)
    publications: list[Publication] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    revisions: list[Revision] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    retrieval_notes: list[str] = Field(default_factory=list)
    retrieval_errors: list[str] = Field(default_factory=list)
    assessments: list[Assessment] = Field(default_factory=list)
    conclusion: str = 'insufficient evidence'
    ai: 'AIReport | None' = None
    search_audit: list[SearchAudit] = Field(default_factory=list)
    coverage: EvidenceCoverage | None = None
    regulatory_records: list[dict] = Field(default_factory=list)
    association: BiologicalAssociation | None = None
    ontology_association: dict = Field(default_factory=dict)
    evidence_plan: EvidencePlan | None = None
    stage_timings: dict[str, float] = Field(default_factory=dict)

class Experiment(BaseModel):
    question: str
    competing_explanations: list[str]
    model: str
    measurement: str
    controls: list[str]
    possible_results: list[str]
    limitations: list[str]
    decision_impact: str
    evidence_ids: list[str]
    hypothesis_evidence: list[list[str]] = Field(default_factory=list)
    knowledge_review: str = ''
    unresolved_gap: str = ''
    scientific_claim: str = ''
    mechanism: str = ''
    context: str = ''
    prior_art_citations: list['AICitation'] = Field(default_factory=list)
    status: str = 'Proposed only; not performed or validated.'

class AICitation(BaseModel):
    source_id: str
    field: str
    excerpt: str = Field(min_length=1, max_length=1000)

class AIClaim(BaseModel):
    claim_id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=1800)
    kind: Literal['fact', 'interpretation', 'unresolved']
    concern: Concern
    stance: Literal['supporting', 'contradictory', 'context']
    citations: list[AICitation] = Field(min_length=1, max_length=3)
    relevance: str
    uncertainty: str

class ChallengeDraft(BaseModel):
    initial_assessment: str
    claims: list[AIClaim] = Field(max_length=4)
    remaining_uncertainty: list[str]

class Adjudication(BaseModel):
    claim_id: str
    verdict: Literal['supported', 'revise', 'unsupported']
    finding: str
    revision_request: str

class AdjudicationBatch(BaseModel):
    findings: list[Adjudication] = Field(max_length=4)

class Reassessment(BaseModel):
    assessment: str
    evidence_claim_ids: list[str]
    remaining_uncertainty: list[str]

class ExperimentalResponse(BaseModel):
    reassessment: Reassessment
    experiment: Experiment

class AIAuditRound(BaseModel):
    round_number: int
    draft: ChallengeDraft
    deterministic_objections: dict[str, list[str]]
    adjudications: list[Adjudication]
    accepted_claim_ids: list[str]

class AICall(BaseModel):
    role: str
    success: bool
    error: str = ''
    usage: dict[str, int] = Field(default_factory=dict)
    started_at: float | None = None
    duration_seconds: float | None = None
    payload_bytes: int | None = None

class AIReport(BaseModel):
    enabled: bool = False
    provider: str = 'anthropic'
    model: str = ''
    thinking_level: str | None = None
    status: Literal['disabled', 'skipped', 'completed', 'failed'] = 'disabled'
    calls: list[AICall] = Field(default_factory=list)
    rounds: list[AIAuditRound] = Field(default_factory=list)
    accepted_claims: list[AIClaim] = Field(default_factory=list)
    source_urls: dict[str, str] = Field(default_factory=dict)
    sent_source_ids: list[str] = Field(default_factory=list)
    source_bundle: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    reassessment: Reassessment | None = None
    experiment: Experiment | None = None
    human_approval_required: bool = True
    prior_art_check: dict = Field(default_factory=dict)
    final_checks: list[str] = Field(default_factory=list)
    packet_audit: dict = Field(default_factory=dict)
    final_draft: ExperimentalResponse | None = Field(default=None,description='Unverified final output retained for audit only; not an accepted proposal.')

Investigation.model_rebuild()
Experiment.model_rebuild()
