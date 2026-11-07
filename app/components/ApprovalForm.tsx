"use client";

import { useState } from "react";
import { postApproval } from "@/lib/api";
import type { RankedTarget } from "@/lib/score";
import type { Weights } from "@/lib/types";

const r4 = (x: number) => Math.round(x * 1e4) / 1e4;

export default function ApprovalForm({
  runId,
  targets,
  weights,
}: {
  runId: string;
  targets: RankedTarget[];
  weights: Weights;
}) {
  const [symbol, setSymbol] = useState(targets[0]?.symbol ?? "");
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const t = targets.find((x) => x.symbol === symbol);
    if (!t) return;
    setBusy(true);
    setMsg(null);
    try {
      const a = await postApproval({
        run_id: runId,
        symbol,
        weights,
        scores: {
          genetic: r4(t.components.genetic),
          association: r4(t.components.association),
          druggability: r4(t.components.druggability),
          literature: r4(t.components.literature),
          total: r4(t.total),
        },
        reason,
      });
      setMsg({ ok: true, text: `Approved ${a.symbol} and sent to protein screening (${a.ts}).` });
      setReason("");
    } catch (err) {
      setMsg({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-6 rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
      <h2 className="mb-2 font-semibold">Human checkpoint</h2>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
        <select value={symbol} onChange={(e) => setSymbol(e.target.value)} className="rounded border border-zinc-300 bg-transparent p-2 dark:border-zinc-700">
          {targets.map((t) => (
            <option key={t.symbol} value={t.symbol}>#{t.rank} {t.symbol} ({t.total.toFixed(3)})</option>
          ))}
        </select>
        <textarea
          required
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Why this target? (recorded in the audit log)"
          className="min-h-16 flex-1 rounded border border-zinc-300 bg-transparent p-2 dark:border-zinc-700"
        />
        <button type="submit" disabled={busy || !reason.trim()} className="rounded bg-emerald-600 px-4 py-2 text-white disabled:opacity-50">
          Approve and send to protein screening
        </button>
      </div>
      {msg && <p className={`mt-2 text-sm ${msg.ok ? "text-emerald-700" : "text-red-600"}`}>{msg.text}</p>}
    </form>
  );
}
