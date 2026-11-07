"use client";

import { useMemo, useState } from "react";
import ApprovalForm from "./components/ApprovalForm";
import TargetTable from "./components/TargetTable";
import WeightSliders from "./components/WeightSliders";
import { postRationale, postScout } from "@/lib/api";
import { DEFAULT_WEIGHTS, rankTargets } from "@/lib/score";
import type { Rationale, ScoutRun, Weights } from "@/lib/types";

export default function ScoutPage() {
  const [disease, setDisease] = useState("Parkinson disease");
  const [n, setN] = useState(25);
  const [weights, setWeights] = useState<Weights>({ ...DEFAULT_WEIGHTS });
  const [run, setRun] = useState<ScoutRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [rationales, setRationales] = useState<Record<string, Rationale>>({});
  const [rationaleWeights, setRationaleWeights] = useState<Weights | null>(null);
  const [rationaleStale, setRationaleStale] = useState(false);
  const [rationaleNote, setRationaleNote] = useState<string | null>(null);

  const ranked = useMemo(() => (run ? rankTargets(run.targets, weights) : []), [run, weights]);

  async function runScout(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setRationales({});
    setRationaleWeights(null);
    setRationaleStale(false);
    try {
      setRun(await postScout(disease, n));
    } catch (err) {
      setRun(null);
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function changeWeights(w: Weights) {
    setWeights(w);
    if (rationaleWeights) setRationaleStale(true);
  }

  async function explain() {
    if (!run) return;
    setBusy(true);
    setRationaleNote(null);
    try {
      const res = await postRationale(run.run_id, weights);
      if ("available" in res && res.available === false) {
        setRationaleNote(`LLM rationale off: ${res.reason}`);
        return;
      }
      if ("rationales" in res) {
        setRationales(Object.fromEntries(res.rationales.map((r) => [r.symbol, r])));
        setRationaleWeights(res.weights);
        setRationaleStale(false);
      }
    } catch (err) {
      setRationaleNote((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4 p-6 lg:flex-row">
      <div className="lg:w-72 lg:shrink-0">
        <form onSubmit={runScout} className="mb-4 flex flex-col gap-2">
          <label className="text-sm">
            Disease
            <input value={disease} onChange={(e) => setDisease(e.target.value)} className="mt-1 w-full rounded border border-zinc-300 bg-transparent p-2 dark:border-zinc-700" />
          </label>
          <label className="text-sm">
            Targets (5–50)
            <input type="number" min={5} max={50} value={n} onChange={(e) => setN(Number(e.target.value))} className="mt-1 w-full rounded border border-zinc-300 bg-transparent p-2 dark:border-zinc-700" />
          </label>
          <button type="submit" disabled={busy} className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50">
            {busy ? "Working…" : "Run Target Scout"}
          </button>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </form>
        <WeightSliders weights={weights} onChange={changeWeights} />
      </div>
      <main className="min-w-0 flex-1">
        {run ? (
          <>
            <p className="mb-2 text-sm text-zinc-600 dark:text-zinc-400">
              Resolved <b>{run.disease.name}</b> ({run.disease.id}) · {run.targets.length} targets
              {run.cache_only && <span className="ml-2 rounded bg-zinc-200 px-1 text-xs dark:bg-zinc-800">cache-only</span>}
              <button type="button" onClick={explain} disabled={busy} className="ml-3 rounded border border-zinc-300 px-2 py-0.5 text-xs dark:border-zinc-700">
                Explain ranking (LLM)
              </button>
              {rationaleNote && <span className="ml-2 text-xs text-amber-700">{rationaleNote}</span>}
            </p>
            <TargetTable targets={ranked} rationales={rationales} rationaleWeights={rationaleWeights} rationaleStale={rationaleStale} />
            <ApprovalForm runId={run.run_id} targets={ranked} weights={weights} />
          </>
        ) : (
          <p className="text-zinc-500">Enter a disease and run the scout. Every score is a weighted sum of four components you can see and adjust.</p>
        )}
      </main>
    </div>
  );
}
