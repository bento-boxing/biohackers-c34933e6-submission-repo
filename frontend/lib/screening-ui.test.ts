import { describe, expect, it } from 'vitest';
import type { Compound } from './scout-types';
import { SCREEN_COLUMN_HELP, clinicalLabel, drugLikenessLabel, orderCompounds, potencyLabel, rankShift, selectivityLabel, warnings } from './screening-ui';

function compound(over: Partial<Compound> = {}): Compound {
  return {
    chembl_id: 'CHEMBL1', name: 'X', best_pchembl: 9, assay_type: 'B', max_phase: null, is_approved: false, mw: null, alogp: null,
    hbd: null, hba: null, psa: null, ro5_violations: 0, lipinski_pass: true, chembl_url: '', qed: 0.62, first_approval: null,
    potency: { n_records: 3, n_assays: 2, n_documents: 1, n_exact: 3, n_censored: 0, n_functional: 0, n_without_pchembl: 0, by_type: {},
      primary_type: 'IC50', aggregate_pchembl: 8.1, aggregate_n: 3, aggregate_method: 'median', range: [7.9, 8.4], spread: 0.5,
      conflicting: false, sparse: false, max_pchembl: 9, max_record: null, flags: [], records: [], records_omitted: 0 },
    clinical: { phase: null, phase_label: 'No development record', indication_status: 'preclinical', matched: [], matched_max_phase: null, other_count: 0, other_examples: [], note: '' },
    selectivity: { status: 'assessed', evidence: 'observed_window', window: 1.9, targets_tested: 3, assays_tested: 5, records: 7, comparable_records: 4,
      incomparable_records: 3, off_targets: [], most_potent_comparable_off_target: { target_chembl_id: 'CHEMBL1862', name: 'ABL', median_pchembl: 6.2, n: 2 },
      comparison_type: 'IC50', partial: false, caution: '', note: '' },
    factors: { potency: 0.775, drug_likeness: 0.62, selectivity: 0.97, clinical: 0, weights_used: {}, missing: [], objective: 'balanced' },
    priority_score: 0.8, rank: 1, baseline_rank: 3, rank_reason: 'because', missing_data: [], ...over,
  };
}

describe('screening labels', () => {
  it('describes potency by its aggregate and context, never by the maximum alone', () => {
    expect(potencyLabel(compound())).toBe('8.10 (IC50 median of 3, 2 assays; max 9.00)');
    const none = compound({ potency: { ...compound().potency!, aggregate_pchembl: null, primary_type: null } });
    expect(potencyLabel(none)).toMatch(/no aggregate/i);
    expect(potencyLabel(none)).toMatch(/9\.00/);
  });
  it('distinguishes missing drug-likeness values from poor ones', () => {
    expect(drugLikenessLabel(compound())).toBe('QED 0.62 · Ro5 violations 0');
    expect(drugLikenessLabel(compound({ qed: null, ro5_violations: 3 }))).toBe('QED not recorded · Ro5 violations 3');
    expect(drugLikenessLabel(compound({ qed: null, ro5_violations: null }))).toBe('Not recorded');
  });
  it('qualifies the clinical phase by indication', () => {
    expect(clinicalLabel(compound())).toBe('No development record');
    const other = compound({ clinical: { ...compound().clinical!, phase: 4, phase_label: 'Approved (phase 4)', indication_status: 'other_indications_only', other_count: 2 } });
    expect(clinicalLabel(other)).toBe('Approved (phase 4) · other indications only (2)');
    const matched = compound({ clinical: { ...compound().clinical!, phase: 2, phase_label: 'Phase 2', indication_status: 'matched' } });
    expect(clinicalLabel(matched)).toBe('Phase 2 · for the approved disease');
  });
  it('never presents absent off-target records as selectivity', () => {
    expect(selectivityLabel(compound())).toBe('+1.90 log vs ABL · 3 targets, 5 assays tested');
    const untested = compound({ selectivity: { ...compound().selectivity!, evidence: 'no_off_target_records', window: null, targets_tested: 0 } });
    expect(selectivityLabel(untested)).toBe('No off-target records · untested, not selective');
    expect(selectivityLabel(compound({ selectivity: { ...compound().selectivity!, evidence: 'not_assessed', status: 'not_assessed', window: null } }))).toBe('Not assessed');
    expect(selectivityLabel(compound({ selectivity: { ...compound().selectivity!, evidence: 'no_comparable_off_target_records', window: null, targets_tested: 2 } }))).toBe('No comparable records · 2 targets tested');
  });
  it('collects missing-data and evidence warnings', () => {
    const c = compound({ missing_data: ['QED not recorded', 'factor:selectivity'], potency: { ...compound().potency!, sparse: true, conflicting: true, flags: ['Single exact IC50 measurement', 'Conflicting measurements'] },
      selectivity: { ...compound().selectivity!, partial: true } });
    const w = warnings(c);
    expect(w).toContain('QED not recorded');
    expect(w).toContain('Selectivity not scored (excluded from the composite)');
    expect(w).toContain('Single exact IC50 measurement');
    expect(w).toContain('Off-target retrieval truncated');
    expect(w).not.toContain('factor:selectivity');
  });
  it('reports rank movement against the potency-only baseline and orders either way', () => {
    expect(rankShift(compound())).toBe(2);
    const a = compound({ chembl_id: 'A', rank: 2, baseline_rank: 1 }); const b = compound({ chembl_id: 'B', rank: 1, baseline_rank: 2 });
    expect(orderCompounds([a, b], 'rubric').map(c => c.chembl_id)).toEqual(['B', 'A']);
    expect(orderCompounds([a, b], 'baseline').map(c => c.chembl_id)).toEqual(['A', 'B']);
  });
  it('explains every screening column', () => {
    for (const key of ['rank', 'potency', 'drug_likeness', 'clinical', 'selectivity', 'warnings', 'reason'] as const) expect(SCREEN_COLUMN_HELP[key].body.length).toBeGreaterThan(40);
    expect(SCREEN_COLUMN_HELP.selectivity.body).toMatch(/not evidence/i);
    expect(SCREEN_COLUMN_HELP.drug_likeness.body).toMatch(/heuristic/i);
  });
});
