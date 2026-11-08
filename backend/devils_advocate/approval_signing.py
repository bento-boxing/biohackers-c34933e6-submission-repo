"""HMAC signatures for researcher approvals.

The stateless server cannot look an approval up later, so the client posts the approval back
when it asks for screening. The signature proves the object came from this server unmodified.
Set WORKBENCH_SECRET in every deployment with more than one process; without it a random
per-process key is used (fine for one local server).
"""
import hashlib
import hmac
import json
import os
import secrets

_PROCESS_KEY = secrets.token_bytes(32)


def signing_key() -> bytes:
    secret = os.environ.get('WORKBENCH_SECRET', '')
    return secret.encode('utf-8') if secret else _PROCESS_KEY


def _canonical(approval: dict) -> bytes:
    return json.dumps({k: v for k, v in approval.items() if k != 'signature'}, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def sign(approval: dict) -> str:
    return hmac.new(signing_key(), _canonical(approval), hashlib.sha256).hexdigest()


def verify(approval: dict) -> bool:
    signature = approval.get('signature')
    if not isinstance(signature, str):
        return False
    return hmac.compare_digest(sign(approval), signature)
