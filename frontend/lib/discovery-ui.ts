// Pure helpers for the discovery table and disease search; no React so they stay unit-testable.

export type ColumnKey = 'rank' | 'target' | 'score' | 'genetic' | 'association' | 'druggability' | 'literature' | 'safety';

export const COLUMN_HELP: Record<ColumnKey, { title: string; body: string }> = {
  rank: { title: 'Rank', body: 'Position after sorting by the ranking score with your current weights. Changing a weight slider re-sorts the table immediately; no new data is fetched.' },
  target: { title: 'Protein target', body: 'Gene symbol and approved protein name from Open Targets. Selecting a row hands the target, its scores and evidence to the Devil’s Advocate investigation.' },
  score: { title: 'Ranking score', body: 'Weighted total between 0 and 1: Σ (normalised weight × component score) over genetics, association, druggability and literature. A higher score means stronger retrieved evidence, not a higher chance of clinical success.' },
  genetic: { title: 'Genetics', body: 'Open Targets genetic-association score (GWAS, rare-variant and gene-burden evidence linking the gene to this disease), 0 to 1. Multiplied by the genetics weight in the total; a higher weight favours targets with human genetic support.' },
  association: { title: 'Association', body: 'Overall Open Targets disease–target association score across all evidence types (genetics, literature, animal models, pathways, drugs), 0 to 1. Multiplied by the association weight, so it broadly rewards well-studied targets.' },
  druggability: { title: 'Druggability', body: 'Half small-molecule tractability (1.0 approved or clinical drugs, 0.7 ligand or structure known, 0.4 druggable pocket or family) plus half the log-scaled count of potent ChEMBL compounds. Multiplied by the druggability weight; raise it to favour targets a chemist can already reach.' },
  literature: { title: 'Literature', body: 'Log-scaled Europe PMC publication count for the gene with this disease, normalised to the most-cited target in the list. Multiplied by the literature weight; a high weight favours established targets over novel ones.' },
  safety: { title: 'Safety flags', body: 'Known safety liabilities and high baseline expression in heart, liver or kidney from Open Targets. Shown for review only: flags are deliberately not folded into the ranking score and never lower a target’s rank. “None retrieved” does not establish safety.' },
};

/** Next highlighted suggestion index for an ArrowUp/ArrowDown key; -1 means nothing highlighted. */
export function stepHighlight(current: number, key: string, count: number): number {
  if (count <= 0) return -1;
  if (key === 'ArrowDown') return (current + 1) % count;
  if (key === 'ArrowUp') return current <= 0 ? count - 1 : current - 1;
  return current;
}
