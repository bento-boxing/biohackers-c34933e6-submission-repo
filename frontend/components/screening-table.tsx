'use client';
import { useState } from 'react';
import type { Compound, RubricObjective, ScreeningResult } from '@/lib/contracts';
import { SCREEN_COLUMN_HELP, clinicalLabel, drugLikenessLabel, orderCompounds, potencyLabel, rankShift, selectivityLabel, warnings, type ScreenView } from '@/lib/screening-ui';

type HelpKey = keyof typeof SCREEN_COLUMN_HELP;

function Th({ column, children }: { column: HelpKey; children: React.ReactNode }) {
  const help = SCREEN_COLUMN_HELP[column];
  return <th scope="col"><span className="th-help" tabIndex={0} aria-describedby={`screen-help-${column}`}>{children}<i aria-hidden="true">?</i>
    <span role="tooltip" id={`screen-help-${column}`} className="tooltip"><strong>{help.title}</strong>{help.body}</span></span></th>;
}

const OBJECTIVES: { value: RubricObjective; label: string; note: string }[] = [
  { value: 'balanced', label: 'Balanced', note: 'Potency 45 · drug-likeness 20 · selectivity 25 · clinical 10' },
  { value: 'novel_candidates', label: 'Novel candidates', note: 'Clinical stage shown but unweighted; approved drugs are not preferred' },
  { value: 'repurposing', label: 'Repurposing', note: 'Clinical stage weighted 30; other-indication development counts half' },
];

function Shift({ c }: { c: Compound }) {
  const s = rankShift(c);
  if (s === null || s === 0) return <small className="muted">=</small>;
  return <small className="mono" title={`Baseline rank ${c.baseline_rank}`}>{s > 0 ? `↑${s}` : `↓${-s}`}</small>;
}

function Factor({ value }: { value: number | null }) {
  if (value === null) return <small className="muted">not scored</small>;
  return <span className="score-value"><span>{value.toFixed(2)}</span><span className="score-track"><i style={{ width: `${Math.round(value * 100)}%` }} /></span></span>;
}

function Detail({ c }: { c: Compound }) {
  const p = c.potency, s = c.selectivity, k = c.clinical;
  return <tr className="screen-detail"><td colSpan={9}>
    <div className="report-grid">
      <div><h3>Potency context</h3>{p ? <><p>{p.aggregate_method || 'No aggregate.'}</p>
        <p className="mono">{Object.entries(p.by_type).map(([t, v]) => `${t}: median ${v.median} (n=${v.n}, ${v.assays} assays, ${v.min}–${v.max})`).join(' · ') || 'no comparable exact binding measurements'}</p>
        <p>{p.n_records} records · {p.n_assays} assays · {p.n_documents} documents · {p.n_exact} exact · {p.n_censored} censored · {p.n_functional} functional</p>
        {p.flags.map(f => <p key={f} className="muted">{f}</p>)}
        {p.records.length > 0 && <details className="technical"><summary>{p.records.length} strongest records (identifiers preserved){p.records_omitted ? `, ${p.records_omitted} more omitted` : ''}</summary>
          <div className="table-scroll"><table><thead><tr><th>activity</th><th>assay</th><th>type</th><th>rel</th><th>value</th><th>pChEMBL</th><th>assay type</th><th>document</th><th>description</th></tr></thead>
            <tbody>{p.records.map(r => <tr key={r.activity_id ?? `${r.assay_chembl_id}-${r.pchembl_value}`}><td className="mono">{r.activity_id}</td><td className="mono">{r.assay_chembl_id}</td><td>{r.standard_type}</td><td>{r.standard_relation}</td><td>{r.standard_value} {r.standard_units}</td><td>{r.pchembl_value ?? '—'}</td><td>{r.assay_type}</td><td className="mono">{r.document_chembl_id}</td><td className="cell-secondary" title={r.assay_description ?? ''}>{r.assay_description}</td></tr>)}</tbody></table></div></details>}</> : <p>Not retrieved.</p>}
        <h3>Clinical stage</h3><p>{k?.note ?? 'Unknown.'}</p>
        {k?.matched?.length ? <p className="mono">{k.matched.map(m => `${m.efo_term} (${m.efo_id ?? 'no id'}${m.max_phase_for_ind !== null ? `, phase ${m.max_phase_for_ind}` : ''})`).join('; ')}</p> : null}
      </div>
      <div><h3>Observed selectivity</h3>{s ? <><p>{s.note}</p><p className="muted">{s.caution}</p>
        {s.off_targets.length > 0 && <div className="table-scroll"><table><thead><tr><th>off-target</th><th>records</th><th>assays</th><th>max pChEMBL</th><th>comparable {s.comparison_type ?? ''} median</th><th>types</th></tr></thead>
          <tbody>{s.off_targets.map(t => <tr key={t.target_chembl_id}><td><a href={`https://www.ebi.ac.uk/chembl/target_report_card/${t.target_chembl_id}/`} target="_blank" rel="noreferrer">{t.name} ↗</a>{t.organism && <span className="cell-secondary">{t.organism}</span>}</td><td>{t.n}</td><td>{t.assays}</td><td>{t.max_pchembl ?? '—'}</td><td>{t.comparable ? `${t.comparable_median} (n=${t.comparable_n})` : 'not comparable'}</td><td>{t.types.join(', ')}</td></tr>)}</tbody></table>{s.off_targets_omitted ? <p className="muted">{s.off_targets_omitted} further off-targets omitted from the display.</p> : null}</div>}</> : <p>Not assessed.</p>}
        <h3>Why this position</h3><p>{c.rank_reason}</p>
        {c.factors && <p className="mono">weights used: {Object.entries(c.factors.weights_used).map(([f, w]) => `${f} ${w}`).join(' · ') || 'none'}</p>}
      </div>
    </div></td></tr>;
}

