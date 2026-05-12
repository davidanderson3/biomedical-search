from __future__ import annotations

from qe_evidence_vectors.search_hit_features import semantic_type_names
from qe_evidence_vectors.search_tokens import canonical_token, content_tokens
from qe_evidence_vectors.text import normalized_key


ASSERTION_CURRENT = "current"
ASSERTION_NEGATED = "negated"
ASSERTION_UNCERTAIN = "uncertain"
ASSERTION_HISTORICAL = "historical"
ASSERTION_FAMILY_HISTORY = "family_history"
ASSERTION_PLANNED = "planned"
ASSERTION_CONFIRMED = "confirmed"

ASSERTION_PRIORITY = {
    ASSERTION_NEGATED: 0,
    ASSERTION_FAMILY_HISTORY: 1,
    ASSERTION_UNCERTAIN: 2,
    ASSERTION_PLANNED: 3,
    ASSERTION_HISTORICAL: 4,
    ASSERTION_CONFIRMED: 5,
}

BEFORE_CUES = {
    ASSERTION_NEGATED: (
        ("no",),
        ("not",),
        ("denies",),
        ("denied",),
        ("deny",),
        ("without",),
        ("negative", "for"),
        ("no", "evidence", "of"),
    ),
    ASSERTION_UNCERTAIN: (
        ("possible",),
        ("possibly",),
        ("probable",),
        ("suspected",),
        ("suspect",),
        ("concern", "for"),
        ("concerning", "for"),
        ("rule", "out"),
        ("r", "o"),
        ("evaluate", "for"),
        ("evaluation", "for"),
        ("question", "of"),
    ),
    ASSERTION_HISTORICAL: (
        ("history", "of"),
        ("past", "history", "of"),
        ("prior",),
        ("previous",),
        ("remote",),
        ("old",),
    ),
    ASSERTION_FAMILY_HISTORY: (
        ("family", "history", "of"),
        ("maternal", "history", "of"),
        ("paternal", "history", "of"),
        ("mother", "had"),
        ("father", "had"),
        ("sister", "had"),
        ("brother", "had"),
        ("parent", "had"),
    ),
    ASSERTION_PLANNED: (
        ("planned",),
        ("plan", "for"),
        ("ordered",),
        ("pending",),
        ("scheduled",),
        ("deferred",),
        ("recommended",),
        ("to", "be"),
    ),
    ASSERTION_CONFIRMED: (
        ("confirmed",),
        ("demonstrated",),
        ("showed",),
        ("shows",),
        ("found",),
        ("grew",),
        ("diagnosed",),
        ("positive", "for"),
        ("consistent", "with"),
        ("supported",),
    ),
}

AFTER_CUES = {
    ASSERTION_NEGATED: (
        ("ruled", "out"),
        ("excluded",),
        ("negative",),
        ("absent",),
    ),
    ASSERTION_UNCERTAIN: (
        ("suspected",),
        ("possible",),
        ("considered",),
        ("not", "excluded"),
    ),
    ASSERTION_HISTORICAL: (
        ("history",),
        ("historical",),
        ("remote",),
    ),
    ASSERTION_PLANNED: (
        ("planned",),
        ("ordered",),
        ("pending",),
        ("scheduled",),
        ("deferred",),
    ),
    ASSERTION_CONFIRMED: (
        ("confirmed",),
        ("demonstrated",),
        ("shown",),
        ("diagnosed",),
        ("found",),
    ),
}

NON_ACTIVE_ASSERTION_TYPES = {
    "acquired abnormality",
    "clinical attribute",
    "congenital abnormality",
    "disease or syndrome",
    "finding",
    "injury or poisoning",
    "mental or behavioral dysfunction",
    "neoplastic process",
    "pathologic function",
    "sign or symptom",
}

PROCEDURE_ASSERTION_TYPES = {
    "diagnostic procedure",
    "health care activity",
    "laboratory procedure",
    "therapeutic or preventive procedure",
}


def assertion_context_for_hit(*, query: str, labels: list[str], hit: dict) -> dict:
    query_tokens = normalized_key(query).split()
    if not query_tokens:
        return {"status": ASSERTION_CURRENT}
    canonical_query = [canonical_token(token) for token in query_tokens]
    spans = mention_spans_for_hit(canonical_query=canonical_query, labels=labels, hit=hit)
    if not spans:
        return {"status": ASSERTION_CURRENT}
    family_history_span = family_history_span_text(labels=labels, spans=spans)
    if family_history_span:
        return {
            "status": ASSERTION_FAMILY_HISTORY,
            "cue": "family history",
            "distance": 0,
            "direction": "label",
            "matched_span": family_history_span,
            "attributes": [ASSERTION_FAMILY_HISTORY],
        }

    candidates = []
    for start, end, span_text in spans:
        candidates.extend(cue_candidates(canonical_query, start=start, end=end, span_text=span_text))
    if not candidates:
        return {"status": ASSERTION_CURRENT}

    candidates.sort(
        key=lambda item: (
            item["distance"],
            ASSERTION_PRIORITY.get(item["status"], 99),
            item["direction"],
            item["cue"],
        )
    )
    best = dict(candidates[0])
    status = str(best["status"])
    attributes = [status]
    if status != ASSERTION_CURRENT:
        best["attributes"] = attributes
    return best


