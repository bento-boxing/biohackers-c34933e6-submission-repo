import type { Investigation } from '@/lib/contracts';
import { AssociationVisual } from './association-visual';

export function CoverageReport({investigation:i}:{investigation:Investigation}){
  const c=i.coverage;
  if(!c)return <aside className="notice warning">Coverage was not assessed for this historical recorded report. It cannot establish absence of effective treatments.</aside>;
  return <section className="panel panel-content" aria-label="Evidence coverage">
    <div className="eyebrow">EVIDENCE COVERAGE CHECK</div><h2>{c.status}</h2>
    <p>{c.caution}</p>{c.gaps.length>0&&<ul>{c.gaps.map((gap,index)=><li key={index}>{gap}</li>)}</ul>}
    <h3>{c.pathway==='preclinical_validation'?'Limited preclinical target-validation assessment':c.pathway==='clinical_precedent'?'Clinical-precedent assessment':'Assessment pathway unresolved'}</h3>
    <p>Claude eligibility: {c.reasoning_permitted?'Coverage permits this limited analysis.':'Not eligible; resolve the coverage gaps above.'}</p>
    <AssociationVisual investigation={i}/>
    <h3>Indication-specific approval versus target druggability</h3>
    {i.compounds.flatMap(compound=>(compound.regulatory_approvals||[]).map(record=><div className="evidence-item" key={compound.chembl_id+record.application_number}><a className="source-link" href={record.source_url} target="_blank" rel="noreferrer">{compound.name} · FDA {record.application_number}</a><p><strong>FDA original approval documented: {record.approval_dates.join(', ')}</strong></p><p>ChEMBL phase remains {compound.max_phase??'unknown'}. {record.disease_match==='lexical'?'The label mentions the selected disease; exact population and product restrictions require review.':'Indication applicability is unresolved.'}</p><p>{record.scope}</p></div>))}
    {i.compounds.filter(compound=>compound.max_phase===4).map(compound=>{const matched=compound.indications?.some(r=>r.approval_precedent&&['identifier','lexical'].includes(String(r.disease_match)));return <div key={compound.chembl_id} className="evidence-item"><a className="source-link" href={compound.url} target="_blank" rel="noreferrer">{compound.name} · {compound.chembl_id}</a><p><strong>{matched?'Matched indication record: review exact population and treatment restrictions.':'Target pharmacology only · No matched approved indication found.'}</strong></p><p>ChEMBL phase 4 for some indication. This does not establish approval or efficacy for the selected disease or population.</p><p>Indication lookup: {compound.indication_search_state||'not searched'}</p><details><summary>Indication records and applicability</summary><pre>{JSON.stringify(compound.indications||[],null,2)}</pre></details></div>;})}
    {!i.compounds.some(compound=>compound.max_phase===4)&&<p>No phase-4 precedent found in the retrieved compounds. This bounded search does not prove none exists.</p>}
    <details><summary>Source search coverage and limits</summary>{i.search_audit?.map((a,index)=><div className="evidence-item" key={index}><h3>{a.source} · {a.operation}</h3><p>{a.state} · {a.returned} returned · {a.relevant} visibly relevant{a.total!=null?` · ${a.total} total matches`:''}</p><p>{a.detail}</p><a className="source-link" href={a.url} target="_blank" rel="noreferrer">Source API</a><pre>{JSON.stringify(a.query,null,2)}</pre></div>)}</details>
    <details><summary>Evidence packet selection and omissions</summary><p>{c.selected_source_ids.length} trial/publication records selected; {c.omitted_source_ids.length} omitted. Stratified bounded selection is not a statistically representative sample.</p>{Object.entries(c.selection_reasons).map(([id,reasons])=><p key={id}><strong>{id}</strong>: {reasons.join('; ')}</p>)}<details><summary>Omitted source identifiers</summary><p>{c.omitted_source_ids.join(', ')||'None'}</p></details><pre>{JSON.stringify(c.facets,null,2)}</pre></details>
    <p className="fine-print">Coverage and selection check: {(c.duration_seconds*1000).toFixed(2)} ms. Direction signals are unadjudicated triage candidates, not clinical outcome findings.</p>
  </section>;
}
