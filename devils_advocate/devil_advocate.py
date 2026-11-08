"""Deterministic evidence pipeline; no language-model confidence as evidence."""
import json
import html
import re
from pathlib import Path
from .http_client import JsonClient, RetrievalError
from .models import Assessment, Claim, Compound, Investigation, Publication, TargetInput, SearchAudit
from .relevance import ALIASES, disease_matches, mentions
from .trial_retriever import TargetIdentityError, resolve_target, retrieve_compounds, retrieve_trials,verify_supplied_gene
from .evidence_verifier import verify_claims
from .stop_reasons import stop_reason_label
from .disease_terms import resolve_disease_terms, matches
from .precedent import retrieve_precedent
from .coverage import check_coverage
from .association import retrieve_association

def classify_concern(text: str) -> str:
    """Only classify explicit reason/evidence text, never registry status alone."""
    text = text.casefold()
    if 'feeder study' in text and 'futility' in text:
        return 'other'  # Dependent programme closure is not an independent efficacy result.
    # Negated safety language does not document an adverse outcome.
    text = re.sub(r'\b(?:no|without) (?:significant |new )?(?:safety concerns?|adverse events?|toxicity)\b', '', text)
    text = re.sub(r'\bnot (?:due to|stopped for|related to) (?:safety concerns?|toxicity|futility)\b', '', text)
    text = re.sub(r'\bnot (?:based on|related to|due to) (?:any )?safety(?: and/or efficacy)? concerns?\b', '', text)
    categories = []
    for category, pattern in [
        ('safety', r'\b(toxicity|adverse events?|safety (?:concerns?|issues)|hepatotoxicity|lack of tolerability|elevations in liver enzymes)\b'),
        ('efficacy', r'\b(futility|lack of (?:promising )?efficacy|no (?:clinical benefit|evidence of potential efficacy)|did not improve|failed to improve|did not demonstrate (?:clinical )?(?:efficacy|benefit)|failed to demonstrate (?:clinical )?(?:efficacy|benefit))\b'),
        ('operational', r'\b(recruitment|(?:slow|low) accrual|accrual limitations|enrollment difficulties|funding|business (?:decision|reasons|priorities|planning)|administrative|covid-19)\b')]:
        if re.search(pattern, text):
            categories.append(category)
    return categories[0] if len(categories) == 1 else 'other' if categories else 'unknown'

from .literature import retrieve_publications

def analyze(investigation: Investigation) -> list[Claim]:
    claims = []
    for trial in investigation.trials:
        relevance = (f'Conditions: {", ".join(trial.conditions)}. Link: {trial.relationship}. '
                     'Registry search relevance is not proof of target engagement. '
                     'Compare mechanism, selectivity, exposure and population before target-level inference.')
        for field in ['status', 'why_stopped']:
            excerpt = getattr(trial, field)
            if excerpt:
                concern = classify_concern(excerpt) if field == 'why_stopped' else 'unknown'
                claims.append(Claim(claim_id=f'{trial.nct_id}:{field}', text=excerpt, kind='fact',
                    concern=concern, stance='contradictory' if concern in ['efficacy', 'safety'] and
                    trial.relationship == 'verified' and trial.disease_match == 'matched' else 'context',
                    source_id=trial.nct_id, source_field=field, excerpt=excerpt, relevance=relevance,
                    source_url=trial.url,
                    uncertainty='Registry-documented programme concern; causality, engagement and target-level relevance remain unproven.'))
    for pub in investigation.publications:
        # Extract context without using keywords to infer therapeutic efficacy.
        # All automatically extracted publication text stays neutral pending review.
        sentences = re.split(r'(?<=[.!?])\s+', pub.abstract)
        selected = [s for s in sentences if s.strip()][:4]
        for i, sentence in enumerate(selected):
            claims.append(Claim(claim_id=f'{pub.identifier}:{i}', text=sentence, kind='fact',
                concern='unknown', source_id=pub.identifier, source_field='abstract',
                excerpt=sentence, stance='context', source_url=pub.url,
                uncertainty='Unadjudicated author-reported passage; no therapeutic conclusion established.',
                relevance=pub.relevance))
        # Titles supply discoverable supporting/contradictory context without inferring efficacy.
        claims.append(Claim(claim_id=f'{pub.identifier}:title', text=pub.title, kind='fact',
            source_id=pub.identifier, source_field='title', excerpt=pub.title,
            source_url=pub.url, relevance='Retrieved literature context; title alone cannot establish a scientific outcome.'))
    return claims

