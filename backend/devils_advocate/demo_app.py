"""Run from backend/: python -m streamlit run devils_advocate/demo_app.py."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import streamlit as st
from devils_advocate import investigate_target, propose_experiment
from devils_advocate.ui_state import REPORT_VERSION, invalidate_results
from devils_advocate.ai_config import load_ai_settings
from devils_advocate.ai_reasoning import run_ai_reasoning
from devils_advocate.stop_reasons import stop_reason_label
from devils_advocate.models import Trial

st.set_page_config(page_title="Target Challenger", page_icon="🔬", layout='wide')
st.title("Devil's Advocate · Target Challenger")
st.caption('Disease + target → evidence → verification → proposed experiment → researcher decision')
disease = st.text_input('Disease', "Alzheimer's disease")
target = st.text_input('Protein target symbol', 'BACE1')
offline = st.toggle('Offline recorded BACE1 example', value=True)
st.caption('OFFLINE — recorded BACE1 example only' if offline else 'LIVE — real biomedical API retrieval')
try:
    ai_settings = load_ai_settings()
except ValueError:
    st.error('Invalid AI configuration. Check the documented provider, thinking level and numeric limits in .env. Private values are not displayed.')
    st.stop()
st.caption(f"AI reasoning: {'ENABLED' if ai_settings.enabled and not offline else 'DISABLED'} · Provider: {ai_settings.provider} · Model: {ai_settings.model or 'not configured'}")
st.caption('Offline mode makes no Gemini calls.' if offline else
           f'Clicking Challenge authorizes up to {ai_settings.max_calls} Gemini request attempts when AI is enabled. No automatic experiment execution.')
request_key = (disease, target, offline, json.dumps(ai_settings.model_dump(mode='json'), sort_keys=True), REPORT_VERSION)
invalidate_results(st.session_state, request_key)
if st.button('Challenge this target', type='primary'):
    invalidate_results(st.session_state, request_key, force=True)
    if not disease.strip() or not target.strip():
        st.error('Enter a disease and target symbol.')
    else:
        try:
            with st.spinner('Retrieving and checking evidence…'):
                investigation = investigate_target({'disease_name': disease.strip(), 'target_symbol': target.strip()}, offline=offline)
                progress_display = st.empty()
                def show_ai_progress(calls):
                    progress_display.caption(f"AI calls completed: {sum(c.success for c in calls)} / {len(calls)} attempted · Current role: {calls[-1].role}")
                investigation.ai = run_ai_reasoning(investigation, settings=ai_settings, on_progress=show_ai_progress)
                progress_display.empty()
                st.session_state['result'] = investigation.model_dump(mode='json')
                st.session_state['experiment'] = propose_experiment(investigation).model_dump(mode='json')
        except (ValueError, OSError) as exc:
            st.error(str(exc))
if 'result' in st.session_state:
    r = st.session_state['result']
    st.info(f"{r['mode'].upper()} · {r['target']['target_symbol']} · {r['target']['disease_name']} · {r['conclusion']}")
    st.caption(f"Resolved ChEMBL target: {r['resolved_target_id'] or 'unresolved'}")
    ai = r.get('ai')
    if ai:
        st.caption(f"AI status: {ai['status'].upper()} · AI calls completed: {sum(c['success'] for c in ai['calls'])} / {len(ai['calls'])} attempted")
        for warning in ai['warnings']:
            st.warning(warning)
        if ai['status'] != 'completed':
            st.info('The evidence analysis and experiment below use deterministic rules; no completed Gemini report is being claimed.')
        with st.expander('Safe AI usage and audit metadata'):
            st.json({'provider': ai['provider'], 'model': ai['model'], 'calls': ai['calls'],
                     'sent_source_ids': ai['sent_source_ids'], 'human_approval_required': ai['human_approval_required']})
        st.subheader('Scientific Challenge & Revision')
        st.write('Initial scientific assessment (deterministic):', r['conclusion'])
        if ai['rounds']:
            for audit in ai['rounds']:
                with st.expander(f"Challenge round {audit['round_number'] + 1}", expanded=True):
                    st.write('Challenger assessment (AI interpretation):', audit['draft']['initial_assessment'])
                    findings = {item['claim_id']: item for item in audit['adjudications']}
                    for claim in audit['draft']['claims']:
                        accepted = claim['claim_id'] in audit['accepted_claim_ids']
                        st.markdown(f"**{claim['claim_id']} · {'ACCEPTED FOR REVIEW' if accepted else 'NOT ACCEPTED'} · {claim['kind']}**")
                        st.write("Challenger's objection:", claim['text'])
                        st.caption('Relevance: ' + claim['relevance'])
                        st.caption('Remaining uncertainty: ' + claim['uncertainty'])
                        for citation in claim['citations']:
                            url = ai['source_urls'].get(citation['source_id'])
                            if url:
                                st.markdown(f"[Source: {citation['source_id']}]({url})")
                            else:
                                st.warning('Unverified citation: ' + citation['source_id'])
                            st.write(citation['excerpt'])
                        for objection in audit['deterministic_objections'].get(claim['claim_id'], []):
                            st.warning(objection)
                        finding = findings.get(claim['claim_id'])
                        if finding:
                            st.write('Adjudicator finding:', finding['verdict'], finding['finding'])
                            if finding['revision_request']:
                                st.write('Requested revision:', finding['revision_request'])
        if ai['reassessment']:
            st.write('Revised assessment (AI synthesis for researcher review):', ai['reassessment']['assessment'])
            for uncertainty in ai['reassessment']['remaining_uncertainty']:
                st.caption(uncertainty)
        st.caption('LLM agreement is not independent evidence. Accepted interpretations still require expert review and researcher approval.')
    for error in r.get('retrieval_errors', []):
        st.error('A live source could not be retrieved. This report may be incomplete; no offline evidence was substituted.')
        with st.expander('Retrieval error details'):
            st.code(error)
    if not offline and not r['resolved_target_id']:
        st.warning('Human target could not be resolved. Check the symbol; downstream evidence retrieval was skipped.')
    with st.expander('Historical relevance and recommendations', expanded=True):
        if not r.get('assessments'):
            st.write('Insufficient evidence for a historical target assessment.')
        for a in r.get('assessments', []):
            st.markdown(f"**{', '.join(a['source_ids'])} · {a['concern']} · {a['recommendation'].upper()}**")
            for source_id in a['source_ids']:
                source = next((t for t in r['trials'] if t['nct_id'] == source_id), None)
                if source:
                    st.markdown(f"[Registry evidence: {source_id}]({source['url']})")
            st.write(a['historical_evidence'])
            st.write(a['relevance'])
            st.write(a['rationale'])
            st.caption(a['compound_specificity'] + ' ' + a['target_engagement'])
            for limit in a['limitations']:
                st.caption(limit)
    tabs = st.tabs(['Compounds & trials', 'Evidence & citations', 'Uncertainty', 'Proposed experiment'])
    with tabs[0]:
        for c in r['compounds']:
            st.markdown(f"[{c['name']} · {c['chembl_id']}]({c['url']})")
            st.write('Mechanism:', '; '.join(c['mechanisms']))
        if not r['compounds']:
            st.write('No compounds retrieved.')
        for t in r['trials']:
            with st.expander(f"{t['nct_id']} · {t['status']} · {t['relationship']} compound match"):
                st.link_button('Registry source', t['url'])
                trial_record = Trial.model_validate(t)
                st.write('Recorded stop reason:', stop_reason_label(trial_record))
                st.caption('Stop-reason state: ' + trial_record.stop_reason.state)
                if trial_record.stop_reason.source_url:
                    st.markdown(f"[Full ClinicalTrials.gov API record]({trial_record.stop_reason.source_url})")
                st.write(t)
    with tabs[1]:
        st.caption('Verified means identifier and excerpt match the retrieved record. It does not certify causality or study quality.')
        for stance in ['supporting', 'contradictory', 'context']:
            st.subheader('Neutral / Insufficient' if stance == 'context' else stance.capitalize())
            claims = [c for c in r['claims'] if c['stance'] == stance]
            if not claims:
                st.write('No evidence automatically assigned to this category; review retrieved publications below.')
            for c in claims:
                st.write(f"{c['concern'].upper()} · {c['kind']} · {c['text']}")
                st.caption(f"{c['source_id']} / {c['source_field']} · {c['relevance']}")
                st.caption('Uncertainty: ' + c['uncertainty'])
                sources = {s.get('nct_id', s.get('identifier')): s['url'] for s in r['trials'] + r['publications']}
                if c['source_id'] in sources:
                    st.markdown(f"[Source record]({sources[c['source_id']]})")
        for p in r['publications']:
            st.markdown(f"[{p['identifier']} · {p['title']}]({p['url']})")
            with st.expander('Publication abstract'):
                st.write(p['abstract'] or 'Abstract unavailable.')
        st.write('Verification objections and revisions:', r['revisions'])
    with tabs[2]:
        for note in r['retrieval_notes'] + r['missing_information']:
            st.write('•', note)
    with tabs[3]:
        st.warning('UNVALIDATED PROPOSAL — not performed or validated. High-level research design only.')
        st.caption('Generated by Gemini Experimental Challenger.' if ai and ai['status'] == 'completed' else 'Generated by the deterministic experiment designer; Gemini was not used for this proposal.')
        experiment = st.session_state['experiment']
        for label, field in [('Research question', 'question'), ('Competing explanations', 'competing_explanations'),
                             ('Proposed experimental model', 'model'), ('Measurements / readouts', 'measurement'),
                             ('Controls', 'controls'), ('Possible results and interpretations', 'possible_results'),
                             ('Limitations', 'limitations'), ('Decision impact', 'decision_impact')]:
            st.subheader(label)
            value = experiment[field]
            if isinstance(value, list):
                for item in value:
                    st.write('•', item)
            else:
                st.write(value)
        st.caption('Evidence anchors: ' + (', '.join(experiment['evidence_ids']) or 'None; provisional design only.'))
        with st.expander('Raw experiment JSON'):
            st.json(experiment)
    decision = st.radio('Researcher decision', ['Investigate', 'Revise', 'Stop'], horizontal=True, key='researcher_decision')
    rationale = st.text_area('Decision rationale', key='decision_rationale')
    approved = st.checkbox('I have reviewed the evidence and recorded this research decision.', key='researcher_approved')
    st.caption('No experiment or further research action is executed by this application.')
    export = {'investigation': r, 'experiment': st.session_state['experiment'],
              'researcher_decision': decision, 'decision_rationale': rationale,
              'researcher_approved': approved}
    st.download_button('Download research report (JSON)', json.dumps(export, indent=2),
                       'target_challenge.json', 'application/json')
st.caption('Sources: ChEMBL (CC BY-SA 3.0), ClinicalTrials.gov (sponsor-reported records), Europe PMC (item-specific reuse rights).')
st.markdown('[ChEMBL attribution](https://www.ebi.ac.uk/chembl/) · [Registry terms](https://clinicaltrials.gov/about-site/terms-conditions) · [Europe PMC copyright](https://europepmc.org/Copyright)')
