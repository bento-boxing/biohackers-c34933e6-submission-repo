import { describe, expect, it } from 'vitest';
import type { Investigation } from './contracts';
import { buildEvidenceGraph, evidenceSourceAnchor } from './evidence-graph';

const investigation = {
  target: { target_symbol: 'MARKER1', disease_name: 'Example disease' },
  resolved_target_id: 'ENSG00000000001',
  publications: [
    { identifier: 'PMID:1', title: 'Target biology', abstract: '', relevance: '', scope_reason: 'Disease-specific primary biological candidate; association/perturbation does not prove therapeutic validity.', url: 'https://example.test/1', evidence_scope: 'direct_biological' },
    { identifier: 'PMID:2', title: 'Background only', abstract: '', relevance: '', scope_reason: 'No visible target or curated compound relationship.', url: 'https://example.test/2', evidence_scope: 'unrelated' },
  ],
  compounds: [{ chembl_id: 'CHEMBL1', name: 'Compound A', mechanisms: [], url: 'https://example.test/CHEMBL1' }],
  trials: [
    { nct_id: 'NCT00000001', title: 'Verified matched trial', status: '', why_stopped: '', url: 'https://example.test/NCT00000001', relationship: 'verified', disease_match: 'matched', compound_ids: ['CHEMBL1'], compound_matches: {}, stop_reason: { state: 'absent', full_record_checked: true, source_url: '', detail: '' } },
    { nct_id: 'NCT00000002', title: 'Unmatched compound', status: '', why_stopped: '', url: 'https://example.test/NCT00000002', relationship: 'verified', disease_match: 'matched', compound_ids: ['CHEMBL2'], compound_matches: {}, stop_reason: { state: 'absent', full_record_checked: true, source_url: '', detail: '' } },
    { nct_id: 'NCT00000003', title: 'Uncertain disease', status: '', why_stopped: '', url: 'https://example.test/NCT00000003', relationship: 'verified', disease_match: 'uncertain', compound_ids: ['CHEMBL1'], compound_matches: {}, stop_reason: { state: 'absent', full_record_checked: true, source_url: '', detail: '' } },
  ],
} satisfies Pick<Investigation, 'target' | 'resolved_target_id' | 'publications' | 'compounds' | 'trials'>;

describe('evidence graph', () => {
  it('groups publications by their assessed target relationship', () => {
    const groups = buildEvidenceGraph(investigation);
    expect(groups.find(group => group.id === 'publication-direct_biological')?.relation).toBe('direct');
    expect(groups.find(group => group.id === 'publication-unrelated')?.relation).toBe('unresolved');
  });

  it('shows trials as mediated only when target compound and disease links are both verified', () => {
    const groups = buildEvidenceGraph(investigation);
    expect(groups.find(group => group.id === 'verified-trials')?.items.map(item => item.id)).toEqual(['NCT00000001']);
    expect(groups.find(group => group.id === 'candidate-trials')?.items.map(item => item.id)).toEqual(['NCT00000002', 'NCT00000003']);
  });

  it('keeps source descriptions available for the selected detail panel', () => {
    const groups = buildEvidenceGraph(investigation);
    expect(groups.find(group => group.id === 'publication-direct_biological')?.items[0].description).toBe(
      'Disease-specific primary biological candidate; association/perturbation does not prove therapeutic validity.',
    );
    expect(groups.find(group => group.id === 'verified-trials')?.items[0].description).toContain('Disease match: matched');
  });

  it('creates stable in-page evidence anchors', () => {
    expect(evidenceSourceAnchor('PMID:123')).toBe('evidence-source-PMID-123');
  });
});