def assess_history(result: Investigation) -> list[Assessment]:
    assessments = []
    for trial in result.trials:
        category = classify_concern(trial.why_stopped)
        applicable = trial.relationship == 'verified' and trial.disease_match == 'matched'
        recommendation = 'escalate'
        rationale = 'Insufficient evidence: obtain outcome interpretation and verify target engagement before changing the target hypothesis.'
        if applicable and category in ['efficacy', 'safety']:
            recommendation = 'revise'
            rationale = 'Review the compound, exposure and population strategy in light of the documented stop reason; target invalidity is not established.'
        elif applicable and category == 'operational':
            recommendation = 'retain'
            rationale = 'Retain the biological hypothesis provisionally: this operational reason does not test target efficacy or safety.'
        assessments.append(Assessment(source_ids=[trial.nct_id], concern=category,
            historical_evidence=f'{trial.status}; recorded stop reason: {stop_reason_label(trial)}; posted outcome measures: {len(trial.outcome_records)}.',
            relevance=f'Compound match: {trial.relationship}; disease applicability: {trial.disease_match}. Conditions: {", ".join(trial.conditions)}.',
            limitations=[f'Mechanisms: {"; ".join(m for c in result.compounds if c.chembl_id in trial.compound_ids for m in c.mechanisms) or "not resolved"}. Curated mechanism is not measured engagement.',
                         f'Population comparison requires review: {trial.population[:400] or "eligibility unavailable"}',
                         'Selectivity, exposure, disease stage and endpoint interpretation have not been established.',
                         'An efficacy or safety stop is a programme concern, not proof of a target-mediated mechanism.'],
            recommendation=recommendation, rationale=rationale))
    return assessments

