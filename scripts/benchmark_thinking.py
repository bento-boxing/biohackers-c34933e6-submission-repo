"""Source-identical Medium/High comparison, opt-in and separately authorized.

--prepare makes NO model/network requests. --paid-authorized permits at most
five attempts per arm (ten aggregate). An existing ledger prevents paid replay.
"""
import argparse,copy,hashlib,json,sys,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from devils_advocate.models import Investigation,AICall
from devils_advocate.ai_config import load_ai_settings,AISettings
from devils_advocate.ai_reasoning import evidence_bundle,run_ai_reasoning
from devils_advocate.ai_client import GeminiRunner
from devils_advocate.prior_art import prior_art_context
from devils_advocate.coverage import check_coverage

OUT=Path('devils_advocate/validation/optimization')
PACKET=OUT/'thinking_packet.json'
LEDGER=OUT/'thinking_paid_ledger.json'

def sha(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true');parser.add_argument('--paid-authorized',action='store_true')
    parser.add_argument('--resume-after-network-failure',action='store_true',help='Explicit operator action; preserve and count prior failed connection attempts.')
    args=parser.parse_args();OUT.mkdir(exist_ok=True)
    old=Path('devils_advocate/validation')
    i=Investigation.model_validate(json.loads((old/'live_gemini_ccr5_sources.json').read_text(encoding='utf-8'))['result']['investigation'])
    report=json.loads((old/'live_gemini_ccr5_report.json').read_text(encoding='utf-8'))
    i.coverage=check_coverage(i);bundle=evidence_bundle(i,AISettings())
    prior=prior_art_context(i,[c['text']+' '+c['uncertainty'] for c in report['ai']['accepted_claims']],exclude_ids=bundle['sources'])
    for p in prior:
        bundle['sources'][p.identifier]={'url':p.url,'fields':{'title':p.title,'abstract':p.abstract[:2400],'conclusion_excerpt':p.conclusion_excerpt[:2400]},
            'prior_art_context':True,'applicability':{'evidence_scope':p.evidence_scope},'caution':'Recorded question-relevant prior art, not an independent scientific finding.'}
    if args.prepare:
        PACKET.write_text(json.dumps({'origin':'RECORDED public evidence, identical source collection for both thinking levels.',
            'source_sha256':sha(bundle['sources']),'source_ids':list(bundle['sources']),'evidence':bundle,
            'limits':{'per_arm':5,'aggregate':10},'prior_art_ids':[p.identifier for p in prior]},ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'prepared':str(PACKET),'source_sha256':sha(bundle['sources']),'source_count':len(bundle['sources']),'paid_calls':0}));sys.exit(0)
    if not args.paid_authorized:parser.error('Separate explicit paid authorization is required; use --prepare for zero-call preparation.')
    previous=None
    if LEDGER.exists():
        if not args.resume_after_network_failure:raise SystemExit('Existing paid ledger: no automatic repeat/resume is permitted. Inspect it before requesting any additional authorization.')
        previous=json.loads(LEDGER.read_text(encoding='utf-8'))
        attempts=[c for a in previous['arms'].values() for c in a['calls']]
        assert attempts and all(not c['success'] and 'connection could not be established' in (c['error'] or '') for c in attempts),'Resume restricted to reviewed connection-only failures.'
    frozen=json.loads(PACKET.read_text(encoding='utf-8'));assert frozen['source_sha256']==sha(bundle['sources']),'Recorded packet changed; re-prepare and review before authorization.'
    ledger=previous or {'authorized_aggregate_max':10,'per_arm_max':5,'source_sha256':frozen['source_sha256'],'origin':'RECORDED','arms':{}}
    assert ledger['source_sha256']==frozen['source_sha256']
    LEDGER.write_text(json.dumps(ledger,indent=2),encoding='utf-8')
    for level in ['medium','high']:
        config=load_ai_settings().model_copy(update={'enabled':True,'thinking_level':level,'max_calls':5})
        packet_hashes=[]
        def progress(calls):
            ledger['arms'][level]={'calls':[c.model_dump(mode='json') for c in calls]}
            assert sum(len(a['calls']) for a in ledger['arms'].values())<=10
            LEDGER.write_text(json.dumps(ledger,indent=2),encoding='utf-8')
        class FrozenRunner(GeminiRunner):
            def generate(self,role,instruction,payload,schema):
                packet_hashes.append(sha(payload['evidence']['sources']))
                assert packet_hashes[-1]==frozen['source_sha256'],'Agent sources differ from the frozen benchmark.'
                return super().generate(role,instruction,payload,schema)
        runner=FrozenRunner(config,on_progress=progress)
        runner.calls=[AICall.model_validate(c) for c in ledger['arms'].get(level,{}).get('calls',[])]
        started=time.perf_counter()
        try:
            with patch('devils_advocate.ai_reasoning.evidence_bundle',side_effect=lambda *a:copy.deepcopy(frozen['evidence'])),\
                 patch('devils_advocate.ai_reasoning.experimental_evidence',side_effect=lambda *a:copy.deepcopy(frozen['evidence'])),\
                 patch('devils_advocate.ai_reasoning.prior_art_context',return_value=prior):
                result=run_ai_reasoning(i.model_copy(deep=True),settings=config,runner=runner)
        finally:runner.close()
        record={'thinking_level':level,'seconds':round(time.perf_counter()-started,6),'report':result.model_dump(mode='json'),
            'agent_source_hashes':packet_hashes,'source_identical':all(h==frozen['source_sha256'] for h in packet_hashes),
            'quality_note':'Human review required for scientific entailment, competing hypotheses and clinical scope; prior-art/quote checks alone are not scientific correctness.'}
        report_path=OUT/('thinking_'+level+'_report.json')
        if previous and report_path.exists():
            (OUT/('thinking_'+level+'_connection_failure.json')).write_text(report_path.read_text(encoding='utf-8'),encoding='utf-8')
        report_path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'thinking':level,'seconds':record['seconds'],'attempts':len(result.calls),'status':result.status,'source_identical':record['source_identical']}),flush=True)
