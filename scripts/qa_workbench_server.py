"""Isolated offline-only browser-test backend; never uses the user's runtime DB."""
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['AI_ENABLED']='false'
from devils_advocate import server

if __name__=='__main__':
    server.ORIGINS.append('http://127.0.0.1:3001')
    with tempfile.TemporaryDirectory(prefix='agentverse-qa-') as directory:
        app=server.create_app(Path(directory))
        app.run(host='127.0.0.1',port=5051,debug=False,use_reloader=False,threaded=True)
