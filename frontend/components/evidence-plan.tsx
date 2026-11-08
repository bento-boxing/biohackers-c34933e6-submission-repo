import type { EvidencePlan, Investigation } from '@/lib/contracts';
import { Badge } from './workbench';

const statusTone:Record<string,string>={satisfied:'live',partial:'warning',unmet:'warning',unverifiable:'warning',not_applicable:'neutral'};
const statusLabel:Record<string,string>={satisfied:'Retrieved',partial:'Partly retrieved',unmet:'Not retrieved',unverifiable:'Source failed',not_applicable:'Not applicable'};
const stopLabel:Record<string,string>={coverage_achieved:'All needs retrieved; follow-up stopped early.',no_actionable_gaps:'Open needs had no further searchable strategy.',no_new_evidence:'A follow-up round returned nothing new; stopped to avoid searching for evidence that is not there.',round_limit:'Follow-up round limit reached with needs still open.',budget_exhausted:'Retrieval time budget ran out; open needs are unverified, not absent.',follow_up_disabled:'Follow-up rounds were disabled for this request.',target_unresolved:'Target identity unresolved; no disease-specific plan could run.',not_run:'Planner did not run.'};

export function openNeeds(plan:EvidencePlan){return plan.needs.filter(n=>['unmet','partial','unverifiable'].includes(n.status)&&n.key!=='unresolved_uncertainty');}

export function EvidencePlanReport({investigation:i}:{investigation:Investigation}){
  const plan=i.evidence_plan;
  if(!plan)return <aside className="notice warning">No evidence discovery plan was recorded for this report (recorded demo or older report). Coverage of positive, negative and recent evidence was not systematically assessed.</aside>;
  const searches=plan.rounds.flatMap(r=>r.searches);
  const newEvidence=plan.rounds.flatMap(r=>r.new_evidence_ids);
  return <section className="panel panel-content" aria-label="Evidence discovery plan" data-testid="evidence-plan">
    <div className="eyebrow">EVIDENCE DISCOVERY PLAN</div>
    <h2>{plan.stage==='clinical'?'Clinical-stage pair':plan.stage==='preclinical'?'Preclinical pair':'Pair unresolved'} · {openNeeds(plan).length===0?'no open evidence needs':`${openNeeds(plan).length} open evidence need${openNeeds(plan).length===1?'':'s'}`}</h2>
    <p>{plan.stage_reason}</p>
    <p>{plan.rounds.length} follow-up round{plan.rounds.length===1?'':'s'} · {searches.length} targeted search{searches.length===1?'':'es'} · {newEvidence.length} new source record{newEvidence.length===1?'':'s'} · stopped: <strong>{stopLabel[plan.stop_reason]||plan.stop_reason}</strong></p>
    <div className="table-scroll"><table><thead><tr><th>What the investigation must establish</th><th>Status</th><th>Source records</th><th>Note</th></tr></thead><tbody>
      {plan.needs.map(n=><tr key={n.key} data-testid={`need-${n.key}`}><td>{n.label}</td><td><Badge tone={statusTone[n.status]||'neutral'}>{statusLabel[n.status]||n.status}</Badge></td><td>{n.evidence_ids.length}{n.material_ids.length>0&&<span className="muted"> · packet must keep {n.material_ids.join(', ')}</span>}{n.searches.length>0&&<span className="muted"> · searched: {Array.from(new Set(n.searches)).join('; ')}</span>}</td><td className="fine-print">{n.note}</td></tr>)}
    </tbody></table></div>
    {plan.rounds.length>0&&<details><summary>Follow-up searches, source responses and what each found</summary>{plan.rounds.map(r=><div key={r.round_number} className="evidence-item"><h3>Round {r.round_number} · {r.duration_seconds.toFixed(2)} s · open before: {r.unmet_before.join(', ')||'none'} · open after: {r.unmet_after.join(', ')||'none'}</h3>{r.searches.map((s,index)=><p key={index} className="fine-print"><strong>{s.need_key}</strong> · {s.source} · {s.operation} · {s.state} · {s.returned} returned · {s.new_evidence_ids.length} new ({s.new_evidence_ids.slice(0,6).join(', ')}{s.new_evidence_ids.length>6?'…':''}) · {s.duration_seconds.toFixed(2)} s{s.detail?` · ${s.detail}`:''}</p>)}</div>)}</details>}
    {plan.planner_suggestions.length>0&&<details><summary>Model planning suggestions (queries only, never evidence)</summary><pre>{JSON.stringify(plan.planner_suggestions,null,2)}</pre></details>}
    <h3>Development evidence tiers</h3>
    <p className="fine-print">Registry status · registry-posted results · peer-reviewed publications · FDA regulatory records. Sponsor-reported results are not retrieved (no permitted API); unverified claims never enter the packet. Dates are shown per record in the Publications and Compounds &amp; trials tabs.</p>
    {plan.limitations.map((l,index)=><p className="notice warning" key={index}>{l}</p>)}
    <p className="fine-print">{plan.caution} Planner: {plan.planner}. Plan and follow-up time: {plan.duration_seconds.toFixed(2)} s.</p>
  </section>;
}
