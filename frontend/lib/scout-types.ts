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

export type Structure = {
  uniprot: string;
  model_id: string;
  pdb_url: string;
  cif_url: string;
  mean_plddt: number;
  fraction_confident: number;
};

export type Compound = {
  chembl_id: string;
  name: string | null;
  best_pchembl: number;
  assay_type: string | null;
  max_phase: string | null;
  is_approved: boolean;
  mw: number | null;
  alogp: number | null;
  hbd: number | null;
  hba: number | null;
  psa: number | null;
  ro5_violations: number | null;
  lipinski_pass: boolean | null;
  chembl_url: string;
};

export type ScreeningResult = {
  approval: Approval;
  structure: Structure | null;
  compounds: Compound[];
};
