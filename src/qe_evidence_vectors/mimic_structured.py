from __future__ import annotations

import csv
import gzip
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from .corpus import stable_doc_id
from .mimic_notes import MimicNoteContextIndex
from .schema import CorpusDocument
from .text import clean_text, normalized_key


@dataclass
class StructuredGroup:
    source: str
    key: str
    title: str
    prefix: str
    metadata: dict
    count: int = 0
    examples: list[str] = field(default_factory=list)
    note_admission_ids: set[str] = field(default_factory=set)
    coordinated_note_count: int = 0
    note_examples: list[str] = field(default_factory=list)

    def add(self, example: str, *, max_examples: int) -> None:
        self.count += 1
        example = clean_text(example)
        if example and len(self.examples) < max_examples and example not in self.examples:
            self.examples.append(example)

    def add_note_context(
        self,
        hadm_id: str,
        note_index: MimicNoteContextIndex | None,
        *,
        max_note_examples: int,
    ) -> None:
        hadm_id = str(hadm_id or "").strip()
        if not hadm_id or note_index is None or hadm_id in self.note_admission_ids:
            return
        if not note_index.has_admission(hadm_id):
            return
        self.note_admission_ids.add(hadm_id)
        self.coordinated_note_count += note_index.note_count(hadm_id)
        for context in note_index.contexts(hadm_id):
            if len(self.note_examples) >= max_note_examples:
                break
            prefix = " ".join(
                part
                for part in [
                    context.source,
                    context.note_kind,
                    context.note_type,
                ]
                if part
            )
            example = clean_text(f"{prefix}: {context.snippet}" if prefix else context.snippet)
            if example and example not in self.note_examples:
                self.note_examples.append(example)

    def to_document(self) -> CorpusDocument:
        parts = [self.prefix, f"Observed in {self.count} MIMIC events."]
        if self.examples:
            parts.append("Examples: " + "; ".join(self.examples) + ".")
        if self.note_admission_ids:
            parts.append(
                "Admission-level MIMIC note coordination: "
                f"structured events for this group co-occurred with {self.coordinated_note_count} "
                f"notes across {len(self.note_admission_ids)} hospital admissions."
            )
        if self.note_examples:
            parts.append(
                "Admission-level note context examples, not direct assertions about the structured item: "
                + "; ".join(self.note_examples)
                + "."
            )
        return CorpusDocument(
            doc_id=stable_doc_id(self.source, self.key),
            source=self.source,
            title=self.title,
            text=clean_text(" ".join(parts)),
            metadata={
                **self.metadata,
                "event_count": self.count,
                "coordinated_note_admission_count": len(self.note_admission_ids),
                "coordinated_note_count": self.coordinated_note_count,
            },
        )


def _open_csv(path: Path):
    path = _resolve_csv_path(path)
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


def _resolve_csv_path(path: Path) -> Path:
    if path.exists():
        return path
    gz_path = Path(f"{path}.gz")
    if gz_path.exists():
        return gz_path
    return path


def _lower_row(row: dict[str, str]) -> dict[str, str]:
    return {name.lower(): value for name, value in row.items() if name is not None}


def _get(row: dict[str, str], key: str) -> str:
    return (row.get(key.lower()) or "").strip()


def _read_lookup(path: Path, key_columns: tuple[str, ...]) -> dict[tuple[str, ...], dict[str, str]]:
    lookup = {}
    with _open_csv(path) as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            row = _lower_row(row)
            key = tuple(_get(row, column) for column in key_columns)
            if all(key):
                lookup[key] = row
    return lookup


def _text(*parts: str) -> str:
    return clean_text(" ".join(part for part in parts if part))


def _value_unit(row: dict[str, str], *, value_column: str = "value", unit_column: str = "valueuom") -> str:
    value = _get(row, value_column)
    unit = _get(row, unit_column)
    if value and unit:
        return f"{value} {unit}"
    return value or unit


def _iter_rows(path: Path, *, max_rows: int | None = None) -> Iterator[dict[str, str]]:
    with _open_csv(path) as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader):
            if max_rows is not None and index >= max_rows:
                break
            yield _lower_row(row)


def _documents_from_groups(groups: dict[str, StructuredGroup]) -> Iterator[CorpusDocument]:
    for _, group in sorted(groups.items()):
        if group.count:
            yield group.to_document()


