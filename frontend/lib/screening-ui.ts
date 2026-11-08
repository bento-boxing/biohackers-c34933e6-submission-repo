import type { Compound } from './scout-types';

export type ScreenView = 'rubric' | 'baseline';

/** Column explanations for the screening table (hover tooltips). */
export const SCREEN_COLUMN_HELP = {
  rank: { title: 'Rank', body: 'Position under the selected prioritisation rubric, a documented heuristic over the four factors shown. The small arrow is the movement against the potency-only baseline (max pChEMBL), which you can switch to for comparison.' },
  potency: { title: 'Potency', body: 'Median pChEMBL of exact (relation "=") binding-assay measurements of one type (IC50, Ki, Kd or EC50); types are never pooled. The maximum value is shown only as the baseline. Single or conflicting measurements are flagged, and a candidate without an exact binding measurement gets no aggregate and sorts last.' },
  drug_likeness: { title: 'Drug-likeness', body: 'ChEMBL QED (0 to 1) and Lipinski rule-of-five violations as recorded. Both are computed heuristics about oral small-molecule properties, not predictors of clinical success. "Not recorded" means the value is missing, which is different from a poor value and is excluded from the composite.' },
  clinical: { title: 'Clinical stage', body: 'Highest ChEMBL development phase, qualified by indication: development for the approved disease is marked separately from development for other indications. A phase reached in another disease is human-exposure precedent, not evidence of efficacy here.' },
  selectivity: { title: 'Selectivity (observed)', body: 'Observed off-target activity in ChEMBL for shortlisted molecules only: how many targets and assays were actually tested and the window between the on-target median and the strongest comparable off-target median of the same measurement type. Untested targets are unknown, and a lack of off-target records is not evidence of selectivity.' },
  warnings: { title: 'Warnings', body: 'Missing values, sparse or conflicting measurements, truncated retrieval and factors excluded from the composite. Nothing here is hidden inside the score: a missing factor removes it from the weighted mean instead of counting as zero.' },
  reason: { title: 'Why this position', body: 'The factor values that produced the rank, which factors were missing and therefore excluded, and the objective in force. Read it as an explanation of the heuristic, not as a prediction of success.' },
} as const;

const f2 = (x: number) => x.toFixed(2);

export function potencyLabel(c: Compound): string {
  const p = c.potency;
  if (!p) return 'Not retrieved';
  const max = p.max_pchembl === null ? 'none' : f2(p.max_pchembl);
  if (p.aggregate_pchembl === null) return `No aggregate (no exact binding measurement; max ${max} isolated)`;
  return `${f2(p.aggregate_pchembl)} (${p.primary_type} median of ${p.aggregate_n}, ${p.n_assays} assay${p.n_assays === 1 ? '' : 's'}; max ${max})`;
}

export function drugLikenessLabel(c: Compound): string {
  if (c.qed === null && c.ro5_violations === null) return 'Not recorded';
  const qed = c.qed === null ? 'QED not recorded' : `QED ${f2(c.qed)}`;
  const ro5 = c.ro5_violations === null ? 'Ro5 not recorded' : `Ro5 violations ${c.ro5_violations}`;
  return `${qed} · ${ro5}`;
}

export function clinicalLabel(c: Compound): string {
  const k = c.clinical;
  if (!k) return c.max_phase ? `Phase ${c.max_phase}` : 'Unknown';
  switch (k.indication_status) {
    case 'matched': return `${k.phase_label} · for the approved disease`;
    case 'other_indications_only': return `${k.phase_label} · other indications only (${k.other_count})`;
    case 'no_indication_records': return `${k.phase_label} · indication not recorded`;
    case 'not_checked': return `${k.phase_label} · indication not checked`;
    default: return k.phase_label;
  }
}

export function selectivityLabel(c: Compound): string {
  const s = c.selectivity;
  if (!s || s.evidence === 'not_assessed') return 'Not assessed';
  if (s.evidence === 'no_off_target_records') return 'No off-target records · untested, not selective';
  if (s.evidence === 'no_comparable_off_target_records') return `No comparable records · ${s.targets_tested} target${s.targets_tested === 1 ? '' : 's'} tested`;
  const sign = (s.window ?? 0) >= 0 ? '+' : '';
  return `${sign}${f2(s.window ?? 0)} log vs ${s.most_potent_comparable_off_target?.name ?? 'off-target'} · ${s.targets_tested} targets, ${s.assays_tested} assays tested`;
}

const FACTOR_NAMES: Record<string, string> = { potency: 'Potency', drug_likeness: 'Drug-likeness', selectivity: 'Selectivity', clinical: 'Clinical stage' };

export function warnings(c: Compound): string[] {
  const out: string[] = [];
  for (const m of c.missing_data) {
    if (m.startsWith('factor:')) out.push(`${FACTOR_NAMES[m.slice(7)] ?? m.slice(7)} not scored (excluded from the composite)`);
    else out.push(m);
  }
  for (const flag of c.potency?.flags ?? []) if (/single|conflict|no exact|validity/i.test(flag)) out.push(flag);
  if (c.selectivity?.partial) out.push('Off-target retrieval truncated');
  if (c.clinical?.indication_status === 'not_checked') out.push('Indication not checked');
  return Array.from(new Set(out));
}

/** Positive = moved up relative to the potency-only baseline. */
export function rankShift(c: Compound): number | null {
  if (c.rank === null || c.baseline_rank === null) return null;
  return c.baseline_rank - c.rank;
}

export function orderCompounds(compounds: Compound[], view: ScreenView): Compound[] {
  const key = view === 'rubric' ? (c: Compound) => c.rank ?? Number.MAX_SAFE_INTEGER : (c: Compound) => c.baseline_rank ?? Number.MAX_SAFE_INTEGER;
  return [...compounds].sort((a, b) => key(a) - key(b));
}
