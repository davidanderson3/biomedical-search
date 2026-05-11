from __future__ import annotations

from qe_evidence_vectors.search_ranking_constants import (
    LOW_SPECIFICITY_QUERY_TOKENS,
    NEGATION_QUERY_TOKENS,
)
from qe_evidence_vectors.search_semantics import semantic_type_name_set
from qe_evidence_vectors.search_tokens import canonical_token, content_tokens


def specific_query_token_set(query_tokens: list[str]) -> set[str]:
    return {
        token
        for token in query_tokens
        if token not in LOW_SPECIFICITY_QUERY_TOKENS and token not in NEGATION_QUERY_TOKENS
    }


def label_tokens_for_hit(hit: dict) -> set[str]:
    labels = list(hit.get("labels") or [])
    if hit.get("name"):
        labels.insert(0, str(hit["name"]))
    label_tokens = set()
    for label in labels:
        label_tokens.update(content_tokens(label))
    return label_tokens


def hit_matched_specific_tokens(hit: dict, *, query_tokens: list[str]) -> set[str]:
    specific_tokens = specific_query_token_set(query_tokens)
    matched = specific_tokens & label_tokens_for_hit(hit)
    for token in hit.get("mrrel_matched_tokens") or []:
        token = canonical_token(str(token))
        if token in specific_tokens:
            matched.add(token)
    return matched


def rare_query_anchor_tokens(tokens: set[str]) -> set[str]:
    return {token for token in tokens if any(char.isdigit() for char in token)}


def numeric_query_anchor_tokens(tokens: set[str]) -> set[str]:
    return {token for token in tokens if token.isdigit()}


def semantic_type_names(hit: dict) -> set[str]:
    return semantic_type_name_set(list(hit.get("semantic_types") or []))


def is_ordered_subsequence(needle: list[str], haystack: list[str]) -> bool:
    pos = 0
    for token in haystack:
        if pos < len(needle) and token == needle[pos]:
            pos += 1
    return pos == len(needle)


def is_contiguous_subsequence(needle: list[str], haystack: list[str]) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    width = len(needle)
    return any(haystack[index : index + width] == needle for index in range(len(haystack) - width + 1))
