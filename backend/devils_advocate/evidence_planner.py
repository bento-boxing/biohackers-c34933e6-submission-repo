"""Evidence Discovery Planner and bounded gap-resolution loop.

For any disease–target pair the planner lists what an investigation must establish,
assesses each need against the records actually retrieved, issues targeted follow-up
searches for unmet needs only, and stops with a stated reason. Everything is
deterministic and auditable; an optional model suggestion is only ever a query, never
evidence. Reference findings for benchmark pairs are never encoded here.
"""
import os
import re
import time
from datetime import date, timedelta

from .association import assess_association, target_mentioned
from .disease_terms import matches, terms
from .http_client import RetrievalDeadlineExceeded, RetrievalError
from .literature import ENDPOINT, annotate, disease_query_term, publication_from_record, quoted
from .models import (Compound, EvidenceNeed, EvidencePlan, EvidenceRound, EvidenceSearch, Investigation,
                     SearchAudit, Trial)
from .relevance import mentions
from .trial_retriever import CTG, complete_trial_records

OT_GRAPHQL = 'https://api.platform.opentargets.org/api/v4/graphql'
OLS_SEARCH = 'https://www.ebi.ac.uk/ols4/api/search'

NEEDS = [
    ('target_disease_association', 'Target–disease biological association', 'both'),
    ('genetic_mechanistic', 'Genetic or mechanistic supporting evidence', 'both'),
    ('approved_therapy', 'Approved therapies and indication-specific clinical precedent', 'clinical'),
    ('positive_clinical', 'Positive clinical studies', 'clinical'),
    ('negative_or_safety', 'Negative efficacy findings and safety concerns', 'clinical'),
    ('programme_status', 'Incomplete, ongoing or discontinued programmes', 'clinical'),
    ('population_subtype', 'Relevant patient populations and disease subtypes', 'both'),
    ('recent_development', 'Recent consequential development updates', 'both'),
    ('unresolved_uncertainty', 'Important unresolved uncertainties', 'both'),
]

# Direction-neutral outcome vocabulary: positive and negative outcome words are searched together.
OUTCOME_TERMS = ['"primary endpoint"', 'efficacy', 'safety', 'tolerability', 'discontinued', 'futility',
                 '"phase 3"', '"phase 2"', '"phase 1"', 'randomized', 'randomised']
MODEL_TERMS = ['knockout', 'knockdown', '"knock-in"', 'transgenic', 'mice', 'mouse', 'zebrafish', 'iPSC',
               '"patient-derived"', 'variant', 'mutation', 'GWAS', '"loss of function"', 'CRISPR', 'siRNA']
POPULATION_TERMS = ['subgroup', 'subtype', 'carriers', 'mutation', '"treatment-naive"', '"treatment-experienced"',
                    'pediatric', 'paediatric', 'genotype', 'stage', 'refractory']
POPULATION_PATTERN = r'\b(subgroup|subtype|carriers?|mutation|variant|treatment[- ]naive|treatment[- ]experienced|p(?:a)?ediatric|genotype|stage|refractory|tropic)\b'
CONSEQUENTIAL = r'\b(primary endpoint|did not meet|failed to|futility|discontinu\w*|withdraw\w*|approv\w*|terminat\w*|halt\w*)\b'
RESERVE_SECONDS = 20


class _DeadlineDuringSearch(RetrievalDeadlineExceeded):
    def __init__(self, record):
        super().__init__('Retrieval budget exhausted during a follow-up search.')
        self.record = record


def settings() -> dict:
    def integer(name, default, low, high):
        try:
            return max(low, min(high, int(os.getenv(name, default))))
        except ValueError:
            return default
    return {'max_rounds': integer('ADAPTIVE_MAX_ROUNDS', 2, 0, 4),
            'max_searches_per_round': integer('ADAPTIVE_MAX_SEARCHES_PER_ROUND', 6, 1, 12),
            'recent_years': integer('ADAPTIVE_RECENT_YEARS', 3, 1, 10)}


def recent_cutoff(years: int, today: date | None = None) -> str:
    today = today or date.today()
    return (today - timedelta(days=365 * years)).isoformat()


def is_recent(value: str | None, cutoff: str) -> bool:
    return bool(value) and value[:10] >= cutoff[:len(value[:10])]


def advanced_compounds(result: Investigation) -> list[Compound]:
    linked = {c for t in result.trials for c in t.compound_ids}
    return sorted((c for c in result.compounds if (c.max_phase or 0) >= 2 or c.chembl_id in linked),
                  key=lambda c: (-(c.max_phase or 0), c.chembl_id))


def direct_pubs(result: Investigation, scope: str):
    return [p for p in result.publications if p.evidence_scope == scope and p.abstract]


