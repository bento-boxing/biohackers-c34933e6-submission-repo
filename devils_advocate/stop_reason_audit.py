"""Explicit full-record audit; no Gemini or Target Scout invocation."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from .http_client import JsonClient
from .stop_reasons import fetch_stop_reason, stop_reason_label
from .trial_retriever import parse_trial

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('nct_ids', nargs='*', default=['NCT02565511'])
    parser.add_argument('--include-recorded-bace1', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).parent
    stored = {}
    if args.include_recorded_bace1:
        for path in [root / 'validation/bace1_sources.json', root / 'fixtures/bace1.json']:
            if path.exists():
                for trial in json.loads(path.read_text(encoding='utf-8')).get('trials', []):
                    stored.setdefault(trial['nct_id'], trial)
    client = JsonClient()
    rows = []
    for nct in dict.fromkeys([*args.nct_ids, *stored]):
        evidence = fetch_stop_reason(client, nct)
        row = {'nct_id': nct, 'registry_url': f'https://clinicaltrials.gov/study/{nct}',
               'stop_reason': evidence.model_dump(mode='json'),
               'stored_parsed_value': stored.get(nct, {}).get('why_stopped')}
        if evidence.state not in ['api_error', 'record_missing', 'invalid']:
            full = client.get(evidence.source_url)  # Cached full response, no new request.
            parsed = parse_trial(full, [])
            row.update(status_module=full['protocolSection']['statusModule'],
                       parsed_value=parsed.why_stopped,
                       present_value_preserved=(parsed.why_stopped == evidence.value) if evidence.state == 'reported' else None)
            parsed.stop_reason = evidence
            row['display'] = stop_reason_label(parsed)
        rows.append(row)
        print(json.dumps({k: v for k, v in row.items() if k != 'status_module'}), flush=True)
    output = {'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'method': 'Full API v2 study endpoint without fields projection; inspect field membership separately from its value.',
              'records': rows}
    path = root / 'validation/stop_reason_audit.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(output, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
