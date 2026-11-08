"""Lossless whyStopped presence checks. Trial status is never a reason."""
from datetime import datetime, timezone
import re
from .http_client import JsonClient, RetrievalError
from .models import StopReasonEvidence, Trial

CTG = 'https://clinicaltrials.gov/api/v2/studies'

def inspect_stop_reason(record: dict, nct_id: str, *, full_record: bool = False) -> StopReasonEvidence:
    evidence = StopReasonEvidence(source_url=f'{CTG}/{nct_id}',
        checked_at_utc=datetime.now(timezone.utc).isoformat() if full_record else None)
    protocol = record.get('protocolSection')
    if not isinstance(protocol, dict):
        return evidence.model_copy(update={'state': 'invalid', 'detail': 'Missing or invalid protocolSection; field presence cannot be established.'})
    identity = protocol.get('identificationModule')
    if not isinstance(identity, dict) or identity.get('nctId') != nct_id:
        return evidence.model_copy(update={'state': 'invalid', 'detail': 'Full-record identity missing or does not match the requested NCT ID.'})
    status = protocol.get('statusModule')
    if not isinstance(status, dict):
        return evidence.model_copy(update={'state': 'invalid', 'detail': 'statusModule missing or invalid; this is not an absent whyStopped field.'})
    evidence.full_record_checked = full_record
    if 'whyStopped' not in status:
        evidence.state = 'absent'
    elif status['whyStopped'] is None:
        evidence.state = 'null'
    elif not isinstance(status['whyStopped'], str):
        evidence.state = 'invalid'
        evidence.detail = 'whyStopped has an unexpected non-string value.'
    else:
        evidence.value = status['whyStopped']  # Preserve registry wording exactly.
        evidence.state = 'reported' if evidence.value.strip() else 'empty'
    return evidence

def fetch_stop_reason(client: JsonClient, nct_id: str, *, on_record=None) -> StopReasonEvidence:
    if not re.fullmatch(r'NCT\d{8}', nct_id):
        raise ValueError('Expected an NCT identifier with eight digits.')
    url = f'{CTG}/{nct_id}'
    try:
        record = client.get(url)  # Full detail endpoint: no fields projection.
    except RetrievalError as exc:
        return StopReasonEvidence(state='record_missing' if exc.status_code == 404 else 'api_error',
            source_url=url, checked_at_utc=datetime.now(timezone.utc).isoformat(),
            detail='Registry returned HTTP 404; no trial record could be checked.' if exc.status_code == 404 else
                   f'Full registry record could not be fetched ({"HTTP " + str(exc.status_code) if exc.status_code else "connection/response error"}).')
    reason=inspect_stop_reason(record, nct_id, full_record=True)
    if on_record and reason.state!='invalid':on_record(record)
    return reason

def stop_reason_label(trial: Trial) -> str:
    evidence = trial.stop_reason
    if evidence.state == 'reported' and evidence.value is not None:
        return evidence.value
    if evidence.state == 'absent':
        return 'Not reported in registry' if evidence.full_record_checked else 'Field absent from search response; full registry record not verified'
    labels = {'empty': 'Registry stop-reason field is an empty string',
              'null': 'Registry stop-reason field is null',
              'invalid': 'Registry record/stop-reason format could not be validated',
              'record_missing': 'Registry record not found (HTTP 404)',
              'api_error': 'Stop reason unavailable because the full-record API request failed',
              'unverified': 'Stop reason not verified against a full registry record'}
    if evidence.state == 'unverified' and trial.why_stopped:
        return 'Recorded stop reason (full record not rechecked): ' + trial.why_stopped
    return labels[evidence.state]
