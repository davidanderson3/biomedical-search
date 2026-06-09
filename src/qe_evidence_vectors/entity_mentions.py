from __future__ import annotations

import re
from dataclasses import dataclass

from qe_evidence_vectors.text import normalized_key


TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
PAREN_ABBREVIATION_RE = re.compile(r"\(([A-Za-z][A-Za-z0-9-]{1,12})\)")
SECTION_RE = re.compile(
    r"(?:^|[\n\r]|(?<=\. )|(?<=\? )|(?<=! ))"
    r"(INTRODUCTION|BACKGROUND|OBJECTIVE|OBJECTIVES|AIMS|METHODS|PATIENTS AND METHODS|"
    r"MATERIALS AND METHODS|RESULTS|FINDINGS|CONCLUSION|CONCLUSIONS|INTERPRETATION|"
    r"ASSESSMENT|PLAN|HISTORY|EXAM|MEDICATIONS|ALLERGIES|IMPRESSION)\s*:",
    re.IGNORECASE,
)
SENTENCE_END_RE = re.compile(r"[.!?](?:\s+|$)")


@dataclass(frozen=True)
class TokenSpan:
    text: str
    norm: str
    start: int
    end: int


def token_spans(text: str) -> list[TokenSpan]:
    tokens: list[TokenSpan] = []
    for match in TOKEN_RE.finditer(str(text or "")):
        raw = match.group(0)
        norm = normalized_key(raw)
        if not norm:
            continue
        parts = norm.split()
        if len(parts) != 1:
            continue
        tokens.append(TokenSpan(text=raw, norm=norm, start=match.start(), end=match.end()))
    return tokens


def detect_parenthetical_abbreviations(text: str) -> dict[str, str]:
    """Return abbreviation norm -> likely long-form phrase from local parenthetical definitions."""
    text = str(text or "")
    expansions: dict[str, str] = {}
    for match in PAREN_ABBREVIATION_RE.finditer(text):
        abbreviation = match.group(1).strip()
        abbreviation_norm = normalized_key(abbreviation)
        if not abbreviation_norm or len(abbreviation_norm) < 2:
            continue
        prefix = text[: match.start()]
        long_form = long_form_before_abbreviation(prefix, abbreviation)
        if long_form:
            expansions[abbreviation_norm] = long_form
    return expansions


def long_form_before_abbreviation(prefix: str, abbreviation: str) -> str:
    tokens = token_spans(prefix)
    if not tokens:
        return ""
    letters = [char.lower() for char in abbreviation if char.isalnum()]
    if not letters:
        return ""
    window = tokens[-min(len(tokens), max(len(letters) + 5, 8)) :]
    letter_index = len(letters) - 1
    start_index = len(window)
    for index in range(len(window) - 1, -1, -1):
        token = window[index].norm
        if not token:
            continue
        if token[0] == letters[letter_index]:
            start_index = index
            letter_index -= 1
            if letter_index < 0:
                break
    if letter_index >= 0 or start_index >= len(window):
        return ""
    start = window[start_index].start
    end = window[-1].end
    candidate = prefix[start:end].strip(" \t\r\n,;:-")
    if len(normalized_key(candidate).split()) < 2:
        return ""
    return candidate


def sentence_index_for_offset(text: str, offset: int) -> int:
    offset = max(0, int(offset or 0))
    return sum(1 for match in SENTENCE_END_RE.finditer(str(text or "")[:offset]) if match.end() <= offset)


def section_for_offset(text: str, offset: int) -> str:
    offset = max(0, int(offset or 0))
    section = ""
    for match in SECTION_RE.finditer(str(text or "")[:offset]):
        section = normalized_key(match.group(1)).replace(" ", "_")
    return section


def context_window(text: str, start: int, end: int, *, chars: int = 140) -> str:
    text = str(text or "")
    start = max(0, int(start or 0))
    end = max(start, int(end or start))
    left = max(0, start - chars)
    right = min(len(text), end + chars)
    while left > 0 and text[left - 1] not in ".!?\n\r":
        left -= 1
    while right < len(text) and text[right - 1] not in ".!?\n\r":
        right += 1
    return re.sub(r"\s+", " ", text[left:right]).strip()
