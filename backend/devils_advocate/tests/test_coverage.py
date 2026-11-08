"""Offline coverage, sampling and false-negative regression tests. No model calls."""
import json
from pathlib import Path
from unittest.mock import Mock,patch
import pytest
from devils_advocate.models import Compound,Investigation,TargetInput,SearchAudit,Publication
from devils_advocate.coverage import check_coverage,select_evidence,target_level_objections
from devils_advocate.literature import retrieve_publications,annotate
from devils_advocate.disease_terms import terms,resolve_disease_terms,matches
from devils_advocate.ai_reasoning import run_ai_reasoning,evidence_bundle,experimental_evidence
from devils_advocate.ai_config import AISettings
from devils_advocate.scientific_benchmark import evaluate
from devils_advocate.http_client import RetrievalError
from devils_advocate.trial_retriever import retrieve_compounds,retrieve_trials
from .test_pipeline import FakeClient,record
from .test_ai import investigation,settings,draft,adjudication,final,ScriptedRunner

def references():
 data=json.loads((Path(__file__).parents[1]/'fixtures/scientific_reference.json').read_text(encoding='utf-8'))
 return data['cases']

def test_general_disease_display_suffix_and_subtype_fallbacks():
 assert 'HIV' in terms(TargetInput(disease_name='HIV infectious disease',target_symbol='CCR5'))
 assert 'rare invented syndrome' in terms(TargetInput(disease_name='rare invented syndrome disorder',target_symbol='X'))
 assert matches('non-small cell lung carcinoma NSCLC',TargetInput(disease_name='EGFR-mutant non-small-cell lung cancer',target_symbol='EGFR'))

def test_ontology_synonyms_use_exact_identifier_not_neighboring_term():
 target=TargetInput(disease_name='Disease display label',disease_id='MONDO_123',target_symbol='X')
 client=FakeClient([{'_embedded':{'terms':[{'obo_id':'MONDO:123','label':'Exact disease','synonyms':['Clinical synonym']},
                                       {'obo_id':'MONDO:124','label':'Wrong disease'}]}}])
 audits=[];resolved=resolve_disease_terms(client,target,audits)
 assert 'Clinical synonym' in resolved.disease_aliases and 'Wrong disease' not in resolved.disease_aliases
 assert audits[0].state=='found' and target.disease_aliases==[]

@pytest.mark.parametrize('response,state',[
 ({'hitCount':0,'resultList':{'result':[]}},'no_results'),
 (RetrievalError('unavailable'),'failed'),({},'failed')])
def test_publication_empty_failed_and_malformed_are_distinct(response,state):
 audit=[];target=TargetInput(disease_name='Example disease',target_symbol='X')
 assert retrieve_publications(FakeClient([response]),target,audit=audit)==[]
 assert audit[0].state==state

def test_limit_and_visible_attrition_are_recorded_without_inventing_outcomes():
 target=TargetInput(disease_name='Example disease',target_symbol='X')
 audit=[];client=FakeClient([{'hitCount':100,'resultList':{'result':[
  {'source':'MED','id':'1','title':'X in Example disease patients','abstractText':'Completed trial.'},
  {'source':'MED','id':'2','title':'Unrelated methods','abstractText':'No evidence.'}]}}])
 pubs=retrieve_publications(client,target,audit=audit)
 assert len(pubs)==1 and audit[0].state=='limit_reached' and audit[0].returned==2 and audit[0].relevant==1
 assert not pubs[0].direction_signals

def test_compound_context_preserved_with_uncertain_disease_scope():
 target=TargetInput(disease_name='Example disease',target_symbol='GENE')
 compound=Compound(chembl_id='CHEMBL1',name='KnownDrug',url='https://example.org')
 page={'resultList':{'result':[{'source':'MED','id':'1','title':'KnownDrug in a different disease','abstractText':'Clinical context.'}]}}
 pubs=retrieve_publications(FakeClient([page,page]),target,[compound])
 assert pubs[0].disease_match=='uncertain' and 'must not be extrapolated' in pubs[0].relevance

def test_approved_molecule_prioritized_before_compound_cap():
 mechanisms=[{'molecule_chembl_id':f'CHEMBL{i}','mechanism_of_action':'Antagonist'} for i in range(16)]
 molecules=[{'molecule_chembl_id':f'CHEMBL{i}','pref_name':f'Drug{i}','max_phase':'4.0' if i==9 else '1.0'} for i in range(16)]
 client=FakeClient([{'mechanisms':mechanisms},{'molecules':molecules}])
 audit=[];compounds=retrieve_compounds(client,'CHEMBL999',[],audit)
 assert len(compounds)==15 and compounds[0].chembl_id=='CHEMBL9' and compounds[0].max_phase==4
 assert audit[0].state=='limit_reached'

