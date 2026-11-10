import type { Config,Report } from '@/lib/contracts';

export function ReportProvenance({report,config}:{report:Report;config:Config|null}){
 const p=report.provenance;const b=config?.backend;
 return <aside className="panel panel-content" aria-label="Report provenance">
  <h3>Report provenance</h3>
  <p>{p?.source_mode==='live_public_api'?'Live public-source retrieval':report.mode==='offline'?'Recorded evidence playback':'Saved report; retrieval provenance unavailable'}{p?` · ${new Date(p.retrieved_at*1000).toLocaleString()} · ${p.cache_hits} public-response cache hits`:''}</p>
  {p&&<p className="fine-print">Pipeline {p.pipeline_version} · source version {p.source_hash}</p>}
  {report.mode==='live'&&(!p||!b||p.source_hash!==b.source_hash)&&<p className="notice warning">This saved report may predate the current evidence pipeline. It is not automatically recomputed. A fresh retrieval requires a new explicit request.</p>}
  {report.mode==='live'&&(!b||!b.code_matches_disk)&&<p className="notice warning">The backend cannot confirm it has loaded the current files. Restart it when safe to apply code changes; existing investigations are preserved.</p>}
  {report.investigation.ai&&['disabled','skipped'].includes(report.investigation.ai.status)&&<div role="status"><strong>Claude was not run</strong>{report.investigation.ai.warnings.length?report.investigation.ai.warnings.map((reason,index)=><p key={index}>{reason}</p>):<p>No paid reasoning was requested or the backend disabled AI. Coverage eligibility is shown separately.</p>}</div>}
 </aside>;
}
