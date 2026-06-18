#!/usr/bin/env python3
"""Small UMLS-backed resolver and search-box server.

The runtime contract is intentionally narrow:

1. Build one SQLite index from a local UMLS META directory.
2. Resolve CUIs, source vocabulary codes, atom identifiers, and text mentions.
3. Serve one browser search box plus a JSON API.

No vector index, Elasticsearch service, evidence corpus, or external Python
package is required.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import threading
import time
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable, Iterator
from urllib.parse import parse_qs, urlparse


API_VERSION = "2026-06-15"
DEFAULT_INDEX = Path("build/umls_resolver.sqlite")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8766
DEFAULT_LANGUAGE = "ENG"
DEFAULT_MAX_PHRASE_TOKENS = 8
DEFAULT_RESULT_LIMIT = 25
DEFAULT_CODE_LIMIT = 40
DEFAULT_AUDIT_CANARIES = (
    ("C0004238", "C0004238"),
    ("atrial fibrillation", "C0004238"),
    ("ICD10CM:I48.91", "C0004238"),
    ("SNOMED CT US 49436004", "C0004238"),
)
SQLITE_CHUNK_SIZE = 450

CUI_RE = re.compile(r"\bC\d{7}\b", re.IGNORECASE)
AUI_RE = re.compile(r"^A\d{7,8}$", re.IGNORECASE)
LUI_RE = re.compile(r"^L\d{7,8}$", re.IGNORECASE)
SUI_RE = re.compile(r"^S\d{7,8}$", re.IGNORECASE)
TUI_RE = re.compile(r"^T\d{3}$", re.IGNORECASE)
ATUI_RE = re.compile(r"^AT\d+$", re.IGNORECASE)
CODE_VALUE_PATTERN = (
    r"[A-Za-z]\d[A-Za-z0-9]{1,31}(?:\.[A-Za-z0-9]{1,8})?"
    r"|\d{1,7}-\d"
    r"|[A-Za-z]{1,8}\d[A-Za-z0-9_.\-/]{1,31}"
    r"|\d{2,18}"
)
GENERIC_SYSTEM_CODE_RE = re.compile(
    rf"(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9_]{{1,31}})\s*:\s*"
    rf"({CODE_VALUE_PATTERN})(?![A-Za-z0-9])",
    re.IGNORECASE,
)
CODE_TOKEN_RE = re.compile(
    rf"(?<![A-Za-z0-9])({CODE_VALUE_PATTERN})(?![A-Za-z0-9])",
    re.IGNORECASE,
)
TOKEN_RE = re.compile(r"[A-Za-z0-9]+")

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
    "MESH": "MSH",
    "MSH": "MSH",
    "NCI": "NCI",
    "NDC": "NDC",
    "RXCUI": "RXNORM",
    "RXNORM": "RXNORM",
    "SNOMED": "SNOMEDCT_US",
    "SNOMEDCT": "SNOMEDCT_US",
    "SNOMEDCTUS": "SNOMEDCT_US",
    "SNOMEDCT_US": "SNOMEDCT_US",
    "SCT": "SNOMEDCT_US",
    "CUI": "CUI",
    "CODE": "CODE",
    "SCUI": "SCUI",
    "SDUI": "SDUI",
    "AUI": "AUI",
    "LUI": "LUI",
    "SUI": "SUI",
    "TUI": "TUI",
    "ATUI": "ATUI",
}

SPACE_SYSTEM_ALIASES = {
    "SNOMED CT US": "SNOMEDCT_US",
    "SNOMED CT": "SNOMEDCT_US",
    "SNOMED": "SNOMEDCT_US",
    "SCT": "SNOMEDCT_US",
    "ICD 10 CM": "ICD10CM",
    "ICD-10-CM": "ICD10CM",
    "ICD10CM": "ICD10CM",
    "ICD 10 PCS": "ICD10PCS",
    "ICD-10-PCS": "ICD10PCS",
    "ICD10PCS": "ICD10PCS",
    "ICD 9 CM": "ICD9CM",
    "ICD-9-CM": "ICD9CM",
    "ICD9CM": "ICD9CM",
    "LOINC": "LNC",
    "LNC": "LNC",
    "RXNORM": "RXNORM",
    "RX CUI": "RXNORM",
    "RXCUI": "RXNORM",
    "MESH": "MSH",
    "MeSH": "MSH",
    "MSH": "MSH",
    "CPT": "CPT",
    "CPT4": "CPT",
    "HCPCS": "HCPCS",
    "NCI": "NCI",
    "NDC": "NDC",
    "MEDDRA": "MDR",
    "MDR": "MDR",
    "AUI": "AUI",
    "LUI": "LUI",
    "SUI": "SUI",
    "SCUI": "SCUI",
    "SDUI": "SDUI",
    "TUI": "TUI",
    "ATUI": "ATUI",
    "CUI": "CUI",
}

IDENTIFIER_TYPES = {"CUI", "CODE", "SCUI", "SDUI", "AUI", "LUI", "SUI", "TUI", "ATUI"}
NAME_SAB_PRIORITY = {
    "MTH": 0,
    "MSH": 1,
    "SNOMEDCT_US": 2,
    "RXNORM": 3,
    "LNC": 4,
    "ICD10CM": 5,
    "ICD10PCS": 6,
    "ICD9CM": 7,
    "CPT": 8,
    "HCPCS": 9,
    "NCI": 10,
    "MDR": 11,
}

CODE_SAB_PRIORITY = {
    "SNOMEDCT_US": 0,
    "RXNORM": 1,
    "LNC": 2,
    "ICD10CM": 3,
    "ICD10PCS": 4,
    "ICD9CM": 5,
    "CPT": 6,
    "HCPCS": 7,
    "MSH": 8,
    "NCI": 9,
    "MDR": 10,
    "NDC": 11,
    "MTH": 99,
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

SKIP_CODES = {"", "NOCODE", "NONE", "N/A"}
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "were",
    "with",
    "without",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS labels (
    norm TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    cui TEXT NOT NULL,
    label TEXT NOT NULL,
    sab TEXT NOT NULL,
    tty TEXT NOT NULL,
    ispref TEXT NOT NULL,
    suppress TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS codes (
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

CREATE TABLE IF NOT EXISTS identifiers (
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

CREATE TABLE IF NOT EXISTS semantic_types (
    cui TEXT NOT NULL,
    tui TEXT NOT NULL,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_labels_norm ON labels(norm);
CREATE INDEX IF NOT EXISTS idx_labels_cui ON labels(cui);
CREATE INDEX IF NOT EXISTS idx_codes_cui ON codes(cui);
CREATE INDEX IF NOT EXISTS idx_codes_sab_code ON codes(sab, code COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_codes_code ON codes(code COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_codes_scui ON codes(scui COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_codes_sdui ON codes(sdui COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_identifiers_type_identifier
    ON identifiers(identifier_type, identifier COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_identifiers_sab_type_identifier
    ON identifiers(sab, identifier_type, identifier COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_semantic_types_cui ON semantic_types(cui);
CREATE INDEX IF NOT EXISTS idx_semantic_types_tui ON semantic_types(tui);
"""

