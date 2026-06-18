from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from .embeddings import Embedder
from .schema import VectorRecord, iter_jsonl


@dataclass(frozen=True)
class SearchHit:
    cui: str
    score: float
    doc_id: str
    view: str
    text: str


def load_vectors(path: str | Path) -> list[VectorRecord]:
    return list(iter_vectors(path))


def iter_vectors(path: str | Path):
    path = Path(path)
    if path.suffix == ".json" and path.name.endswith(".manifest.json"):
        from .compact_vectors import iter_compact_vectors

        yield from iter_compact_vectors(path)
        return

    for payload in iter_jsonl(path):
        yield VectorRecord(
            doc_id=payload["doc_id"],
            cui=payload["cui"],
            view=payload["view"],
            vector=[float(value) for value in payload["vector"]],
            text=payload.get("text", ""),
            metadata=payload.get("metadata", {}),
        )


def dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector
    return [value / norm for value in vector]


def search_vectors(
    records,
    query: str,
    embedder: Embedder,
    *,
    top_k: int = 10,
) -> list[SearchHit]:
    query_vector = l2_normalize(embedder.embed([query])[0])
    best_by_cui: dict[str, SearchHit] = {}
    for record in records:
        score = dot(query_vector, l2_normalize(record.vector))
        current = best_by_cui.get(record.cui)
        if current is None or score > current.score:
            best_by_cui[record.cui] = SearchHit(
                cui=record.cui,
                score=score,
                doc_id=record.doc_id,
                view=record.view,
                text=record.text,
            )
    return sorted(best_by_cui.values(), key=lambda hit: hit.score, reverse=True)[:top_k]


def search_vector_file(
    path: str | Path,
    query: str,
    embedder: Embedder,
    *,
    top_k: int = 10,
) -> list[SearchHit]:
    return search_vectors(iter_vectors(path), query, embedder, top_k=top_k)
