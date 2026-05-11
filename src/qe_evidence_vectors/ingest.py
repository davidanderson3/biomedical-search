from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Iterator

from .schema import EvidenceRecord
from .text import clean_text


def stable_evidence_id(*parts: str) -> str:
    payload = "\t".join(parts)
    return "EVID_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:20]


def _get(row: dict[str, str], *names: str) -> str:
    lower = {key.lower(): value for key, value in row.items() if key is not None}
    for name in names:
        value = lower.get(name.lower())
        if value is not None:
            return value.strip()
    return ""


def _float_or_default(value: str, default: float) -> float:
    if not value:
        return default
    return float(value)


def _metadata(row: dict[str, str], exclude: set[str]) -> dict[str, str]:
    metadata = {}
    for key, value in row.items():
        if key is None or key.lower() in exclude or value == "":
            continue
        metadata[key] = value
    return metadata


def read_query_log_tsv(
    path: str | Path,
    *,
    default_source: str,
    default_evidence_type: str = "failed_query",
) -> Iterator[EvidenceRecord]:
    with Path(path).expanduser().open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for line_number, row in enumerate(reader, start=2):
            query = clean_text(_get(row, "query", "search", "text"))
            cui = _get(row, "cui", "CUI")
            if not query or not cui:
                raise ValueError(f"{path}:{line_number}: query-log evidence requires query and cui")
            source = _get(row, "source") or default_source
            evidence_type = _get(row, "evidence_type", "type") or default_evidence_type
            count = _float_or_default(_get(row, "count", "frequency"), 1.0)
            weight = _float_or_default(_get(row, "weight"), count)
            evidence_id = stable_evidence_id(source, str(line_number), cui, query)
            yield EvidenceRecord(
                evidence_id=evidence_id,
                cui=cui,
                text=query,
                source=source,
                evidence_type=evidence_type,
                weight=weight,
                metadata=_metadata(
                    row,
                    {
                        "query",
                        "search",
                        "text",
                        "cui",
                        "source",
                        "evidence_type",
                        "type",
                        "count",
                        "frequency",
                        "weight",
                    },
                ),
            )


def read_snippet_tsv(
    path: str | Path,
    *,
    default_source: str,
    default_evidence_type: str = "reviewed_snippet",
) -> Iterator[EvidenceRecord]:
    with Path(path).expanduser().open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for line_number, row in enumerate(reader, start=2):
            text = clean_text(_get(row, "text", "snippet", "mention"))
            cui = _get(row, "cui", "CUI")
            if not text or not cui:
                raise ValueError(f"{path}:{line_number}: snippet evidence requires cui and text")
            source = _get(row, "source") or default_source
            evidence_type = _get(row, "evidence_type", "type") or default_evidence_type
            weight = _float_or_default(_get(row, "weight"), 1.0)
            evidence_id = stable_evidence_id(source, str(line_number), cui, text)
            yield EvidenceRecord(
                evidence_id=evidence_id,
                cui=cui,
                text=text,
                source=source,
                evidence_type=evidence_type,
                weight=weight,
                metadata=_metadata(
                    row,
                    {
                        "text",
                        "snippet",
                        "mention",
                        "cui",
                        "source",
                        "evidence_type",
                        "type",
                        "weight",
                    },
                ),
            )

