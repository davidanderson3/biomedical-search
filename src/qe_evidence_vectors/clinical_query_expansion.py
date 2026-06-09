from __future__ import annotations

import re

from .text import normalized_key


TYPO_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bfevr\b", re.IGNORECASE), "fever"),
    (re.compile(r"\bnitrtes\b", re.IGNORECASE), "nitrites"),
    (re.compile(r"\bpyelonephrits\b", re.IGNORECASE), "pyelonephritis"),
    (re.compile(r"\bwarfrin\b", re.IGNORECASE), "warfarin"),
    (re.compile(r"\bepistaxsis\b", re.IGNORECASE), "epistaxis"),
)

SAFE_ABBREVIATION_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bw/\s*", re.IGNORECASE), "with "),
    (re.compile(r"\bafib\b", re.IGNORECASE), "atrial fibrillation"),
    (re.compile(r"\bsob\b", re.IGNORECASE), "shortness of breath"),
    (re.compile(r"\bcta\b", re.IGNORECASE), "computed tomography angiography"),
    (re.compile(r"\bdvt\b", re.IGNORECASE), "deep vein thrombosis"),
    (re.compile(r"\brle\b", re.IGNORECASE), "right lower extremity"),
    (re.compile(r"\be[ .-]?coli\b", re.IGNORECASE), "Escherichia coli"),
)


def clinical_query_variants(query: str) -> list[str]:
    original = str(query or "")
    expanded = clinical_query_expansion(original)
    variants: list[str] = []
    seen: set[str] = set()
    for value in (original, expanded):
        key = normalized_key(value)
        if not key or key in seen:
            continue
        seen.add(key)
        variants.append(value)
    return variants


def clinical_query_expansion(query: str) -> str:
    expanded = str(query or "")
    for pattern, replacement in TYPO_REPLACEMENTS:
        expanded = pattern.sub(replacement, expanded)
    for pattern, replacement in SAFE_ABBREVIATION_REPLACEMENTS:
        expanded = pattern.sub(replacement, expanded)
    normalized = f" {normalized_key(expanded)} "
    expanded = _contextual_expansion(expanded, normalized)
    return re.sub(r"\s+", " ", expanded).strip()


def _contextual_expansion(text: str, normalized: str) -> str:
    expanded = text
    if _has_any(
        normalized,
        {
            "pleuritic cp",
            "sob",
            "long flight",
            "pulmonary embolism",
            "computed tomography angiography",
        },
    ):
        expanded = re.sub(r"\bcp\b", "chest pain", expanded, flags=re.IGNORECASE)
    if _has_any(
        normalized,
        {
            "computed tomography angiography",
            "pleuritic",
            "long flight",
            "deep vein thrombosis",
            "venous duplex",
            "segmental pe",
        },
    ):
        expanded = re.sub(r"\bpe\b", "pulmonary embolism", expanded, flags=re.IGNORECASE)
    if _has_any(normalized, {"dysuria", "pyuria", "nitrites", "urine", "flank pain"}):
        expanded = re.sub(r"\bua\b", "urinalysis", expanded, flags=re.IGNORECASE)
        expanded = re.sub(r"\bcx\b", "culture", expanded, flags=re.IGNORECASE)
    if _has_any(
        normalized,
        {
            "neurology",
            "optic neuritis",
            "demyelinating",
            "paresthesia",
            "paresthesias",
            "methylprednisolone",
        },
    ):
        expanded = re.sub(r"\bms\b", "multiple sclerosis", expanded, flags=re.IGNORECASE)
    if _has_any(
        normalized,
        {
            "rheumatology",
            "mcp",
            "morning stiffness",
            "methotrexate",
            "anti ccp",
            "positive rf",
            "rheumatoid factor",
        },
    ):
        expanded = re.sub(r"\bra\b", "rheumatoid arthritis", expanded, flags=re.IGNORECASE)
        expanded = re.sub(r"\brf\b", "rheumatoid factor", expanded, flags=re.IGNORECASE)
        expanded = re.sub(
            r"\banti[- ]?ccp\b",
            "anti cyclic citrullinated peptide",
            expanded,
            flags=re.IGNORECASE,
        )
        expanded = re.sub(r"\bccp\b", "cyclic citrullinated peptide", expanded, flags=re.IGNORECASE)
    return expanded


def _has_any(normalized: str, phrases: set[str]) -> bool:
    return any(f" {normalized_key(phrase)} " in normalized for phrase in phrases)
