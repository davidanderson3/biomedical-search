from __future__ import annotations

import csv
import gzip
import hashlib
from pathlib import Path
from typing import Iterable, Iterator

from .schema import CorpusDocument, iter_jsonl
from .text import clean_text, normalized_key


def stable_doc_id(*parts: str) -> str:
    payload = "\t".join(parts)
    return "DOC_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:20]


def _open_text(path: str | Path):
    path = Path(path).expanduser()
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


def _get(row: dict[str, str], name: str) -> str:
    lower = {key.lower(): value for key, value in row.items() if key is not None}
    return (lower.get(name.lower()) or "").strip()


def _lower_row(row: dict[str, str]) -> dict[str, str]:
    return {key.lower(): value for key, value in row.items() if key is not None}


def _get_lower(row: dict[str, str], name: str) -> str:
    return (row.get(name.lower()) or "").strip()


def read_corpus_jsonl(path: str | Path) -> Iterator[CorpusDocument]:
    for payload in iter_jsonl(path):
        yield CorpusDocument(
            doc_id=payload["doc_id"],
            source=payload["source"],
            text=payload["text"],
            title=payload.get("title", ""),
            metadata=payload.get("metadata", {}),
        )


def read_tabular_corpus(
    path: str | Path,
    *,
    source: str,
    text_columns: list[str],
    id_columns: list[str] | None = None,
    title_columns: list[str] | None = None,
    delimiter: str | None = None,
    max_rows: int | None = None,
) -> Iterator[CorpusDocument]:
    path = Path(path).expanduser()
    if delimiter is None:
        delimiter = "\t" if path.suffixes[-2:] == [".tsv", ".gz"] or path.suffix == ".tsv" else ","
    elif delimiter == "\\t":
        delimiter = "\t"
    id_columns = id_columns or []
    title_columns = title_columns or []

    with _open_text(path) as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        for line_number, row in enumerate(reader, start=2):
            if max_rows is not None and line_number - 2 >= max_rows:
                break
            lower_row = _lower_row(row)
            text_parts = [clean_text(_get_lower(lower_row, column)) for column in text_columns]
            text = clean_text(" ".join(part for part in text_parts if part))
            if not text:
                continue
            id_parts = [_get_lower(lower_row, column) for column in id_columns]
            id_parts = [part for part in id_parts if part]
            if not id_parts:
                id_parts = [path.name, str(line_number)]
            title_parts = [clean_text(_get_lower(lower_row, column)) for column in title_columns]
            title = clean_text(" ".join(part for part in title_parts if part))
            metadata = {
                "input_path": str(path),
                "line_number": line_number,
                "id_columns": {column: _get_lower(lower_row, column) for column in id_columns},
            }
            yield CorpusDocument(
                doc_id=stable_doc_id(source, *id_parts),
                source=source,
                title=title,
                text=text,
                metadata=metadata,
            )


def _dedupe_keys(document: CorpusDocument) -> list[str]:
    keys = [f"doc_id:{document.doc_id}"]
    pmid = str(document.metadata.get("pmid", "")).strip()
    pmcid = str(document.metadata.get("pmcid", "")).strip()
    doi = str(document.metadata.get("doi", "")).strip().lower()
    if pmid:
        keys.append(f"pmid:{pmid}")
    if pmcid:
        keys.append(f"pmcid:{pmcid}")
    if doi:
        keys.append(f"doi:{doi}")
    title_key = normalized_key(document.title)
    if len(title_key) >= 24:
        keys.append(f"title:{title_key}")
    return keys


def merge_corpus_documents(paths: Iterable[str | Path]) -> Iterator[CorpusDocument]:
    seen: set[str] = set()
    for path in paths:
        for document in read_corpus_jsonl(path):
            keys = _dedupe_keys(document)
            if any(key in seen for key in keys):
                continue
            seen.update(keys)
            yield document
