import { describe, expect, it } from 'vitest';
import type { Investigation } from './contracts';
import { associationSourceUrl, associationStrengthLabel, associationVisualNodes } from './association-visual';

const association: NonNullable<Investigation['association']> = {
  strength: 'clinical_context',
  explanation: 'Clinical publications were retrieved; target engagement remains uncertain.',
  direct_source_ids: ['MED:1'],
  indirect_source_ids: ['MED:2'],
  unrelated_source_ids: ['MED:3'],
  independent_groups: 1,
  evidence_types: ['cellular_mechanistic'],
  limitations: ['Source triage is not causal verification.'],
  ontology_association: { state: 'found', score: 0.72 },
};

describe('association visual', () => {
  it('labels clinical context without implying efficacy', () => {
    expect(associationStrengthLabel(association.strength)).toBe('Clinical context retrieved');
  });

  it('builds selectable evidence and limitation nodes from report values', () => {
    const nodes = associationVisualNodes(association);
    expect(nodes.find(node => node.id === 'direct')?.sourceIds).toEqual(['MED:1']);
    expect(nodes.find(node => node.id === 'groups')?.count).toBe(1);
    expect(nodes.find(node => node.id === 'limitations')?.count).toBe(1);
  });

  it('does not present an unknown strength as a positive finding', () => {
    expect(associationStrengthLabel('unexpected')).toBe('Association not classified');
  });

  it('links direct PubMed records to PubMed while preserving other source links', () => {
    const europePmcUrl = 'https://europepmc.org/article/MED/12345678';
    expect(associationSourceUrl('MED:12345678', europePmcUrl, true))
      .toBe('https://pubmed.ncbi.nlm.nih.gov/12345678/');
    expect(associationSourceUrl('MED:12345678', europePmcUrl, false)).toBe(europePmcUrl);
    expect(associationSourceUrl('PMC:PMC1234567', europePmcUrl, true)).toBe(europePmcUrl);
  });
});
