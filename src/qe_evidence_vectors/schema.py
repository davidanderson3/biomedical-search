from __future__ import annotations

import gzip
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator


@dataclass(frozen=True)
class CorpusDocument:
    doc_id: str
    source: str
    text: str
    title: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    cui: str
    text: str
    source: str
    evidence_type: str
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConceptDocument:
    doc_id: str
    cui: str
    view: str
    text: str
    evidence_count: int
    sources: list[str]
    labels: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VectorRecord:
    doc_id: str
    cui: str
    view: str
    vector: list[float]
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


def write_jsonl(path: str | Path, records: Iterable[Any]) -> int:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    opener = gzip.open if path.suffix == ".gz" else Path.open
    with opener(path, "wt", encoding="utf-8") as handle:
        for record in records:
            payload = asdict(record) if hasattr(record, "__dataclass_fields__") else record
            handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
            count += 1
    return count


def iter_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    path = Path(path).expanduser()
    opener = gzip.open if path.suffix == ".gz" else Path.open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSONL") from exc
