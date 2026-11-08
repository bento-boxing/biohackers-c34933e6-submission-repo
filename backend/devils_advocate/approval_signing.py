"""Signed tokens for data the stateless server must trust when a client posts it back.

A token is `base64url(json payload) + '.' + hmac_sha256_hex`. Verification decodes the exact
signed bytes, so a browser re-serialising the JSON (1.0 → 1, reordered keys) cannot break it,
and whatever fields are posted next to the token are ignored: the token's payload is authoritative.

Set WORKBENCH_SECRET wherever more than one process may answer requests (Vercel). Without it a
random per-process key is used, which is fine for one local server and refused on Vercel.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets

_PROCESS_KEY = secrets.token_bytes(32)


def configured() -> bool:
    """False when running on Vercel without a shared secret (instances would disagree)."""
    return bool(os.environ.get('WORKBENCH_SECRET')) or not os.environ.get('VERCEL')


def signing_key() -> bytes:
    secret = os.environ.get('WORKBENCH_SECRET', '')
    return secret.encode('utf-8') if secret else _PROCESS_KEY


def _mac(body: bytes) -> str:
    return hmac.new(signing_key(), body, hashlib.sha256).hexdigest()


def sign_payload(payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return base64.urlsafe_b64encode(body).decode('ascii').rstrip('=') + '.' + _mac(body)


def verify_token(token) -> dict | None:
    if not isinstance(token, str) or token.count('.') != 1:
        return None
    encoded, mac = token.split('.')
    try:
        body = base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4))
    except (ValueError, TypeError):
        return None
    if not hmac.compare_digest(_mac(body), mac):
        return None
    try:
        payload = json.loads(body)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def sign(record: dict) -> str:
    """Token over every field of `record` except 'signature'."""
    return sign_payload({k: v for k, v in record.items() if k != 'signature'})


def verify(record: dict) -> dict | None:
    """The signed payload carried by record['signature'], or None if absent or tampered."""
    return verify_token(record.get('signature')) if isinstance(record, dict) else None
