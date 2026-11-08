from devils_advocate import approval_signing as signing


def test_sign_verify_round_trip_and_tamper_detection(monkeypatch):
    monkeypatch.setenv('WORKBENCH_SECRET', 'test-secret')
    approval = {'ts': '2026-11-08T00:00:00Z', 'symbol': 'LRRK2', 'scores': {'total': 0.5}}
    signed = {**approval, 'signature': signing.sign(approval)}
    assert signing.verify(signed)
    assert not signing.verify({**signed, 'symbol': 'SNCA'})
    assert not signing.verify({**approval, 'signature': 'deadbeef'})
    assert not signing.verify(approval)  # no signature at all


def test_secret_changes_signature(monkeypatch):
    approval = {'ts': 't', 'symbol': 'X'}
    monkeypatch.setenv('WORKBENCH_SECRET', 'one'); a = signing.sign(approval)
    monkeypatch.setenv('WORKBENCH_SECRET', 'two'); b = signing.sign(approval)
    assert a != b
