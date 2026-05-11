from __future__ import annotations

from qe_evidence_vectors.text import normalized_key


RANK_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "being",
    "by",
    "from",
    "is",
    "or",
    "of",
    "the",
    "to",
    "in",
    "on",
    "for",
    "with",
    "within",
    "without",
    "over",
    "past",
    "current",
    "recent",
    "further",
    "no",
    "evidence",
    "note",
    "noted",
    "patient",
    "patients",
    "report",
    "reports",
    "reported",
    "perform",
    "performed",
    "reveals",
    "use",
    "used",
    "uses",
    "using",
    "was",
    "were",
    "includes",
    "include",
    "requiring",
    "suggest",
    "suggests",
    "advised",
    "maintain",
}
TOKEN_ALIASES = {
    "abdominal": "abdomen",
    "abdomen": "abdomen",
    "antibiotics": "antibiotic",
    "exertional": "exertion",
    "exertion": "exertion",
    "denied": "deny",
    "denies": "deny",
    "hyperlactatemia": "lactate",
    "infectious": "infection",
    "lactic": "lactate",
    "hypotensive": "hypotension",
    "loc": "consciousness",
    "medications": "medication",
    "norepi": "norepinephrine",
    "probable": "likely",
    "prescriptions": "prescription",
    "septic": "sepsis",
    "tender": "pain",
    "tenderness": "pain",
    "unconscious": "consciousness",
    "unconsciousness": "consciousness",
    "vasoactive": "vasopressor",
    "prevents": "prevent",
    "preventing": "prevent",
    "treated": "treat",
    "treating": "treat",
}

SINGULAR_S_TOKENS = {
    "arthritis",
    "cirrhosis",
    "diabetes",
    "diagnosis",
    "fibrosis",
    "psoriasis",
    "sepsis",
    "sclerosis",
    "stenosis",
    "thrombosis",
}

def content_tokens(text: str) -> list[str]:
    tokens = []
    for token in normalized_key(text).split():
        canonical = canonical_token(token)
        if not canonical or canonical in RANK_STOPWORDS:
            continue
        tokens.append(canonical)
    return tokens


def canonical_token(token: str) -> str:
    token = TOKEN_ALIASES.get(token, token)
    if token.endswith("ies") and len(token) > 4:
        token = f"{token[:-3]}y"
    elif token.endswith("s") and len(token) > 4 and not token.endswith("ss") and token not in SINGULAR_S_TOKENS:
        token = token[:-1]
    return TOKEN_ALIASES.get(token, token)
