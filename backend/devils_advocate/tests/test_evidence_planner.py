"""Offline tests for the Evidence Discovery Planner and the bounded gap-resolution loop. No network, no model."""
from datetime import date
from unittest.mock import Mock

import pytest

from devils_advocate.evidence_planner import (advanced_compounds, assess_plan, build_plan, followup_searches, is_recent,
                                              recent_cutoff, resolve_loop)
from devils_advocate.http_client import RetrievalDeadlineExceeded, RetrievalError
from devils_advocate.models import Compound, Investigation, Publication, SearchAudit, TargetInput, Trial
from devils_advocate.literature import annotate, publication_from_record
from devils_advocate.models import EvidenceRound
from devils_advocate.trial_retriever import parse_trial

TODAY = date(2026, 11, 8)


def pub(identifier, title, abstract, *, year='2015', cited=10, types=()):
    return annotate(Publication(identifier=identifier, title=title, abstract=abstract, url='https://europepmc.org/article/MED/' + identifier.split(':')[1],
                       publication_date=year + '-01-01', cited_by_count=cited, study_types=list(types), disease_match='matched'))


def trial(nct, status='COMPLETED', conditions=('Example disease',), interventions=('drugone',), compound_ids=('CHEMBL1',), **extra):
    return Trial(nct_id=nct, title='Trial ' + nct, status=status, conditions=list(conditions), interventions=list(interventions),
                 compound_ids=list(compound_ids), compound_matches={c: 'verified' for c in compound_ids}, relationship='verified' if compound_ids else 'uncertain',
                 disease_match='matched', url='https://clinicaltrials.gov/study/' + nct, population='Adults with example disease', **extra)


def clinical_investigation(*, audited=True):
    target = TargetInput(disease_name='Example disease', target_symbol='GENEX', disease_id='MONDO_0000001', target_id='ENSG00000000001')
    result = Investigation(target=target, mode='live', resolved_target_id='CHEMBL999', resolution_status='resolved')
    result.compounds = [Compound(chembl_id='CHEMBL1', name='drugone', url='u', max_phase=4,
                                 indications=[{'efo_term': 'Example disease', 'max_phase_for_ind': 4, 'approval_precedent': True, 'disease_match': 'lexical'}],
                                 indication_search_state='found')]
    result.trials = [trial('NCT00000001', has_results=True, results_posted_date='2025-03-01', last_update_date='2025-03-01')]
    result.publications = [
        pub('MED:1', 'Randomized trial of drugone in example disease', 'In this randomized, placebo-controlled trial in 300 patients with example disease, drugone significantly improved outcomes compared with placebo. Conclusions: drugone significantly improved the primary endpoint.', year='2012', cited=500, types=['Randomized Controlled Trial']),
        pub('MED:2', 'Phase 3 trial of drugone in treatment-naive example disease', 'Randomized trial in 200 patients with example disease; drugone did not improve the primary endpoint. Conclusions: drugone did not improve outcomes versus placebo and adverse events were more frequent.', year='2025', cited=5, types=['Randomized Controlled Trial'])]
    result.ontology_association = {'state': 'found', 'target_id': 'ENSG00000000001', 'disease_id': 'MONDO_0000001', 'score': 0.5, 'datatype_scores': [{'id': 'genetic_association', 'score': 0.3}]}
    if audited:
        result.search_audit = [SearchAudit(source=s, operation='test', url='https://example.org', state='found') for s in ['ChEMBL', 'Europe PMC', 'ClinicalTrials.gov']]
    return result


def preclinical_investigation():
    target = TargetInput(disease_name='Rare disorder', target_symbol='GENEY', disease_id='MONDO_0000002', target_id='ENSG00000000002')
    result = Investigation(target=target, mode='live', resolved_target_id='CHEMBL998', resolution_status='resolved')
    result.publications = [
        pub('MED:10', 'GENEY variants in rare disorder', 'Genome-wide association in rare disorder patients identified GENEY risk variants associated with rare disorder.', year='2019', cited=40),
        pub('MED:11', 'GENEY knockdown in rare disorder chondrocytes', 'Knockdown of GENEY in cultured patient chondrocytes from rare disorder altered proliferation; GENEY regulates rare disorder pathogenesis.', year='2021', cited=12)]
    result.ontology_association = {'state': 'found', 'target_id': 'ENSG00000000002', 'disease_id': 'MONDO_0000002', 'score': 0.1, 'datatype_scores': []}
    result.search_audit = [SearchAudit(source=s, operation='test', url='https://example.org', state='found') for s in ['ChEMBL', 'Europe PMC', 'ClinicalTrials.gov']]
    return result


