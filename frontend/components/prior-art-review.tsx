import type { AIReport } from '@/lib/contracts';
export function PriorArtReview({ai}:{ai?:AIReport|null}){
 const check=ai?.prior_art_check;if(!check?.status)return null;
 return <section className="panel panel-content" aria-label="Prior-art and final claim checks"><h2>Question-specific prior-art review</h2><p>{check.status}</p><p>{check.decision==='abstain'?'The proposal was withheld pending a more specific supported question or expert review.':'No strong overlap was flagged; novelty remains unestablished and the proposal requires expert review.'}</p>
 {check.objections.map((issue,index)=><p className="notice warning" key={index}>{issue}</p>)}
 <details><summary>Matching publications and known findings</summary>{check.matches.map(match=><article className="evidence-item" key={match.source_id}><a className="source-link" href={match.url} target="_blank" rel="noreferrer">{match.source_id} · {match.title}</a><p>{match.conclusion}</p></article>)}</details>
 <p className="fine-print">Overlap is a review flag, not proof that every detail is answered. No search result establishes novelty. All experiments remain unvalidated.</p>
 {check.original_proposal!=null&&<details className="technical"><summary>Original proposal retained for audit</summary><pre>{JSON.stringify(check.original_proposal,null,2)}</pre></details>}</section>;
}
