"""Conservative lexical applicability checks, not biological entailment."""
import re

ALIASES = {
    "alzheimer's disease": ['alzheimer'],
    "parkinson's disease": ['parkinson'],
    'hypercholesterolemia': ['hypercholesterolemia', 'hypercholesterolaemia', 'hypercholesterolemic', 'hypercholesterolaemic'],
    'non-small-cell lung cancer': ['non-small cell lung', 'non small cell lung', 'non-small-cell lung', 'nsclc'],
}

def mentions(text: str, term: str) -> bool:
    return bool(re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', text, re.I))

def disease_matches(text: str, disease: str) -> bool:
    aliases = ALIASES.get(disease.casefold(), [disease])
    return any(mentions(text, term) for term in aliases)
