"""Verify source identity and exact field grounding; never certify causality."""
from .models import Claim, Investigation, Publication, Revision, Trial

def verify_claims(investigation: Investigation, claims: list[Claim]) -> tuple[list[Claim], list[Revision]]:
    sources = {t.nct_id: t for t in investigation.trials}
    sources.update({p.identifier: p for p in investigation.publications})
    accepted, objections = [], []
    for claim in claims:
        source = sources.get(claim.source_id)
        field = getattr(source, claim.source_field, None) if source else None
        permitted = ['title', 'abstract'] if isinstance(source, Publication) else ['status', 'why_stopped']
        if claim.source_field not in permitted or not isinstance(field, str) or not claim.excerpt.strip() or claim.excerpt not in field:
            objections.append(Revision(claim_id=claim.claim_id,
                objection='Identifier or exact source excerpt could not be verified.',
                action='Rejected; reasoning agent must revise from retrieved fields.'))
        elif claim.kind == 'fact' and claim.text != claim.excerpt:
            objections.append(Revision(claim_id=claim.claim_id,
                objection='Fact wording differs from source excerpt; entailment is unproven.',
                action='Revised to the exact source excerpt.'))
            accepted.append(claim.model_copy(update={'text': claim.excerpt, 'verified': True}))
        else:
            accepted.append(claim.model_copy(update={'verified': True}))
    grounded = []
    for claim in accepted:
        source = sources[claim.source_id]
        changes = {'source_url': source.url}
        # Excerpt matching proves provenance, not efficacy. Never accept a
        # therapeutic stance merely because an arbitrary sentence was cited.
        eligible = (isinstance(source, Trial) and claim.source_field == 'why_stopped'
                    and source.relationship == 'verified' and source.disease_match == 'matched'
                    and claim.concern in ['efficacy', 'safety'] and claim.kind == 'fact'
                    and claim.excerpt == source.why_stopped)
        if eligible:
            from .devil_advocate import classify_concern
            eligible = classify_concern(source.why_stopped) == claim.concern
        if claim.stance != 'context' and (not eligible or claim.stance == 'supporting'):
            changes.update(stance='context', uncertainty='Insufficient evidence: stance requires scientific adjudication.')
            objections.append(Revision(claim_id=claim.claim_id, objection='Source grounding does not establish this scientific stance.',
                                       action='Reclassified as Neutral/Insufficient.'))
        if claim.kind == 'interpretation':
            changes['uncertainty'] = 'Source-linked interpretation only; scientific entailment has not been verified.'
        grounded.append(claim.model_copy(update=changes))
    return grounded, objections
