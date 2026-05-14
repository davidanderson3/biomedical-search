from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable, Iterator

from .label_index import LabelIndex
from .schema import CorpusDocument, EvidenceRecord
from .text import clean_text, normalized_key


TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
LEADING_LABEL_EDGE_STOPWORDS = {
    "a",
    "an",
    "and",
    "by",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "without",
}
TRAILING_LABEL_EDGE_STOPWORDS = {
    "an",
    "and",
    "by",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "without",
}


@dataclass(frozen=True)
class TokenSpan:
    token: str
    start: int
    end: int


def _evidence_id(document: CorpusDocument, cui: str, start: int, end: int) -> str:
    payload = "\t".join([document.doc_id, cui, str(start), str(end)])
    return "EVID_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:20]


def token_spans(text: str) -> list[TokenSpan]:
    return [TokenSpan(match.group(0), match.start(), match.end()) for match in TOKEN_RE.finditer(text)]


def is_acceptable_label_match(text: str, start: int, end: int, norm: str) -> bool:
    tokens = norm.split()
    if not tokens:
        return False
    if tokens[0] in LEADING_LABEL_EDGE_STOPWORDS:
        return False
    if tokens[-1] in TRAILING_LABEL_EDGE_STOPWORDS:
        return False
    if start > 0 and text[start - 1] == "-":
        return False
    if end < len(text) and text[end] == "-":
        return False
    return True


def context_window(text: str, start: int, end: int, *, chars: int) -> str:
    left = max(0, start - chars)
    right = min(len(text), end + chars)
    if left:
        space = text.find(" ", left)
        if 0 <= space < start:
            left = space + 1
    if right < len(text):
        space = text.rfind(" ", end, right)
        if space > end:
            right = space
    return clean_text(text[left:right])


def _label_weight(row) -> float:
    weight = 1.0
    if row["ispref"] == "Y":
        weight += 0.25
    if row["tty"] in {"PT", "MH", "PN", "FN"}:
        weight += 0.25
    return weight


def _selected_cui_for_rows(rows, *, max_ambiguity: int) -> str:
    best_by_cui = {}
    for row in rows:
        cui = row["cui"]
        current = best_by_cui.get(cui)
        if current is None or (-_label_weight(row), row["label"]) < (
            -_label_weight(current),
            current["label"],
        ):
            best_by_cui[cui] = row
    cuis = sorted(best_by_cui)
    if len(cuis) <= max_ambiguity:
        return cuis[0] if cuis else ""
    if max_ambiguity != 1:
        return ""
    best_rows = sorted(best_by_cui.values(), key=lambda row: (-_label_weight(row), row["label"]))
    if len(best_rows) < 2:
        return best_rows[0]["cui"] if best_rows else ""
    best_weight = _label_weight(best_rows[0])
    next_weight = _label_weight(best_rows[1])
    return best_rows[0]["cui"] if best_weight > next_weight else ""


def evidence_type_for_source(source: str, evidence_tag: str = "") -> str:
    if evidence_tag:
        return f"{source}_{evidence_tag}_context"
    return f"{source}_context"


def link_document_to_evidence(
    document: CorpusDocument,
    index: LabelIndex,
    *,
    max_label_tokens: int = 8,
    context_chars: int = 320,
    max_ambiguity: int = 1,
    max_mentions_per_cui: int = 8,
    evidence_tag: str = "",
) -> Iterator[EvidenceRecord]:
    text = clean_text(" ".join(part for part in [document.title, document.text] if part))
    spans = token_spans(text)
    emitted: set[tuple[str, str]] = set()
    counts_by_cui: dict[str, int] = {}
    occupied_tokens: set[int] = set()

    for start_index in range(len(spans)):
        if start_index in occupied_tokens:
            continue
        max_end = min(len(spans), start_index + max_label_tokens)
        for end_index in range(max_end, start_index, -1):
            if any(index in occupied_tokens for index in range(start_index, end_index)):
                continue
            phrase_start = spans[start_index].start
            phrase_end = spans[end_index - 1].end
            phrase = text[phrase_start:phrase_end]
            norm = normalized_key(phrase)
            if len(norm) < 3:
                continue
            if not is_acceptable_label_match(text, phrase_start, phrase_end, norm):
                continue
            rows = index.lookup(norm, limit=100)
            if not rows:
                continue
            cui = _selected_cui_for_rows(rows, max_ambiguity=max_ambiguity)
            if not cui:
                continue
            if counts_by_cui.get(cui, 0) >= max_mentions_per_cui:
                break
            context = context_window(text, phrase_start, phrase_end, chars=context_chars)
            context_key = normalized_key(context)
            emit_key = (cui, context_key)
            if emit_key in emitted:
                break
            best_row = sorted(
                (row for row in rows if row["cui"] == cui),
                key=lambda row: (-_label_weight(row), row["label"]),
            )[0]
            emitted.add(emit_key)
            occupied_tokens.update(range(start_index, end_index))
            counts_by_cui[cui] = counts_by_cui.get(cui, 0) + 1
            yield EvidenceRecord(
                evidence_id=_evidence_id(document, cui, phrase_start, phrase_end),
                cui=cui,
                text=context,
                source=document.source,
                evidence_type=evidence_type_for_source(document.source, evidence_tag),
                weight=_label_weight(best_row),
                metadata={
                    "corpus_doc_id": document.doc_id,
                    "matched_text": phrase,
                    "matched_label": best_row["label"],
                    "matched_norm": norm,
                    "match_start": phrase_start,
                    "match_end": phrase_end,
                    **document.metadata,
                },
            )
            break


def iter_linked_corpus_evidence(
    documents: Iterable[CorpusDocument],
    index: LabelIndex,
    **kwargs,
) -> Iterator[EvidenceRecord]:
    for document in documents:
        yield from link_document_to_evidence(document, index, **kwargs)


def link_corpus_to_evidence(
    documents: list[CorpusDocument],
    index: LabelIndex,
    **kwargs,
) -> list[EvidenceRecord]:
    return list(iter_linked_corpus_evidence(documents, index, **kwargs))
