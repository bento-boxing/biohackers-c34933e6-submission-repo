"""Explicit live capture; never replace real records with fabricated outcomes."""
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path
from .http_client import JsonClient
from .models import Investigation, TargetInput
from .trial_retriever import resolve_target, retrieve_compounds, parse_trial, CTG
from .devil_advocate import retrieve_publications

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-search', action='store_true', help='Smoke-test full live pipeline instead of writing a fixture')
    args = parser.parse_args()
    client = JsonClient()
    target = TargetInput(disease_name="Alzheimer's disease", target_symbol='BACE1')
    if args.check_search:
        from .devil_advocate import investigate_target
        result = investigate_target(target, client=client)
        print(json.dumps({'target_id': result.resolved_target_id, 'compounds': len(result.compounds),
                          'trials': len(result.trials), 'publications': len(result.publications),
                          'verified_claims': len(result.claims), 'notes': result.retrieval_notes}))
        if not result.trials or not result.publications or not result.compounds:
            raise RuntimeError('Live smoke check incomplete; inspect notes.')
        return
    target_id = resolve_target(client, target)
    if not target_id:
        raise RuntimeError('BACE1 could not be resolved; no fixture written.')
    compounds = retrieve_compounds(client, target_id)
    trials = [parse_trial(client.get(f'{CTG}/{nct}'), compounds)
              for nct in ['NCT01739348', 'NCT01953601']]
    publications = retrieve_publications(client, target, compounds)
    result = Investigation(target=target, mode='offline', resolved_target_id=target_id,
        compounds=compounds, trials=trials, publications=publications,
        retrieval_notes=[f'Recorded live API example captured {datetime.now(timezone.utc).isoformat()}.',
                         'Selected BACE1 example: two registry records, not exhaustive. Outcomes are not inferred from status.'])
    data = result.model_dump(mode='json', exclude={'target', 'mode', 'claims', 'revisions', 'conclusion'})
    (Path(__file__).parent / 'fixtures' / 'bace1.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
    print(f'Captured {len(compounds)} compounds, {len(trials)} trials, {len(publications)} publications.')

if __name__ == '__main__':
    main()