class ScriptedClient:
    """Routes follow-up requests by URL/params; records what was asked."""
    def __init__(self, responses, remaining=200.):
        self.responses, self.requests, self.remaining = responses, [], remaining
        self.max_workers = 1

    def remaining_seconds(self):
        return self.remaining

    def _answer(self, key):
        value = self.responses.get(key, {'hitCount': 0, 'resultList': {'result': []}})
        if isinstance(value, Exception):
            raise value
        return value

    def get(self, url, params=None):
        self.requests.append((url, params))
        if url in self.responses:
            return self._answer(url)
        if 'europepmc' in url:
            for key, value in self.responses.items():
                if key in (params or {}).get('query', ''):
                    return self._answer(key)
            return self._answer('__pmc__')
        if 'clinicaltrials' in url:
            return self._answer('__ctg__')
        if 'ols4' in url:
            return self._answer('__ols__')
        return self._answer(url)

    def post_json(self, url, payload):
        self.requests.append((url, payload))
        return self._answer('__ot__')


def pmc_rows(*rows):
    return {'hitCount': len(rows), 'resultList': {'result': list(rows)}}


def row(pmid, title, abstract, date='2025-06-01', types=('Randomized Controlled Trial',)):
    return {'source': 'MED', 'id': pmid, 'title': title, 'abstractText': abstract, 'firstPublicationDate': date, 'citedByCount': 3,
            'pubTypeList': {'pubType': list(types)}}


def test_dates_and_tiers_are_parsed_from_source_records():
    p = publication_from_record(row('77', 'T', 'A', date='2024-02-03'))
    assert p.publication_date == '2024-02-03' and p.evidence_tier == 'peer_reviewed' and p.identifier == 'MED:77'
    assert publication_from_record({'source': 'MED', 'id': '1', 'firstPublicationDate': 'not a date'}).publication_date is None
    assert publication_from_record({'id': '1'}) is None
    record = {'protocolSection': {'identificationModule': {'nctId': 'NCT00000009'}, 'statusModule': {'overallStatus': 'COMPLETED',
              'startDateStruct': {'date': '2019-05'}, 'primaryCompletionDateStruct': {'date': '2021-01-15'}, 'lastUpdatePostDateStruct': {'date': '2024-07-01'},
              'resultsFirstPostDateStruct': {'date': 'bad'}}}, 'hasResults': True}
    t = parse_trial(record, [])
    assert (t.start_date, t.completion_date, t.last_update_date, t.results_posted_date) == ('2019-05', '2021-01-15', '2024-07-01', None)
    assert t.evidence_tier == 'registry_results'
    assert is_recent('2024', recent_cutoff(3, TODAY)) and not is_recent('2020-01-01', recent_cutoff(3, TODAY)) and not is_recent(None, '2023')


def test_clinical_plan_marks_needs_from_scoped_records_and_flags_material_ids():
    result = clinical_investigation()
    plan = assess_plan(result, build_plan(result), today=TODAY)
    status = {n.key: n.status for n in plan.needs}
    assert plan.stage == 'clinical'
    assert status['approved_therapy'] == 'satisfied' and status['positive_clinical'] == 'satisfied'
    assert status['negative_or_safety'] == 'satisfied' and status['programme_status'] == 'satisfied'
    assert status['target_disease_association'] == 'satisfied' and status['recent_development'] == 'satisfied'
    need = {n.key: n for n in plan.needs}
    assert 'MED:1' in need['positive_clinical'].material_ids and 'MED:2' in need['negative_or_safety'].material_ids
    assert 'MED:2' in need['recent_development'].material_ids  # dated 2025 with consequential wording
    assert 'Sponsor press releases' in plan.limitations[0]
    # Only the one partial need (a single genetic line) generates a search; satisfied needs generate none.
    assert [s['need_key'] for s in followup_searches(result, plan, 0, today=TODAY)] == ['genetic_mechanistic']


