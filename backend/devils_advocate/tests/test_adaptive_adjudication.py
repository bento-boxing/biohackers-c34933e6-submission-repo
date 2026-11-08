"""Offline tests: adjudicator applicability rules, coverage retrieval requests, packet material records, prior-art facets."""
from types import SimpleNamespace
from unittest.mock import Mock

from devils_advocate.ai_reasoning import evidence_bundle, omitted_contradictions, run_ai_reasoning, validate_ai_claim
from devils_advocate.coverage import check_coverage, select_evidence, target_level_objections
from devils_advocate.evidence_planner import assess_plan, build_plan
from devils_advocate.models import AIClaim, AICitation, Adjudication, AdjudicationBatch, EvidenceNeed, EvidencePlan, Experiment
from devils_advocate.prior_art import check_prior_art
from .test_ai import ScriptedRunner, draft, final, settings
from .test_evidence_planner import TODAY, clinical_investigation, pub, trial


def bundle_with(result):
    assess_plan(result, build_plan(result), today=TODAY)
    result.evidence_plan = result.evidence_plan or build_plan(result)
    result.coverage = check_coverage(result)
    return evidence_bundle(result, settings())


def make_claim(stance, text, source_id, field, excerpt, *, kind='interpretation', concern='efficacy'):
    return AIClaim(claim_id='c1', text=text, kind=kind, concern=concern, stance=stance,
                   citations=[AICitation(source_id=source_id, field=field, excerpt=excerpt)],
                   relevance='Disease-matched trial context.', uncertainty='Bounded packet; population equivalence unverified.')


def test_supporting_stance_on_a_negative_excerpt_is_objected():
    result = clinical_investigation()
    bundle = bundle_with(result)
    negative = 'drugone did not improve outcomes versus placebo and adverse events were more frequent.'
    claim = make_claim('supporting', 'drugone is effective in example disease.', 'MED:2', 'conclusion_excerpt', negative)
    assert any(o.startswith('Stance/excerpt mismatch') for o in validate_ai_claim(claim, bundle, result))
    ok = make_claim('contradictory', 'drugone did not improve outcomes in this trial.', 'MED:2', 'conclusion_excerpt', negative)
    assert not any(o.startswith('Stance/excerpt mismatch') for o in validate_ai_claim(ok, bundle, result))


def test_causal_wording_beyond_an_observed_association_is_objected():
    result = clinical_investigation()
    result.publications.append(pub('MED:3', 'GENEX expression and disease severity', 'GENEX expression was associated with severity in patients with example disease. Conclusions: GENEX expression is associated with severity.', year='2018'))
    bundle = bundle_with(result)
    bundle['sources']['MED:3'] = {'url': 'u', 'fields': {'abstract': result.publications[-1].abstract}, 'applicability': {'disease_match': 'matched'}}
    claim = make_claim('context', 'GENEX drives disease severity in example disease.', 'MED:3', 'abstract', 'GENEX expression was associated with severity in patients with example disease.', concern='unknown')
    assert any(o.startswith('Causal wording') for o in validate_ai_claim(claim, bundle, result))
    hedged = claim.model_copy(update={'text': 'GENEX may drive severity; this is an interpretation of an association.'})
    assert not any(o.startswith('Causal wording') for o in validate_ai_claim(hedged, bundle, result))


def test_uncertain_disease_sources_cannot_ground_a_disease_specific_stance():
    result = clinical_investigation()
    bundle = bundle_with(result)
    bundle['sources']['MED:9'] = {'url': 'u', 'fields': {'abstract': 'drugone lowered a biomarker in healthy volunteers.'}, 'applicability': {'disease_match': 'uncertain'}}
    claim = make_claim('supporting', 'drugone lowers the biomarker in example disease.', 'MED:9', 'abstract', 'drugone lowered a biomarker in healthy volunteers.')
    assert any(o.startswith('Population applicability') for o in validate_ai_claim(claim, bundle, result))


def test_universal_and_exclusive_claims_are_rejected_deterministically():
    assert any('Universal or exclusive' in o for o in target_level_objections('drugone cures example disease in all patients.'))
    assert any('Universal or exclusive' in o for o in target_level_objections('GENEX inhibition is the only effective mechanism.'))
    assert not target_level_objections('drugone improved outcomes in the studied cohort; this does not apply to all patients.')


