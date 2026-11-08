'use client';
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import Image from 'next/image';
import { api } from '@/lib/api';
import { ClaimText } from './evidence-trace';
import type { AIReport } from '@/lib/contracts';
import { DEFAULT_WEIGHTS, rankTargets } from '@/lib/contracts';
import type { Config, Job, Mode, ScoutRun, ScoutTarget, Weights } from '@/lib/contracts';

type State = {
  mode:Mode; setMode:(mode:Mode)=>void; run:ScoutRun|null; setRun:(run:ScoutRun|null)=>void;
  weights:Weights; setWeights:(weights:Weights)=>void; target:ScoutTarget|null; select:(target:ScoutTarget)=>void;
  job:Job|null; config:Config|null; error:string; setError:(error:string)=>void;
  busy:boolean; challenge:(useAI:boolean, manual?:{disease_name:string;target_symbol:string;chembl_target_id?:string})=>Promise<void>;
  cancel:()=>Promise<void>; refresh:()=>Promise<void>; refreshConfig:()=>Promise<void>;
  reset:()=>void; resume:(identifier:string)=>Promise<void>;
};
const Context = createContext<State|null>(null);
export function useWorkbench() { const state=useContext(Context); if(!state) throw new Error('Workbench context missing'); return state; }
const steps = [{href:'/',label:'Discover Targets',number:'01'}, {href:'/challenge',label:"Challenge Targets",number:'02'}, {href:'/experiment',label:'Clarify Experiment',number:'03'}, {href:'/decision',label:'Researcher decision',number:'04'}];
const terminal = new Set(['completed','failed','cancelled','interrupted']);

