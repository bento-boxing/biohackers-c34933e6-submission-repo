"""Score human-labelled cases; baseline uses the identical frozen source bundle.

No baseline is silently simulated and no model performance is precomputed.
"""
import argparse
import json
from pathlib import Path

BASELINE_PROMPT = '''Using only the attached investigation sources, return JSON with
an items list containing id, concern (efficacy/safety/operational/unknown/other),
relevant_failure (boolean), unsupported (boolean). Do not infer target invalidity
from a trial status. Assess each labelled case independently. No outside sources.'''

def prepare_evaluation(investigation, candidate_claims=None) -> dict:
    """Freeze evidence once for both systems; include adversarial claims if supplied.

    Human labels must be independent of these predictions. A relevant failure is
    conservatively flagged only for an explicit concern and exact compound link.
    """
    from .models import Investigation
    from .devil_advocate import classify_concern
    from .evidence_verifier import verify_claims
    result = Investigation.model_validate(investigation)
    cases, predictions = [], []
    for trial in result.trials:
        identifier = trial.nct_id + ':outcome'
        category = classify_concern(trial.why_stopped)
        cases.append({'id': identifier, 'type': 'trial_outcome', 'source_id': trial.nct_id})
        predictions.append({'id': identifier, 'concern': category,
            'relevant_failure': category in ['efficacy', 'safety'] and trial.relationship == 'verified',
            'unsupported': not bool(trial.why_stopped)})
    candidates = candidate_claims if candidate_claims is not None else result.claims
    for claim in candidates:
        accepted, revisions = verify_claims(result, [claim])
        identifier = claim.claim_id + ':support'
        cases.append({'id': identifier, 'type': 'claim_support', 'claim': claim.model_dump(mode='json')})
        predictions.append({'id': identifier, 'concern': claim.concern, 'relevant_failure': False,
                            'unsupported': not accepted or bool(revisions)})
    return {'prompt': BASELINE_PROMPT, 'sources': result.model_dump(mode='json', exclude={'claims', 'revisions', 'conclusion'}),
            'cases': cases, 'system_predictions': predictions}

def score(labels: list[dict], predictions: list[dict]) -> dict:
    expected = {x['id']: x for x in labels}
    supplied = {x['id']: x for x in predictions}
    fields = ['concern', 'relevant_failure', 'unsupported']
    return {'cases': len(expected), 'missing_predictions': len(expected.keys() - supplied.keys()),
            **{f'{field}_accuracy': sum(supplied.get(k, {}).get(field) == v[field]
                                        for k, v in expected.items()) / len(expected)
               if expected else None for field in fields}}

def main():
    parser = argparse.ArgumentParser(description='Evaluate actual submitted predictions against human labels.')
    parser.add_argument('labels', type=Path)
    parser.add_argument('system_predictions', type=Path)
    parser.add_argument('baseline_predictions', type=Path)
    args = parser.parse_args()
    read = lambda p: json.loads(p.read_text(encoding='utf-8'))
    print(json.dumps({'system': score(read(args.labels), read(args.system_predictions)),
                      'single_llm': score(read(args.labels), read(args.baseline_predictions))}, indent=2))

if __name__ == '__main__':
    main()
