"use client";

import { Fragment, useState } from "react";
import type { RankedTarget } from "@/lib/score";
import type { Rationale, Weights } from "@/lib/types";

const f = (x: number) => x.toFixed(2);

export default function TargetTable({
  targets,
  rationales,
  rationaleWeights,
  rationaleStale,
}: {
  targets: RankedTarget[];
  rationales: Record<string, Rationale>;
  rationaleWeights: Weights | null;
  rationaleStale: boolean;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const rw = rationaleWeights;
  const rationaleHeader = rw
    ? `rationale (weights g/a/d/l = ${f(rw.genetic)}/${f(rw.association)}/${f(rw.druggability)}/${f(rw.literature)})`
    : "rationale";
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-xs uppercase text-zinc-500">
          <tr>
            {["#", "symbol", "name", "total", "gen", "assoc", "drug", "lit", "potent", "approved", "papers", "safety", rationaleHeader, ""].map((h) => (
              <th key={h} className="px-2 py-1">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {targets.map((t) => {
            const r = rationales[t.symbol];
            return (
              <Fragment key={t.symbol}>
                <tr className="border-t border-zinc-200 dark:border-zinc-800">
                  <td className="px-2 py-1">{t.rank}</td>
                  <td className="px-2 py-1 font-semibold">
                    <a href={t.open_targets_url} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline">{t.symbol}</a>
                  </td>
                  <td className="max-w-48 truncate px-2 py-1" title={t.name}>{t.name}</td>
                  <td className="px-2 py-1 font-mono font-semibold">{t.total.toFixed(3)}</td>
                  <td className="px-2 py-1 font-mono">{f(t.components.genetic)}</td>
                  <td className="px-2 py-1 font-mono">{f(t.components.association)}</td>
                  <td className="px-2 py-1 font-mono">{f(t.components.druggability)}</td>
                  <td className="px-2 py-1 font-mono">{f(t.components.literature)}</td>
                  <td className="px-2 py-1 font-mono">{t.potent_count}</td>
                  <td className="px-2 py-1">{t.has_approved_drug ? "yes" : ""}</td>
                  <td className="px-2 py-1">
                    {t.literature_hits}{" "}
                    {t.pmids.map((p) => (
                      <a key={p} href={`https://pubmed.ncbi.nlm.nih.gov/${p}/`} target="_blank" rel="noreferrer" className="ml-1 text-blue-600 hover:underline">[{p}]</a>
                    ))}
                  </td>
                  <td className="px-2 py-1">
                    {t.safety_flags.length > 0 && (
                      <span className="rounded bg-amber-100 px-1 text-amber-900 dark:bg-amber-900 dark:text-amber-100" title={t.safety_flags.map((s) => s.detail).join("; ")}>
                        {t.safety_flags.length} flag{t.safety_flags.length > 1 ? "s" : ""}
                      </span>
                    )}
                  </td>
                  <td className="max-w-md px-2 py-1 text-xs">
                    {rationaleStale || !r ? (
                      <span className="text-zinc-400">{rationaleStale ? "weights changed, re-run explain" : ""}</span>
                    ) : (
                      <span><b>{r.evidence_strength}</b>: {r.rationale}</span>
                    )}
                  </td>
                  <td className="px-2 py-1">
                    <button type="button" className="text-xs text-blue-600 hover:underline" onClick={() => setOpen(open === t.symbol ? null : t.symbol)}>
                      {open === t.symbol ? "less" : "more"}
                    </button>
                  </td>
                </tr>
                {open === t.symbol && (
                  <tr className="bg-zinc-50 text-xs dark:bg-zinc-900">
                    <td colSpan={14} className="px-4 py-2">
                      <p><b>UniProt:</b> {t.uniprot ?? "none"} · <b>ChEMBL target:</b> {t.chembl_target_id ?? "none"}</p>
                      <p><b>SM tractability:</b> {t.tractability_sm_labels.join(", ") || "none"}</p>
                      <p><b>Safety:</b> {t.safety_flags.map((s) => `${s.kind}: ${s.detail}`).join("; ") || "no flags"}</p>
                      <p><b>PMIDs:</b> {t.pmids.join(", ") || "none"}</p>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
