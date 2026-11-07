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

class Compound(BaseModel):
    chembl_id: str
    name: str
    synonyms: list[str] = Field(default_factory=list)
    mechanisms: list[str] = Field(default_factory=list)
    url: str

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

class Publication(BaseModel):
    identifier: str
    title: str
    abstract: str = ''
    doi: str | None = None
    relevance: str = 'Search candidate; target and disease applicability require review.'
    url: str

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
    resolution_status: Literal['resolved', 'unknown', 'unavailable', 'invalid_identifier'] = 'unknown'
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

class AIReport(BaseModel):
    enabled: bool = False
    provider: str = 'google'
    model: str = ''
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

Investigation.model_rebuild()
