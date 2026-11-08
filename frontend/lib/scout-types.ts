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
  /** Raw TargetEvidence from the server; posted back verbatim for stateless rationale. */
  evidence?: Record<string, unknown>;
  /** Server-signed claims (ids, components, safety flags) a later approval relies on. */
  sig?: string;
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
  /** Immutable unique id issued by the server; the only thing /api/screen keys on. */
  approval_id: string;
  decision_id?: string | null;
  action?: string;
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
  /** HMAC issued by the workbench server; required by /api/screen. */
  signature?: string;
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
  /** Four-factor evidence. null = not available (never zero). */
  qed: number | null;
  first_approval: number | null;
  potency: PotencySummary | null;
  clinical: ClinicalSummary | null;
  selectivity: SelectivitySummary | null;
  factors: FactorScores | null;
  priority_score: number | null;
  rank: number | null;
  baseline_rank: number | null;
  rank_reason: string;
  missing_data: string[];
};

export type ActivityRecord = {
  activity_id: number | null; molecule_chembl_id: string; assay_chembl_id: string | null; assay_type: string | null;
  assay_description: string | null; bao_label: string | null; standard_type: string | null; standard_relation: string | null;
  standard_value: string | null; standard_units: string | null; pchembl_value: number | null; target_chembl_id: string | null;
  document_chembl_id: string | null; data_validity_comment: string | null; potential_duplicate: number | null;
};

export type PotencySummary = {
  n_records: number; n_assays: number; n_documents: number; n_exact: number; n_censored: number; n_functional: number;
  n_without_pchembl: number; by_type: Record<string, { n: number; median: number; min: number; max: number; assays: number }>;
  primary_type: string | null; aggregate_pchembl: number | null; aggregate_n: number; aggregate_method: string;
  range: [number, number] | null; spread: number | null; conflicting: boolean; sparse: boolean;
  max_pchembl: number | null; max_record: Record<string, string | number | null> | null; flags: string[];
  records: ActivityRecord[]; records_omitted: number;
};

export type ClinicalSummary = {
  phase: number | null; phase_label: string;
  indication_status: 'matched' | 'other_indications_only' | 'no_indication_records' | 'preclinical' | 'not_checked';
  matched: { efo_id: string | null; efo_term: string; mesh_heading: string; max_phase_for_ind: number | null }[];
  matched_max_phase: number | null; other_count: number; other_examples: string[]; note: string;
};

export type OffTarget = {
  target_chembl_id: string; name: string; organism: string | null; n: number; assays: number; max_pchembl: number | null;
  comparable: boolean; comparable_n: number; comparable_median: number | null; types: string[];
};

export type SelectivitySummary = {
  status: 'assessed' | 'not_assessed';
  evidence: 'observed_window' | 'no_off_target_records' | 'no_comparable_off_target_records' | 'not_assessed';
  window: number | null; targets_tested: number; assays_tested: number; records: number; comparable_records: number;
  incomparable_records: number; off_targets: OffTarget[]; off_targets_omitted?: number;
  most_potent_comparable_off_target: { target_chembl_id: string; name: string; median_pchembl: number; n: number } | null;
  comparison_type: string | null; partial: boolean; caution: string; note: string;
};

export type FactorScores = {
  potency: number | null; drug_likeness: number | null; selectivity: number | null; clinical: number;
  weights_used: Record<string, number>; missing: string[]; objective: string;
};

export type RubricObjective = 'balanced' | 'novel_candidates' | 'repurposing';

export type RubricDescription = {
  objective: RubricObjective; weights: Record<string, number>; caveat: string; objectives: RubricObjective[];
  factors: Record<string, string>;
};

export type ScreeningCoverage = {
  partial: boolean; elapsed_seconds?: number;
  stage1?: { total_count: number; retrieved: number; complete: boolean; cutoff_pchembl: number | null; order_by: string; selection_method: string };
  candidate_pool?: { size: number; molecules_retrieved: number; method: string };
  stage2?: { molecules: number; records: number; truncated_batches: number };
  indications?: { molecules_checked: number; molecules_with_records: number };
  stage3?: { molecules_assessed: number; shortlist: string[]; truncated_batches: number; skipped_for_budget: string[]; method: string };
};

export type ScreeningResult = {
  approval: Approval;
  structure: Structure | null;
  compounds: Compound[];
  coverage: ScreeningCoverage;
  rubric: RubricDescription;
  /** ChEMBL ids in the preserved potency-only (baseline) order. */
  baseline: string[];
  notes: string[];
};
