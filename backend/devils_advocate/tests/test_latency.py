import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest
from devils_advocate.ai_config import load_ai_settings
from devils_advocate.ai_client import ClaudeRunner
from devils_advocate.ai_reasoning import experimental_evidence, run_ai_reasoning
from devils_advocate.http_client import JsonClient, RetrievalDeadlineExceeded
from devils_advocate.models import ExperimentalResponse
from .test_ai import reply, settings, investigation, draft, adjudication, final, ScriptedRunner, claim

def response(data):
    return SimpleNamespace(status_code=200,raise_for_status=lambda:None,json=lambda:data,
                           raw=SimpleNamespace(retries=SimpleNamespace(history=())))

@pytest.mark.parametrize('level',['medium','HIGH'])
def test_dotenv_thinking_level_reaches_official_sdk(tmp_path,monkeypatch,level):
    monkeypatch.delenv('AI_THINKING_LEVEL',raising=False)
    monkeypatch.setenv('AI_MODEL','configured-test-model')
    monkeypatch.setenv('ANTHROPIC_API_KEY','PRIVATE-TEST-KEY')
    path=tmp_path/'.env'
    path.write_text('AI_THINKING_LEVEL='+level,encoding='utf-8')
    config=load_ai_settings(path)
    runner=ClaudeRunner(config)
    runner.client=Mock()
    runner.client.beta.messages.create.return_value=reply(draft().model_dump_json())
    runner.generate('test','instructions',{},type(draft()))
    assert runner.client.beta.messages.create.call_args.kwargs['output_config']['effort']==level.lower()
    assert runner.client.beta.messages.create.call_args.kwargs['model']=='configured-test-model'
    assert 'PRIVATE-TEST-KEY' not in json.dumps([c.model_dump() for c in runner.calls])

def test_agent_attempt_duration_and_compact_payload_are_measured():
    runner=ClaudeRunner(settings())
    runner.client=Mock()
    runner.client.beta.messages.create.return_value=reply(draft().model_dump_json())
    with patch('devils_advocate.ai_client.time.monotonic',side_effect=[100.,101.25]):
        runner.generate('test','instructions',{'public':'record'},type(draft()))
    assert runner.calls[0].duration_seconds==1.25
    assert runner.calls[0].payload_bytes==len(b'{"public":"record"}')
    assert runner.calls[0].started_at is not None

def test_accepted_claims_need_no_revision_and_keep_all_adjudication_context():
    runner=ScriptedRunner([draft(),adjudication(),final()])
    report=run_ai_reasoning(investigation(),settings=settings(),runner=runner)
    assert len(runner.calls)==3 and len(report.rounds)==1
    assert runner.payloads[0][1]['evidence']['sources']==runner.payloads[1][1]['evidence']['sources']
    assert set(runner.payloads[2][1]['evidence']['sources'])<=set(report.source_bundle['sources'])

def test_designer_context_is_scoped_without_mutating_evidence():
    bundle={'sources':{'NCT01739348':{'fields':{'status':'TERMINATED'},'applicability':{'compound_ids':['CHEMBL1']}},
                       'CHEMBL1':{'fields':{'mechanisms':'Recorded mechanism'}},'MED:2':{'fields':{'abstract':'Unrelated'}},
                       'MED:3':{'fields':{'abstract':'Preserved full context'}}},'selection':{'publications_sent':2}}
    before=copy.deepcopy(bundle)
    scoped=experimental_evidence(bundle,[claim()])
    assert set(scoped['sources'])=={'NCT01739348','CHEMBL1'}
    assert bundle==before and scoped['sources']['NCT01739348']==bundle['sources']['NCT01739348']
    assert scoped['selection']['publications_sent']==0

def test_hypothesis_references_allow_shared_evidence_but_reject_invented_ids():
    value=final()
    value.experiment.hypothesis_evidence=[['c1'],['c1']]
    report=run_ai_reasoning(investigation(),settings=settings(),runner=ScriptedRunner([draft(),adjudication(),value]))
    assert report.status=='completed' and report.experiment.hypothesis_evidence==[['c1'],['c1']]
    value=final();value.experiment.hypothesis_evidence=[['invented'],['c1']]
    report=run_ai_reasoning(investigation(),settings=settings(),runner=ScriptedRunner([draft(),adjudication(),value]))
    assert report.status=='failed'

def test_request_profile_is_measured_and_cache_hit_avoids_network():
    client=JsonClient(min_interval=0);client.session.get=Mock(return_value=response({'record':'public'}))
    events=[]
    with client.tracking(events.append) as measured:
        client.get('https://www.ebi.ac.uk/chembl/api/data/target/CHEMBL4822.json')
        client.get('https://www.ebi.ac.uk/chembl/api/data/target/CHEMBL4822.json')
    assert measured['requests']==1 and measured['cache_hits']==1 and measured['completed_requests']==1
    assert measured['total_seconds']>=0 and 'ChEMBL' in measured['source_seconds']
    assert [e['state'] for e in events]==['request','completed','cache_hit']
    assert events[1]['retries_observed']==0
    assert client.session.get.call_count==1

def test_expired_retrieval_budget_blocks_requests_and_has_no_hidden_model_call():
    client=JsonClient();client.session.get=Mock()
    with pytest.raises(RetrievalDeadlineExceeded):
        with client.tracking(budget_seconds=0):client.get('https://example.org')
    client.session.get.assert_not_called()

def test_source_progress_redacts_query_and_counts_real_retry_history():
    client=JsonClient(min_interval=0);item=response({})
    item.raw.retries.history=('attempt one','attempt two')
    client.session.get=Mock(return_value=item)
    events=[]
    with client.tracking(events.append):client.get('https://clinicaltrials.gov/api/v2/studies',{'private':'QUERY-MUST-NOT-LOG'})
    assert events[-1]['retries_observed']==2
    assert 'QUERY-MUST-NOT-LOG' not in json.dumps(events)

def test_budget_crossed_during_response_records_source_duration_without_caching(monkeypatch):
    current=[0.]
    monkeypatch.setattr('devils_advocate.http_client.time.monotonic',lambda:current[0])
    client=JsonClient(min_interval=0)
    def delayed_response(*args,**kwargs):
        current[0]=2.
        return response({'record':'public'})
    client.session.get=Mock(side_effect=delayed_response)
    events=[]
    with pytest.raises(RetrievalDeadlineExceeded):
        with client.tracking(events.append,budget_seconds=1) as measured:
            client.get('https://clinicaltrials.gov/api/v2/studies')
    assert events[-1]['state']=='failed' and measured['total_seconds']==2.
    assert measured['source_seconds']['ClinicalTrials.gov']==2.
    assert not client.cache

def test_budget_error_is_explicit_and_prevents_paid_reasoning():
    from devils_advocate.investigation import InvestigationFailed, run_investigation
    payload={'mode':'live','use_ai':True,'weights':{},'selection':{'target_input':{'target_symbol':'BACE1','disease_name':'Example'}}}
    reasoner=Mock(side_effect=AssertionError('paid forbidden'))
    with pytest.raises(InvestigationFailed) as exc:
        run_investigation(payload,investigator=Mock(side_effect=RetrievalDeadlineExceeded('Biomedical retrieval time budget exhausted.')),ai_reasoner=reasoner)
    assert 'time budget' in str(exc.value)
    reasoner.assert_not_called()
