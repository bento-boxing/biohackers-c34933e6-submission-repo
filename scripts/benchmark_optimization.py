"""Opt-in public-only five-case cold/warm measurements; never imports Gemini SDK."""
import sys,json,time,statistics,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from devils_advocate.http_client import JsonClient,RetrievalDeadlineExceeded
from devils_advocate.devil_advocate import investigate_target
from devils_advocate.ai_config import AISettings
from devils_advocate.ai_reasoning import evidence_bundle
from devils_advocate.prior_art import check_prior_art
from devils_advocate.models import Investigation,Experiment

OUT=Path('devils_advocate/validation/optimization')
CASES=[('CCR5',{'disease_name':'HIV infectious disease','disease_id':'MONDO_0005109','target_symbol':'CCR5','chembl_target_id':'CHEMBL274','target_id':'ENSG00000160791'}),
 ('PCSK9',{'disease_name':'Hypercholesterolemia','target_symbol':'PCSK9'}),
 ('BACE1',{'disease_name':"Alzheimer's disease",'target_symbol':'BACE1'}),
 ('LRRK2',{'disease_name':"Parkinson's disease",'target_symbol':'LRRK2'}),
 ('BCL2',{'disease_name':'scoliosis','disease_id':'MONDO_0005392','target_symbol':'BCL2','chembl_target_id':'CHEMBL4860','target_id':'ENSG00000171791'})]

def digest(i):
    import hashlib
    records=i.model_dump(mode='json',include={'target','resolved_target_id','compounds','trials','publications'})
    for t in records['trials']:t['stop_reason']['checked_at_utc']=None
    return hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest()

if __name__=='__main__':
 OUT.mkdir(exist_ok=True)
 output={'baseline_job':'398304dac2fd43ae9edcf3ad044e9a7d','baseline_retrieval_seconds':139.197922,
  'baseline_model_seconds':92.947826,'baseline_end_to_end_seconds':238.884471,
  'method':'Real public sources, max four workers, per-host minimum .35 seconds (ClinicalTrials.gov 1.25 seconds). Separate clients for cold and warm passes. No model calls.',
  'cases':[],'paid_calls':0,'limitations':['Single measurements; network/time-of-day variability applies.','New Gemini latency and Medium/High scientific quality require separate paid authorization.']}
 selected=os.getenv('BENCHMARK_TARGETS','').split(',')
 if selected!=[''] and (OUT/'retrieval_report.json').exists():output=json.loads((OUT/'retrieval_report.json').read_text())
 for name,target in CASES:
  if selected!=[''] and name not in selected:continue
  path=Path('devils_advocate/runtime/optimization-benchmark')/(name+'-'+str(time.time_ns())+'.sqlite3')
  pair={};hashes=[]
  for mode in ['cold','warm']:
   client=JsonClient(cache_path=path,max_workers=4);start=time.perf_counter()
   try:
    with client.tracking(scope=target,budget_seconds=300) as profile:
     i=investigate_target(target,client=client)
    hashes.append(digest(i))
    summary={'seconds':round(time.perf_counter()-start,6),'requests':profile['requests'],'network_attempts':profile['network_attempts'],
     'cache_hits':profile['cache_hits'],'cache_hit_rate':round(profile['cache_hits']/max(1,profile['requests']+profile['cache_hits']),6),
     'source_seconds':profile['source_seconds'],'compounds':len(i.compounds),'trials':len(i.trials),'publications':len(i.publications),
     'coverage':i.coverage.status,'pathway':i.coverage.pathway,'gaps':i.coverage.gaps,'data_digest':hashes[-1]}
    (OUT/(name+'_'+mode+'_sources.json')).write_text(i.model_dump_json(indent=2),encoding='utf-8')
   except RetrievalDeadlineExceeded as e:summary={'seconds':round(time.perf_counter()-start,6),'error':str(e)}
   finally:client.close()
   pair[mode]=summary;print(name,mode,json.dumps(summary),flush=True)
  output['cases']=[c for c in output['cases'] if c['target']!=name]
  output['cases'].append({'target':name,**pair,'scientific_records_identical':len(hashes)==2 and hashes[0]==hashes[1]})
  (OUT/'retrieval_report.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
 # Frozen historic output is reviewed, never regenerated or overwritten.
 baseline=json.loads(Path('devils_advocate/validation/live_gemini_ccr5_report.json').read_text(encoding='utf-8'))
 old=json.loads(Path('devils_advocate/validation/live_gemini_ccr5_sources.json').read_text(encoding='utf-8'))['result']['investigation']
 i=Investigation.model_validate(old);new=evidence_bundle(i,AISettings())
 before={'evidence':baseline['ai']['source_bundle'],'initial_rule_based_assessment':i.conclusion}
 after={'evidence':new,'initial_rule_based_assessment':i.conclusion}
 size=lambda x:len(json.dumps(x,ensure_ascii=False,separators=(',',':')).encode())
 output['initial_packet_bytes']={'before':size(before),'after':size(after),'source_ids_preserved':set(before['evidence']['sources'])<=set(after['evidence']['sources']),
  'note':'Same selected source IDs and clinical counterevidence. Repeated audit/coverage arrays compacted; truncated outcome JSON replaced by complete endpoint-title index, explicitly insufficient to establish efficacy or safety. Full numeric outcomes and audit remain in the saved Investigation.'}
 output['historic_bad_proposal_replay']=check_prior_art(i,Experiment.model_validate(baseline['experiment']))
 (OUT/'retrieval_report.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
 print('SUMMARY',json.dumps({'packet':output['initial_packet_bytes'],'bad_proposal_check':output['historic_bad_proposal_replay']['decision']}),flush=True)
