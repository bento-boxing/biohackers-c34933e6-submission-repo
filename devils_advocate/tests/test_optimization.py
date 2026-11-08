"""Offline reliability tests for cache, bounded concurrency and prior-art gates."""
import json,time,threading,sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from devils_advocate.http_client import JsonClient,RetrievalError
from devils_advocate.models import Investigation,Experiment
from devils_advocate.source_cache import SourceCache
from devils_advocate.prior_art import check_prior_art,proposal_objections
from devils_advocate.ai_reasoning import evidence_bundle
from devils_advocate.ai_config import AISettings
from devils_advocate.server import create_app

URL='https://www.ebi.ac.uk/europepmc/webservices/rest/search'
DATA={'hitCount':1,'resultList':{'result':[{'source':'MED','id':'123','title':'A source'}]}}
def response(data,status=200,headers=None):
    import requests
    r=SimpleNamespace(status_code=status,json=lambda:data,headers=headers or {},raw=SimpleNamespace(retries=SimpleNamespace(history=())))
    def raise_error():
        if status>=400:raise requests.HTTPError('public failure',response=r)
    r.raise_for_status=raise_error
    return r

def test_cache_survives_new_client_and_keeps_timestamp_scope_and_query(tmp_path):
    path=tmp_path/'cache.sqlite3';scope={'disease_name':'Example','target_symbol':'GENE','target_id':'ENSG1'}
    c=JsonClient(min_interval=0,cache_path=path);c.session.get=Mock(return_value=response(DATA));events=[]
    with c.tracking(events.append,scope=scope):c.get(URL,{'query':'GENE'} )
    fetched=events[-1]['fetched_at'];c.close()
    d=JsonClient(min_interval=0,cache_path=path);d.session.get=Mock(return_value=response(DATA));events=[]
    with d.tracking(events.append,scope={**scope,'disease_aliases':[],'uniprot':None}):d.get(URL,{'query':'GENE'})
    assert events[-1]['provenance']=='CACHED_PERSISTENT' and events[-1]['fetched_at']==fetched
    d.session.get.assert_not_called()
    with d.tracking(scope={**scope,'disease_name':'Other'}):d.get(URL,{'query':'GENE'})
    assert d.session.get.call_count==1
    with d.tracking(scope=scope):d.get(URL,{'query':'different'})
    assert d.session.get.call_count==2

def test_refresh_bypasses_valid_cache(tmp_path):
    c=JsonClient(min_interval=0,cache_path=tmp_path/'c.db');c.session.get=Mock(return_value=response(DATA))
    c.get(URL);c.get(URL);assert c.session.get.call_count==1
    with c.tracking(refresh=True):c.get(URL)
    assert c.session.get.call_count==2

@pytest.mark.parametrize('data',[{}, {'error':'failed'}, {'resultList':None},
    {'resultList':{'result':[None]}},{'hitCount':3,'resultList':{'result':[]}},
    {'resultList':{'result':[{'title':'Missing identifier'}]}}])
def test_incomplete_or_error_body_never_becomes_cached_evidence(tmp_path,data):
    c=JsonClient(min_interval=0,cache_path=tmp_path/'c.db');c.session.get=Mock(return_value=response(data))
    c.get(URL);c.get(URL)
    assert c.session.get.call_count==2
    with sqlite3.connect(tmp_path/'c.db') as db:assert db.execute('SELECT count(*) FROM public_responses').fetchone()[0]==0

def test_expired_or_corrupted_cache_is_not_used(tmp_path):
    path=tmp_path/'c.db';c=JsonClient(min_interval=0,cache_path=path);c.session.get=Mock(return_value=response(DATA));c.get(URL)
    with sqlite3.connect(path) as db:db.execute("UPDATE public_responses SET payload='{}'")
    d=JsonClient(min_interval=0,cache_path=path);d.session.get=Mock(return_value=response(DATA));d.get(URL)
    assert d.session.get.call_count==1
    with sqlite3.connect(path) as db:db.execute('UPDATE public_responses SET expires=0')
    e=JsonClient(min_interval=0,cache_path=path);e.session.get=Mock(return_value=response(DATA));e.get(URL)
    assert e.session.get.call_count==1

def test_bounded_concurrency_and_singleflight_deduplication(tmp_path):
    c=JsonClient(min_interval=0,cache_path=tmp_path/'c.db',max_workers=4)
    session=Mock();session.get.return_value=response(DATA);c._session=lambda:session
    with c.tracking() as profile:answers=c.map(lambda _:c.get(URL),range(12))
    assert len(answers)==12 and session.get.call_count==1 and profile['cache_hits']==11
    active=0;maximum=0;lock=threading.Lock()
    def task(n):
        nonlocal active,maximum
        with lock:active+=1;maximum=max(maximum,active)
        time.sleep(.02)
        with lock:active-=1
        return n
    assert c.map(task,range(12))==list(range(12)) and 1<maximum<=4
    c.close()

