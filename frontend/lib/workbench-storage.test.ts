import { describe, expect, it } from 'vitest';
import { STORAGE_KEY, loadState, saveState, withDecision, type SavedState } from './workbench-storage';
import type { Decision, Job, ScoutRun } from './contracts';

function memory() {
  const m = new Map<string, string>();
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => { m.set(k, v); }, map: m };
}
const run: ScoutRun = { run_id: 'r1', disease: { id: 'MONDO_1', name: 'X' }, cache_only: true, default_weights: { genetic: 0.4, association: 0.3, druggability: 0.2, literature: 0.1 },
  targets: [{ target_id: 'ENSG1', symbol: 'A', name: 'A', uniprot: null, chembl_target_id: null, components: { genetic: 0, association: 0, druggability: 0, literature: 0 }, potent_count: 0, has_approved_drug: false, literature_hits: 0, pmids: [], safety_flags: [], tractability_sm_labels: [], open_targets_url: '' }] };
const job = { job_id: 'j'.repeat(32), state: 'completed', progress: { stage: 's', calls: [] }, result: null, error: null, mode: 'offline', selection: { target_input: { disease_name: 'X', target_symbol: 'A', target_id: 'ENSG1' }, cache_only: true }, weights: run.default_weights, decisions: [] } as unknown as Job;
const base: SavedState = { mode: 'offline', run, target_id: 'ENSG1', weights: run.default_weights, job };

describe('workbench storage', () => {
  it('round-trips the full state', () => {
    const s = memory(); saveState(s, base);
    expect(JSON.parse(s.map.get(STORAGE_KEY)!).run.run_id).toBe('r1');
    expect(loadState(s)).toEqual(base);
  });
  it('returns null on missing or corrupt data', () => {
    expect(loadState(memory())).toBeNull();
    const s = memory(); s.setItem(STORAGE_KEY, '{not json'); expect(loadState(s)).toBeNull();
    const t = memory(); t.setItem(STORAGE_KEY, JSON.stringify({ mode: 'weird' })); expect(loadState(t)).toBeNull();
  });
  it('restores run but drops a target that is no longer in it', () => {
    const s = memory(); saveState(s, { ...base, target_id: 'ENSG_GONE' });
    const restored = loadState(s)!;
    expect(restored.run?.run_id).toBe('r1'); expect(restored.target_id).toBeNull(); expect(restored.job).toBeNull();
  });
  it('drops a run whose cache_only disagrees with the mode', () => {
    const s = memory(); saveState(s, { ...base, mode: 'live' });
    const restored = loadState(s)!;
    expect(restored.mode).toBe('live'); expect(restored.run).toBeNull(); expect(restored.target_id).toBeNull(); expect(restored.job).toBeNull();
  });
  it('withDecision appends and replaces by decision_id', () => {
    const d1 = { decision_id: 'd1', job_id: job.job_id, action: 'investigate', rationale: 'r', confirmed: false, mode: 'offline' } as Decision;
    const once = withDecision(job, d1);
    const twice = withDecision(once, { ...d1, rationale: 'updated' });
    expect(twice.decisions).toHaveLength(1); expect(twice.decisions[0].rationale).toBe('updated');
    expect(withDecision(twice, { ...d1, decision_id: 'd2' }).decisions).toHaveLength(2);
    expect(job.decisions).toHaveLength(0); // input not mutated
  });
});
