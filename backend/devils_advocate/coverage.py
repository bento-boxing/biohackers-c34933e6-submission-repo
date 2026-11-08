"""Deterministic balanced selection and coverage gates; no efficacy inference."""
import os,time,re
from .models import EvidenceCoverage, Investigation, Trial, Publication
from .association import assess_association, target_mentioned,aggregate_publication

def relevant_trials(result: Investigation) -> list[Trial]:
    return [t for t in result.trials if t.disease_match=='matched' and
        (t.relationship=='verified' or any(target_mentioned(i,result.target) for i in t.interventions))]

def material_extra_limit() -> int:
    try:return max(0,min(12,int(os.getenv('AI_MAX_MATERIAL_EXTRA','6'))))
    except ValueError:return 6

def material_records(result: Investigation) -> dict[str,list[str]]:
    """Planner-flagged records the packet must not silently drop: {source_id: [need keys]}.

    Ordered round-robin by need (each need's first material record before any need's second), so a
    bounded extra allowance represents every need before deepening any one of them."""
    flagged: dict[str,list[str]]={}
    needs=[n for n in (result.evidence_plan.needs if result.evidence_plan else []) if n.material_ids]
    for rank in range(max((len(n.material_ids) for n in needs),default=0)):
        for need in needs:
            if rank<len(need.material_ids):
                identifier=need.material_ids[rank]
                if identifier.startswith(('NCT','MED:','PMC:','PPR:')):flagged.setdefault(identifier,[]).append(need.key)
    return flagged

def unrepresented_needs(result: Investigation,selected: list[str]) -> list[str]:
    """Needs whose material records are all missing from the packet (the packet carries nothing for them)."""
    chosen=set(selected)
    out=[]
    for n in (result.evidence_plan.needs if result.evidence_plan else []):
        records=[i for i in n.material_ids if i.startswith(('NCT','MED:','PMC:','PPR:'))]  # compounds/ontology rows always travel with the bundle
        if records and not set(records)&chosen:out.append(n.key)
    return out

def select_evidence(result: Investigation,max_trials: int=6,max_publications: int=4) -> tuple[list[Trial],list[Publication],dict[str,list[str]]]:
    from .devil_advocate import classify_concern
    approved={c.chembl_id for c in result.compounds if c.max_phase==4}
    reasons={}
    selected=[]
    def choose(items,limit,reason):
        for item in items:
            key=getattr(item,'nct_id',None) or item.identifier
            if key not in reasons and len(selected)<limit:
                selected.append(item);reasons[key]=[reason]
                return
    ranked=sorted(result.trials,key=lambda t:(t.disease_match!='matched',t.relationship!='verified',
        not bool(set(t.compound_ids)&approved),not t.has_results,not bool(t.outcome_records),
        -max([int(p[-1]) for p in t.phases if p[-1:].isdigit()] or [0]),t.nct_id))
    applicable=[t for t in ranked if t.disease_match=='matched' and t.relationship=='verified']
    choose([t for t in applicable if set(t.compound_ids)&approved],max_trials,'Approved-compound precedent; status does not determine outcome')
    choose([t for t in applicable if t.has_results or t.outcome_records],max_trials,'Posted results available; direction requires interpretation')
    for concern in ['efficacy','safety','operational','unknown']:
        choose([t for t in applicable if classify_concern(t.why_stopped)==concern],max_trials,'Stop-reason stratum: '+concern)
    for trial in ranked:
        choose([trial],max_trials,'Relevance, verified alias, approval precedent, results, phase, stable NCT order')
    trials=selected;selected=[]
    # Keep reasons separately because publication selection has its own capacity.
    assess_association(result)
    for p in result.publications:
        if aggregate_publication(p):reasons[p.identifier]=['Excluded from model packet: bundled conference/session record, not a coherent primary source; full record retained as a lead.']
    pubs=sorted((p for p in result.publications if not aggregate_publication(p)),key=lambda p:(p.evidence_scope not in ['direct_clinical','direct_biological'],p.disease_match!='matched',not p.clinical_candidate,not bool(p.conclusion_excerpt),-p.cited_by_count,p.identifier))
    if not relevant_trials(result):
        for kind in ['human_genetic_association','cellular_mechanistic','animal_model']:
            choose([p for p in pubs if p.evidence_scope=='direct_biological' and kind in p.biological_signals],max_publications,'Disease-specific biological stratum: '+kind)
    for signal in ['positive_candidate','negative_candidate','safety_candidate','compound_limitation_candidate']:
        choose([p for p in pubs if signal in p.direction_signals],max_publications,'Unadjudicated conclusion stratum: '+signal)
    choose([p for p in pubs if not p.clinical_candidate],max_publications,'Mechanistic/context stratum; no therapeutic outcome assumed')
    for pub in pubs:choose([pub],max_publications,'Disease match, clinical context, conclusion, citation count, stable ID; citation count is not study quality')
    # Material records flagged by the evidence planner enter beyond the stratified cutoff (bounded),
    # so an important source is never omitted merely because it fell past the cutoff.
    extra=material_extra_limit();added=0
    by_id={t.nct_id:t for t in result.trials};by_id.update({p.identifier:p for p in result.publications if not aggregate_publication(p)})
    for identifier,needs in material_records(result).items():
        if identifier in reasons or identifier not in by_id:continue
        if added>=extra:
            reasons[identifier]=['OMITTED material record: planner need(s) '+', '.join(needs)+' flagged it but the packet extra-record limit ('+str(extra)+') was reached; retained in the full investigation.']
            continue
        item=by_id[identifier];added+=1
        (trials if isinstance(item,Trial) else selected).append(item)
        reasons[identifier]=['Planner material record for need(s): '+', '.join(needs)+'; included beyond the stratified cutoff. Selection is not an outcome judgement.']
    return trials,selected,reasons

