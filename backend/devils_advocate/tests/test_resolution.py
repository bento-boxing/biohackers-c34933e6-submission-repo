from unittest.mock import Mock
import pytest
from devils_advocate.http_client import JsonClient, RetrievalError
from devils_advocate.models import TargetInput
from devils_advocate.trial_retriever import TargetIdentityError, resolve_target
from devils_advocate.devil_advocate import investigate_target
from .test_pipeline import FakeClient

def target(symbol='BACE1', identifier='CHEMBL4822', accession='P56817'):
    return {'target_chembl_id': identifier, 'organism': 'Homo sapiens', 'tax_id':9606,
            'target_type':'SINGLE PROTEIN', 'pref_name':'Beta-secretase 1',
            'target_components':[{'accession':accession,'target_component_synonyms':[{'component_synonym':symbol}]}]}

def test_supplied_chembl_id_avoids_search_and_validates_components():
    client=Mock(spec=JsonClient)
    client.get.return_value=target()
    result=resolve_target(client,TargetInput(disease_name='Example',target_symbol='BACE1',
        target_id='ENSG00000186318',chembl_target_id='CHEMBL4822',uniprot='P56817'))
    assert result=='CHEMBL4822'
    assert client.get.call_args.args==('https://www.ebi.ac.uk/chembl/api/data/target/CHEMBL4822.json',)

@pytest.mark.parametrize('change', [{'organism':'Mus musculus'},{'target_type':'PROTEIN FAMILY'},
    {'tax_id':10090},{'target_components':[]},{'target_chembl_id':'CHEMBL203'}])
def test_supplied_id_cannot_bypass_scientific_identity(change):
    with pytest.raises(TargetIdentityError):
        resolve_target(FakeClient([{**target(),**change}]),TargetInput(disease_name='Example',target_symbol='BACE1',chembl_target_id='CHEMBL4822'))

def test_component_symbol_and_uniprot_must_match():
    for record in [target(symbol='BACE2'),target(accession='OTHER')]:
        with pytest.raises(TargetIdentityError):
            resolve_target(FakeClient([record]),TargetInput(disease_name='Example',target_symbol='BACE1',chembl_target_id='CHEMBL4822',uniprot='P56817'))

def test_verified_resolution_cache_is_reused_but_not_for_other_proteins():
    client=JsonClient()
    client.get=Mock(return_value=target())
    requested=TargetInput(disease_name='Example',target_symbol='BACE1',chembl_target_id='CHEMBL4822')
    assert resolve_target(client,requested)=='CHEMBL4822'
    assert resolve_target(client,requested)=='CHEMBL4822'
    assert client.get.call_count==1
    with pytest.raises(TargetIdentityError):
        resolve_target(client,requested.model_copy(update={'target_symbol':'EGFR'}))
    assert client.get.call_count==2

def test_search_exact_match_still_works_and_ambiguous_or_similar_names_do_not():
    request=TargetInput(disease_name='Example',target_symbol='BACE1')
    assert resolve_target(FakeClient([{'targets':[target(),target('BACE2','CHEMBL4593')]}]),request)=='CHEMBL4822'
    assert resolve_target(FakeClient([{'targets':[target('BACE2','CHEMBL4593')]}]),request) is None
    assert resolve_target(FakeClient([{'targets':[target(),target(identifier='CHEMBL111')]}]),request) is None

def test_transient_search_failure_is_not_an_unknown_target_or_offline_result():
    result=investigate_target({'disease_name':'Example','target_symbol':'BACE1'},client=FakeClient([RetrievalError('https://example.org: HTTP 503',status_code=503)]))
    assert result.mode=='live' and result.resolution_status=='unavailable'
    assert not result.trials and not result.publications and result.retrieval_errors
    unknown=investigate_target({'disease_name':'Example','target_symbol':'FAKEGENE123'},client=FakeClient([{'targets':[]}]))
    assert unknown.resolution_status=='unknown' and not unknown.retrieval_errors

def test_missing_direct_record_and_transient_direct_failure_are_distinct():
    request=TargetInput(disease_name='Example',target_symbol='BACE1',chembl_target_id='CHEMBL4822')
    with pytest.raises(TargetIdentityError):resolve_target(FakeClient([RetrievalError('404',status_code=404)]),request)
    with pytest.raises(RetrievalError):resolve_target(FakeClient([RetrievalError('503',status_code=503)]),request)

def test_malformed_responses_are_unavailability_not_unknown_targets():
    request=TargetInput(disease_name='Example',target_symbol='BACE1')
    with pytest.raises(RetrievalError):resolve_target(FakeClient([{}]),request)
    with pytest.raises(RetrievalError):resolve_target(FakeClient([{}]),request.model_copy(update={'chembl_target_id':'CHEMBL4822'}))

def test_conflicting_supplied_identifiers_are_rejected():
    with pytest.raises(TargetIdentityError):
        resolve_target(FakeClient([]),TargetInput(disease_name='Example',target_symbol='BACE1',target_id='CHEMBL203',chembl_target_id='CHEMBL4822'))

def test_transient_ensembl_identity_failure_does_not_blank_the_report():
    # Ensembl REST intermittently answers HTTP 500; the gene-identity check is a cross-check,
    # not the evidence source, so ChEMBL resolution by symbol must still proceed and be audited.
    responses=[RetrievalError('https://rest.ensembl.org/lookup/id/ENSG00000186318: HTTPError',status_code=500),
               {'targets':[target()]},*[RetrievalError('https://www.ebi.ac.uk/chembl/api/data/mechanism.json: HTTPError',status_code=503)]*40]
    result=investigate_target({'disease_name':'Example','target_symbol':'BACE1','target_id':'ENSG00000186318'},client=FakeClient(responses))
    assert result.resolution_status=='resolved' and result.resolved_target_id=='CHEMBL4822'
    assert any(e.startswith('https://rest.ensembl.org/') for e in result.retrieval_errors)
    ensembl=[a for a in result.search_audit if a.source=='Ensembl' and a.operation=='gene identity']
    assert ensembl and ensembl[0].state=='failed'
    assert any('Ensembl' in note and 'not verified' in note for note in result.missing_information)
