"use client";

import type { Compound } from "@/lib/types";

const n = (x: number | null, d = 1) => (x === null ? "–" : x.toFixed(d));

export default function CompoundTable({
  compounds,
  selected,
  onToggle,
}: {
  compounds: Compound[];
  selected: Set<string>;
  onToggle: (id: string) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-xs uppercase text-zinc-500">
          <tr>
            {["", "#", "ChEMBL", "name", "pChEMBL", "assay", "phase", "MW", "ALogP", "Ro5 viol.", "Lipinski"].map((h, i) => (
              <th key={i} className="px-2 py-1">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {compounds.map((c, i) => (
            <tr key={c.chembl_id} className="border-t border-zinc-200 dark:border-zinc-800">
              <td className="px-2 py-1"><input type="checkbox" checked={selected.has(c.chembl_id)} onChange={() => onToggle(c.chembl_id)} /></td>
              <td className="px-2 py-1">{i + 1}</td>
              <td className="px-2 py-1 font-mono"><a className="text-blue-600 hover:underline" href={c.chembl_url} target="_blank" rel="noreferrer">{c.chembl_id}</a></td>
              <td className="max-w-48 truncate px-2 py-1" title={c.name ?? ""}>{c.name ?? ""}</td>
              <td className="px-2 py-1 font-mono font-semibold">{c.best_pchembl.toFixed(2)}</td>
              <td className="px-2 py-1">{c.assay_type ?? "–"}</td>
              <td className="px-2 py-1">
                {c.max_phase ?? "–"}
                {c.is_approved && <span className="ml-1 rounded bg-emerald-100 px-1 text-xs text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100">approved</span>}
              </td>
              <td className="px-2 py-1 font-mono">{n(c.mw)}</td>
              <td className="px-2 py-1 font-mono">{n(c.alogp, 2)}</td>
              <td className="px-2 py-1 font-mono">{c.ro5_violations ?? "–"}</td>
              <td className="px-2 py-1">{c.lipinski_pass === null ? "–" : c.lipinski_pass ? "pass" : "fail"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