def iter_lab_documents(
    root: Path,
    *,
    source: str = "mimic_demo_labevents",
    max_rows: int | None = None,
    max_examples: int = 8,
    note_index: MimicNoteContextIndex | None = None,
    max_note_examples: int = 4,
) -> Iterator[CorpusDocument]:
    d_labitems = _read_lookup(root / "hosp" / "d_labitems.csv", ("itemid",))
    groups: dict[str, StructuredGroup] = {}
    for row in _iter_rows(root / "hosp" / "labevents.csv", max_rows=max_rows):
        itemid = _get(row, "itemid")
        item = d_labitems.get((itemid,), {})
        label = clean_text(item.get("label") or f"lab item {itemid}")
        fluid = clean_text(item.get("fluid") or "")
        category = clean_text(item.get("category") or "")
        title = label
        key = itemid
        prefix = _text(
            f"MIMIC laboratory event: {label}.",
            f"Fluid: {fluid}." if fluid else "",
            f"Category: {category}." if category else "",
        )
        group = groups.setdefault(
            key,
            StructuredGroup(
                source=source,
                key=key,
                title=title,
                prefix=prefix,
                metadata={"table": "hosp.labevents", "itemid": itemid, "label": label},
            ),
        )
        value = _value_unit(row)
        flag = _get(row, "flag")
        priority = _get(row, "priority")
        ref_low = _get(row, "ref_range_lower")
        ref_high = _get(row, "ref_range_upper")
        example = _text(
            value,
            f"flag {flag}" if flag else "",
            f"reference range {ref_low}-{ref_high}" if ref_low or ref_high else "",
            priority,
        )
        group.add(example, max_examples=max_examples)
        group.add_note_context(
            _get(row, "hadm_id"),
            note_index,
            max_note_examples=max_note_examples,
        )
    yield from _documents_from_groups(groups)


def _item_prefix(table_label: str, label: str, item: dict[str, str]) -> str:
    category = clean_text(item.get("category") or "")
    unit = clean_text(item.get("unitname") or "")
    param_type = clean_text(item.get("param_type") or "")
    return _text(
        f"MIMIC {table_label}: {label}.",
        f"Category: {category}." if category else "",
        f"Unit: {unit}." if unit else "",
        f"Parameter type: {param_type}." if param_type else "",
    )


def _iter_item_event_documents(
    *,
    root: Path,
    relative_path: str,
    source: str,
    table_label: str,
    example_columns: Iterable[str],
    max_rows: int | None,
    max_examples: int,
    note_index: MimicNoteContextIndex | None,
    max_note_examples: int,
) -> Iterator[CorpusDocument]:
    d_items = _read_lookup(root / "icu" / "d_items.csv", ("itemid",))
    groups: dict[str, StructuredGroup] = {}
    for row in _iter_rows(root / relative_path, max_rows=max_rows):
        itemid = _get(row, "itemid")
        item = d_items.get((itemid,), {})
        label = clean_text(item.get("label") or f"ICU item {itemid}")
        key = itemid
        group = groups.setdefault(
            key,
            StructuredGroup(
                source=source,
                key=key,
                title=label,
                prefix=_item_prefix(table_label, label, item),
                metadata={"table": relative_path, "itemid": itemid, "label": label},
            ),
        )
        example_parts = []
        value = _value_unit(row)
        if value:
            example_parts.append(value)
        for column in example_columns:
            value = _get(row, column)
            if value:
                example_parts.append(f"{column}: {value}")
        warning = _get(row, "warning")
        if warning and warning not in {"0", "0.0"}:
            example_parts.append("warning")
        group.add("; ".join(example_parts), max_examples=max_examples)
        group.add_note_context(
            _get(row, "hadm_id"),
            note_index,
            max_note_examples=max_note_examples,
        )
    yield from _documents_from_groups(groups)


