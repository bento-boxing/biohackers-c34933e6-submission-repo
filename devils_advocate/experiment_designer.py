from .models import Experiment, Investigation

def propose_experiment(investigation: Investigation | dict) -> Experiment:
    result = Investigation.model_validate(investigation)
    if result.ai and result.ai.status == 'completed' and result.ai.experiment is not None:
        return result.ai.experiment.model_copy(deep=True)
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
    return Experiment(
        question=f'Does selective modulation of {target} produce a disease-relevant benefit in {disease} at tolerable exposure?',
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
