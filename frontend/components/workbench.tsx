'use client';
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { api } from '@/lib/api';
import { ClaimText } from './evidence-trace';
import type { AIReport, Decision, ProgressSnapshot, ScreeningResult } from '@/lib/contracts';
import { DEFAULT_WEIGHTS, rankTargets } from '@/lib/contracts';
import type { Config, Job, Mode, ScoutRun, ScoutTarget, Weights } from '@/lib/contracts';
import { loadState, saveState, withDecision } from '@/lib/workbench-storage';

type State = {
  mode:Mode; setMode:(mode:Mode)=>void; run:ScoutRun|null; setRun:(run:ScoutRun|null)=>void;
  weights:Weights; setWeights:(weights:Weights)=>void; target:ScoutTarget|null; select:(target:ScoutTarget)=>void;
  job:Job|null; config:Config|null; error:string; setError:(error:string)=>void;
  busy:boolean; progress:ProgressSnapshot|null;
  challenge:(useAI:boolean, manual?:{disease_name:string;target_symbol:string;chembl_target_id?:string}, options?:{refresh?:boolean})=>Promise<void>;
  addDecision:(decision:Decision)=>void; refreshConfig:()=>Promise<void>; reset:()=>void;
  screening:ScreeningResult|null; setScreening:(screening:ScreeningResult|null)=>void;
};
const Context = createContext<State|null>(null);
export function useWorkbench() { const state=useContext(Context); if(!state) throw new Error('Workbench context missing'); return state; }
const steps = [{href:'/',label:'Target discovery',number:'01'}, {href:'/challenge',label:"Devil’s Advocate",number:'02'}, {href:'/experiment',label:'Experimental Challenger',number:'03'}, {href:'/decision',label:'Researcher decision',number:'04'}, {href:'/screening',label:'Compound candidates',number:'05'}];

