"""Reproducible opt-in real API checks; not part of offline pytest."""
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path
from .devil_advocate import investigate_target
from .http_client import JsonClient
from .http_client import RetrievalError
from .target_scout_adapter import validate_target_scout
from .relevance import disease_matches, mentions

CASES = [
    ("Alzheimer's disease", 'BACE1'),
    ("Parkinson's disease", 'LRRK2'),
    ('Hypercholesterolemia', 'PCSK9'),
    ('Non-small-cell lung cancer', 'EGFR'),
    ("Alzheimer's disease", 'FAKEGENE123'),
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--metadata-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).parent / 'validation'
    root.mkdir(exist_ok=True)
    client = JsonClient()
    try:
        metadata = {'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
                    'chembl_status': client.get('https://www.ebi.ac.uk/chembl/api/data/status.json'),
                    'sources': ['https://www.ebi.ac.uk/chembl/', 'https://clinicaltrials.gov/about-site/terms-conditions', 'https://europepmc.org/Copyright']}
    except RetrievalError as exc:
        metadata = {'error': str(exc)}
    (root / 'source_metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    if args.metadata_only:
        print(json.dumps(metadata, indent=2))
        return
    results = []
    for disease, symbol in CASES:
        investigation = investigate_target({'disease_name': disease, 'target_symbol': symbol}, client=client)
        row = {'disease': disease, 'target': symbol, 'resolved_target_id': investigation.resolved_target_id,
               'compounds': len(investigation.compounds), 'trials': len(investigation.trials),
               'publications': len(investigation.publications),
               'exact_compound_and_disease_trials': sum(t.relationship == 'verified' and t.disease_match == 'matched' for t in investigation.trials),
               'trials_with_posted_outcomes': sum(bool(t.outcome_records) for t in investigation.trials),
               'explicit_target_or_compound_and_disease_publications': sum(
                   disease_matches(p.title + ' ' + p.abstract, disease) and any(
                       mentions(p.title + ' ' + p.abstract, term) for term in [symbol, *[c.name for c in investigation.compounds]])
                   for p in investigation.publications),
               'errors': investigation.retrieval_errors, 'notes': investigation.retrieval_notes,
               'missing_information': investigation.missing_information,
               'trial_samples': [t.model_dump(mode='json', exclude={'outcome_records', 'population'}) for t in investigation.trials[:3]],
               'publication_samples': [p.model_dump(mode='json', exclude={'abstract'}) for p in investigation.publications[:3]]}
        # Retain source records once for shared-evidence evaluation. Source rights
        # remain separate from the application code; see README attribution notes.
        (root / f'{symbol.lower()}_sources.json').write_text(investigation.model_dump_json(indent=2,
            exclude={'claims', 'revisions', 'assessments'}), encoding='utf-8')
        results.append(row)
        print(json.dumps({k: v for k, v in row.items() if k not in ['trial_samples', 'publication_samples', 'missing_information', 'notes']}), flush=True)
    payload = json.loads((Path(__file__).parent / 'fixtures' / 'target_scout_lrrk2.json').read_text(encoding='utf-8'))
    handoff = validate_target_scout(payload, client=client)
    report = {'captured_at_utc': datetime.now(timezone.utc).isoformat(), 'cases': results,
              'target_scout_handoff': handoff.model_dump(mode='json'),
              'interpretation': 'Applicability counts are lexical checks, not expert confirmation of scientific relevance or target failure.'}
    (root / 'live_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
