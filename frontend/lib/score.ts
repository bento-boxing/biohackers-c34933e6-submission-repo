import type { Components, ScoutTarget, Weights } from "./scout-types";

export const DEFAULT_WEIGHTS: Weights = {
  genetic: 0.4,
  association: 0.3,
  druggability: 0.2,
  literature: 0.1,
};

export const WEIGHT_KEYS = ["genetic", "association", "druggability", "literature"] as const;

export function normaliseWeights(w: Weights): Weights {
  const sum = WEIGHT_KEYS.reduce((acc, k) => acc + (w[k] ?? 0), 0);
  if (sum <= 0) return { ...DEFAULT_WEIGHTS };
  return {
    genetic: w.genetic / sum,
    association: w.association / sum,
    druggability: w.druggability / sum,
    literature: w.literature / sum,
  };
}

export function total(c: Components, w: Weights): number {
  const n = normaliseWeights(w);
  return WEIGHT_KEYS.reduce((acc, k) => acc + n[k] * c[k], 0);
}

export type RankedTarget = ScoutTarget & { total: number; rank: number };

export function rankTargets(targets: ScoutTarget[], w: Weights): RankedTarget[] {
  return targets
    .map((t) => ({ ...t, total: total(t.components, w), rank: 0 }))
    .sort((a, b) => b.total - a.total)
    .map((t, i) => ({ ...t, rank: i + 1 }));
}
