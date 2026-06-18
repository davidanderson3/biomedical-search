from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from .generic_filters import is_blocked_generic_concept
from .lexical_normalization import (
    lexical_normalized_key,
    lexical_normalized_tokens,
    lexical_variant_keys,
)
from .semantic_profiles import resolve_profiles
from .text import normalized_key


TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS labels (
    norm TEXT NOT NULL,
    cui TEXT NOT NULL,
    label TEXT NOT NULL,
    sab TEXT NOT NULL,
    tty TEXT NOT NULL,
    ispref TEXT NOT NULL,
    suppress TEXT NOT NULL
);
"""

INDEX_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_labels_norm ON labels(norm);
CREATE INDEX IF NOT EXISTS idx_labels_cui ON labels(cui);
"""


BLOCKED_SINGLE_TOKEN_LABELS = {
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "also",
    "and",
    "any",
    "are",
    "because",
    "been",
    "before",
    "being",
    "between",
    "both",
    "but",
    "can",
    "could",
    "did",
    "does",
    "doing",
    "during",
    "each",
    "few",
    "for",
    "from",
    "had",
    "has",
    "have",
    "having",
    "here",
    "how",
    "into",
    "issue",
    "its",
    "left",
    "may",
    "might",
    "more",
    "most",
    "new",
    "nor",
    "not",
    "off",
    "once",
    "only",
    "other",
    "our",
    "out",
    "over",
    "own",
    "same",
    "she",
    "should",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "too",
    "under",
    "until",
    "very",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "will",
    "with",
    "would",
}


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(Path(path).expanduser()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-200000")
    return conn


def create_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript(INDEX_SCHEMA)
    conn.commit()


def load_semantic_type_filter(
    mrsty_path: str | Path | None,
    semantic_types: Iterable[str] | None,
) -> set[str] | None:
    if not mrsty_path or not semantic_types:
        return None
    wanted = {value.strip().lower() for value in semantic_types if value.strip()}
    cuis: set[str] = set()
    with Path(mrsty_path).expanduser().open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("|")
            if len(fields) < 4:
                continue
            cui, tui, _, sty = fields[:4]
            if tui.lower() in wanted or sty.lower() in wanted:
                cuis.add(cui)
    return cuis


def _valid_label(
    label: str,
    *,
    min_chars: int,
    min_tokens: int,
    max_tokens: int,
    allow_short_labels: bool = False,
) -> bool:
    norm = normalized_key(label)
    if len(norm) < min_chars:
        return False
    if not any(char.isalpha() for char in norm):
        return False
    tokens = norm.split()
    if not (min_tokens <= len(tokens) <= max_tokens):
        return False
    if len(tokens) == 1 and not allow_short_labels:
        token = tokens[0]
        if token in BLOCKED_SINGLE_TOKEN_LABELS:
            return False
        if len(token) < max(4, min_chars):
            return False
    return True


def label_index_norms(label: str, *, include_lexical_variants: bool = True) -> list[str]:
    if not include_lexical_variants:
        norm = normalized_key(label)
        return [norm] if norm else []
    return lexical_variant_keys(label)


def build_label_index(
    *,
    mrconso_path: str | Path,
    out_path: str | Path,
    mrsty_path: str | Path | None = None,
    semantic_types: Iterable[str] | None = None,
    semantic_profiles: Iterable[str] | None = None,
    language: str = "ENG",
    include_suppressed: bool = False,
    include_generic: bool = False,
    min_chars: int = 3,
    min_tokens: int = 1,
    max_tokens: int = 8,
    allow_short_labels: bool = False,
    include_lexical_variants: bool = True,
    replace: bool = False,
) -> int:
    profile_types = resolve_profiles(list(semantic_profiles or []))
    if profile_types is None:
        semantic_type_filter = None
    else:
        semantic_type_filter = set(profile_types)
        semantic_type_filter.update(semantic_types or [])
    allowed_cuis = load_semantic_type_filter(mrsty_path, semantic_type_filter)
    out_path = Path(out_path).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(out_path)
    if replace:
        conn.execute("DROP TABLE IF EXISTS labels")
    conn.executescript(TABLE_SCHEMA)
    sql = """
        INSERT INTO labels(norm, cui, label, sab, tty, ispref, suppress)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    batch = []
    count = 0
    with Path(mrconso_path).expanduser().open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("|")
            if len(fields) < 18:
                continue
            cui = fields[0]
            if fields[1] != language:
                continue
            if allowed_cuis is not None and cui not in allowed_cuis:
                continue
            if not include_suppressed and fields[16] != "N":
                continue
            label = fields[14].strip()
            if not include_generic and is_blocked_generic_concept(cui, label):
                continue
            if not _valid_label(
                label,
                min_chars=min_chars,
                min_tokens=min_tokens,
                max_tokens=max_tokens,
                allow_short_labels=allow_short_labels,
            ):
                continue
            norms = label_index_norms(label, include_lexical_variants=include_lexical_variants)
            for norm in norms:
                batch.append(
                    (
                        norm,
                        cui,
                        label,
                        fields[11],
                        fields[12],
                        fields[6],
                        fields[16],
                    )
                )
            count += 1
            if len(batch) >= 50_000:
                conn.executemany(sql, batch)
                conn.commit()
                batch.clear()
    if batch:
        conn.executemany(sql, batch)
        conn.commit()
    create_indexes(conn)
    conn.close()
    return count


def build_label_index_from_code_index(
    *,
    source_path: str | Path,
    out_path: str | Path,
    include_generic: bool = False,
    min_chars: int = 3,
    min_tokens: int = 1,
    max_tokens: int = 8,
    allow_short_labels: bool = False,
    include_lexical_variants: bool = True,
    replace: bool = False,
    batch_size: int = 50_000,
) -> int:
    source_path = Path(source_path).expanduser()
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    out_path = Path(out_path).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_conn = connect(out_path)
    if replace:
        out_conn.execute("DROP TABLE IF EXISTS labels")
    out_conn.executescript(TABLE_SCHEMA)
    source_conn = sqlite3.connect(str(source_path))
    source_conn.row_factory = sqlite3.Row
    source_conn.execute("PRAGMA temp_store=MEMORY")
    insert_sql = """
        INSERT INTO labels(norm, cui, label, sab, tty, ispref, suppress)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    batch = []
    count = 0
    try:
        rows = source_conn.execute(
            """
            SELECT cui, label, sab, tty, ispref, suppress
            FROM code_mappings
            WHERE label <> ''
            """
        )
        for row in rows:
            cui = str(row["cui"] or "")
            label = str(row["label"] or "").strip()
            if not include_generic and is_blocked_generic_concept(cui, label):
                continue
            if not _valid_label(
                label,
                min_chars=min_chars,
                min_tokens=min_tokens,
                max_tokens=max_tokens,
                allow_short_labels=allow_short_labels,
            ):
                continue
            norms = label_index_norms(label, include_lexical_variants=include_lexical_variants)
            for norm in norms:
                batch.append(
                    (
                        norm,
                        cui,
                        label,
                        str(row["sab"] or ""),
                        str(row["tty"] or ""),
                        str(row["ispref"] or ""),
                        str(row["suppress"] or ""),
                    )
                )
            count += 1
            if len(batch) >= batch_size:
                out_conn.executemany(insert_sql, batch)
                out_conn.commit()
                batch.clear()
        if batch:
            out_conn.executemany(insert_sql, batch)
            out_conn.commit()
        create_indexes(out_conn)
    finally:
        source_conn.close()
        out_conn.close()
    return count


class LabelIndex:
    def __init__(self, path: str | Path) -> None:
        self.conn = connect(path)
        self.cache: dict[tuple, list[sqlite3.Row] | list[dict]] = {}

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "LabelIndex":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def lookup(self, norm: str, *, limit: int = 100) -> list[sqlite3.Row]:
        key = ("lookup", norm, int(limit))
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        rows = list(
            self.conn.execute(
                """
                SELECT norm, cui, label, sab, tty, ispref
                FROM labels
                WHERE norm = ? AND suppress = 'N'
                LIMIT ?
                """,
                (norm, limit),
            )
        )
        self.cache[key] = rows
        return rows

    def search(
        self,
        query: str,
        *,
        search_type: str = "words",
        sabs: Iterable[str] | None = None,
        include_obsolete: bool = False,
        include_suppressible: bool = False,
        partial: bool = False,
        limit: int = 200,
    ) -> list[dict]:
        search_type = str(search_type or "words").strip()
        limit = max(1, int(limit or 1))
        sab_values = tuple(sorted(str(sab or "").strip().upper() for sab in (sabs or []) if str(sab or "").strip()))
        key = (
            "search",
            normalized_key(query),
            lexical_normalized_key(query),
            search_type,
            sab_values,
            bool(include_obsolete),
            bool(include_suppressible),
            bool(partial),
            limit,
        )
        cached = self.cache.get(key)
        if cached is not None:
            return [dict(row) for row in cached]

        rows = self._search_rows(
            query,
            search_type=search_type,
            sabs=sab_values,
            include_obsolete=include_obsolete,
            include_suppressible=include_suppressible,
            partial=partial,
            limit=limit,
        )
        results = _dedupe_label_rows(rows, query=query, search_type=search_type)[:limit]
        self.cache[key] = [dict(row) for row in results]
        return [dict(row) for row in results]

    def _search_rows(
        self,
        query: str,
        *,
        search_type: str,
        sabs: tuple[str, ...],
        include_obsolete: bool,
        include_suppressible: bool,
        partial: bool,
        limit: int,
    ) -> list[sqlite3.Row]:
        norm = normalized_key(query)
        if not norm:
            return []
        if search_type == "normalizedString":
            norms = [key for key in lexical_variant_keys(query) if key]
            if partial:
                clauses = ["norm LIKE ?"]
                values: list[object] = [f"%{lexical_normalized_key(query) or norm}%"]
            else:
                placeholders = ",".join("?" for _ in norms)
                clauses = [f"norm IN ({placeholders})"]
                values = list(norms)
        elif search_type == "exact":
            if partial:
                clauses = ["norm LIKE ?"]
                values = [f"%{norm}%"]
            else:
                clauses = ["norm = ?"]
                values = [norm]
        elif search_type in {"words", "normalizedWords"}:
            tokens = (
                lexical_normalized_tokens(query)
                if search_type == "normalizedWords"
                else norm.split()
            )
            tokens = [token for token in tokens if token]
            if not tokens:
                return []
            joiner = " OR " if partial else " AND "
            clauses = [joiner.join("norm LIKE ?" for _ in tokens)]
            values = [f"%{token}%" for token in tokens]
        elif search_type == "rightTruncation":
            clauses = ["norm LIKE ?"]
            values = [f"{norm}%"]
        elif search_type == "leftTruncation":
            clauses = ["norm LIKE ?"]
            values = [f"%{norm}"]
        else:
            return []

        clauses.append(_suppress_visibility_clause(include_obsolete, include_suppressible))
        if sabs:
            placeholders = ",".join("?" for _ in sabs)
            clauses.append(f"sab IN ({placeholders})")
            values.extend(sabs)

        sql = f"""
            SELECT norm, cui, label, sab, tty, ispref, suppress
            FROM labels
            WHERE {' AND '.join(f'({clause})' for clause in clauses)}
            LIMIT ?
        """
        query_limit = max(limit * 30, limit + 500)
        rows = list(self.conn.execute(sql, (*values, query_limit)))
        if search_type in {"words", "normalizedWords"}:
            wanted_tokens = (
                lexical_normalized_tokens(query)
                if search_type == "normalizedWords"
                else norm.split()
            )
            rows = [
                row
                for row in rows
                if _row_word_match(
                    str(row["norm"] or ""),
                    wanted_tokens,
                    partial=partial,
                )
            ]
        return rows


def _suppress_visibility_clause(include_obsolete: bool, include_suppressible: bool) -> str:
    if include_obsolete and include_suppressible:
        return "1 = 1"
    if include_obsolete:
        return "suppress IN ('N', 'O')"
    if include_suppressible:
        return "suppress IN ('N', 'E', 'Y')"
    return "suppress = 'N'"


def _row_word_match(row_norm: str, tokens: list[str], *, partial: bool) -> bool:
    row_tokens = set(row_norm.split())
    wanted = [token for token in tokens if token]
    if not wanted:
        return False
    if partial:
        return any(token in row_tokens for token in wanted)
    return all(token in row_tokens for token in wanted)


def _label_sort_key(row: sqlite3.Row | dict, *, query_norm: str) -> tuple:
    value = row.get if isinstance(row, dict) else row.__getitem__
    label_norm = normalized_key(str(value("label") or ""))
    row_norm = str(value("norm") or "")
    return (
        0 if row_norm == query_norm or label_norm == query_norm else 1,
        0 if str(value("suppress") or "") == "N" else 1,
        0 if str(value("ispref") or "") == "Y" else 1,
        str(value("sab") or ""),
        str(value("tty") or ""),
        len(str(value("label") or "")),
        str(value("label") or "").lower(),
        str(value("cui") or ""),
    )


def _dedupe_label_rows(
    rows: Iterable[sqlite3.Row],
    *,
    query: str,
    search_type: str,
) -> list[dict]:
    query_norm = (
        lexical_normalized_key(query)
        if search_type in {"normalizedString", "normalizedWords"}
        else normalized_key(query)
    )
    best_by_key: dict[tuple[str, str, str, str], dict] = {}
    for row in rows:
        item = {
            "norm": row["norm"],
            "cui": row["cui"],
            "label": row["label"],
            "sab": row["sab"],
            "tty": row["tty"],
            "ispref": row["ispref"],
            "suppress": row["suppress"],
        }
        key = (
            str(item["cui"] or ""),
            str(item["label"] or "").lower(),
            str(item["sab"] or ""),
            str(item["tty"] or ""),
        )
        current = best_by_key.get(key)
        if current is None or _label_sort_key(item, query_norm=query_norm) < _label_sort_key(
            current,
            query_norm=query_norm,
        ):
            best_by_key[key] = item
    return sorted(best_by_key.values(), key=lambda row: _label_sort_key(row, query_norm=query_norm))
