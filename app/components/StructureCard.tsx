import type { Structure } from "@/lib/types";

export default function StructureCard({ structure, symbol }: { structure: Structure | null; symbol: string }) {
  if (!structure) {
    return <div className="rounded-lg border border-zinc-200 p-4 text-sm text-zinc-500 dark:border-zinc-800">No AlphaFold structure found for {symbol}.</div>;
  }
  const s = structure;
  return (
    <div className="rounded-lg border border-zinc-200 p-4 text-sm dark:border-zinc-800">
      <h2 className="mb-1 font-semibold">Predicted structure · {s.model_id}</h2>
      <p>
        Mean pLDDT <b>{s.mean_plddt.toFixed(1)}</b> · confident residues <b>{Math.round(s.fraction_confident * 100)}%</b>
      </p>
      <p className="mt-1 flex gap-3">
        <a className="text-blue-600 hover:underline" href={`https://alphafold.ebi.ac.uk/entry/${s.uniprot}`} target="_blank" rel="noreferrer">AlphaFold entry</a>
        <a className="text-blue-600 hover:underline" href={s.pdb_url} target="_blank" rel="noreferrer">PDB</a>
        <a className="text-blue-600 hover:underline" href={s.cif_url} target="_blank" rel="noreferrer">mmCIF</a>
      </p>
    </div>
  );
}
