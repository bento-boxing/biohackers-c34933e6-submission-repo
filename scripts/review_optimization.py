"""Offline review of measured optimization outputs. Makes zero model/API calls."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from devils_advocate.ai_reasoning import validate_ai_claim
from devils_advocate.models import AIClaim,Experiment,Investigation
from devils_advocate.prior_art import check_prior_art

if __name__=='__main__':
    root=Path('devils_advocate/validation'); out=root/'optimization'
    raw=json.loads((root/'live_gemini_ccr5_sources.json').read_text(encoding='utf-8'))['result']['investigation']
    i=Investigation.model_validate(raw)
    record_ids={t.nct_id for t in i.trials}|{p.identifier for p in i.publications}|{c.chembl_id for c in i.compounds}|{r['id'] for r in i.regulatory_records}
    arms={}
    for level in ['medium','high']:
        saved=json.loads((out/('thinking_'+level+'_report.json')).read_text(encoding='utf-8')); report=saved['report']; bundle=report['source_bundle']
        claims=[]
        for c in report['accepted_claims']:
            refs=[]
            for ref in c['citations']:
                field=bundle['sources'].get(ref['source_id'],{}).get('fields',{}).get(ref['field'])
                refs.append({'source_id':ref['source_id'],'retrieved_record_exists':ref['source_id'] in record_ids,
                    'exact_excerpt':isinstance(field,str) and ref['excerpt'] in field})
            claims.append({'claim_id':c['claim_id'],'citations':refs,
                'current_guard_objections':validate_ai_claim(AIClaim.model_validate(c),bundle)})
        calls=report['calls']; successful=[c for c in calls if c['success']]
        proposal=report.get('prior_art_check',{}).get('original_proposal')
        arms[level]={'technical_status':report['status'],'measured_orchestration_seconds':saved['seconds'],
            'all_attempts':len(calls),'successful_calls':len(successful),
            'connection_failures':sum('connection could not be established' in c['error'] for c in calls),
            'provider_attempt_seconds':round(sum(c['duration_seconds'] or 0 for c in calls if 'connection could not be established' not in c['error']),6),
            'stages':[{'role':c['role'],'seconds':c['duration_seconds'],'success':c['success'],'payload_bytes':c['payload_bytes'],'usage':c['usage'],'error':c['error']} for c in calls],
            'accepted_claim_checks':claims,'exact_citations':sum(x['exact_excerpt'] for c in claims for x in c['citations']),
            'total_citations':sum(len(c['citations']) for c in claims),
            'revised_or_removed_claim_ids':sorted({f['claim_id'] for r in report['rounds'] for f in r['adjudications'] if f['verdict']!='supported' or r['deterministic_objections'].get(f['claim_id'])}),
            'source_identical':saved['source_identical'],
            'current_prior_art_guard_replay':check_prior_art(i.model_copy(deep=True),Experiment.model_validate(proposal)) if proposal else None,
            'scientific_review':(
                'Recognised population-scoped efficacy and safety warnings. Adjudicator rejected population conflation. Accepted CLM-4 still bundles four compound approval statements with citations to only two compound records; current offline guard flags both missing citations. Do not present the preserved paid output as fully verified. Proposed off-target/on-target liver-toxicity hypotheses are plausible but require primary mechanistic support and expert model review. Original lexical checker falsely flagged generic binding/clinical background; current offline replay removes those blocks, without establishing novelty.'
                if level=='medium' else
                'Recognised established R5 combination-therapy efficacy. Accepted CLM-2 overstates absence of activity in dual/mixed virus and combines cross-population explanatory evidence; current guard flags the causal attribution. Adjudicator requested compound-specific citations for another claim. Experimental output was incomplete, so hypotheses, proposal citations and prior-art awareness cannot be scored as successful.')}
    historic=json.loads((root/'live_gemini_ccr5_report.json').read_text(encoding='utf-8'))['experiment']
    bad=check_prior_art(i,Experiment.model_validate(historic))
    summary={'method':'Offline source/quote validation plus explicit qualitative review of the two actual paid outputs. No new paid or public requests.',
        'arms':arms,'aggregate_attempts':sum(a['all_attempts'] for a in arms.values()),
        'authorized_maximum':10,'historic_bad_proposal_current_guard':bad,
        'limitations':['One sample per level; no statistical quality or latency claim.',
            'Source collection identical; adjudication/design prompts differ because generated claims differ.',
            'Connection failures count toward five attempts per arm and leave insufficient room for a full revision/re-adjudication/design sequence; rejected claims were removed.',
            'Recorded corpus prior-art checks only in paid comparison; normal live jobs additionally perform a bounded targeted Europe PMC search.',
            'Exact citation matching is not semantic entailment or proof of novelty.',
            'No combined live-retrieval-plus-Gemini optimized end-to-end timing was measured.']}
    (out/'scientific_review.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    retrieval=json.loads((out/'retrieval_report.json').read_text(encoding='utf-8'))
    retrieval['historic_bad_proposal_replay']=bad
    (out/'retrieval_report.json').write_text(json.dumps(retrieval,indent=2),encoding='utf-8')
    print(json.dumps({'aggregate_attempts':summary['aggregate_attempts'],
        'arms':{k:{s:a[s] for s in ['technical_status','provider_attempt_seconds','exact_citations','total_citations']} for k,a in arms.items()},
        'bad_proposal_decision':bad['decision']}))