DROP_SCHEMA = """
DROP TABLE IF EXISTS labels;
DROP TABLE IF EXISTS codes;
DROP TABLE IF EXISTS identifiers;
DROP TABLE IF EXISTS semantic_types;
DROP TABLE IF EXISTS metadata;
"""


def ascii_fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def normalized_key(text: str) -> str:
    text = ascii_fold(str(text or "")).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_sab(value: str) -> str:
    key = re.sub(r"[^A-Za-z0-9_]+", "", str(value or "")).upper()
    return SAB_ALIASES.get(key, key)


def is_cui(value: str) -> bool:
    return bool(re.fullmatch(r"C\d{7}", str(value or "").strip(), re.IGNORECASE))


def infer_identifier_type(value: str) -> str:
    text = str(value or "").strip()
    checks = (
        ("CUI", re.compile(r"^C\d{7}$", re.IGNORECASE)),
        ("AUI", AUI_RE),
        ("LUI", LUI_RE),
        ("SUI", SUI_RE),
        ("TUI", TUI_RE),
        ("ATUI", ATUI_RE),
    )
    for identifier_type, pattern in checks:
        if pattern.match(text):
            return identifier_type
    return ""


def looks_like_code(value: str) -> bool:
    text = str(value or "").strip()
    if not text or any(char.isspace() for char in text):
        return False
    if infer_identifier_type(text):
        return True
    return bool(CODE_TOKEN_RE.fullmatch(text)) and any(char.isdigit() for char in text)


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-200000")
    return conn


