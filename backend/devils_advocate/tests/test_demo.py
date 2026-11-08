from pathlib import Path
from streamlit.testing.v1 import AppTest

def test_offline_demo_end_to_end():
    app = AppTest.from_file(str(Path(__file__).parents[1] / 'demo_app.py')).run()
    assert not app.exception
    app.button[0].click().run(timeout=30)
    assert not app.exception
    assert 'result' in app.session_state
    assert app.session_state['result']['mode'] == 'offline'
    assert len(app.radio) == 1
