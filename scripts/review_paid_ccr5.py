"""Offline provenance recheck and measured attempt accounting; never calls an LLM.

Human scientific/novelty assessment is deliberately separate from these checks.
"""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from devils_advocate.models import AIClaim
from devils_advocate.ai_reasoning import validate_ai_claim

if __name__=='__main__':
    root=Path('devils_advocate/validation')
    job=json.loads((root/'live_gemini_ccr5_sources.json').read_text(encoding='utf-8'))
    result=job.get('result') or {};i=result.get('investigation') or {};ai=i.get('ai') or {}
    bundle=ai.get('source_bundle') or {'sources':{}}
    records={r['nct_id']:r for r in i.get('trials',[])}
    records.update({p['identifier']:p for p in i.get('publications',[])})
    records.update({c['chembl_id']:c for c in i.get('compounds',[])})
    records.update({r['id']:r for r in i.get('regulatory_records',[])})
    claims=[]
    for claim in ai.get('accepted_claims',[]):
        citations=[]
        for c in claim['citations']:
            source=bundle['sources'].get(c['source_id'],{});raw=records.get(c['source_id'])
            value=source.get('fields',{}).get(c['field'])
            # Exact packet support is necessary; meaning still needs human review.
            citations.append({'source_id':c['source_id'],'field':c['field'],'url':source.get('url'),
                'retrieved_record_exists':raw is not None,'exact_excerpt_in_packet':isinstance(value,str) and c['excerpt'] in value,
                'note':'Compound approval_metadata is constructed source-linked metadata, not a verbatim registry prose field.' if c['field']=='approval_metadata' else ''})
        claims.append({'claim_id':claim['claim_id'],'kind':claim['kind'],'text':claim['text'],
            'relevance':claim['relevance'],'uncertainty':claim['uncertainty'],'citations':citations,
            'deterministic_objections':validate_ai_claim(AIClaim.model_validate(claim),bundle)})
    objections=[]
    for r in ai.get('rounds',[]):
        for f in r['adjudications']:
            deterministic=r['deterministic_objections'].get(f['claim_id'],[])
            if f['verdict']!='supported' or deterministic:
                objections.append({'round':r['round_number'],'claim_id':f['claim_id'],'verdict':f['verdict'],
                    'finding':f['finding'],'revision_request':f['revision_request'],'deterministic_objections':deterministic})
    previous=root/'live_gemini_ccr5_initial_sources.json'
    previous_calls=len(json.loads(previous.read_text())['result']['investigation']['ai']['calls']) if previous.exists() else 0
    calls=ai.get('calls',[])
    output={'job_id':job['job_id'],'technical_job_state':job['state'],'ai_status':ai.get('status'),
        'prior_failed_job_attempts':previous_calls,'current_attempts':len(calls),'aggregate_attempts':previous_calls+len(calls),
        'within_authorized_five':previous_calls+len(calls)<=5,'coverage':i.get('coverage',{}).get('status'),
        'pathway':i.get('coverage',{}).get('pathway'),'retrieval_seconds':result.get('timings',{}).get('retrieval',{}).get('total_seconds'),
        'attempts':[{'role':c['role'],'success':c['success'],'seconds':c.get('duration_seconds'),'payload_bytes':c.get('payload_bytes'),'usage':c['usage'],'error':c['error']} for c in calls],
        'model_attempt_seconds':sum(c.get('duration_seconds') or 0 for c in calls),
        'accepted_claims':claims,'rejected_or_revised':objections,
        'accepted_citations_all_grounded':bool(claims) and all(not c['deterministic_objections'] and all(x['retrieved_record_exists'] and x['exact_excerpt_in_packet'] for x in c['citations']) for c in claims),
        'scientific_review_status':'Requires separate human assessment of entailment, population scope, established efficacy and experimental novelty; these checks do not prove scientific correctness.'}
    (root/'live_gemini_ccr5_verification.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(output,ensure_ascii=True,indent=2))
