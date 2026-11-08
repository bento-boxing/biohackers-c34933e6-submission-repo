"""Curated phase/indication precedent, with official-label context where available."""
import json,re
from .http_client import JsonClient, RetrievalError
from .models import SearchAudit, Investigation
from .disease_terms import matches
from .trial_retriever import CHEMBL, normalize

def label_identity_match(compound,record) -> str | None:
    metadata=record.get('openfda',{});names=metadata.get('generic_name',[])
    known={normalize(n) for n in [compound.name,*compound.synonyms] if n}
    if any(normalize(n) in known for n in names):return 'exact_curated_name_or_synonym'
    # A suffix does not establish product interchangeability. Require a
    # separately curated brand match before accepting a generic base.
    brands=metadata.get('brand_name',[])
    if any(normalize(b) in known for b in brands) and any(normalize(re.sub(r'-[A-Za-z]{4}$','',n))==normalize(compound.name) for n in names):
        return 'curated_brand_and_generic_base_with_FDA_suffix'
    if any(normalize(re.sub(r'-[A-Za-z]{4}$','',n))==normalize(compound.name) for n in names):
        return 'probable_generic_base_suffix_variant_not_interchangeable'
    return None

def record_application_approval(client,result,compound,label,fields) -> None:
    """Verify original FDA approval independently; never rewrite ChEMBL phase."""
    for application in label.get('openfda',{}).get('application_number',[])[:2]:
        if not re.fullmatch(r'(?:NDA|BLA|ANDA)\d+',application):continue
        url='https://api.fda.gov/drug/drugsfda.json';params={'search':'application_number:'+application,'limit':1}
        try:
            data=client.get(url,params)
            exact=[r for r in data.get('results',[]) if r.get('application_number')==application]
            approved=[s for r in exact for s in r.get('submissions',[]) if s.get('submission_type')=='ORIG' and s.get('submission_status')=='AP']
            result.search_audit.append(SearchAudit(source='openFDA',operation='original application approval',url=url,query=params,state='found' if approved else 'no_results',returned=len(exact),relevant=len(approved)))
            if not approved:continue
            source=url+'?search=application_number:'+application+'&limit=1'
            context={'application_number':application,'approval_dates':[s.get('submission_status_date') for s in approved],
                'generic_names':label.get('openfda',{}).get('generic_name',[]),
                'disease_match':'lexical' if matches(fields.get('indications_and_usage',''),result.target) else 'unresolved',
                'source_url':source,'scope':'FDA original approval documented; product/route/age/genotype restrictions and subsequent status require label review. ChEMBL phase is retained unchanged.'}
            if context not in compound.regulatory_approvals:compound.regulatory_approvals.append(context)
            identifier='FDAAPP:'+application
            if not any(r['id']==identifier for r in result.regulatory_records):
                result.regulatory_records.append({'id':identifier,'compound_id':compound.chembl_id,'url':source,
                    'fields':{'application_number':application,'original_approval_submissions':json.dumps(approved),'product_context':json.dumps(context)},
                    'caution':'Original FDA approval is not proof of target-specific efficacy, current availability, or product interchangeability.'})
        except RetrievalError as exc:
            result.search_audit.append(SearchAudit(source='openFDA',operation='original application approval',url=url,query=params,
                state='no_results' if exc.status_code==404 else 'failed',detail='Missing/unavailable approval data do not establish nonapproval.'))

