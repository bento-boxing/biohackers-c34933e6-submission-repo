'use client';
import { useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Badge, PageTitle, useWorkbench } from '@/components/workbench';
import { api } from '@/lib/api';
import { rankTargets, normaliseWeights } from '@/lib/contracts';
import type { ScoutRun, Weights } from '@/lib/contracts';

export default function Discovery(){
  const {mode,run,setRun,weights,setWeights,target,select,busy,setError}=useWorkbench();
  const [disease,setDisease]=useState('Parkinson disease');
  const [loading,setLoading]=useState(false);
  const requestVersion=useRef(0);
  const router=useRouter();
  const ranked=run?rankTargets(run.targets,weights):[];
  const effectiveWeights=normaliseWeights(weights);
  async function discover(){
    const version=++requestVersion.current;
    setRun(null);setLoading(true);setError('');
    try{const result=await api<ScoutRun>('/api/scout',mode,{method:'POST',body:JSON.stringify({disease,n:25})});if(version===requestVersion.current)setRun(result);}
    catch(e){setError((e as Error).message);}finally{if(version===requestVersion.current)setLoading(false);}
  }
  return <>
    <PageTitle eyebrow="01 / TARGET DISCOVERY" title="A stronger starting hypothesis." description="Discover protein targets, inspect the evidence, and choose what deserves a closer look."/>
    <section className="panel discovery-form"><div><label htmlFor="disease">Disease or indication</label><div className="search-row"><span aria-hidden="true">⌕</span><input id="disease" value={disease} onChange={e=>{setDisease(e.target.value);requestVersion.current++;setRun(null);setLoading(false);}} onKeyDown={e=>{if(e.key==='Enter'&&disease.trim()&&!loading)void discover();}} placeholder="e.g. Parkinson disease"/><button className="button primary" onClick={()=>void discover()} disabled={loading||!disease.trim()}>{loading?'Retrieving evidence…':'Discover targets →'}</button></div></div><p>{mode==='offline'?'Recorded Parkinson disease demonstration · no network or paid AI calls.':'Live Open Targets, ChEMBL and Europe PMC · no paid reasoning at discovery.'}</p></section>
    <div className="metric-grid"><div className="metric"><span>Candidate targets</span><strong>{run?ranked.length:'—'}</strong><small>Evidence-ranked proteins</small></div><div className="metric"><span>Evidence dimensions</span><strong>04</strong><small>Genetic · association · druggability · literature</small></div><div className="metric"><span>Research control</span><strong className="metric-word">Human</strong><small>Approval before protein screening</small></div></div>
    <div className="discovery-grid"><section className="panel target-panel"><div className="panel-heading"><div><h2>Ranked protein targets</h2><p>{run?`${run.disease.name} · ${run.disease.id}`:'Run discovery to build your shortlist.'}</p></div><Badge tone={mode==='offline'?'recorded':'live'}>{mode==='offline'?'RECORDED':'LIVE / API CACHE'}</Badge></div>
      {loading?<div className="empty-table"><div className="spinner"/>Retrieving and enriching target evidence. This can take several minutes.</div>:!run?<div className="empty-table"><div className="empty-symbol">⌘</div><h3>Evidence before commitment.</h3><p>Your ranked target shortlist will appear here. Choose a disease above to begin.</p></div>:<div className="table-scroll"><table><thead><tr><th>Rank</th><th>Protein target</th><th>Ranking score</th><th>Genetics</th><th>Association</th><th>Druggability</th><th>Literature</th><th>Safety flags</th><th/></tr></thead><tbody>{ranked.map(t=><tr key={t.target_id} className={target?.target_id===t.target_id?'row-selected':''}><td className="muted mono">{String(t.rank).padStart(2,'0')}</td><td><strong>{t.symbol}</strong><small className="cell-secondary">{t.name}</small></td><td><div className="score-value">{t.total.toFixed(3)}<span className="score-track"><i style={{width:`${t.total*100}%`}}/></span></div></td><td>{t.components.genetic.toFixed(2)}</td><td>{t.components.association.toFixed(2)}</td><td>{t.components.druggability.toFixed(2)}</td><td>{t.components.literature.toFixed(2)}</td><td>{t.safety_flags.length?<Badge tone="warning">{t.safety_flags.length} to review</Badge>:<span className="muted">None retrieved</span>}</td><td><button className="text-button" onClick={()=>{select(t);router.push('/challenge');}}>Select {t.symbol} →</button></td></tr>)}</tbody></table></div>}
      <div className="table-note">Ranking scores summarize retrieved evidence. They are not clinical success probabilities.</div></section>
      <aside className="panel weights-panel"><div className="eyebrow">TRANSPARENT RANKING</div><h2>Your research priorities.</h2><p>Adjust the evidence weights to explore a different ranking. The scientific scoring formula is unchanged.</p>{(Object.keys(weights) as (keyof Weights)[]).map(key=><label className="weight-row" key={key}><span>{key}<b>{Math.round(effectiveWeights[key]*100)}%</b></span><input aria-label={`${key} weight`} type="range" min="0" max="1" step="0.05" value={weights[key]} disabled={busy} onChange={e=>setWeights({...weights,[key]:Number(e.target.value)})}/></label>)}<div className="formula">Weighted total<br/><span>Σ normalized weight × component score</span></div><p className="fine-print">Safety flags remain visible and are not folded into a single ranking score.</p></aside></div>
    <section className="bottom-note"><span>↗</span><div><h3>Discovery is the beginning of the investigation.</h3><p>Select a target to challenge historical evidence, verify claims and identify the next scientific question.</p></div></section>
  </>;
}
