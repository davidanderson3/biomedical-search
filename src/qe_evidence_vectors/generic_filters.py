from __future__ import annotations

from .text import normalized_key


# Narrow, audited suppression list for UMLS labels that behave like ordinary
# prose/research phrasing rather than useful biomedical retrieval anchors.
BLOCKED_GENERIC_LABELS = {
    "chart [medical device]",
    "control aspects",
    "control veterinary product",
    "extremely limited",
    "greater than",
    "intimate",
    "mediation analysis",
    "needs",
    "restart",
    "study results",
    "source",
    "too little",
    "tests",
    "tests and testing",
    "true control status",
}

BLOCKED_GENERIC_CUIS = {
    "C0007963",  # chart [medical device]
    "C0027552",  # Needs
    "C0243148",  # control aspects
    "C0308718",  # CONTROL veterinary product
    "C0439093",  # Greater Than
    "C0449416",  # Source
    "C0699756",  # Intimate (qualifier value)
    "C0683954",  # Study Results
    "C0683443",  # tests and testing
    "C0814912",  # Mediation Analysis
    "C1514902",  # Restart (start again)
    "C3274648",  # True Control Status
    "C0022885",  # Tests
    "C3843661",  # Too little
    "C4489374",  # Extremely Limited
}


def is_blocked_generic_label(label: str) -> bool:
    return normalized_key(label) in BLOCKED_GENERIC_LABELS


def is_blocked_generic_cui(cui: str) -> bool:
    return cui in BLOCKED_GENERIC_CUIS


def is_blocked_generic_concept(cui: str, label: str) -> bool:
    return is_blocked_generic_cui(cui) or is_blocked_generic_label(label)
