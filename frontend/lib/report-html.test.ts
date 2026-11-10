import { describe, expect, it } from 'vitest';
import { reportHtml } from './report-html';
import type { Report } from './contracts';

const report = {
  mode: 'live', recorded_ai: false, weights: {}, selection: { target_input: { disease_name: 'HIV infectious disease', target_symbol: 'CCR5' }, cache_only: false },
  provenance: { source_hash: 'abc', pipeline_version: '1.0', retrieved_at: 1762600000, source_mode: 'live_public_api', cache_hits: 3, code_matches_disk: true },
  experiment: { question: 'Which factors limit benefit <from> CCR5 modulation?', competing_explanations: ['H1', 'H2'], model: 'm', measurement: 'x', controls: ['c'], possible_results: ['r'],
    limitations: ['Review flag: Claude reasoning was not run', 'Cell models differ'], decision_impact: 'd', evidence_ids: [], status: 'Rule-based template proposal' },
  investigation: { target: { disease_name: 'HIV infectious disease', target_symbol: 'CCR5', target_id: 'ENSG00000160791' }, mode: 'live', resolved_target_id: 'CHEMBL274', resolution_status: 'resolved',
    compounds: [{ chembl_id: 'CHEMBL1201187', name: 'MARAVIROC', mechanisms: ['CCR5 antagonist'], url: 'https://ebi.ac.uk/x', max_phase: 4 }],
    trials: [{ nct_id: 'NCT00123890', title: 'A trial', status: 'TERMINATED', why_stopped: 'hepatoxicity', relationship: 'verified', compound_ids: [], compound_matches: {}, disease_match: 'matched', url: 'https://clinicaltrials.gov/study/NCT00123890', stop_reason: { state: 'reported', value: 'hepatoxicity', full_record_checked: true, source_url: '', detail: '' } }],
    publications: [{ identifier: 'MED:1', title: 'Paper "quoted"', abstract: '', url: 'https://europepmc.org/article/MED/1', relevance: '', direction_signals: ['negative_candidate'] }],
    claims: [], assessments: [{ source_ids: ['NCT00123890'], historical_evidence: 'TERMINATED; hepatoxicity', concern: 'safety', relevance: '', limitations: [], recommendation: 'revise', rationale: '', compound_specificity: '', target_engagement: '' }],
    conclusion: 'INSUFFICIENT COVERAGE', missing_information: ['m1'], retrieval_notes: [], retrieval_errors: [],
    ai: { enabled: true, status: 'completed', model: 'claude-opus-5-5', provider: 'anthropic', warnings: [], rounds: [], accepted_claims: [{ claim_id: 'DA_CLAIM_1', text: 'Claim <b>text</b>', kind: 'interpretation', concern: 'efficacy', stance: 'supporting', relevance: 'r', uncertainty: 'u', citations: [{ source_id: 'MED:1', field: 'abstract', excerpt: 'quoted & excerpt' }] }], source_urls: { 'MED:1': 'https://europepmc.org/article/MED/1' } } },
} as unknown as Report;

describe('reportHtml', () => {
  const html = reportHtml(report, [{ decision_id: 'd1', job_id: 'j', action: 'approve_for_screening', rationale: 'Because <reasons>', confirmed: true, mode: 'live' }]);
  it('is a self-contained document with the key sections', () => {
    expect(html.startsWith('<!doctype html>')).toBe(true);
    for (const text of ['CCR5 in HIV infectious disease', 'Initial assessment', 'Accepted claims (1)', 'DA_CLAIM_1', 'Proposed experiment', 'Review before proceeding', 'Claude reasoning was not run', 'approve for screening', 'MARAVIROC', 'NCT00123890', 'safety', 'MED:1']) expect(html).toContain(text);
  });
  it('escapes report text so it cannot inject markup', () => {
    expect(html).not.toContain('<b>text</b>');
    expect(html).toContain('Claim &lt;b&gt;text&lt;/b&gt;');
    expect(html).toContain('quoted &amp; excerpt');
    expect(html).toContain('Because &lt;reasons&gt;');
    expect(html).toContain('Which factors limit benefit &lt;from&gt; CCR5 modulation?');
  });
  it('keeps review flags out of the plain limitations list', () => {
    expect(html.split('Claude reasoning was not run').length).toBe(2);
    expect(html).toContain('Cell models differ');
  });
});
