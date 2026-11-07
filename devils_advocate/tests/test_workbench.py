from dataclasses import asdict
from pathlib import Path
from unittest.mock import Mock
import json
import time
import uuid
import pytest
from devils_advocate.job_store import JobStore
from devils_advocate.server import create_app
from devils_advocate.models import TargetInput
from devils_advocate.target_scout_adapter import flatten_scout_selection
from devils_advocate.workbench_demo import load_recorded

HEADERS={'X-Research-Mode':'offline'}

@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path,start_worker=False)

def scout(client):
    response=client.post('/api/scout',headers=HEADERS,json={'disease':'Parkinson disease','n':25})
    assert response.status_code==200,response.get_json()
    return response.get_json()

def queue(client,run,**updates):
    body={'run_id':run['run_id'],'symbol':'LRRK2',**updates}
    return client.post('/api/investigations',json=body,headers={**HEADERS,'Idempotency-Key':str(uuid.uuid4())})

def completed_job(app):
    client=app.test_client();run=scout(client)
    response=queue(client,run);assert response.status_code==202,response.get_json()
    store=app.config['STORE'];job=store.claim();app.config['WORKER'].execute(job)
    result=store.get(job['id']);assert result['state']=='completed',result['error']
    return client,run,result

def test_actual_nested_lrrk2_handoff_preserves_ids_scores_and_provenance(app):
    run=scout(app.test_client());flat=flatten_scout_selection(run,'LRRK2')
    assert flat['target_input']['target_id']=='ENSG00000188906'
    assert flat['target_input']['chembl_target_id']=='CHEMBL1075104'
    assert flat['target_input']['uniprot']=='Q5S007'
    assert flat['target_input']['disease_id']=='MONDO_0005180'
    assert flat['evidence_pmids'] and flat['cache_only']
    assert 'association_score' not in flat['target_input']

def test_offline_job_never_calls_live_retrieval_or_gemini(app):
    app.config['WORKER'].investigator=Mock(side_effect=AssertionError('live forbidden'))
    app.config['WORKER'].ai_reasoner=Mock(side_effect=AssertionError('paid forbidden'))
    client,run,job=completed_job(app)
    assert job['result']['investigation']['mode']=='offline'
    assert job['result']['investigation']['target']['target_symbol']=='LRRK2'
    assert not job['result']['recorded_ai']
    assert not app.config['WORKER'].ai_reasoner.called

def test_bace1_playback_is_explicitly_recorded_and_never_validates_wrong_identity():
    result,recorded=load_recorded(TargetInput(disease_name="Alzheimer's disease",target_symbol='BACE1',chembl_target_id='CHEMBL4822'))
    assert result.mode=='offline' and recorded and result.ai.status=='completed'
    assert 'RECORDED AI PLAYBACK' in result.ai.warnings[0]
    with pytest.raises(ValueError):load_recorded(TargetInput(disease_name='Parkinson disease',target_symbol='LRRK2',chembl_target_id='CHEMBL203'))
    with pytest.raises(ValueError):load_recorded(TargetInput(disease_name='Other',target_symbol='EGFR'))

def test_active_jobs_and_request_retries_are_deduplicated(app):
    client=app.test_client();run=scout(client)
    body={'run_id':run['run_id'],'symbol':'LRRK2'}
    headers={**HEADERS,'Idempotency-Key':'same-request-key'}
    first=client.post('/api/investigations',json=body,headers=headers).get_json()
    second=client.post('/api/investigations',json=body,headers=headers).get_json()
    third=queue(client,run).get_json()
    assert first['job_id']==second['job_id']==third['job_id']
    bad=client.post('/api/investigations',json={**body,'symbol':'SNCA'},headers=headers)
    assert bad.status_code==409

def test_cancelled_job_does_not_run_and_expired_lease_does_not_retry(tmp_path):
    store=JobStore(tmp_path/'jobs.db')
    first,_=store.create('test-key-one','f','s',{'mode':'offline'})
    store.cancel(first['id']);assert store.claim() is None
    second,_=store.create('test-key-two','f','s2',{'mode':'offline'})
    claimed=store.claim();assert claimed['id']==second['id']
    with store.connect() as db:db.execute('UPDATE jobs SET lease=? WHERE id=?',(time.time()-1,claimed['id']))
    assert store.claim() is None
    assert store.get(second['id'])['state']=='interrupted'

def test_restarts_keep_runs_jobs_and_decision_history(app,tmp_path):
    client,run,job=completed_job(app)
    data={'decision_id':'test-decision-id','job_id':job['id'],'action':'investigate','rationale':'Review the unknown engagement before proceeding.'}
    assert client.post('/api/research-decisions',headers=HEADERS,json=data).status_code==200
    new=create_app(tmp_path,start_worker=False).test_client()
    assert new.get('/api/investigations/'+job['id'],headers=HEADERS).get_json()['decisions'][0]['rationale']==data['rationale']
    assert new.get('/api/workbench/runs/'+run['run_id'],headers=HEADERS).status_code==200

