"""User-authorized three-case audit: <=5 attempts/case and <=15 aggregate.

Requires explicit --authorized. Existing manifests only poll an existing job;
failed jobs are never repeated automatically. No direct SDK calls in this script.
"""
import argparse,json,time,uuid,requests
from pathlib import Path
ROOT=Path('devils_advocate/validation/cross_disease');BASE='http://127.0.0.1:3001'
HEADERS={'X-Research-Mode':'live'}
SELECTED=['PCSK9','BACE1','preclinical']

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--authorized',action='store_true');args=parser.parse_args()
    assert args.authorized,'Explicit task authorization required.'
    references={r['case']:r for r in json.loads((ROOT/'references.json').read_text())}
    ledger_path=ROOT/'paid_ledger.json'
    ledger=json.loads(ledger_path.read_text()) if ledger_path.exists() else {
        'authorization':'Current cross-disease audit request: up to three cases, five attempts each, fifteen aggregate; do not repeat failed jobs.',
        'max_total':15,'max_per_case':5,'selected_cases':SELECTED,'cases':{}}
    assert ledger['selected_cases']==SELECTED
    for name in SELECTED:
        config=requests.get(BASE+'/api/workbench/config',timeout=20).json()
        assert config['backend']['code_matches_disk'] and config['ai']['enabled'] and config['ai']['max_calls']<=5
        # Independently inspect actual saved coverage from the updated unpaid job.
        audited=json.loads((ROOT/(name+'_verified_sources.json')).read_text(encoding='utf-8'))
        assert audited['result']['provenance']['source_hash']==config['backend']['source_hash'],'Unpaid coverage must use the same current backend code.'
        assert audited['result']['investigation']['coverage']['reasoning_permitted'],name+' coverage inadequate; do not pay.'
        if name not in ledger['cases']:
            item={'idempotency_key':str(uuid.uuid4()),'started_at':time.time(),'backend':config['backend'],
                'configuration':config['ai'],'calls':[],'target_input':references[name]['target_input']}
            ledger['cases'][name]=item;ledger_path.write_text(json.dumps(ledger,indent=2),encoding='utf-8')
            response=requests.post(BASE+'/api/investigations',headers={**HEADERS,'Idempotency-Key':item['idempotency_key']},
                json={'target_input':item['target_input'],'use_ai':True,'paid_authorized':True,'model_call_limit':5},timeout=30)
            response.raise_for_status();item['job_id']=response.json()['job_id']
            ledger_path.write_text(json.dumps(ledger,indent=2),encoding='utf-8')
        item=ledger['cases'][name];assert item.get('job_id'),'Ambiguous submission: inspect SQLite; never automatically submit again.'
        last=None;poll_started=time.monotonic()
        while True:
            r=requests.get(BASE+'/api/investigations/'+item['job_id'],headers=HEADERS,timeout=30);r.raise_for_status();job=r.json()
            calls=job['progress'].get('calls',[])
            if job.get('result'):calls=(job['result']['investigation'].get('ai') or {}).get('calls',calls)
            item['calls']=calls;assert len(calls)<=5
            assert sum(len(v['calls']) for v in ledger['cases'].values())<=15
            ledger_path.write_text(json.dumps(ledger,indent=2),encoding='utf-8')
            state=(job['state'],job['progress']['stage'],len(calls),sum(c['success'] for c in calls))
            if state!=last:print(name,json.dumps({'state':state[0],'stage':state[1],'attempts':state[2],'successful':state[3]}),flush=True);last=state
            if job['state'] in ['completed','failed','cancelled','interrupted']:break
            if time.monotonic()-poll_started>1200:raise RuntimeError('Polling timeout; job retained unchanged, no new job submitted.')
            time.sleep(3)
        item['state']=job['state'];item['finished_at']=job['updated'];item['wall_seconds']=round(job['updated']-item['started_at'],6)
        item['ai_status']=((job.get('result') or {}).get('investigation',{}).get('ai') or {}).get('status')
        ledger_path.write_text(json.dumps(ledger,indent=2),encoding='utf-8')
        (ROOT/(name+'_paid_sources.json')).write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding='utf-8')
        print(name,json.dumps({k:item[k] for k in ['job_id','state','ai_status','wall_seconds']}),flush=True)
