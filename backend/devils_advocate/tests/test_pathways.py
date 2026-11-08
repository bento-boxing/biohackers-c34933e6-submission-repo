"""Clinical, exploratory and unsupported coverage, with full job round trips."""
import json
from pathlib import Path
from unittest.mock import Mock,patch
import pytest
from devils_advocate.models import Investigation,TargetInput,AIClaim,AICitation,ChallengeDraft
from devils_advocate.association import assess_association,retrieve_association
from devils_advocate.coverage import check_coverage
from devils_advocate.ai_reasoning import run_ai_reasoning,evidence_bundle
from devils_advocate.server import create_app
from devils_advocate.literature import retrieve_publications
from devils_advocate.http_client import RetrievalError
from .test_ai import settings,ScriptedRunner,adjudication,final

FIXTURES=Path(__file__).parents[1]/'fixtures'

def case(name):
    return Investigation.model_validate_json((FIXTURES/f'pathway_{name}.json').read_text(encoding='utf-8'))

def test_exploratory_biology_needs_no_clinical_trials_or_approved_indication():
    i=case('exploratory');assert not i.trials
    coverage=check_coverage(i)
    assert coverage.status=='BOUNDED REVIEW' and coverage.pathway=='preclinical_validation' and coverage.reasoning_permitted
    assert i.association.strength=='exploratory'
    assert 'MED:31337422' in i.association.direct_source_ids
    assert 'MED:33209193' in i.association.indirect_source_ids  # scoliosis tissue is contextual in an IDD study
    assert 'MED:38750761' in i.association.indirect_source_ids  # environmental fish toxicity is not scoliosis validation
    i.coverage=coverage;packet=evidence_bundle(i,settings())
    assert packet['assessment_pathway']=='preclinical_validation'
    assert not any(s.get('precedent') for s in packet['sources'].values())
    assert not any(key.startswith('SPL:') for key in packet['sources'])

def test_preprint_and_published_versions_do_not_count_twice():
    i=case('exploratory');pub=i.publications[0]
    i.publications=[pub,pub.model_copy(update={'identifier':'PPR:alternate','doi':'10.example/preprint'})]
    assert assess_association(i).independent_groups==1
    assert check_coverage(i).status=='INSUFFICIENT COVERAGE'

def test_same_doi_with_different_titles_does_not_count_twice():
    i=case('exploratory');pub=i.publications[0];pub.doi='10.example/same'
    i.publications=[pub,pub.model_copy(update={'identifier':'PMC:other','title':pub.title+' Updated'})]
    assert assess_association(i).independent_groups==1

def test_druggability_is_not_disease_target_biology():
    i=case('exploratory');i.target=TargetInput(disease_name='Invented unsupported condition',target_symbol='BCL2',chembl_target_id='CHEMBL4860')
    # Even unrelated cancer pharmacology and approvals do not qualify.
    a=assess_association(i);coverage=check_coverage(i)
    assert a.strength=='insufficient' and not a.direct_source_ids
    assert coverage.pathway=='unresolved' and not coverage.reasoning_permitted
    with patch('devils_advocate.ai_reasoning.GeminiRunner',side_effect=AssertionError('paid forbidden')):
        report=run_ai_reasoning(i,settings=settings())
    assert report.status=='skipped' and not report.calls

def test_verified_clinical_case_permits_reasoning_and_keeps_both_directions():
    i=case('clinical');c=check_coverage(i)
    assert c.pathway=='clinical_precedent' and c.reasoning_permitted
    assert {'MED:18832244','MED:20151839'}<=set(c.selected_source_ids)
    assert i.association.strength=='clinical_context'

def test_failed_optional_query_does_not_erase_verified_retrieval():
    from devils_advocate.models import SearchAudit
    i=case('clinical');i.search_audit.append(SearchAudit(source='Europe PMC',operation='optional broad query',url='https://europepmc.org',state='failed'))
    c=check_coverage(i)
    assert c.reasoning_permitted and 'failed' in c.facets['Europe PMC']['states']
    i.search_audit=[a for a in i.search_audit if a.source!='Europe PMC' or a.state=='failed']
    assert not check_coverage(i).reasoning_permitted