def test_preclinical_plan_skips_clinical_needs_and_searches_genetic_evidence_not_trials():
    result = preclinical_investigation()
    plan = assess_plan(result, build_plan(result), today=TODAY)
    status = {n.key: n.status for n in plan.needs}
    assert plan.stage == 'preclinical'
    assert status['positive_clinical'] == 'not_applicable' and status['programme_status'] == 'not_applicable'
    assert status['genetic_mechanistic'] == 'satisfied' and status['recent_development'] == 'unmet'
    searches = followup_searches(result, plan, 0, today=TODAY)
    assert [s['need_key'] for s in searches] == ['recent_development', 'population_subtype']
    assert all(s['source'] == 'Europe PMC' for s in searches) and 'FIRST_PDATE' in searches[0]['query']['query']
    assert not any('ClinicalTrials' in s['source'] for s in searches)


def test_unmet_clinical_needs_generate_targeted_queries_with_identifiers_and_outcome_terms():
    result = clinical_investigation()
    result.publications = []
    result.trials[0].has_results = False
    result.trials[0].status = 'TERMINATED'
    plan = assess_plan(result, build_plan(result), today=TODAY)
    assert {n.key: n.status for n in plan.needs}['positive_clinical'] == 'unmet'
    searches = followup_searches(result, plan, 0, today=TODAY)
    operations = {s['operation'] for s in searches}
    assert 'clinical outcome follow-up' in operations and 'registry-linked outcome publications' in operations
    outcome = next(s for s in searches if s['operation'] == 'clinical outcome follow-up')['query']['query']
    assert 'GENEX' in outcome and 'drugone' in outcome and '"primary endpoint"' in outcome and 'sort_cited:y' in outcome
    linked = next(s for s in searches if s['operation'] == 'registry-linked outcome publications')['query']['query']
    assert 'NCT00000001' in linked
    assert len(searches) <= 6
    # Round two varies the strategy instead of repeating identical queries.
    plan.rounds.append(EvidenceRound(round_number=1, searches=[]))
    later = next(s for s in followup_searches(result, plan, 1, today=TODAY) if s['operation'] == 'clinical outcome follow-up')
    assert 'sort_date:y' in later['query']['query'] and later['query'] != next(s for s in searches if s['operation'] == 'clinical outcome follow-up')['query']


def test_manual_pair_without_identifiers_resolves_them_before_association():
    target = TargetInput(disease_name='Example disease', target_symbol='GENEX')
    result = Investigation(target=target, mode='live', resolved_target_id='CHEMBL999', resolution_status='resolved')
    result.search_audit = [SearchAudit(source=s, operation='test', url='https://example.org', state='found') for s in ['Europe PMC', 'ClinicalTrials.gov']]
    plan = assess_plan(result, build_plan(result), today=TODAY)
    searches = followup_searches(result, plan, 0, today=TODAY)
    assert ('Open Targets', 'gene identifier resolution') in {(s['source'], s['operation']) for s in searches}
    assert ('OLS', 'disease identifier resolution') in {(s['source'], s['operation']) for s in searches}
    client = ScriptedClient({'__ot__': {'data': {'search': {'hits': [{'id': 'ENSG00000000001', 'name': 'GENEX', 'entity': 'target'}]}}},
                             '__ols__': {'response': {'docs': [{'obo_id': 'MONDO:0000001', 'label': 'Example disease', 'synonym': ['example illness']}]}}})
    resolve_loop(client, result, max_rounds=1, today=TODAY)
    assert result.target.target_id == 'ENSG00000000001' and result.target.disease_id == 'MONDO_0000001'
    assert 'example illness' in result.target.disease_aliases
    identity = [s for r in result.evidence_plan.rounds for s in r.searches if s.source in ['Open Targets', 'OLS']]
    assert all(s.state == 'found' for s in identity) and all(s.new_evidence_ids for s in identity)


def test_ambiguous_identifier_lookups_guess_nothing():
    target = TargetInput(disease_name='Example disease', target_symbol='GENEX')
    result = Investigation(target=target, mode='live', resolved_target_id='CHEMBL999', resolution_status='resolved')
    client = ScriptedClient({'__ot__': {'data': {'search': {'hits': [{'id': 'ENSG00000000001', 'name': 'GENEX', 'entity': 'target'}, {'id': 'ENSG00000000003', 'name': 'GENEX', 'entity': 'target'}]}}},
                             '__ols__': {'response': {'docs': [{'obo_id': 'MONDO:0000001', 'label': 'Example disease (other)'}]}}})
    resolve_loop(client, result, max_rounds=1, today=TODAY)
    assert result.target.target_id is None and result.target.disease_id is None
    assert {s.state for r in result.evidence_plan.rounds for s in r.searches if s.source in ['Open Targets', 'OLS']} == {'no_results'}