export function Workbench({children}:{children:React.ReactNode}) {
  // Live APIs by default; the recorded demo (no network, two pre-captured investigations) is opt-in.
  const [mode,setModeState]=useState<Mode>('live');
  const modeRef=useRef<Mode>('live');
  const [run,setRunState]=useState<ScoutRun|null>(null);
  const [weights,setWeightsState]=useState<Weights>(DEFAULT_WEIGHTS);
  const [target,setTarget]=useState<ScoutTarget|null>(null);
  const [job,setJob]=useState<Job|null>(null);
  // Screening belongs to one investigation; it is kept in memory only and re-run from the signed approval after a reload.
  const [screening,setScreening]=useState<ScreeningResult|null>(null);
  const [config,setConfig]=useState<Config|null>(null);
  const [error,setError]=useState('');
  const [submitting,setSubmitting]=useState(false);
  const [progress,setProgress]=useState<ProgressSnapshot|null>(null);
  const progressToken=useRef<string>('');
  const [hydrated,setHydrated]=useState(false);
  const generation=useRef(0);
  const submittingRef=useRef(false);
  const pathname=usePathname();

  const clear=useCallback(()=>{generation.current+=1;setJob(null);setScreening(null);setError('');},[]);
  const setMode=useCallback((value:Mode)=>{clear();modeRef.current=value;setModeState(value);setRunState(null);setTarget(null);},[clear]);
  const setRun=useCallback((value:ScoutRun|null)=>{if(value&&value.cache_only!==(modeRef.current==='offline'))return;clear();setRunState(value);setTarget(null);},[clear]);
  const select=useCallback((value:ScoutTarget)=>{if(value.target_id!==target?.target_id){clear();setTarget(value);}},[clear,target]);
  const setWeights=useCallback((value:Weights)=>{clear();setWeightsState(value);},[clear]);
  const refreshConfig=useCallback(async()=>{try{setConfig(await api<Config>('/api/workbench/config',mode));}catch(e){setError((e as Error).message);}},[mode]);

  // Restore the previous session from this browser only; the server keeps nothing between requests.
  useEffect(()=>{
    let disposed=false;
    const restore=()=>{
      if(disposed)return;
      const saved=loadState(window.localStorage);
      if(saved){
        modeRef.current=saved.mode;setModeState(saved.mode);setRunState(saved.run);setWeightsState(saved.weights);
        setTarget(saved.run?.targets.find(t=>t.target_id===saved.target_id)||null);setJob(saved.job);
      }
      setHydrated(true);
    };
    const timer=setTimeout(restore,0);
    return ()=>{disposed=true;clearTimeout(timer);};
  },[]);
  useEffect(()=>{let active=true;void api<Config>('/api/workbench/config',mode).then(value=>{if(active)setConfig(value);}).catch(e=>{if(active)setError((e as Error).message);});return()=>{active=false;};},[mode]);
  useEffect(()=>{if(hydrated)saveState(window.localStorage,{mode,run,target_id:target?.target_id||null,weights,job});},[hydrated,mode,run,target,weights,job]);

  // Real backend stage progress: the server writes stages under a client-chosen token while the one
  // request runs; the browser polls it. A host that cannot serve it says so instead of inventing progress.
  useEffect(()=>{
    if(!submitting||!progressToken.current)return;
    let active=true;
    const poll=async()=>{try{const snapshot=await api<ProgressSnapshot>(`/api/investigations/progress/${progressToken.current}`,modeRef.current);if(active)setProgress(snapshot);}catch{/* progress is optional */}};
    const first=setTimeout(poll,1500);const timer=setInterval(poll,2500);
    return()=>{active=false;clearTimeout(first);clearInterval(timer);};
  },[submitting]);
  const challenge=async(useAI:boolean,manual?:{disease_name:string;target_symbol:string;chembl_target_id?:string},options?:{refresh?:boolean})=>{
    if(submittingRef.current)return;
    submittingRef.current=true;setSubmitting(true);setError('');setProgress(null);
    progressToken.current=newProgressToken();
    const current=generation.current;
    try {
      const extras={refresh_evidence:Boolean(options?.refresh),progress_token:progressToken.current};
      const body=manual?{target_input:manual,use_ai:useAI,paid_authorized:useAI,weights,...extras}:{run,symbol:target?.symbol,use_ai:useAI,paid_authorized:useAI,weights,...extras};
      const finished=await api<Job>('/api/investigations',mode,{method:'POST',body:JSON.stringify(body)});
      if(current===generation.current)setJob(finished);
    } catch(e) {if(current===generation.current)setError((e as Error).message);}
    finally{submittingRef.current=false;setSubmitting(false);setProgress(null);}
  };
  const addDecision=useCallback((decision:Decision)=>{setJob(previous=>previous?withDecision(previous,decision):previous);},[]);
  return <Context.Provider value={{mode,setMode,run,setRun,weights,setWeights,target,select,job,config,error,setError,busy:submitting,progress,challenge,addDecision,refreshConfig,reset:clear,screening,setScreening}}>
    <div className="workspace">
      <aside className="sidebar">
        <Link href="/" className="brand"><span className="brand-symbol">✳</span><span>AGENTVERSE<small>RESEARCH WORKBENCH</small></span></Link>
        <div className="nav-label">TARGET VALIDATION</div>
        <nav>{steps.map(s=><Link key={s.href} href={s.href} className={pathname===s.href?'nav-item selected':'nav-item'}><span>{s.number}</span>{s.label}</Link>)}</nav>
        <div className="sidebar-note"><span className="status-dot"/> Human judgment, supported.<p>Trace every claim.<br/>Challenge every assumption.</p></div>
        <div className="sidebar-foot">AGENTVERSE 2026<span>Biotech research prototype</span></div>
      </aside>
      <div className="main-frame">
        <header className="topbar"><span>Research workspace <span className="muted">/ Target validation</span></span><div className="top-actions"><span className={`badge ${mode==='live'?'live':'recorded'}`}>{mode==='live'?'LIVE DATA':'RECORDED DEMO'}</span><label className="mode-switch">Data source<select aria-label="Research data mode" value={mode} onChange={e=>setMode(e.target.value as Mode)} disabled={submitting}><option value="offline">Recorded demo</option><option value="live">Live APIs</option></select></label></div></header>
        <main>{error&&<div role="alert" className="notice error">{error}<button className="text-button" onClick={()=>setError('')}>Dismiss</button></div>}{children}</main>
        <footer>Public research evidence only <span>ChEMBL · Open Targets · Europe PMC · ClinicalTrials.gov</span><span>Research use · Expert review required</span></footer>
      </div>
    </div>
  </Context.Provider>;
}

