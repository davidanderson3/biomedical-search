from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .mrconso_labels import collect_labels
from .schema import iter_jsonl
from .universal_relationship import attach_universal_edge


TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS related_concepts (
    source_cui TEXT NOT NULL,
    target_cui TEXT NOT NULL,
    relation TEXT NOT NULL,
    rela TEXT NOT NULL,
    sab TEXT NOT NULL,
    direction TEXT NOT NULL,
    label TEXT NOT NULL,
    rank INTEGER NOT NULL
);
"""

INDEX_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_related_source_rank
ON related_concepts(source_cui, rank);

CREATE INDEX IF NOT EXISTS idx_related_target_rank
ON related_concepts(target_cui, rank);
"""

REL_PRIORITY = {
    "PAR": 0,
    "CHD": 0,
    "RB": 1,
    "RN": 1,
    "RO": 2,
    "RQ": 3,
    "SY": 4,
}

SAB_PRIORITY = {
    "MTH": 0,
    "MSH": 1,
    "SNOMEDCT_US": 2,
    "NCI": 3,
    "RXNORM": 4,
}


@dataclass(frozen=True)
class RelationCandidate:
    source_cui: str
    target_cui: str
    relation: str
    rela: str
    sab: str
    direction: str


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def read_doc_cuis(paths: Iterable[str | Path]) -> set[str]:
    _, cuis = read_doc_labels(paths)
    return cuis


def read_doc_labels(paths: Iterable[str | Path]) -> tuple[dict[str, str], set[str]]:
    labels: dict[str, str] = {}
    cuis: set[str] = set()
    for path in paths:
        path = Path(path).expanduser()
        if not path.exists():
            continue
        for payload in iter_jsonl(path):
            cui = str(payload.get("cui") or "").strip()
            if cui:
                cuis.add(cui)
                doc_labels = payload.get("labels") or []
                if cui not in labels and doc_labels:
                    label = str(doc_labels[0]).strip()
                    if label:
                        labels[cui] = label
    return labels, cuis


def relation_sort_key(candidate: RelationCandidate) -> tuple[int, int, str, str, str]:
    return (
        REL_PRIORITY.get(candidate.relation, 50),
        SAB_PRIORITY.get(candidate.sab, 50),
        candidate.rela or candidate.relation,
        candidate.target_cui,
        candidate.direction,
    )


def display_label(label: str) -> str:
    if ";" not in label:
        return label
    parts = [part.strip() for part in label.split(";") if part.strip()]
    if len(parts) != 2:
        return label
    return f"{parts[1]} {parts[0]}"


def _maybe_add_candidate(
    buckets: dict[str, dict[str, RelationCandidate]],
    candidate: RelationCandidate,
    *,
    max_relations_per_cui: int,
) -> None:
    bucket = buckets.setdefault(candidate.source_cui, {})
    current = bucket.get(candidate.target_cui)
    if current is None or relation_sort_key(candidate) < relation_sort_key(current):
        bucket[candidate.target_cui] = candidate
    if len(bucket) > max_relations_per_cui * 8:
        kept = sorted(bucket.values(), key=relation_sort_key)[: max_relations_per_cui * 4]
        buckets[candidate.source_cui] = {item.target_cui: item for item in kept}


def collect_relation_candidates(
    *,
    mrrel_path: str | Path,
    source_cuis: set[str],
    max_relations_per_cui: int = 16,
    include_inverse: bool = True,
    include_suppressed: bool = False,
) -> dict[str, list[RelationCandidate]]:
    buckets: dict[str, dict[str, RelationCandidate]] = {}
    with Path(mrrel_path).expanduser().open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("|")
            if len(fields) < 15:
                continue
            cui1, rel, cui2, rela, sab, suppress = (
                fields[0],
                fields[3],
                fields[4],
                fields[7],
                fields[10],
                fields[14],
            )
            if cui1 == cui2:
                continue
            if not include_suppressed and suppress == "Y":
                continue
            if cui1 in source_cuis:
                _maybe_add_candidate(
                    buckets,
                    RelationCandidate(cui1, cui2, rel, rela, sab, "outgoing"),
                    max_relations_per_cui=max_relations_per_cui,
                )
            if include_inverse and cui2 in source_cuis:
                _maybe_add_candidate(
                    buckets,
                    RelationCandidate(cui2, cui1, rel, rela, sab, "incoming"),
                    max_relations_per_cui=max_relations_per_cui,
                )
    return {
        source_cui: sorted(bucket.values(), key=relation_sort_key)[:max_relations_per_cui]
        for source_cui, bucket in buckets.items()
    }


