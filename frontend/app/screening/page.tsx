'use client';
import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { Badge, EmptyState, PageTitle, SelectionBar, useWorkbench } from '@/components/workbench';
import type { RubricObjective, ScreeningResult } from '@/lib/contracts';
import { ScreeningTable } from '@/components/screening-table';

export default function ScreeningPage(){const {job}=useWorkbench();return <ScreeningView key={job?.job_id||'empty'}/>;}

function ScreeningView(){
  const {job,mode,screening,setScreening,setError}=useWorkbench();
  const [busy,setBusy]=useState(false);
  const [objective,setObjective]=useState<RubricObjective>(screening?.rubric?.objective??'balanced');
  const started=useRef(false);
  const result=job?.result;
  // The newest signed approval on this investigation is the only thing the server will screen.
  const approval=job?.decisions.findLast(d=>d.approval)?.approval;

  async function screen(obj:RubricObjective=objective){if(!approval||!job)return;setBusy(true);setError('');try{
    const body={approval,approval_id:approval.approval_id,disease_id:job.selection.target_input.disease_id??approval.disease_id,target_id:job.selection.target_input.target_id??approval.target_id,rubric:{objective:obj}};
    setScreening(await api<ScreeningResult>('/api/screen',mode,{method:'POST',body:JSON.stringify(body)}));}catch(e){setError((e as Error).message);}finally{setBusy(false);}}

  // Approval already is the human action; the retrieval that follows it starts on arrival and is never repeated silently.
  useEffect(()=>{if(approval&&!screening&&!started.current){started.current=true;void screen();}
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[approval]);

  return <><PageTitle eyebrow="05 / COMPOUND CANDIDATES" title="Known ligands, ranked and traceable." description="Published ChEMBL compounds for the approved target, ordered by a documented four-factor rubric. Starting points for a tool-compound or repurposing search, not predictions."/><SelectionBar/>
    {!result?<EmptyState title="Approve a target first.">Compound screening opens after a completed investigation and an explicit researcher approval.</EmptyState>
    :!approval?<section className="panel empty-state"><div className="empty-symbol">◎</div><h2>Locked until a researcher approves this target.</h2><p>The screening request carries the signed approval; without it the server refuses to run. Record an approval on the decision page.</p><Link className="button secondary" href="/decision">Open researcher decision →</Link></section>
    :<section className="panel panel-content">
      <div className="panel-heading inline"><div><div className="eyebrow">APPROVED TARGET SCREENING</div><h2>{approval.symbol} compound pool</h2><p>Approval <span className="mono">{approval.approval_id}</span> by {approval.approved_by} · {approval.ts}</p></div><button className="button primary" disabled={busy} onClick={()=>void screen()}>{busy?'Retrieving screening evidence…':screening?'Re-run screening ↻':'Run approved screening →'}</button></div>
      {busy&&!screening&&<div className="progress-panel" aria-live="polite"><div className="spinner"/><div><h3>Screening {approval.symbol}…</h3><p>{mode==='offline'?'Loading the recorded compound pool.':'Retrieving ChEMBL activities, drug-likeness, indications and off-target records, and the AlphaFold model. About ten to twenty seconds.'}</p></div></div>}
      {screening&&<><div className="notice"><Badge tone={mode==='offline'?'recorded':'live'}>{mode==='offline'?'RECORDED SCREENING DATA':'LIVE / API CACHE'}</Badge> {mode==='offline'?'RECORDED SCREENING DATA':'LIVE / API CACHE'} · {screening.approval.symbol} · approval <span className="mono">{screening.approval.approval_id}</span></div>
        {screening.structure&&<p>AlphaFold structure: <a className="source-link" href={screening.structure.pdb_url} target="_blank" rel="noreferrer">{screening.structure.model_id} ↗</a> · mean pLDDT {screening.structure.mean_plddt.toFixed(1)}</p>}
        <ScreeningTable screening={screening} objective={objective} busy={busy} onObjective={o=>{setObjective(o);void screen(o);}}/></>}
    </section>}
  </>;
}
