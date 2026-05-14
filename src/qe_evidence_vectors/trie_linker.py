from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from .linker import (
    _evidence_id,
    context_window,
    evidence_type_for_source,
    is_acceptable_label_match,
    token_spans,
)
from .schema import CorpusDocument, EvidenceRecord
from .text import clean_text, normalized_key


@dataclass(frozen=True)
class LabelEntry:
    cui: str
    label: str
    tty: str
    ispref: str


@dataclass
class TrieNode:
    children: dict[str, "TrieNode"] = field(default_factory=dict)
    entries: tuple[LabelEntry, ...] = ()


def label_weight(entry: LabelEntry) -> float:
    weight = 1.0
    if entry.ispref == "Y":
        weight += 0.25
    if entry.tty in {"PT", "MH", "PN", "FN"}:
        weight += 0.25
    return weight


class LabelTrie:
    def __init__(self) -> None:
        self.root = TrieNode()
        self.norm_count = 0
        self.entry_count = 0

    def add(self, norm: str, entries: list[LabelEntry]) -> None:
        tokens = norm.split()
        if not tokens or not entries:
            return
        node = self.root
        for token in tokens:
            node = node.children.setdefault(token, TrieNode())
        if not node.entries:
            self.norm_count += 1
        self.entry_count += len(entries)
        node.entries = tuple(entries)

    @classmethod
    def from_sqlite(cls, path: str | Path, *, max_label_tokens: int | None = None) -> "LabelTrie":
        trie = cls()
        conn = sqlite3.connect(str(Path(path).expanduser()))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT norm, cui, label, tty, ispref
                FROM labels
                ORDER BY norm, cui
                """
            )
            current_norm: str | None = None
            current_rows: list[sqlite3.Row] = []
            for row in rows:
                norm = row["norm"]
                if current_norm is not None and norm != current_norm:
                    _flush_norm(trie, current_norm, current_rows, max_label_tokens=max_label_tokens)
                    current_rows = []
                current_norm = norm
                current_rows.append(row)
            if current_norm is not None:
                _flush_norm(trie, current_norm, current_rows, max_label_tokens=max_label_tokens)
        finally:
            conn.close()
        return trie


def _flush_norm(
    trie: LabelTrie,
    norm: str,
    rows: list[sqlite3.Row],
    *,
    max_label_tokens: int | None,
) -> None:
    if max_label_tokens is not None and len(norm.split()) > max_label_tokens:
        return
    best_by_cui: dict[str, LabelEntry] = {}
    for row in rows:
        entry = LabelEntry(
            cui=row["cui"],
            label=row["label"],
            tty=row["tty"],
            ispref=row["ispref"],
        )
        current = best_by_cui.get(entry.cui)
        if current is None or _entry_sort_key(entry) < _entry_sort_key(current):
            best_by_cui[entry.cui] = entry
    trie.add(norm, list(best_by_cui.values()))


def _entry_sort_key(entry: LabelEntry) -> tuple[float, str]:
    return (-label_weight(entry), entry.label)


def _best_entry_for_cui(entries: tuple[LabelEntry, ...], cui: str) -> LabelEntry:
    return min((entry for entry in entries if entry.cui == cui), key=_entry_sort_key)


def _selected_cui_for_entries(entries: tuple[LabelEntry, ...], *, max_ambiguity: int) -> str:
    cuis = sorted({entry.cui for entry in entries})
    if len(cuis) <= max_ambiguity:
        return cuis[0] if cuis else ""
    if max_ambiguity != 1:
        return ""
    best_entries = sorted((_best_entry_for_cui(entries, cui) for cui in cuis), key=_entry_sort_key)
    if len(best_entries) < 2:
        return best_entries[0].cui if best_entries else ""
    best_weight = label_weight(best_entries[0])
    next_weight = label_weight(best_entries[1])
    return best_entries[0].cui if best_weight > next_weight else ""


def normalized_span_tokens(text: str) -> tuple[list, list[str]]:
    spans = token_spans(text)
    # token_spans only emits ASCII alphanumeric tokens, so lowercasing is
    # equivalent to full normalized_key() here and avoids regex work per token.
    tokens = [span.token.lower() for span in spans]
    return spans, tokens


def link_document_to_evidence_trie(
    document: CorpusDocument,
    trie: LabelTrie,
    *,
    max_label_tokens: int = 8,
    context_chars: int = 320,
    max_ambiguity: int = 1,
    max_mentions_per_cui: int = 8,
    evidence_tag: str = "",
) -> Iterator[EvidenceRecord]:
    text = clean_text(" ".join(part for part in [document.title, document.text] if part))
    spans, tokens = normalized_span_tokens(text)
    emitted: set[tuple[str, str]] = set()
    counts_by_cui: dict[str, int] = {}
    occupied_tokens: set[int] = set()

    for start_index in range(len(spans)):
        if start_index in occupied_tokens:
            continue
        node = trie.root
        best: tuple[int, tuple[LabelEntry, ...], str] | None = None
        max_end = min(len(spans), start_index + max_label_tokens)
        for end_index in range(start_index, max_end):
            if end_index in occupied_tokens:
                break
            token = tokens[end_index]
            if not token or token not in node.children:
                break
            node = node.children[token]
            if node.entries:
                selected_cui = _selected_cui_for_entries(
                    node.entries,
                    max_ambiguity=max_ambiguity,
                )
                phrase_start = spans[start_index].start
                phrase_end = spans[end_index].end
                norm = " ".join(tokens[start_index : end_index + 1])
                if selected_cui and is_acceptable_label_match(
                    text,
                    phrase_start,
                    phrase_end,
                    norm,
                ):
                    best = (end_index + 1, node.entries, selected_cui)
        if best is None:
            continue

        end_index, entries, cui = best
        if counts_by_cui.get(cui, 0) >= max_mentions_per_cui:
            continue

        phrase_start = spans[start_index].start
        phrase_end = spans[end_index - 1].end
        phrase = text[phrase_start:phrase_end]
        norm = " ".join(tokens[start_index:end_index])
        context = context_window(text, phrase_start, phrase_end, chars=context_chars)
        context_key = normalized_key(context)
        emit_key = (cui, context_key)
        if emit_key in emitted:
            continue

        best_entry = _best_entry_for_cui(entries, cui)
        emitted.add(emit_key)
        occupied_tokens.update(range(start_index, end_index))
        counts_by_cui[cui] = counts_by_cui.get(cui, 0) + 1
        yield EvidenceRecord(
            evidence_id=_evidence_id(document, cui, phrase_start, phrase_end),
            cui=cui,
            text=context,
            source=document.source,
            evidence_type=evidence_type_for_source(document.source, evidence_tag),
            weight=label_weight(best_entry),
            metadata={
                "corpus_doc_id": document.doc_id,
                "matched_text": phrase,
                "matched_label": best_entry.label,
                "matched_norm": norm,
                "match_start": phrase_start,
                "match_end": phrase_end,
                **document.metadata,
            },
        )


def iter_linked_corpus_evidence_trie(
    documents: Iterable[CorpusDocument],
    trie: LabelTrie,
    **kwargs,
) -> Iterator[EvidenceRecord]:
    for document in documents:
        yield from link_document_to_evidence_trie(document, trie, **kwargs)
