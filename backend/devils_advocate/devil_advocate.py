"""Deterministic evidence pipeline; no language-model confidence as evidence."""
import json
import html
import re
from pathlib import Path
from .http_client import JsonClient, RetrievalError
from .models import Assessment, Claim, Compound, Investigation, Publication, TargetInput
from .relevance import ALIASES, disease_matches, mentions
from .trial_retriever import TargetIdentityError, resolve_target, retrieve_compounds, retrieve_trials
from .evidence_verifier import verify_claims
from .stop_reasons import stop_reason_label

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

def retrieve_publications(client: JsonClient, target: TargetInput, compounds: list[Compound] | None = None) -> list[Publication]:
    # Quote input safely for the Europe PMC query grammar.
    clean = lambda s: re.sub(r'[^\w\s-]', ' ', s).strip()
    terms = [target.target_symbol, *[c.name for c in compounds or []]]
    disease_terms = ALIASES.get(target.disease_name.casefold(), [target.disease_name])
    disease_query = '(' + ' OR '.join('TITLE_ABS:' + clean(term) + '*' if term in ['alzheimer', 'parkinson']
                                     else f'TITLE_ABS:"{clean(term)}"' for term in disease_terms) + ')'
    query = '(' + ' OR '.join(f'TITLE_ABS:"{clean(term)}"' for term in terms) + ')'
    query += f' AND {disease_query}'
    # Prioritize clinical challenge evidence without excluding supportive studies.
    query += ' AND (trial OR efficacy OR safety OR failure OR randomized)'
    endpoint = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search'
    page = client.get(endpoint, {'query': query, 'format': 'json', 'resultType': 'core', 'pageSize': 25})
    records = page.get('resultList', {}).get('result', [])
    if compounds:
        clinical_query = '(' + ' OR '.join(f'TITLE_ABS:"{clean(c.name)}"' for c in compounds) + ')'
        clinical_query += f' AND {disease_query} AND (TITLE:trial OR TITLE:randomized)'
        clinical = client.get(endpoint, {'query': clinical_query, 'format': 'json', 'resultType': 'core', 'pageSize': 10})
        records = clinical.get('resultList', {}).get('result', []) + records
    unique = {f"{p['source']}:{p['id']}": p for p in records}
    publications = [Publication(identifier=f"{p['source']}:{p['id']}", title=p.get('title', ''),
                        abstract=re.sub(r'</?[A-Za-z][^>]*>', '', html.unescape(p.get('abstractText', ''))),
                        doi=p.get('doi'), url=f"https://europepmc.org/article/{p['source']}/{p['id']}")
            for p in unique.values()]
    for pub in publications:
        text = pub.title + ' ' + pub.abstract
        named = any(mentions(text, name) for name in terms)
        disease = disease_matches(text, target.disease_name)
        pub.relevance = (f'Target/curated compound explicitly named: {named}; disease explicitly named: {disease}. '
                         'Lexical applicability only; study population, mechanism, direction of effect and study quality need review.')
    # Search engines can match full-text indexing outside the returned abstract.
    # Do not present those candidates as applicable evidence without visible context.
    return [p for p in publications if
            disease_matches(p.title + ' ' + p.abstract, target.disease_name) and
            any(mentions(p.title + ' ' + p.abstract, term) for term in terms)]

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
        result = Investigation(target=target, mode='live')
        client = client or JsonClient()
        try:
            result.resolved_target_id = resolve_target(client, target)
            result.resolution_status = 'resolved' if result.resolved_target_id else 'unknown'
            if result.resolved_target_id:
                result.compounds = retrieve_compounds(client, result.resolved_target_id, result.retrieval_errors)
            else:
                result.missing_information.append('No unambiguous exact human ChEMBL target resolution; no target ID guessed.')
        except TargetIdentityError as exc:
            result.resolution_status = 'invalid_identifier'
            result.missing_information.append(str(exc))
        except RetrievalError as exc:
            result.resolution_status = 'unavailable' if not result.resolved_target_id else 'resolved'
            result.retrieval_errors.append(str(exc))
        if result.resolved_target_id:
            result.trials = retrieve_trials(client, target, result.compounds, result.retrieval_errors)
            try:
                result.publications = retrieve_publications(client, target, result.compounds)
            except RetrievalError as exc:
                result.retrieval_errors.append(str(exc))
        else:
            result.missing_information.append('Unresolved target: downstream retrieval skipped to prevent unrelated disease-only evidence.')
        result.retrieval_notes.append('Bounded search: at most 30 target candidates, 300 mechanisms, 15 compounds, 100 trials/query and 35 publications; not a systematic review.')
    # Recheck legacy recorded fixture applicability using the current rules.
    if offline and result.resolved_target_id:
        result.resolution_status = 'resolved'
    for trial in result.trials:
        trial.disease_match = 'matched' if disease_matches(' '.join(trial.conditions), target.disease_name) else 'uncertain'
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
    return result
