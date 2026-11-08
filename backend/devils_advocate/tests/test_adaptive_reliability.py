"""End-to-end reliability through the production Flask app with a scripted public-source transport.

Simulates transient API failures, missing publications, incomplete trial records, stale cached
evidence, conflicting sources, unknown targets, partial retrieval and search limits. The real
investigator, planner loop, SQLite source cache and server run; only HTTP is scripted. No paid calls.
"""
import json
import time
from unittest.mock import patch

import requests

from devils_advocate.http_client import JsonClient
from devils_advocate.server import create_app
from devils_advocate.source_cache import SourceCache, expiration

LIVE = {'X-Research-Mode': 'live'}
CHEMBL = 'https://www.ebi.ac.uk/chembl/api/data'
TARGET = {'disease_name': 'Example disease', 'disease_id': 'MONDO_0000001', 'target_symbol': 'GENEX', 'target_id': 'ENSG00000000001'}


def chembl_target():
    return {'targets': [{'target_chembl_id': 'CHEMBL999', 'organism': 'Homo sapiens', 'target_type': 'SINGLE PROTEIN', 'tax_id': 9606,
                         'target_components': [{'accession': 'P00001', 'target_component_synonyms': [{'component_synonym': 'GENEX', 'syn_type': 'GENE_SYMBOL'}]}]}]}


def pmc(rows, total=None):
    return {'hitCount': total if total is not None else len(rows), 'resultList': {'result': rows}}


def pub(pmid, title, abstract, date='2024-05-01'):
    return {'source': 'MED', 'id': pmid, 'title': title, 'abstractText': abstract, 'firstPublicationDate': date, 'citedByCount': 10, 'pubTypeList': {'pubType': ['Randomized Controlled Trial']}}


def study(nct, status='COMPLETED', *, with_results=True, broken=False):
    record = {'protocolSection': {'identificationModule': {'nctId': nct, 'briefTitle': 'drugone in example disease'},
              'statusModule': {'overallStatus': status, 'lastUpdatePostDateStruct': {'date': '2025-02-01'}},
              'conditionsModule': {'conditions': ['Example disease']},
              'armsInterventionsModule': {'interventions': [{'name': 'drugone'}]}}, 'hasResults': with_results}
    if broken:
        record['protocolSection']['statusModule'] = 'not a module'
    return record


