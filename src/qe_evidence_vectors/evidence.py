from __future__ import annotations

from pathlib import Path
from typing import Iterator

from .schema import EvidenceRecord, iter_jsonl


def evidence_from_payload(payload: dict) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=payload["evidence_id"],
        cui=payload["cui"],
        text=payload["text"],
        source=payload.get("source", ""),
        evidence_type=payload.get("evidence_type", ""),
        weight=float(payload.get("weight", 1.0)),
        metadata=payload.get("metadata", {}),
    )


def iter_evidence_jsonl(path: str | Path) -> Iterator[EvidenceRecord]:
    for payload in iter_jsonl(path):
        yield evidence_from_payload(payload)


def filter_evidence_records(
    records,
    *,
    include_source: set[str] | None = None,
    exclude_source: set[str] | None = None,
    include_evidence_type: set[str] | None = None,
    exclude_evidence_type: set[str] | None = None,
) -> Iterator[EvidenceRecord]:
    for record in records:
        if include_source is not None and record.source not in include_source:
            continue
        if exclude_source is not None and record.source in exclude_source:
            continue
        if include_evidence_type is not None and record.evidence_type not in include_evidence_type:
            continue
        if exclude_evidence_type is not None and record.evidence_type in exclude_evidence_type:
            continue
        yield record


def iter_filtered_evidence_files(
    paths: list[str | Path],
    *,
    include_source: set[str] | None = None,
    exclude_source: set[str] | None = None,
    include_evidence_type: set[str] | None = None,
    exclude_evidence_type: set[str] | None = None,
) -> Iterator[EvidenceRecord]:
    for path in paths:
        yield from filter_evidence_records(
            iter_evidence_jsonl(path),
            include_source=include_source,
            exclude_source=exclude_source,
            include_evidence_type=include_evidence_type,
            exclude_evidence_type=exclude_evidence_type,
        )

