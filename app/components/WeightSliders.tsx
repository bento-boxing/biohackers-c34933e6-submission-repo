"use client";

import { DEFAULT_WEIGHTS, WEIGHT_KEYS, normaliseWeights } from "@/lib/score";
import type { Weights } from "@/lib/types";

const LABELS: Record<(typeof WEIGHT_KEYS)[number], string> = {
  genetic: "Genetic evidence",
  association: "Overall association",
  druggability: "Druggability",
  literature: "Literature",
};

export default function WeightSliders({
  weights,
  onChange,
}: {
  weights: Weights;
  onChange: (w: Weights) => void;
}) {
  const norm = normaliseWeights(weights);
  return (
    <aside className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-semibold">Score weights</h2>
        <button
          type="button"
          className="text-sm text-blue-600 hover:underline"
          onClick={() => onChange({ ...DEFAULT_WEIGHTS })}
        >
          Reset
        </button>
      </div>
      {WEIGHT_KEYS.map((k) => (
        <label key={k} className="mb-3 block text-sm">
          <span className="flex justify-between">
            <span>{LABELS[k]}</span>
            <span className="font-mono text-zinc-500">
              {weights[k].toFixed(2)} → {norm[k].toFixed(2)}
            </span>
          </span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={weights[k]}
            onChange={(e) => onChange({ ...weights, [k]: Number(e.target.value) })}
            className="w-full"
          />
        </label>
      ))}
      <p className="text-xs text-zinc-500">
        total = Σ weight × component. Weights are normalised to sum to 1.
      </p>
    </aside>
  );
}
