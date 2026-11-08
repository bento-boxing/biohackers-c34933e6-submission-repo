import type { AIReport, Experiment } from './contracts';

export function evidenceEntries(ai?: AIReport | null) {
  return (ai?.accepted_claims || []).map((claim,index)=>({claim,label:`Evidence ${index+1}`,anchor:`evidence-${index+1}`}));
}

export function claimTokens(text:string, ai?:AIReport|null):string[] {
  const known=evidenceEntries(ai).map(e=>e.claim.claim_id.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'));
  const pattern=new RegExp(`\\b(${[...known.sort((a,b)=>b.length-a.length),'DA_CLAIM_\\d+'].join('|')})\\b`,'g');
  return text.split(pattern).filter(Boolean);
}

export function hypothesisReferences(experiment:Experiment, ai?:AIReport|null) {
  const entries=evidenceEntries(ai);
  const valid=new Set(entries.map(e=>e.claim.claim_id));
  return experiment.competing_explanations.map((text,index)=>{
    const candidates=experiment.hypothesis_evidence?.[index] || claimTokens(text,ai).filter(t=>valid.has(t));
    return [...new Set(candidates.filter(id=>valid.has(id)))];
  });
}

export function sharedHypothesisReferences(experiment:Experiment, ai?:AIReport|null) {
  const groups=hypothesisReferences(experiment,ai);
  if(groups.length<2)return [];
  return groups[0].filter(id=>groups.slice(1).every(group=>group.includes(id)));
}
