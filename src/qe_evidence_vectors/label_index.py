from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from .generic_filters import is_blocked_generic_concept
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


def _valid_label(label: str, *, min_chars: int, min_tokens: int, max_tokens: int) -> bool:
    norm = normalized_key(label)
    if len(norm) < min_chars:
        return False
    if not any(char.isalpha() for char in norm):
        return False
    tokens = norm.split()
    if not (min_tokens <= len(tokens) <= max_tokens):
        return False
    if len(tokens) == 1:
        token = tokens[0]
        if token in BLOCKED_SINGLE_TOKEN_LABELS:
            return False
        if len(token) < max(4, min_chars):
            return False
    return True


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
            ):
                continue
            batch.append(
                (
                    normalized_key(label),
                    cui,
                    label,
                    fields[11],
                    fields[12],
                    fields[6],
                    fields[16],
                )
            )
            if len(batch) >= 50_000:
                conn.executemany(sql, batch)
                conn.commit()
                count += len(batch)
                batch.clear()
    if batch:
        conn.executemany(sql, batch)
        conn.commit()
        count += len(batch)
    create_indexes(conn)
    conn.close()
    return count


class LabelIndex:
    def __init__(self, path: str | Path) -> None:
        self.conn = connect(path)
        self.cache: dict[str, list[sqlite3.Row]] = {}

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "LabelIndex":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def lookup(self, norm: str, *, limit: int = 100) -> list[sqlite3.Row]:
        cached = self.cache.get(norm)
        if cached is not None:
            return cached
        rows = list(
            self.conn.execute(
                """
                SELECT norm, cui, label, sab, tty, ispref
                FROM labels
                WHERE norm = ?
                LIMIT ?
                """,
                (norm, limit),
            )
        )
        self.cache[norm] = rows
        return rows
