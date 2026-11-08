"""Isolated production factory for explicitly authorized audit jobs only."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['AI_ENABLED']='true'
from devils_advocate import server

if __name__=='__main__':
    server.ORIGINS.append('http://127.0.0.1:3001')
    app=server.create_app(Path('devils_advocate/runtime/pathway-validation'))
    print('Isolated audit backend; paid requests still require per-job authorization; original runtime untouched.',flush=True)
    app.run(host='127.0.0.1',port=5051,debug=False,use_reloader=False,threaded=True)