def test_loop_ingests_new_follow_up_publications_and_stops_when_coverage_is_achieved():
    result = clinical_investigation()
    result.publications = [result.publications[0]]  # positive only: negative/safety unmet, recent unmet
    result.trials[0].has_results = False
    new = row('555', 'Phase 3 drugone trial in example disease did not meet primary endpoint',
              'Randomized placebo-controlled trial in 400 patients with example disease. Conclusions: drugone did not meet the primary endpoint and adverse events were frequent.', date='2025-09-01')
    client = ScriptedClient({'clinical outcome follow-up': pmc_rows(new), '"primary endpoint"': pmc_rows(new)})
    plan = resolve_loop(client, result, max_rounds=2, today=TODAY)
    assert 'MED:555' in {p.identifier for p in result.publications}
    added = next(p for p in result.publications if p.identifier == 'MED:555')
    assert added.discovered_by != 'initial retrieval' and added.publication_date == '2025-09-01' and 'negative_candidate' in added.direction_signals
    assert plan.rounds[0].new_evidence_ids and 'MED:555' in plan.rounds[0].new_evidence_ids
    status = {n.key: n.status for n in plan.needs}
    assert status['negative_or_safety'] == 'satisfied' and status['recent_development'] == 'satisfied'
    assert plan.stop_reason in ['coverage_achieved', 'no_new_evidence', 'round_limit']
    assert any(a.operation.startswith('adaptive:') and a.relevant >= 1 for a in result.search_audit)
    # No publication was ingested twice.
    assert len({p.identifier for p in result.publications}) == len(result.publications)


def test_loop_stops_with_no_new_evidence_and_never_promotes_failed_searches_to_absence():
    result = clinical_investigation()
    result.publications = []
    result.trials = []
    client = ScriptedClient({'__pmc__': RetrievalError('Europe PMC unavailable', status_code=503), '__ctg__': RetrievalError('registry down')})
    plan = resolve_loop(client, result, max_rounds=2, today=TODAY)
    assert plan.stop_reason == 'no_new_evidence' and len(plan.rounds) == 1
    assert all(s.state == 'failed' for s in plan.rounds[0].searches)
    assert all('not a zero-result search' in s.detail for s in plan.rounds[0].searches)
    failed = [a for a in result.search_audit if a.operation.startswith('adaptive:')]
    assert failed and all(a.state == 'failed' for a in failed)
    assert not any(n.status == 'satisfied' for n in plan.needs if n.key in ['positive_clinical', 'negative_or_safety'])


def test_loop_honours_round_limit_zero_and_budget_reserve():
    result = clinical_investigation()
    result.publications = []
    plan = resolve_loop(ScriptedClient({}), result, max_rounds=0, today=TODAY)
    assert plan.stop_reason == 'follow_up_disabled' and plan.rounds == []
    short = ScriptedClient({}, remaining=3.)
    plan = resolve_loop(short, result, max_rounds=2, today=TODAY)
    assert plan.stop_reason == 'budget_exhausted' and short.requests == [] and plan.limitations[-1].startswith('Follow-up round 1 skipped')


def test_deadline_inside_a_round_records_completed_searches_and_stops():
    result = clinical_investigation()
    result.publications = []
    result.trials[0].has_results = False
    client = ScriptedClient({'__pmc__': RetrievalDeadlineExceeded('budget')})
    plan = resolve_loop(client, result, max_rounds=2, today=TODAY)
    assert plan.stop_reason == 'budget_exhausted' and plan.rounds and plan.rounds[0].searches
    assert plan.rounds[0].searches[0].state == 'failed'


def test_unresolved_target_runs_no_follow_up_and_marks_every_need_unverifiable():
    result = Investigation(target=TargetInput(disease_name='Example disease', target_symbol='NOPE'), mode='live', resolution_status='unknown')
    client = ScriptedClient({})
    plan = resolve_loop(client, result, max_rounds=2, today=TODAY)
    assert plan.stage == 'unresolved' and plan.stop_reason == 'target_unresolved' and client.requests == []
    assert {n.status for n in plan.needs} == {'unverifiable'}


