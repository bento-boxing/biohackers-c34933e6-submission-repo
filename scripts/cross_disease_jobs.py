"""Serial public-only investigations via Next proxy; durable no-auto-rerun manifest."""
import json,time,uuid,sqlite3,argparse,requests
from pathlib import Path
ROOT=Path('devils_advocate/validation/cross_disease');BASE='http://127.0.0.1:3001'
HEADERS={'X-Research-Mode':'live'}

def run_case(reference,tag,refresh=False):
    manifest_path=ROOT/(tag+'_manifest.json')
    if manifest_path.exists():
        m=json.loads(manifest_path.read_text());assert m.get('job_id'),'Inspect ambiguous submission; never resubmit automatically.'
    else:
        m={'case':reference['case'],'target_input':reference['target_input'],'started_at':time.time(),'idempotency_key':str(uuid.uuid4()),'paid_calls_authorized':0}
        manifest_path.write_text(json.dumps(m,indent=2),encoding='utf-8')
        r=requests.post(BASE+'/api/investigations',headers={**HEADERS,'Idempotency-Key':m['idempotency_key']},
            json={'target_input':reference['target_input'],'use_ai':False,'paid_authorized':False,'refresh_evidence':refresh},timeout=30)
        r.raise_for_status();m['job_id']=r.json()['job_id'];manifest_path.write_text(json.dumps(m,indent=2),encoding='utf-8')
    last=None;poll=time.monotonic()
    while True:
        r=requests.get(BASE+'/api/investigations/'+m['job_id'],headers=HEADERS,timeout=30);r.raise_for_status();job=r.json()
        state=(job['state'],job['progress']['stage'])
        if state!=last:print(tag,*state,flush=True);last=state
        if job['state'] in ['completed','failed','cancelled','interrupted']:break
        if time.monotonic()-poll>420:raise RuntimeError('Polling timed out; existing job retained, not cancelled.')
        time.sleep(2)
    (ROOT/(tag+'_sources.json')).write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding='utf-8')
    result=job.get('result') or {};i=result.get('investigation') or {};ai=i.get('ai') or {};assert not ai.get('calls')
    with sqlite3.connect('file:devils_advocate/runtime/pathway-validation/workbench.sqlite3?mode=ro',uri=True) as db:
        saved=json.loads(db.execute('SELECT result FROM jobs WHERE id=?',(m['job_id'],)).fetchone()[0] or 'null')
    assert saved==job['result']
    m['finished_at']=job['updated']
    manifest_path.write_text(json.dumps(m,indent=2),encoding='utf-8')
    return {'case':reference['case'],'phase':tag,'job_id':m['job_id'],'state':job['state'],'error':job.get('error'),
        'elapsed_seconds':round(m['finished_at']-m['started_at'],6),'target_input':i.get('target',reference['target_input']),
        'resolved_target_id':i.get('resolved_target_id'),'resolution_status':i.get('resolution_status'),
        'counts':{k:len(i.get(k,[])) for k in ['compounds','trials','publications']},
        'coverage':i.get('coverage'),'association':i.get('association'),'timings':result.get('timings'),
        'provenance':result.get('provenance'),'retrieval_errors':i.get('retrieval_errors'),
        'search_audit':i.get('search_audit'),'paid_calls':0,'sqlite_api_equal':True}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--cases');parser.add_argument('--phase',default='cold');parser.add_argument('--refresh',action='store_true');args=parser.parse_args()
    config=requests.get(BASE+'/api/workbench/config',timeout=30).json();assert config['backend']['code_matches_disk']
    refs=json.loads((ROOT/'references.json').read_text());chosen=args.cases.split(',') if args.cases else None
    path=ROOT/'retrieval_report.json';report=json.loads(path.read_text()) if path.exists() else {'method':'Actual Next proxy -> Flask worker -> SQLite; public only, no model authorization.','cases':[]}
    for reference in refs:
        if chosen and reference['case'] not in chosen:continue
        tag=reference['case']+'_'+args.phase
        record=run_case(reference,tag,refresh=args.refresh)
        if path.exists():report=json.loads(path.read_text())
        report['cases']=[r for r in report['cases'] if r['phase']!=tag]+[record]
        path.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({k:record[k] for k in ['case','phase','state','elapsed_seconds','resolved_target_id','counts','retrieval_errors']}),flush=True)
