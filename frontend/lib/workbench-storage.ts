import type { Decision, Job, Mode, ScoutRun, Weights } from './contracts';
import { DEFAULT_WEIGHTS } from './contracts';

export const STORAGE_KEY = 'agentverse-workbench-v2';

export type SavedState = { mode: Mode; run: ScoutRun | null; target_id: string | null; weights: Weights; job: Job | null };

type Reader = Pick<Storage, 'getItem'>;
type Writer = Pick<Storage, 'setItem'>;

/** Restore the last session. Drops anything that no longer fits together; never throws. */
export function loadState(storage: Reader): SavedState | null {
  let raw: unknown;
  try { raw = JSON.parse(storage.getItem(STORAGE_KEY) || 'null'); } catch { return null; }
  if (!raw || typeof raw !== 'object') return null;
  const saved = raw as Partial<SavedState>;
  if (saved.mode !== 'live' && saved.mode !== 'offline') return null;
  const mode = saved.mode;
  const weights = saved.weights && typeof saved.weights === 'object' ? saved.weights : DEFAULT_WEIGHTS;
  let run = saved.run && typeof saved.run === 'object' && Array.isArray(saved.run.targets) ? saved.run : null;
  if (run && run.cache_only !== (mode === 'offline')) run = null;
  const target = run && saved.target_id ? run.targets.find(t => t.target_id === saved.target_id) : undefined;
  const target_id = target ? target.target_id : null;
  let job = saved.job && typeof saved.job === 'object' && saved.job.result !== undefined ? saved.job : null;
  if (job && job.mode !== mode) job = null;
  if (job && saved.target_id && !target) job = null; // target vanished: its report must go too
  if (job && target && job.selection?.target_input?.target_id !== target.target_id) job = null;
  return { mode, run, target_id, weights, job };
}

export function saveState(storage: Writer, state: SavedState): void {
  try { storage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch { /* quota or private mode: state stays in memory */ }
}

export function withDecision(job: Job, decision: Decision): Job {
  const decisions = job.decisions.filter(d => d.decision_id !== decision.decision_id).concat(decision);
  return { ...job, decisions };
}
