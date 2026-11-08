"""One explicitly authorized job; durable idempotency, never an automatic rerun.

Authorized in conversation: HIV/CCR5, at most five total Gemini attempts.
Existing manifest resumes polling only. No SDK calls are made by this script.
"""
import json,time,uuid,sqlite3
from datetime import datetime,timezone
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'devils_advocate/validation'
MANIFEST=OUT/'live_gemini_ccr5_manifest.json'
BASE='http://127.0.0.1:5050'

if __name__=='__main__':
    config=requests.get(BASE+'/api/workbench/config',timeout=10).json()
    assert config['backend']['code_matches_disk'],'Backend must load latest source.'
    assert config['ai']['enabled'] and config['ai']['max_calls']<=5,'Authorization ceiling is five.'
    started=time.perf_counter()
    if MANIFEST.exists():
        manifest=json.loads(MANIFEST.read_text())
        if not manifest.get('job_id'):
            raise RuntimeError('A submission manifest exists without a confirmed job ID; inspect SQLite by idempotency key. Do not submit again.')
    else:
        previous=OUT/'live_gemini_ccr5_initial_sources.json'
        previous_job=None
        if previous.exists():
            previous_job=json.loads(previous.read_text(encoding='utf-8'))
            assert not previous_job['result']['investigation']['ai']['calls'],'A replacement may not reset a consumed paid budget.'
        db=sqlite3.connect('file:'+(ROOT/'devils_advocate/runtime/workbench.sqlite3').as_posix()+'?mode=ro',uri=True)
        assert not db.execute("SELECT 1 FROM jobs WHERE state IN ('running','queued','cancel_requested')").fetchone(),'Do not overlap an existing job.'
        selection=None
        for raw, in db.execute('SELECT payload FROM jobs ORDER BY created DESC'):
            s=json.loads(raw).get('selection',{})
            if s.get('target_input',{}).get('target_symbol')=='CCR5' and s.get('run_id'):
                selection=s;break
        db.close();assert selection,'Existing verified Scout context required.'
        manifest={'idempotency_key':str(uuid.uuid4()),'started_at':time.time(),
                  'authorized_max_calls':5,'backend':config['backend'],'ai':config['ai'],
                  'authorization':'Explicit user authorization for one fresh HIV/CCR5 investigation, up to five model attempts.'}
        if previous_job:
            manifest['previous_job_id']=previous_job['job_id']
            manifest['previous_paid_attempts']=0
            manifest['authorization']='User explicitly authorized one replacement after ChEMBL HTTP 500; five total attempts across both jobs.'
        MANIFEST.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        response=requests.post(BASE+'/api/investigations',headers={'X-Research-Mode':'live','Idempotency-Key':manifest['idempotency_key']},
            json={'run_id':selection['run_id'],'symbol':'CCR5','use_ai':True,'paid_authorized':True},timeout=15)
        response.raise_for_status();manifest['job_id']=response.json()['job_id']
        MANIFEST.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        print('SUBMITTED',manifest['job_id'],'ceiling: 5 attempts',flush=True)
    last=''
    while True:
        job=requests.get(BASE+'/api/investigations/'+manifest['job_id'],headers={'X-Research-Mode':'live'},timeout=15).json()
        progress=job.get('progress',{});calls=progress.get('calls',[])
        assert len(calls)<=5,'Backend exceeded authorization; do not request any more calls.'
        state=(job['state'],progress.get('stage'),len(calls),sum(c['success'] for c in calls))
        if state!=last:
            print(json.dumps({'state':state[0],'stage':state[1],'attempts':state[2],'completed':state[3],
                              'observed_seconds':round(time.time()-manifest['started_at'],2)}),flush=True);last=state
        if job['state'] in ['completed','failed','cancelled','interrupted']:break
        if time.perf_counter()-started>1200:
            raise RuntimeError('Polling stopped; existing job left untouched. Resume this script using its manifest, never create another job.')
        time.sleep(3)
    finished=time.time()
    manifest['finished_at']=finished;manifest['wall_seconds']=round(finished-manifest['started_at'],6)
    MANIFEST.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (OUT/'live_gemini_ccr5_sources.json').write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding='utf-8')
    i=(job.get('result') or {}).get('investigation') or {};ai=i.get('ai') or {}
    summary={'job_id':manifest['job_id'],'state':job['state'],'error':job.get('error'),'wall_seconds':manifest['wall_seconds'],
        'coverage':i.get('coverage'),'timings':(job.get('result') or {}).get('timings'),'provenance':(job.get('result') or {}).get('provenance'),
        'retrieved':{k:len(i.get(k,[])) for k in ['compounds','trials','publications']},'ai':ai,
        'experiment':(job.get('result') or {}).get('experiment'),
        'note':'Technical completion only; scientific review is recorded separately. No automatic retry/new job is authorized.'}
    (OUT/'live_gemini_ccr5_report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'job_id':manifest['job_id'],'state':job['state'],'ai_status':ai.get('status'),
        'attempts':len(ai.get('calls',calls)),'wall_seconds':manifest['wall_seconds'],'warnings':ai.get('warnings')}),flush=True)
