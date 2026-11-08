"""Cross-disease regression benchmark for the adaptive evidence loop.

Runs every rubric case through the real HTTP path (Next.js proxy → Flask → SQLite source cache)
with follow-up disabled (baseline) and enabled (adaptive), then scores identity, routing, need
coverage, reference-record recall, packet inclusion, abstention and timing. Reference records are
an EVALUATION RUBRIC only: nothing here is read by production code. Zero paid model calls.

    python -m devils_advocate.adaptive_benchmark --base http://127.0.0.1:3002 --out validation/adaptive
"""
import argparse
import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent
PMC = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search'


def load_rubric(path: Path | None = None) -> dict:
    return json.loads((path or ROOT / 'validation' / 'adaptive' / 'rubric.json').read_text(encoding='utf-8'))


def verify_reference(pmid: str) -> dict:
    """Independent landmark lookup for the rubric (never injected into retrieval)."""
    try:
        data = requests.get(PMC, params={'query': f'EXT_ID:{pmid} AND SRC:MED', 'format': 'json', 'pageSize': 1}, timeout=30).json()
        rows = data.get('resultList', {}).get('result', [])
        return {'pmid': pmid, 'exists': bool(rows), 'title': rows[0].get('title', '') if rows else '', 'date': rows[0].get('firstPublicationDate') if rows else None}
    except Exception as exc:  # noqa: BLE001 - evaluation helper
        return {'pmid': pmid, 'exists': None, 'error': type(exc).__name__}


def investigate(base: str, target_input: dict, *, rounds: int | None, refresh: bool, timeout: int = 320) -> dict:
    body = {'target_input': target_input, 'refresh_evidence': refresh}
    if rounds is not None:
        body['max_followup_rounds'] = rounds
    started = time.monotonic()
    response = requests.post(base.rstrip('/') + '/api/investigations', json=body, headers={'X-Research-Mode': 'live'}, timeout=timeout)
    wall = round(time.monotonic() - started, 3)
    try:
        job = response.json()
    except ValueError:
        job = {'state': 'failed', 'error': f'HTTP {response.status_code} non-JSON', 'result': None}
    job['http_status'] = response.status_code
    job['wall_seconds'] = wall
    return job


def score(case: dict, job: dict) -> dict:
    out = {'case': case['name'], 'state': job.get('state'), 'http_status': job.get('http_status'), 'wall_seconds': job.get('wall_seconds'), 'error': job.get('error')}
    result = job.get('result') or {}
    inv = result.get('investigation') or {}
    if not inv:
        return out
    plan = inv.get('evidence_plan') or {}
    coverage = inv.get('coverage') or {}
    pubs = {p['identifier'] for p in inv.get('publications', [])}
    selected = set(coverage.get('selected_source_ids', []))
    references = case.get('reference_pmids', [])
    found = [f'MED:{p}' for p in references if f'MED:{p}' in pubs]
    in_packet = [i for i in found if i in selected]
    timings = (result.get('timings') or {})
    retrieval = timings.get('retrieval') or {}
    needs = {n['key']: n['status'] for n in plan.get('needs', [])}
    expected_needs = case.get('expected_needs', {})
    experiment = result.get('experiment') or {}
    out.update({
        'identity': {'resolved_chembl': inv.get('resolved_target_id'), 'resolution_status': inv.get('resolution_status'),
                     'ensembl': inv['target'].get('target_id'), 'disease_id': inv['target'].get('disease_id'),
                     'expected_chembl': case.get('expected_chembl'), 'chembl_ok': (case.get('expected_chembl') is None) or inv.get('resolved_target_id') == case.get('expected_chembl')},
        'pathway': coverage.get('pathway'), 'expected_pathway': case.get('expected_pathway'),
        'pathway_ok': case.get('expected_pathway') is None or coverage.get('pathway') == case.get('expected_pathway'),
        'coverage_status': coverage.get('status'), 'coverage_gaps': coverage.get('gaps', []),
        'plan': {'stage': plan.get('stage'), 'stop_reason': plan.get('stop_reason'), 'rounds': len(plan.get('rounds', [])),
                 'searches': sum(len(r['searches']) for r in plan.get('rounds', [])),
                 'failed_searches': sum(1 for r in plan.get('rounds', []) for s in r['searches'] if s['state'] == 'failed'),
                 'new_evidence': sum(len(r['new_evidence_ids']) for r in plan.get('rounds', [])),
                 'needs': needs, 'open_needs': [k for k, v in needs.items() if v in ['unmet', 'partial', 'unverifiable'] and k != 'unresolved_uncertainty'],
                 'expected_needs_ok': {k: needs.get(k) in v for k, v in expected_needs.items()}, 'limitations': plan.get('limitations', [])},
        'sources': {'trials': len(inv.get('trials', [])), 'publications': len(pubs), 'compounds': len(inv.get('compounds', [])),
                    'followup_publications': sum(1 for p in inv.get('publications', []) if p.get('discovered_by', 'initial retrieval') != 'initial retrieval'),
                    'dated_publications': sum(1 for p in inv.get('publications', []) if p.get('publication_date')),
                    'recent_direct': sorted((p['identifier'], p.get('publication_date')) for p in inv.get('publications', []) if (p.get('publication_date') or '') >= case.get('recent_cutoff', '2023-11-08') and p.get('evidence_scope') in ['direct_clinical', 'direct_biological'])[:8]},
        'references': {'rubric': references, 'retrieved': found, 'in_packet': in_packet, 'missed': [p for p in references if f'MED:{p}' not in pubs],
                       'recall': round(len(found) / len(references), 3) if references else None},
        'packet': {'selected': len(selected), 'omitted': len(coverage.get('omitted_source_ids', [])),
                   'material_included': (coverage.get('facets', {}).get('evidence_plan') or {}).get('material_included', []),
                   'material_omitted': (coverage.get('facets', {}).get('evidence_plan') or {}).get('material_omitted', [])},
        'abstention': {'experiment_status': experiment.get('status'), 'expected_abstain': case.get('expected_abstain'),
                       'abstained': experiment.get('status') == 'INSUFFICIENT EVIDENCE FOR EXPERIMENT',
                       'reasoning_permitted': coverage.get('reasoning_permitted')},
        'claims': {'verified': sum(1 for c in inv.get('claims', []) if c.get('verified')),
                   'unverified_supporting': sum(1 for c in inv.get('claims', []) if c.get('stance') == 'supporting' and not c.get('verified'))},
        'timing': {'retrieval_seconds': retrieval.get('total_seconds'), 'requests': retrieval.get('requests'), 'cache_hits': retrieval.get('cache_hits'),
                   'network_attempts': retrieval.get('network_attempts'), 'source_seconds': retrieval.get('source_seconds'), 'stages': timings.get('stages')},
        'retrieval_errors': inv.get('retrieval_errors', []),
    })
    abstain_expected = case.get('expected_abstain')
    out['abstention']['ok'] = abstain_expected is None or out['abstention']['abstained'] == abstain_expected
    return out