export function Workbench({children}:{children:React.ReactNode}) {
  const [mode,setModeState]=useState<Mode>('offline');
  const modeRef=useRef<Mode>('offline');
  const [run,setRunState]=useState<ScoutRun|null>(null);
  const [weights,setWeightsState]=useState<Weights>(DEFAULT_WEIGHTS);
  const [target,setTarget]=useState<ScoutTarget|null>(null);
  const [job,setJob]=useState<Job|null>(null);
  const [config,setConfig]=useState<Config|null>(null);
  const [error,setError]=useState('');
  const [submitting,setSubmitting]=useState(false);
  const [hydrated,setHydrated]=useState(false);
  const [sidebarCollapsed,setSidebarCollapsed]=useState(false);
  const requestId=useRef<string|null>(null);
  const generation=useRef(0);
  const submittingRef=useRef(false);
  const persistReady=useRef(false);
  const pathname=usePathname();

  const clear=useCallback(()=>{persistReady.current=true;generation.current+=1;requestId.current=null;setJob(null);setError('');},[]);
  const setMode=useCallback((value:Mode)=>{clear();modeRef.current=value;setModeState(value);setRunState(null);setTarget(null);},[clear]);
  const setRun=useCallback((value:ScoutRun|null)=>{if(value&&value.cache_only!==(modeRef.current==='offline'))return;clear();setRunState(value);setTarget(null);},[clear]);
  const select=useCallback((value:ScoutTarget)=>{if(value.target_id!==target?.target_id){clear();setTarget(value);}},[clear,target]);
  const setWeights=useCallback((value:Weights)=>{clear();setWeightsState(value);},[clear]);
  const refreshConfig=useCallback(async()=>{try{setConfig(await api<Config>('/api/workbench/config',mode));}catch(e){setError((e as Error).message);}},[mode]);

  useEffect(()=>{
    let disposed=false;
    const initialGeneration=generation.current;
    async function restore() {
      try {
        const saved=JSON.parse(localStorage.getItem('agentverse-workbench-v1') || 'null');
        if(saved) {
          const m:Mode=saved.mode==='live'?'live':'offline';
          if(!disposed){modeRef.current=m;setModeState(m);}
          if(saved.run_id) {
            const restored=await api<ScoutRun>(`/api/workbench/runs/${saved.run_id}`,m);
            if(!disposed&&generation.current===initialGeneration){setRunState(restored);setWeightsState(saved.weights||DEFAULT_WEIGHTS);setTarget(restored.targets.find(t=>t.target_id===saved.target_id)||null);}
          }
          if(saved.job_id) {
            const restoredJob=await api<Job>(`/api/investigations/${saved.job_id}`,m);
            if(!disposed&&generation.current===initialGeneration&&(!saved.target_id || restoredJob.selection.target_input.target_id===saved.target_id))setJob(restoredJob);
          }
        }
        if(!disposed&&generation.current===initialGeneration)persistReady.current=true;
      } catch { if(!disposed)setError('Previous session could not be restored. Start a new discovery or reconnect to the backend.'); }
      finally {if(!disposed)setHydrated(true);}
    }
    void restore();
    return ()=>{disposed=true;};
  },[]);
  useEffect(()=>{let active=true;void api<Config>('/api/workbench/config',mode).then(value=>{if(active)setConfig(value);}).catch(e=>{if(active)setError((e as Error).message);});return()=>{active=false;};},[mode]);
  useEffect(()=>{if(hydrated&&persistReady.current)localStorage.setItem('agentverse-workbench-v1',JSON.stringify({mode,run_id:run?.run_id,target_id:target?.target_id,weights,job_id:job?.job_id}));},[hydrated,mode,run,target,weights,job?.job_id]);

  const jobId=job?.job_id;
  const active=Boolean(job && !terminal.has(job.state));
  const refresh=useCallback(async()=>{
    if(!jobId)return;
    const current=generation.current;
    const updated=await api<Job>(`/api/investigations/${jobId}`,mode);
    if(current===generation.current)setJob(updated);
  },[jobId,mode]);
  useEffect(()=>{
    if(!active)return;
    const timer=setInterval(()=>{void refresh().catch(()=>setError('Connection interrupted. The job remains on the backend; polling will retry.'));},1500);
    return ()=>clearInterval(timer);
  },[active,refresh]);

  const challenge=async(useAI:boolean,manual?:{disease_name:string;target_symbol:string;chembl_target_id?:string})=>{
    if(submittingRef.current || active)return;
    submittingRef.current=true;setSubmitting(true);setError('');
    const current=generation.current;
    requestId.current ||= crypto.randomUUID();
    try {
      const body=manual?{target_input:manual,use_ai:useAI,paid_authorized:useAI,weights}:{run_id:run?.run_id,symbol:target?.symbol,use_ai:useAI,paid_authorized:useAI,weights};
      const created=await api<{job_id:string}>('/api/investigations',mode,{method:'POST',headers:{'Idempotency-Key':requestId.current},body:JSON.stringify(body)});
      const updated=await api<Job>(`/api/investigations/${created.job_id}`,mode);
      if(current===generation.current)setJob(updated);
    } catch(e) {setError((e as Error).message);}
    finally{submittingRef.current=false;setSubmitting(false);}
  };
  const cancel=async()=>{if(jobId){await api(`/api/investigations/${jobId}/cancel`,mode,{method:'POST'});await refresh();}};
  const resume=async(identifier:string)=>{try{clear();const current=generation.current;const updated=await api<Job>(`/api/investigations/${identifier}`,mode);let restored:ScoutRun|null=null;if(updated.selection.run_id)restored=await api<ScoutRun>(`/api/workbench/runs/${updated.selection.run_id}`,mode);if(current!==generation.current)return;setRunState(restored);setTarget(restored?.targets.find(t=>t.target_id===updated.selection.target_input.target_id)||null);setWeightsState(updated.weights);setJob(updated);}catch(e){setError((e as Error).message);}};
  return <Context.Provider value={{mode,setMode,run,setRun,weights,setWeights,target,select,job,config,error,setError,busy:active||submitting,challenge,cancel,refresh,refreshConfig,reset:clear,resume}}>
    <div className={`workspace${sidebarCollapsed?' sidebar-collapsed':''}`}>
      <aside className="sidebar">
        <div className="sidebar-header">
          <Link href="/" className="brand" aria-label="AgentVerse Research Workbench">
            <Image
              className="brand-logo"
              src="/agentverse-logo.png"
              alt=""
              width={40}
              height={40}
              priority
            />
            <span className="brand-copy">AGENTVERSE<small>RESEARCH WORKBENCH</small></span>
          </Link>
          <button
            type="button"
            className="sidebar-toggle"
            aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-expanded={!sidebarCollapsed}
            aria-controls="workbench-navigation"
            onClick={() => setSidebarCollapsed((collapsed) => !collapsed)}
          >
            {sidebarCollapsed ? '›' : '‹'}
          </button>
        </div>
        <div className="nav-label">TARGET VALIDATION</div>
        <nav id="workbench-navigation">{steps.map(s=><Link key={s.href} href={s.href} title={s.label} aria-label={s.label} className={pathname===s.href?'nav-item selected':'nav-item'}><span className="nav-number">{s.number}</span><span className="nav-text">{s.label}</span></Link>)}</nav>
      </aside>
      <div className="main-frame">
        <header className="topbar"><span>Research workspace <span className="muted">/ Target validation</span></span><div className="top-actions"><span className={`badge ${mode==='live'?'live':'recorded'}`}>{mode==='live'?'LIVE DATA':'RECORDED DEMO'}</span><label className="mode-switch">Data source<select aria-label="Research data mode" value={mode} onChange={e=>setMode(e.target.value as Mode)} disabled={submitting}><option value="offline">Recorded demo</option><option value="live">Live APIs</option></select></label></div></header>
        <main>{error&&<div role="alert" className="notice error">{error}<button className="text-button" onClick={()=>setError('')}>Dismiss</button></div>}{children}</main>
        <footer>Public research evidence only <span>ChEMBL · Open Targets · Europe PMC · ClinicalTrials.gov</span><span>Research use · Expert review required</span></footer>
      </div>
    </div>
  </Context.Provider>;
}

