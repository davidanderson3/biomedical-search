from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path
from typing import Iterable


CUI_RE = re.compile(r"^C\d{7}$", re.IGNORECASE)
SYSTEM_CODE_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_ -]{1,31}):(.+)$")
LIKELY_CODE_RE = re.compile(
    r"^(?:"
    r"[A-Za-z]\d[A-Za-z0-9](?:\.[A-Za-z0-9]{1,5})?"
    r"|\d{1,5}-\d"
    r"|\d{3,18}"
    r"|[A-Za-z0-9][A-Za-z0-9_.\-/]{1,31}"
    r")$"
)

SAB_ALIASES = {
    "CPT": "CPT",
    "CPT4": "CPT",
    "HCPCS": "HCPCS",
    "ICD10": "ICD10CM",
    "ICD10CM": "ICD10CM",
    "ICD10PCS": "ICD10PCS",
    "ICD9": "ICD9CM",
    "ICD9CM": "ICD9CM",
    "LNC": "LNC",
    "LOINC": "LNC",
    "MDR": "MDR",
    "MEDDRA": "MDR",
    "MSH": "MSH",
    "MESH": "MSH",
    "NCI": "NCI",
    "NDC": "NDC",
    "RXCUI": "RXNORM",
    "RXNORM": "RXNORM",
    "SNOMED": "SNOMEDCT_US",
    "SNOMEDCT": "SNOMEDCT_US",
    "SNOMEDCT_US": "SNOMEDCT_US",
}

SAB_PRIORITY = {
    "MTH": 0,
    "MSH": 1,
    "SNOMEDCT_US": 2,
    "RXNORM": 3,
    "ICD10CM": 4,
    "ICD9CM": 5,
    "LNC": 6,
    "CPT": 7,
    "HCPCS": 8,
    "NCI": 9,
    "MDR": 10,
}

TTY_PRIORITY = {
    "PT": 0,
    "MH": 1,
    "PN": 2,
    "IN": 3,
    "ET": 4,
    "FN": 5,
    "SY": 6,
    "LLT": 7,
}

TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS code_mappings (
    cui TEXT NOT NULL,
    sab TEXT NOT NULL,
    code TEXT NOT NULL,
    scui TEXT NOT NULL,
    sdui TEXT NOT NULL,
    tty TEXT NOT NULL,
    label TEXT NOT NULL,
    ispref TEXT NOT NULL,
    suppress TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS preferred_terms (
    cui TEXT NOT NULL,
    label TEXT NOT NULL,
    sab TEXT NOT NULL,
    code TEXT NOT NULL,
    tty TEXT NOT NULL,
    suppress TEXT NOT NULL
);
"""

INDEX_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_code_mappings_cui
ON code_mappings(cui);
CREATE INDEX IF NOT EXISTS idx_code_mappings_sab_code
ON code_mappings(sab, code COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_code_mappings_code
ON code_mappings(code COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_code_mappings_scui
ON code_mappings(scui COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_code_mappings_sdui
ON code_mappings(sdui COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_preferred_terms_cui
ON preferred_terms(cui);
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


def normalize_sab(value: str) -> str:
    key = re.sub(r"[^A-Za-z0-9_]+", "", value or "").upper()
    return SAB_ALIASES.get(key, key)


def is_cui(value: str) -> bool:
    return bool(CUI_RE.match((value or "").strip()))


def parse_system_code(value: str) -> tuple[str, str] | None:
    match = SYSTEM_CODE_RE.match((value or "").strip())
    if not match:
        return None
    system = normalize_sab(match.group(1))
    code = match.group(2).strip()
    if not system or not code:
        return None
    return system, code


def looks_like_code(value: str) -> bool:
    text = (value or "").strip()
    if not text or any(char.isspace() for char in text):
        return False
    if is_cui(text):
        return True
    return bool(LIKELY_CODE_RE.match(text)) and any(char.isdigit() for char in text)


def _sort_key(row: sqlite3.Row) -> tuple[int, int, int, str, str]:
    return (
        0 if row["suppress"] == "N" else 1,
        TTY_PRIORITY.get(str(row["tty"]), 99),
        0 if row["ispref"] == "Y" else 1,
        SAB_PRIORITY.get(str(row["sab"]), 99),
        str(row["label"]).lower(),
    )


def _row_dict(row: sqlite3.Row) -> dict:
    return {
        "cui": row["cui"],
        "sab": row["sab"],
        "code": row["code"],
        "scui": row["scui"],
        "sdui": row["sdui"],
        "tty": row["tty"],
        "label": row["label"],
        "ispref": row["ispref"],
        "suppress": row["suppress"],
    }


def _preferred_sort_key(row: sqlite3.Row) -> tuple[int, int, int, str]:
    return (
        0 if row["suppress"] == "N" else 1,
        SAB_PRIORITY.get(str(row["sab"]), 99),
        TTY_PRIORITY.get(str(row["tty"]), 99),
        str(row["label"]).lower(),
    )


def _dedupe_rows(rows: Iterable[sqlite3.Row]) -> list[dict]:
    best_by_key: dict[tuple[str, str, str], sqlite3.Row] = {}
    for row in rows:
        key = (row["cui"], row["sab"], row["code"])
        current = best_by_key.get(key)
        if current is None or _sort_key(row) < _sort_key(current):
            best_by_key[key] = row
    return [_row_dict(row) for row in sorted(best_by_key.values(), key=_sort_key)]


def build_code_index(
    *,
    mrconso_path: str | Path,
    out_path: str | Path,
    language: str = "ENG",
    include_suppressed: bool = False,
    replace: bool = False,
    batch_size: int = 50_000,
) -> int:
    out_path = Path(out_path).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(out_path)
    if replace:
        conn.execute("DROP TABLE IF EXISTS code_mappings")
        conn.execute("DROP TABLE IF EXISTS preferred_terms")
    conn.executescript(TABLE_SCHEMA)
    mapping_sql = """
        INSERT INTO code_mappings(cui, sab, code, scui, sdui, tty, label, ispref, suppress)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    preferred_sql = """
        INSERT INTO preferred_terms(cui, label, sab, code, tty, suppress)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    batch = []
    preferred_batch = []
    count = 0
    with Path(mrconso_path).expanduser().open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("|")
            if len(fields) < 18:
                continue
            if fields[1] != language:
                continue
            suppress = fields[16]
            if not include_suppressed and suppress != "N":
                continue
            code = fields[13].strip()
            label = fields[14].strip()
            if not code or not label:
                continue
            if fields[2] == "P" and fields[4] == "PF" and fields[6] == "Y":
                preferred_batch.append(
                    (
                        fields[0],
                        label,
                        fields[11],
                        code,
                        fields[12],
                        suppress,
                    )
                )
            batch.append(
                (
                    fields[0],
                    fields[11],
                    code,
                    fields[9],
                    fields[10],
                    fields[12],
                    label,
                    fields[6],
                    suppress,
                )
            )
            if len(batch) >= batch_size:
                conn.executemany(mapping_sql, batch)
                if preferred_batch:
                    conn.executemany(preferred_sql, preferred_batch)
                conn.commit()
                count += len(batch)
                batch.clear()
                preferred_batch.clear()
    if batch:
        conn.executemany(mapping_sql, batch)
        if preferred_batch:
            conn.executemany(preferred_sql, preferred_batch)
        conn.commit()
        count += len(batch)
    conn.executescript(INDEX_SCHEMA)
    conn.commit()
    conn.close()
    return count


class CodeIndex:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self._local = threading.local()
        self.cache: dict[tuple, list[dict]] = {}
        self.preferred_cache: dict[str, str] = {}
        self.active_cui_cache: dict[str, bool] = {}
        self._mapping_count: int | None = None

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

    def mapping_count(self) -> int:
        if self._mapping_count is None:
            row = self.connection().execute("SELECT COUNT(*) AS count FROM code_mappings").fetchone()
            self._mapping_count = int(row["count"] or 0)
        return self._mapping_count

    def preferred_label(self, cui: str) -> str:
        cui = cui.strip().upper()
        if not cui:
            return ""
        cached = self.preferred_cache.get(cui)
        if cached is not None:
            return cached
        try:
            rows = list(
                self.connection().execute(
                    """
                    SELECT cui, label, sab, code, tty, suppress
                    FROM preferred_terms
                    WHERE cui = ?
                    """,
                    (cui,),
                )
            )
        except sqlite3.OperationalError:
            rows = []
        label = ""
        if rows:
            label = str(sorted(rows, key=_preferred_sort_key)[0]["label"] or "")
        if not label:
            mapping_rows = self.lookup_cui(cui, limit=1)
            if mapping_rows:
                label = str(mapping_rows[0].get("label") or "")
        self.preferred_cache[cui] = label
        return label

    def has_active_cui(self, cui: str) -> bool:
        cui = cui.strip().upper()
        if not cui:
            return False
        cached = self.active_cui_cache.get(cui)
        if cached is not None:
            return cached
        row = self.connection().execute(
            """
            SELECT 1
            FROM code_mappings
            WHERE cui = ? AND suppress = 'N'
            LIMIT 1
            """,
            (cui,),
        ).fetchone()
        active = row is not None
        self.active_cui_cache[cui] = active
        return active

    def lookup_cui(self, cui: str, *, sabs: Iterable[str] | None = None, limit: int = 100) -> list[dict]:
        cui = cui.strip().upper()
        sab_values = tuple(sorted(normalize_sab(sab) for sab in (sabs or []) if sab))
        key = ("cui", cui, sab_values, limit)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        query_limit = max(limit * 4, limit + 50)
        if sab_values:
            placeholders = ",".join("?" for _ in sab_values)
            rows = self.connection().execute(
                f"""
                SELECT cui, sab, code, scui, sdui, tty, label, ispref, suppress
                FROM code_mappings
                WHERE cui = ? AND sab IN ({placeholders})
                LIMIT ?
                """,
                (cui, *sab_values, query_limit),
            )
        else:
            rows = self.connection().execute(
                """
                SELECT cui, sab, code, scui, sdui, tty, label, ispref, suppress
                FROM code_mappings
                WHERE cui = ?
                LIMIT ?
                """,
                (cui, query_limit),
            )
        results = _dedupe_rows(rows)[:limit]
        self.cache[key] = results
        return results

    def lookup_code(
        self,
        code: str,
        *,
        sab: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        code = code.strip()
        sab_value = normalize_sab(sab or "") if sab else ""
        key = ("code", sab_value, code.lower(), limit)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        query_limit = max(limit * 4, limit + 50)
        if sab_value:
            rows = self.connection().execute(
                """
                SELECT cui, sab, code, scui, sdui, tty, label, ispref, suppress
                FROM code_mappings
                WHERE sab = ? AND code = ? COLLATE NOCASE
                LIMIT ?
                """,
                (sab_value, code, query_limit),
            )
        else:
            rows = self.connection().execute(
                """
                SELECT cui, sab, code, scui, sdui, tty, label, ispref, suppress
                FROM code_mappings
                WHERE code = ? COLLATE NOCASE
                   OR scui = ? COLLATE NOCASE
                   OR sdui = ? COLLATE NOCASE
                LIMIT ?
                """,
                (code, code, code, query_limit),
            )
        results = _dedupe_rows(rows)[:limit]
        self.cache[key] = results
        return results
