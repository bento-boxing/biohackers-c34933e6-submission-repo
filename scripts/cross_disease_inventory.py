"""Offline inventory and citation checks for the cross-disease audit; no requests."""
import json,sys,hashlib
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from devils_advocate.models import AIClaim
from devils_advocate.ai_reasoning import validate_ai_claim
ROOT=Path('devils_advocate/validation/cross_disease')

def snapshot(name,phase,landmarks):
    path=ROOT/(name+'_'+phase+'_sources.json')
    if not path.exists():return None
    job=json.loads(path.read_text(encoding='utf-8'));result=job.get('result') or {};i=result.get('investigation') or {};coverage=i.get('coverage') or {};profile=result.get('timings',{}).get('retrieval',{})
    pubs={p['identifier']:p for p in i.get('publications',[])};selected=set(coverage.get('selected_source_ids',[]))
    records={t['nct_id']:t for t in i.get('trials',[])};records.update(pubs);records.update({c['chembl_id']:c for c in i.get('compounds',[])});records.update({r['id']:r for r in i.get('regulatory_records',[])})
    ai=i.get('ai') or {};bundle=ai.get('source_bundle',{});claims=[]
    for c in ai.get('accepted_claims',[]):
        refs=[]
        for ref in c['citations']:
            source=bundle.get('sources',{}).get(ref['source_id'],{});value=source.get('fields',{}).get(ref['field'])
            refs.append({'source_id':ref['source_id'],'field':ref['field'],'url':source.get('url'),
                'record_exists':ref['source_id'] in records,'exact_excerpt':isinstance(value,str) and ref['excerpt'] in value})
        claims.append({'claim_id':c['claim_id'],'text':c['text'],'relevance':c['relevance'],'uncertainty':c['uncertainty'],
            'citations':refs,'current_guard_objections':validate_ai_claim(AIClaim.model_validate(c),bundle)})
    return {'job_id':job['job_id'],'state':job['state'],'target':i.get('target'),'resolved_target_id':i.get('resolved_target_id'),
        'counts':{k:len(i.get(k,[])) for k in ['trials','compounds','publications']},
        'publication_scopes':dict(Counter(p['evidence_scope'] for p in pubs.values())),
        'coverage':coverage.get('status'),'pathway':coverage.get('pathway'),'gaps':coverage.get('gaps',[]),
        'selected_source_ids':list(selected),'source_limits':[a for a in i.get('search_audit',[]) if a['state']=='limit_reached'],
        'source_failures':[a for a in i.get('search_audit',[]) if a['state']=='failed'],
        'retrieval_seconds':profile.get('total_seconds'),'requests':profile.get('requests'),'cache_hits':profile.get('cache_hits'),
        'network_attempts':profile.get('network_attempts'),'cache_hit_rate':round(profile.get('cache_hits',0)/max(1,profile.get('cache_hits',0)+profile.get('requests',0)),6),
        'source_provenance_modes':sorted({r.get('provenance','') for r in profile.get('response_provenance',[])}),
        'provenance':result.get('provenance'),
        'landmarks':[{'id':r['id'],'title':r['title'],'url':r['url'],'retrieved':r['id'] in pubs,
            'sent':r['id'] in selected,'scope':pubs.get(r['id'],{}).get('evidence_scope')} for r in landmarks],
        'phase4_compounds':[{'name':c['name'],'id':c['chembl_id'],'molecule_type':c.get('molecule_type'),
            'matched_indications':[r for r in c.get('indications',[]) if r.get('approval_precedent') and r.get('disease_match') in ['identifier','lexical']]} for c in i.get('compounds',[]) if c.get('max_phase')==4],
        'regulatory_source_urls':[r['url'] for r in i.get('regulatory_records',[])],
        'authoritative_approval_context':[{'compound':c['name'],'chembl_id':c['chembl_id'],'chembl_phase':c.get('max_phase'),'records':c.get('regulatory_approvals',[])} for c in i.get('compounds',[]) if c.get('regulatory_approvals')],
        'reason_examples':[{'nct_id':t['nct_id'],'url':t['url'],'why_stopped':t['why_stopped'],
            'relationship':t['relationship'],'disease_match':t['disease_match'],'state':t['stop_reason']['state']} for t in i.get('trials',[]) if t['why_stopped']][:8],
        'extractive_claims':len(i.get('claims',[])),'extractive_quotes_verified':sum(c['verified'] for c in i.get('claims',[])),
        'ai_status':ai.get('status'),'ai_warnings':ai.get('warnings',[]),'calls':ai.get('calls',[]),
        'model_seconds':round(sum(c.get('duration_seconds') or 0 for c in ai.get('calls',[])),6),
        'accepted_claims':claims,'adjudications':[{'round':r['round_number'],'findings':r['adjudications'],'deterministic_objections':r['deterministic_objections']} for r in ai.get('rounds',[])],
        'prior_art_check':ai.get('prior_art_check',{}),'experiment':result.get('experiment')}

if __name__=='__main__':
    refs=json.loads((ROOT/'references.json').read_text());landmarks=json.loads((ROOT/'landmarks.json').read_text())['cases']
    cases=[]
    for r in refs:
        name=r['case'];snapshots={phase:snapshot(name,phase,landmarks.get(name,[])) for phase in ['cold','final','warm','verified','refreshed','refreshed_warm','paid','labels','regulatory']}
        cases.append({'case':name,'identity_reference':r,'snapshots':{k:v for k,v in snapshots.items() if v is not None}})
    output={'method':'Offline review of actual Next/Flask/worker/SQLite reports and independent landmark lookups. Exact citation checks do not establish semantic entailment.',
        'cases':cases,'paid_ledger':json.loads((ROOT/'paid_ledger.json').read_text()) if (ROOT/'paid_ledger.json').exists() else None}
    (ROOT/'inventory.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    for c in cases:
        s=c['snapshots'].get('verified') or c['snapshots']['cold'];print(json.dumps({'case':c['case'],'coverage':s['coverage'],'pathway':s['pathway'],'counts':s['counts'],'landmarks':[(r['id'],r['retrieved']) for r in s['landmarks']]}))
