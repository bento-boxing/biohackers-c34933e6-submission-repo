"""Opt-in read-only public-source diagnostic, never starts a job or model call."""
import sys,json,sqlite3,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from devils_advocate.models import Investigation,SearchAudit
from devils_advocate.http_client import JsonClient
from devils_advocate.literature import retrieve_publications
from devils_advocate.precedent import retrieve_precedent
from devils_advocate.coverage import check_coverage
from devils_advocate.disease_terms import resolve_disease_terms,matches

if __name__=='__main__':
 db=sqlite3.connect('file:devils_advocate/runtime/workbench.sqlite3?mode=ro',uri=True)
 rows=[json.loads(r[0])['investigation'] for r in db.execute('select result from jobs where result is not null')]
 i=Investigation.model_validate(next(r for r in rows if r['target']['target_symbol']=='CCR5'))
 db.close();client=JsonClient(min_interval=0);i.search_audit=[]
 for c in i.compounds:
  url='https://www.ebi.ac.uk/chembl/api/data/molecule/'+c.chembl_id+'.json'
  m=client.get(url)
  # ChEMBL sometimes returns phase as a decimal string; validate on assignment.
  c.max_phase=float(m['max_phase']) if m.get('max_phase') is not None else None
  c.approval_source_url=url
 with client.tracking() as phase:
  start=time.perf_counter();i.target=resolve_disease_terms(client,i.target,i.search_audit);retrieve_precedent(client,i);precedent=time.perf_counter()-start
 with client.tracking() as publications:
  start=time.perf_counter();i.publications=retrieve_publications(client,i.target,i.compounds,i.search_audit);pubtime=time.perf_counter()-start
 i.search_audit.append(SearchAudit(source='ChEMBL',operation='saved mechanism candidates with refreshed molecule phase',url='https://www.ebi.ac.uk/chembl/api/data',state='found',returned=len(i.compounds)))
 for trial in i.trials:trial.disease_match='matched' if matches(' '.join(trial.conditions),i.target) else 'uncertain'
 i.search_audit.append(SearchAudit(source='ClinicalTrials.gov',operation='saved trial set, not refetched',url='https://clinicaltrials.gov',state='not_searched',returned=len(i.trials)))
 i.coverage=check_coverage(i)
 report={'case':'Saved HIV infectious disease / CCR5, new public retrieval only',
  'before_publications':0,'after_publications':len(i.publications),
  'positive_candidates':[p.identifier for p in i.publications if 'positive_candidate' in p.direction_signals],
  'approved_compounds':[c.name for c in i.compounds if c.max_phase==4],
  'precedent_seconds':round(precedent,6),'precedent_profile':phase,
  'publication_seconds':round(pubtime,6),'publication_profile':publications,
  'search_audit':[a.model_dump(mode='json') for a in i.search_audit],'coverage':i.coverage.model_dump(mode='json'),
  'paid_calls':0,'limitation':'Saved trial set was not refetched; new publication/precedent retrieval and triage only. No LLM or end-to-end scientific accuracy evaluation.'}
 Path('devils_advocate/validation/coverage_live_ccr5.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(json.dumps({k:report[k] for k in ['after_publications','positive_candidates','approved_compounds','precedent_seconds','publication_seconds','paid_calls']}))
