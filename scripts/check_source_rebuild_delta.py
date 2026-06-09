#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


FIELD_ALIASES = {
    "source_url": ("source_url", "url", "download_url", "source.url", "source.download_url"),
    "source_version": ("source_version", "version", "release", "release_version", "source.version"),
    "source_date": ("source_date", "release_date", "date", "fetch_date", "fetched_at", "source.date"),
    "source_hash": ("source_hash", "content_hash", "hash", "sha256", "source.hash"),
    "records_fetched": ("records_fetched", "fetched_records", "counts.records_fetched", "counts.corpus_documents"),
    "records_changed": ("records_changed", "changed_records", "delta.records_changed", "changes.records_changed"),
    "cuis_gained": ("cuis_gained", "delta.cuis_gained", "cui_delta.gained", "cuis.gained"),
    "cuis_lost": ("cuis_lost", "delta.cuis_lost", "cui_delta.lost", "cuis.lost"),
    "relationship_edges_gained": (
        "relationship_edges_gained",
        "delta.relationship_edges_gained",
        "relationship_edge_delta.gained",
        "relationship_edges.gained",
    ),
    "relationship_edges_lost": (
        "relationship_edges_lost",
        "delta.relationship_edges_lost",
        "relationship_edge_delta.lost",
        "relationship_edges.lost",
    ),
    "top_source_changes_for_benchmark_queries": (
        "top_source_changes_for_benchmark_queries",
        "top_source_changes",
        "benchmark_source_changes",
        "query_source_changes",
    ),
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def value_at_path(record: dict, path: str):
    value = record
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def first_value(record: dict, aliases: tuple[str, ...]):
    for alias in aliases:
        value = value_at_path(record, alias)
        if value is not None:
            return value
    return None


def source_records(manifest: dict) -> list[dict]:
    sources = manifest.get("sources")
    if isinstance(sources, list):
        return [source for source in sources if isinstance(source, dict)]
    if isinstance(manifest.get("source"), list):
        return [source for source in manifest["source"] if isinstance(source, dict)]
    if manifest.get("source") or manifest.get("source_id") or manifest.get("source_name"):
        return [manifest]
    records = []
    for key, value in manifest.items():
        if isinstance(value, dict) and (value.get("source") or value.get("source_id")):
            item = dict(value)
            item.setdefault("source_id", key)
            records.append(item)
    return records


def source_key(record: dict) -> str:
    return str(
        record.get("source_id")
        or record.get("source")
        or record.get("source_name")
        or record.get("source_subset_prefix")
        or "unknown"
    )


def normalize_record(record: dict) -> dict:
    normalized = {"source_id": source_key(record)}
    for field, aliases in FIELD_ALIASES.items():
        normalized[field] = first_value(record, aliases)
    return normalized


def missing_required_fields(record: dict) -> list[str]:
    return [field for field in FIELD_ALIASES if record.get(field) is None]


def numeric(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compare_records(previous: dict | None, current: dict) -> dict:
    fields = {}
    for field in FIELD_ALIASES:
        previous_value = None if previous is None else previous.get(field)
        current_value = current.get(field)
        fields[field] = {
            "previous": previous_value,
            "current": current_value,
            "changed": previous is not None and previous_value != current_value,
        }
    return fields


def collapse_failure(
    previous: dict | None,
    current: dict,
    *,
    tolerance: float,
    min_baseline: int,
) -> dict | None:
    if previous is None:
        return None
    previous_count = numeric(previous.get("records_fetched"))
    current_count = numeric(current.get("records_fetched"))
    if previous_count is None or current_count is None or previous_count < min_baseline:
        return None
    minimum = previous_count * max(0.0, 1.0 - tolerance)
    if current_count >= minimum:
        return None
    return {
        "baseline": previous_count,
        "current": current_count,
        "minimum_allowed": minimum,
        "tolerance": tolerance,
    }


def build_delta_report(previous_manifest: dict | None, current_manifest: dict, args: argparse.Namespace) -> dict:
    previous_records = {}
    if previous_manifest is not None:
        previous_records = {
            source_key(record): normalize_record(record)
            for record in source_records(previous_manifest)
        }
    current_records = [normalize_record(record) for record in source_records(current_manifest)]
    source_reports = []
    failures = []
    for current in current_records:
        source_id = current["source_id"]
        previous = previous_records.get(source_id)
        missing = missing_required_fields(current)
        collapse = collapse_failure(
            previous,
            current,
            tolerance=args.source_count_collapse_tolerance,
            min_baseline=args.source_count_collapse_min_baseline,
        )
        source_report = {
            "source_id": source_id,
            "missing_required_fields": missing,
            "delta": compare_records(previous, current),
            "source_count_collapse": collapse,
        }
        source_reports.append(source_report)
        if missing and not args.allow_missing_required:
            failures.append(
                {
                    "source_id": source_id,
                    "check": "required_source_delta_fields_present",
                    "missing_fields": missing,
                }
            )
        if collapse is not None:
            failures.append(
                {
                    "source_id": source_id,
                    "check": "records_fetched_no_unexpected_collapse",
                    **collapse,
                }
            )
    if not current_records:
        failures.append({"check": "current_manifest_has_sources", "message": "No source records found."})
    return {
        "passed": not failures,
        "summary": {
            "sources": len(current_records),
            "failures": len(failures),
        },
        "sources": source_reports,
        "failures": failures,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate source rebuild delta metadata.")
    parser.add_argument("--current", type=Path, required=True, help="Current source rebuild manifest JSON.")
    parser.add_argument("--previous", type=Path, help="Previous retained source rebuild manifest JSON.")
    parser.add_argument("--out", type=Path, help="Optional JSON report path.")
    parser.add_argument(
        "--allow-missing-required",
        action="store_true",
        help="Report missing required fields without failing.",
    )
    parser.add_argument("--source-count-collapse-tolerance", type=float, default=0.25)
    parser.add_argument("--source-count-collapse-min-baseline", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    previous = read_json(args.previous) if args.previous else None
    current = read_json(args.current)
    report = build_delta_report(previous, current, args)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
