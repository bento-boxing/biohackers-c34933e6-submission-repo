"""General identity/alias regressions found by the live cross-disease audit."""
from unittest.mock import Mock,patch
from devils_advocate.models import TargetInput,Publication,SearchAudit
from devils_advocate.trial_retriever import resolve_target
from devils_advocate.association import scope_publication
from devils_advocate.coverage import check_coverage
from devils_advocate.ai_reasoning import run_ai_reasoning
from devils_advocate.devil_advocate import investigate_target
from .test_ai import investigation,settings
from .test_pipeline import FakeClient

def test_verified_gene_alias_supports_retrieval_and_biological_scope():
    target=TargetInput(disease_name='Example syndrome',target_symbol='GENEX')
    record={'target_chembl_id':'CHEMBL1','organism':'Homo sapiens','target_type':'SINGLE PROTEIN',
        'target_components':[{'target_component_synonyms':[
            {'component_synonym':'GENEX','syn_type':'GENE_SYMBOL'},
            {'component_synonym':'ALTGENE','syn_type':'GENE_SYMBOL_OTHER'},
            {'component_synonym':'Unverified descriptive class','syn_type':'UNIPROT'}]}]}
    assert resolve_target(FakeClient([{'targets':[record]}]),target)=='CHEMBL1'
    assert target.target_aliases==['ALTGENE']
    i=investigation();i.target=target
    p=Publication(identifier='MED:1',url='https://example.org',title='ALTGENE rescue in Example syndrome neurons',
        abstract='Overexpression of ALTGENE rescued functional deficits in cultured neurons from Example syndrome.')
    assert scope_publication(p,i)[0]=='direct_biological'

def test_confirmed_invalid_disease_id_blocks_paid_runner_even_with_good_clinical_sources():
    i=investigation();i.target.disease_id='MONDO_999999999'
    i.search_audit.append(SearchAudit(source='OLS',operation='disease synonyms',url='https://example.org',state='no_results'))
    assert any('identifier was not found' in s for s in check_coverage(i).gaps)
    with patch('devils_advocate.ai_reasoning.ClaudeRunner',side_effect=AssertionError('paid call forbidden')):
        report=run_ai_reasoning(i,settings=settings())
    assert report.status=='skipped' and not report.calls

def test_ontology_api_outage_is_not_a_confirmed_nonexistent_id():
    i=investigation();i.target.disease_id='MONDO_0004975'
    i.search_audit.append(SearchAudit(source='OLS',operation='disease synonyms',url='https://example.org',state='failed'))
    assert not any('identifier was not found' in s for s in check_coverage(i).gaps)
    assert any('could not be verified' in s for s in check_coverage(i).gaps)

def test_ontology_404_is_not_generic_transport_failure():
    from devils_advocate.disease_terms import resolve_disease_terms
    from devils_advocate.http_client import RetrievalError
    target=TargetInput(disease_name='Example',disease_id='MONDO_999999999',target_symbol='GENEX');audits=[]
    resolve_disease_terms(FakeClient([RetrievalError('not found',status_code=404)]),target,audits)
    assert audits[0].state=='no_results' and audits[0].query=={'obo_id':'MONDO:999999999'}

def test_wrong_ensembl_identity_blocks_the_actual_investigator_before_compounds():
    client=Mock();client.get.return_value={'id':'ENSG00000160791','species':'homo_sapiens','display_name':'OTHERGENE'}
    result=investigate_target({'disease_name':'Example','target_symbol':'GENEX','target_id':'ENSG00000160791'},client=client)
    assert result.resolution_status=='invalid_identifier' and result.resolved_target_id is None
    assert not result.coverage.reasoning_permitted and client.get.call_count==1

def test_recent_clinical_search_is_balanced_by_foundational_query_without_known_compounds():
    from devils_advocate.literature import retrieve_publications
    target=TargetInput(disease_name='Example syndrome',target_symbol='GENEX',target_aliases=['ALTGENE'])
    client=Mock();client.get.return_value={'hitCount':0,'resultList':{'result':[]}}
    retrieve_publications(client,target,include_clinical=True)
    queries=[call.args[1]['query'] for call in client.get.call_args_list]
    assert any('sort_cited:y' in q and 'ALTGENE' in q and 'Example syndrome' in q for q in queries)

def test_short_uppercase_disease_acronym_retained_for_infection_suffix():
    from devils_advocate.disease_terms import terms
    assert 'ABC' in terms(TargetInput(disease_name='ABC infection',target_symbol='GENEX'))
    assert 'urinary tract' not in terms(TargetInput(disease_name='urinary tract infection',target_symbol='GENEX'))

def test_shared_protein_does_not_expand_to_another_canonical_gene_or_ambiguous_alias():
    target=TargetInput(disease_name='Example',target_symbol='GENEX')
    record={'target_chembl_id':'CHEMBL1','organism':'Homo sapiens','target_type':'SINGLE PROTEIN',
        'target_components':[{'target_component_synonyms':[
            {'component_synonym':'GENEX','syn_type':'GENE_SYMBOL'},
            {'component_synonym':'GENEY','syn_type':'GENE_SYMBOL'},
            {'component_synonym':'SHARED','syn_type':'GENE_SYMBOL_OTHER'}]}]}
    assert resolve_target(FakeClient([{'targets':[record]}]),target)=='CHEMBL1'
    assert target.protein_gene_symbols==['GENEX','GENEY'] and target.target_aliases==[]