def test_stratified_trials_include_results_and_preserve_stop_reason_categories():
 i=investigation();i.trials=[]
 base=record()
 for index,reason in enumerate(['futility','safety concerns','recruitment difficulties','','','','']):
  from devils_advocate.trial_retriever import parse_trial
  raw=json.loads(json.dumps(base));raw['protocolSection']['identificationModule']['nctId']=f'NCT{index:08d}'
  raw['protocolSection']['statusModule']['whyStopped']=reason
  t=parse_trial(raw,[]);t.compound_ids=[i.compounds[0].chembl_id];t.relationship='verified';t.disease_match='matched';t.has_results=index==6
  i.trials.append(t)
 i.compounds[0].max_phase=4
 selected,_,reasons=select_evidence(i)
 assert len(selected)==6 and any(t.has_results for t in selected)
 assert all(any(t.why_stopped==reason for t in selected) for reason in ['futility','safety concerns','recruitment difficulties'])
 assert len(i.trials)==7 and reasons

def test_full_record_results_and_phase_are_not_dropped():
 raw=record();full=record();full['protocolSection']['designModule']={'phases':['PHASE3']}
 full['resultsSection']={'outcomeMeasuresModule':{'outcomeMeasures':[{'title':'Exact recorded endpoint'}]}}
 result=retrieve_trials(FakeClient([{'studies':[raw]},full]),TargetInput(disease_name='Example',target_symbol='X'),[],[])
 assert result[0].has_results and result[0].phases==['PHASE3'] and result[0].outcome_records[0]['title']=='Exact recorded endpoint'

def test_inadequate_coverage_blocks_runner_construction_even_if_enabled():
 i=investigation();i.publications=[]
 with patch('devils_advocate.ai_reasoning.GeminiRunner',side_effect=AssertionError('paid call forbidden')):
  report=run_ai_reasoning(i,settings=settings())
 assert report.status=='skipped' and not report.calls and 'INSUFFICIENT COVERAGE' in report.warnings[0]

def test_configured_packet_excluding_positive_evidence_fails_coverage():
 i=investigation()
 i.publications=[annotate(Publication(identifier='MED:1',title="Randomized BACE1 inhibitor trial in Alzheimer's disease",abstract='Conclusions: Treatment significantly improved function.',url='https://example.org'))]
 coverage=check_coverage(i,max_publications=0)
 assert coverage.status=='INSUFFICIENT COVERAGE' and any('excluded' in gap for gap in coverage.gaps)

def test_designer_keeps_clinical_counterevidence_not_cited_by_challenger():
 bundle={'sources':{'MED:1':{'clinical_context':True,'fields':{'abstract':'Positive context'}},
                    'CHEMBL1':{'precedent':True,'fields':{'approval_metadata':'Recorded phase'}}}}
 assert set(experimental_evidence(bundle,[])['sources'])==set(bundle['sources'])

def test_target_level_invalidity_cannot_be_supported_by_model_agreement():
 assert target_level_objections('The target is invalid.')
 candidate=draft();candidate.claims[0].text='The target is ineffective.';candidate.claims[0].kind='interpretation'
 runner=ScriptedRunner([candidate,adjudication(),final(False)])
 report=run_ai_reasoning(investigation(),settings=settings(max_calls=3),runner=runner)
 assert not report.accepted_claims and report.rounds[0].deterministic_objections['c1']

@pytest.mark.parametrize('text',['This trial does not prove that the target is invalid.',
                                'There is no evidence that the target is ineffective.'])
def test_qualified_non_invalidity_statement_is_not_rejected(text):
 assert not target_level_objections(text)

def test_all_five_recorded_scientific_cases_and_measurements():
 report=evaluate()
 assert {c['target'] for c in report['cases']}=={'CCR5','PCSK9','EGFR','BACE1','LRRK2'}
 assert report['checks_passed']==report['checks_total']==30
 assert report['positive_evidence_omission']['new_filter_and_packet_misses']==0
 assert report['positive_evidence_omission']['legacy_phrase_filter_misses']==2
 assert report['paid_calls']==0 and report['coverage_check_ms']['median']>=0

def test_existing_approval_does_not_justify_repeating_generic_benefit_experiment():
 from devils_advocate.experiment_designer import check_experiment_readiness
 i=investigation();i.compounds[0].max_phase=4
 i.compounds[0].indications=[{'approval_precedent':True,'disease_match':'lexical'}]
 e=final().experiment;e.question='Does this treatment work?'
 checked=check_experiment_readiness(i,e,1)
 # The design is kept for the researcher; the repetition risk is a visible review flag, not an erased proposal.
 assert checked.competing_explanations and checked.question=='Does this treatment work?'
 assert any(l.startswith('Review flag:') and 'approved clinical precedent' in l for l in checked.limitations)

def test_string_indication_phase_is_preserved_and_disease_scope_not_transferred():
 from devils_advocate.precedent import retrieve_precedent
 i=Investigation(target=TargetInput(disease_name='Disease A',target_symbol='X'),mode='live',
  compounds=[Compound(chembl_id='CHEMBL1',name='Drug',max_phase=4,url='https://example.org')])
 client=FakeClient([{'drug_indications':[{'efo_term':'Disease B','max_phase_for_ind':'4.0'}]},RetrievalError('no label',status_code=404)])
 retrieve_precedent(client,i)
 r=i.compounds[0].indications[0]
 assert r['max_phase_for_ind']=='4.0' and r['approval_precedent'] and r['disease_match']=='unresolved'