def test_omitted_contradictory_evidence_is_named_and_pulled_into_the_revision_packet():
    result = clinical_investigation()
    for i in range(6):  # push the negative trial past the publication cutoff with other direct records
        result.publications.insert(0, pub(f'MED:10{i}', f'Randomized trial {i} of drugone in example disease', 'Randomized trial in 100 patients with example disease; drugone significantly improved outcomes compared with placebo. Conclusions: drugone significantly improved outcomes compared with placebo.', year='2010', cited=900 - i, types=['Randomized Controlled Trial']))
    # A second, better-cited negative record fills the negative stratum, so MED:2 falls past the cutoff.
    result.publications.append(pub('MED:4', 'Second phase 3 trial of drugone in example disease', 'Randomized trial in 500 patients with example disease. Conclusions: drugone did not improve the primary endpoint and adverse events were frequent.', year='2024', cited=50, types=['Randomized Controlled Trial']))
    assess_plan(result, build_plan(result), today=TODAY)
    result.evidence_plan.needs = [EvidenceNeed(key='x', label='x')]  # no material flags for this test
    result.coverage = check_coverage(result, 6, 2)
    bundle = evidence_bundle(result, settings(max_publications=2))
    assert 'MED:2' not in bundle['sources'] and 'MED:4' in bundle['sources']
    positive = make_claim('supporting', 'drugone improves outcomes in example disease.', 'MED:100', 'conclusion_excerpt', 'drugone significantly improved outcomes compared with placebo.')
    assert omitted_contradictions(result, bundle, positive) == ['MED:2']
    assert any('Material contradictory evidence omitted' in o for o in validate_ai_claim(positive, bundle, result))
    # The reasoning loop adds the omitted record to the packet before adjudication and records the request.
    runner = ScriptedRunner([draft(positive), AdjudicationBatch(findings=[Adjudication(claim_id='c1', verdict='revise', finding='Omitted contradiction.', revision_request='Qualify.')]),
                             draft(positive.model_copy(update={'stance': 'context'})), AdjudicationBatch(findings=[Adjudication(claim_id='c1', verdict='supported', finding='ok', revision_request='')]), final()])
    report = run_ai_reasoning(result, settings=settings(max_publications=2), runner=runner)
    assert report.packet_audit['retrieval_requests'][0]['source_ids'] == ['MED:2']
    assert 'MED:2' in report.sent_source_ids and 'MED:2' in runner.payloads[1][1]['evidence']['sources']


def test_unverified_consequential_claim_triggers_one_targeted_retrieval():
    result = clinical_investigation()
    bundle_with(result)
    claim = make_claim('contradictory', 'drugone failed in treatment-experienced patients with example disease.', 'MED:2', 'conclusion_excerpt', 'drugone did not improve outcomes versus placebo and adverse events were more frequent.')
    row = {'source': 'MED', 'id': '777', 'title': 'drugone in treatment-experienced example disease', 'abstractText': 'GENEX inhibitor drugone in treatment-experienced patients with example disease.', 'firstPublicationDate': '2024-01-01'}
    client = SimpleNamespace(get=Mock(return_value={'hitCount': 1, 'resultList': {'result': [row]}}))
    runner = ScriptedRunner([draft(claim), AdjudicationBatch(findings=[Adjudication(claim_id='c1', verdict='unsupported', finding='Population not in excerpt.', revision_request='Cite population.')]),
                             draft(claim.model_copy(update={'stance': 'context'})), AdjudicationBatch(findings=[Adjudication(claim_id='c1', verdict='supported', finding='ok', revision_request='')]), final()])
    report = run_ai_reasoning(result, settings=settings(), runner=runner, prior_art_client=client)
    requests = [r for r in report.packet_audit['retrieval_requests'] if r['kind'] == 'unverified_consequential_claim']
    assert requests and requests[0]['new_source_ids'] == ['MED:777'] and 'MED:777' in report.sent_source_ids
    assert any('experienc' in call.args[1]['query'] and 'drugone' in call.args[1]['query'] for call in client.get.call_args_list)


