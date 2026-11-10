from .models import Experiment, Investigation

def abstain_experiment(reason: str) -> Experiment:
    return Experiment(question='Insufficient evidence to identify a meaningful unresolved experiment.',
        competing_explanations=[],model='',measurement='',controls=[],possible_results=[],
        limitations=[reason,'Existing clinical knowledge and population-specific precedent must be reviewed before proposing a novel study.'],
        decision_impact='Obtain missing clinical/indication evidence and researcher review before choosing an experiment.',
        evidence_ids=[],status='INSUFFICIENT EVIDENCE FOR EXPERIMENT')

REVIEW_FLAG = 'Review flag: '

def flag(experiment: Experiment, reason: str) -> Experiment:
    """Keep the proposal and make the concern visible; the researcher decides, the gate does not erase the design."""
    if REVIEW_FLAG + reason not in experiment.limitations:
        experiment.limitations.insert(0, REVIEW_FLAG + reason)
    return experiment

def has_design(experiment: Experiment | None) -> bool:
    return bool(experiment and experiment.status != 'INSUFFICIENT EVIDENCE FOR EXPERIMENT'
                and experiment.question.strip() and experiment.competing_explanations)

def approved_precedent(result: Investigation) -> list[str]:
    return [c.name for c in result.compounds if c.max_phase == 4 and
            any(r.get('approval_precedent') and r.get('disease_match') in ['identifier', 'lexical'] for r in c.indications)]

def check_experiment_readiness(result: Investigation, experiment: Experiment, accepted_count: int) -> Experiment:
    """Flag missing anchors, knowledge review or scope; this cannot certify scientific novelty."""
    if not has_design(experiment):return experiment
    if not accepted_count or not experiment.evidence_ids:
        flag(experiment, 'No accepted challenger claim anchors this study; its motivation is the model\'s reading of the packet, not a verified uncertainty.')
    if not experiment.knowledge_review.strip() or not experiment.unresolved_gap.strip():
        flag(experiment, 'The synthesis did not document existing knowledge and a specific unresolved gap; check novelty before proceeding.')
    import re
    if approved_precedent(result):
        broad=re.search(r'\b(?:does|can)\b.{0,150}\b(?:benefit|effective|efficacy|work)\b',experiment.question,re.I)
        scoped=re.search(r'\b(resistan\w*|subgroup|population|mechanism|selectiv\w*|toxic\w*|safety|tropism|stage|exposure|combination|dose|variant|mutation|therapeutic window)\b',experiment.question,re.I)
        if broad and not scoped:
            flag(experiment, 'A broad treatment-benefit question may repeat approved clinical precedent ('+', '.join(approved_precedent(result))+'); narrow it to an unresolved population, mechanism or safety question.')
    return experiment

TEMPLATE_STATUS = ('Rule-based template proposal: built from retrieved registry and approval records, not AI-synthesised; '
                   'unvalidated and not performed. Researcher approval required.')

def propose_experiment(investigation: Investigation | dict) -> Experiment:
    result = Investigation.model_validate(investigation)
    if result.ai and result.ai.status == 'completed' and result.ai.experiment is not None:
        return result.ai.experiment.model_copy(deep=True)
    if result.mode=='live':
        # Abstain only when there is nothing to ground a study in: an unresolved target or no records at all.
        if not (result.resolved_target_id or result.resolution_status=='gene_verified') or not (result.trials or result.publications):
            return abstain_experiment('Target identity is unresolved or no registry or literature records were retrieved; '+result.conclusion)
        experiment=template_experiment(result)
        reason={'failed':'Claude synthesis did not complete','skipped':'Claude reasoning was skipped','disabled':'Claude reasoning was not run'}.get(
            result.ai.status if result.ai else 'disabled','Claude reasoning was not run')
        return flag(experiment, reason+'; this is a rule-based template from retrieved records. Re-run with Claude or have an expert scope it.')
    return template_experiment(result)

