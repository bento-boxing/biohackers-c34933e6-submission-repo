"""Negation-aware outcome direction, context-aware contradictions, and proposals that are never erased."""
from devils_advocate.ai_reasoning import comparability, omitted_contradictions, omitted_related, validate_ai_claim
from devils_advocate.evidence_context import directional
from devils_advocate.experiment_designer import propose_experiment, TEMPLATE_STATUS
from devils_advocate.literature import annotate
from devils_advocate.models import AICitation, AIClaim, Compound, Investigation, Publication, TargetInput, Trial

POSITIVE = r'\bsignificantly (?:reduced|improved)\b'
# Conclusion of PMID 38819839, quoted in the bug report.
MVC_MET = 'Conclusions: neither MVC, MET, or the combination significantly reduced liver fat in people with HIV.'


def test_negated_positive_phrase_is_a_null_result():
    assert directional(POSITIVE, 'neither MVC, MET, or the combination significantly reduced liver fat') == (False, True)
    assert directional(POSITIVE, 'Liver fat was not significantly reduced.') == (False, True)
    assert directional(POSITIVE, 'Maraviroc significantly reduced viral load.') == (True, False)
    # A negation in an earlier clause does not reach a later affirmative one.
    assert directional(POSITIVE, 'Although drug A did not improve fatigue, drug B significantly reduced viral load.') == (True, False)
    assert directional(POSITIVE, 'Drug A did not improve fatigue, but drug B significantly reduced viral load.') == (True, False)


def test_pmid_38819839_conclusion_is_labelled_negative_not_positive():
    pub = annotate(Publication(identifier='MED:38819839', title='Maraviroc and metformin for liver fat in HIV',
                               abstract='Randomized trial. ' + MVC_MET, url='https://europepmc.org/article/MED/38819839'))
    assert 'negative_candidate' in pub.direction_signals and 'positive_candidate' not in pub.direction_signals


TARGET = TargetInput(disease_name='HIV infectious disease', target_symbol='CCR5')


def hiv_result(*pubs):
    result = Investigation(target=TARGET, mode='live', resolved_target_id='CHEMBL274', resolution_status='resolved',
                           compounds=[Compound(chembl_id='CHEMBL1201187', name='MARAVIROC', synonyms=['Selzentry'], url='u', max_phase=4,
                                               indications=[{'approval_precedent': True, 'disease_match': 'lexical'}])],
                           publications=list(pubs))
    return result


def record(identifier, title, abstract, signal):
    return Publication(identifier=identifier, title=title, abstract=abstract, url='u', disease_match='matched',
                       evidence_scope='direct_clinical', direction_signals=[signal], cited_by_count=10)


MOTIVATE = AIClaim(claim_id='c1', kind='interpretation', concern='efficacy', stance='supporting',
    text='In treatment-experienced patients with CCR5-tropic HIV-1, maraviroc lowered viral load more than placebo (MOTIVATE).',
    citations=[AICitation(source_id='MED:1', field='conclusion_excerpt', excerpt='maraviroc significantly reduced viral load in treatment-experienced patients')],
    relevance='Approved-setting efficacy.', uncertainty='Restricted to CCR5-tropic virus.')


def test_csf_failure_in_suppressed_patients_is_related_not_contradictory():
    csf = record('MED:9', 'Maraviroc intensification and residual CSF HIV in suppressed patients',
                 'Maraviroc intensification in virologically suppressed patients did not reduce residual cerebrospinal fluid HIV RNA.', 'negative_candidate')
    result = hiv_result(csf)
    bundle = {'sources': {}, 'target': TARGET.model_dump()}
    assert omitted_related(result, bundle, MOTIVATE) == ['MED:9']
    assert omitted_contradictions(result, bundle, MOTIVATE) == []
    ok, reason = comparability(result, MOTIVATE, csf)
    assert not ok and 'suppressed' in reason
    assert not any('Material contradictory evidence' in o for o in validate_ai_claim(MOTIVATE, bundle, result))


def test_comparable_failure_still_counts_as_a_contradiction():
    same_question = record('MED:8', 'Maraviroc in treatment-experienced patients: 48-week viral load',
                           'In treatment-experienced patients, maraviroc did not reduce viral load versus placebo.', 'negative_candidate')
    result = hiv_result(same_question)
    bundle = {'sources': {}, 'target': TARGET.model_dump()}
    assert omitted_contradictions(result, bundle, MOTIVATE) == ['MED:8']
    assert any('Material contradictory evidence' in o for o in validate_ai_claim(MOTIVATE, bundle, result))


def test_live_fallback_is_a_flagged_template_not_an_abstention():
    result = hiv_result(record('MED:1', 'Maraviroc in HIV', 'Maraviroc significantly reduced viral load.', 'positive_candidate'))
    result.trials = [Trial(nct_id='NCT00098306', title='MOTIVATE 1', status='COMPLETED', conditions=['HIV Infections'], url='u')]
    experiment = propose_experiment(result)
    assert experiment.status == TEMPLATE_STATUS and experiment.competing_explanations
    assert 'MARAVIROC' in experiment.question  # scoped to the approved precedent, not a generic benefit question
    assert experiment.limitations[0].startswith('Review flag:')


def test_unresolved_target_still_abstains():
    result = Investigation(target=TARGET, mode='live', resolution_status='unknown')
    assert propose_experiment(result).status == 'INSUFFICIENT EVIDENCE FOR EXPERIMENT'