class FakeResponse:
    def __init__(self, status, body, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.raw = None

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError(f'HTTP {self.status_code}')
            error.response = self
            raise error


class Transport:
    """Scripted public sources; counts upstream hits so cache behaviour is observable."""
    def __init__(self):
        self.hits = []
        self.flaky_pmc_remaining = 0
        self.publications = [pub('1001', 'Randomized trial of drugone in example disease', 'In 300 patients with example disease drugone significantly improved outcomes compared with placebo. Conclusions: drugone significantly improved the primary endpoint.')]
        self.trials = [study('NCT00000001')]
        self.ensembl_down = False

    def get(self, url, params=None, timeout=None, **_):
        self.hits.append((url, dict(params or {})))
        if 'rest.ensembl.org' in url:
            if self.ensembl_down:
                return FakeResponse(503, {'error': 'down'})
            return FakeResponse(200, {'id': 'ENSG00000000001', 'species': 'homo_sapiens', 'display_name': 'GENEX'})
        if '/ols4/api/ontologies' in url:
            return FakeResponse(200, {'_embedded': {'terms': [{'obo_id': 'MONDO:0000001', 'label': 'Example disease', 'synonyms': ['example illness']}]}})
        if url.endswith('/target/search.json'):
            return FakeResponse(200, chembl_target())
        if url.endswith('/mechanism.json'):
            return FakeResponse(200, {'mechanisms': [{'molecule_chembl_id': 'CHEMBL1', 'mechanism_of_action': 'GENEX inhibitor', 'target_chembl_id': 'CHEMBL999'}], 'page_meta': {'next': None}})
        if url.endswith('/molecule/CHEMBL1.json'):
            return FakeResponse(200, {'molecule_chembl_id': 'CHEMBL1', 'pref_name': 'drugone', 'max_phase': 4, 'molecule_synonyms': [], 'first_approval': 2015})
        if url.endswith('/drug_indication.json'):
            return FakeResponse(200, {'drug_indications': [{'efo_term': 'Example disease', 'max_phase_for_ind': 4, 'efo_id': 'MONDO:0000001'}], 'page_meta': {'next': None}})
        if 'api.fda.gov' in url:
            return FakeResponse(404, {'error': {'code': 'NOT_FOUND'}})
        if 'europepmc' in url:
            if self.flaky_pmc_remaining > 0:
                self.flaky_pmc_remaining -= 1
                return FakeResponse(503, {'error': 'overloaded'})
            query = params.get('query', '')
            if 'FIRST_PDATE' in query:
                return FakeResponse(200, pmc([]))
            return FakeResponse(200, pmc(self.publications, total=len(self.publications) + 5 if 'sort_cited' in query else None))
        if 'clinicaltrials.gov' in url:
            if url.endswith('/studies'):
                if 'filter.ids' in params:
                    ids = params['filter.ids'].split(',')
                    return FakeResponse(200, {'studies': [s for s in self.trials if s['protocolSection']['identificationModule']['nctId'] in ids]})
                return FakeResponse(200, {'studies': self.trials, 'totalCount': len(self.trials)})
            nct = url.rsplit('/', 1)[-1]
            found = [s for s in self.trials if s['protocolSection']['identificationModule']['nctId'] == nct]
            return FakeResponse(200, found[0]) if found else FakeResponse(404, {'error': 'missing'})
        return FakeResponse(404, {'error': 'unknown'})

    def close(self):
        pass

    def post(self, url, json=None, timeout=None, **_):
        self.hits.append((url, json))
        if 'search(' in json.get('query', ''):
            return FakeResponse(200, {'data': {'search': {'hits': []}}})
        return FakeResponse(200, {'data': {'target': {'id': 'ENSG00000000001', 'approvedSymbol': 'GENEX'},
                                           'disease': {'id': 'MONDO_0000001', 'name': 'Example disease', 'associatedTargets': {'rows': [{'score': 0.4, 'datatypeScores': [{'id': 'genetic_association', 'score': 0.2}], 'target': {'id': 'ENSG00000000001', 'approvedSymbol': 'GENEX'}}]}}}})


def make_app(tmp_path, transport):
    app = create_app(tmp_path)
    # Route every requests.Session call through the scripted transport (thread sessions included).
    patcher = patch.object(JsonClient, '_new_session', lambda self=None: transport)
    patcher.start()
    app.config['_patcher'] = patcher
    return app


def run(app, body=None, **extra):
    body = {'target_input': TARGET, **(body or {}), **extra}
    response = app.test_client().post('/api/investigations', headers=LIVE, json=body)
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def test_end_to_end_live_path_with_follow_up_and_cache_reuse(tmp_path, monkeypatch):
    monkeypatch.setenv('WORKBENCH_SECRET', 'test-secret')
    monkeypatch.setenv('SCOUT_DATA_DIR', str(tmp_path))
    transport = Transport()
    app = make_app(tmp_path, transport)
    try:
        job = run(app, progress_token='abcdef0123456789')
        inv = job['result']['investigation']
        assert inv['resolved_target_id'] == 'CHEMBL999' and inv['coverage']['pathway'] == 'clinical_precedent'
        plan = inv['evidence_plan']
        assert plan['stage'] == 'clinical' and plan['rounds'] and plan['stop_reason'] in ['no_new_evidence', 'round_limit', 'coverage_achieved']
        assert {n['key']: n['status'] for n in plan['needs']}['approved_therapy'] == 'satisfied'
        assert job['progress']['timings']['stages']['adaptive_rounds'] >= 0
        upstream = len(transport.hits)
        # Second identical request: verified responses come from the SQLite cache, follow-ups included.
        again = run(app)
        assert again['result']['provenance']['cache_hits'] > 0 and len(transport.hits) < upstream * 2
        assert again['result']['investigation']['evidence_plan']['stop_reason'] == plan['stop_reason']
        # Manual refresh bypasses both caches and records that it did.
        refreshed = run(app, refresh_evidence=True)
        assert refreshed['progress']['timings']['refresh_evidence'] is True and refreshed['result']['provenance']['cache_hits'] == 0
    finally:
        app.config['_patcher'].stop()


def test_transient_failures_are_retried_never_cached_and_never_reported_as_absence(tmp_path, monkeypatch):
    monkeypatch.setenv('WORKBENCH_SECRET', 'test-secret')
    monkeypatch.setenv('SCOUT_DATA_DIR', str(tmp_path))
    transport = Transport()
    transport.flaky_pmc_remaining = 40  # every Europe PMC attempt fails in the first investigation
    app = make_app(tmp_path, transport)
    try:
        job = run(app)
        inv = job['result']['investigation']
        failed = [a for a in inv['search_audit'] if a['source'] == 'Europe PMC' and a['state'] == 'failed']
        assert failed and inv['publications'] == []
        assert inv['coverage']['status'] == 'INSUFFICIENT COVERAGE'
        assert any('failed' in g for g in inv['coverage']['gaps'])
        needs = {n['key']: n for n in inv['evidence_plan']['needs']}
        assert needs['positive_clinical']['status'] in ['unverifiable', 'partial']  # a results-posted trial exists; literature failed
        assert 'absence' not in needs['positive_clinical']['note'].lower() or 'not' in needs['positive_clinical']['note'].lower()
        cache = SourceCache(tmp_path / 'runtime' / 'public-evidence-cache.sqlite3')
        with cache.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM public_responses WHERE source='Europe PMC'").fetchone()[0] == 0
        transport.flaky_pmc_remaining = 0
        recovered = run(app)
        assert recovered['result']['investigation']['publications'] and recovered['result']['investigation']['coverage']['status'] == 'BOUNDED REVIEW'
    finally:
        app.config['_patcher'].stop()


def test_stale_cached_evidence_is_refetched_after_expiry(tmp_path, monkeypatch):
    monkeypatch.setenv('WORKBENCH_SECRET', 'test-secret')
    monkeypatch.setenv('SCOUT_DATA_DIR', str(tmp_path))
    transport = Transport()
    app = make_app(tmp_path, transport)
    try:
        run(app)
        cache = SourceCache(tmp_path / 'runtime' / 'public-evidence-cache.sqlite3')
        with cache.connect() as db:
            db.execute('UPDATE public_responses SET expires=? WHERE source=?', (time.time() - 1, 'Europe PMC'))
        before = sum(1 for url, _ in transport.hits if 'europepmc' in url)
        transport.publications.append(pub('1002', 'Newer trial of drugone in example disease', 'Randomized trial in 200 patients with example disease. Conclusions: drugone did not improve the primary endpoint.', date='2025-09-01'))
        fresh = run(app)
        assert sum(1 for url, _ in transport.hits if 'europepmc' in url) > before
        assert 'MED:1002' in {p['identifier'] for p in fresh['result']['investigation']['publications']}
        assert expiration('https://www.ebi.ac.uk/europepmc/webservices/rest/search') == 6 * 3600
    finally:
        app.config['_patcher'].stop()


def test_incomplete_trial_records_and_unknown_targets_degrade_explicitly(tmp_path, monkeypatch):
    monkeypatch.setenv('WORKBENCH_SECRET', 'test-secret')
    monkeypatch.setenv('SCOUT_DATA_DIR', str(tmp_path))
    transport = Transport()
    transport.trials = [study('NCT00000001'), study('NCT00000002', 'TERMINATED', with_results=False, broken=True)]
    app = make_app(tmp_path, transport)
    try:
        job = run(app)
        inv = job['result']['investigation']
        states = {t['nct_id']: t['stop_reason']['state'] for t in inv['trials']}
        assert states['NCT00000001'] in ['absent', 'reported'] and states.get('NCT00000002', 'invalid') in ['invalid', 'unverified']
        assert all(not c['verified'] or c['source_field'] != 'why_stopped' for c in inv['claims'] if c['source_id'] == 'NCT00000002')
        unknown = app.test_client().post('/api/investigations', headers=LIVE, json={'target_input': {**TARGET, 'target_symbol': 'NOPE123', 'target_id': None}}).get_json()
        plan = unknown['result']['investigation']['evidence_plan']
        assert plan['stage'] == 'unresolved' and plan['stop_reason'] == 'target_unresolved' and not plan['rounds']
        assert unknown['result']['investigation']['publications'] == [] and unknown['result']['experiment']['status'] == 'INSUFFICIENT EVIDENCE FOR EXPERIMENT'
    finally:
        app.config['_patcher'].stop()


def test_gene_registry_outage_is_a_retrieval_failure_not_an_identity_failure(tmp_path, monkeypatch):
    monkeypatch.setenv('WORKBENCH_SECRET', 'test-secret')
    monkeypatch.setenv('SCOUT_DATA_DIR', str(tmp_path))
    transport = Transport()
    transport.ensembl_down = True
    app = make_app(tmp_path, transport)
    try:
        inv = run(app)['result']['investigation']
        assert inv['resolved_target_id'] == 'CHEMBL999' and inv['resolution_status'] == 'resolved'
        ensembl = [a for a in inv['search_audit'] if a['source'] == 'Ensembl']
        assert ensembl and ensembl[0]['state'] == 'failed' and 'not established wrong' in ensembl[0]['detail']
        # The Open Targets exact-pair lookup confirmed id + symbol, so coverage does not demand a second check.
        assert not any('gene identifier could not be verified' in g for g in inv['coverage']['gaps'])
        assert sum(1 for url, _ in transport.hits if 'ensembl' in url) == 2  # host policy: two attempts, not three
    finally:
        app.config['_patcher'].stop()


def test_search_limits_and_partial_retrieval_are_recorded_not_hidden(tmp_path, monkeypatch):
    monkeypatch.setenv('WORKBENCH_SECRET', 'test-secret')
    monkeypatch.setenv('SCOUT_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('RESEARCH_RETRIEVAL_BUDGET_SECONDS', '1')
    transport = Transport()
    app = make_app(tmp_path, transport)
    try:
        response = app.test_client().post('/api/investigations', headers=LIVE, json={'target_input': TARGET})
        job = response.get_json()
        if job['state'] == 'failed':
            assert 'time budget' in job['error']
        else:
            inv = job['result']['investigation']
            plan = inv['evidence_plan']
            assert plan['stop_reason'] in ['budget_exhausted', 'no_new_evidence', 'round_limit', 'coverage_achieved', 'no_actionable_gaps']
            limited = [a for a in inv['search_audit'] if a['state'] == 'limit_reached']
            assert limited, 'hitCount above the page size must be recorded as limit_reached'
    finally:
        app.config['_patcher'].stop()