def test_failed_task_drains_workers_before_tracking_scope_restores():
    c=JsonClient(max_workers=4);finished=[]
    def task(n):
        if n==0:raise ValueError('test')
        time.sleep(.01);finished.append(c.scope['disease_name'])
    with pytest.raises(ValueError):
        with c.tracking(scope={'disease_name':'Scoped'}):c.map(task,range(4))
    assert finished==['Scoped']*3 and c.scope=={}
    c.close()

@pytest.mark.parametrize('retry_header',['120','http-date'])
def test_long_retry_after_is_not_ignored_or_cached(tmp_path,retry_header):
    from email.utils import formatdate
    value=formatdate(time.time()+120,usegmt=True) if retry_header=='http-date' else retry_header
    c=JsonClient(min_interval=0,cache_path=tmp_path/'c.db');c.session.get=Mock(return_value=response({},429,{'Retry-After':value}))
    with pytest.raises(RetrievalError):c.get(URL)
    assert c.session.get.call_count==1 and not c.cache

def test_historic_bad_proposal_is_blocked_for_prior_art_and_absolute_claims():
    fixture=json.loads((Path(__file__).parents[1]/'fixtures/optimization_reference.json').read_text(encoding='utf-8'))
    i=Investigation.model_validate(fixture['investigation'])
    original=Experiment.model_validate(fixture['bad_experiment'])
    review=check_prior_art(i,original)
    assert review['decision']=='abstain' and 'MED:16641282' in review['close_matches']
    assert any('exclusivity' in s for s in review['objections']) and any('Assay sensitivity' in s for s in review['objections'])
    # Same vocabulary with invented IDs would not become a verified source.
    assert all(m['source_id'] in {p.identifier for p in i.publications} for m in review['matches'])

def test_prior_art_is_general_and_no_match_does_not_claim_novelty():
    from .test_ai import investigation,final
    i=investigation();i.publications=[]
    review=check_prior_art(i,final().experiment)
    assert review['status']=='NOVELTY_NOT_ESTABLISHED' and 'proof of novelty' in review['caution']

def test_background_binding_publication_cannot_answer_a_toxicity_question():
    from .test_ai import investigation,final
    from devils_advocate.models import Publication
    i=investigation()
    i.publications=[Publication(identifier='MED:1',title='BACE1 pharmacological binding comparison',
        abstract='A human compound scaffold comparison investigated receptor blockade and inhibition.',url='https://example.org/1')]
    proposal=final().experiment.model_copy(update={
        'question':'Is hepatotoxicity caused by metabolite reactivity or immune hypersensitivity?',
        'scientific_claim':'Human clinical compound scaffold comparison and pharmacological inhibition.',
        'unresolved_gap':'Human clinical compound scaffold comparison and pharmacological inhibition.'})
    check=check_prior_art(i,proposal)
    assert not check['close_matches'] and check['status']=='NOVELTY_NOT_ESTABLISHED'

def test_specific_matching_mechanistic_work_requires_review_for_arbitrary_target():
    from .test_ai import investigation,final
    from devils_advocate.models import Publication
    i=investigation()
    i.publications=[Publication(identifier='MED:2',title='Sustained receptor engagement induces mitochondrial depolarization',
        abstract='Orthogonal perturbation demonstrated oxidative injury and mitochondrial depolarization.',url='https://example.org/2')]
    proposal=final().experiment.model_copy(update={
        'question':'Does sustained receptor engagement induce mitochondrial depolarization and oxidative injury?'})
    check=check_prior_art(i,proposal)
    assert check['decision']=='abstain' and check['close_matches']==['MED:2']

def test_parenthetical_cohort_label_does_not_validate_cross_trial_causality():
    from .test_ai import claim
    from devils_advocate.ai_reasoning import validate_ai_claim
    candidate=claim().model_copy(update={'text':
        'Treatment-naive patients failed largely due to receptor shifts (observed in treatment-experienced trials).',
        'kind':'interpretation'})
    bundle={'sources':{'NCT01739348':{'fields':{'status':'TERMINATED'},'url':'https://example.org'}}}
    assert any('Cross-population causal' in issue for issue in validate_ai_claim(candidate,bundle))

