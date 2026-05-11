from __future__ import annotations

from .text import normalized_key


# Narrow, audited suppression list for UMLS labels that behave like ordinary
# prose/research phrasing rather than useful biomedical retrieval anchors.
BLOCKED_GENERIC_LABELS = {
    "extremely limited",
    "mediation analysis",
    "study results",
    "too little",
}

BLOCKED_GENERIC_CUIS = {
    "C0683954",  # Study Results
    "C0814912",  # Mediation Analysis
    "C3843661",  # Too little
    "C4489374",  # Extremely Limited
}


def is_blocked_generic_label(label: str) -> bool:
    return normalized_key(label) in BLOCKED_GENERIC_LABELS


def is_blocked_generic_cui(cui: str) -> bool:
    return cui in BLOCKED_GENERIC_CUIS


def is_blocked_generic_concept(cui: str, label: str) -> bool:
    return is_blocked_generic_cui(cui) or is_blocked_generic_label(label)