export function ScreeningTable({ screening, objective, onObjective, busy }: { screening: ScreeningResult; objective: RubricObjective; onObjective: (o: RubricObjective) => void; busy: boolean }) {
  const [view, setView] = useState<ScreenView>('rubric');
  const [open, setOpen] = useState<string | null>(null);
  const rows = orderCompounds(screening.compounds, view);
  const cov = screening.coverage;
  return <>
    {cov.partial && <div className="notice warning"><strong>Partial retrieval.</strong> {screening.notes.join(' ')}</div>}
    <div className="notice">
      <strong>Candidate prioritisation is a heuristic.</strong> {screening.rubric.caveat}
      <p>Stage 1: {cov.stage1 ? `${cov.stage1.retrieved} of ${cov.stage1.total_count} potent records, ${cov.stage1.selection_method}` : 'no ChEMBL target'}.{cov.candidate_pool && ` Pool: ${cov.candidate_pool.size} molecules (${cov.candidate_pool.method}).`}{cov.stage2 && ` Stage 2: ${cov.stage2.records} complete on-target records.`}{cov.stage3 && ` Stage 3: off-target evidence for ${cov.stage3.molecules_assessed} molecules${cov.stage3.skipped_for_budget.length ? `, ${cov.stage3.skipped_for_budget.length} skipped for time` : ''}.`}{cov.indications && ` Indications checked for ${cov.indications.molecules_checked} phased molecules.`}</p>
    </div>
    <div className="actions" style={{ justifyContent: 'flex-start', flexWrap: 'wrap', marginBottom: 16 }}>
      <label className="mode-switch">Objective <select aria-label="Prioritisation objective" value={objective} disabled={busy} onChange={e => onObjective(e.target.value as RubricObjective)}>{OBJECTIVES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select></label>
      <span>{OBJECTIVES.find(o => o.value === objective)?.note}</span>
      <label className="mode-switch">View <select aria-label="Ranking view" value={view} onChange={e => setView(e.target.value as ScreenView)}><option value="rubric">Four-factor rubric</option><option value="baseline">Potency-only baseline (max pChEMBL)</option></select></label>
    </div>
    <div className="table-scroll"><table>
      <thead><tr><Th column="rank">{view === 'rubric' ? 'Rank' : 'Baseline rank'}</Th><th>Compound</th><Th column="potency">Potency</Th><Th column="drug_likeness">Drug-likeness</Th><Th column="clinical">Clinical stage</Th><Th column="selectivity">Selectivity (observed)</Th><Th column="warnings">Warnings</Th><Th column="reason">Why</Th><th>Score</th></tr></thead>
      <tbody>{rows.map(c => { const w = warnings(c); return <>
        <tr key={c.chembl_id} className={open === c.chembl_id ? 'row-selected' : undefined}>
          <td><strong>{view === 'rubric' ? c.rank : c.baseline_rank}</strong>{view === 'rubric' ? <Shift c={c} /> : <small className="muted">rubric #{c.rank}</small>}</td>
          <td><strong>{c.name || 'Unnamed compound'}</strong><a className="cell-secondary" href={c.chembl_url} target="_blank" rel="noreferrer">{c.chembl_id} ↗</a></td>
          <td>{potencyLabel(c)}<Factor value={c.factors?.potency ?? null} /></td>
          <td>{drugLikenessLabel(c)}<Factor value={c.factors?.drug_likeness ?? null} /></td>
          <td>{clinicalLabel(c)}<Factor value={c.factors?.clinical ?? null} /></td>
          <td>{selectivityLabel(c)}<Factor value={c.factors?.selectivity ?? null} /></td>
          <td>{w.length ? <ul className="report-list" style={{ margin: 0 }}>{w.map(x => <li key={x}>{x}</li>)}</ul> : <small className="muted">none</small>}</td>
          <td><button className="text-button" onClick={() => setOpen(open === c.chembl_id ? null : c.chembl_id)}>{open === c.chembl_id ? 'Hide detail' : 'Explain'}</button></td>
          <td className="mono">{c.priority_score === null ? 'n/a' : c.priority_score.toFixed(3)}</td>
        </tr>
        {open === c.chembl_id && <Detail key={`${c.chembl_id}-detail`} c={c} />}
      </>; })}</tbody>
    </table></div>
    <p className="table-note">Scores are factor values on 0–1 scales under the documented rubric. A missing factor is excluded from a candidate&apos;s composite and listed under Warnings, never counted as zero. Nothing on this page predicts efficacy or clinical success.</p>
  </>;
}
