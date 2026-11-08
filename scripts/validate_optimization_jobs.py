"""Public-only Next proxy / production worker / SQLite cold and warm validation.

Requires pathway_validation_server.py on 5051 and Next on 3001. Never enables
or authorizes AI. Existing jobs and source caches are retained untouched.
"""
import json, sqlite3, time, uuid
from pathlib import Path
import requests

URL = 'http://127.0.0.1:3001'
RUNTIME = Path('devils_advocate/runtime/pathway-validation')
OUT = Path('devils_advocate/validation/optimization/job_end_to_end.json')
HEADERS = {'X-Research-Mode': 'live'}

if __name__ == '__main__':
    config = requests.get(URL+'/api/workbench/config', timeout=30).json()
    assert not config['ai']['enabled'] and config['backend']['code_matches_disk']
    cache = RUNTIME/'public-evidence-cache.sqlite3'
    with sqlite3.connect('file:'+cache.as_posix()+'?mode=ro', uri=True) as db:
        initial_entries = db.execute('SELECT count(*) FROM public_responses').fetchone()[0]
    records = []
    for phase in ['first', 'repeat']:
        body = {'target_input': {'disease_name':'HIV infectious disease', 'disease_id':'MONDO_0005109',
            'target_symbol':'CCR5', 'chembl_target_id':'CHEMBL274','target_id':'ENSG00000160791'},
            'use_ai':False, 'paid_authorized':False}
        started = time.perf_counter()
        r = requests.post(URL+'/api/investigations', headers={**HEADERS,'Idempotency-Key':str(uuid.uuid4())}, json=body, timeout=30)
        r.raise_for_status(); identifier = r.json()['job_id']; last = ''
        while True:
            response = requests.get(URL+'/api/investigations/'+identifier, headers=HEADERS, timeout=30)
            response.raise_for_status(); job = response.json()
            stage = job['progress']['stage']
            if stage != last: print(phase, stage, flush=True); last = stage
            if job['state'] in ['completed','failed','cancelled','interrupted']: break
            if time.perf_counter()-started > 400: raise RuntimeError('Polling timed out; job left untouched: '+identifier)
            time.sleep(1)
        assert job['state']=='completed', job.get('error')
        result = job['result']; i = result['investigation']
        assert not i['ai']['calls'] and i['coverage']['reasoning_permitted']
        assert result['provenance']['code_matches_disk']
        with sqlite3.connect('file:'+(RUNTIME/'workbench.sqlite3').as_posix()+'?mode=ro',uri=True) as db:
            saved=json.loads(db.execute('SELECT result FROM jobs WHERE id=?',(identifier,)).fetchone()[0])
        assert saved==result
        profile=result['timings']['retrieval']
        record={'phase':phase,'job_id':identifier,'end_to_end_seconds':round(time.perf_counter()-started,6),
            'retrieval_seconds':profile['total_seconds'],'requests':profile['requests'],
            'cache_hits':profile['cache_hits'],'network_attempts':profile['network_attempts'],
            'trials':len(i['trials']),'publications':len(i['publications']),
            'coverage':i['coverage']['status'],'pathway':i['coverage']['pathway'],
            'sqlite_api_equal':True,'source_provenance_modes':sorted({p.get('provenance','') for p in profile['response_provenance']}),
            'paid_calls':0}
        records.append(record)
        OUT.write_text(json.dumps({'backend':config['backend'],'initial_cache_entries':initial_entries,
            'method':'Fresh Next proxy -> Flask production worker -> SQLite -> Next GET, public-only, AI disabled.',
            'cases':records,'paid_calls':0},indent=2),encoding='utf-8')
        print(json.dumps(record),flush=True)
