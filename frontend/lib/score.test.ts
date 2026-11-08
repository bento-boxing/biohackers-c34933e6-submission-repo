import { describe, expect, it } from "vitest";
import { DEFAULT_WEIGHTS, normaliseWeights, rankTargets, total } from "./score";
import type { ScoutTarget } from "./scout-types";

const sum = (w: Record<string, number>) => Object.values(w).reduce((a, b) => a + b, 0);

const target = (symbol: string, genetic: number): ScoutTarget => ({
  target_id: symbol, symbol, name: symbol, uniprot: null, chembl_target_id: null,
  components: { genetic, association: 0.5, druggability: 0.5, literature: 0.5 },
  potent_count: 0, has_approved_drug: false, literature_hits: 0, pmids: [], safety_flags: [],
  tractability_sm_labels: [], open_targets_url: "",
});

describe("score", () => {
  it("normaliseWeights sums to 1", () => {
    const w = normaliseWeights({ genetic: 4, association: 3, druggability: 2, literature: 1 });
    expect(sum(w)).toBeCloseTo(1, 9);
    expect(w.genetic).toBeCloseTo(0.4, 9);
  });

  it("all-zero weights fall back to defaults", () => {
    expect(normaliseWeights({ genetic: 0, association: 0, druggability: 0, literature: 0 })).toEqual(DEFAULT_WEIGHTS);
  });

  it("total matches Python example (0.5,0.8,0.6,0.5 → 0.61)", () => {
    expect(total({ genetic: 0.5, association: 0.8, druggability: 0.6, literature: 0.5 }, DEFAULT_WEIGHTS)).toBeCloseTo(0.61, 6);
  });

  it("rankTargets sorts desc and numbers ranks", () => {
    const ranked = rankTargets([target("A", 0.1), target("B", 0.9), target("C", 0.5)], DEFAULT_WEIGHTS);
    expect(ranked.map((t) => t.symbol)).toEqual(["B", "C", "A"]);
    expect(ranked.map((t) => t.rank)).toEqual([1, 2, 3]);
    expect(ranked[0].total).toBeGreaterThan(ranked[2].total);
  });
});
