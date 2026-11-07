import type { AIReport, Experiment } from '@/lib/contracts';
import { claimTokens, evidenceEntries, sharedHypothesisReferences } from '@/lib/evidence';

export function ClaimText({text,ai}:{text:string;ai?:AIReport|null}) {
  const entries=evidenceEntries(ai);
  return <>{claimTokens(text,ai).map((token,index)=>{
    const entry=entries.find(e=>e.claim.claim_id===token);
    if(entry)return <a className="source-link inline-reference" key={index} href={`#${entry.anchor}`} title={entry.claim.text} onClick={()=>{const trace=document.getElementById(entry.anchor)?.closest('details');if(trace)trace.open=true;}}>[{entry.label}]</a>;
    if(/^DA_CLAIM_\d+$/.test(token))return <span className="muted" key={index}>[Unresolved evidence reference]</span>;
    return token;
  })}</>;
}

export function SharedEvidenceNote({experiment,ai}:{experiment:Experiment;ai?:AIReport|null}) {
  const shared=sharedHypothesisReferences(experiment,ai);
  if(!shared.length)return null;
  const entries=evidenceEntries(ai);
  const labels=entries.filter(e=>shared.includes(e.claim.claim_id)).map(e=>e.label);
  return <p className="notice" data-testid="shared-evidence">Both hypotheses draw on {labels.join(', ')}. This is shared motivating evidence, not independent confirmation of either proposed explanation.</p>;
}

export function EvidenceTrace({ai}:{ai?:AIReport|null}) {
  const entries=evidenceEntries(ai);
  return <details className="panel panel-content evidence-trace"><summary>Evidence Trace · claim-to-source references</summary>
    {!entries.length&&<p>No accepted AI claim is available to trace. The proposal remains provisional.</p>}
    {entries.map(({claim,label,anchor})=><article id={anchor} className="evidence-item" key={claim.claim_id}>
      <h3>{label} · {claim.concern}</h3><p><ClaimText text={claim.text} ai={ai}/></p>
      <span className="badge">{claim.kind} · adjudicated for review</span><p><ClaimText text={claim.uncertainty} ai={ai}/></p>
      {claim.citations.map((citation,index)=><blockquote key={index}>{citation.excerpt}<br/>{ai?.source_urls[citation.source_id]?<a className="source-link" href={ai.source_urls[citation.source_id]} target="_blank" rel="noreferrer">{citation.source_id} · {citation.field} ↗</a>:<span>Supporting source URL unavailable; reference remains unresolved.</span>}</blockquote>)}
      <details className="technical"><summary>Internal audit reference</summary><code>{claim.claim_id}</code></details>
    </article>)}
    <p className="fine-print">References preserve the original claim and actual retrieved source links. Shared evidence is not independent replication. Model adjudication is not scientific validation.</p>
  </details>;
}
