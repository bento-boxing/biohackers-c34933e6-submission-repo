export type Weights = {
  genetic: number;
  association: number;
  druggability: number;
  literature: number;
};

export type Components = Weights;

export type SafetyFlag = { kind: "liability" | "expression"; detail: string };

export type ScoutTarget = {
  target_id: string;
  symbol: string;
  name: string;
  uniprot: string | null;
  chembl_target_id: string | null;
  components: Components;
  potent_count: number;
  has_approved_drug: boolean;
  literature_hits: number;
  pmids: string[];
  safety_flags: SafetyFlag[];
  tractability_sm_labels: string[];
  open_targets_url: string;
};

export type ScoutRun = {
  run_id: string;
  disease: { id: string; name: string };
  cache_only: boolean;
  default_weights: Weights;
  targets: ScoutTarget[];
};

export type Scores = Components & { total: number };

export type Approval = {
  ts: string;
  disease_id: string;
  disease_name: string;
  target_id: string;
  symbol: string;
  uniprot: string | null;
  chembl_target_id: string | null;
  weights: Weights;
  scores: Scores;
  safety_flags: string[];
  reason: string;
  approved_by: string;
};

export type Rationale = {
  symbol: string;
  rationale: string;
  evidence_strength: "strong" | "moderate" | "weak";
};

export type RationaleResponse =
  | { available: false; reason: string }
  | { available?: true; run_id: string; weights: Weights; rationales: Rationale[] };