def test_model_planner_suggestions_become_queries_only_never_evidence():
    result = clinical_investigation()
    result.publications = []
    hook = Mock(return_value=[{'need_key': 'positive_clinical', 'terms': ['open-label extension', 'biomarker; DROP TABLE']}, 'junk'])
    client = ScriptedClient({})
    plan = resolve_loop(client, result, max_rounds=1, planner_hook=hook, today=TODAY)
    assert plan.planner.startswith('deterministic + model') and len(plan.planner_suggestions) == 1
    suggested = [s for s in plan.rounds[0].searches if s.operation == 'model-suggested follow-up']
    assert suggested and '"open-label extension"' in suggested[0].query['query'] and 'DROP' not in suggested[0].query['query']
    assert suggested[0].state == 'no_results' and not suggested[0].new_evidence_ids
    assert not any('open-label' in (p.title + p.abstract) for p in result.publications)


def test_planner_hook_failure_does_not_stop_deterministic_follow_up():
    result = clinical_investigation()
    result.publications = []
    plan = resolve_loop(ScriptedClient({}), result, max_rounds=1, planner_hook=Mock(side_effect=RuntimeError('refused')), today=TODAY)
    assert plan.rounds and any('Model planning suggestion failed' in l for l in plan.limitations)


def test_follow_up_trials_are_verified_with_full_records_and_deduplicated():
    result = clinical_investigation()
    result.trials = []
    result.publications = []
    study = {'protocolSection': {'identificationModule': {'nctId': 'NCT00000077'}, 'statusModule': {'overallStatus': 'TERMINATED', 'whyStopped': 'futility'},
             'conditionsModule': {'conditions': ['Example disease']}, 'armsInterventionsModule': {'interventions': [{'name': 'drugone'}]}}}
    client = ScriptedClient({'__ctg__': {'studies': [study, study]}, 'https://clinicaltrials.gov/api/v2/studies/NCT00000077': study})
    resolve_loop(client, result, max_rounds=1, today=TODAY)
    assert [t.nct_id for t in result.trials] == ['NCT00000077'] and result.trials[0].why_stopped == 'futility'
    assert result.trials[0].relationship == 'verified' and result.trials[0].disease_match == 'matched'
    assert {n.key: n.status for n in result.evidence_plan.needs}['negative_or_safety'] == 'satisfied'


def test_advanced_compounds_prefer_phase_then_trial_links():
    result = clinical_investigation()
    result.compounds.append(Compound(chembl_id='CHEMBL2', name='earlyone', url='u', max_phase=1))
    result.compounds.append(Compound(chembl_id='CHEMBL3', name='linkedone', url='u', max_phase=None))
    result.trials[0].compound_ids.append('CHEMBL3')
    assert [c.chembl_id for c in advanced_compounds(result)] == ['CHEMBL1', 'CHEMBL3']


def test_gene_named_disorders_accept_gene_loss_wording_but_biomarker_cancers_do_not():
    from devils_advocate.disease_terms import gene_defined_terms, matches, terms
    rare = TargetInput(disease_name='GENEZ deficiency', target_symbol='GENEZ')
    assert 'GENEZ-defective' in gene_defined_terms(rare) and 'GENEZ-defective' in terms(rare)
    assert matches('ERAD dysregulation in Genez-defective cells reflects mutation of the human GENEZ gene.', rare)
    assert not matches('GENEZ is expressed in liver.', rare)
    cancer = TargetInput(disease_name='GENEZ-mutant non-small-cell lung cancer', target_symbol='GENEZ')
    assert gene_defined_terms(cancer) == []
    assert not matches('GENEZ mutation in glioblastoma', cancer)


def test_symbol_shared_with_a_historical_alias_resolves_by_current_gene_symbol():
    from devils_advocate.trial_retriever import resolve_target
    from .test_pipeline import FakeClient
    def record(chembl_id, name, syn_type):
        return {'target_chembl_id': chembl_id, 'organism': 'Homo sapiens', 'target_type': 'SINGLE PROTEIN', 'tax_id': 9606,
                'target_components': [{'accession': 'P1', 'target_component_synonyms': [{'component_synonym': 'HTT', 'syn_type': syn_type}, {'component_synonym': name, 'syn_type': 'GENE_SYMBOL' if syn_type != 'GENE_SYMBOL' else 'GENE_SYMBOL_OTHER'}]}]}
    client = FakeClient([{'targets': [record('CHEMBL228', 'SLC6A4', 'GENE_SYMBOL_OTHER'), record('CHEMBL5514', 'HD', 'GENE_SYMBOL')]}])
    assert resolve_target(client, TargetInput(disease_name='Huntington disease', target_symbol='HTT')) == 'CHEMBL5514'
    tie = FakeClient([{'targets': [record('CHEMBL1', 'A', 'GENE_SYMBOL'), record('CHEMBL2', 'B', 'GENE_SYMBOL')]}])
    assert resolve_target(tie, TargetInput(disease_name='x', target_symbol='HTT')) is None


