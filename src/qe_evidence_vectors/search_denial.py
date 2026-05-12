from __future__ import annotations

from qe_evidence_vectors.search_hit_features import semantic_type_names
from qe_evidence_vectors.search_ranking_constants import (
    DENIAL_SCOPE_BREAK_AFTER_WITHOUT_AND,
    DENIAL_SCOPE_BREAK_BIGRAMS,
    DENIED_CONTEXT_MISMATCH_PENALTY,
    DENIED_POSITIVE_FINDING_STRONG_PENALTY,
    DENIED_POSITIVE_FINDING_WEAK_PENALTY,
    LOW_SPECIFICITY_QUERY_TOKENS,
    NEGATED_LABEL_PREFIXES,
    NEGATED_LABEL_TOKENS,
    NEGATION_QUERY_TOKENS,
)
from qe_evidence_vectors.search_tokens import canonical_token, content_tokens
from qe_evidence_vectors.text import normalized_key


def has_denial_context(raw_query_tokens: set[str]) -> bool:
    return any(canonical_token(token) in NEGATION_QUERY_TOKENS for token in raw_query_tokens)


def label_is_negated(label: str) -> bool:
    if label_is_low_quality_negated_fragment(label):
        return False
    norm = normalized_key(label)
    if norm.startswith(NEGATED_LABEL_PREFIXES):
        return True
    return bool(set(norm.split()) & NEGATED_LABEL_TOKENS)


def label_is_low_quality_negated_fragment(label: str) -> bool:
    if ";" not in (label or ""):
        return False
    tokens = {
        token
        for token in content_tokens(label)
        if token not in LOW_SPECIFICITY_QUERY_TOKENS and token not in NEGATED_LABEL_TOKENS
    }
    return len(tokens) <= 1 and bool(set(normalized_key(label).split()) & NEGATED_LABEL_TOKENS)


def denied_positive_finding_penalty_for_hit(
    *,
    raw_query_tokens: set[str],
    raw_query_token_list: list[str],
    query_tokens: list[str],
    label_tokens: set[str],
    labels: list[str],
    hit: dict,
) -> float:
    if not has_denial_context(raw_query_tokens):
        return 0.0
    if not label_tokens or any(label_is_negated(label) for label in labels):
        return 0.0
    deniable_types = {
        "clinical attribute",
        "disease or syndrome",
        "finding",
        "injury or poisoning",
        "mental or behavioral dysfunction",
        "pathologic function",
        "sign or symptom",
    }
    hit_types = semantic_type_names(hit)
    if hit_types and not (hit_types & deniable_types):
        return 0.0
    denied_tokens = denied_scope_specific_token_set(raw_query_token_list)
    matched = denied_tokens & label_tokens
    if not matched:
        return 0.0
    for label in labels:
        if label_is_negated(label):
            continue
        label_specific_tokens = {
            token
            for token in content_tokens(label)
            if token not in LOW_SPECIFICITY_QUERY_TOKENS and token not in NEGATION_QUERY_TOKENS
        }
        if label_specific_tokens and label_specific_tokens <= denied_tokens:
            return DENIED_POSITIVE_FINDING_STRONG_PENALTY
        if len(label_specific_tokens & denied_tokens) >= 2:
            return DENIED_POSITIVE_FINDING_STRONG_PENALTY
    label_specific_tokens = {
        token
        for token in label_tokens
        if token not in LOW_SPECIFICITY_QUERY_TOKENS and token not in NEGATION_QUERY_TOKENS
    }
    if label_specific_tokens and label_specific_tokens <= denied_tokens:
        return DENIED_POSITIVE_FINDING_STRONG_PENALTY
    return DENIED_POSITIVE_FINDING_WEAK_PENALTY


def denied_context_mismatch_penalty_for_hit(
    *,
    raw_query_tokens: set[str],
    raw_query_token_list: list[str],
    label_tokens: set[str],
    labels: list[str],
    hit: dict,
) -> float:
    if not has_denial_context(raw_query_tokens):
        return 0.0
    if not label_tokens or any(label_is_negated(label) for label in labels):
        return 0.0
    denied_tokens = denied_scope_specific_token_set(raw_query_token_list)
    if not (denied_tokens & label_tokens):
        return 0.0
    deniable_types = {
        "clinical attribute",
        "disease or syndrome",
        "finding",
        "injury or poisoning",
        "mental or behavioral dysfunction",
        "pathologic function",
        "sign or symptom",
    }
    if semantic_type_names(hit) & deniable_types:
        return 0.0
    return DENIED_CONTEXT_MISMATCH_PENALTY


def denied_scope_specific_token_set(raw_query_tokens: list[str]) -> set[str]:
    scoped_tokens = []
    for scope in denial_scope_token_lists(raw_query_tokens):
        scoped_tokens.extend(scope)
    return {
        token
        for token in content_tokens(" ".join(scoped_tokens))
        if token not in LOW_SPECIFICITY_QUERY_TOKENS and token not in NEGATION_QUERY_TOKENS
    }


def denial_scope_token_lists(raw_query_tokens: list[str]) -> list[list[str]]:
    scopes = []
    for index, token in enumerate(raw_query_tokens):
        canonical = canonical_token(token)
        if canonical not in NEGATION_QUERY_TOKENS:
            continue
        if (
            canonical == "without"
            and index >= 2
            and canonical_token(raw_query_tokens[index - 2]) == "with"
            and canonical_token(raw_query_tokens[index - 1]) == "or"
        ):
            continue
        start = index + 1
        if canonical == "no" and raw_query_tokens[index + 1 : index + 3] == ["evidence", "of"]:
            start = index + 3
        max_scope_tokens = None if canonical in {"deny", "denied", "denies", "without"} else 8
        scope = []
        for offset, scope_token in enumerate(raw_query_tokens[start:], start=start):
            scope_canonical = canonical_token(scope_token)
            if scope_canonical in {"but", "however", "though", "although", "except", "unless", "while"}:
                break
            next_canonical = (
                canonical_token(raw_query_tokens[offset + 1])
                if offset + 1 < len(raw_query_tokens)
                else ""
            )
            if (
                canonical == "without"
                and scope_canonical == "and"
                and next_canonical in DENIAL_SCOPE_BREAK_AFTER_WITHOUT_AND
            ):
                break
            if (scope_canonical, next_canonical) in DENIAL_SCOPE_BREAK_BIGRAMS:
                break
            scope.append(scope_token)
            if max_scope_tokens is not None and len(scope) >= max_scope_tokens:
                break
        if scope:
            scopes.append(scope)
    return scopes