def test_grouped_approval_claim_needs_each_named_compound_source():
    from .test_ai import claim
    from devils_advocate.ai_reasoning import validate_ai_claim
    from devils_advocate.models import AICitation
    candidate=claim().model_copy(update={'text':'Alphaagent and Betaagent lack approval precedent.',
        'kind':'unresolved','citations':[AICitation(source_id='CHEMBL1',field='name',excerpt='Alphaagent')]})
    bundle={'sources':{f'CHEMBL{n}':{'fields':{'name':name},'url':'https://example.org'}
        for n,name in [(1,'Alphaagent'),(2,'Betaagent')]}}
    assert any('Betaagent' in issue for issue in validate_ai_claim(candidate,bundle))

def test_compact_packet_preserves_scientific_sources():
    fixture=json.loads((Path(__file__).parents[1]/'fixtures/optimization_reference.json').read_text(encoding='utf-8'))
    original=fixture['baseline_bundle']
    i=Investigation.model_validate(fixture['investigation'])
    i.publications=[p for p in i.publications if p.identifier in original['sources']]
    compact=evidence_bundle(i,AISettings())
    assert set(original['sources'])==set(compact['sources'])
    for key in original['sources']:
        for field,value in original['sources'][key]['fields'].items():
            actual=compact['sources'][key]['fields'][field]
            # Flask sorts saved dictionary keys; constructed JSON metadata can
            # reorder on replay while preserving every scientific value.
            if field=='outcome_records':
                index=json.loads(actual)
                trial=next(t for t in i.trials if t.nct_id==key)
                assert index['record_count']==len(trial.outcome_records)
                assert [v['title'] for v in index['outcome_index']]==[o.get('title','') for o in trial.outcome_records]
            else:assert json.loads(value)==json.loads(actual) if field=='approval_metadata' else value==actual
    assert len(json.dumps(compact))<len(json.dumps(original))

def test_more_than_five_calls_requires_separate_explicit_authorization(tmp_path,monkeypatch):
    monkeypatch.setenv('AI_ENABLED','true');app=create_app(tmp_path,start_worker=False)
    body={'target_input':{'disease_name':'Example','target_symbol':'GENE'},'use_ai':True,'paid_authorized':True,'model_call_limit':8}
    client=app.test_client();headers={'X-Research-Mode':'live','Idempotency-Key':'extra-call-test'}
    assert client.post('/api/investigations',headers=headers,json=body).status_code==400
    body['extra_calls_authorized']=True
    r=client.post('/api/investigations',headers=headers,json=body)
    assert r.status_code==202
    saved=app.config['STORE'].get(r.json['job_id'])
    assert saved['payload']['ai_policy']['max_calls']==8 and saved['payload']['extra_calls_authorized']
    # Worker is not started: this authorization-contract test makes zero model calls.

@pytest.mark.parametrize('bulk_differs',[False,True])
def test_bulk_trial_records_match_individual_evidence_and_fall_back_if_needed(tmp_path,bulk_differs):
    from devils_advocate.trial_retriever import retrieve_trials
    from devils_advocate.models import TargetInput
    import copy
    records=[]
    for n in range(8):
        records.append({'hasResults':True,'protocolSection':{'identificationModule':{'nctId':f'NCT{n:08d}'},
            'statusModule':{'overallStatus':'TERMINATED',**({'whyStopped':'Recruitment problem'} if n==0 else {})},
            'conditionsModule':{'conditions':['Example disease']}},
            'resultsSection':{'outcomeMeasuresModule':{'outcomeMeasures':[{'title':'Uninterpreted endpoint'}]}}})
    c=JsonClient(min_interval=0,cache_path=tmp_path/'c.db',max_workers=4);c._rate_limit=lambda url:None
    session=Mock();c._session=lambda:session
    def get(url,params=None,**kwargs):
        if url.endswith('/studies'):
            rows=copy.deepcopy(records)
            if (params or {}).get('filter.ids') and bulk_differs:
                for row in rows:row.pop('resultsSection')
            return response({'studies':rows})
        return response(records[int(url[-8:])])
    session.get.side_effect=get
    target=TargetInput(disease_name='Example disease',target_symbol='GENE')
    with c.tracking(scope=target.model_dump()):trials=retrieve_trials(c,target,[],[],[])
    assert len(trials)==8 and all(t.stop_reason.full_record_checked for t in trials)
    assert trials[0].why_stopped=='Recruitment problem' and trials[1].stop_reason.state=='absent'
    assert all(t.outcome_records[0]['title']=='Uninterpreted endpoint' for t in trials)
    assert session.get.call_count==(10 if bulk_differs else 3)
    c.close()
