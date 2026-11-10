"""Measure packet sizes and optional public-data cache reuse. Never invokes the model."""
import argparse
import json
from pathlib import Path
import time
from .ai_reasoning import experimental_evidence
from .http_client import JsonClient, RetrievalError
from .models import AIReport

def measure_packets(report: AIReport):
    if not report.rounds:
        return {}
    first=report.rounds[0]
    base={'evidence':report.source_bundle,'initial_rule_based_assessment':'Recorded assessment for request-size comparison.'}
    revision_old={**base,'previous_draft':first.draft.model_dump(mode='json'),'revision_feedback':first.model_dump(mode='json')}
    revision_new={**base,'previous_draft':first.draft.model_dump(mode='json'),'revision_feedback':{
        'deterministic_objections':first.deterministic_objections,'adjudications':[f.model_dump(mode='json') for f in first.adjudications]}}
    design_old={**base,'accepted_claims':[c.model_dump(mode='json') for c in report.accepted_claims]}
    design_new={**design_old,'evidence':experimental_evidence(report.source_bundle,report.accepted_claims)}
    def size(value,compact=False):
        return len(json.dumps(value,ensure_ascii=False,**({'separators':(',',':')} if compact else {})).encode('utf-8'))
    return {name:{'before_bytes':size(old),'after_bytes':size(new,True),'bytes_removed':size(old)-size(new,True)}
            for name,old,new in [('initial_challenge',base,base),('revision',revision_old,revision_new),('experimental_challenger',design_old,design_new)]}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--live-cache-check',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).parent
    archived=AIReport.model_validate(json.loads((root/'validation/gemini_report.json').read_text(encoding='utf-8'))['ai'])
    result={'method':'Reconstructed request shapes using existing recorded BACE1 audit. No scientific records changed.',
            'packets':measure_packets(archived),'live_gemini_calls':0,
            'limitation':'Packet byte reductions do not measure provider latency or token savings. No High-versus-Medium paid comparison was performed.'}
    if args.live_cache_check:
        client=JsonClient(min_interval=0)
        try:
            events=[]
            with client.tracking(events.append) as profile:
                start=time.perf_counter();client.get('https://www.ebi.ac.uk/chembl/api/data/target/CHEMBL4822.json');cold=time.perf_counter()-start
                start=time.perf_counter();client.get('https://www.ebi.ac.uk/chembl/api/data/target/CHEMBL4822.json');warm=time.perf_counter()-start
            result['cache_check']={'uncached_seconds':round(cold,6),'cached_seconds':round(warm,6),'profile':profile,
                                   'note':'Actual single-endpoint timings for this run; cache behavior already existed and is now instrumented.'}
        except RetrievalError as exc:
            result['cache_check']={'error':'Public ChEMBL record unavailable during the timing check.','status_code':exc.status_code}
    (root/'validation/presentation_latency.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
