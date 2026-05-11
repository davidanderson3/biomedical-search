from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

from .documents import document_text, evidence_view
from .evidence import iter_filtered_evidence_files
from .mrconso_labels import collect_labels
from .schema import ConceptDocument, write_jsonl
from .text import normalized_key


TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence (
    cui TEXT NOT NULL,
    view TEXT NOT NULL,
    norm_text TEXT NOT NULL,
    text TEXT NOT NULL,
    source TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    weight REAL NOT NULL
);
"""

INDEX_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_evidence_group ON evidence(cui, view);
CREATE INDEX IF NOT EXISTS idx_evidence_group_norm ON evidence(cui, view, norm_text);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(Path(path).expanduser()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-200000")
    return conn


def init_store(conn: sqlite3.Connection, *, replace: bool = False) -> None:
    if replace:
        conn.execute("DROP TABLE IF EXISTS evidence")
    conn.executescript(TABLE_SCHEMA)
    conn.commit()


def create_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript(INDEX_SCHEMA)
    conn.commit()


def load_evidence_store(
    conn: sqlite3.Connection,
    evidence_paths: list[str | Path],
    *,
    include_source: set[str] | None = None,
    exclude_source: set[str] | None = None,
    include_evidence_type: set[str] | None = None,
    exclude_evidence_type: set[str] | None = None,
    batch_size: int = 25_000,
) -> int:
    sql = """
        INSERT INTO evidence(cui, view, norm_text, text, source, evidence_type, evidence_id, weight)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    count = 0
    batch = []
    records = iter_filtered_evidence_files(
        evidence_paths,
        include_source=include_source,
        exclude_source=exclude_source,
        include_evidence_type=include_evidence_type,
        exclude_evidence_type=exclude_evidence_type,
    )
    for record in records:
        batch.append(
            (
                record.cui,
                evidence_view(record.evidence_type),
                normalized_key(record.text),
                record.text,
                record.source,
                record.evidence_type,
                record.evidence_id,
                record.weight,
            )
        )
        if len(batch) >= batch_size:
            conn.executemany(sql, batch)
            conn.commit()
            count += len(batch)
            batch.clear()
    if batch:
        conn.executemany(sql, batch)
        conn.commit()
        count += len(batch)
    return count


def _group_rows(conn: sqlite3.Connection) -> Iterator[sqlite3.Row]:
    yield from conn.execute(
        """
        SELECT cui, view, COUNT(*) AS evidence_count, SUM(weight) AS total_weight
        FROM evidence
        GROUP BY cui, view
        ORDER BY cui, view
        """
    )


def _top_rows(
    conn: sqlite3.Connection,
    *,
    cui: str,
    view: str,
    max_items: int,
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT text, source, weight
            FROM (
                SELECT
                    text,
                    source,
                    weight,
                    evidence_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY norm_text
                        ORDER BY weight DESC, text ASC, evidence_id ASC
                    ) AS rn
                FROM evidence
                WHERE cui = ? AND view = ?
            )
            WHERE rn = 1
            ORDER BY weight DESC, text ASC
            LIMIT ?
            """,
            (cui, view, max_items),
        )
    )


def iter_sqlite_documents(
    conn: sqlite3.Connection,
    *,
    mrconso_path: str | Path | None = None,
    max_labels: int = 8,
    max_items_per_doc: int = 100,
) -> Iterator[ConceptDocument]:
    cuis = {row["cui"] for row in conn.execute("SELECT DISTINCT cui FROM evidence")}
    labels = collect_labels(mrconso_path, cuis, max_labels=max_labels) if mrconso_path else {}

    for group in _group_rows(conn):
        cui = group["cui"]
        view = group["view"]
        top_rows = _top_rows(conn, cui=cui, view=view, max_items=max_items_per_doc)
        doc_labels = labels.get(cui, [])
        pseudo_records = [
            SimpleNamespace(text=row["text"], source=row["source"], weight=float(row["weight"]))
            for row in top_rows
        ]
        sources = sorted({row["source"] for row in top_rows if row["source"]})
        yield ConceptDocument(
            doc_id=f"{cui}:{view}",
            cui=cui,
            view=view,
            text=document_text(cui, view, doc_labels, pseudo_records),  # type: ignore[arg-type]
            evidence_count=int(group["evidence_count"]),
            sources=sources,
            labels=doc_labels,
            metadata={
                "document_builder": "sqlite",
                "max_items_per_doc": max_items_per_doc,
                "total_weight": float(group["total_weight"] or 0),
            },
        )


def build_documents_sqlite(
    *,
    evidence_paths: list[str | Path],
    out_path: str | Path,
    sqlite_path: str | Path,
    mrconso_path: str | Path | None = None,
    max_labels: int = 8,
    max_items_per_doc: int = 100,
    include_source: set[str] | None = None,
    exclude_source: set[str] | None = None,
    include_evidence_type: set[str] | None = None,
    exclude_evidence_type: set[str] | None = None,
    replace: bool = False,
) -> tuple[int, int]:
    sqlite_path = Path(sqlite_path).expanduser()
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(sqlite_path)
    try:
        init_store(conn, replace=replace)
        evidence_count = load_evidence_store(
            conn,
            evidence_paths,
            include_source=include_source,
            exclude_source=exclude_source,
            include_evidence_type=include_evidence_type,
            exclude_evidence_type=exclude_evidence_type,
        )
        create_indexes(conn)
        doc_count = write_jsonl(
            out_path,
            iter_sqlite_documents(
                conn,
                mrconso_path=mrconso_path,
                max_labels=max_labels,
                max_items_per_doc=max_items_per_doc,
            ),
        )
        return evidence_count, doc_count
    finally:
        conn.close()