def build_relation_index(
    *,
    mrrel_path: str | Path,
    mrconso_path: str | Path,
    out_path: str | Path,
    doc_paths: Iterable[str | Path] = (),
    source_cuis: set[str] | None = None,
    max_relations_per_cui: int = 16,
    include_inverse: bool = True,
    include_suppressed: bool = False,
    replace: bool = True,
) -> dict[str, int]:
    doc_labels, doc_cuis = read_doc_labels(doc_paths)
    cuis = set(source_cuis or set())
    cuis.update(doc_cuis)
    relation_candidates = collect_relation_candidates(
        mrrel_path=mrrel_path,
        source_cuis=cuis,
        max_relations_per_cui=max_relations_per_cui,
        include_inverse=include_inverse,
        include_suppressed=include_suppressed,
    )
    target_cuis = {
        candidate.target_cui
        for candidates in relation_candidates.values()
        for candidate in candidates
    }
    missing_label_cuis = target_cuis - set(doc_labels)
    mrconso_labels = collect_labels(mrconso_path, missing_label_cuis, max_labels=1)
    conn = connect(out_path)
    if replace:
        conn.execute("DROP TABLE IF EXISTS related_concepts")
    conn.executescript(TABLE_SCHEMA)
    batch = []
    for source_cui, candidates in relation_candidates.items():
        for rank, candidate in enumerate(candidates, start=1):
            label = doc_labels.get(candidate.target_cui)
            if not label:
                label = (mrconso_labels.get(candidate.target_cui) or [candidate.target_cui])[0]
            batch.append(
                (
                    source_cui,
                    candidate.target_cui,
                    candidate.relation,
                    candidate.rela,
                    candidate.sab,
                    candidate.direction,
                    label,
                    rank,
                )
            )
    conn.executemany(
        """
        INSERT INTO related_concepts(
            source_cui, target_cui, relation, rela, sab, direction, label, rank
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        batch,
    )
    conn.executescript(INDEX_SCHEMA)
    conn.commit()
    conn.close()
    return {
        "source_cuis": len(cuis),
        "sources_with_relations": len(relation_candidates),
        "target_cuis": len(target_cuis),
        "relations": len(batch),
    }


class RelationIndex:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self._local = threading.local()
        self.cache: dict[tuple[str, int], list[dict]] = {}

    def connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = connect(self.path)
            self._local.conn = conn
        return conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def source_count(self) -> int:
        row = self.connection().execute(
            "SELECT COUNT(DISTINCT source_cui) AS count FROM related_concepts"
        ).fetchone()
        return int(row["count"] or 0)

    def relation_count(self) -> int:
        row = self.connection().execute("SELECT COUNT(*) AS count FROM related_concepts").fetchone()
        return int(row["count"] or 0)

    def lookup(self, cui: str, *, limit: int = 8) -> list[dict]:
        key = (cui, limit)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        rows = self.connection().execute(
            """
            SELECT target_cui, relation, rela, sab, direction, label
            FROM related_concepts
            WHERE source_cui = ?
            ORDER BY rank ASC
            LIMIT ?
            """,
            (cui, limit),
        )
        results = [
            attach_universal_edge(
                {
                    "source_cui": cui,
                    "target_cui": row["target_cui"],
                    "cui": row["target_cui"],
                    "relation": row["relation"],
                    "rela": row["rela"],
                    "source": row["sab"],
                    "direction": row["direction"],
                    "label": display_label(str(row["label"])),
                },
                subject_cui=cui,
                object_cui=row["target_cui"],
            )
            for row in rows
        ]
        self.cache[key] = results
        return results

    def lookup_incoming(self, cui: str, *, limit: int = 16) -> list[dict]:
        key = (f"incoming:{cui}", limit)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        rows = self.connection().execute(
            """
            SELECT source_cui, target_cui, relation, rela, sab, direction, label, rank
            FROM related_concepts
            WHERE target_cui = ?
            ORDER BY rank ASC
            LIMIT ?
            """,
            (cui, limit),
        )
        results = [
            attach_universal_edge(
                {
                    "source_cui": row["source_cui"],
                    "target_cui": row["target_cui"],
                    "relation": row["relation"],
                    "rela": row["rela"],
                    "source": row["sab"],
                    "direction": row["direction"],
                    "label": display_label(str(row["label"])),
                    "rank": int(row["rank"] or 0),
                },
                subject_cui=row["source_cui"],
                object_cui=row["target_cui"],
            )
            for row in rows
        ]
        self.cache[key] = results
        return results
