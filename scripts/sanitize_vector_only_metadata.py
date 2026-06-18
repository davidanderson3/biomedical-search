#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

LEVEL_ZERO_DOCUMENT_STEMS = [
    "scaling_chunk_001_gap_topics",
    "scaling_chunk_002_common_clinical",
    "scaling_chunk_003_abbreviation_language",
    "scaling_chunk_004_drug_safety_therapeutics",
    "scaling_chunk_005_diagnostics_procedures_devices",
]

FULL_VECTOR_STEMS = [
    *LEVEL_ZERO_DOCUMENT_STEMS,
    "pubmed_bulk_recent_baseline",
    "pubmed_bulk_recent_next2",
    "pubmed_bulk_recent_1331_1330",
    "pubmed_bulk_recent_1329_1328",
    "pubmed_bulk_recent_1327_1326",
    "pubmed_bulk_recent_1325_1324",
    "pubmed_bulk_recent_1323_1322",
    "pubmed_bulk_recent_1321_1320",
]

VECTOR_ONLY_STEMS = [
    stem for stem in FULL_VECTOR_STEMS if stem not in set(LEVEL_ZERO_DOCUMENT_STEMS)
]

SAFE_METADATA_KEYS = {
    "embedding_device",
    "embedding_model",
    "embedding_pooling",
    "embedding_provider",
    "evidence_count",
    "sources",
    "total_weight",
}


def sanitize_metadata(metadata: object) -> dict:
    if not isinstance(metadata, dict):
        return {
            "vector_content_category": "category-3-vector-only",
            "vector_metadata_policy": "no-text-no-labels-no-codes",
        }
    sanitized = {
        key: value
        for key, value in metadata.items()
        if key in SAFE_METADATA_KEYS
    }
    sanitized["vector_content_category"] = "category-3-vector-only"
    sanitized["vector_metadata_policy"] = "no-text-no-labels-no-codes"
    return sanitized


def sanitize_file(path: Path, *, dry_run: bool) -> dict:
    if not path.exists():
        return {"path": str(path), "exists": False, "records": 0, "changed": False}

    records = 0
    changed = False
    path = path.expanduser()
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with gzip.open(path, "rt", encoding="utf-8") as source, gzip.open(
            tmp_path,
            "wt",
            encoding="utf-8",
            compresslevel=6,
        ) as target:
            for line in source:
                if not line.strip():
                    continue
                payload = json.loads(line)
                sanitized = {
                    "doc_id": payload.get("doc_id"),
                    "cui": payload.get("cui"),
                    "view": payload.get("view"),
                    "text": "",
                    "metadata": sanitize_metadata(payload.get("metadata")),
                }
                if sanitized != payload:
                    changed = True
                target.write(json.dumps(sanitized, ensure_ascii=False, separators=(",", ":")))
                target.write("\n")
                records += 1
        if dry_run:
            tmp_path.unlink(missing_ok=True)
        else:
            os.replace(tmp_path, path)
        return {
            "path": str(path),
            "exists": True,
            "records": records,
            "changed": changed,
        }
    finally:
        tmp_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Strip readable labels/text/code-like metadata from compact vector shards "
            "that are distributed as vector-only evidence."
        )
    )
    parser.add_argument(
        "--build-dir",
        type=Path,
        default=ROOT / "build",
        help="Build directory containing compact_vectors/.",
    )
    parser.add_argument(
        "--stem",
        action="append",
        help="Vector stem to sanitize. Repeat as needed. Defaults to non-level-zero PubMed bulk stems.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    build_dir = args.build_dir.expanduser()
    stems = args.stem or VECTOR_ONLY_STEMS
    results = []
    for stem in stems:
        metadata_path = build_dir / "compact_vectors" / f"{stem}_sapbert_cls.metadata.jsonl.gz"
        results.append(sanitize_file(metadata_path, dry_run=args.dry_run))
    print(json.dumps({"dry_run": args.dry_run, "results": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