def check_coverage(result: Investigation,max_trials: int=6,max_publications: int=4) -> EvidenceCoverage:
    started=time.monotonic()
    result.association=assess_association(result)
    clinical_trials=relevant_trials(result)
    clinical_pubs=[p for p in result.publications if p.evidence_scope=='direct_clinical' and p.abstract]
    pathway='clinical_precedent' if clinical_trials or clinical_pubs else 'preclinical_validation' if result.association.strength=='exploratory' else 'unresolved'
    trials,pubs,reasons=select_evidence(result,max_trials,max_publications)
    selected=[t.nct_id for t in trials]+[p.identifier for p in pubs]
    all_ids=[t.nct_id for t in result.trials]+[p.identifier for p in result.publications]
    approved=[c for c in result.compounds if c.max_phase==4]
    gaps=[];facets={}
    for source in ['ChEMBL','ClinicalTrials.gov','Europe PMC','OLS','openFDA','Open Targets','Ensembl']:
        searches=[a for a in result.search_audit if a.source==source]
        facets[source]={'states':sorted({a.state for a in searches}) or ['not_searched'],
            'queries':len(searches),'limited':any(a.state=='limit_reached' for a in searches)}
    if not result.resolved_target_id and result.resolution_status!='gene_verified':gaps.append('Exact target identity unresolved.')
    if result.resolution_status=='gene_verified':
        facets['target_identity_note']='Gene verified by its registry; ChEMBL curates no exact single-protein mechanism target, so compound-linked precedent and approval lookups are unavailable from ChEMBL. Registry and literature evidence are gene-symbol based.'
    invalid_disease=[a for a in result.search_audit if a.source=='OLS' and a.operation=='disease synonyms' and a.state=='no_results']
    if result.target.disease_id and invalid_disease:
        gaps.append('Supplied disease identifier was not found in the ontology registry; correct or remove it before paid reasoning. Label-based evidence does not verify the identifier.')
    if result.target.disease_id and any(a.source=='OLS' and a.operation=='disease synonyms' and a.state=='failed' for a in result.search_audit):
        gaps.append('Supplied disease identifier could not be verified because ontology lookup failed; this is not evidence that the identifier is absent. Verify it before paid reasoning.')
    ensembl_failed=any(a.source=='Ensembl' and a.operation=='gene identity' and a.state=='failed' for a in result.search_audit)
    # The exact-pair Open Targets query checks gene id + approved symbol even when no association row exists.
    if ensembl_failed and not any(a.source=='Ensembl' and a.operation=='gene identity' and a.state=='found' for a in result.search_audit) and (result.ontology_association or {}).get('state') not in ['found','no_results']:
        gaps.append('Supplied gene identifier could not be verified (gene registry lookup failed and no exact-pair association confirmed the symbol); this is a retrieval failure, not evidence of a wrong identifier. Retry or verify before paid reasoning.')
    if result.target.disease_id and not re.fullmatch(r'(?:MONDO|EFO)[:_]\d+',result.target.disease_id):
        gaps.append('Supplied disease identifier namespace/format is unsupported by the identity checker; verify or remove it before paid reasoning.')
    facets['target_identity']={'protein_gene_symbols':result.target.protein_gene_symbols,
        'caution':'A shared protein component is not a gene-specific drug mechanism; distinguish gene replacement from paralog splicing/regulation.' if len(result.target.protein_gene_symbols)>1 else 'Exact requested symbol; aliases are verified component synonyms, not clinical efficacy evidence.'}
    for source in ['ClinicalTrials.gov','Europe PMC']:
        if not set(facets[source]['states'])&{'found','no_results','limit_reached'}:
            gaps.append(source+' search missing or failed; cannot establish pathway coverage.')
    if pathway=='clinical_precedent':
        if not clinical_pubs:gaps.append('No disease-specific interventional clinical publication with abstract retrieved.')
        if not clinical_trials:gaps.append('No verified compound/target-linked registry trial with a visible disease match; clinical population applicability unresolved.')
        if clinical_pubs and not any(p in pubs for p in clinical_pubs):gaps.append('All disease-specific interventional clinical publications excluded from packet.')
        if any(c.max_phase is None for c in result.compounds):gaps.append('Some compound approval metadata is missing.')
        if any(c.indication_search_state in ['not_searched','failed'] for c in approved):
            gaps.append('Approved-compound indication lookup missing/failed; approval cannot be assigned to this disease.')
    elif pathway=='preclinical_validation':
        sent=result.model_copy(deep=True);sent.publications=pubs
        if assess_association(sent).strength!='exploratory':gaps.append('Selected packet lacks multiple primary disease-specific biological study groups and functional/genetic/model evidence.')
    else:
        gaps.append(result.association.explanation)
    facets['biological_association']=result.association.model_dump(mode='json')
    facets['pathway']={'selected':pathway,'clinical_trial_ids':[t.nct_id for t in clinical_trials],
        'clinical_publication_ids':[p.identifier for p in clinical_pubs],
        'meaning':'Clinical programmes use clinical coverage; exploratory biology does not require trials, approval or clinical efficacy evidence.'}
    facets['approved_precedent']={'ids':[c.chembl_id for c in approved],
        'meaning':'Phase 4 in ChEMBL for some indication; current authorisation/withdrawal and population require review, not inferred from phase alone.',
        'disease_matched_indications':[r for c in approved for r in c.indications if r.get('disease_match') in ['identifier','lexical'] and r.get('approval_precedent')]}
    for signal in ['positive_candidate','negative_candidate','safety_candidate','compound_limitation_candidate']:
        found=[p.identifier for p in result.publications if signal in p.direction_signals]
        sent=[p.identifier for p in pubs if signal in p.direction_signals]
        facets[signal]={'retrieved':found,'included':sent,'omitted':[i for i in found if i not in sent],
            'meaning':'Conclusion-text triage candidates, not independently verified clinical outcomes.'}
        applicable=[p.identifier for p in result.publications if signal in p.direction_signals and p.evidence_scope in ['direct_clinical','direct_biological']]
        if applicable and not set(applicable)&set(sent):gaps.append(signal+' disease-specific evidence retrieved but excluded from packet.')
    facets['trial_results']={'retrieved':[t.nct_id for t in result.trials if t.has_results or t.outcome_records],
        'included':[t.nct_id for t in trials if t.has_results or t.outcome_records],
        'meaning':'Results availability is not success; stopping status is not failure.'}
    if facets['trial_results']['retrieved'] and not facets['trial_results']['included']:gaps.append('All posted-result trials excluded from packet.')
    plan=result.evidence_plan
    if plan is not None:
        flagged=material_records(result)
        omitted_material=[i for i in flagged if i not in selected]
        facets['evidence_plan']={'stage':plan.stage,'stop_reason':plan.stop_reason,'rounds':len(plan.rounds),
            'needs':{n.key:n.status for n in plan.needs},'open_needs':[n.key for n in plan.needs if n.status in ['unmet','partial','unverifiable']],
            'material_included':[i for i in flagged if i in selected],'material_omitted':omitted_material,
            'follow_up_searches':sum(len(r.searches) for r in plan.rounds),'new_evidence':sum(len(r.new_evidence_ids) for r in plan.rounds),
            'meaning':'Need statuses are deterministic retrieval-coverage labels, not scientific verdicts; unmet after bounded search is not absence.'}
        unrepresented=unrepresented_needs(result,selected)
        facets['evidence_plan']['unrepresented_needs']=unrepresented
        if unrepresented:gaps.append('Evidence need(s) with no representative record in the packet: '+', '.join(unrepresented)+' (flagged records '+', '.join(i for i in omitted_material if any(k in unrepresented for k in flagged[i]))+'). Raise AI_MAX_MATERIAL_EXTRA or review them before paid reasoning.')
        if plan.stage=='clinical' and any(n.key=='recent_development' and n.status=='unverifiable' for n in plan.needs):
            gaps.append('Recent development sources failed; recency of the evidence packet is unverified.')
    facets['population']={'state':'requires_review','detail':'Lexical disease/compound matches do not establish population equivalence; retain eligibility text and indication restrictions.'}
    facets['stop_reasons']={'reported':[t.nct_id for t in result.trials if t.why_stopped],
        'unavailable':[t.nct_id for t in result.trials if t.stop_reason.state in ['api_error','invalid','record_missing']]}
    facets['sampling']={'policy':'Deterministic stratified bounded sample; not statistically representative or exhaustive.',
        'limits':[a.model_dump(mode='json') for a in result.search_audit if a.state=='limit_reached']}
    return EvidenceCoverage(status='INSUFFICIENT COVERAGE' if gaps else 'BOUNDED REVIEW',gaps=gaps,
        pathway=pathway,reasoning_permitted=not gaps,
        facets=facets,selected_source_ids=selected,omitted_source_ids=[i for i in all_ids if i not in selected],
        selection_reasons=reasons,duration_seconds=round(time.monotonic()-started,6))

def target_level_objections(text: str) -> list[str]:
    """Defense in depth; semantic scope also remains subject to the adjudicator."""
    import re
    text=re.sub(r'\b(?:(?:does not|cannot) (?:establish|prove|show|demonstrate|mean|imply) (?:that )?|no evidence that )(?:the )?target (?:is )?(?:invalid|ineffective|disproven)\b','',text,flags=re.I)
    issues=[]
    if re.search(r'\b(?:target (?:is |has been )?(?:invalid|ineffective|disproven)|invalidates? (?:the )?target|no (?:therapeutic|clinical) (?:value|utility))\b',text,re.I):
        issues.append('Target-level invalidity exceeds this bounded evidence packet; make a compound/disease/population-specific claim.')
    if re.search(r'\b(?:in all patients|all patients|every patient|always|never (?:effective|works)|universally|in all cases|cures?\b|the only (?:effective|viable|possible)|proven to (?:cure|work in all))\b',text,re.I) and not re.search(r'\b(?:not (?:in )?all|cannot be generalized|does not apply to all)\b',text,re.I):
        issues.append('Universal or exclusive claim exceeds the bounded packet: restrict the statement to the studied compound, population and disease stage.')
    return issues
