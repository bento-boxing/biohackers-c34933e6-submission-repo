"""Recorded scientific regression checks, separate from software test counts.

This measures preservation/coverage of curated evidence, not model accuracy.
Reference expectations never enter production retrieval or reasoning.
"""
import json,time,statistics
from pathlib import Path
from .models import Investigation
from .coverage import check_coverage
from .ai_reasoning import evidence_bundle
from .ai_config import AISettings
from .literature import annotate
from .relevance import disease_matches,mentions
from .disease_terms import matches
from .devil_advocate import classify_concern
from .experiment_designer import propose_experiment

ROOT=Path(__file__).parent

def evaluate():
 data=json.loads((ROOT/'fixtures/scientific_reference.json').read_text(encoding='utf-8'))
 cases=[];before_missed=after_missed=positive_cases=0;measurements=[]
 for case in data['cases']:
  i=Investigation.model_validate(case['investigation'])
  for p in i.publications:
   annotate(p)
   p.disease_match='matched' if matches(p.title+' '+p.abstract,i.target) else 'uncertain'
  approved=any(c.max_phase==4 for c in i.compounds)
  settings=AISettings()
  for _ in range(100):
   start=time.perf_counter();coverage=check_coverage(i);measurements.append((time.perf_counter()-start)*1000)
  i.coverage=coverage;packet=evidence_bundle(i,settings)
  names=[i.target.target_symbol,*[c.name for c in i.compounds]]
  visible=[p for p in i.publications if matches(p.title+' '+p.abstract,i.target) and any(mentions(p.title+' '+p.abstract,n) for n in names)]
  legacy=[p for p in i.publications if disease_matches(p.title+' '+p.abstract,i.target.disease_name) and any(mentions(p.title+' '+p.abstract,n) for n in names)]
  # These are reference labels for this evaluation only; not production answers.
  expected_positive=case.get('reference_positive_ids',[])
  if expected_positive:
   positive_cases+=1
   before_missed+=not bool(set(expected_positive)&{p.identifier for p in legacy})
   after_missed+=not bool(set(expected_positive)&{p.identifier for p in visible}&set(packet['sources']))
  missing=i.model_copy(deep=True);missing.publications=[]
  checks={
   'reference_context_preserved_and_scoped':all(p.identifier in packet['sources'] and
       (p.disease_match=='matched' or packet['sources'][p.identifier]['applicability']['disease_match']=='uncertain') for p in i.publications),
   'approval_metadata_preserved':all('approval_metadata' in packet['sources'][c.chembl_id]['fields'] for c in i.compounds if c.max_phase==4),
   'status_not_used_as_outcome':all(classify_concern(t.status)=='unknown' for t in i.trials),
   'missing_publications_abstains':check_coverage(missing).status=='INSUFFICIENT COVERAGE',
   # Without a verified synthesis the fallback is either an abstention or a flagged rule-based template,
   # never a design presented as AI-generated or validated.
   'fallback_experiment_labelled_not_ai':(lambda e:e.status=='INSUFFICIENT EVIDENCE FOR EXPERIMENT' or
       (e.status.startswith('Rule-based template') and any(l.startswith('Review flag:') for l in e.limitations)) or
       (missing.mode=='offline' and not e.status.startswith('AI-generated')))(propose_experiment(missing)),
   'all_curated_directions_kept':all(p.identifier in packet['sources'] for p in i.publications if p.direction_signals)}
  cases.append({'target':case['target'],'expected_conclusion':case['expected'],'checks':checks,
   'approved_precedent_in_fixture':approved,'coverage':coverage.status,'coverage_gaps':coverage.gaps,
   'selected':list(packet['sources']),'direction_candidates':{p.identifier:p.direction_signals for p in i.publications},
   'uncertainty':'Curated source subset; not an exhaustive clinical search or a verified Claude interpretation.'})
 return {'cases':cases,'checks_passed':sum(sum(c['checks'].values()) for c in cases),
  'checks_total':sum(len(c['checks']) for c in cases),
  'positive_evidence_omission':{'cases':positive_cases,'legacy_phrase_filter_misses':before_missed,'new_filter_and_packet_misses':after_missed,
   'meaning':'False-negative evidence omission in recorded reference replay, not measured AI scientific false-negative diagnoses.'},
  'coverage_check_ms':{'runs':len(measurements),'median':round(statistics.median(measurements),6),'p95':round(sorted(measurements)[int(.95*len(measurements))-1],6)},
  'paid_calls':0,'limitations':['No paid or semantic Claude evaluation performed.','Reference cases and expectations selected by implementer, not independently blinded.',
   'No absence-of-approval claim is made for BACE1/LRRK2; phase and source extracts only describe retrieved records.',
   'Direction detectors are triage signals; published efficacy and safety interpretations require expert adjudication.']}

if __name__=='__main__':
 report=evaluate();(ROOT/'validation/scientific_coverage_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(json.dumps(report,indent=2))
