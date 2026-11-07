"use client";

import { useState } from "react";
import { postShortlist } from "@/lib/api";

export default function ShortlistForm({ approvalTs, selected }: { approvalTs: string; selected: string[] }) {
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await postShortlist({ approval_ts: approvalTs, chembl_ids: selected, reason });
      setMsg({ ok: true, text: `Shortlisted ${selected.length} compound${selected.length === 1 ? "" : "s"}.` });
      setReason("");
    } catch (err) {
      setMsg({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-4 rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
      <h2 className="mb-2 font-semibold">Human checkpoint · shortlist ({selected.length} selected)</h2>
      <div className="flex flex-col gap-2 sm:flex-row">
        <textarea required value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why these compounds?" className="min-h-16 flex-1 rounded border border-zinc-300 bg-transparent p-2 dark:border-zinc-700" />
        <button type="submit" disabled={busy || selected.length === 0 || !reason.trim()} className="rounded bg-emerald-600 px-4 py-2 text-white disabled:opacity-50">Shortlist</button>
      </div>
      {msg && <p className={`mt-2 text-sm ${msg.ok ? "text-emerald-700" : "text-red-600"}`}>{msg.text}</p>}
    </form>
  );
}