def retrieve_precedent(client: JsonClient,result: Investigation) -> None:
    for compound in result.compounds:
        url=f'{CHEMBL}/drug_indication.json'
        params={'molecule_chembl_id':compound.chembl_id,'limit':100}
        try:
            data=client.get(url,params)
            records=data.get('drug_indications')
            if not isinstance(records,list):raise RetrievalError(url+': malformed indication records')
            def phase4(value):
                try:return float(value)==4
                except (TypeError,ValueError):return False
            compound.indications=[{**r,'approval_precedent':phase4(r.get('max_phase_for_ind')),
                'disease_match':'identifier' if r.get('efo_id') and r['efo_id'].replace('_',':')==(result.target.disease_id or '').replace('_',':') else
                    'lexical' if matches(r.get('efo_term',''),result.target) else 'unresolved',
                'source_url':url+'?molecule_chembl_id='+compound.chembl_id} for r in records]
            limited=bool(data.get('page_meta',{}).get('next'))
            compound.indication_search_state='limit_reached' if limited else 'found' if records else 'no_results'
            result.search_audit.append(SearchAudit(source='ChEMBL',operation='drug indications',url=url,query=params,
                state=compound.indication_search_state,returned=len(records),relevant=sum(r['disease_match']=='lexical' for r in compound.indications)))
        except RetrievalError:
            compound.indication_search_state='failed'
            result.search_audit.append(SearchAudit(source='ChEMBL',operation='drug indications',url=url,query=params,state='failed'))
    approved=[c for c in result.compounds if c.max_phase==4]
    if not approved:
        result.search_audit.append(SearchAudit(source='openFDA',operation='phase-4 label context',url='https://api.fda.gov/drug/label.json',
            state='not_searched',detail='No phase-4 compound retrieved; advanced candidates are checked separately. Missing matches do not establish nonapproval.'))
    advanced=sorted((c for c in result.compounds if c.max_phase is not None and 3<=c.max_phase<4),key=lambda c:c.chembl_id,reverse=True)
    candidates=[*approved[:3],*advanced[:5]]
    if len(approved)>3 or len(advanced)>5:
        result.search_audit.append(SearchAudit(source='openFDA',operation='label candidate limit',url='https://api.fda.gov/drug/label.json',state='limit_reached',returned=len(candidates),total=len(approved)+len(advanced),detail='At most three phase-4 and five advanced candidates; unsearched approval status remains unknown.'))
    for compound in candidates:
        url='https://api.fda.gov/drug/label.json'
        safe=compound.name.replace('"','')
        search=f'openfda.generic_name:{safe}*' if re.fullmatch(r'[A-Za-z0-9-]+',safe) else f'openfda.generic_name:"{safe}"'
        params={'search':search,'limit':2}
        try:
            data=client.get(url,params)
            records=data.get('results')
            if not isinstance(records,list):raise RetrievalError(url+': malformed label response')
            retained=0
            for record in records:
                names=record.get('openfda',{}).get('generic_name',[])
                match=label_identity_match(compound,record)
                if not match:continue
                identifier=record.get('set_id')
                if not identifier:continue
                retained+=1
                fields={key:'\n'.join(record.get(key,[])) for key in ['indications_and_usage','clinical_studies','warnings_and_cautions','mechanism_of_action']}
                fields['product_identity']=json.dumps({'generic_names':names,'brand_names':record.get('openfda',{}).get('brand_name',[]),
                    'match':match,'scope':'Product-specific label: do not transfer route, formulation, age or genotype indications to products sharing a generic base.'})
                if compound.max_phase!=4:record_application_approval(client,result,compound,record,fields)
                result.regulatory_records.append({'id':'SPL:'+identifier,'compound_id':compound.chembl_id,
                    'url':'https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid='+identifier,'fields':fields,
                    'caution':'Official public label submission, not independent proof of approval; indication, population and version require review.'})
            total=data.get('meta',{}).get('results',{}).get('total')
            result.search_audit.append(SearchAudit(source='openFDA',operation='label context',url=url,query=params,
                state='limit_reached' if total and total>len(records) else 'found' if retained else 'no_results',returned=len(records),relevant=retained,total=total))
        except RetrievalError as exc:
            result.search_audit.append(SearchAudit(source='openFDA',operation='label context',url=url,query=params,
                state='no_results' if exc.status_code==404 else 'failed',detail='Label availability does not establish approval status.'))
