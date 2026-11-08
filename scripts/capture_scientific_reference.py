"""Explicit public-data reference capture, never imported by production or pytest.

Curated study IDs below define a small regression sheet, not a search strategy
or production answer table. Run only to refresh these versioned source extracts.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json,re,html,time,hashlib
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
from devils_advocate.http_client import JsonClient
from devils_advocate.models import TargetInput,Investigation,Compound,Publication,SearchAudit
from devils_advocate.trial_retriever import resolve_target,parse_trial,CHEMBL,normalize
from devils_advocate.stop_reasons import inspect_stop_reason
from devils_advocate.literature import annotate,ENDPOINT
from devils_advocate.precedent import retrieve_precedent
from devils_advocate.disease_terms import matches

CASES=[
 ('HIV infectious disease','CCR5',['maraviroc'],['18832244','20151839'],'NCT00098306',
  'Maraviroc is an approved precedent for selected CCR5-tropic HIV-1 populations, in combination therapy. MERIT endpoint and tropism differences do not invalidate CCR5.',
  'https://www.ema.europa.eu/en/documents/product-information/celsentri-epar-product-information_en.pdf'),
 ('Hypercholesterolemia','PCSK9',['evolocumab','bococizumab'],['24825642','28304227'],'NCT01763866',
  'Evolocumab provides approved LDL-lowering precedent; bococizumab immunogenicity/variability is a compound-specific concern, not PCSK9 invalidity.',
  'https://www.ema.europa.eu/en/medicines/human/EPAR/repatha'),
 ('EGFR-mutant non-small-cell lung cancer','EGFR',['osimertinib'],['29151359'],'NCT02296125',
  'Osimertinib provides approved precedent for specified EGFR-mutant NSCLC populations; do not generalise efficacy to EGFR-wild-type disease or all resistance settings.',
  'https://www.ema.europa.eu/en/medicines/human/EPAR/tagrisso'),
 ("Alzheimer's disease",'BACE1',['verubecestat'],['30970186'],'NCT01953601',
  'Verubecestat did not improve prodromal Alzheimer clinical outcomes; some outcomes worsened. Biomarker modulation is not clinical efficacy, and this is not universal target invalidity.',
  'https://pubmed.ncbi.nlm.nih.gov/30970186/'),
 ("Parkinson's disease",'LRRK2',['BIIB122'],['36807624'],'NCT05418673',
  'Early clinical safety/engagement is not established disease-modifying benefit. Distinguish the registry stop reason from a demonstrated efficacy failure. Contemporary efficacy/approval remains outside this small reference extract.',
  'https://pubmed.ncbi.nlm.nih.gov/36807624/')]

def capture(case):
 disease,symbol,names,pmids,nct,expected,regulator=case
 client=JsonClient(min_interval=0)
 target=TargetInput(disease_name=disease,target_symbol=symbol)
 result=Investigation(target=target,mode='live',resolved_target_id=resolve_target(client,target),resolution_status='resolved')
 provenance=[]
 for name in names:
  page=client.get(CHEMBL+'/molecule/search.json',{'q':name,'limit':30})
  mols=[m for m in page.get('molecules',[]) if normalize(m.get('pref_name') or '')==normalize(name)]
  if not mols:
   result.search_audit.append(SearchAudit(source='ChEMBL',operation='reference molecule search',url=CHEMBL+'/molecule/search.json',state='no_results',detail='No exact preferred-name compound: '+name))
   continue
  molecule=sorted(mols,key=lambda m:m['molecule_chembl_id'])[0];identifier=molecule['molecule_chembl_id']
  mechanisms=client.get(CHEMBL+'/mechanism.json',{'molecule_chembl_id':identifier,'target_chembl_id':result.resolved_target_id,'limit':100})['mechanisms']
  if not mechanisms:
   result.search_audit.append(SearchAudit(source='ChEMBL',operation='reference mechanism search',url=CHEMBL+'/mechanism.json',state='no_results',detail='No curated mechanism for exact compound; no drug-target link invented.'))
   continue
  result.compounds.append(Compound(chembl_id=identifier,name=molecule['pref_name'],synonyms=[s['molecule_synonym'] for s in molecule.get('molecule_synonyms',[])],
   mechanisms=[m.get('mechanism_of_action') or '' for m in mechanisms],max_phase=molecule.get('max_phase'),
   url='https://www.ebi.ac.uk/chembl/explore/compound/'+identifier,approval_source_url=CHEMBL+'/molecule/'+identifier+'.json'))
 retrieve_precedent(client,result)
 for label in result.regulatory_records:
  label['fields']={k:v[:4096] for k,v in label['fields'].items()}
  label['caution']+=' Recorded fixture retains at most the first 4096 characters per label section; consult full source for context.'
 # Keep only bounded exact extracts of each abstract; no full-text redistribution.
 for pmid in pmids:
  params={'query':'EXT_ID:'+pmid+' AND SRC:MED','format':'json','resultType':'core','pageSize':1}
  record=client.get(ENDPOINT,params)['resultList']['result'][0]
  if record['id']!=pmid:raise RuntimeError('Publication identity mismatch')
  full=re.sub(r'</?[A-Za-z][^>]*>',' ',html.unescape(record.get('abstractText') or '')).strip()
  conclusion=re.split(r'\bconclusions?\s*:?\s*',full,flags=re.I)[-1].strip()
  # At most 150 words, retaining original exact contiguous excerpts.
  prefix=' '.join(full.split()[:40]);tail=' '.join(conclusion.split()[:105])
  excerpt=prefix+'\n[intervening abstract text omitted]\nConclusions: '+tail
  pub=annotate(Publication(identifier='MED:'+pmid,title=record['title'],abstract=excerpt,doi=record.get('doi'),
     url='https://europepmc.org/article/MED/'+pmid,relevance='Curated reference excerpt; assess actual disease/population restrictions.'))
  result.publications.append(pub)
  provenance.append({'id':pub.identifier,'url':pub.url,'sha256_full_abstract':hashlib.sha256(full.encode()).hexdigest(),
    'note':'First 40 and conclusion 105 words; whitespace normalized, omitted text explicitly marked; not a full abstract.'})
 raw=client.get('https://clinicaltrials.gov/api/v2/studies/'+nct)
 trial=parse_trial(raw,result.compounds);trial.stop_reason=inspect_stop_reason(raw,nct,full_record=True)
 trial.disease_match='matched' if matches(' '.join(trial.conditions),target) else 'uncertain'
 result.trials=[trial]
 result.search_audit.extend([SearchAudit(source=source,operation='curated reference subset',url=url,state='found',returned=1,
  detail='Selected source extract, not an exhaustive production retrieval.') for source,url in [
   ('ChEMBL',CHEMBL),('Europe PMC',ENDPOINT),('ClinicalTrials.gov',trial.url)]])
 return {'target':symbol,'expected':expected,'regulatory_reference':regulator,'investigation':result.model_dump(mode='json'),
    'publication_extracts':provenance,'scope':'Curated subset to check retrieval/coverage invariants; no full live search or LLM evaluation.'}

if __name__=='__main__':
 start=time.perf_counter()
 with ThreadPoolExecutor(max_workers=5) as pool:cases=list(pool.map(capture,CASES))
 output={'captured_at_utc':datetime.now(timezone.utc).isoformat(),'cases':cases,
  'license_note':'ChEMBL CC BY-SA 3.0, original IDs/URLs retained. ClinicalTrials.gov public sponsor records. Publication excerpts have item-specific rights, no full text. FDA label submissions retain notices; no endorsement/approval inferred from listing.',
  'capture_seconds':round(time.perf_counter()-start,6),'paid_calls':0}
 path=Path('devils_advocate/fixtures/scientific_reference.json')
 path.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'cases':[{ 'target':c['target'],'compounds':len(c['investigation']['compounds']),'publications':len(c['investigation']['publications'])} for c in cases],
   'seconds':output['capture_seconds'],'paid_calls':0}))
