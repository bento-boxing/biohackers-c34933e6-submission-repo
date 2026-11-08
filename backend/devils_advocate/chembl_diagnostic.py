"""Explicit public endpoint diagnostic; no paid model calls."""
import json
from pathlib import Path
import requests

def main():
    rows = []
    for url, params in [('https://www.ebi.ac.uk/chembl/api/data/target/search.json', {'q': 'BACE1', 'limit': 30}),
                        ('https://www.ebi.ac.uk/chembl/api/data/target/CHEMBL4822.json', None)]:
        row = {'url': url, 'status': None}
        try:
            response = requests.get(url, params=params, timeout=(5, 25))
            row.update(url=response.url, status=response.status_code, content_type=response.headers.get('Content-Type'))
            data = response.json()
            row.update(response_count=len(data.get('targets', [])) if 'targets' in data else 1,
                       record=data if 'targets' not in data else None,
                       exact_target_ids=[t['target_chembl_id'] for t in data.get('targets', [])])
        except (requests.RequestException, ValueError) as exc:
            row['error_type'] = type(exc).__name__
        rows.append(row)
    path = Path(__file__).parent / 'validation/chembl_diagnostic.json'
    path.write_text(json.dumps(rows, indent=2), encoding='utf-8')
    print(json.dumps([{k:v for k,v in r.items() if k != 'record'} for r in rows], indent=2))

if __name__ == '__main__':
    main()