def investigate_target(target_input: TargetInput | dict, *, offline: bool = False,
                       client: JsonClient | None = None) -> Investigation:
    target = TargetInput.model_validate(target_input)
    if offline:
        if target.target_symbol.upper() != 'BACE1' or target.disease_name.casefold() != "alzheimer's disease":
            raise ValueError("Offline example supports only BACE1 and Alzheimer's disease.")
        data = json.loads((Path(__file__).parent / 'fixtures' / 'bace1.json').read_text(encoding='utf-8'))
        result = Investigation(target=target, mode='offline', **data)
    else:
        target=target.model_copy(update={'target_aliases':[],'protein_gene_symbols':[]})
        result = Investigation(target=target, mode='live')
        client = client or JsonClient()
        target = resolve_disease_terms(client, target, result.search_audit)
        result.target = target
        try:
            verify_supplied_gene(client,target,result.search_audit)
            result.resolved_target_id = resolve_target(client, target)
            result.search_audit.append(SearchAudit(source='ChEMBL',operation='target identity',
                url='https://www.ebi.ac.uk/chembl/api/data/target/search.json',query={'q':target.target_symbol},
                state='found' if result.resolved_target_id else 'no_results',relevant=int(bool(result.resolved_target_id))))
            result.resolution_status = 'resolved' if result.resolved_target_id else 'unknown'
            if result.resolved_target_id and target.target_aliases:
                result.search_audit.append(SearchAudit(source='ChEMBL',operation='verified target aliases',
                    url='https://www.ebi.ac.uk/chembl/api/data/target/'+result.resolved_target_id+'.json',
                    state='found',returned=len(target.target_aliases),detail='Bounded gene-symbol aliases from the exact human component, not inferred protein-family synonyms. Shared protein aliases do not establish an identical gene-level therapeutic mechanism.'))
            if result.resolved_target_id:
                result.compounds = retrieve_compounds(client, result.resolved_target_id, result.retrieval_errors, result.search_audit)
            else:
                result.missing_information.append('No unambiguous exact human ChEMBL target resolution; no target ID guessed.')
        except TargetIdentityError as exc:
            result.resolution_status = 'invalid_identifier'
            result.missing_information.append(str(exc))
            result.search_audit.append(SearchAudit(source='ChEMBL',operation='target identity',url='https://www.ebi.ac.uk/chembl/api/data/target',state='failed',detail='Supplied target identity failed validation.'))
        except RetrievalError as exc:
            result.resolution_status = 'unavailable' if not result.resolved_target_id else 'resolved'
            result.retrieval_errors.append(str(exc))
            result.search_audit.append(SearchAudit(source='ChEMBL',operation='target/compound retrieval',url='https://www.ebi.ac.uk/chembl/api/data',state='failed',detail='ChEMBL retrieval unavailable; not evidence of absent compounds or approvals.'))
        if result.resolved_target_id:
            retrieve_association(client,result)
            retrieve_precedent(client, result)
            result.trials = retrieve_trials(client, target, result.compounds, result.retrieval_errors, result.search_audit)
            try:
                refs=[p for t in result.trials if t.disease_match=='matched' and t.relationship=='verified' for p in t.publication_ids]
                result.publications = retrieve_publications(client, target, result.compounds, result.search_audit,refs,include_clinical=True)
            except RetrievalError as exc:
                result.retrieval_errors.append(str(exc))
        else:
            result.missing_information.append('Unresolved target: downstream retrieval skipped to prevent unrelated disease-only evidence.')
            result.search_audit.extend(SearchAudit(source=source,operation='downstream retrieval',url=url,state='not_searched',detail='Target identity unresolved.') for source,url in [
                ('ChEMBL','https://www.ebi.ac.uk/chembl/api/data/mechanism.json'),
                ('ClinicalTrials.gov','https://clinicaltrials.gov/api/v2/studies'),
                ('Europe PMC','https://www.ebi.ac.uk/europepmc/webservices/rest/search')])
        result.retrieval_notes.append('Bounded search: at most 30 target candidates, 300 mechanisms, 15 compounds and 100 trials/query. Literature queries/chunks return at most 40 records each, plus up to 60 registry-linked result PMIDs and one minimal fallback. Actual per-query limits and omissions are audited; not a systematic review.')
    # Recheck legacy recorded fixture applicability using the current rules.
    if offline and result.resolved_target_id:
        result.resolution_status = 'resolved'
    for trial in result.trials:
        trial.disease_match = 'matched' if matches(' '.join(trial.conditions), target) else 'uncertain'
    # Retrieval helpers retain limit warnings as notes, not failed requests.
    result.retrieval_notes.extend(n for n in result.retrieval_errors if not n.startswith('https://'))
    result.retrieval_errors = [n for n in result.retrieval_errors if n.startswith('https://')]
    if not result.compounds:
        result.missing_information.append('No curated ChEMBL mechanism compounds retrieved. This is not evidence that no relevant compounds exist; trial compound links remain unverified.')
    result.claims, result.revisions = verify_claims(result, analyze(result))
    result.assessments = assess_history(result)
    result.missing_information.extend([
        'Target validity cannot be inferred from compound or trial failure alone.',
        'Mechanism selectivity, exposure, disease stage and trial population require expert comparison.',
        'Registry results presence is not an efficacy conclusion; numerical endpoints are not automatically interpreted.',
        'Literature triage does not establish causality, negate contradictory findings or assess study quality.'])
    if not result.trials:
        result.missing_information.append('No relevant trial records retrieved; this does not establish absence of trials.')
    if not result.publications:
        result.missing_information.append('No publication evidence retrieved.')
    result.conclusion = ('Documented concerns require investigation; target-level invalidity remains unproven.'
        if any(a.recommendation == 'revise' for a in result.assessments)
        else 'insufficient evidence')
    if not offline:
        result.coverage = check_coverage(result)
        if result.coverage.status == 'INSUFFICIENT COVERAGE':
            result.conclusion = 'INSUFFICIENT COVERAGE: ' + '; '.join(result.coverage.gaps)
        elif result.coverage.pathway=='preclinical_validation':
            result.conclusion='Limited preclinical target-validation review permitted: '+result.association.explanation+' No disease-specific treatment efficacy is established.'
        else:
            result.conclusion='Clinical-precedent review permitted; interpret disease-specific trial/publication and indication evidence, including positive and negative results. Target-wide validity is not inferred.'
    return result