def test_material_records_enter_the_packet_beyond_the_cutoff_with_reasons():
    result = clinical_investigation()
    for i in range(6):
        result.publications.insert(0, pub(f'MED:10{i}', f'Randomized trial {i} of drugone in example disease', 'Randomized trial in 100 patients with example disease; drugone significantly improved outcomes compared with placebo. Conclusions: drugone significantly improved outcomes compared with placebo.', year='2010', cited=900 - i, types=['Randomized Controlled Trial']))
    assess_plan(result, build_plan(result), today=TODAY)
    trials, pubs, reasons = select_evidence(result, 6, 1)
    ids = {p.identifier for p in pubs}
    assert 'MED:2' in ids and any('Planner material record' in r for r in reasons['MED:2'])
    assert len(pubs) <= 1 + 6
    coverage = check_coverage(result, 6, 1)
    assert 'MED:2' in coverage.facets['evidence_plan']['material_included'] and not coverage.facets['evidence_plan']['material_omitted']


def test_material_records_that_cannot_fit_become_a_coverage_gap(monkeypatch):
    monkeypatch.setenv('AI_MAX_MATERIAL_EXTRA', '0')
    result = clinical_investigation()
    for i in range(6):
        result.publications.insert(0, pub(f'MED:10{i}', f'Randomized trial {i} of drugone in example disease', 'Randomized trial in 100 patients with example disease; drugone significantly improved outcomes compared with placebo. Conclusions: drugone significantly improved outcomes compared with placebo.', year='2010', cited=900 - i, types=['Randomized Controlled Trial']))
    assess_plan(result, build_plan(result), today=TODAY)
    coverage = check_coverage(result, 6, 1)
    assert coverage.status == 'INSUFFICIENT COVERAGE' and any('no representative record in the packet' in g for g in coverage.gaps)
    assert 'negative_or_safety' in coverage.facets['evidence_plan']['unrepresented_needs']
    assert any('OMITTED material record' in r[0] for r in coverage.selection_reasons.values())


def test_bundle_carries_dates_tiers_plan_and_timeline():
    result = clinical_investigation()
    bundle = bundle_with(result)
    assert bundle['sources']['MED:2']['fields']['publication_date'] == '2025-01-01'
    assert bundle['sources']['MED:2']['fields']['evidence_tier'] == 'unverified'
    assert 'development_dates' in bundle['sources']['NCT00000001']['fields']
    assert bundle['evidence_plan']['stage'] == 'clinical' and {n['key'] for n in bundle['evidence_plan']['needs']} >= {'recent_development', 'negative_or_safety'}
    assert bundle['development_timeline'][0]['date'] >= bundle['development_timeline'][-1]['date']
    assert any(r['kind'] == 'registry results posted' for r in bundle['development_timeline'])


def test_prior_art_searches_question_mechanism_and_hypotheses_and_flags_answered_questions():
    result = clinical_investigation()
    result.publications.append(pub('MED:50', 'Selective GENEX inhibition and cognitive toxicity in example disease neurons',
        'We compared selective GENEX inhibition with genetic knockdown in example disease neurons and measured synaptic density and viability; cognitive toxicity tracked on-target inhibition. Conclusions: on-target GENEX inhibition reduced synaptic density.', year='2020'))
    experiment = final().experiment.model_copy(update={
        'question': 'Does selective GENEX inhibition reduce synaptic density through on-target cognitive toxicity in example disease neurons?',
        'mechanism': 'on-target GENEX inhibition versus genetic knockdown', 'measurement': 'synaptic density and viability readouts',
        'competing_explanations': ['Cognitive toxicity is on-target GENEX inhibition.', 'Cognitive toxicity is compound-specific off-target activity.']})
    client = SimpleNamespace(get=Mock(return_value={'hitCount': 0, 'resultList': {'result': []}}))
    check = check_prior_art(result, experiment, client=client)
    assert [s['facet'] for s in check['searches']] == ['question', 'mechanism_readout', 'competing_hypotheses']
    assert check['status'] == 'PRIOR_ART_OVERLAP_REQUIRES_REVIEW' and 'MED:50' in check['close_matches']
    assert check['substantially_answered_by'] == ['MED:50'] and check['decision'] == 'abstain'
    assert any('scientifically meaningful refinement' in o for o in check['objections'])
    assert check['label'].startswith('Potentially informative and unvalidated')


def test_prior_art_failed_search_is_an_objection_not_novelty():
    result = clinical_investigation()
    from devils_advocate.http_client import RetrievalError
    client = SimpleNamespace(get=Mock(side_effect=RetrievalError('down')))
    check = check_prior_art(result, final().experiment, client=client)
    assert check['status'] == 'NOVELTY_NOT_ESTABLISHED' and any('lookup failed' in o for o in check['objections']) and check['decision'] == 'abstain'