def run(base: str, out_dir: Path, rubric: dict, *, modes=('baseline', 'adaptive_cold', 'adaptive_warm'), cases=None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {'base': base, 'started_at': time.time(), 'paid_calls': 0, 'modes': list(modes), 'cases': [],
              'reference_checks': {}, 'caution': rubric.get('caution', '')}
    for case in rubric['cases']:
        if cases and case['name'] not in cases:
            continue
        refs = {pmid: verify_reference(pmid) for pmid in case.get('reference_pmids', [])}
        report['reference_checks'][case['name']] = refs
        row = {'name': case['name'], 'held_out': case.get('held_out', False), 'target_input': case['target_input'], 'runs': {}}
        for mode in modes:
            rounds = 0 if mode == 'baseline' else None
            refresh = mode in ['baseline', 'adaptive_cold']
            job = investigate(base, case['target_input'], rounds=rounds, refresh=refresh)
            scored = score(case, job)
            scored['mode'] = mode
            row['runs'][mode] = scored
            (out_dir / f"{case['name']}_{mode}.json").write_text(json.dumps(job, indent=1), encoding='utf-8')
            print(f"{case['name']:<14}{mode:<14}state={scored['state']} wall={scored['wall_seconds']}s "
                  f"retrieval={scored.get('timing', {}).get('retrieval_seconds')} pubs={scored.get('sources', {}).get('publications')} "
                  f"recall={scored.get('references', {}).get('recall')} open={scored.get('plan', {}).get('open_needs')} stop={scored.get('plan', {}).get('stop_reason')}", flush=True)
        report['cases'].append(row)
    report['finished_at'] = time.time()
    (out_dir / 'benchmark_report.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
    (out_dir / 'benchmark_summary.md').write_text(summary_table(report), encoding='utf-8')
    return report


def summary_table(report: dict) -> str:
    lines = ['| Case | Mode | State | ChEMBL ok | Pathway | Plan stage · stop | Rounds/searches/new | Open needs | Ref recall (packet) | Pubs/trials | Retrieval s | Requests (cache) | Abstain ok |', '|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for row in report['cases']:
        for mode, s in row['runs'].items():
            if 'plan' not in s:
                lines.append(f"| {row['name']} | {mode} | {s.get('state')} | – | – | – | – | – | – | – | – | – | error: {s.get('error')} |")
                continue
            p, r, t = s['plan'], s['references'], s['timing']
            lines.append(f"| {row['name']}{' (held-out)' if row.get('held_out') else ''} | {mode} | {s['state']} | {s['identity']['chembl_ok']} | {s['pathway']} | {p['stage']} · {p['stop_reason']} | {p['rounds']}/{p['searches']}/{p['new_evidence']} | {', '.join(p['open_needs']) or 'none'} | {r['recall']} ({len(r['in_packet'])}/{len(r['retrieved'])}) | {s['sources']['publications']}/{s['sources']['trials']} | {t['retrieval_seconds']} | {t['requests']} ({t['cache_hits']}) | {s['abstention']['ok']} |")
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:3002')
    parser.add_argument('--out', default=str(ROOT / 'validation' / 'adaptive'))
    parser.add_argument('--rubric', default=None)
    parser.add_argument('--modes', default='baseline,adaptive_cold,adaptive_warm')
    parser.add_argument('--cases', default='')
    args = parser.parse_args()
    rubric = load_rubric(Path(args.rubric) if args.rubric else None)
    run(args.base, Path(args.out), rubric, modes=tuple(args.modes.split(',')), cases=[c for c in args.cases.split(',') if c])


if __name__ == '__main__':
    main()
