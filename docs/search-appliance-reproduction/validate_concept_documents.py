#!/usr/bin/env python3
"""Validate UMLS search concept-document JSON, JSONL, or gzipped JSONL files."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Iterator


VIEW_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
REQUIRED_FIELDS = {
    "doc_id",
    "cui",
    "view",
    "text",
    "evidence_count",
    "sources",
    "labels",
    "metadata",
}


def iter_records(path: Path) -> Iterator[tuple[int, dict]]:
    if path.suffix == ".json" and not path.name.endswith(".jsonl.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            for number, record in enumerate(payload, start=1):
                yield number, record
        else:
            yield 1, payload
        return

    opener = gzip.open if path.suffix == ".gz" else Path.open
    with opener(path, "rt", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if line.strip():
                yield number, json.loads(line)


def finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_record(record: object, *, path: Path, line: int) -> list[str]:
    location = f"{path}:{line}"
    if not isinstance(record, dict):
        return [f"{location}: record must be a JSON object"]

    errors: list[str] = []
    missing = sorted(REQUIRED_FIELDS - set(record))
    if missing:
        errors.append(f"{location}: missing fields: {', '.join(missing)}")
        return errors

    doc_id = record.get("doc_id")
    cui = record.get("cui")
    view = record.get("view")
    text = record.get("text")
    expected_doc_id = f"{cui}:{view}"
    if not isinstance(doc_id, str) or not doc_id:
        errors.append(f"{location}: doc_id must be a non-empty string")
    elif doc_id != expected_doc_id:
        errors.append(f"{location}: doc_id must be {expected_doc_id!r}")
    if not isinstance(cui, str) or not cui:
        errors.append(f"{location}: cui must be a non-empty string")
    if not isinstance(view, str) or not VIEW_RE.fullmatch(view):
        errors.append(f"{location}: invalid view {view!r}")
    if not isinstance(text, str) or not text:
        errors.append(f"{location}: text must be a non-empty string")
    else:
        expected_prefix = f"CUI: {cui}\nEvidence view: {view}\n"
        if not text.startswith(expected_prefix):
            errors.append(f"{location}: text does not start with the canonical CUI/view header")

    evidence_count = record.get("evidence_count")
    if not isinstance(evidence_count, int) or isinstance(evidence_count, bool) or evidence_count < 0:
        errors.append(f"{location}: evidence_count must be a non-negative integer")

    for field in ("sources", "labels"):
        values = record.get(field)
        if not isinstance(values, list) or not all(isinstance(value, str) and value for value in values):
            errors.append(f"{location}: {field} must be an array of non-empty strings")
        elif field == "sources" and len(values) != len(set(values)):
            errors.append(f"{location}: sources must not contain duplicates")

    metadata = record.get("metadata")
    if not isinstance(metadata, dict):
        errors.append(f"{location}: metadata must be an object")
    else:
        total_weight = metadata.get("total_weight")
        if total_weight is not None and not finite_number(total_weight):
            errors.append(f"{location}: metadata.total_weight must be finite")
        expected_hash = metadata.get("document_text_hash")
        if expected_hash and isinstance(text, str):
            actual_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if expected_hash.lower() != actual_hash:
                errors.append(f"{location}: metadata.document_text_hash does not match text")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()

    errors: list[str] = []
    seen: dict[str, str] = {}
    count = 0
    for path in args.paths:
        try:
            records = iter_records(path)
            for line, record in records:
                count += 1
                errors.extend(validate_record(record, path=path, line=line))
                if isinstance(record, dict) and isinstance(record.get("doc_id"), str):
                    doc_id = record["doc_id"]
                    location = f"{path}:{line}"
                    if doc_id in seen:
                        errors.append(f"{location}: duplicate doc_id {doc_id!r}; first seen at {seen[doc_id]}")
                    else:
                        seen[doc_id] = location
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"{path}: could not read records: {exc}")

    if errors:
        for error in errors:
            print(error)
        print(f"FAILED: {len(errors)} error(s) across {count} record(s)")
        return 1
    print(f"OK: {count} record(s), {len(seen)} unique doc_id value(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