def test_possessive_disease_is_not_split_into_a_spurious_s_token():
    from devils_advocate.literature import quoted,disease_query_term
    assert quoted("Example's disease")=='''"Example's disease"'''
    clause=disease_query_term("Example's disease")
    assert 'TITLE_ABS:Example*' in clause and 'Example s disease' not in clause

def test_ensembl_wrong_record_cannot_be_persisted_as_verified_response():
    from devils_advocate.source_cache import verified_response
    assert not verified_response('https://rest.ensembl.org/lookup/id/ENSG00000160791',
        {'id':'ENSG00000169174','species':'homo_sapiens','display_name':'OTHER'})

def test_bundled_conference_record_is_retained_but_cannot_ground_clinical_or_biological_assessment():
    from devils_advocate.literature import annotate
    from devils_advocate.coverage import select_evidence
    i=investigation();pub=Publication(identifier='PMC:aggregate',title='Poster Session B',url='https://example.org',
        abstract='Randomized BACE1 inhibitor trial in patients with Alzheimer disease. Conclusions: significantly improved function.',study_types=['Abstract'])
    i.publications=[annotate(pub)]
    assert scope_publication(pub,i)[0]=='indirect_mechanistic'
    _,selected,reasons=select_evidence(i)
    assert not selected and len(i.publications)==1 and 'bundled' in reasons[pub.identifier][0]

def test_primary_early_human_trial_is_not_demoted_to_cellular_biology():
    from devils_advocate.association import interventional
    pub=Publication(identifier='MED:1',url='https://example.org',title='Clinical evaluation of a kinase inhibitor',
        abstract='In phase 1 and phase 1b clinical trials in 122 healthy volunteers and in 28 patients, the inhibitor engaged its target.')
    assert interventional(pub)

def test_biologic_suffix_requires_matching_curated_brand_and_preserves_distinct_products():
    from devils_advocate.precedent import label_identity_match
    from devils_advocate.models import Compound
    c=Compound(chembl_id='CHEMBL1',name='GENE THERAPY',synonyms=['Knownbrand'],url='https://example.org')
    good={'openfda':{'generic_name':['GENE THERAPY-ABCD'],'brand_name':['Knownbrand']}}
    other={'openfda':{'generic_name':['GENE THERAPY-EFGH'],'brand_name':['Otherbrand']}}
    assert label_identity_match(c,good)=='curated_brand_and_generic_base_with_FDA_suffix'
    assert label_identity_match(c,other)=='probable_generic_base_suffix_variant_not_interchangeable'

def test_bounded_packet_cannot_establish_unperformed_research_as_a_fact():
    from .test_ai import claim
    from devils_advocate.ai_reasoning import validate_ai_claim
    c=claim().model_copy(update={'uncertainty':'It remains untested in vivo whether selective modulation restores function.'})
    bundle={'sources':{'NCT01739348':{'fields':{'status':'TERMINATED'},'url':'https://example.org'}}}
    assert any('literature-absence' in s for s in validate_ai_claim(c,bundle))

def test_targeted_prior_art_uses_verified_gene_aliases():
    from types import SimpleNamespace
    from .test_ai import final
    from devils_advocate.prior_art import check_prior_art
    i=investigation();i.target.target_aliases=['ALTGENE']
    client=SimpleNamespace(get=Mock(return_value={'hitCount':0,'resultList':{'result':[]}}))
    check_prior_art(i,final().experiment,client=client)
    assert 'TITLE_ABS:"ALTGENE"' in client.get.call_args.args[1]['query']

def test_rejected_final_output_remains_available_for_audit_and_is_not_an_accepted_experiment():
    from .test_ai import draft,adjudication,final,ScriptedRunner
    from devils_advocate.models import AICitation
    response=final();response.experiment.prior_art_citations=[AICitation(source_id='MED:999',field='abstract',excerpt='Unsupported')]
    runner=ScriptedRunner([draft(),adjudication(),response])
    report=run_ai_reasoning(investigation(),settings=settings(),runner=runner)
    assert report.status=='failed' and report.experiment is None and report.final_draft is not None
    assert report.packet_audit['final_citation_objections'][0]['source_id']=='MED:999'

def test_original_fda_approval_is_separate_from_historical_chembl_phase():
    from devils_advocate.precedent import record_application_approval
    from devils_advocate.models import Compound
    i=investigation();c=Compound(chembl_id='CHEMBL1',name='Exampledrug',url='https://example.org',max_phase=3)
    client=FakeClient([{'results':[{'application_number':'BLA123456','submissions':[{'submission_type':'ORIG','submission_status':'AP','submission_status_date':'20251212'}]}]}])
    label={'openfda':{'application_number':['BLA123456'],'generic_name':['Exampledrug-abcd']}}
    record_application_approval(client,i,c,label,{'indications_and_usage':"Alzheimer's disease"})
    assert c.max_phase==3 and c.regulatory_approvals[0]['application_number']=='BLA123456'
    assert i.regulatory_records[-1]['id']=='FDAAPP:BLA123456'
