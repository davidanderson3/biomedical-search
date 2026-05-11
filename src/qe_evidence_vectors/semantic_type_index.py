from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS semantic_types (
    cui TEXT NOT NULL,
    tui TEXT NOT NULL,
    stn TEXT NOT NULL,
    sty TEXT NOT NULL,
    atui TEXT NOT NULL,
    PRIMARY KEY (cui, tui, atui)
) WITHOUT ROWID;
"""

INDEX_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_semantic_types_cui
ON semantic_types(cui);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-200000")
    return conn


def build_semantic_type_index(
    *,
    mrsty_path: str | Path,
    out_path: str | Path,
    replace: bool = False,
    batch_size: int = 50_000,
) -> int:
    out_path = Path(out_path).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(out_path)
    if replace:
        conn.execute("DROP TABLE IF EXISTS semantic_types")
    conn.executescript(TABLE_SCHEMA)
    sql = """
        INSERT OR IGNORE INTO semantic_types(cui, tui, stn, sty, atui)
        VALUES (?, ?, ?, ?, ?)
    """
    count = 0
    batch = []
    with Path(mrsty_path).expanduser().open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("|")
            if len(fields) < 5:
                continue
            batch.append((fields[0], fields[1], fields[2], fields[3], fields[4]))
            if len(batch) >= batch_size:
                conn.executemany(sql, batch)
                conn.commit()
                count += len(batch)
                batch.clear()
    if batch:
        conn.executemany(sql, batch)
        conn.commit()
        count += len(batch)
    conn.executescript(INDEX_SCHEMA)
    conn.commit()
    conn.close()
    return count


class SemanticTypeIndex:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self._local = threading.local()
        self.cache: dict[str, list[dict]] = {}

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

    def semantic_type_count(self) -> int:
        row = self.connection().execute("SELECT COUNT(*) AS count FROM semantic_types").fetchone()
        return int(row["count"] or 0)

    def source_count(self) -> int:
        row = self.connection().execute(
            "SELECT COUNT(DISTINCT cui) AS count FROM semantic_types"
        ).fetchone()
        return int(row["count"] or 0)

    def lookup(self, cui: str) -> list[dict]:
        cached = self.cache.get(cui)
        if cached is not None:
            return cached
        rows = self.connection().execute(
            """
            SELECT tui, stn, sty, atui
            FROM semantic_types
            WHERE cui = ?
            ORDER BY tui, sty
            """,
            (cui,),
        )
        results = [
            {
                "tui": row["tui"],
                "stn": row["stn"],
                "name": row["sty"],
                "atui": row["atui"],
            }
            for row in rows
        ]
        self.cache[cui] = results
        return results