def chunks(values: list[str], size: int = SQLITE_CHUNK_SIZE) -> Iterator[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def count_rows(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return int(row["count"] or 0)


def build_index(
    *,
    umls_meta: str | Path | None = None,
    mrconso: str | Path | None = None,
    mrsty: str | Path | None = None,
    index: str | Path = DEFAULT_INDEX,
    language: str = DEFAULT_LANGUAGE,
    include_suppressed: bool = False,
    replace: bool = True,
    batch_size: int = 50_000,
) -> dict:
    if umls_meta:
        meta_path = Path(umls_meta).expanduser()
        mrconso_path = meta_path / "MRCONSO.RRF"
        mrsty_path = meta_path / "MRSTY.RRF"
    else:
        if not mrconso:
            raise ValueError("pass --umls-meta or --mrconso")
        mrconso_path = Path(mrconso).expanduser()
        mrsty_path = Path(mrsty).expanduser() if mrsty else None

    if not mrconso_path.exists():
        raise FileNotFoundError(f"MRCONSO.RRF not found: {mrconso_path}")
    if mrsty_path and not mrsty_path.exists():
        mrsty_path = None

    conn = connect(index)
    if replace:
        conn.executescript(DROP_SCHEMA)
    conn.executescript(SCHEMA)

    label_sql = """
        INSERT INTO labels(norm, token_count, cui, label, sab, tty, ispref, suppress)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    code_sql = """
        INSERT INTO codes(cui, sab, code, scui, sdui, tty, label, ispref, suppress)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    identifier_sql = """
        INSERT INTO identifiers(
            cui, identifier_type, identifier, sab, code, scui, sdui, tty, label, ispref, suppress
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    semantic_type_sql = """
        INSERT INTO semantic_types(cui, tui, name)
        VALUES (?, ?, ?)
    """

    label_batch = []
    code_batch = []
    identifier_batch = []
    source_atoms = 0
    skipped_suppressed = 0
    with mrconso_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("|")
            if len(fields) < 18:
                continue
            cui, lat, _ts, lui, _stt, sui, ispref, aui = fields[:8]
            scui, sdui, sab, tty, code, label, suppress = (
                fields[9].strip(),
                fields[10].strip(),
                fields[11].strip(),
                fields[12].strip(),
                fields[13].strip(),
                fields[14].strip(),
                fields[16].strip(),
            )
            if lat != language:
                continue
            if not include_suppressed and suppress != "N":
                skipped_suppressed += 1
                continue
            if not cui or not label:
                continue
            source_atoms += 1
            norm = normalized_key(label)
            if norm:
                label_batch.append(
                    (
                        norm,
                        len(norm.split()),
                        cui,
                        label,
                        sab,
                        tty,
                        ispref,
                        suppress,
                    )
                )
            if code:
                code_batch.append((cui, sab, code, scui, sdui, tty, label, ispref, suppress))
            for identifier_type, identifier in (
                ("CODE", code),
                ("SCUI", scui),
                ("SDUI", sdui),
                ("AUI", aui.strip()),
                ("LUI", lui.strip()),
                ("SUI", sui.strip()),
            ):
                if identifier:
                    identifier_batch.append(
                        (
                            cui,
                            identifier_type,
                            identifier,
                            sab,
                            code,
                            scui,
                            sdui,
                            tty,
                            label,
                            ispref,
                            suppress,
                        )
                    )
            if len(label_batch) >= batch_size:
                conn.executemany(label_sql, label_batch)
                conn.executemany(code_sql, code_batch)
                conn.executemany(identifier_sql, identifier_batch)
                conn.commit()
                label_batch.clear()
                code_batch.clear()
                identifier_batch.clear()

    if label_batch:
        conn.executemany(label_sql, label_batch)
    if code_batch:
        conn.executemany(code_sql, code_batch)
    if identifier_batch:
        conn.executemany(identifier_sql, identifier_batch)
    conn.commit()

    semantic_type_rows = 0
    if mrsty_path:
        semantic_batch = []
        with mrsty_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                fields = line.rstrip("\n").split("|")
                if len(fields) < 4:
                    continue
                semantic_batch.append((fields[0], fields[1], fields[3]))
                semantic_type_rows += 1
                if len(semantic_batch) >= batch_size:
                    conn.executemany(semantic_type_sql, semantic_batch)
                    conn.commit()
                    semantic_batch.clear()
        if semantic_batch:
            conn.executemany(semantic_type_sql, semantic_batch)
            conn.commit()

    conn.executescript(INDEXES)
    metadata = {
        "api_version": API_VERSION,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "language": language,
        "mrconso": str(mrconso_path),
        "mrsty": str(mrsty_path or ""),
        "include_suppressed": "1" if include_suppressed else "0",
        "source_atoms": str(source_atoms),
        "skipped_suppressed_atoms": str(skipped_suppressed),
    }
    conn.executemany(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
        sorted(metadata.items()),
    )
    conn.commit()
    stats = {
        "index": str(Path(index).expanduser()),
        "labels": count_rows(conn, "labels"),
        "codes": count_rows(conn, "codes"),
        "identifiers": count_rows(conn, "identifiers"),
        "semantic_types": count_rows(conn, "semantic_types"),
        "source_atoms": source_atoms,
        "skipped_suppressed_atoms": skipped_suppressed,
    }
    conn.close()
    return stats


def row_value(row: sqlite3.Row | dict, key: str, default: str = "") -> str:
    if isinstance(row, dict):
        return str(row.get(key, default) or default)
    return str(row[key] if key in row.keys() and row[key] is not None else default)


def code_row_sort_key(row: sqlite3.Row | dict) -> tuple:
    sab = row_value(row, "sab")
    tty = row_value(row, "tty")
    return (
        0 if row_value(row, "suppress") == "N" else 1,
        CODE_SAB_PRIORITY.get(sab, 50),
        TTY_PRIORITY.get(tty, 99),
        0 if row_value(row, "ispref") == "Y" else 1,
        row_value(row, "label").lower(),
        row_value(row, "code").lower(),
    )


def name_row_sort_key(row: sqlite3.Row | dict) -> tuple:
    sab = row_value(row, "sab")
    tty = row_value(row, "tty")
    return (
        0 if row_value(row, "suppress") == "N" else 1,
        NAME_SAB_PRIORITY.get(sab, 50),
        TTY_PRIORITY.get(tty, 99),
        0 if row_value(row, "ispref") == "Y" else 1,
        row_value(row, "label").lower(),
    )


def dict_for_code_row(row: sqlite3.Row | dict) -> dict:
    return {
        "cui": row_value(row, "cui"),
        "sab": row_value(row, "sab"),
        "code": row_value(row, "code"),
        "scui": row_value(row, "scui"),
        "sdui": row_value(row, "sdui"),
        "tty": row_value(row, "tty"),
        "label": row_value(row, "label"),
        "ispref": row_value(row, "ispref"),
        "suppress": row_value(row, "suppress"),
    }


def dict_for_label_row(row: sqlite3.Row | dict) -> dict:
    return {
        "norm": row_value(row, "norm"),
        "token_count": int(row_value(row, "token_count", "0") or 0),
        "cui": row_value(row, "cui"),
        "label": row_value(row, "label"),
        "sab": row_value(row, "sab"),
        "tty": row_value(row, "tty"),
        "ispref": row_value(row, "ispref"),
        "suppress": row_value(row, "suppress"),
    }


def dedupe_code_rows(rows: Iterable[sqlite3.Row | dict]) -> list[dict]:
    best: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        item = dict_for_code_row(row)
        key = (item["cui"], item["sab"], item["code"].upper())
        current = best.get(key)
        if current is None or code_row_sort_key(item) < code_row_sort_key(current):
            best[key] = item
    return sorted(best.values(), key=code_row_sort_key)


def alias_regex(alias: str) -> str:
    pieces = [re.escape(piece) for piece in re.findall(r"[A-Za-z0-9]+", alias)]
    return r"[\s_-]*".join(pieces)


SYSTEM_CODE_PATTERNS = [
    (
        re.compile(
            rf"(?<![A-Za-z0-9]){alias_regex(alias)}\s*:?\s*({CODE_VALUE_PATTERN})(?![A-Za-z0-9])",
            re.IGNORECASE,
        ),
        sab,
    )
    for alias, sab in sorted(SPACE_SYSTEM_ALIASES.items(), key=lambda item: -len(item[0]))
]


def iter_system_code_mentions(text: str) -> Iterator[dict]:
    seen: set[tuple[int, int, str, str]] = set()
    for pattern, sab in SYSTEM_CODE_PATTERNS:
        for match in pattern.finditer(text):
            code = match.group(1).strip()
            key = (match.start(), match.end(), sab, code.lower())
            if key in seen or not code:
                continue
            seen.add(key)
            yield {
                "system": sab,
                "code": code,
                "text": match.group(0),
                "start": match.start(),
                "end": match.end(),
            }
    for match in GENERIC_SYSTEM_CODE_RE.finditer(text):
        system = normalize_sab(match.group(1))
        code = match.group(2).strip()
        if system not in set(SAB_ALIASES.values()) | IDENTIFIER_TYPES:
            continue
        key = (match.start(), match.end(), system, code.lower())
        if key in seen:
            continue
        seen.add(key)
        yield {
            "system": system,
            "code": code,
            "text": match.group(0),
            "start": match.start(),
            "end": match.end(),
        }


def overlaps(span: tuple[int, int], spans: Iterable[tuple[int, int]]) -> bool:
    start, end = span
    return any(start < other_end and end > other_start for other_start, other_end in spans)


def tokenize_with_spans(text: str) -> list[dict]:
    tokens = []
    for match in TOKEN_RE.finditer(text):
        norm = normalized_key(match.group(0))
        if norm:
            tokens.append(
                {
                    "norm": norm,
                    "text": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                }
            )
    return tokens


def phrase_candidates(text: str, *, max_tokens: int = DEFAULT_MAX_PHRASE_TOKENS) -> dict[str, dict]:
    tokens = tokenize_with_spans(text)
    phrases: dict[str, dict] = {}
    for start in range(len(tokens)):
        parts = []
        for end in range(start, min(len(tokens), start + max_tokens)):
            parts.append(tokens[end]["norm"])
            token_count = end - start + 1
            if token_count == 1:
                token = parts[0]
                if token in STOPWORDS or (len(token) < 4 and not any(char.isdigit() for char in token)):
                    continue
            elif parts[0] in STOPWORDS or parts[-1] in STOPWORDS:
                continue
            norm = " ".join(parts)
            span = {
                "text": text[tokens[start]["start"] : tokens[end]["end"]],
                "start": tokens[start]["start"],
                "end": tokens[end]["end"],
                "token_count": token_count,
            }
            current = phrases.get(norm)
            if current is None:
                phrases[norm] = {"token_count": token_count, "spans": [span]}
            elif len(current["spans"]) < 5:
                current["spans"].append(span)
    return phrases


class UMLSResolver:
    def __init__(self, index: str | Path) -> None:
        self.index = Path(index).expanduser()
        if not self.index.exists():
            raise FileNotFoundError(f"resolver index not found: {self.index}")
        self.conn = connect(self.index)
        self._lock = threading.RLock()
        self._name_cache: dict[str, str] = {}
        self._code_cache: dict[tuple[str, int], list[dict]] = {}
        self._semantic_type_cache: dict[str, list[dict]] = {}

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def metadata(self) -> dict:
        with self._lock:
            rows = self.conn.execute("SELECT key, value FROM metadata").fetchall()
            metadata = {row["key"]: row["value"] for row in rows}
            for table in ("labels", "codes", "identifiers", "semantic_types"):
                try:
                    metadata[f"{table}_rows"] = count_rows(self.conn, table)
                except sqlite3.OperationalError:
                    metadata[f"{table}_rows"] = 0
            return metadata

    def source_counts(self) -> dict[str, int]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT sab, COUNT(*) AS count
                FROM codes
                GROUP BY sab
                ORDER BY sab
                """
            ).fetchall()
            return {str(row["sab"]): int(row["count"] or 0) for row in rows}

    def lookup_cui(self, cui: str, *, limit: int = 250) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT cui, sab, code, scui, sdui, tty, label, ispref, suppress
            FROM codes
            WHERE cui = ?
            LIMIT ?
            """,
            (cui.strip().upper(), limit),
        ).fetchall()
        return dedupe_code_rows(rows)

    def lookup_code(self, code: str, *, sab: str = "", limit: int = 250) -> list[dict]:
        code = str(code or "").strip()
        if not code:
            return []
        sab = normalize_sab(sab) if sab else ""
        if sab:
            rows = self.conn.execute(
                """
                SELECT cui, sab, code, scui, sdui, tty, label, ispref, suppress
                FROM codes
                WHERE sab = ?
                  AND (
                    code = ? COLLATE NOCASE
                    OR scui = ? COLLATE NOCASE
                    OR sdui = ? COLLATE NOCASE
                  )
                LIMIT ?
                """,
                (sab, code, code, code, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT cui, sab, code, scui, sdui, tty, label, ispref, suppress
                FROM codes
                WHERE code = ? COLLATE NOCASE
                   OR scui = ? COLLATE NOCASE
                   OR sdui = ? COLLATE NOCASE
                LIMIT ?
                """,
                (code, code, code, limit),
            ).fetchall()
        return dedupe_code_rows(rows)

    def lookup_identifier(
        self,
        identifier: str,
        *,
        identifier_type: str = "",
        sab: str = "",
        limit: int = 250,
    ) -> list[dict]:
        identifier = str(identifier or "").strip()
        if not identifier:
            return []
        identifier_type = normalize_sab(identifier_type or infer_identifier_type(identifier) or "CODE")
        sab = normalize_sab(sab) if sab else ""
        if identifier_type == "CUI":
            return self.lookup_cui(identifier, limit=limit)
        if identifier_type in {"CODE", "SCUI", "SDUI"} and not sab:
            return self.lookup_code(identifier, limit=limit)
        if identifier_type in {"CODE", "SCUI", "SDUI"} and sab:
            column = {"CODE": "code", "SCUI": "scui", "SDUI": "sdui"}[identifier_type]
            rows = self.conn.execute(
                f"""
                SELECT cui, sab, code, scui, sdui, tty, label, ispref, suppress
                FROM codes
                WHERE sab = ?
                  AND {column} = ? COLLATE NOCASE
                LIMIT ?
                """,
                (sab, identifier, limit),
            ).fetchall()
            return dedupe_code_rows(rows)
        rows = self.conn.execute(
            """
            SELECT cui, sab, code, scui, sdui, tty, label, ispref, suppress
            FROM identifiers
            WHERE identifier_type = ?
              AND identifier = ? COLLATE NOCASE
            LIMIT ?
            """,
            (identifier_type, identifier, limit),
        ).fetchall()
        return dedupe_code_rows(rows)

    def lookup_labels(self, norms: list[str], *, limit: int = 5000) -> list[dict]:
        rows: list[sqlite3.Row] = []
        seen_norms = list(dict.fromkeys(norm for norm in norms if norm))
        for norm_chunk in chunks(seen_norms):
            if len(rows) >= limit:
                break
            placeholders = ",".join("?" for _ in norm_chunk)
            remaining = max(limit - len(rows), 1)
            rows.extend(
                self.conn.execute(
                    f"""
                    SELECT norm, token_count, cui, label, sab, tty, ispref, suppress
                    FROM labels
                    WHERE norm IN ({placeholders})
                    LIMIT ?
                    """,
                    (*norm_chunk, remaining),
                ).fetchall()
            )
        return [dict_for_label_row(row) for row in rows]

    def best_name(self, cui: str) -> str:
        cui = cui.strip().upper()
        cached = self._name_cache.get(cui)
        if cached is not None:
            return cached
        rows = self.lookup_cui(cui, limit=300)
        name = sorted(rows, key=name_row_sort_key)[0]["label"] if rows else cui
        self._name_cache[cui] = name
        return name

    def semantic_types(self, cui: str) -> list[dict]:
        cui = cui.strip().upper()
        cached = self._semantic_type_cache.get(cui)
        if cached is not None:
            return cached
        rows = self.conn.execute(
            """
            SELECT tui, name
            FROM semantic_types
            WHERE cui = ?
            ORDER BY tui
            """,
            (cui,),
        ).fetchall()
        result = [{"tui": row["tui"], "name": row["name"]} for row in rows]
        self._semantic_type_cache[cui] = result
        return result

    def codes_for_cui(self, cui: str, *, limit: int = DEFAULT_CODE_LIMIT) -> list[dict]:
        key = (cui.strip().upper(), limit)
        cached = self._code_cache.get(key)
        if cached is not None:
            return cached
        rows = [
            row
            for row in self.lookup_cui(cui, limit=max(limit * 8, 200))
            if row["code"].strip().upper() not in SKIP_CODES
        ]
        result = sorted(rows, key=code_row_sort_key)[:limit]
        for row in result:
            row["system"] = row["sab"]
            row["source_asserted_code"] = row["code"]
        self._code_cache[key] = result
        return result

    def _quality_bonus(self, row: dict) -> float:
        bonus = 0.0
        if row.get("ispref") == "Y":
            bonus += 1.0
        bonus += max(0.0, 1.5 - (NAME_SAB_PRIORITY.get(row.get("sab", ""), 30) * 0.05))
        if row.get("suppress") != "N":
            bonus -= 4.0
        return bonus

    def _add_match(self, found: dict, row: dict, match: dict) -> None:
        cui = row["cui"].strip().upper()
        if not cui:
            return
        entry = found.setdefault(cui, {"score": 0.0, "matches": []})
        score = float(match["score"]) + self._quality_bonus(row)
        entry["score"] = max(entry["score"], score)
        item = dict(match)
        item.update(
            {
                "score": round(score, 3),
                "label": row.get("label", ""),
                "sab": row.get("sab", ""),
                "tty": row.get("tty", ""),
                "code": row.get("code", ""),
            }
        )
        key = (
            item.get("type", ""),
            item.get("text", ""),
            item.get("label", ""),
            item.get("sab", ""),
            item.get("code", ""),
        )
        existing_keys = {
            (
                existing.get("type", ""),
                existing.get("text", ""),
                existing.get("label", ""),
                existing.get("sab", ""),
                existing.get("code", ""),
            )
            for existing in entry["matches"]
        }
        if key not in existing_keys and len(entry["matches"]) < 12:
            entry["matches"].append(item)

    def resolve(
        self,
        text: str,
        *,
        limit: int = DEFAULT_RESULT_LIMIT,
        code_limit: int = DEFAULT_CODE_LIMIT,
        max_phrase_tokens: int = DEFAULT_MAX_PHRASE_TOKENS,
    ) -> dict:
        with self._lock:
            return self._resolve_unlocked(
                text,
                limit=limit,
                code_limit=code_limit,
                max_phrase_tokens=max_phrase_tokens,
            )

    def _resolve_unlocked(
        self,
        text: str,
        *,
        limit: int = DEFAULT_RESULT_LIMIT,
        code_limit: int = DEFAULT_CODE_LIMIT,
        max_phrase_tokens: int = DEFAULT_MAX_PHRASE_TOKENS,
    ) -> dict:
        query = str(text or "")
        found: dict[str, dict] = {}
        covered_code_spans: list[tuple[int, int]] = []
        unresolved_codes: list[dict] = []

        for match in CUI_RE.finditer(query):
            cui = match.group(0).upper()
            rows = self.lookup_cui(cui)
            for row in rows[:20]:
                self._add_match(
                    found,
                    row,
                    {
                        "type": "cui",
                        "text": match.group(0),
                        "start": match.start(),
                        "end": match.end(),
                        "score": 100.0,
                    },
                )

        for mention in iter_system_code_mentions(query):
            covered_code_spans.append((mention["start"], mention["end"]))
            system = mention["system"]
            code = mention["code"]
            if system in IDENTIFIER_TYPES:
                rows = self.lookup_identifier(code, identifier_type=system)
                match_type = "identifier"
            else:
                rows = self.lookup_code(code, sab=system)
                match_type = "system_code"
            if not rows:
                unresolved_codes.append({"system": system, "code": code, "text": mention["text"]})
                continue
            for row in rows[:40]:
                self._add_match(
                    found,
                    row,
                    {
                        "type": match_type,
                        "system": system,
                        "text": mention["text"],
                        "start": mention["start"],
                        "end": mention["end"],
                        "score": 96.0,
                    },
                )

        for match in CODE_TOKEN_RE.finditer(query):
            if overlaps((match.start(), match.end()), covered_code_spans):
                continue
            token = match.group(1)
            if is_cui(token):
                continue
            rows = self.lookup_code(token)
            if not rows:
                continue
            for row in rows[:30]:
                self._add_match(
                    found,
                    row,
                    {
                        "type": "code",
                        "text": token,
                        "start": match.start(),
                        "end": match.end(),
                        "score": 88.0,
                    },
                )

        phrases = phrase_candidates(query, max_tokens=max_phrase_tokens)
        label_norms = sorted(phrases, key=lambda norm: (-phrases[norm]["token_count"], norm))
        label_rows = self.lookup_labels(label_norms, limit=max(limit * 400, 4000))
        full_query_norm = normalized_key(query)
        for row in label_rows:
            phrase = phrases.get(row["norm"])
            if not phrase:
                continue
            span = phrase["spans"][0]
            score = 70.0 + min(phrase["token_count"], max_phrase_tokens) * 3.0
            if row["norm"] == full_query_norm:
                score += 15.0
            self._add_match(
                found,
                row,
                {
                    "type": "text",
                    "text": span["text"],
                    "start": span["start"],
                    "end": span["end"],
                    "score": score,
                },
            )

        results = []
        for cui, entry in found.items():
            matches = sorted(entry["matches"], key=lambda item: (-float(item["score"]), item["start"], item["text"]))
            results.append(
                {
                    "cui": cui,
                    "name": self.best_name(cui),
                    "score": round(float(entry["score"]), 3),
                    "semantic_types": self.semantic_types(cui),
                    "codes": self.codes_for_cui(cui, limit=code_limit),
                    "matches": matches,
                }
            )
        results.sort(key=lambda item: (-float(item["score"]), item["name"].lower(), item["cui"]))
        return {
            "api_version": API_VERSION,
            "query": query,
            "characters": len(query),
            "max_phrase_tokens": max_phrase_tokens,
            "result_count": min(len(results), limit),
            "results": results[:limit],
            "unresolved_codes": unresolved_codes,
        }


HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>UMLS Resolver</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f8fa;
      --panel: #ffffff;
      --line: #d9dee7;
      --ink: #17202e;
      --muted: #5b6472;
      --accent: #0f766e;
      --accent-ink: #ffffff;
      --chip: #eef2f6;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
    }
    main {
      width: min(1180px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 24px 0 48px;
    }
    header {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 16px;
    }
    h1 {
      margin: 0;
      font-size: 24px;
      line-height: 1.15;
      letter-spacing: 0;
    }
    .status {
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }
    form {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: end;
      margin-bottom: 18px;
    }
    textarea {
      width: 100%;
      min-height: 116px;
      resize: vertical;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px 13px;
      font: inherit;
      line-height: 1.45;
      background: var(--panel);
      color: var(--ink);
    }
    button {
      height: 44px;
      border: 0;
      border-radius: 8px;
      padding: 0 18px;
      font: inherit;
      font-weight: 650;
      color: var(--accent-ink);
      background: var(--accent);
      cursor: pointer;
    }
    button:disabled { opacity: 0.65; cursor: wait; }
    .result {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 14px;
      margin-bottom: 10px;
    }
    .head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 8px;
    }
    h2 {
      margin: 0;
      font-size: 18px;
      line-height: 1.25;
      letter-spacing: 0;
    }
    .mono {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 13px;
    }
    .muted { color: var(--muted); }
    .chips {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin: 8px 0;
    }
    .chip {
      display: inline-flex;
      gap: 5px;
      align-items: center;
      border-radius: 999px;
      padding: 4px 8px;
      background: var(--chip);
      font-size: 12px;
      max-width: 100%;
    }
    .matches {
      display: grid;
      gap: 6px;
      margin-top: 8px;
      font-size: 13px;
    }
    .empty, .error {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 16px;
      color: var(--muted);
    }
    .error { border-color: #f1a8a8; color: #8a1f1f; }
    @media (max-width: 720px) {
      main { width: min(100vw - 20px, 1180px); padding-top: 14px; }
      header, .head { align-items: flex-start; flex-direction: column; }
      form { grid-template-columns: 1fr; }
      button { width: 100%; }
      .status { white-space: normal; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>UMLS Resolver</h1>
      <div id="status" class="status">Loading</div>
    </header>
    <form id="form">
      <textarea id="query" autofocus spellcheck="false" placeholder="Paste text, C0004238, ICD10CM:I48.91, SNOMED CT US 49436004"></textarea>
      <button id="submit" type="submit">Resolve</button>
    </form>
    <section id="results" aria-live="polite"></section>
  </main>
  <script>
    const statusEl = document.getElementById("status");
    const form = document.getElementById("form");
    const queryEl = document.getElementById("query");
    const submitEl = document.getElementById("submit");
    const resultsEl = document.getElementById("results");

    function esc(value) {
      return String(value ?? "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }[char]));
    }

    function render(payload) {
      const results = payload.results || [];
      if (!results.length) {
        resultsEl.innerHTML = '<div class="empty">No UMLS matches found.</div>';
        return;
      }
      resultsEl.innerHTML = results.map((item) => {
        const types = (item.semantic_types || []).slice(0, 4).map((type) =>
          `<span class="chip">${esc(type.tui)} ${esc(type.name)}</span>`
        ).join("");
        const codes = (item.codes || []).slice(0, 12).map((code) =>
          `<span class="chip"><span class="mono">${esc(code.sab)}:${esc(code.code)}</span> ${esc(code.label)}</span>`
        ).join("");
        const matches = (item.matches || []).slice(0, 6).map((match) =>
          `<div><span class="mono">${esc(match.type)}</span> ${esc(match.text)} -> ${esc(match.label)} <span class="muted">${esc(match.sab)} ${esc(match.tty)}</span></div>`
        ).join("");
        return `<article class="result">
          <div class="head">
            <h2>${esc(item.name)}</h2>
            <div class="mono">${esc(item.cui)} score ${esc(item.score)}</div>
          </div>
          <div class="chips">${types}</div>
          <div class="chips">${codes}</div>
          <div class="matches">${matches}</div>
        </article>`;
      }).join("");
    }

    async function loadStatus() {
      try {
        const response = await fetch("/api/health");
        const payload = await response.json();
        statusEl.textContent = `${payload.codes_rows || 0} code rows, ${payload.labels_rows || 0} label rows`;
      } catch {
        statusEl.textContent = "Status unavailable";
      }
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const q = queryEl.value;
      submitEl.disabled = true;
      resultsEl.innerHTML = '<div class="empty">Resolving...</div>';
      try {
        const response = await fetch("/api/resolve", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({q, limit: 25})
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "request failed");
        render(payload);
      } catch (error) {
        resultsEl.innerHTML = `<div class="error">${esc(error.message)}</div>`;
      } finally {
        submitEl.disabled = false;
      }
    });
    loadStatus();
  </script>
</body>
</html>
"""


def json_response(handler: BaseHTTPRequestHandler, payload: dict, *, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def text_response(handler: BaseHTTPRequestHandler, body: str, *, status: int = 200, content_type: str = "text/html; charset=utf-8") -> None:
    data = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def make_handler(resolver: UMLSResolver):
    class ResolverHandler(BaseHTTPRequestHandler):
        server_version = "UMLSResolver/1.0"

        def log_message(self, fmt: str, *args) -> None:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                text_response(self, HTML_PAGE)
                return
            if parsed.path == "/api/health":
                metadata = resolver.metadata()
                payload = {
                    "ok": True,
                    "api_version": API_VERSION,
                    "index": str(resolver.index),
                    **metadata,
                }
                json_response(self, payload)
                return
            if parsed.path == "/api/resolve":
                params = parse_qs(parsed.query)
                query = params.get("q", [""])[0]
                limit = parse_int(params.get("limit", ["25"])[0], default=25, minimum=1, maximum=100)
                code_limit = parse_int(
                    params.get("code_limit", ["40"])[0],
                    default=40,
                    minimum=0,
                    maximum=1000,
                )
                json_response(self, resolver.resolve(query, limit=limit, code_limit=code_limit))
                return
            json_response(self, {"error": "not found"}, status=404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/api/resolve":
                json_response(self, {"error": "not found"}, status=404)
                return
            length = parse_int(self.headers.get("Content-Length", "0"), default=0, minimum=0, maximum=20_000_000)
            raw = self.rfile.read(length)
            content_type = self.headers.get("Content-Type", "")
            try:
                if "application/json" in content_type:
                    payload = json.loads(raw.decode("utf-8") or "{}")
                    query = str(payload.get("q", ""))
                    limit = parse_int(payload.get("limit", 25), default=25, minimum=1, maximum=100)
                    code_limit = parse_int(
                        payload.get("code_limit", 40),
                        default=40,
                        minimum=0,
                        maximum=1000,
                    )
                else:
                    query = raw.decode("utf-8", errors="replace")
                    limit = 25
                    code_limit = 40
            except Exception as exc:
                json_response(self, {"error": str(exc)}, status=400)
                return
            json_response(self, resolver.resolve(query, limit=limit, code_limit=code_limit))

    return ResolverHandler


def parse_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def serve(index: str | Path, *, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    resolver = UMLSResolver(index)
    try:
        server = ThreadingHTTPServer((host, port), make_handler(resolver))
        print(f"Serving UMLS resolver on http://{host}:{port}", file=sys.stderr)
        server.serve_forever()
    finally:
        resolver.close()


def parse_canary(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise ValueError(f"canary must be QUERY=CUI, got: {value}")
    query, expected_cui = value.rsplit("=", 1)
    query = query.strip()
    expected_cui = expected_cui.strip().upper()
    if not query or not is_cui(expected_cui):
        raise ValueError(f"canary must be QUERY=CUI with a valid CUI, got: {value}")
    return query, expected_cui


def audit_index(
    index: str | Path,
    *,
    min_labels: int = 1,
    min_codes: int = 1,
    min_semantic_types: int = 0,
    required_sabs: Iterable[str] = (),
    canaries: Iterable[tuple[str, str]] = DEFAULT_AUDIT_CANARIES,
) -> dict:
    resolver = UMLSResolver(index)
    checks = []
    failures = []

    def add_check(name: str, ok: bool, **details: object) -> None:
        check = {"name": name, "ok": bool(ok), **details}
        checks.append(check)
        if not ok:
            failures.append(check)

    try:
        metadata = resolver.metadata()
        labels = int(metadata.get("labels_rows") or 0)
        codes = int(metadata.get("codes_rows") or 0)
        semantic_types = int(metadata.get("semantic_types_rows") or 0)
        add_check("min_labels", labels >= min_labels, actual=labels, expected_min=min_labels)
        add_check("min_codes", codes >= min_codes, actual=codes, expected_min=min_codes)
        add_check(
            "min_semantic_types",
            semantic_types >= min_semantic_types,
            actual=semantic_types,
            expected_min=min_semantic_types,
        )

        source_counts = resolver.source_counts()
        for sab in required_sabs:
            normalized_sab = normalize_sab(sab)
            actual = int(source_counts.get(normalized_sab, 0))
            add_check(
                f"required_sab:{normalized_sab}",
                actual > 0,
                sab=normalized_sab,
                actual=actual,
            )

        for query, expected_cui in canaries:
            payload = resolver.resolve(query, limit=10, code_limit=10)
            actual_cuis = [str(item.get("cui") or "") for item in payload.get("results") or []]
            add_check(
                f"canary:{query}",
                expected_cui in actual_cuis,
                query=query,
                expected_cui=expected_cui,
                actual_cuis=actual_cuis[:10],
            )

        return {
            "ok": not failures,
            "api_version": API_VERSION,
            "index": str(Path(index).expanduser()),
            "metadata": metadata,
            "source_counts": source_counts,
            "checks": checks,
            "failures": failures,
        }
    finally:
        resolver.close()


def resolve_cli(args: argparse.Namespace) -> int:
    resolver = UMLSResolver(args.index)
    try:
        if args.stdin:
            query = sys.stdin.read()
        elif args.query:
            query = " ".join(args.query)
        else:
            query = sys.stdin.read()
        payload = resolver.resolve(query, limit=args.limit, code_limit=args.code_limit)
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    finally:
        resolver.close()
    return 0


def audit_cli(args: argparse.Namespace) -> int:
    canaries = [] if args.no_default_canaries else list(DEFAULT_AUDIT_CANARIES)
    for value in args.canary or []:
        canaries.append(parse_canary(value))
    payload = audit_index(
        args.index,
        min_labels=args.min_labels,
        min_codes=args.min_codes,
        min_semantic_types=args.min_semantic_types,
        required_sabs=args.require_sab or [],
        canaries=canaries,
    )
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if payload["ok"] else 1


def build_cli(args: argparse.Namespace) -> int:
    stats = build_index(
        umls_meta=args.umls_meta,
        mrconso=args.mrconso,
        mrsty=args.mrsty,
        index=args.index,
        language=args.language,
        include_suppressed=args.include_suppressed,
        replace=not args.no_replace,
    )
    json.dump(stats, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def serve_cli(args: argparse.Namespace) -> int:
    serve(args.index, host=args.host, port=args.port)
    return 0


def add_common_index_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX, help="SQLite resolver index path.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tiny UMLS CUI/code/text resolver.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build the SQLite resolver index from UMLS META files.")
    add_common_index_arg(build)
    build.add_argument("--umls-meta", type=Path, help="Directory containing MRCONSO.RRF and optional MRSTY.RRF.")
    build.add_argument("--mrconso", type=Path, help="Direct path to MRCONSO.RRF.")
    build.add_argument("--mrsty", type=Path, help="Optional direct path to MRSTY.RRF.")
    build.add_argument("--language", default=DEFAULT_LANGUAGE, help="MRCONSO language filter, default ENG.")
    build.add_argument("--include-suppressed", action="store_true", help="Include suppressed UMLS atoms.")
    build.add_argument("--no-replace", action="store_true", help="Append to an existing compatible index.")
    build.set_defaults(func=build_cli)

    resolve = subparsers.add_parser("resolve", help="Resolve text, CUIs, and codes to UMLS CUIs.")
    add_common_index_arg(resolve)
    resolve.add_argument("query", nargs="*", help="Input text. If omitted, stdin is read.")
    resolve.add_argument("--stdin", action="store_true", help="Read input text from stdin.")
    resolve.add_argument("--limit", type=int, default=DEFAULT_RESULT_LIMIT, help="Maximum CUI results.")
    resolve.add_argument("--code-limit", type=int, default=DEFAULT_CODE_LIMIT, help="Maximum code rows per CUI.")
    resolve.set_defaults(func=resolve_cli)

    audit = subparsers.add_parser("audit", help="Validate a built index with row-count, source, and canary checks.")
    add_common_index_arg(audit)
    audit.add_argument("--min-labels", type=int, default=1, help="Minimum indexed label rows.")
    audit.add_argument("--min-codes", type=int, default=1, help="Minimum indexed source-code rows.")
    audit.add_argument("--min-semantic-types", type=int, default=0, help="Minimum indexed semantic-type rows.")
    audit.add_argument(
        "--require-sab",
        action="append",
        default=[],
        help="Require at least one code row from this source vocabulary. Repeatable.",
    )
    audit.add_argument(
        "--canary",
        action="append",
        default=[],
        help="Expected resolver result in QUERY=CUI form. Repeatable.",
    )
    audit.add_argument(
        "--no-default-canaries",
        action="store_true",
        help="Skip built-in atrial-fibrillation canaries and use only explicit --canary values.",
    )
    audit.set_defaults(func=audit_cli)

    run = subparsers.add_parser("serve", help="Serve the browser search box and JSON API.")
    add_common_index_arg(run)
    run.add_argument("--host", default=os.environ.get("HOST", DEFAULT_HOST))
    run.add_argument("--port", type=int, default=int(os.environ.get("PORT", DEFAULT_PORT)))
    run.set_defaults(func=serve_cli)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