export function PageTitle({title}:{title:string}) {return <div className="page-title"><h1>{title}</h1></div>;}
export function Badge({children,tone='neutral'}:{children:React.ReactNode;tone?:string}){return <span className={`badge ${tone}`}>{children}</span>;}
export function EmptyState({title,children}:{title:string;children:React.ReactNode}) {return <section className="panel empty-state"><div className="empty-symbol">◎</div><h2>{title}</h2><p>{children}</p><Link className="button secondary" href="/">Open Target Discovery →</Link></section>;}
export function SelectionBar(){const {target,run,job}=useWorkbench();const input=job?.selection.target_input;return <div className="selection-bar"><span className="target-symbol">{target?.symbol||input?.target_symbol||'No target selected'}</span><span>{run?.disease.name||input?.disease_name}</span><span className="mono muted">{target?.target_id||input?.target_id}</span>{target?.chembl_target_id&&<Badge>{target.chembl_target_id}</Badge>}</div>;}
export function Progress(){
  const {job,busy,cancel}=useWorkbench();
  const [now,setNow]=useState(0);
  useEffect(()=>{if(!busy)return;const timer=setInterval(()=>setNow(Date.now()/1000),1000);return()=>clearInterval(timer);},[busy]);
  if(!job||!busy)return null;
  const done=job.progress.calls.filter(c=>c.success).length;
  const call=job.progress.calls.at(-1);
  const started=call?.duration_seconds==null?call?.started_at:undefined;
  const elapsed=started&&now?Math.max(0,now-started):null;
  const retrieval=job.progress.retrieval;
  return <section className="panel progress-panel" aria-live="polite"><div className="spinner"/><div><h3>{job.progress.stage}</h3><p>{done} model calls completed · {job.progress.calls.length} attempted. The investigation continues on the backend if you leave this page.</p>
    {elapsed!==null&&<p>Current model request: {elapsed.toFixed(1)} s elapsed (backend start timestamp).</p>}
    {retrieval&&<p>{retrieval.source} · {retrieval.state} · retry policy: at most {retrieval.retry_policy_max_attempts} attempts per request{retrieval.retries_observed!=null?` · ${retrieval.retries_observed} retries observed`:''}</p>}
    {retrieval?.state==='request'&&retrieval.started_at&&now>0&&<p>Current public-data request: {Math.max(0,now-retrieval.started_at).toFixed(1)} s elapsed, including any retry wait.</p>}
    {job.progress.timings?.retrieval&&<p>Retrieval measured so far: {job.progress.timings.retrieval.total_seconds.toFixed(2)} s · {job.progress.timings.retrieval.completed_requests} requests completed · {job.progress.timings.retrieval.cache_hits} cache hits.</p>}
    <small>Cancellation stops future calls. An in-flight provider request may complete and be billed.</small></div><button className="button secondary" disabled={job.state==='cancel_requested'} onClick={()=>void cancel()}>Stop after current call</button></section>;
}
export function Bullets({items,ai}:{items:string[];ai?:AIReport|null}){return <ul className="report-list">{items.map((item,i)=><li key={i}>{ai?<ClaimText text={item} ai={ai}/>:item}</li>)}</ul>;}
export function selectedScore(target:ScoutTarget,weights:Weights){return rankTargets([target],weights)[0].total;}

export function RecentJobs(){const {mode,job,resume}=useWorkbench();const [items,setItems]=useState<{job_id:string;state:string;target:{target_symbol:string;disease_name:string}}[]>([]);useEffect(()=>{let active=true;void api<typeof items>('/api/investigations',mode).then(data=>{if(active)setItems(data);}).catch(()=>{});return()=>{active=false;};},[mode,job?.state]);if(!items.length)return null;return <details className="panel panel-content"><summary>Recent investigations · resume a saved job</summary><div className="recent-jobs">{items.map(item=><button key={item.job_id} className="mini-card" onClick={()=>void resume(item.job_id)}><strong>{item.target.target_symbol}</strong><span>{item.target.disease_name}</span><Badge>{item.state}</Badge></button>)}</div></details>;}