def matched_trials(result: Investigation) -> list[Trial]:
    """Disease-matched trials linked to the target by a compound alias, an intervention mention or the
    registry's own target-term intervention index (recorded as search_terms). Linkage is not engagement."""
    names = {n.casefold() for n in [result.target.target_symbol, *result.target.target_aliases]}
    return [t for t in result.trials if t.disease_match == 'matched' and
            (t.relationship in ['verified', 'probable'] or any(target_mentioned(i, result.target) for i in t.interventions)
             or any(term.casefold() in names for term in t.search_terms))]


def identifiers(result: Investigation) -> dict:
    t = result.target
    return {'disease_name': t.disease_name, 'disease_id': t.disease_id, 'disease_aliases': len(t.disease_aliases),
            'target_symbol': t.target_symbol, 'ensembl_gene_id': t.target_id if (t.target_id or '').startswith('ENSG') else None,
            'uniprot': t.uniprot, 'chembl_target_id': result.resolved_target_id, 'target_aliases': list(t.target_aliases),
            'compound_chembl_ids': [c.chembl_id for c in result.compounds], 'trial_ids': len(result.trials),
            'caution': 'Identifiers verified against their registries where a lookup succeeded; see search audit.'}


def programme_trials(result: Investigation) -> list[Trial]:
    """Disease-matched trials with a verified/probable compound link or the target named in an intervention."""
    return [t for t in result.trials if t.disease_match == 'matched' and
            (t.relationship in ['verified', 'probable'] or any(target_mentioned(i, result.target) for i in t.interventions))]


def build_plan(result: Investigation, *, max_rounds: int | None = None) -> EvidencePlan:
    assess_association(result)
    clinical = bool(programme_trials(result) or direct_pubs(result, 'direct_clinical') or
                    any(r.get('approval_precedent') and r.get('disease_match') in ['identifier', 'lexical']
                        for c in result.compounds for r in c.indications))
    if not result.resolved_target_id and result.resolution_status != 'gene_verified':
        stage, reason = 'unresolved', 'Target identity unresolved; no disease-specific plan can be executed.'
    elif clinical:
        stage, reason = 'clinical', 'Disease-matched registry trials, interventional publications or a matched approved indication were retrieved.'
    else:
        stage, reason = 'preclinical', 'No disease-matched clinical programme retrieved; biological association, genetic and model evidence are assessed instead of clinical outcomes.'
    needs = [EvidenceNeed(key=k, label=label, applies_to=applies) for k, label, applies in NEEDS]
    plan = EvidencePlan(stage=stage, stage_reason=reason, identifiers=identifiers(result), needs=needs,
                        max_rounds=settings()['max_rounds'] if max_rounds is None else max_rounds)
    plan.limitations.append('Sponsor press releases and investor announcements are not retrieved: no permitted public API exists. '
                            'Registry status, registry-posted results, peer-reviewed publications and FDA records are the only development tiers searched.')
    if result.resolution_status == 'gene_verified':
        plan.limitations.append('No exact ChEMBL single-protein target: compound-linked trial verification and ChEMBL/FDA approval lookups are unavailable; registry records are linked by gene-symbol search only.')
    result.evidence_plan = plan
    return plan


def _searched(result: Investigation, source: str) -> dict:
    audits = [a for a in result.search_audit if a.source == source]
    return {'ok': any(a.state in ['found', 'no_results', 'limit_reached'] for a in audits),
            'failed': any(a.state == 'failed' for a in audits) and not any(a.state in ['found', 'limit_reached'] for a in audits)}


