from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from .schema import VectorRecord
from .search import iter_vectors


def elastic_mapping(
    *,
    dims: int,
    vector_field: str = "vector",
    similarity: str = "cosine",
    index_vectors: bool = True,
    shards: int = 1,
    replicas: int = 0,
) -> dict:
    return {
        "settings": {
            "number_of_shards": shards,
            "number_of_replicas": replicas,
        },
        "mappings": {
            "properties": {
                "doc_id": {"type": "keyword"},
                "cui": {"type": "keyword"},
                "view": {"type": "keyword"},
                "sources": {"type": "keyword"},
                "labels": {
                    "type": "text",
                    "fields": {"keyword": {"type": "keyword", "ignore_above": 512}},
                },
                "text": {"type": "text"},
                "evidence_count": {"type": "integer"},
                "total_weight": {"type": "float"},
                "embedding_provider": {"type": "keyword"},
                "embedding_model": {"type": "keyword"},
                vector_field: {
                    "type": "dense_vector",
                    "dims": dims,
                    "similarity": similarity,
                    "index": index_vectors,
                },
            }
        },
    }


def vector_source(record: VectorRecord, *, vector_field: str = "vector") -> dict:
    document = record.metadata.get("document", {})
    sources = record.metadata.get("sources", document.get("sources", []))
    labels = record.metadata.get("labels", document.get("labels", []))
    evidence_count = record.metadata.get("evidence_count", document.get("evidence_count"))
    return {
        "doc_id": record.doc_id,
        "cui": record.cui,
        "view": record.view,
        "sources": sources,
        "labels": labels,
        "text": record.text,
        "evidence_count": evidence_count,
        "total_weight": record.metadata.get("total_weight"),
        "embedding_provider": record.metadata.get("embedding_provider"),
        "embedding_model": record.metadata.get("embedding_model"),
        "metadata": {
            key: value
            for key, value in record.metadata.items()
            if key not in {"document"}
        },
        vector_field: record.vector,
    }


def iter_elastic_bulk_lines(
    vectors_path: str | Path,
    *,
    index: str,
    vector_field: str = "vector",
    op_type: str = "index",
) -> Iterator[str]:
    if op_type not in {"index", "create"}:
        raise ValueError("op_type must be 'index' or 'create'")
    for record in iter_vectors(vectors_path):
        action = {op_type: {"_index": index, "_id": record.doc_id}}
        yield json.dumps(action, ensure_ascii=False, separators=(",", ":"))
        yield json.dumps(
            vector_source(record, vector_field=vector_field),
            ensure_ascii=False,
            separators=(",", ":"),
        )


def write_elastic_mapping(path: str | Path, mapping: dict) -> None:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_elastic_bulk(
    path: str | Path,
    vectors_path: str | Path,
    *,
    index: str,
    vector_field: str = "vector",
    op_type: str = "index",
) -> int:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for line_number, line in enumerate(
            iter_elastic_bulk_lines(
                vectors_path,
                index=index,
                vector_field=vector_field,
                op_type=op_type,
            ),
            start=1,
        ):
            handle.write(line)
            handle.write("\n")
            if line_number % 2 == 0:
                count += 1
    return count


def _bulk_part_path(path: Path, part_number: int) -> Path:
    suffix = path.suffix or ".ndjson"
    stem = path.name[: -len(suffix)] if path.name.endswith(suffix) else path.name
    return path.with_name(f"{stem}.part-{part_number:06d}{suffix}")


def write_elastic_bulk_sharded(
    path: str | Path,
    vectors_path: str | Path,
    *,
    index: str,
    docs_per_file: int,
    vector_field: str = "vector",
    op_type: str = "index",
) -> tuple[int, list[Path]]:
    if docs_per_file <= 0:
        raise ValueError("docs_per_file must be positive")
    base_path = Path(path).expanduser()
    base_path.parent.mkdir(parents=True, exist_ok=True)
    total_docs = 0
    part_docs = 0
    part_number = 1
    output_paths: list[Path] = []
    handle = None
    try:
        for line_number, line in enumerate(
            iter_elastic_bulk_lines(
                vectors_path,
                index=index,
                vector_field=vector_field,
                op_type=op_type,
            ),
            start=1,
        ):
            if handle is None:
                part_path = _bulk_part_path(base_path, part_number)
                output_paths.append(part_path)
                handle = part_path.open("w", encoding="utf-8")
            handle.write(line)
            handle.write("\n")
            if line_number % 2 == 0:
                total_docs += 1
                part_docs += 1
                if part_docs >= docs_per_file:
                    handle.close()
                    handle = None
                    part_docs = 0
                    part_number += 1
    finally:
        if handle is not None:
            handle.close()
    return total_docs, output_paths


def vector_dims(path: str | Path) -> int:
    for record in iter_vectors(path):
        return len(record.vector)
    raise ValueError(f"{path} contains no vectors")
