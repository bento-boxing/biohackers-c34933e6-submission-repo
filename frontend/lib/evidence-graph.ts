import type { Investigation } from './contracts';

export type EvidenceGraphItem = { id: string; title: string; url: string; description: string };
export type EvidenceGraphGroup = {
  id: string;
  label: string;
  linkLabel: string;
  relation: 'direct' | 'context' | 'mediated' | 'unresolved';
  items: EvidenceGraphItem[];
  side?: 'left' | 'right';
};

const publicationScopes: Record<string, Omit<EvidenceGraphGroup, 'id' | 'items'>> = {
  direct_biological: {
    label: 'Disease-specific biology',
    linkLabel: 'Direct biological candidate; causality is not established',
    relation: 'direct',
  },
  direct_clinical: {
    label: 'Disease-specific clinical context',
    linkLabel: 'Disease-matched publication via target/compound context; engagement is unresolved',
    relation: 'context',
  },
  indirect_mechanistic: {
    label: 'Indirect mechanistic context',
    linkLabel: 'Context only; not a direct target link',
    relation: 'context',
  },
  target_pharmacology: {
    label: 'Target pharmacology',
    linkLabel: 'Target-related, but not disease-specific',
    relation: 'context',
  },
  unrelated: {
    label: 'No visible target link',
    linkLabel: 'No target or curated compound relationship identified',
    relation: 'unresolved',
  },
  unassessed: {
    label: 'Unassessed publications',
    linkLabel: 'Relationship has not been assessed',
    relation: 'unresolved',
  },
};

type EvidenceGraphInput = Pick<Investigation, 'target' | 'resolved_target_id' | 'publications' | 'compounds' | 'trials'>;

export function evidenceSourceAnchor(sourceId: string): string {
  return `evidence-source-${sourceId.replace(/[^a-zA-Z0-9_-]/g, '-')}`;
}

export function buildEvidenceGraph(investigation: EvidenceGraphInput): EvidenceGraphGroup[] {
  const grouped = new Map<string, EvidenceGraphGroup>();
  const addGroup = (group: EvidenceGraphGroup) => {
    const existing = grouped.get(group.id);
    if (existing) existing.items.push(...group.items);
    else grouped.set(group.id, group);
  };

  for (const publication of investigation.publications) {
    const scope = publicationScopes[publication.evidence_scope || 'unassessed'] || publicationScopes.unassessed;
    addGroup({
      id: `publication-${publication.evidence_scope || 'unassessed'}`,
      ...scope,
      items: [{
        id: publication.identifier,
        title: publication.title,
        url: publication.url,
        description: publication.scope_reason || publication.relevance || 'No further source-scope description is available.',
      }],
    });
  }

  const knownCompounds = new Set(investigation.compounds.map(compound => compound.chembl_id));
  if (investigation.compounds.length) {
    addGroup({
      id: 'target-compounds',
      label: 'ChEMBL target compounds',
      linkLabel: `Retrieved for ${investigation.resolved_target_id || investigation.target.target_symbol}; curated mechanisms are not measured engagement`,
      relation: 'direct',
      items: investigation.compounds.map(compound => ({
        id: compound.chembl_id,
        title: compound.name,
        url: compound.url,
        description: compound.mechanisms.join('; ') || 'No curated mechanism description was retrieved.',
      })),
    });
  }

  const linkedTrials: EvidenceGraphItem[] = [];
  const candidateTrials: EvidenceGraphItem[] = [];
  for (const trial of investigation.trials) {
    const sharesTargetCompound = trial.compound_ids.some(id => knownCompounds.has(id));
    const item = {
      id: trial.nct_id,
      title: trial.title,
      url: trial.url,
      description: `Status: ${trial.status || 'not reported'}. Disease match: ${trial.disease_match}. Compound relationship: ${trial.relationship}. Compound identifiers: ${trial.compound_ids.join(', ') || 'none resolved'}.`,
    };
    if (trial.relationship === 'verified' && trial.disease_match === 'matched' && sharesTargetCompound) {
      linkedTrials.push(item);
    } else {
      candidateTrials.push(item);
    }
  }
  if (linkedTrials.length) {
    addGroup({
      id: 'verified-trials',
      label: 'Disease-matched trials',
      linkLabel: 'Mediated by a matching target-retrieved compound; not proof of target engagement',
      relation: 'mediated',
      items: linkedTrials,
    });
  }
  if (candidateTrials.length) {
    addGroup({
      id: 'candidate-trials',
      label: 'Trial candidates',
      linkLabel: 'Compound link or disease applicability is unresolved',
      relation: 'unresolved',
      items: candidateTrials,
    });
  }

  const order = [
    'publication-direct_biological',
    'publication-direct_clinical',
    'target-compounds',
    'verified-trials',
    'publication-indirect_mechanistic',
    'publication-target_pharmacology',
    'candidate-trials',
    'publication-unrelated',
    'publication-unassessed',
  ];
  return [...grouped.values()]
    .sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id))
    .map((group, index) => ({ ...group, side: index % 2 === 0 ? 'left' : 'right' }));
}
