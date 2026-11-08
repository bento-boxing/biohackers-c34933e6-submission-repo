"""Negation-aware outcome direction and clinical-context comparability for triage text.

Both are heuristics over titles, abstracts and quoted excerpts. They decide which deterministic
objections fire; they never adjudicate an outcome or establish that two studies agree or disagree.
"""
import re

# A clause ends at sentence punctuation or a contrastive conjunction; "neither" scopes over a whole
# clause (it governs comma-separated lists), other negators only over the few words before the phrase.
CLAUSE_BREAK = r'[.;:!?]|\b(?:but|whereas|although|though|however|while|yet)\b'
NEAR_NEGATOR = re.compile(r"\b(?:not|no|never|without|failed to|fails to|did not|does not|do not|was not|were not|is not|are not|nor)\b|n't\b", re.I)
SCOPE_NEGATOR = re.compile(r'\bneither\b', re.I)


def _negated(text: str, start: int) -> bool:
    clauses = re.split(CLAUSE_BREAK, text[:start], flags=re.I)
    clause = clauses[-1] if clauses else ''
    if SCOPE_NEGATOR.search(clause):
        return True
    near = clause.rsplit(',', 1)[-1]  # a comma separates "did not improve Y, Z significantly reduced W"
    return bool(NEAR_NEGATOR.search(' '.join(near.split()[-4:])))


def directional(pattern: str, text: str) -> tuple[bool, bool]:
    """(affirmed, negated): whether `pattern` occurs outside any negation, and inside one.
    A negated positive phrase ("neither drug significantly reduced liver fat") is a null result."""
    affirmed = negated = False
    for match in re.finditer(pattern, text or '', re.I):
        if _negated(text, match.start()):
            negated = True
        else:
            affirmed = True
    return affirmed, negated


# Population, setting and regimen qualifiers. Two records that differ on any of these answer different
# clinical questions, so opposite outcomes between them are related evidence, not a contradiction.
QUALIFIERS = {
    'treatment-naive': r'treatment[- ]na[iï]ve|antiretroviral[- ]na[iï]ve|therapy[- ]na[iï]ve|previously untreated',
    'treatment-experienced': r'treatment[- ]experienced|previously treated|pre-?treated|refractory|salvage',
    'suppressed': r'(?:virolog\w*|viral(?:ly)?) suppress\w*|\bsuppressed\b|undetectable (?:viral|plasma)',
    'csf/cns': r'\bcsf\b|cerebrospinal|central nervous system|\bcns\b|neurocognitive',
    'paediatric': r'p(?:a)?ediatric|\bchildren\b|\binfants?\b|\badolescents?\b|neonat\w*',
    'prevention': r'prophyla\w*|pre-exposure|\bprep\b|\bprevention\b',
    'intensification/switch': r'\bintensification\b|\badd-on\b|\bswitch(?:ing|ed)? (?:to|from)\b',
    'liver/metabolic': r'liver fat|steatosis|\bnafld\b|\bnash\b|\bmasld\b|\bmash\b|hepatic fat|fatty liver',
    'healthy volunteers': r'healthy (?:volunteers|subjects|participants|adults)',
    'transplant/gvhd': r'transplant\w*|graft[- ]versus[- ]host|\bgvhd\b',
    'monotherapy': r'\bmonotherapy\b',
    'first-line': r'first[- ]line',
    'maintenance': r'\bmaintenance\b',
    'adjuvant': r'\b(?:neo)?adjuvant\b',
}


# Population subsets conflict only when both texts name a population and they differ; a general claim is
# still contradicted by a subgroup result. Question-defining settings conflict whenever only one side has them.
POPULATION = {'treatment-naive', 'treatment-experienced', 'suppressed', 'paediatric', 'monotherapy', 'first-line',
              'maintenance', 'adjuvant'}


def context_qualifiers(text: str) -> set[str]:
    return {key for key, pattern in QUALIFIERS.items() if re.search(pattern, text or '', re.I)}


def context_mismatch(claim_text: str, record_text: str) -> set[str]:
    claim, record = context_qualifiers(claim_text), context_qualifiers(record_text)
    claim_pop, record_pop = claim & POPULATION, record & POPULATION
    mismatch = (claim - POPULATION) ^ (record - POPULATION)
    if claim_pop and record_pop and claim_pop.isdisjoint(record_pop):
        mismatch |= claim_pop | record_pop
    return mismatch


GENERIC = set('''patient patients study studies trial trials treatment treated therapy clinical efficacy safety
significant significantly randomized randomised compared comparison versus result results group groups placebo week
weeks month months year years conclusion conclusions data effect effects improve improved improves improvement reduce
reduced reduces reduction increase increased showed shown demonstrated demonstrate associated among after with were this
that these those from have than which there their other more less both during between into also however although whereas
while neither may could should would well model findings evidence analysis outcome outcomes primary secondary endpoint
endpoints phase double blind controlled dose doses daily total overall respectively including included compared
participants subjects baseline levels level change changes response responses observed reported report trend combination'''.split())


def _terms(text: str, exclude: set[str]) -> set[str]:
    words = {w.rstrip('s') for w in re.findall(r'[a-z][a-z0-9-]{3,}', (text or '').lower())}
    return {w for w in words if w not in GENERIC and w not in exclude}


def comparable(claim_text: str, record_text: str, compound_names: list[str], exclude: set[str]) -> tuple[bool, str]:
    """Whether a record answers the same clinical question as a claim: same compound when the claim names
    one, at least one shared endpoint/setting term, and no population/setting/regimen mismatch."""
    from .relevance import mentions
    named = [n for n in compound_names if n and mentions(claim_text, n)]
    if named and not any(mentions(record_text, n) for n in named):
        return False, 'different compound'
    differing = context_mismatch(claim_text, record_text)
    if differing:
        return False, 'different population/setting: ' + ', '.join(sorted(differing))
    claim_terms = _terms(claim_text, exclude)
    if not claim_terms:
        return True, 'general claim without a specific endpoint'
    shared = claim_terms & _terms(record_text, exclude)
    if not shared:
        return False, 'no shared endpoint or setting'
    return True, 'shared ' + ', '.join(sorted(shared)[:4])