def test_human_approval_gates_existing_screening(app):
    client,run,job=completed_job(app)
    assert client.post('/api/screen',headers=HEADERS,json={'approval_ts':'forged'}).status_code==403
    assert client.post('/api/approvals',headers=HEADERS,json={}).status_code==403
    body={'decision_id':'decision-approval','job_id':job['id'],'action':'approve_screening','rationale':'Offline test decision: explore evidence only; not a clinical approval.'}
    assert client.post('/api/research-decisions',headers=HEADERS,json=body).status_code==400
    approval=client.post('/api/research-decisions',headers=HEADERS,json={**body,'confirmed':True})
    assert approval.status_code==200,approval.get_json()
    ts=approval.get_json()['approval']['ts']
    screened=client.post('/api/screen',headers=HEADERS,json={'approval_ts':ts})
    assert screened.status_code==200,screened.get_json()
    assert screened.get_json()['compounds']

def test_mode_origin_consent_and_input_validation(app):
    client=app.test_client();run=scout(client)
    assert client.post('/api/scout',headers={**HEADERS,'Origin':'https://untrusted.example'},json={'disease':'Parkinson disease'}).status_code==403
    assert queue(client,run,weights={'unknown':1}).status_code==400
    assert queue(client,run,symbol='FAKEGENE123').status_code==400
    assert client.post('/api/investigations',headers={'X-Research-Mode':'live','Idempotency-Key':'paid-no-consent'},json={'target_input':{'disease_name':'Example','target_symbol':'EGFR'},'use_ai':True,'paid_authorized':False}).status_code==400
    assert client.get('/api/workbench/runs/'+run['run_id'],headers={'X-Research-Mode':'live'}).status_code==404

def test_live_mode_does_not_read_recorded_scout_cache(app):
    live=app.config['SCOUT_APPS']['live'].config['HTTP_CLIENT']
    recorded=app.config['SCOUT_APPS']['offline'].config['HTTP_CLIENT']
    assert not live.cache_only
    assert all('demo_cache' not in str(path) for path in live.read_dirs)
    assert recorded.cache_only and recorded.write_dir is None
    assert any('demo_cache' in str(path) for path in recorded.read_dirs)
    client=app.test_client()
    cfg=client.get('/api/workbench/config',headers=HEADERS).get_json()
    assert 'api_key' not in json.dumps(cfg)

def test_live_job_preserves_failed_ai_report_without_discarding_retrieval(app,monkeypatch):
    from devils_advocate.ai_config import AISettings
    from devils_advocate.models import Investigation, AIReport, AICall
    from pydantic import SecretStr
    config=AISettings(enabled=True,model='test-model',api_key=SecretStr('SECRET-TEST-ONLY'))
    monkeypatch.setattr('devils_advocate.server.load_ai_settings',lambda:config)
    monkeypatch.setattr('devils_advocate.job_worker.load_ai_settings',lambda:config)
    client=app.test_client()
    payload={'target_input':{'disease_name':'Non-small-cell lung cancer','target_symbol':'EGFR','chembl_target_id':'CHEMBL203'},'use_ai':True,'paid_authorized':True}
    created=client.post('/api/investigations',headers={'X-Research-Mode':'live','Idempotency-Key':'explicit-paid-test'},json=payload)
    assert created.status_code==202
    worker=app.config['WORKER']
    worker.investigator=Mock(return_value=Investigation(target=TargetInput.model_validate(payload['target_input']),mode='live',resolved_target_id='CHEMBL203',resolution_status='resolved'))
    worker.ai_reasoner=Mock(return_value=AIReport(enabled=True,model='test-model',status='failed',calls=[AICall(role='Devils Advocate',success=False,error='Gemini response timed out.')],warnings=['Gemini response timed out.']))
    job=app.config['STORE'].claim();worker.execute(job)
    finished=app.config['STORE'].get(job['id'])
    assert finished['state']=='completed'
    assert finished['result']['investigation']['ai']['status']=='failed'
    assert finished['result']['investigation']['resolved_target_id']=='CHEMBL203'
    assert 'AI-generated' not in finished['result']['experiment']['status']
    assert 'SECRET-TEST-ONLY' not in json.dumps(finished)

def test_unrelated_or_invalid_live_targets_use_given_identifiers(app):
    from devils_advocate.models import Investigation
    client=app.test_client();worker=app.config['WORKER']
    for symbol,identifier,status in [('EGFR','CHEMBL203','resolved'),('FAKEGENE123',None,'unknown')]:
        value={'disease_name':'Example','target_symbol':symbol,'chembl_target_id':identifier}
        created=client.post('/api/investigations',headers={'X-Research-Mode':'live','Idempotency-Key':str(uuid.uuid4())},json={'target_input':value})
        assert created.status_code==202
        worker.investigator=Mock(return_value=Investigation(target=TargetInput.model_validate(value),mode='live',resolved_target_id=identifier,resolution_status=status))
        worker.ai_reasoner=Mock(return_value=None)
        job=app.config['STORE'].claim();worker.execute(job)
        assert worker.investigator.call_args.args[0].chembl_target_id==identifier
        assert app.config['STORE'].get(job['id'])['state']=='completed'