def assess_plan(result: Investigation, plan: EvidencePlan, *, today: date | None = None) -> EvidencePlan:
    """Deterministic status per need from scoped records. Failure is never absence."""
    assess_association(result)
    cutoff = recent_cutoff(settings()['recent_years'], today)
    clinical_pubs = direct_pubs(result, 'direct_clinical')
    biological = direct_pubs(result, 'direct_biological')
    trials = matched_trials(result)
    ontology = result.ontology_association or {}
    pmc, ctg = _searched(result, 'Europe PMC'), _searched(result, 'ClinicalTrials.gov')
    by_citations = lambda pubs: sorted(pubs, key=lambda p: (-p.cited_by_count, p.identifier))
    by_date = lambda pubs: sorted(pubs, key=lambda p: (p.publication_date or '', p.identifier), reverse=True)

    def set_need(key, status, ids=(), material=(), note=''):
        need = next(n for n in plan.needs if n.key == key)
        need.status, need.note = status, note
        need.evidence_ids = list(dict.fromkeys(ids))[:40]
        need.material_ids = list(dict.fromkeys(material))[:4]

    for need in plan.needs:
        if plan.stage == 'unresolved':
            set_need(need.key, 'unverifiable', note='Target identity unresolved; the need cannot be assessed.')
        elif plan.stage == 'preclinical' and need.applies_to == 'clinical':
            registry = [t.nct_id for t in trials] if need.key == 'programme_status' else []
            set_need(need.key, 'not_applicable', registry, note='No disease-matched clinical programme retrieved; assessed as a preclinical target.' +
                     (f' {len(registry)} registry record(s) matched by gene-symbol search without a verified intervention link are retained for review.' if registry else ''))
    if plan.stage == 'unresolved':
        return plan

    # Association
    direct_ids = [p.identifier for p in clinical_pubs + biological]
    if ontology.get('state') == 'found' and direct_ids:
        set_need('target_disease_association', 'satisfied', ['OT:' + str(ontology.get('target_id')) + ':' + str(ontology.get('disease_id')), *direct_ids], direct_ids[:2],
                 'Open Targets exact-pair association plus disease-specific primary sources; a descriptive score is not causal validation.')
    elif ontology.get('state') == 'found' or direct_ids:
        set_need('target_disease_association', 'partial', direct_ids or ['OT:pair'], direct_ids[:2],
                 'One association line only (ontology pair or literature); the other is missing or was not searchable with the supplied identifiers.')
    elif ontology.get('state') == 'failed' or pmc['failed']:
        set_need('target_disease_association', 'unverifiable', note='Association sources failed; this is a retrieval failure, not absence of association.')
    else:
        set_need('target_disease_association', 'unmet', note='No exact-pair association record and no disease-specific primary source retrieved.')

    # Genetic / mechanistic
    kinds = {'human_genetic_association', 'cellular_mechanistic', 'animal_model'}
    genetic = [p for p in biological if set(p.biological_signals) & kinds]
    ot_genetic = any(s.get('id') == 'genetic_association' and (s.get('score') or 0) > 0 for s in ontology.get('datatype_scores', []))
    ids = [p.identifier for p in by_citations(genetic)] + (['OT:genetic_association'] if ot_genetic else [])
    if len(genetic) >= 2 or (genetic and ot_genetic):
        set_need('genetic_mechanistic', 'satisfied', ids, [p.identifier for p in by_citations(genetic)[:2]], 'Multiple disease-specific primary biological records; locus-to-gene and model relevance still need review.')
    elif ids:
        set_need('genetic_mechanistic', 'partial', ids, ids[:1], 'A single genetic/mechanistic line; independent replication not retrieved.')
    elif pmc['failed']:
        set_need('genetic_mechanistic', 'unverifiable', note='Literature search failed.')
    else:
        set_need('genetic_mechanistic', 'unmet', note='No disease-specific genetic, cellular or model record retrieved.')

    # Approved therapy
    approved = [c for c in result.compounds if c.max_phase == 4]
    matched = [c for c in approved if any(r.get('approval_precedent') and r.get('disease_match') in ['identifier', 'lexical'] for r in c.indications)
               or any(r.get('disease_match') == 'lexical' for r in c.regulatory_approvals)]
    label_ids = [r['id'] for r in result.regulatory_records if r['id'].startswith(('SPL:', 'FDAAPP:'))]
    if plan.stage == 'clinical':
        if matched:
            set_need('approved_therapy', 'satisfied', [c.chembl_id for c in matched] + label_ids, [c.chembl_id for c in matched[:2]], 'Disease-matched approved indication or FDA record retrieved; population and product restrictions require review.')
        elif any(c.indication_search_state in ['failed', 'not_searched'] for c in approved):
            set_need('approved_therapy', 'unverifiable', [c.chembl_id for c in approved], note='Indication lookup failed for an approved compound; approval for this disease is unknown, not absent.')
        elif approved:
            set_need('approved_therapy', 'partial', [c.chembl_id for c in approved] + label_ids, note='Approved compounds exist for other indications only in the retrieved records; no disease-matched approval was found in bounded lookups.')
        else:
            set_need('approved_therapy', 'unmet', note='No phase-4 compound among the curated mechanism compounds; the bounded compound set is not exhaustive.')
    elif approved:
        set_need('approved_therapy', 'not_applicable', [c.chembl_id for c in approved], note='Other-indication approval only: pharmacological tractability, not efficacy for this disease.')

    if plan.stage == 'clinical':
        positive = [p for p in clinical_pubs if 'positive_candidate' in p.direction_signals]
        results_trials = [t for t in trials if t.has_results or t.outcome_records]
        if positive:
            set_need('positive_clinical', 'satisfied', [p.identifier for p in by_citations(positive)] + [t.nct_id for t in results_trials],
                     [p.identifier for p in by_citations(positive)[:2]], 'Disease-matched interventional publication with a positive conclusion signal (unadjudicated triage).')
        elif clinical_pubs or results_trials:
            set_need('positive_clinical', 'partial', [p.identifier for p in clinical_pubs] + [t.nct_id for t in results_trials],
                     [p.identifier for p in by_citations(clinical_pubs)[:1]], 'Interventional records retrieved without a positive conclusion signal; outcome direction needs reading.')
        elif pmc['failed'] or ctg['failed']:
            set_need('positive_clinical', 'unverifiable', note='Clinical sources failed; not evidence of absent benefit.')
        else:
            set_need('positive_clinical', 'unmet', note='No disease-matched interventional publication or results-posted trial retrieved.')

        negative = [p for p in clinical_pubs if set(p.direction_signals) & {'negative_candidate', 'safety_candidate'}]
        stopped = [t for t in trials if t.relationship == 'verified' and t.why_stopped]
        warnings = [r['id'] for r in result.regulatory_records if r['id'].startswith('SPL:') and r.get('fields', {}).get('warnings_and_cautions')]
        if negative or stopped:
            set_need('negative_or_safety', 'satisfied', [p.identifier for p in by_citations(negative)] + [t.nct_id for t in stopped] + warnings,
                     [p.identifier for p in by_citations(negative)[:2]] + [t.nct_id for t in stopped[:1]], 'Negative/safety conclusion signals or documented stop reasons retrieved; compound-specific, not target-level.')
        elif warnings or [t for t in trials if t.status in ['TERMINATED', 'WITHDRAWN', 'SUSPENDED']]:
            set_need('negative_or_safety', 'partial', warnings + [t.nct_id for t in trials if t.status in ['TERMINATED', 'WITHDRAWN', 'SUSPENDED']],
                     note='Label warnings or stopped trials without a classified reason; no negative outcome publication retrieved.')
        elif pmc['failed'] or ctg['failed']:
            set_need('negative_or_safety', 'unverifiable', note='Clinical sources failed; absence of negative findings is not established.')
        else:
            set_need('negative_or_safety', 'unmet', note='No negative efficacy or safety record retrieved in bounded searches.')

        if trials:
            set_need('programme_status', 'satisfied', [t.nct_id for t in trials], [t.nct_id for t in sorted(trials, key=lambda t: (t.last_update_date or '', t.nct_id), reverse=True)[:1]],
                     f'{len(trials)} disease-matched registry records with status; status is not outcome.')
        elif result.trials:
            set_need('programme_status', 'partial', [t.nct_id for t in result.trials], note='Registry records retrieved only with uncertain disease match.')
        elif ctg['failed']:
            set_need('programme_status', 'unverifiable', note='Registry search failed.')
        else:
            set_need('programme_status', 'unmet', note='No registry record retrieved for this pair.')

    # Population / subtype
    subtype_pubs = [p for p in clinical_pubs + biological if re.search(POPULATION_PATTERN, p.title + ' ' + p.abstract, re.I)]
    eligible = [t for t in trials if t.population]
    if subtype_pubs or eligible:
        set_need('population_subtype', 'satisfied', [p.identifier for p in subtype_pubs] + [t.nct_id for t in eligible],
                 [p.identifier for p in by_citations(subtype_pubs)[:1]], 'Population/subtype wording or eligibility text retrieved; equivalence to the requested population is not established.')
    elif clinical_pubs or biological or trials:
        set_need('population_subtype', 'partial', note='Direct records retrieved without explicit population/subtype context.')
    else:
        set_need('population_subtype', 'unverifiable' if pmc['failed'] else 'unmet', note='No direct record to read population context from.')

    # Recent development
    recent_pubs = [p for p in clinical_pubs + biological if is_recent(p.publication_date, cutoff)]
    consequential = [p for p in recent_pubs if re.search(CONSEQUENTIAL, p.title + ' ' + p.conclusion_excerpt, re.I)]
    recent_trials = [t for t in trials if is_recent(t.results_posted_date, cutoff) or (is_recent(t.last_update_date, cutoff) and t.status in ['TERMINATED', 'WITHDRAWN', 'SUSPENDED', 'COMPLETED'])]
    recent_approvals = [c.chembl_id for c in result.compounds for r in c.regulatory_approvals if any(is_recent(d, cutoff) for d in r.get('approval_dates', []))]
    if consequential or recent_approvals or (recent_pubs and recent_trials):
        set_need('recent_development', 'satisfied', [p.identifier for p in by_date(recent_pubs)] + [t.nct_id for t in recent_trials] + recent_approvals,
                 [p.identifier for p in by_date(consequential or recent_pubs)[:2]] + [t.nct_id for t in recent_trials[:1]],
                 f'Dated records since {cutoff}: tiers = peer-reviewed publications, registry updates/results, FDA approvals. Sponsor announcements not searched.')
    elif recent_pubs or recent_trials:
        set_need('recent_development', 'partial', [p.identifier for p in by_date(recent_pubs)] + [t.nct_id for t in recent_trials],
                 [p.identifier for p in by_date(recent_pubs)[:1]] + [t.nct_id for t in recent_trials[:1]], f'Some dated records since {cutoff}, none with consequential outcome wording; a recent outcome may still be unretrieved.')
    elif pmc['failed'] and ctg['failed']:
        set_need('recent_development', 'unverifiable', note='Dated sources failed.')
    else:
        set_need('recent_development', 'unmet', note=f'No direct record dated since {cutoff} retrieved. Absence in a bounded search is not absence of developments.')

    unmet = [n.key for n in plan.needs if n.status in ['unmet', 'partial', 'unverifiable'] and n.key != 'unresolved_uncertainty']
    set_need('unresolved_uncertainty', 'satisfied', note='Open needs after assessment: ' + (', '.join(unmet) or 'none') + '. Scientific uncertainties are enumerated in missing_information and by the adjudicated claims.')
    return plan