def template_experiment(result: Investigation) -> Experiment:
    """Deterministic study template grounded in verified stop reasons and approval precedent."""
    evidence = [c.claim_id for c in result.claims if c.verified and c.source_field == 'why_stopped']
    target = result.target.target_symbol
    disease = result.target.disease_name
    concerns = {c.concern for c in result.claims if c.verified and c.stance == 'contradictory'}
    functional_readout = ('amyloid-beta processing, synaptic function and neuronal viability in a human neuronal model'
                          if target.upper() == 'BACE1' else
                          'a predeclared disease-relevant functional phenotype and viability')
    model = f'a researcher-selected human disease-relevant cellular model of {disease}'
    if target.upper() == 'LRRK2':
        model = 'a genotype-stratified human neuronal model with a suitable disease-relevant comparator'
        functional_readout = 'proximal kinase engagement, lysosomal function, neuronal phenotype and viability'
    elif target.upper() == 'PCSK9':
        model = 'a human hepatic model with functional LDL-receptor-mediated uptake'
        functional_readout = 'proximal engagement, LDL receptor availability, LDL uptake and viability'
    elif target.upper() == 'EGFR':
        model = 'molecularly stratified human lung tumour models with an appropriate non-tumour comparator'
        functional_readout = 'proximal signalling, tumour growth phenotype and comparator-cell viability'
    precedent = approved_precedent(result)
    question = (f'Which population, resistance or mechanism factors limit benefit from {target} modulation in {disease}, '
                f'given approved precedent with {", ".join(precedent[:3])}?' if precedent else
                f'Does selective modulation of {target} produce a disease-relevant benefit in {disease} at tolerable exposure?')
    return Experiment(
        question=question,
        status=TEMPLATE_STATUS if result.mode == 'live' else 'Proposed only; not performed or validated.',
        competing_explanations=[
            'Target modulation changes a proximal biomarker but does not improve the disease-relevant functional phenotype.',
            'Target modulation can improve function, but compound-specific effects or an inadequate therapeutic window obscure benefit.'] if evidence else
            ['Provisional hypothesis: selective target modulation affects a disease-relevant phenotype.',
             'Provisional alternative: modulation changes a proximal biomarker without functional benefit. These hypotheses are not inferred from documented trial failure.'],
        model=f'One comparative perturbation study in {model}; establish model suitability first.',
        measurement=f'Compare graded selective pharmacological modulation of {target} with an orthogonal genetic perturbation; measure target engagement alongside {functional_readout}. ' +
                    ('Prioritize the separation between beneficial activity and toxicity because registry evidence flags safety.' if 'safety' in concerns else
                     'Prioritize whether engagement translates into functional benefit because registry evidence flags efficacy.' if 'efficacy' in concerns else
                     'This is a provisional target-validation question because retrieved records do not establish a specific failure mechanism.'),
        controls=['Vehicle and non-targeting genetic control', 'Independent selective tool compound and genetic rescue where feasible',
                  'Matched target engagement and exposure checks', 'Healthy comparator and assay positive control; independent biological replicates and blinded analysis'],
        possible_results=[
            'Concordant engagement without functional improvement weakens the model-specific causal hypothesis.',
            'Genetic benefit with compound-only toxicity motivates chemistry or selectivity revision.',
            'Concordant functional improvement without viability loss supports further validation, not clinical efficacy.',
            'Absent engagement or failed assay controls makes the study inconclusive.'],
        limitations=['Hypotheses are proposed interpretations, not established causes of previous trial outcomes.',
                     'Cell models do not reproduce clinical disease stage, chronic exposure or patient heterogeneity.',
                     'Genetic perturbation may differ from pharmacology; off-target and model effects remain possible.',
                     'Insufficient evidence: validate the model and obtain missing clinical context before execution.' if not evidence else
                     'Retrieved records ground the question but do not validate this experimental design.'],
        decision_impact='Investigate if orthogonal effects agree; revise chemistry/model if effects diverge; consider stopping this model-specific approach only after controls and independent replication.',
        evidence_ids=evidence)
