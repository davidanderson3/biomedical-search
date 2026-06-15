#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SLICE = ROOT / "config" / "search_quality_pubmed_long_document_slice.tsv"
DEFAULT_QUERY_FILES = [
    ROOT / "build" / "pubmed_literature_benchmark_seed" / "pubmed_literature_dev_queries.tsv",
    ROOT / "build" / "pubmed_literature_benchmark_seed" / "pubmed_literature_heldout_queries.tsv",
]
DEFAULT_OUTPUT = ROOT / "build" / "pubmed_literature_benchmark_seed" / "pubmed_long_document_focused_queries.tsv"
DEFAULT_MANIFEST = ROOT / "build" / "pubmed_literature_benchmark_seed" / "pubmed_long_document_focused_manifest.json"
QUERY_FIELDS = ["id", "query", "expected_cuis", "why", "disallowed_cuis"]
SLICE_FIELDS = ["id", "split", "focus", "why"]


def _dict_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(
            (line for line in handle if line.strip() and not line.lstrip().startswith("#")),
            delimiter="\t",
        )
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def read_slice(path: Path) -> list[dict[str, str]]:
    rows = _dict_rows(path)
    missing_fields = [field for field in SLICE_FIELDS if not rows or field not in rows[0]]
    if missing_fields:
        raise ValueError(f"{path} is missing required columns: {', '.join(missing_fields)}")
    seen: set[str] = set()
    cleaned: list[dict[str, str]] = []
    for row in rows:
        row_id = row["id"]
        if not row_id:
            continue
        if row_id in seen:
            raise ValueError(f"{path} contains duplicate slice id: {row_id}")
        seen.add(row_id)
        if not row_id.startswith("pubmed_"):
            raise ValueError(f"{row_id} must use a pubmed_ id")
        if row["split"] not in {"dev", "heldout"}:
            raise ValueError(f"{row_id} has unsupported split {row['split']!r}")
        for field in ("focus", "why"):
            if not row[field]:
                raise ValueError(f"{row_id} is missing {field}")
        cleaned.append({field: row[field] for field in SLICE_FIELDS})
    if not cleaned:
        raise ValueError(f"{path} does not contain any slice rows")
    return cleaned


def read_query_rows(paths: list[Path]) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    missing_paths = [path for path in paths if not path.exists()]
    if missing_paths:
        missing = ", ".join(str(path) for path in missing_paths)
        raise FileNotFoundError(
            "Missing PubMed seed query file(s): "
            f"{missing}. Run scripts/fetch_pubmed_paragraph_queries.py with --strict-curation first."
        )

    rows_by_id: dict[str, dict[str, str]] = {}
    sources_by_id: dict[str, str] = {}
    for path in paths:
        for row in _dict_rows(path):
            row_id = row.get("id", "")
            if not row_id:
                continue
            if row_id in rows_by_id:
                raise ValueError(f"Duplicate query id {row_id} across query files")
            for field in QUERY_FIELDS:
                if field not in row:
                    raise ValueError(f"{path} row {row_id} is missing {field}")
            rows_by_id[row_id] = {field: row.get(field, "") for field in QUERY_FIELDS}
            sources_by_id[row_id] = str(path)
    return rows_by_id, sources_by_id


def materialize_slice(
    slice_rows: list[dict[str, str]],
    query_rows: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    missing_ids = [row["id"] for row in slice_rows if row["id"] not in query_rows]
    if missing_ids:
        raise KeyError(f"Slice ids are missing from PubMed seed query files: {', '.join(missing_ids)}")

    for slice_row in slice_rows:
        source = query_rows[slice_row["id"]]
        query = source["query"]
        expected_cuis = source["expected_cuis"]
        if "PubMed PMID" not in query:
            raise ValueError(f"{slice_row['id']} is not a PubMed query row")
        if len(query) < 500:
            raise ValueError(f"{slice_row['id']} is too short for the long-document slice")
        if not expected_cuis:
            raise ValueError(f"{slice_row['id']} is missing expected_cuis")
        selected.append(
            {
                "id": source["id"],
                "query": query,
                "expected_cuis": expected_cuis,
                "why": (
                    f"{source['why']} Focused long-document lane: {slice_row['focus']}. "
                    f"Slice reason: {slice_row['why']}"
                ).strip(),
                "disallowed_cuis": source["disallowed_cuis"],
            }
        )
    return selected


def write_query_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=QUERY_FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in QUERY_FIELDS})


def write_manifest(
    path: Path,
    *,
    slice_path: Path,
    slice_rows: list[dict[str, str]],
    selected_rows: list[dict[str, str]],
    query_sources: dict[str, str],
    query_files: list[Path],
    output: Path,
) -> dict[str, object]:
    manifest = {
        "slice": str(slice_path),
        "query_files": [str(path) for path in query_files],
        "output": str(output),
        "rows": len(selected_rows),
        "splits": {
            split: sum(1 for row in slice_rows if row["split"] == split)
            for split in sorted({row["split"] for row in slice_rows})
        },
        "min_query_chars": min(len(row["query"]) for row in selected_rows),
        "max_query_chars": max(len(row["query"]) for row in selected_rows),
        "selected": [
            {
                "id": row["id"],
                "split": row["split"],
                "focus": row["focus"],
                "source": query_sources.get(row["id"], ""),
            }
            for row in slice_rows
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize the focused PubMed long-document benchmark slice.")
    parser.add_argument("--slice", type=Path, default=DEFAULT_SLICE)
    parser.add_argument("--query-file", type=Path, action="append", default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    query_files = args.query_file or DEFAULT_QUERY_FILES
    slice_rows = read_slice(args.slice)
    query_rows, query_sources = read_query_rows(query_files)
    selected_rows = materialize_slice(slice_rows, query_rows)
    write_query_tsv(args.output, selected_rows)
    manifest = write_manifest(
        args.manifest,
        slice_path=args.slice,
        slice_rows=slice_rows,
        selected_rows=selected_rows,
        query_sources=query_sources,
        query_files=query_files,
        output=args.output,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
