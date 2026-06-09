from __future__ import annotations

import re
from dataclasses import dataclass

from qe_evidence_vectors.text import normalized_key


TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
SENTENCE_RE = re.compile(r"[^.!?\n\r]+(?:[.!?]+|$)")
SECTION_HEADING_RE = re.compile(
    r"(?:^|[\n\r]|(?<=\. )|(?<=\? )|(?<=! ))"
    r"(TITLE|ABSTRACT|INTRODUCTION|BACKGROUND|OBJECTIVE|OBJECTIVES|AIMS|"
    r"METHODS|PATIENTS AND METHODS|MATERIALS AND METHODS|WHAT IS KNOWN AND OBJECTIVE|"
    r"WHAT IS NEW AND CONCLUSIONS|RESULTS|RESULTS AND DISCUSSION|FINDINGS|"
    r"OBSERVATIONS|LESSONS|DISCUSSION|CONCLUSION|CONCLUSIONS|INTERPRETATION|"
    r"ASSESSMENT|PLAN|HISTORY|EXAM|MEDICATIONS|ALLERGIES|IMPRESSION)\s*:",
    re.IGNORECASE,
)
LONG_DOCUMENT_MIN_TOKENS = 90
LONG_DOCUMENT_MIN_SENTENCES = 5
CHUNK_TARGET_TOKENS = 70
CHUNK_MAX_TOKENS = 95
MAX_LONG_DOCUMENT_CHUNKS = 12


@dataclass(frozen=True)
class LongDocumentChunk:
    index: int
    section: str
    text: str
    start: int
    end: int
    token_count: int
    weight: float


def token_count(text: str) -> int:
    return sum(1 for _match in TOKEN_RE.finditer(str(text or "")))


def section_key(value: str) -> str:
    return normalized_key(value).replace(" ", "_")


def section_weight(section: str, *, is_lead: bool = False) -> float:
    section = section_key(section)
    if is_lead or section in {"title", "abstract", "objective", "objectives", "aims"}:
        return 1.0
    if section in {
        "results",
        "results_and_discussion",
        "findings",
        "observations",
        "lessons",
        "conclusion",
        "conclusions",
        "interpretation",
        "discussion",
        "what_is_new_and_conclusions",
    }:
        return 0.95
    if section in {"background", "introduction"}:
        return 0.88
    if section in {"methods", "patients_and_methods", "materials_and_methods"}:
        return 0.72
    return 0.82


def sentence_spans(text: str, *, base: int = 0) -> list[tuple[int, int, str]]:
    spans = []
    for match in SENTENCE_RE.finditer(str(text or "")):
        sentence = re.sub(r"\s+", " ", match.group(0)).strip()
        if not sentence:
            continue
        start = base + match.start()
        end = base + match.end()
        spans.append((start, end, sentence))
    return spans


def should_plan_long_document_chunks(text: str) -> bool:
    text = str(text or "")
    if token_count(text) >= LONG_DOCUMENT_MIN_TOKENS:
        return True
    if len(list(SECTION_HEADING_RE.finditer(text))) >= 2:
        return True
    return len(sentence_spans(text)) >= LONG_DOCUMENT_MIN_SENTENCES and len(text) >= 520


def section_spans(text: str) -> list[tuple[str, int, int]]:
    matches = list(SECTION_HEADING_RE.finditer(text))
    spans: list[tuple[str, int, int]] = []
    if not matches:
        return [("body", 0, len(text))]
    first = matches[0]
    if first.start() > 0:
        spans.append(("lead", 0, first.start()))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        spans.append((section_key(match.group(1)), start, end))
    return spans


def pack_sentence_chunks(
    sentences: list[tuple[int, int, str]],
    *,
    section: str,
    next_index: int,
    max_chunks: int,
) -> tuple[list[LongDocumentChunk], int]:
    chunks: list[LongDocumentChunk] = []
    current: list[tuple[int, int, str]] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current, current_tokens, next_index
        if not current or len(chunks) >= max_chunks:
            current = []
            current_tokens = 0
            return
        start = current[0][0]
        end = current[-1][1]
        text = re.sub(r"\s+", " ", " ".join(item[2] for item in current)).strip()
        count = token_count(text)
        if count:
            chunks.append(
                LongDocumentChunk(
                    index=next_index,
                    section=section,
                    text=text,
                    start=start,
                    end=end,
                    token_count=count,
                    weight=section_weight(section, is_lead=section == "lead"),
                )
            )
            next_index += 1
        current = []
        current_tokens = 0

    for sentence in sentences:
        sentence_tokens = token_count(sentence[2])
        if not sentence_tokens:
            continue
        if current and current_tokens + sentence_tokens > CHUNK_MAX_TOKENS:
            flush()
        current.append(sentence)
        current_tokens += sentence_tokens
        if current_tokens >= CHUNK_TARGET_TOKENS:
            flush()
        if len(chunks) >= max_chunks:
            break
    flush()
    return chunks, next_index


def plan_long_document_chunks(text: str, *, max_chunks: int = MAX_LONG_DOCUMENT_CHUNKS) -> list[LongDocumentChunk]:
    text = str(text or "")
    if not should_plan_long_document_chunks(text):
        return []
    chunks: list[LongDocumentChunk] = []
    next_index = 1
    for section, start, end in section_spans(text):
        if len(chunks) >= max_chunks:
            break
        section_text = text[start:end]
        sentences = sentence_spans(section_text, base=start)
        if not sentences and token_count(section_text):
            sentences = [(start, end, re.sub(r"\s+", " ", section_text).strip())]
        new_chunks, next_index = pack_sentence_chunks(
            sentences,
            section=section,
            next_index=next_index,
            max_chunks=max_chunks - len(chunks),
        )
        chunks.extend(new_chunks)
    return chunks[:max_chunks]