def iter_pharmacy_documents(
    root: Path,
    *,
    source: str = "mimic_demo_pharmacy",
    max_rows: int | None = None,
    max_examples: int = 8,
    note_index: MimicNoteContextIndex | None = None,
    max_note_examples: int = 4,
) -> Iterator[CorpusDocument]:
    groups: dict[str, StructuredGroup] = {}
    for row in _iter_rows(root / "hosp" / "pharmacy.csv", max_rows=max_rows):
        medication = clean_text(_get(row, "medication"))
        if not medication:
            continue
        key = normalized_key(medication)
        group = groups.setdefault(
            key,
            StructuredGroup(
                source=source,
                key=key,
                title=medication,
                prefix=f"MIMIC pharmacy order: {medication}.",
                metadata={"table": "hosp.pharmacy", "medication": medication},
            ),
        )
        group.add(
            _text(
                f"route {_get(row, 'route')}" if _get(row, "route") else "",
                f"frequency {_get(row, 'frequency')}" if _get(row, "frequency") else "",
                f"status {_get(row, 'status')}" if _get(row, "status") else "",
                f"procedure type {_get(row, 'proc_type')}" if _get(row, "proc_type") else "",
            ),
            max_examples=max_examples,
        )
        group.add_note_context(
            _get(row, "hadm_id"),
            note_index,
            max_note_examples=max_note_examples,
        )
    yield from _documents_from_groups(groups)


def iter_mimic_structured_documents(
    root: str | Path,
    *,
    sources: set[str] | None = None,
    source_prefix: str = "mimic_demo",
    max_rows_per_table: int | None = None,
    max_examples_per_group: int = 8,
    note_corpus_paths: Iterable[str | Path] = (),
    max_notes_per_admission: int = 3,
    max_note_examples_per_group: int = 4,
    note_context_chars: int = 240,
) -> Iterator[CorpusDocument]:
    root = Path(root).expanduser()
    source_prefix = source_prefix.strip().strip("_") or "mimic_demo"
    note_paths = [Path(path).expanduser() for path in note_corpus_paths]
    note_index = (
        MimicNoteContextIndex.from_corpus(
            note_paths,
            max_notes_per_admission=max_notes_per_admission,
            snippet_chars=note_context_chars,
        )
        if note_paths
        else None
    )
    source_names = {
        "labevents": f"{source_prefix}_labevents",
        "chartevents": f"{source_prefix}_chartevents",
        "datetimeevents": f"{source_prefix}_datetimeevents",
        "outputevents": f"{source_prefix}_outputevents",
        "inputevents": f"{source_prefix}_inputevents",
        "ingredientevents": f"{source_prefix}_ingredientevents",
        "procedureevents": f"{source_prefix}_procedureevents",
        "pharmacy": f"{source_prefix}_pharmacy",
    }
    available = set(source_names.values())
    selected = sources or available
    unknown = selected - available
    if unknown:
        raise ValueError(f"unknown MIMIC structured sources: {', '.join(sorted(unknown))}")

    if source_names["labevents"] in selected:
        yield from iter_lab_documents(
            root,
            source=source_names["labevents"],
            max_rows=max_rows_per_table,
            max_examples=max_examples_per_group,
            note_index=note_index,
            max_note_examples=max_note_examples_per_group,
        )
    specs = [
        (
            source_names["chartevents"],
            "icu/chartevents.csv",
            "ICU chart event",
            ["valueuom"],
        ),
        (
            source_names["datetimeevents"],
            "icu/datetimeevents.csv",
            "ICU datetime event",
            ["valueuom"],
        ),
        (
            source_names["outputevents"],
            "icu/outputevents.csv",
            "ICU output event",
            ["valueuom"],
        ),
        (
            source_names["inputevents"],
            "icu/inputevents.csv",
            "ICU input event",
            ["amount", "amountuom", "rate", "rateuom", "ordercategoryname", "statusdescription"],
        ),
        (
            source_names["ingredientevents"],
            "icu/ingredientevents.csv",
            "ICU ingredient event",
            ["amount", "amountuom", "rate", "rateuom", "statusdescription"],
        ),
        (
            source_names["procedureevents"],
            "icu/procedureevents.csv",
            "ICU procedure event",
            ["value", "valueuom", "location", "ordercategoryname", "statusdescription"],
        ),
    ]
    for source, relative_path, table_label, example_columns in specs:
        if source not in selected:
            continue
        yield from _iter_item_event_documents(
            root=root,
            relative_path=relative_path,
            source=source,
            table_label=table_label,
            example_columns=example_columns,
            max_rows=max_rows_per_table,
            max_examples=max_examples_per_group,
            note_index=note_index,
            max_note_examples=max_note_examples_per_group,
        )
    if source_names["pharmacy"] in selected:
        yield from iter_pharmacy_documents(
            root,
            source=source_names["pharmacy"],
            max_rows=max_rows_per_table,
            max_examples=max_examples_per_group,
            note_index=note_index,
            max_note_examples=max_note_examples_per_group,
        )
