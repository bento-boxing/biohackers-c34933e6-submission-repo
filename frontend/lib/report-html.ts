import type { Decision, Report } from './contracts';

const esc = (v: unknown) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c] as string));
const list = (items: string[] | undefined, empty = 'None recorded.') => items?.length ? `<ul>${items.map(i => `<li>${esc(i)}</li>`).join('')}</ul>` : `<p class="muted">${empty}</p>`;
const link = (url: string, text: string) => `<a href="${esc(url)}">${esc(text)}</a>`;

/** A self-contained, printable HTML version of the research report: open in a browser, then Print → Save as PDF. */
export function reportHtml(report: Report, decisions: Decision[]): string {
  const inv = report.investigation; const t = inv.target; const ai = inv.ai; const e = report.experiment;
  const when = report.provenance ? new Date(report.provenance.retrieved_at * 1000).toLocaleString() : 'unknown';
  const flags = e.limitations.filter(l => l.startsWith('Review flag: ')).map(l => l.slice(13));
  const accepted = ai?.accepted_claims ?? [];
  const rounds = ai?.rounds ?? [];
  const concerns = inv.assessments.filter(a => a.concern !== 'unknown');
  const pubs = inv.publications.slice(0, 40);
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${esc(t.target_symbol)} · ${esc(t.disease_name)} · research report</title>
<style>
body{font:11pt/1.45 Georgia,serif;color:#111;max-width:860px;margin:32px auto;padding:0 20px}h1{font-size:22pt;margin:0 0 4px}h2{font-size:15pt;margin:28px 0 8px;border-bottom:1px solid #999;padding-bottom:3px;page-break-after:avoid}h3{font-size:12pt;margin:16px 0 4px}
.muted{color:#666}.meta{color:#444;font-size:10pt}.box{border:1px solid #bbb;padding:10px 14px;margin:10px 0;page-break-inside:avoid}.warn{border-color:#b8860b;background:#fff8e6}.claim{margin:10px 0;page-break-inside:avoid}blockquote{margin:4px 0 4px 14px;padding-left:10px;border-left:3px solid #ccc;color:#333;font-size:10pt}
table{border-collapse:collapse;width:100%;font-size:9.5pt}th,td{border:1px solid #ccc;padding:4px 6px;text-align:left;vertical-align:top}th{background:#eee}a{color:#1a4e8a}small{font-size:9pt}
@media print{body{margin:0;max-width:none}a{text-decoration:none}}
</style></head><body>
<h1>${esc(t.target_symbol)} in ${esc(t.disease_name)}</h1>
<p class="meta">Research workbench report · retrieved ${esc(when)} · ${esc(report.mode)} mode · pipeline ${esc(report.provenance?.pipeline_version ?? 'n/a')} · ChEMBL target ${esc(inv.resolved_target_id ?? 'unresolved')} · ${esc(t.target_id ?? '')}</p>
<p class="meta">Public research evidence only (ChEMBL, Open Targets, ClinicalTrials.gov, Europe PMC). Not a systematic review. Expert review required before any decision or experiment.</p>

<h2>1. Initial assessment (deterministic evidence rules)</h2><p>${esc(inv.conclusion)}</p>
${inv.coverage ? `<p><strong>Coverage:</strong> ${esc(inv.coverage.status)}${inv.coverage.pathway ? ` · ${esc(inv.coverage.pathway.replaceAll('_',' '))}` : ''}</p>${list(inv.coverage.gaps, 'No coverage gaps recorded.')}` : ''}
<h3>Missing information</h3>${list(inv.missing_information)}

<h2>2. Scientific challenge (Gemini ${esc(ai?.model ?? '')}${ai ? `, status ${esc(ai.status)}` : ': not run'})</h2>
${ai?.warnings?.length ? `<div class="box warn">${list(ai.warnings)}</div>` : ''}
<h3>Accepted claims (${accepted.length})</h3>
${accepted.length ? accepted.map(c => `<div class="claim"><strong>${esc(c.claim_id)}</strong> · ${esc(c.kind)} · ${esc(c.concern)} · ${esc(c.stance)}<p>${esc(c.text)}</p><p><em>Relevance:</em> ${esc(c.relevance)}<br><em>Uncertainty:</em> ${esc(c.uncertainty)}</p>${c.citations.map(ci => `<blockquote>${esc(ci.excerpt)}<br><small>${ai?.source_urls?.[ci.source_id] ? link(ai.source_urls[ci.source_id], ci.source_id) : esc(ci.source_id)} · ${esc(ci.field)}</small></blockquote>`).join('')}</div>`).join('') : '<p class="muted">No challenger claim was accepted for review.</p>'}
${rounds.map(r => `<h3>Round ${r.round_number + 1} · ${r.round_number === 0 ? 'initial challenge' : 'revised challenge'}</h3><p>${esc(r.draft.initial_assessment)}</p><table><tr><th>Claim</th><th>Kind</th><th>Verdict</th><th>Objections / adjudicator finding</th></tr>${r.draft.claims.map(c => { const f = r.adjudications.find(a => a.claim_id === c.claim_id); const obj = r.deterministic_objections?.[c.claim_id] ?? []; return `<tr><td>${esc(c.text)}</td><td>${esc(c.kind)}</td><td>${r.accepted_claim_ids.includes(c.claim_id) ? 'accepted' : 'not accepted'}</td><td>${obj.map(o => esc(o)).join('<br>')}${obj.length && f ? '<br>' : ''}${f ? `<em>${esc(f.verdict)}:</em> ${esc(f.finding)}` : ''}</td></tr>`; }).join('')}</table>`).join('')}

<h2>3. Proposed experiment</h2>
<p class="meta">${esc(e.status)}</p>
${flags.length ? `<div class="box warn"><strong>Review before proceeding</strong>${list(flags)}</div>` : ''}
<h3>Research question</h3><p><strong>${esc(e.question)}</strong></p>
${e.knowledge_review ? `<h3>Existing knowledge</h3><p>${esc(e.knowledge_review)}</p>` : ''}${e.unresolved_gap ? `<h3>Decision-relevant gap</h3><p>${esc(e.unresolved_gap)}</p>` : ''}
<h3>Competing explanations</h3>${list(e.competing_explanations)}
<h3>Model</h3><p>${esc(e.model)}</p><h3>Measurements</h3><p>${esc(e.measurement)}</p><h3>Controls</h3>${list(e.controls)}
<h3>Possible results</h3>${list(e.possible_results)}<h3>How it changes the decision</h3><p>${esc(e.decision_impact)}</p>
<h3>Limitations</h3>${list(e.limitations.filter(l => !l.startsWith('Review flag: ')))}

<h2>4. Researcher decisions</h2>
${decisions.length ? decisions.map(d => `<div class="box"><strong>${esc(d.action.replaceAll('_',' '))}</strong> · <small>${esc(d.decision_id)}</small><p>${esc(d.rationale)}</p>${d.approval ? `<p class="meta">Approved by ${esc(d.approval.approved_by)} · ${esc(d.approval.ts)}</p>` : ''}</div>`).join('') : '<p class="muted">No decision recorded.</p>'}

<h2>5. Evidence</h2>
<h3>Curated compounds (${inv.compounds.length})</h3>
${inv.compounds.length ? `<table><tr><th>Compound</th><th>Max phase</th><th>Mechanisms</th></tr>${inv.compounds.map(c => `<tr><td>${link(c.url, c.name)}</td><td>${esc(c.max_phase ?? '')}</td><td>${esc(c.mechanisms.join('; '))}</td></tr>`).join('')}</table>` : '<p class="muted">No curated mechanism compounds retrieved.</p>'}
<h3>Historical programme concerns (${concerns.length} of ${inv.assessments.length} trials with a classified stop reason)</h3>
${concerns.length ? `<table><tr><th>Trial</th><th>Concern</th><th>Review</th><th>Registry evidence</th></tr>${concerns.map(a => `<tr><td>${a.source_ids.map(id => link(`https://clinicaltrials.gov/study/${id}`, id)).join(', ')}</td><td>${esc(a.concern)}</td><td>${esc(a.recommendation)}</td><td>${esc(a.historical_evidence)}</td></tr>`).join('')}</table>` : '<p class="muted">No trial recorded an efficacy, safety or operational stop reason.</p>'}
<h3>Registry trials (${inv.trials.length})</h3>
${inv.trials.length ? `<table><tr><th>NCT</th><th>Status</th><th>Title</th><th>Disease match</th></tr>${inv.trials.map(tr => `<tr><td>${link(tr.url, tr.nct_id)}</td><td>${esc(tr.status)}</td><td>${esc(tr.title)}</td><td>${esc(tr.disease_match)}</td></tr>`).join('')}</table>` : '<p class="muted">None retrieved.</p>'}
<h3>Publications (${pubs.length}${inv.publications.length > pubs.length ? ` of ${inv.publications.length}; full list in the JSON export` : ''})</h3>
${pubs.length ? `<table><tr><th>ID</th><th>Title</th><th>Date</th><th>Triage signals</th></tr>${pubs.map(p => `<tr><td>${link(p.url, p.identifier)}</td><td>${esc(p.title)}</td><td>${esc(p.publication_date ?? '')}</td><td>${esc((p.direction_signals ?? []).join(', '))}</td></tr>`).join('')}</table>` : '<p class="muted">None retrieved.</p>'}
${inv.retrieval_errors.length ? `<h3>Retrieval problems</h3>${list(inv.retrieval_errors)}` : ''}
<p class="meta">Triage signals and model agreement are not independent evidence. This document was generated by the research workbench from public sources and AI synthesis; it has not been reviewed by an expert.</p>
</body></html>`;
}
