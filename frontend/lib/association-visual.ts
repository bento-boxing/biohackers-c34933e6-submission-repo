import type { Investigation } from './contracts';

type Association = NonNullable<Investigation['association']>;

export type AssociationVisualNode = {
  id: string;
  label: string;
  count?: number;
  description: string;
  sourceIds?: string[];
  tone: 'direct' | 'context' | 'neutral';
};

const strengthLabels: Record<string, string> = {
  clinical_context: 'Clinical context retrieved',
  exploratory: 'Exploratory biological support',
  insufficient: 'Insufficient direct support',
};

export function associationStrengthLabel(strength: string): string {
  return strengthLabels[strength] || 'Association not classified';
}

export function associationSourceUrl(identifier: string, url: string, isDirect: boolean): string {
  const pmid = identifier.match(/^MED:(\d+)$/)?.[1];
  return isDirect && pmid ? `https://pubmed.ncbi.nlm.nih.gov/${pmid}/` : url;
}

export function associationVisualNodes(association: Association): AssociationVisualNode[] {
  const ontology = association.ontology_association;
  const score = typeof ontology.score === 'number' ? ` Descriptive score: ${ontology.score.toFixed(5)}.` : '';
  return [
    {
      id: 'direct',
      label: 'Disease-specific sources',
      count: association.direct_source_ids.length,
      description: 'Sources classified as direct disease-specific biological or clinical candidates. Direct classification is a source-scope screen, not proof of causality or target engagement.',
      sourceIds: association.direct_source_ids,
      tone: 'direct',
    },
    {
      id: 'indirect',
      label: 'Indirect / pharmacology',
      count: association.indirect_source_ids.length,
      description: 'Sources with indirect mechanistic context or target pharmacology. These do not independently establish a disease-specific target relationship.',
      sourceIds: association.indirect_source_ids,
      tone: 'context',
    },
    {
      id: 'unrelated',
      label: 'Unrelated / unqualified',
      count: association.unrelated_source_ids.length,
      description: 'Retrieved sources that did not qualify as direct or indirect evidence for this disease–target pair.',
      sourceIds: association.unrelated_source_ids,
      tone: 'neutral',
    },
    {
      id: 'groups',
      label: 'Distinct primary source groups',
      count: association.independent_groups,
      description: 'Distinct groups based on publication title and DOI. They are not confirmed independent cohorts or replications.',
      tone: 'neutral',
    },
    {
      id: 'types',
      label: 'Evidence types',
      count: association.evidence_types.length,
      description: 'Evidence-type signals identified during source-scope triage. Their presence does not establish evidence quality, direction, causality, or therapeutic value.',
      tone: 'context',
    },
    {
      id: 'limitations',
      label: 'Limitations',
      count: association.limitations.length,
      description: 'Read the assessment limitations before interpreting the association or comparing it with another target.',
      tone: 'neutral',
    },
    {
      id: 'ontology',
      label: 'Open Targets provenance',
      description: `Exact disease–target lookup: ${String(ontology.state || 'not searched').replaceAll('_', ' ')}.${score} ${String(ontology.caution || 'No additional lookup caveat was returned.')}`,
      tone: 'context',
    },
  ];
}
