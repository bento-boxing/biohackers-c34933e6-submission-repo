"""Isolated production Flask factory/worker with public APIs and paid AI disabled.

Copies existing Scout run context read-only; never touches original jobs.
"""
import os,sys,json,sqlite3
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['AI_ENABLED']='false'
from devils_advocate import server

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    runtime=root/'devils_advocate/runtime/pathway-validation'
    server.ORIGINS.append('http://127.0.0.1:3001')
    app=server.create_app(runtime)
    original=root/'devils_advocate/runtime/workbench.sqlite3'
    db=sqlite3.connect('file:'+original.as_posix()+'?mode=ro',uri=True)
    seeded={}
    for payload, in db.execute('SELECT payload FROM jobs ORDER BY created DESC'):
        p=json.loads(payload);selection=p.get('selection',{});symbol=selection.get('target_input',{}).get('target_symbol')
        if symbol not in ['CCR5','BCL2'] or symbol in seeded or not selection.get('run_id'):continue
        row=db.execute('SELECT mode,data FROM scout_runs WHERE id=?',(selection['run_id'],)).fetchone()
        if row:
            app.config['STORE'].save_run(selection['run_id'],row[0],json.loads(row[1]))
            seeded[symbol]={'run_id':selection['run_id'],'target_input':selection['target_input']}
    db.close()
    (runtime/'seeded-runs.json').write_text(json.dumps(seeded,indent=2),encoding='utf-8')
    print('Production factory + worker; public live sources; AI_ENABLED=false; original DB read-only.',flush=True)
    app.run(host='127.0.0.1',port=5051,debug=False,use_reloader=False,threaded=True)