def test_gene_verified_target_without_chembl_protein_still_retrieves_by_symbol():
    from devils_advocate.devil_advocate import investigate_target
    class Client:
        """Ensembl verifies the gene; ChEMBL has no single-protein match; registry/literature answer by symbol."""
        def __init__(self): self.urls = []
        def remaining_seconds(self): return 100.
        def get(self, url, params=None):
            self.urls.append(url)
            if 'ensembl' in url: return {'id': 'ENSG00000197386', 'species': 'homo_sapiens', 'display_name': 'HTT'}
            if 'ols4' in url: return {'_embedded': {'terms': [{'obo_id': 'MONDO:0007739', 'label': 'Huntington disease', 'synonyms': []}]}}
            if url.endswith('/target/search.json'): return {'targets': []}
            if 'clinicaltrials' in url and url.endswith('/studies'):
                return {'studies': [{'protocolSection': {'identificationModule': {'nctId': 'NCT03761849', 'briefTitle': 'tominersen in Huntington disease'}, 'statusModule': {'overallStatus': 'TERMINATED', 'whyStopped': 'futility'},
                        'conditionsModule': {'conditions': ['Huntington Disease']}, 'armsInterventionsModule': {'interventions': [{'name': 'tominersen (HTT antisense oligonucleotide)'}]}}}]}
            if 'clinicaltrials' in url: return {'protocolSection': {'identificationModule': {'nctId': 'NCT03761849'}, 'statusModule': {'overallStatus': 'TERMINATED', 'whyStopped': 'futility'}, 'conditionsModule': {'conditions': ['Huntington Disease']}, 'armsInterventionsModule': {'interventions': [{'name': 'tominersen (HTT antisense oligonucleotide)'}]}}}
            if 'europepmc' in url:
                return {'hitCount': 1, 'resultList': {'result': [{'source': 'MED', 'id': '31059641', 'title': 'Targeting Huntingtin Expression in Patients with Huntington disease', 'abstractText': 'Phase 1-2a trial in 46 patients with Huntington disease: the HTT-lowering antisense oligonucleotide reduced CSF mutant huntingtin.', 'firstPublicationDate': '2019-05-06', 'pubTypeList': {'pubType': ['Clinical Trial, Phase I']}}]}}
            return {}
        def post_json(self, url, payload): return {'data': {'target': {'id': 'ENSG00000197386', 'approvedSymbol': 'HTT'}, 'disease': {'id': 'MONDO_0007739', 'name': 'Huntington disease', 'associatedTargets': {'rows': [{'score': 0.9, 'datatypeScores': [{'id': 'genetic_association', 'score': 0.9}], 'target': {'id': 'ENSG00000197386', 'approvedSymbol': 'HTT'}}]}}}}
    client = Client()
    result = investigate_target({'disease_name': 'Huntington disease', 'disease_id': 'MONDO_0007739', 'target_symbol': 'HTT', 'target_id': 'ENSG00000197386'}, client=client)
    assert result.resolved_target_id is None and result.resolution_status == 'gene_verified'
    assert [t.nct_id for t in result.trials] == ['NCT03761849'] and result.trials[0].why_stopped == 'futility'
    assert 'MED:31059641' in {p.identifier for p in result.publications}
    assert result.evidence_plan.stage == 'clinical' and 'Exact target identity unresolved.' not in result.coverage.gaps
    assert any('ChEMBL single-protein target' in l for l in result.evidence_plan.limitations)
    assert any('ChEMBL has no exact single-protein' in m for m in result.missing_information)


def test_invalid_symbol_stays_unresolved_when_no_registry_verifies_it():
    from devils_advocate.devil_advocate import investigate_target
    class Client:
        def get(self, url, params=None):
            if url.endswith('/target/search.json'): return {'targets': []}
            return {}
        def post_json(self, url, payload): return {'data': {'search': {'hits': []}}}
    result = investigate_target({'disease_name': 'HIV infection', 'target_symbol': 'AUDIT_FAKE_GENE_ZXQ987'}, client=Client())
    assert result.resolution_status == 'unknown' and result.trials == [] and result.publications == []
    assert result.evidence_plan.stage == 'unresolved' and result.target.target_id is None