def assertion_context_penalty_for_hit(*, assertion: dict, hit: dict) -> float:
    status = str(assertion.get("status") or ASSERTION_CURRENT)
    if status in {ASSERTION_CURRENT, ASSERTION_CONFIRMED, ASSERTION_NEGATED, ASSERTION_FAMILY_HISTORY}:
        return 0.0
    hit_types = semantic_type_names(hit)
    if status == ASSERTION_HISTORICAL and hit_types & NON_ACTIVE_ASSERTION_TYPES:
        return 0.22
    if status == ASSERTION_UNCERTAIN and hit_types & NON_ACTIVE_ASSERTION_TYPES:
        return 0.18
    if status == ASSERTION_PLANNED:
        if hit_types & PROCEDURE_ASSERTION_TYPES:
            return 0.08
        if hit_types & NON_ACTIVE_ASSERTION_TYPES:
            return 0.14
    return 0.0


def mention_spans_for_hit(*, canonical_query: list[str], labels: list[str], hit: dict) -> list[tuple[int, int, str]]:
    candidates: list[tuple[list[str], str, int]] = []
    matched_span = str(hit.get("matched_query_span") or "").strip()
    if matched_span:
        tokens = [canonical_token(token) for token in normalized_key(matched_span).split()]
        if tokens:
            candidates.append((tokens, matched_span, 1000 + len(tokens)))

    for label in labels:
        label_tokens = content_tokens(label)
        if label_tokens:
            candidates.append((label_tokens, label, len(label_tokens)))

    spans = []
    seen = set()
    for tokens, label, _weight in sorted(candidates, key=lambda item: -item[2]):
        for start in find_subsequence_positions(canonical_query, tokens):
            key = (start, start + len(tokens), " ".join(tokens))
            if key in seen:
                continue
            seen.add(key)
            spans.append((start, start + len(tokens), label))
    return spans


def cue_candidates(
    canonical_query: list[str],
    *,
    start: int,
    end: int,
    span_text: str,
) -> list[dict]:
    candidates = []
    for status, phrases in BEFORE_CUES.items():
        for phrase in phrases:
            for pos in find_subsequence_positions(canonical_query, list(phrase)):
                phrase_end = pos + len(phrase)
                distance = start - phrase_end
                if 0 <= distance <= max_before_distance(status) and not cue_scope_blocked(
                    canonical_query,
                    phrase_end,
                    start,
                    status=status,
                ):
                    candidates.append(candidate(status, phrase, distance, "before", span_text))
    for status, phrases in AFTER_CUES.items():
        for phrase in phrases:
            for pos in find_subsequence_positions(canonical_query, list(phrase)):
                distance = pos - end
                if 0 <= distance <= max_after_distance(status) and not cue_scope_blocked(
                    canonical_query,
                    end,
                    pos,
                    status=status,
                ):
                    candidates.append(candidate(status, phrase, distance, "after", span_text))
    return candidates


def candidate(status: str, phrase: tuple[str, ...], distance: int, direction: str, span_text: str) -> dict:
    return {
        "status": status,
        "cue": " ".join(phrase),
        "distance": distance,
        "direction": direction,
        "matched_span": span_text,
    }


def max_before_distance(status: str) -> int:
    if status == ASSERTION_FAMILY_HISTORY:
        return 8
    if status == ASSERTION_HISTORICAL:
        return 6
    if status == ASSERTION_CONFIRMED:
        return 7
    return 8


def max_after_distance(status: str) -> int:
    if status == ASSERTION_HISTORICAL:
        return 4
    if status == ASSERTION_CONFIRMED:
        return 5
    if status == ASSERTION_PLANNED:
        return 1
    return 6


def family_history_span_text(*, labels: list[str], spans: list[tuple[int, int, str]]) -> str:
    for label in labels:
        label_tokens = set(normalized_key(label).split())
        if {"family", "history"} <= label_tokens:
            return label
    for _start, _end, span_text in spans:
        span_tokens = set(normalized_key(span_text).split())
        if {"family", "history"} <= span_tokens:
            return span_text
    return ""


def cue_scope_blocked(
    canonical_query: list[str],
    start: int,
    end: int,
    *,
    status: str,
) -> bool:
    between = set(canonical_query[start:end])
    if between & {"but", "however", "though", "although", "except", "unless", "while"}:
        return True
    if status in {ASSERTION_HISTORICAL, ASSERTION_FAMILY_HISTORY} and between & {
        "active",
        "acute",
        "current",
        "currently",
        "new",
        "now",
        "today",
    }:
        return True
    if status in {ASSERTION_HISTORICAL, ASSERTION_UNCERTAIN, ASSERTION_PLANNED} and between & {
        "confirmed",
        "demonstrated",
        "diagnosed",
        "found",
        "grew",
    }:
        return True
    return False


def find_subsequence_positions(haystack: list[str], needle: list[str]) -> list[int]:
    if not needle or len(needle) > len(haystack):
        return []
    width = len(needle)
    return [
        index
        for index in range(0, len(haystack) - width + 1)
        if haystack[index : index + width] == needle
    ]
