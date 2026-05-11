from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Iterable

from .relation_index import read_doc_cuis
from .text import clean_text, normalized_key


SOURCE_PRIORITY = {
    "MSH": 0,
    "NCI": 1,
    "HPO": 2,
    "OMIM": 3,
    "MEDLINEPLUS": 4,
    "SNOMEDCT_US": 5,
    "MTH": 6,
}

DEFINITION_SEARCH_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "by",
    "drug",
    "drugs",
    "for",
    "from",
    "in",
    "is",
    "medication",
    "medications",
    "of",
    "or",
    "the",
    "to",
    "use",
    "used",
    "uses",
    "using",
    "with",
}

TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS concept_definitions (
    cui TEXT NOT NULL,
    source TEXT NOT NULL,
    definition TEXT NOT NULL,
    rank INTEGER NOT NULL
);
"""

INDEX_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_concept_definitions_cui_rank
ON concept_definitions(cui, rank);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS concept_definition_fts
USING fts5(
    cui UNINDEXED,
    source UNINDEXED,
    definition_rank UNINDEXED,
    definition,
    tokenize='unicode61 remove_diacritics 2'
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def _source_sort_key(source: str) -> tuple[int, str]:
    return (SOURCE_PRIORITY.get(str(source or ""), 99), str(source or ""))


def _search_tokens(query: str, *, max_tokens: int = 8) -> list[str]:
    tokens = []
    seen = set()
    for token in normalized_key(query).split():
        if token.endswith("s") and len(token) > 4 and not token.endswith("ss"):
            token = token[:-1]
        if len(token) < 3 or token in DEFINITION_SEARCH_STOPWORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
        if len(tokens) >= max_tokens:
            break
    return tokens


def _fts_match_query(query: str) -> str:
    tokens = _search_tokens(query)
    if len(tokens) < 2:
        return ""
    return " ".join(f"{token}*" for token in tokens)


def _trim_bucket(bucket: list[tuple[tuple[int, str], str, str]]) -> list[tuple[tuple[int, str], str, str]]:
    return sorted(bucket, key=lambda item: (item[0], len(item[2]), item[2].lower()))


def build_definition_index(
    *,
    mrdef_path: str | Path,
    out_path: str | Path,
    doc_paths: Iterable[str | Path] = (),
    source_cuis: set[str] | None = None,
    max_definitions_per_cui: int = 3,
    include_suppressed: bool = False,
    replace: bool = True,
) -> dict[str, int]:
    cuis = set(source_cuis or set())
    cuis.update(read_doc_cuis(doc_paths))
    buckets: dict[str, list[tuple[tuple[int, str], str, str]]] = {}
    seen_definitions: dict[str, set[str]] = {}
    scanned = 0
    accepted = 0
    with Path(mrdef_path).expanduser().open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("|")
            if len(fields) < 7:
                continue
            scanned += 1
            cui = fields[0].strip()
            if not cui or (cuis and cui not in cuis):
                continue
            suppress = fields[6].strip()
            if not include_suppressed and suppress != "N":
                continue
            definition = clean_text(fields[5])
            if not definition:
                continue
            normalized_definition = normalized_key(definition)
            if not normalized_definition:
                continue
            cui_seen = seen_definitions.setdefault(cui, set())
            if normalized_definition in cui_seen:
                continue
            cui_seen.add(normalized_definition)
            source = fields[4].strip()
            bucket = buckets.setdefault(cui, [])
            bucket.append((_source_sort_key(source), source, definition))
            accepted += 1
            if len(bucket) > max_definitions_per_cui * 5:
                buckets[cui] = _trim_bucket(bucket)[: max_definitions_per_cui * 3]

    rows = []
    for cui, bucket in buckets.items():
        for rank, (_, source, definition) in enumerate(
            _trim_bucket(bucket)[:max_definitions_per_cui],
            start=1,
        ):
            rows.append((cui, source, definition, rank))

    conn = connect(out_path)
    if replace:
        conn.execute("DROP TABLE IF EXISTS concept_definition_fts")
        conn.execute("DROP TABLE IF EXISTS concept_definitions")
    conn.executescript(TABLE_SCHEMA)
    conn.executescript(FTS_SCHEMA)
    conn.executemany(
        """
        INSERT INTO concept_definitions(cui, source, definition, rank)
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )
    conn.executemany(
        """
        INSERT INTO concept_definition_fts(cui, source, definition, definition_rank)
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )
    conn.executescript(INDEX_SCHEMA)
    conn.commit()
    conn.close()
    return {
        "source_cuis": len(cuis),
        "cuis_with_definitions": len(buckets),
        "definitions_seen": scanned,
        "definitions_accepted": accepted,
        "definitions_indexed": len(rows),
    }


class DefinitionIndex:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self._local = threading.local()
        self.lookup_cache: dict[tuple[str, int], list[dict]] = {}
        self.search_cache: dict[tuple[str, int], list[dict]] = {}
        self._definition_count: int | None = None
        self._cui_count: int | None = None

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

    def definition_count(self) -> int:
        if self._definition_count is None:
            row = self.connection().execute(
                "SELECT COUNT(*) AS count FROM concept_definitions"
            ).fetchone()
            self._definition_count = int(row["count"] or 0)
        return self._definition_count

    def cui_count(self) -> int:
        if self._cui_count is None:
            row = self.connection().execute(
                "SELECT COUNT(DISTINCT cui) AS count FROM concept_definitions"
            ).fetchone()
            self._cui_count = int(row["count"] or 0)
        return self._cui_count

    def lookup(self, cui: str, *, limit: int = 3) -> list[dict]:
        cui = str(cui or "").strip().upper()
        key = (cui, limit)
        cached = self.lookup_cache.get(key)
        if cached is not None:
            return [dict(item) for item in cached]
        rows = self.connection().execute(
            """
            SELECT cui, source, definition, rank
            FROM concept_definitions
            WHERE cui = ?
            ORDER BY rank ASC
            LIMIT ?
            """,
            (cui, limit),
        )
        results = [
            {
                "cui": row["cui"],
                "source": row["source"],
                "definition": row["definition"],
                "rank": int(row["rank"] or 0),
            }
            for row in rows
        ]
        self.lookup_cache[key] = results
        return [dict(item) for item in results]

    def search(self, query: str, *, limit: int = 50) -> list[dict]:
        match_query = _fts_match_query(query)
        if not match_query:
            return []
        key = (match_query, limit)
        cached = self.search_cache.get(key)
        if cached is not None:
            return [dict(item) for item in cached]
        try:
            rows = self.connection().execute(
                """
                SELECT cui, source, definition, CAST(definition_rank AS INTEGER) AS rank,
                       bm25(concept_definition_fts) AS bm25
                FROM concept_definition_fts
                WHERE concept_definition_fts MATCH ?
                ORDER BY bm25(concept_definition_fts), definition_rank ASC
                LIMIT ?
                """,
                (match_query, max(limit * 4, limit + 25)),
            )
        except sqlite3.OperationalError:
            return []
        best_by_cui: dict[str, dict] = {}
        for row in rows:
            cui = str(row["cui"] or "")
            if not cui:
                continue
            rank = int(row["rank"] or 0)
            bm25 = float(row["bm25"] or 0.0)
            item = {
                "cui": cui,
                "source": row["source"],
                "definition": row["definition"],
                "rank": rank,
                "score": round(max(0.72, 0.90 - (0.015 * max(rank - 1, 0))), 6),
                "bm25": bm25,
                "match_query": match_query,
            }
            current = best_by_cui.get(cui)
            if current is None or (bm25, rank) < (float(current["bm25"]), int(current["rank"])):
                best_by_cui[cui] = item
        results = sorted(
            best_by_cui.values(),
            key=lambda item: (float(item["bm25"]), int(item["rank"]), str(item["cui"])),
        )[:limit]
        self.search_cache[key] = [dict(item) for item in results]
        return [dict(item) for item in results]
