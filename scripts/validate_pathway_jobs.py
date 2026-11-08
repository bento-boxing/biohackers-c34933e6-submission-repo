"""Opt-in fresh Next proxy → Flask job → worker → SQLite → API validation.

Requires pathway_validation_server.py and Next on localhost:3001. Public API
traffic only. This never requests or authorizes Gemini.
"""
import json,time,uuid,requests,sqlite3
from pathlib import Path

if __name__=='__main__':
    runtime=Path('devils_advocate/runtime/pathway-validation')
    seeds=json.loads((runtime/'seeded-runs.json').read_text())
    url='http://127.0.0.1:3001'
    config=requests.get(url+'/api/workbench/config',timeout=10).json()
    assert config['ai']['enabled'] is False,'Paid AI must be disabled in validation process.'
    assert config['backend']['code_matches_disk'],'Validation process must load latest code.'
    results=[]
    cases=[(symbol,{'run_id':seeds[symbol]['run_id'],'symbol':symbol}) for symbol in ['CCR5','BCL2']]
    cases.append(('unsupported',{'target_input':{'target_symbol':'BCL2','chembl_target_id':'CHEMBL4860','disease_name':'Invented unsupported condition ZXQ987'}}))
    for name,selection in cases:
        start=time.perf_counter()
        headers={'X-Research-Mode':'live','Idempotency-Key':str(uuid.uuid4())}
        response=requests.post(url+'/api/investigations',headers=headers,json={**selection,'use_ai':False,'paid_authorized':False},timeout=15)
        response.raise_for_status();job_id=response.json()['job_id']
        last=''
        while True:
            item=requests.get(url+'/api/investigations/'+job_id,headers={'X-Research-Mode':'live'},timeout=15).json()
            stage=item['progress']['stage']
            if stage!=last:print(name,stage,flush=True);last=stage
            if item['state'] in ['completed','failed','cancelled','interrupted']:break
            if time.perf_counter()-start>400:raise RuntimeError('Validation polling timed out; job left untouched: '+job_id)
            time.sleep(2)
        elapsed=time.perf_counter()-start
        assert item['state']=='completed',item.get('error')
        i=item['result']['investigation'];assert not i['ai']['calls']
        db=sqlite3.connect('file:'+str(runtime/'workbench.sqlite3').replace('\\','/')+'?mode=ro',uri=True)
        stored=json.loads(db.execute('SELECT result FROM jobs WHERE id=?',(job_id,)).fetchone()[0]);db.close()
        assert stored==item['result'],'API and persisted report differ.'
        assert item['result']['provenance']['source_counts']['publications']==len(i['publications'])
        packet_ids=i['coverage']['selected_source_ids']
        result={'case':name,'job_id':job_id,'seconds':round(elapsed,6),'trials':len(i['trials']),
            'publications':len(i['publications']),'compound_count':len(i['compounds']),
            'coverage':i['coverage']['status'],'pathway':i['coverage']['pathway'],'gaps':i['coverage']['gaps'],
            'reasoning_permitted':i['coverage']['reasoning_permitted'],'association':i['association'],
            'selected':packet_ids,'positive':[p['identifier'] for p in i['publications'] if 'positive_candidate' in p['direction_signals']],
            'negative':[p['identifier'] for p in i['publications'] if 'negative_candidate' in p['direction_signals']],
            'api_persistence_equal':True,'ai_status':i['ai']['status'],'paid_calls':0,'provenance':item['result']['provenance']}
        results.append(result)
        (runtime/(name+'-report.json')).write_text(json.dumps(item,ensure_ascii=False,indent=2),encoding='utf-8')
        output={'method':'Fresh Next.js proxy / Flask production job endpoint, production worker, real public API retrieval, SQLite roundtrip. AI disabled; no mocks.',
                'backend':config['backend'],'cases':results,'paid_calls':0}
        Path('devils_advocate/validation/pathway_end_to_end.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
        print(json.dumps(result),flush=True)
