from __future__ import annotations

import csv
import gzip
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from .schema import CorpusDocument, iter_jsonl, write_jsonl
from .text import clean_text


@dataclass(frozen=True)
class MimicNoteSpec:
    note_kind: str
    source: str
    relative_path: str
    max_rows: int | None = None


@dataclass(frozen=True)
class MimicNoteCorpusResult:
    note_kind: str
    source: str
    path: Path
    count: int


@dataclass(frozen=True)
class MimicNoteContext:
    source: str
    note_kind: str
    note_type: str
    note_id: str
    snippet: str


class MimicNoteContextIndex:
    def __init__(
        self,
        contexts_by_hadm_id: dict[str, list[MimicNoteContext]],
        note_counts_by_hadm_id: dict[str, int],
    ) -> None:
        self.contexts_by_hadm_id = contexts_by_hadm_id
        self.note_counts_by_hadm_id = note_counts_by_hadm_id

    def has_admission(self, hadm_id: str) -> bool:
        return bool(self.note_counts_by_hadm_id.get(str(hadm_id or "").strip()))

    def note_count(self, hadm_id: str) -> int:
        return int(self.note_counts_by_hadm_id.get(str(hadm_id or "").strip()) or 0)

    def contexts(self, hadm_id: str) -> list[MimicNoteContext]:
        return list(self.contexts_by_hadm_id.get(str(hadm_id or "").strip()) or [])

    @classmethod
    def from_corpus(
        cls,
        paths: Iterable[str | Path],
        *,
        max_notes_per_admission: int = 3,
        snippet_chars: int = 240,
    ) -> "MimicNoteContextIndex":
        contexts_by_hadm_id: dict[str, list[MimicNoteContext]] = {}
        note_counts_by_hadm_id: dict[str, int] = {}
        for path in paths:
            for payload in iter_jsonl(path):
                metadata = payload.get("metadata") or {}
                hadm_id = str(metadata.get("hadm_id") or "").strip()
                if not hadm_id:
                    continue
                note_counts_by_hadm_id[hadm_id] = note_counts_by_hadm_id.get(hadm_id, 0) + 1
                bucket = contexts_by_hadm_id.setdefault(hadm_id, [])
                if len(bucket) >= max_notes_per_admission:
                    continue
                text = clean_text(str(payload.get("text") or ""))
                if not text:
                    continue
                if snippet_chars > 0 and len(text) > snippet_chars:
                    text = text[:snippet_chars].rstrip() + "..."
                bucket.append(
                    MimicNoteContext(
                        source=str(payload.get("source") or ""),
                        note_kind=str(metadata.get("note_kind") or ""),
                        note_type=str(metadata.get("note_type") or ""),
                        note_id=str(metadata.get("note_id") or payload.get("doc_id") or ""),
                        snippet=text,
                    )
                )
        return cls(contexts_by_hadm_id, note_counts_by_hadm_id)


MIMIC_NOTE_SPECS = {
    "discharge": MimicNoteSpec(
        note_kind="discharge",
        source="mimic_iv_note_discharge",
        relative_path="note/discharge.csv.gz",
    ),
    "radiology": MimicNoteSpec(
        note_kind="radiology",
        source="mimic_iv_note_radiology",
        relative_path="note/radiology.csv.gz",
    ),
}


def _open_text(path: str | Path):
    path = Path(path).expanduser()
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


def _get(row: dict[str, str], key: str) -> str:
    return (row.get(key) or "").strip()


def iter_mimic_note_documents(
    path: str | Path,
    *,
    note_kind: str,
    source: str,
    max_rows: int | None = None,
) -> Iterator[CorpusDocument]:
    if max_rows is not None and max_rows <= 0:
        raise ValueError("max_rows must be positive when supplied")
    path = Path(path).expanduser()
    with _open_text(path) as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=1):
            if max_rows is not None and row_number > max_rows:
                break
            text = clean_text(_get(row, "text"))
            note_id = _get(row, "note_id")
            if not text or not note_id:
                continue
            note_type = _get(row, "note_type")
            title = f"{note_kind} note {note_type}".strip()
            yield CorpusDocument(
                doc_id=f"MIMIC_NOTE:{note_id}",
                source=source,
                title=title,
                text=text,
                metadata={
                    "note_id": note_id,
                    "subject_id": _get(row, "subject_id"),
                    "hadm_id": _get(row, "hadm_id"),
                    "note_type": note_type,
                    "note_seq": _get(row, "note_seq"),
                    "charttime": _get(row, "charttime"),
                    "storetime": _get(row, "storetime"),
                    "note_kind": note_kind,
                    "table": f"{note_kind}.csv.gz",
                    "input_path": str(path),
                },
            )


def mimic_note_specs(
    *,
    root: str | Path,
    note_kinds: list[str] | None = None,
    max_discharge_rows: int | None = None,
    max_radiology_rows: int | None = None,
) -> list[MimicNoteSpec]:
    root = Path(root).expanduser()
    selected = note_kinds or list(MIMIC_NOTE_SPECS)
    unknown = sorted(set(selected) - set(MIMIC_NOTE_SPECS))
    if unknown:
        raise ValueError(f"unknown MIMIC note kind(s): {', '.join(unknown)}")
    max_by_kind = {
        "discharge": max_discharge_rows,
        "radiology": max_radiology_rows,
    }
    specs = []
    for note_kind in selected:
        base = MIMIC_NOTE_SPECS[note_kind]
        path = root / base.relative_path
        if not path.exists():
            raise FileNotFoundError(f"missing MIMIC note file: {path}")
        specs.append(
            MimicNoteSpec(
                note_kind=base.note_kind,
                source=base.source,
                relative_path=str(path),
                max_rows=max_by_kind.get(note_kind),
            )
        )
    return specs


def write_mimic_note_corpora(
    *,
    root: str | Path,
    out_dir: str | Path,
    note_kinds: list[str] | None = None,
    max_discharge_rows: int | None = None,
    max_radiology_rows: int | None = None,
) -> list[MimicNoteCorpusResult]:
    out_dir = Path(out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for spec in mimic_note_specs(
        root=root,
        note_kinds=note_kinds,
        max_discharge_rows=max_discharge_rows,
        max_radiology_rows=max_radiology_rows,
    ):
        out_path = out_dir / f"{spec.source}_corpus.jsonl"
        documents = iter_mimic_note_documents(
            spec.relative_path,
            note_kind=spec.note_kind,
            source=spec.source,
            max_rows=spec.max_rows,
        )
        count = write_jsonl(out_path, documents)
        results.append(
            MimicNoteCorpusResult(
                note_kind=spec.note_kind,
                source=spec.source,
                path=out_path,
                count=count,
            )
        )
    return results
