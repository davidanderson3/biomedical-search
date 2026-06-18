#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qe_evidence_vectors.elastic_client import add_alias, create_index, load_bulk_files
from qe_evidence_vectors.elastic_export import (
    elastic_mapping,
    vector_dims,
    write_elastic_bulk_sharded,
    write_elastic_mapping,
)


def cmd_export_elastic(args: argparse.Namespace) -> int:
    dims = vector_dims(args.vectors)
    mapping = elastic_mapping(
        dims=dims,
        shards=args.shards,
        replicas=args.replicas,
    )
    write_elastic_mapping(args.out_mapping, mapping)
    count, parts = write_elastic_bulk_sharded(
        args.out_bulk,
        args.vectors,
        index=args.index,
        docs_per_file=args.bulk_docs_per_file,
    )
    print(
        json.dumps(
            {
                "vectors": str(args.vectors),
                "mapping": str(args.out_mapping),
                "bulk_base": str(args.out_bulk),
                "bulk_parts": [str(path) for path in parts],
                "documents": count,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def cmd_load_elastic(args: argparse.Namespace) -> int:
    if args.create_index:
        create_index(
            base_url=args.url,
            index=args.index,
            mapping_path=args.mapping,
            delete_existing=args.delete_existing,
        )
    items, errors = load_bulk_files(base_url=args.url, paths=args.bulk)
    if errors:
        raise SystemExit(f"Elasticsearch bulk load had {errors} failed item(s)")
    if args.delete_bulk_after_load:
        for raw_path in args.bulk:
            path = Path(raw_path)
            if path.exists():
                path.unlink()
            suffix = path.suffix or ".ndjson"
            stem = path.name[: -len(suffix)] if path.name.endswith(suffix) else path.name
            for part_path in path.parent.glob(f"{stem}.part-*{suffix}"):
                part_path.unlink()
    print(json.dumps({"items": items, "errors": errors}, indent=2, sort_keys=True))
    return 0


def cmd_alias_elastic(args: argparse.Namespace) -> int:
    result = add_alias(base_url=args.url, index=args.index, alias=args.alias)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Runtime Elasticsearch helpers for UMLS Search Docker.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export-elastic")
    export_parser.add_argument("--vectors", required=True, type=Path)
    export_parser.add_argument("--index", required=True)
    export_parser.add_argument("--out-mapping", required=True, type=Path)
    export_parser.add_argument("--out-bulk", required=True, type=Path)
    export_parser.add_argument("--bulk-docs-per-file", type=int, default=25000)
    export_parser.add_argument("--shards", type=int, default=1)
    export_parser.add_argument("--replicas", type=int, default=0)
    export_parser.set_defaults(func=cmd_export_elastic)

    load_parser = subparsers.add_parser("load-elastic")
    load_parser.add_argument("--url", required=True)
    load_parser.add_argument("--index", required=True)
    load_parser.add_argument("--mapping", required=True, type=Path)
    load_parser.add_argument("--bulk", action="append", required=True, type=Path)
    load_parser.add_argument("--create-index", action="store_true")
    load_parser.add_argument("--delete-existing", action="store_true")
    load_parser.add_argument("--delete-bulk-after-load", action="store_true")
    load_parser.set_defaults(func=cmd_load_elastic)

    alias_parser = subparsers.add_parser("alias-elastic")
    alias_parser.add_argument("--url", required=True)
    alias_parser.add_argument("--index", required=True)
    alias_parser.add_argument("--alias", required=True)
    alias_parser.set_defaults(func=cmd_alias_elastic)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
