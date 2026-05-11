from __future__ import annotations

import json
import sys
from array import array
from pathlib import Path
from typing import Iterator

from .schema import VectorRecord
from .search import iter_vectors


def compact_paths(out_prefix: str | Path) -> dict[str, Path]:
    prefix = Path(out_prefix).expanduser()
    return {
        "manifest": prefix.with_suffix(prefix.suffix + ".manifest.json") if prefix.suffix else prefix.with_name(prefix.name + ".manifest.json"),
        "metadata": prefix.with_suffix(prefix.suffix + ".metadata.jsonl") if prefix.suffix else prefix.with_name(prefix.name + ".metadata.jsonl"),
        "vectors": prefix.with_suffix(prefix.suffix + ".vectors.f32") if prefix.suffix else prefix.with_name(prefix.name + ".vectors.f32"),
    }


def _little_endian_float_array(values: list[float]) -> array:
    floats = array("f", values)
    if sys.byteorder != "little":
        floats.byteswap()
    return floats


def write_compact_vectors(
    *,
    vectors_path: str | Path,
    out_prefix: str | Path,
) -> dict:
    paths = compact_paths(out_prefix)
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    dims: int | None = None
    with paths["vectors"].open("wb") as vector_handle, paths["metadata"].open("w", encoding="utf-8") as metadata_handle:
        for record in iter_vectors(vectors_path):
            if dims is None:
                dims = len(record.vector)
            elif len(record.vector) != dims:
                raise ValueError(
                    f"inconsistent vector dimensions in {vectors_path}: expected {dims}, got {len(record.vector)}"
                )
            vector_handle.write(_little_endian_float_array(record.vector).tobytes())
            metadata_handle.write(
                json.dumps(
                    {
                        "doc_id": record.doc_id,
                        "cui": record.cui,
                        "view": record.view,
                        "text": record.text,
                        "metadata": record.metadata,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
            metadata_handle.write("\n")
            count += 1

    if dims is None:
        raise ValueError(f"{vectors_path} contains no vectors")
    manifest = {
        "format": "qe-compact-vectors-v1",
        "source": str(Path(vectors_path).expanduser()),
        "count": count,
        "dims": dims,
        "dtype": "float32-le",
        "vectors": str(paths["vectors"]),
        "metadata": str(paths["metadata"]),
    }
    paths["manifest"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def iter_compact_vectors(manifest_path: str | Path) -> Iterator[VectorRecord]:
    manifest = json.loads(Path(manifest_path).expanduser().read_text(encoding="utf-8"))
    dims = int(manifest["dims"])
    width = dims * array("f").itemsize
    vectors_path = Path(manifest["vectors"]).expanduser()
    metadata_path = Path(manifest["metadata"]).expanduser()

    with vectors_path.open("rb") as vector_handle, metadata_path.open("r", encoding="utf-8") as metadata_handle:
        for line_number, line in enumerate(metadata_handle, start=1):
            payload = json.loads(line)
            raw = vector_handle.read(width)
            if len(raw) != width:
                raise ValueError(f"{vectors_path}: missing vector bytes for metadata line {line_number}")
            vector = array("f")
            vector.frombytes(raw)
            if sys.byteorder != "little":
                vector.byteswap()
            yield VectorRecord(
                doc_id=payload["doc_id"],
                cui=payload["cui"],
                view=payload["view"],
                vector=list(vector),
                text=payload.get("text", ""),
                metadata=payload.get("metadata", {}),
            )
        trailing = vector_handle.read(1)
        if trailing:
            raise ValueError(f"{vectors_path}: vector bytes remain after reading metadata")
