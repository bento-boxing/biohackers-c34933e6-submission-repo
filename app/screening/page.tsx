"use client";

import { useEffect, useState } from "react";
import CompoundTable from "../components/CompoundTable";
import ShortlistForm from "../components/ShortlistForm";
import StructureCard from "../components/StructureCard";
import { getApprovals, postScreen } from "@/lib/api";
import type { Approval, ScreeningResult } from "@/lib/types";

export default function ScreeningPage() {
  const [approvals, setApprovals] = useState<Approval[] | null>(null);
  const [ts, setTs] = useState("");
  const [result, setResult] = useState<ScreeningResult | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getApprovals()
      .then((a) => {
        setApprovals(a);
        if (a[0]) setTs(a[0].ts);
      })
      .catch((e) => setError((e as Error).message));
  }, []);

  async function run() {
    setBusy(true);
    setError(null);
    setResult(null);
    setSelected(new Set());
    try {
      setResult(await postScreen(ts));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function toggle(id: string) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <main className="mx-auto max-w-7xl p-6">
      {approvals && approvals.length === 0 && <p className="text-zinc-500">Approve a target on the Scout page first.</p>}
      {approvals && approvals.length > 0 && (
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center">
          <select value={ts} onChange={(e) => setTs(e.target.value)} className="rounded border border-zinc-300 bg-transparent p-2 dark:border-zinc-700">
            {approvals.map((a) => (
              <option key={a.ts} value={a.ts}>
                {a.symbol} for {a.disease_name} ({a.ts}) by {a.approved_by}
              </option>
            ))}
          </select>
          <button type="button" onClick={run} disabled={busy || !ts} className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50">
            {busy ? "Working…" : "Run screening"}
          </button>
        </div>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
      {result && (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            <b>{result.approval.symbol}</b> approved by {result.approval.approved_by}: “{result.approval.reason}”
          </p>
          <StructureCard structure={result.structure} symbol={result.approval.symbol} />
          {result.compounds.length === 0 ? (
            <p className="text-zinc-500">No ChEMBL target mapped for this protein, so there are no known potent compounds to rank.</p>
          ) : (
            <>
              <CompoundTable compounds={result.compounds} selected={selected} onToggle={toggle} />
              <ShortlistForm approvalTs={result.approval.ts} selected={[...selected]} />
            </>
          )}
        </div>
      )}
    </main>
  );
}
