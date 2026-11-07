"""Dataclasses shared by the pipeline, the API and the tests."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Literal


@dataclass(frozen=True)
class Weights:
    genetic: float = 0.4
    association: float = 0.3
    druggability: float = 0.2
    literature: float = 0.1

    def normalised(self) -> "Weights":
        total = self.genetic + self.association + self.druggability + self.literature
        if total <= 0:
            return Weights()
        return Weights(self.genetic / total, self.association / total,
                       self.druggability / total, self.literature / total)

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass
class Disease:
    id: str
    name: str


@dataclass
class SafetyFlag:
    kind: Literal["liability", "expression"]
    detail: str


@dataclass
class TargetEvidence:
    target_id: str
    symbol: str
    name: str
    uniprot: str | None
    ot_score: float
    datatype_scores: dict[str, float]
    tractability: list[dict]
    has_approved_drug: bool
    literature_hits: int = 0
    pmids: list[str] = field(default_factory=list)
    chembl_target_id: str | None = None
    potent_count: int = 0
    safety_flags: list[SafetyFlag] = field(default_factory=list)


@dataclass
class ComponentScores:
    genetic: float
    association: float
    druggability: float
    literature: float
    total: float


@dataclass
class ScoredTarget:
    evidence: TargetEvidence
    scores: ComponentScores
    rationale: str | None = None
    evidence_strength: str | None = None


@dataclass
class ScoutResult:
    disease: Disease
    weights: Weights
    targets: list[ScoredTarget]


@dataclass
class Approval:
    ts: str
    disease_id: str
    disease_name: str
    target_id: str
    symbol: str
    uniprot: str | None
    chembl_target_id: str | None
    weights: dict
    scores: dict
    safety_flags: list[str]
    reason: str
    approved_by: str

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, line: str) -> "Approval":
        return cls(**json.loads(line))


@dataclass
class Compound:
    chembl_id: str
    name: str | None
    best_pchembl: float
    assay_type: str | None
    max_phase: str | None
    mw: float | None
    alogp: float | None
    hbd: int | None
    hba: int | None
    psa: float | None
    ro5_violations: int | None

    @property
    def is_approved(self) -> bool:
        return self.max_phase == "4.0"

    @property
    def lipinski_pass(self) -> bool | None:
        if self.ro5_violations is None:
            return None
        return self.ro5_violations <= 1


@dataclass
class Structure:
    uniprot: str
    model_id: str
    pdb_url: str
    cif_url: str
    mean_plddt: float
    fraction_confident: float


@dataclass
class ScreeningResult:
    approval: Approval
    structure: Structure | None
    compounds: list[Compound]
