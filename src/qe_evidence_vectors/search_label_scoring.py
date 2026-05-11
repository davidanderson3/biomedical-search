from __future__ import annotations

import re

from qe_evidence_vectors.search_hit_features import (
    is_contiguous_subsequence,
    is_ordered_subsequence,
    semantic_type_names,
    specific_query_token_set,
)
from qe_evidence_vectors.search_ranking_constants import (
    BROAD_PRIMARY_LABEL_TEXTS,
    GENERIC_LABEL_TEXTS,
    LOW_SPECIFICITY_QUERY_TOKENS,
)
from qe_evidence_vectors.search_role_tokens import (
    DRUG_ROLE_QUERY_TOKENS,
    PHARMACOLOGIC_SEMANTIC_TYPES,
    THERAPEUTIC_ACTION_QUERY_TOKENS,
)
from qe_evidence_vectors.search_tokens import content_tokens
from qe_evidence_vectors.text import normalized_key


def label_relevance(query_tokens: list[str], label: str) -> float:
    label_tokens = content_tokens(label)
    if not query_tokens or not label_tokens:
        return 0.0
    query_set = set(query_tokens)
    label_unique = []
    seen = set()
    for token in label_tokens:
        if token not in seen:
            seen.add(token)
            label_unique.append(token)
    matched = [token for token in label_unique if token in query_set]
    if not matched:
        return 0.0
    specific_tokens = specific_query_token_set(query_tokens)
    if specific_tokens and not any(token in specific_tokens for token in matched):
        return 0.0
    coverage = len(matched) / len(label_unique)
    if coverage >= 1.0:
        score = 0.60 + (0.10 * min(len(label_unique), 5))
        if is_ordered_subsequence(label_unique, query_tokens):
            score += 0.08
        if is_contiguous_subsequence(label_unique, query_tokens):
            score += 0.05
        return score
    return 0.25 + (0.35 * coverage) + (0.03 * min(len(matched), 4))


def exact_label_match(query_norm: str, labels: list[str]) -> bool:
    if not query_norm:
        return False
    for label in labels:
        if normalized_key(label) == query_norm and not is_generic_label([label]):
            return True
    return False


def exact_primary_name_match(query_norm: str, hit: dict, labels: list[str]) -> bool:
    if not query_norm:
        return False
    primary = str(hit.get("name") or (labels[0] if labels else "")).strip()
    return bool(primary) and normalized_key(primary) == query_norm and not is_generic_label([primary])


def is_generic_label(labels: list[str]) -> bool:
    for label in labels:
        tokens = set(content_tokens(label))
        norm = " ".join(content_tokens(label)) or normalized_key(label)
        if norm in GENERIC_LABEL_TEXTS:
            return True
        if tokens and tokens <= LOW_SPECIFICITY_QUERY_TOKENS:
            return True
    return False


def is_broad_primary_label(hit: dict) -> bool:
    primary = str(hit.get("name") or "").strip()
    if not primary:
        labels = list(hit.get("labels") or [])
        primary = str(labels[0] if labels else "")
    norm = " ".join(content_tokens(primary)) or normalized_key(primary)
    return norm in BROAD_PRIMARY_LABEL_TEXTS


def is_disambiguated_homonym_label(label: str) -> bool:
    return bool(re.search(r"<[^<>]+>\s*$", label or ""))


def should_suppress_label_fallback_hit(hit: dict) -> bool:
    if int(hit.get("evidence_count") or 0) > 0:
        return False
    labels = [str(hit.get("name") or ""), *[str(label) for label in hit.get("labels") or []]]
    return any(is_disambiguated_homonym_label(label) for label in labels)


def semantic_query_boost(query_tokens: set[str], label_tokens: set[str], hit: dict) -> float:
    if int(hit.get("evidence_count") or 0) <= 0:
        return 0.0
    semantic_types = semantic_type_names(hit)
    if "infection" in query_tokens and "infection" in label_tokens and (
        "disease or syndrome" in semantic_types or "pathologic function" in semantic_types
    ):
        if content_tokens(str(hit.get("name") or "")) == ["infection"]:
            return 0.28
        return 0.16
    if {"sepsis", "septic"} & query_tokens and {"sepsis", "septicemia"} & label_tokens and (
        "disease or syndrome" in semantic_types or "pathologic function" in semantic_types
    ):
        return 0.16
    if "antibiotic" in query_tokens and (
        "antibiotic" in label_tokens or "antibiotic" in semantic_types
    ):
        return 0.12
    if query_tokens & DRUG_ROLE_QUERY_TOKENS and semantic_types & PHARMACOLOGIC_SEMANTIC_TYPES:
        component = 0.22
        if query_tokens & THERAPEUTIC_ACTION_QUERY_TOKENS:
            component += 0.06
        if {"blood", "clot"} <= query_tokens and label_tokens & {
            "anticoagulant",
            "antithrombotic",
            "fibrinolytic",
        }:
            component += 0.04
        return min(component, 0.30)
    if "pain" in query_tokens and "pain" in label_tokens and "sign or symptom" in semantic_types:
        return 0.08
    return 0.0