def _entity(result: Investigation, extra: list[str] = ()) -> str:
    names = list(dict.fromkeys([result.target.target_symbol, *result.target.target_aliases, *extra]))[:12]
    return '(' + ' OR '.join('TITLE_ABS:' + quoted(n) for n in names) + ')'


def _disease(result: Investigation) -> str:
    names = []
    for name in sorted(terms(result.target), key=len):
        candidate = '(' + ' OR '.join(disease_query_term(n) for n in [*names, name]) + ')'
        if len(candidate) <= 400:
            names.append(name)
    return '(' + ' OR '.join(disease_query_term(n) for n in names) + ')'


def _ors(words) -> str:
    return '(' + ' OR '.join('TITLE_ABS:' + w for w in words) + ')'


def followup_searches(result: Investigation, plan: EvidencePlan, round_number: int, *, today: date | None = None) -> list[dict]:
    """Targeted searches for unmet/partial needs only; nothing for satisfied or inapplicable needs."""
    open_needs = {n.key: n for n in plan.needs if n.status in ['unmet', 'partial'] or (n.status == 'unverifiable' and round_number == 0)}
    if plan.stage == 'unresolved' or not open_needs:
        return []
    done = {(s.source, s.operation, str(sorted(s.query.items()))) for r in plan.rounds for s in r.searches}
    sort = 'sort_date:y' if round_number else 'sort_cited:y'
    cutoff = recent_cutoff(settings()['recent_years'], today)
    disease = _disease(result)
    compounds = advanced_compounds(result)
    compound_names = [c.name for c in compounds if len(c.name) >= 4 and not c.name.startswith('CHEMBL')][:6]
    searches = []

    def add(need, source, operation, query):
        key = (source, operation, str(sorted(query.items())))
        if key in done:
            return
        done.add(key)
        searches.append({'need_key': need, 'source': source, 'operation': operation, 'query': query})

    pmc = lambda q, page=25: {'query': q, 'format': 'json', 'resultType': 'core', 'pageSize': page}
    # Explicitly authorised model suggestions run first; they are queries, never evidence.
    for suggestion in plan.planner_suggestions:
        words = [w for w in suggestion.get('terms', []) if isinstance(w, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 -]{2,40}', w)][:6]
        if words and suggestion.get('need_key') in open_needs:
            add(suggestion['need_key'], 'Europe PMC', 'model-suggested follow-up', pmc(_entity(result, compound_names) + ' AND ' + disease + ' AND ' + _ors(quoted(w) for w in words) + ' ' + sort))
    if 'target_disease_association' in open_needs:
        if not (result.target.target_id or '').startswith('ENSG'):
            add('target_disease_association', 'Open Targets', 'gene identifier resolution', {'symbol': result.target.target_symbol})
        if not result.target.disease_id:
            add('target_disease_association', 'OLS', 'disease identifier resolution', {'q': result.target.disease_name, 'ontology': 'mondo'})
        add('target_disease_association', 'Europe PMC', 'association follow-up', pmc(_entity(result) + ' AND ' + disease + ' ' + sort))
    if 'genetic_mechanistic' in open_needs:
        add('genetic_mechanistic', 'Europe PMC', 'genetic/mechanistic follow-up', pmc(_entity(result) + ' AND ' + disease + ' AND ' + _ors(MODEL_TERMS) + ' ' + sort))
    outcome_needs = [k for k in ['positive_clinical', 'negative_or_safety'] if k in open_needs]
    if outcome_needs:
        need = outcome_needs[0]
        add(need, 'Europe PMC', 'clinical outcome follow-up', pmc(_entity(result, compound_names) + ' AND ' + disease + ' AND ' + _ors(OUTCOME_TERMS) + ' ' + sort))
        for name in compound_names[:2]:
            add(need, 'Europe PMC', 'compound outcome follow-up', pmc('TITLE_ABS:' + quoted(name) + ' AND ' + disease + ' AND ' + _ors(OUTCOME_TERMS) + ' ' + sort))
        linked = [t.nct_id for t in matched_trials(result) if (t.has_results or t.status in ['COMPLETED', 'TERMINATED']) and not t.publication_ids][:10]
        if linked:
            add(need, 'Europe PMC', 'registry-linked outcome publications', pmc('(' + ' OR '.join(quoted(n) for n in linked) + ')'))
    if 'recent_development' in open_needs:
        add('recent_development', 'Europe PMC', 'recent development follow-up',
            pmc(_entity(result, compound_names) + ' AND ' + disease + ' AND FIRST_PDATE:[' + cutoff + ' TO 2100-12-31] sort_date:y'))
    if 'programme_status' in open_needs:
        add('programme_status', 'ClinicalTrials.gov', 'full-text registry follow-up',
            {'query.cond': result.target.disease_name, 'query.term': result.target.target_symbol, 'pageSize': 50, 'format': 'json'})
        for name in compound_names[:3]:
            add('programme_status', 'ClinicalTrials.gov', 'compound programme status', {'query.intr': name, 'pageSize': 25, 'format': 'json'})
    if 'population_subtype' in open_needs:
        add('population_subtype', 'Europe PMC', 'population/subtype follow-up', pmc(_entity(result, compound_names) + ' AND ' + disease + ' AND ' + _ors(POPULATION_TERMS) + ' ' + sort))
    if 'approved_therapy' in open_needs and open_needs['approved_therapy'].status == 'unverifiable':
        add('approved_therapy', 'ChEMBL', 'indication lookup retry', {'compounds': [c.chembl_id for c in result.compounds if c.max_phase == 4 and c.indication_search_state in ['failed', 'not_searched']]})
    return searches[:settings()['max_searches_per_round']]


def ingest_publications(result: Investigation, raw: list, operation: str) -> list[str]:
    names = [result.target.target_symbol, *result.target.target_aliases, *[c.name for c in result.compounds],
             *[s for c in result.compounds for s in c.synonyms if 4 <= len(s) <= 60]]
    known = {p.identifier for p in result.publications}
    new = []
    for record in raw:
        pub = publication_from_record(record, discovered_by=operation)
        if pub is None or pub.identifier in known:
            continue
        text = pub.title + ' ' + pub.abstract
        named = target_mentioned(text, result.target) or any(mentions(text, n) for n in names)
        disease = matches(text, result.target)
        if not named or not disease:
            continue  # Follow-ups keep the same visibility rules as the initial search.
        pub.disease_match = 'matched'
        pub.relevance = f'Visible entity match; disease match: matched. Retrieved by follow-up search ({operation}).'
        result.publications.append(annotate(pub))
        known.add(pub.identifier)
        new.append(pub.identifier)
    return new


def _run_search(client, result: Investigation, search: dict) -> EvidenceSearch:
    started = time.monotonic()
    source, operation, query = search['source'], search['operation'], search['query']
    record = EvidenceSearch(need_key=search['need_key'], source=source, operation=operation, query=query, state='not_searched')
    try:
        if source == 'Europe PMC':
            data = client.get(ENDPOINT, query)
            raw = data.get('resultList', {}).get('result')
            if not isinstance(raw, list):
                raise RetrievalError(ENDPOINT + ': malformed publication search')
            record.returned = len(raw)
            record.new_evidence_ids = ingest_publications(result, raw, operation)
            total = data.get('hitCount')
            record.state = 'limit_reached' if isinstance(total, int) and total > len(raw) else 'found' if raw else 'no_results'
        elif source == 'ClinicalTrials.gov':
            data = client.get(CTG, query)
            if not isinstance(data.get('studies'), list):
                raise RetrievalError(CTG + ': malformed trial search')
            known = {t.nct_id for t in result.trials}
            raw = {}
            for row in data['studies']:
                try:
                    nct = row['protocolSection']['identificationModule']['nctId']
                except (KeyError, TypeError):
                    continue
                if re.fullmatch(r'NCT\d{8}', str(nct)) and nct not in known:
                    raw[nct] = row
            record.returned = len(data['studies'])
            notes = []
            term = query.get('query.intr') or query.get('query.term') or ''
            trials = complete_trial_records(client, result.target, result.compounds, raw, notes, result.search_audit,
                                            search_terms={nct: [term] for nct in raw}) if raw else []
            for trial in trials:
                trial.disease_match = 'matched' if matches(' '.join(trial.conditions), result.target) else 'uncertain'
            result.trials.extend(trials)
            result.retrieval_notes.extend(notes)
            record.new_evidence_ids = [t.nct_id for t in trials]
            record.state = 'limit_reached' if data.get('nextPageToken') else 'found' if data['studies'] else 'no_results'
        elif source == 'Open Targets':
            data = client.post_json(OT_GRAPHQL, {'query': 'query($q:String!){ search(queryString:$q, entityNames:["target"], page:{index:0,size:5}){ hits{ id name entity } } }', 'variables': {'q': query['symbol']}})
            hits = [h for h in (data.get('data') or {}).get('search', {}).get('hits', []) if h.get('entity') == 'target' and str(h.get('name', '')).casefold() == query['symbol'].casefold() and re.fullmatch(r'ENSG\d{11}', str(h.get('id', '')))]
            record.returned = len(hits)
            if len({h['id'] for h in hits}) == 1:
                result.target.target_id = hits[0]['id']
                record.new_evidence_ids = ['ENSEMBL:' + hits[0]['id']]
                record.state = 'found'
                record.detail = 'Exact approved-symbol match; identifier used only to query the exact-pair association.'
            else:
                record.state = 'no_results'
                record.detail = 'No unique exact symbol match; no identifier guessed.'
        elif source == 'OLS':
            data = client.get(OLS_SEARCH, {'q': query['q'], 'ontology': query['ontology'], 'exact': 'true', 'rows': 5})
            docs = [d for d in data.get('response', {}).get('docs', []) if str(d.get('label', '')).casefold() == query['q'].casefold() and re.fullmatch(r'MONDO:\d+', str(d.get('obo_id', '')))]
            record.returned = len(docs)
            if len({d['obo_id'] for d in docs}) == 1:
                result.target.disease_id = docs[0]['obo_id'].replace(':', '_')
                synonyms = [s for s in docs[0].get('synonym', []) if isinstance(s, str)]
                result.target.disease_aliases = list(dict.fromkeys([*result.target.disease_aliases, *synonyms]))[:30]
                record.new_evidence_ids = ['MONDO:' + docs[0]['obo_id']]
                record.state = 'found'
                record.detail = 'Exact label match; synonyms added to the visible-context vocabulary.'
            else:
                record.state = 'no_results'
                record.detail = 'No unique exact label match; no identifier guessed.'
        elif source == 'ChEMBL':
            from .precedent import retrieve_precedent
            before = {c.chembl_id: c.indication_search_state for c in result.compounds}
            retrieve_precedent(client, result)
            record.returned = sum(1 for c in result.compounds if before.get(c.chembl_id) != c.indication_search_state)
            record.state = 'found' if record.returned else 'no_results'
        else:
            record.state = 'skipped'
            record.detail = 'No retrieval adapter for this source.'
    except RetrievalDeadlineExceeded:
        record.state = 'failed'
        record.detail = 'Retrieval budget exhausted before this search completed; not a zero-result search.'
        record.duration_seconds = round(time.monotonic() - started, 6)
        raise _DeadlineDuringSearch(record)
    except (RetrievalError, ValueError, KeyError, TypeError) as exc:
        record.state = 'failed'
        record.detail = f'Follow-up search failed ({type(exc).__name__}); not a zero-result search and not cached.'
    finally:
        record.duration_seconds = round(time.monotonic() - started, 6)
    return record


def _audit(result: Investigation, record: EvidenceSearch) -> None:
    url = {'Europe PMC': ENDPOINT, 'ClinicalTrials.gov': CTG, 'Open Targets': OT_GRAPHQL, 'OLS': OLS_SEARCH, 'ChEMBL': 'https://www.ebi.ac.uk/chembl/api/data/drug_indication.json'}.get(record.source, '')
    state = record.state if record.state != 'skipped' else 'not_searched'
    result.search_audit.append(SearchAudit(source=record.source, operation='adaptive: ' + record.operation, url=url, query=record.query,
                                           state=state, returned=record.returned, relevant=len(record.new_evidence_ids),
                                           detail=(record.detail or f'Follow-up for need {record.need_key}; {len(record.new_evidence_ids)} new records.')))


def resolve_loop(client, result: Investigation, *, max_rounds: int | None = None, planner_hook=None, on_stage=None, today: date | None = None) -> EvidencePlan:
    """Assess → targeted search → reassess, bounded; every search and stop reason is recorded."""
    started = time.monotonic()
    plan = build_plan(result, max_rounds=max_rounds)
    result.evidence_plan = plan
    assess_plan(result, plan, today=today)
    if plan.stage == 'unresolved':
        plan.stop_reason = 'target_unresolved'
    elif plan.max_rounds == 0:
        plan.stop_reason = 'follow_up_disabled'
    for round_number in range(plan.max_rounds if plan.stage != 'unresolved' else 0):
        open_before = [n.key for n in plan.needs if n.status in ['unmet', 'partial', 'unverifiable'] and n.key != 'unresolved_uncertainty']
        if not open_before:
            plan.stop_reason = 'coverage_achieved'
            break
        if planner_hook is not None and round_number == 0:
            try:
                suggestions = planner_hook(result, plan) or []
                plan.planner_suggestions = [s for s in suggestions if isinstance(s, dict)][:6]
                plan.planner = 'deterministic + model suggestions (queries only)'
            except Exception:
                plan.limitations.append('Model planning suggestion failed or was refused; deterministic follow-ups continued.')
        searches = followup_searches(result, plan, round_number, today=today)
        if not searches:
            plan.stop_reason = 'no_actionable_gaps'
            break
        remaining = getattr(client, 'remaining_seconds', lambda: None)()
        if isinstance(remaining, (int, float)) and remaining < RESERVE_SECONDS:
            plan.stop_reason = 'budget_exhausted'
            plan.limitations.append(f'Follow-up round {round_number + 1} skipped: {remaining:.0f} s of retrieval budget left. Open needs remain unverified, not absent.')
            break
        if on_stage:
            on_stage(f'Adaptive evidence round {round_number + 1}: {len(searches)} targeted searches')
        round_started = time.monotonic()
        current = EvidenceRound(round_number=round_number + 1, unmet_before=open_before)
        plan.rounds.append(current)
        try:
            # Publications may be fetched in parallel; registry/identifier searches mutate shared state sequentially.
            parallel = [s for s in searches if s['source'] == 'Europe PMC']
            serial = [s for s in searches if s['source'] != 'Europe PMC']
            mapper = getattr(client, 'map', None)
            if callable(mapper) and len(parallel) > 1:
                fetched = mapper(lambda s: (s, _fetch_only(client, s)), parallel)
                for search, data in fetched:
                    current.searches.append(_ingest_fetched(result, search, data))
            else:
                for search in parallel:
                    current.searches.append(_run_search(client, result, search))
            for search in serial:
                current.searches.append(_run_search(client, result, search))
        except RetrievalDeadlineExceeded as exc:
            if isinstance(exc, _DeadlineDuringSearch):
                current.searches.append(exc.record)
            plan.stop_reason = 'budget_exhausted'
            plan.limitations.append('Retrieval budget exhausted during a follow-up round; completed searches are recorded, the rest were not run.')
            for record in current.searches:
                _audit(result, record)
            current.duration_seconds = round(time.monotonic() - round_started, 6)
            break
        for record in current.searches:
            _audit(result, record)
            need = next(n for n in plan.needs if n.key == record.need_key)
            need.searches.append(record.operation)
        current.new_evidence_ids = [i for s in current.searches for i in s.new_evidence_ids]
        assess_plan(result, plan, today=today)
        current.unmet_after = [n.key for n in plan.needs if n.status in ['unmet', 'partial', 'unverifiable'] and n.key != 'unresolved_uncertainty']
        current.duration_seconds = round(time.monotonic() - round_started, 6)
        if not current.unmet_after:
            plan.stop_reason = 'coverage_achieved'
            break
        if not current.new_evidence_ids:
            plan.stop_reason = 'no_new_evidence'
            break
        plan.stop_reason = 'round_limit'
    plan.duration_seconds = round(time.monotonic() - started, 6)
    return plan


def _fetch_only(client, search: dict):
    try:
        return client.get(ENDPOINT, search['query'])
    except RetrievalDeadlineExceeded:
        raise
    except (RetrievalError, ValueError) as exc:
        return exc


def _ingest_fetched(result: Investigation, search: dict, data) -> EvidenceSearch:
    record = EvidenceSearch(need_key=search['need_key'], source=search['source'], operation=search['operation'], query=search['query'], state='failed')
    if isinstance(data, Exception):
        record.detail = f'Follow-up search failed ({type(data).__name__}); not a zero-result search and not cached.'
        return record
    raw = data.get('resultList', {}).get('result') if isinstance(data, dict) else None
    if not isinstance(raw, list):
        record.detail = 'Malformed publication search response; treated as failed.'
        return record
    record.returned = len(raw)
    record.new_evidence_ids = ingest_publications(result, raw, search['operation'])
    total = data.get('hitCount')
    record.state = 'limit_reached' if isinstance(total, int) and total > len(raw) else 'found' if raw else 'no_results'
    return record
