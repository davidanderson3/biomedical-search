from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path
from typing import Iterable


CUI_RE = re.compile(r"^C\d{7}$", re.IGNORECASE)
AUI_RE = re.compile(r"^A\d{7,8}$", re.IGNORECASE)
LUI_RE = re.compile(r"^L\d{7,8}$", re.IGNORECASE)
SUI_RE = re.compile(r"^S\d{7,8}$", re.IGNORECASE)
RUI_RE = re.compile(r"^R\d{7,8}$", re.IGNORECASE)
ATUI_RE = re.compile(r"^AT\d+$", re.IGNORECASE)
TUI_RE = re.compile(r"^T\d{3}$", re.IGNORECASE)
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
    "SNOMEDCTUS": "SNOMEDCT_US",
    "SNOMEDCT_US": "SNOMEDCT_US",
    "CODE": "CODE",
    "SCUI": "SCUI",
    "SDUI": "SDUI",
    "AUI": "AUI",
    "LUI": "LUI",
    "SUI": "SUI",
    "RUI": "RUI",
    "ATUI": "ATUI",
    "TUI": "TUI",
}

UMLS_IDENTIFIER_SYSTEMS = frozenset(
    {"CUI", "CODE", "SCUI", "SDUI", "AUI", "LUI", "SUI", "RUI", "ATUI", "TUI"}
)
CODE_IDENTIFIER_SYSTEMS = frozenset({"CODE", "SCUI", "SDUI", "AUI", "LUI", "SUI"})
PATTERNED_UMLS_IDENTIFIER_SYSTEMS = frozenset({"CUI", "AUI", "LUI", "SUI", "RUI", "ATUI", "TUI"})
KNOWN_SOURCE_SYSTEMS = frozenset(SAB_ALIASES.values()) | UMLS_IDENTIFIER_SYSTEMS

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
CREATE TABLE IF NOT EXISTS identifier_mappings (
    cui TEXT NOT NULL,
    identifier_type TEXT NOT NULL,
    identifier TEXT NOT NULL,
    sab TEXT NOT NULL,
    code TEXT NOT NULL,
    scui TEXT NOT NULL,
    sdui TEXT NOT NULL,
    tty TEXT NOT NULL,
    label TEXT NOT NULL,
    ispref TEXT NOT NULL,
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
CREATE INDEX IF NOT EXISTS idx_identifier_mappings_identifier
ON identifier_mappings(identifier_type, identifier COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_identifier_mappings_sab_identifier
ON identifier_mappings(sab, identifier_type, identifier COLLATE NOCASE);
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


def infer_umls_identifier_type(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    checks = (
        ("CUI", CUI_RE),
        ("AUI", AUI_RE),
        ("LUI", LUI_RE),
        ("SUI", SUI_RE),
        ("RUI", RUI_RE),
        ("ATUI", ATUI_RE),
        ("TUI", TUI_RE),
    )
    for identifier_type, pattern in checks:
        if pattern.match(text):
            return identifier_type
    return ""


def looks_like_umls_identifier(value: str, identifier_type: str | None = None) -> bool:
    inferred = infer_umls_identifier_type(value)
    if not identifier_type:
        return bool(inferred)
    return inferred == normalize_sab(identifier_type)


def parse_system_code(value: str) -> tuple[str, str] | None:
    text = (value or "").strip()
    match = SYSTEM_CODE_RE.match(text)
    if match:
        system = normalize_sab(match.group(1))
        code = match.group(2).strip()
        if system in PATTERNED_UMLS_IDENTIFIER_SYSTEMS:
            if not looks_like_umls_identifier(code, system):
                return None
    else:
        parts = text.rsplit(None, 1)
        if len(parts) != 2:
            return None
        system_text, code = parts[0], parts[1].strip()
        system = normalize_sab(system_text)
        if system not in KNOWN_SOURCE_SYSTEMS:
            return None
        if system in PATTERNED_UMLS_IDENTIFIER_SYSTEMS:
            if not looks_like_umls_identifier(code, system):
                return None
        elif not looks_like_code(code):
            return None
    if not system or not code:
        return None
    return system, code


def looks_like_code(value: str) -> bool:
    text = (value or "").strip()
    if not text or any(char.isspace() for char in text):
        return False
    if is_cui(text):
        return True
    if infer_umls_identifier_type(text):
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
    result = {
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
    if "identifier_type" in row.keys():
        result["matched_identifier_type"] = row["identifier_type"]
    if "identifier" in row.keys():
        result["matched_identifier"] = row["identifier"]
    return result


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
        conn.execute("DROP TABLE IF EXISTS identifier_mappings")
    conn.executescript(TABLE_SCHEMA)
    mapping_sql = """
        INSERT INTO code_mappings(cui, sab, code, scui, sdui, tty, label, ispref, suppress)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    identifier_sql = """
        INSERT INTO identifier_mappings(
            cui, identifier_type, identifier, sab, code, scui, sdui, tty, label, ispref, suppress
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    preferred_sql = """
        INSERT INTO preferred_terms(cui, label, sab, code, tty, suppress)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    batch = []
    identifier_batch = []
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
            aui = fields[7].strip()
            scui = fields[9].strip()
            sdui = fields[10].strip()
            sab = fields[11].strip()
            tty = fields[12].strip()
            if not code or not label:
                continue
            if fields[2] == "P" and fields[4] == "PF" and fields[6] == "Y":
                preferred_batch.append(
                    (
                        fields[0],
                        label,
                        sab,
                        code,
                        tty,
                        suppress,
                    )
                )
            batch.append(
                (
                    fields[0],
                    sab,
                    code,
                    scui,
                    sdui,
                    tty,
                    label,
                    fields[6],
                    suppress,
                )
            )
            for identifier_type, identifier in (
                ("CODE", code),
                ("SCUI", scui),
                ("SDUI", sdui),
                ("AUI", aui),
                ("LUI", fields[3].strip()),
                ("SUI", fields[5].strip()),
            ):
                if not identifier:
                    continue
                identifier_batch.append(
                    (
                        fields[0],
                        identifier_type,
                        identifier,
                        sab,
                        code,
                        scui,
                        sdui,
                        tty,
                        label,
                        fields[6],
                        suppress,
                    )
                )
            if len(batch) >= batch_size:
                conn.executemany(mapping_sql, batch)
                if identifier_batch:
                    conn.executemany(identifier_sql, identifier_batch)
                if preferred_batch:
                    conn.executemany(preferred_sql, preferred_batch)
                conn.commit()
                count += len(batch)
                batch.clear()
                identifier_batch.clear()
                preferred_batch.clear()
    if batch:
        conn.executemany(mapping_sql, batch)
        if identifier_batch:
            conn.executemany(identifier_sql, identifier_batch)
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
        self._identifier_table_available: bool | None = None

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

    def identifier_table_available(self) -> bool:
        if self._identifier_table_available is None:
            row = self.connection().execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table' AND name = 'identifier_mappings'
                LIMIT 1
                """
            ).fetchone()
            self._identifier_table_available = row is not None
        return self._identifier_table_available

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
                WHERE sab = ?
                  AND (
                    code = ? COLLATE NOCASE
                    OR scui = ? COLLATE NOCASE
                    OR sdui = ? COLLATE NOCASE
                  )
                LIMIT ?
                """,
                (sab_value, code, code, code, query_limit),
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

    def lookup_identifier(
        self,
        identifier: str,
        *,
        identifier_type: str | None = None,
        sab: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        identifier = str(identifier or "").strip()
        if not identifier:
            return []
        identifier_type_value = normalize_sab(identifier_type or infer_umls_identifier_type(identifier) or "CODE")
        sab_value = normalize_sab(sab or "") if sab else ""
        key = ("identifier", identifier_type_value, sab_value, identifier.lower(), limit)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        if identifier_type_value == "CUI":
            results = self.lookup_cui(identifier, sabs=[sab_value] if sab_value else None, limit=limit)
            self.cache[key] = results
            return results
        if identifier_type_value in {"CODE", "SCUI", "SDUI"}:
            column = {"CODE": "code", "SCUI": "scui", "SDUI": "sdui"}[identifier_type_value]
            query_limit = max(limit * 4, limit + 50)
            if sab_value:
                rows = self.connection().execute(
                    f"""
                    SELECT cui, sab, code, scui, sdui, tty, label, ispref, suppress
                    FROM code_mappings
                    WHERE sab = ?
                      AND {column} = ? COLLATE NOCASE
                    LIMIT ?
                    """,
                    (sab_value, identifier, query_limit),
                )
            else:
                rows = self.connection().execute(
                    f"""
                    SELECT cui, sab, code, scui, sdui, tty, label, ispref, suppress
                    FROM code_mappings
                    WHERE {column} = ? COLLATE NOCASE
                    LIMIT ?
                    """,
                    (identifier, query_limit),
                )
            results = _dedupe_rows(rows)[:limit]
            self.cache[key] = results
            return results
        if identifier_type_value not in {"AUI", "LUI", "SUI"} or not self.identifier_table_available():
            self.cache[key] = []
            return []
        query_limit = max(limit * 4, limit + 50)
        if sab_value:
            rows = self.connection().execute(
                """
                SELECT
                    cui, identifier_type, identifier, sab, code, scui, sdui, tty, label, ispref, suppress
                FROM identifier_mappings
                WHERE sab = ?
                  AND identifier_type = ?
                  AND identifier = ? COLLATE NOCASE
                LIMIT ?
                """,
                (sab_value, identifier_type_value, identifier, query_limit),
            )
        else:
            rows = self.connection().execute(
                """
                SELECT
                    cui, identifier_type, identifier, sab, code, scui, sdui, tty, label, ispref, suppress
                FROM identifier_mappings
                WHERE identifier_type = ?
                  AND identifier = ? COLLATE NOCASE
                LIMIT ?
                """,
                (identifier_type_value, identifier, query_limit),
            )
        results = _dedupe_rows(rows)[:limit]
        self.cache[key] = results
        return results
