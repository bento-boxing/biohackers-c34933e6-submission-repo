import json

from devils_advocate import approval_signing as signing


def browser_round_trip(obj):
    """What a browser does to our JSON: 1.0 becomes 1, key order may change."""
    return json.loads(json.dumps(obj), parse_float=lambda s: int(float(s)) if float(s).is_integer() else float(s))


def test_token_round_trip_survives_browser_json(monkeypatch):
    monkeypatch.setenv('WORKBENCH_SECRET', 'test-secret')
    approval = {'ts': '2026-11-08T00:00:00Z', 'symbol': 'LRRK2', 'scores': {'total': 0.5, 'literature': 1.0, 'genetic': 0.0}}
    signed = {**approval, 'signature': signing.sign(approval)}
    posted = browser_round_trip(signed)
    payload = signing.verify(posted)
    assert payload is not None and payload['scores']['literature'] == 1.0 and payload['symbol'] == 'LRRK2'


def test_tampered_or_missing_token_is_rejected(monkeypatch):
    monkeypatch.setenv('WORKBENCH_SECRET', 'test-secret')
    approval = {'ts': 't', 'symbol': 'LRRK2'}
    token = signing.sign(approval)
    body, mac = token.split('.')
    assert signing.verify({'signature': body + '.' + 'deadbeef' * 8}) is None
    assert signing.verify({'signature': 'bm90anNvbg.' + mac}) is None
    assert signing.verify({'signature': 'garbage'}) is None
    assert signing.verify(approval) is None
    # fields posted alongside the token are ignored: the token's payload is authoritative
    assert signing.verify({'symbol': 'SNCA', 'signature': token})['symbol'] == 'LRRK2'


def test_secret_changes_signature(monkeypatch):
    approval = {'ts': 't', 'symbol': 'X'}
    monkeypatch.setenv('WORKBENCH_SECRET', 'one'); a = signing.sign(approval)
    monkeypatch.setenv('WORKBENCH_SECRET', 'two'); b = signing.sign(approval)
    assert a != b and signing.verify({'signature': a}) is None


def test_secret_is_required_on_vercel(monkeypatch):
    monkeypatch.delenv('WORKBENCH_SECRET', raising=False)
    monkeypatch.setenv('VERCEL', '1')
    assert not signing.configured()
    monkeypatch.delenv('VERCEL')
    assert signing.configured()  # local single process: random key is fine