@pytest.mark.parametrize('name,expected_path',[('clinical','clinical_precedent'),('exploratory','preclinical_validation')])
def test_production_investigation_returns_pathway_coverage_and_provenance(tmp_path,monkeypatch,name,expected_path):
    monkeypatch.setenv('AI_ENABLED','false')
    record=case(name);record.coverage=check_coverage(record)
    app=create_app(tmp_path,investigator=Mock(return_value=record))
    client=app.test_client();headers={'X-Research-Mode':'live'}
    with patch('devils_advocate.ai_reasoning.GeminiRunner',side_effect=AssertionError('paid forbidden')):
        response=client.post('/api/investigations',headers=headers,json={'target_input':record.target.model_dump(mode='json'),'use_ai':False,'paid_authorized':False})
    assert response.status_code==200,response.get_json()
    job=response.get_json();assert job['state']=='completed',job['error']
    saved=job['result']
    assert saved['investigation']['coverage']['pathway']==expected_path
    assert saved['provenance']['source_counts']['publications']==len(saved['investigation']['publications'])
    assert saved['provenance']['source_mode']=='live_public_api' and saved['provenance']['pipeline_version']
    assert not saved['investigation']['ai']['calls']

def test_preclinical_role_workflow_permitted_only_with_scripted_paid_transport():
    i=case('exploratory');pub=next(p for p in i.publications if p.identifier=='MED:31337422')
    claim=AIClaim(claim_id='c1',text=pub.title,kind='fact',concern='unknown',stance='context',
        citations=[AICitation(source_id=pub.identifier,field='title',excerpt=pub.title)],
        relevance='Candidate cellular association; not proof of causal target validity.',uncertainty='Direction, causality and population scope require review.')
    d=ChallengeDraft(initial_assessment='Exploratory biology only.',claims=[claim],remaining_uncertainty=['Causality unresolved.'])
    f=final();f.experiment.question='Does the candidate mechanism causally affect a disease-relevant cellular phenotype?'
    runner=ScriptedRunner([d,adjudication(),f])
    report=run_ai_reasoning(i,settings=settings(),runner=runner)
    assert report.status=='completed' and len(report.calls)==3
    assert report.accepted_claims and runner.payloads[0][1]['evidence']['assessment_pathway']=='preclinical_validation'
    assert all('LIMITED PRECLINICAL' in instructions for instructions,_ in runner.payloads)

def test_association_score_does_not_override_missing_biological_sources():
    i=case('exploratory');i.publications=[];i.ontology_association={'state':'found','score':.99}
    assert assess_association(i).strength=='insufficient' and not check_coverage(i).reasoning_permitted

def test_minimal_retry_recovers_publications_without_hiding_error():
    i=case('clinical');pub=i.publications[0]
    client=Mock()
    client.get.side_effect=[RetrievalError('public source failed',status_code=503)]*3+[
        {'hitCount':1,'resultList':{'result':[{'source':'MED','id':'18832244','title':pub.title,'abstractText':pub.abstract}]}}]
    audit=[];result=retrieve_publications(client,i.target,i.compounds,audit)
    assert result and sum(a.state=='failed' for a in audit)==3
    assert audit[-1].operation=='minimal disease-target fallback' and audit[-1].state=='found'
    assert '503' in audit[0].detail

def test_production_paid_request_still_requires_authorization(tmp_path,monkeypatch):
    monkeypatch.setenv('AI_ENABLED','true');app=create_app(tmp_path)
    r=app.test_client().post('/api/investigations',headers={'X-Research-Mode':'live'},
        json={'target_input':case('exploratory').target.model_dump(mode='json'),'use_ai':True,'paid_authorized':False})
    assert r.status_code==400