export function PageTitle({eyebrow,title,description}:{eyebrow:string;title:string;description:string}) {return <div className="page-title"><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>;}
export function Badge({children,tone='neutral'}:{children:React.ReactNode;tone?:string}){return <span className={`badge ${tone}`}>{children}</span>;}
export function EmptyState({title,children}:{title:string;children:React.ReactNode}) {return <section className="panel empty-state"><div className="empty-symbol">◎</div><h2>{title}</h2><p>{children}</p><Link className="button secondary" href="/">Open Target Discovery →</Link></section>;}
export function SelectionBar(){const {target,run,job}=useWorkbench();const input=job?.selection.target_input;return <div className="selection-bar"><span className="target-symbol">{target?.symbol||input?.target_symbol||'No target selected'}</span><span>{run?.disease.name||input?.disease_name}</span><span className="mono muted">{target?.target_id||input?.target_id}</span>{target?.chembl_target_id&&<Badge>{target.chembl_target_id}</Badge>}</div>;}
export function newProgressToken(){
  const bytes=new Uint8Array(16);
  if(typeof crypto!=='undefined'&&crypto.getRandomValues)crypto.getRandomValues(bytes);else for(let i=0;i<bytes.length;i++)bytes[i]=Math.floor(Math.random()*256);
  return Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
}
export function Progress(){
  const {busy,mode,target,config,progress}=useWorkbench();
  const [seconds,setSeconds]=useState(0);
  useEffect(()=>{if(!busy)return;const started=Date.now();const tick=()=>setSeconds(Math.round((Date.now()-started)/1000));const first=setTimeout(tick,0);const timer=setInterval(tick,1000);return()=>{clearTimeout(first);clearInterval(timer);};},[busy]);
  if(!busy)return null;
  const symbol=target?.symbol||'this target';
  const stages=progress?.available?progress.stages||[]:[];
  return <section className="panel progress-panel" aria-live="polite"><div className="spinner"/><div><h3>Investigating {symbol}…</h3>
    <p>{mode==='offline'?'Loading the recorded public evidence.':`Retrieving ChEMBL, ClinicalTrials.gov and Europe PMC records, assessing evidence coverage and running targeted follow-up searches${config?.ai.enabled?', then Gemini reasoning if you authorized it':''}. This usually takes one to three minutes.`}</p>
    <p>{seconds} s elapsed. The report arrives in one response; keep this page open.</p>
    {stages.length>0&&<ul className="report-list" data-testid="progress-stages">{stages.map((s,index)=><li key={index}>{s.finished_at?`✓ ${s.name} · ${(s.seconds??0).toFixed(1)} s`:`… ${s.name}`}</li>)}</ul>}
    {progress&&!progress.available&&<small>Backend stage progress is not available from this host instance; the investigation is still running.</small>}
    <small>No progress percentage is invented. A request that exceeds its time budget fails with an explicit message and no recorded data is substituted.</small></div></section>;
}
export function Bullets({items,ai}:{items:string[];ai?:AIReport|null}){return <ul className="report-list">{items.map((item,i)=><li key={i}>{ai?<ClaimText text={item} ai={ai}/>:item}</li>)}</ul>;}
export function selectedScore(target:ScoutTarget,weights:Weights){return rankTargets([target],weights)[0].total;}
