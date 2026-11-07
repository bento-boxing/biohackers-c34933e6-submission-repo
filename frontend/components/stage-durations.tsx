import type { AIReport, Timings } from '@/lib/contracts';

export function duration(value?:number|null) { return typeof value==='number'?`${value.toFixed(2)} s`:'Not recorded'; }
export function StageDurations({timings,ai,recorded=false}:{timings?:Timings;ai?:AIReport|null;recorded?:boolean}) {
  return <details className="panel panel-content"><summary>Measured stage durations & request sizes</summary><div className="table-scroll"><table><thead><tr><th>Stage</th><th>Measured elapsed</th><th>Input payload</th></tr></thead><tbody>
    <tr><td>{timings?.recorded_playback_seconds!=null?'Recorded evidence playback':'Biomedical retrieval pipeline'}</td><td>{duration(timings?.recorded_playback_seconds??timings?.retrieval?.total_seconds)}</td><td>Public evidence</td></tr>
    {Object.entries(timings?.retrieval?.source_seconds||{}).map(([source,seconds])=><tr key={source}><td>{source} requests, including retry waits</td><td>{duration(seconds)}</td><td>Measured HTTP activity</td></tr>)}
    {ai?.calls.map((call,index)=><tr key={index}><td>{call.role}{recorded?' · historical output':''}</td><td>{duration(call.duration_seconds)}</td><td>{call.payload_bytes==null?'Not recorded':`${call.payload_bytes.toLocaleString()} bytes`}</td></tr>)}
  </tbody></table></div><p className="fine-print">Thinking level: {ai?.thinking_level||'not recorded for this historical report'}. Completed stages use backend monotonic measurements. No retrospective timing or live speed estimate is invented. Payload bytes are not token counts.</p>
  {timings?.retrieval&&<p className="fine-print">{timings.retrieval.requests} logical public-data requests · {timings.retrieval.cache_hits} cached responses reused. HTTP timings include bounded automatic retries; cache hits perform no upstream request.</p>}
  </details>;
}
