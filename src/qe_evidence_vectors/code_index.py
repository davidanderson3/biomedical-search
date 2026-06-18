from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path
from typing import Iterable

from .lexical_normalization import (
    lexical_normalized_key,
    lexical_normalized_tokens,
    lexical_variant_keys,
)
from .text import normalized_key


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
DEFAULT_LEGACY_IDENTIFIER_TYPES = ("CUI", "CODE", "SCUI", "SDUI", "AUI")
LEGACY_IDENTIFIER_TYPES = frozenset(DEFAULT_LEGACY_IDENTIFIER_TYPES)
LEGACY_GLOBAL_IDENTIFIER_TYPES = frozenset({"CUI", "AUI"})

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

SOURCE_ATOM_SEARCH_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "patient",
    "patients",
    "search",
    "source",
    "the",
    "to",
    "with",
}

RXNORM_PRODUCT_TTYS = {
    "BPCK",
    "GPCK",
    "SBDC",
    "SBDF",
    "SBDG",
    "SCD",
    "SCDC",
    "SCDF",
    "SCDG",
}
RXNORM_INGREDIENT_TTYS = {"IN", "MIN", "PIN"}
LNC_OBSERVATION_TTYS = {"LC", "LN", "OSN", "DN"}
LNC_PART_TTYS = {"CN", "LPN", "LPDN"}
LNC_NON_OBSERVATION_CODE_PREFIXES = ("LA", "LP", "MTHU")

TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS code_mappings (
    cui TEXT NOT NULL,
    sab TEXT NOT NULL,
    code TEXT NOT NULL,
    aui TEXT NOT NULL DEFAULT '',
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
CREATE TABLE IF NOT EXISTS legacy_identifier_mappings (
    cui TEXT NOT NULL,
    identifier_type TEXT NOT NULL,
    identifier TEXT NOT NULL,
    sab TEXT NOT NULL,
    code TEXT NOT NULL,
    aui TEXT NOT NULL,
    scui TEXT NOT NULL,
    sdui TEXT NOT NULL,
    tty TEXT NOT NULL,
    label TEXT NOT NULL,
    ispref TEXT NOT NULL,
    suppress TEXT NOT NULL,
    last_release TEXT NOT NULL
);
"""

INDEX_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_code_mappings_cui
ON code_mappings(cui);
CREATE INDEX IF NOT EXISTS idx_code_mappings_sab_code
ON code_mappings(sab, code COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_code_mappings_code
ON code_mappings(code COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_code_mappings_aui
ON code_mappings(aui COLLATE NOCASE);
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
CREATE INDEX IF NOT EXISTS idx_legacy_identifier_mappings_identifier
ON legacy_identifier_mappings(identifier_type, identifier COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_legacy_identifier_mappings_sab_identifier
ON legacy_identifier_mappings(sab, identifier_type, identifier COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_legacy_identifier_mappings_cui
ON legacy_identifier_mappings(cui);
CREATE INDEX IF NOT EXISTS idx_legacy_identifier_mappings_sab_code
ON legacy_identifier_mappings(sab, code COLLATE NOCASE);
CREATE UNIQUE INDEX IF NOT EXISTS idx_legacy_identifier_mappings_unique
ON legacy_identifier_mappings(
    identifier_type,
    sab,
    identifier COLLATE NOCASE,
    cui,
    code,
    aui,
    last_release
);
"""

RUNTIME_INDEX_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_code_mappings_cui
ON code_mappings(cui);
CREATE INDEX IF NOT EXISTS idx_code_mappings_sab_code
ON code_mappings(sab, code COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_code_mappings_code
ON code_mappings(code COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_code_mappings_aui
ON code_mappings(aui COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_code_mappings_scui
ON code_mappings(scui COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_code_mappings_sdui
ON code_mappings(sdui COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_preferred_terms_cui
ON preferred_terms(cui);
"""

RUNTIME_SEARCH_LABEL_SCHEMA = """
CREATE TABLE IF NOT EXISTS search_labels (
    norm TEXT NOT NULL,
    atom_id INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_search_labels_norm
ON search_labels(norm);
"""

RUNTIME_LEGACY_INDEX_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_legacy_identifier_mappings_identifier
ON legacy_identifier_mappings(identifier_type, identifier COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_legacy_identifier_mappings_sab_identifier
ON legacy_identifier_mappings(sab, identifier_type, identifier COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_legacy_identifier_mappings_cui
ON legacy_identifier_mappings(cui);
CREATE INDEX IF NOT EXISTS idx_legacy_identifier_mappings_sab_code
ON legacy_identifier_mappings(sab, code COLLATE NOCASE);
CREATE UNIQUE INDEX IF NOT EXISTS idx_legacy_identifier_mappings_unique
ON legacy_identifier_mappings(
    identifier_type,
    sab,
    identifier COLLATE NOCASE,
    cui,
    code,
    aui,
    last_release
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


def _row_text(row: sqlite3.Row, key: str) -> str:
    if key not in row.keys():
        return ""
    return str(row[key] or "")


def _release_sort_value(value: object) -> int:
    text = str(value or "").strip().upper()
    match = re.match(r"^(\d{4})([A-Z]{2})$", text)
    if not match:
        return 0
    suffix = match.group(2)
    suffix_value = ((ord(suffix[0]) - ord("A")) * 26) + (ord(suffix[1]) - ord("A"))
    return (int(match.group(1)) * 1000) + suffix_value


def _sort_key(row: sqlite3.Row) -> tuple[int, int, int, int, str, str]:
    return (
        0 if row["suppress"] == "N" else 1,
        TTY_PRIORITY.get(str(row["tty"]), 99),
        0 if row["ispref"] == "Y" else 1,
        SAB_PRIORITY.get(str(row["sab"]), 99),
        -_release_sort_value(_row_text(row, "last_release")),
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
    if "aui" in row.keys():
        result["aui"] = _row_text(row, "aui")
    if "identifier_type" in row.keys():
        result["matched_identifier_type"] = row["identifier_type"]
    if "identifier" in row.keys():
        result["matched_identifier"] = row["identifier"]
    if "last_release" in row.keys():
        result["legacy_identifier_only"] = True
        result["legacy_last_release"] = row["last_release"]
        result["last_release"] = row["last_release"]
        result["legacy_aui"] = _row_text(row, "aui")
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


def _search_label_word_match(row_norm: str, tokens: list[str], *, partial: bool) -> bool:
    row_tokens = set(str(row_norm or "").split())
    wanted = [token for token in tokens if token]
    if not wanted:
        return False
    if partial:
        return any(token in row_tokens for token in wanted)
    return all(token in row_tokens for token in wanted)


def _search_label_sort_key(row: dict, *, query_norm: str) -> tuple:
    label_norm = normalized_key(str(row.get("label") or ""))
    row_norm = str(row.get("norm") or "")
    return (
        0 if row_norm == query_norm or label_norm == query_norm else 1,
        0 if str(row.get("suppress") or "") == "N" else 1,
        0 if str(row.get("ispref") or "") == "Y" else 1,
        SAB_PRIORITY.get(str(row.get("sab") or ""), 99),
        TTY_PRIORITY.get(str(row.get("tty") or ""), 99),
        len(str(row.get("label") or "")),
        str(row.get("label") or "").lower(),
        str(row.get("cui") or ""),
        str(row.get("code") or ""),
    )


def _dedupe_search_label_rows(
    rows: Iterable[dict],
    *,
    query: str,
    search_type: str,
) -> list[dict]:
    query_norm = (
        lexical_normalized_key(query)
        if search_type in {"normalizedString", "normalizedWords"}
        else normalized_key(query)
    )
    best_by_key: dict[tuple[str, str, str, str, str], dict] = {}
    for row in rows:
        item = dict(row)
        key = (
            str(item.get("cui") or ""),
            str(item.get("label") or "").lower(),
            str(item.get("sab") or ""),
            str(item.get("tty") or ""),
            str(item.get("code") or ""),
        )
        current = best_by_key.get(key)
        if current is None or _search_label_sort_key(item, query_norm=query_norm) < _search_label_sort_key(
            current,
            query_norm=query_norm,
        ):
            best_by_key[key] = item
    return sorted(best_by_key.values(), key=lambda row: _search_label_sort_key(row, query_norm=query_norm))


def _source_atom_query_tokens(query: str) -> list[str]:
    tokens = []
    seen = set()
    for token in normalized_key(query).split():
        if token in SOURCE_ATOM_SEARCH_STOPWORDS:
            continue
        if len(token) < 2 and not any(char.isdigit() for char in token):
            continue
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _suppress_visibility_clause(include_obsolete: bool, include_suppressible: bool) -> str:
    if include_obsolete and include_suppressible:
        return "1 = 1"
    if include_obsolete:
        return "suppress IN ('N', 'O')"
    if include_suppressible:
        return "suppress IN ('N', 'E', 'Y')"
    return "suppress = 'N'"


def _source_atom_row_score(row: sqlite3.Row, *, query_norm: str, tokens: list[str]) -> float:
    label_norm = normalized_key(str(row["label"] or ""))
    label_tokens = label_norm.split()
    token_hits = sum(1 for token in tokens if token in label_tokens or token in label_norm)
    coverage = token_hits / max(len(tokens), 1)
    exact_bonus = 0.45 if label_norm == query_norm else 0.0
    prefix_bonus = 0.18 if query_norm and label_norm.startswith(query_norm) else 0.0
    preferred_bonus = 0.03 if str(row["ispref"] or "") == "Y" else 0.0
    suppress_penalty = 0.50 if str(row["suppress"] or "") != "N" else 0.0
    tty = str(row["tty"] or "").upper()
    sab = str(row["sab"] or "").upper()
    code = str(row["code"] or "").upper()
    label = str(row["label"] or "")
    vocabulary_bonus = 0.0
    vocabulary_penalty = 0.0
    if sab == "RXNORM":
        if tty == "IN":
            vocabulary_bonus = 0.45
        elif tty == "PIN":
            vocabulary_bonus = 0.20
        elif tty == "MIN":
            vocabulary_bonus = 0.10
            if len(tokens) <= 1:
                vocabulary_penalty += 0.25
            if "/" in label:
                vocabulary_penalty += 0.25
        elif tty in RXNORM_PRODUCT_TTYS:
            if len(tokens) <= 1:
                vocabulary_penalty += 0.35
            if "/" in label:
                vocabulary_penalty += 0.20
    elif sab == "LNC":
        if code.startswith(LNC_NON_OBSERVATION_CODE_PREFIXES):
            vocabulary_penalty += 0.55
        if tty in LNC_PART_TTYS:
            vocabulary_penalty += 0.35
        elif tty in LNC_OBSERVATION_TTYS and looks_like_code(code):
            vocabulary_bonus = 0.20
        label_token_set = set(label_tokens)
        token_set = set(tokens)
        if "device" in label_token_set and "device" not in token_set:
            vocabulary_penalty += 0.45
        if "panel" in label_token_set and "panel" not in token_set:
            vocabulary_penalty += 0.30
        if "goal" in label_token_set and "goal" not in token_set:
            vocabulary_penalty += 0.25
        label_lower = label.lower()
        if {"hemoglobin", "a1c"}.issubset(token_set) and "hemoglobin.total" in label_lower:
            vocabulary_bonus += 0.25 if "hemoglobin.total in blood" in label_lower else 0.12
    length_penalty = min(max(len(label_tokens) - max(len(tokens), 1), 0), 20) * 0.004
    return (
        coverage
        + exact_bonus
        + prefix_bonus
        + preferred_bonus
        + vocabulary_bonus
        - vocabulary_penalty
        - suppress_penalty
        - length_penalty
    )


def _normalize_legacy_identifier_types(values: Iterable[str] | None = None) -> tuple[str, ...]:
    raw_values = tuple(values or DEFAULT_LEGACY_IDENTIFIER_TYPES)
    normalized = []
    for value in raw_values:
        identifier_type = normalize_sab(value)
        if identifier_type not in LEGACY_IDENTIFIER_TYPES:
            raise ValueError(
                "legacy identifier types must be drawn from: "
                + ", ".join(sorted(LEGACY_IDENTIFIER_TYPES))
            )
        if identifier_type not in normalized:
            normalized.append(identifier_type)
    return tuple(normalized)


def _connection_has_table(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _current_identifier_values(fields: list[str], identifier_types: set[str]) -> Iterable[tuple[str, str, str]]:
    cui = fields[0].strip()
    sab = fields[11].strip()
    code = fields[13].strip()
    if "CUI" in identifier_types and cui:
        yield ("CUI", "", cui.upper())
    for identifier_type, identifier in (
        ("CODE", code),
        ("SCUI", fields[9].strip()),
        ("SDUI", fields[10].strip()),
        ("AUI", fields[7].strip()),
    ):
        if identifier_type not in identifier_types or not identifier:
            continue
        identifier_sab = "" if identifier_type in LEGACY_GLOBAL_IDENTIFIER_TYPES else sab
        yield (identifier_type, identifier_sab, identifier)


def _legacy_identifier_stage_rows(
    fields: list[str],
    identifier_types: set[str],
) -> Iterable[tuple[str, str, str, str, str, str, str, str, str, str, str, str, str]]:
    cui = fields[0].strip().upper()
    sab = fields[11].strip()
    code = fields[13].strip()
    aui = fields[7].strip()
    scui = fields[9].strip()
    sdui = fields[10].strip()
    tty = fields[12].strip()
    label = fields[14].strip()
    ispref = fields[6].strip()
    suppress = fields[16].strip()
    last_release = fields[18].strip().upper()
    if not cui or not sab or not code or not label or not last_release:
        return
    for identifier_type, identifier in (
        ("CUI", cui),
        ("CODE", code),
        ("SCUI", scui),
        ("SDUI", sdui),
        ("AUI", aui),
    ):
        if identifier_type not in identifier_types or not identifier:
            continue
        yield (
            cui,
            identifier_type,
            identifier,
            sab,
            code,
            aui,
            scui,
            sdui,
            tty,
            label,
            ispref,
            suppress,
            last_release,
        )


def _load_current_identifier_keys_from_mrconso(
    conn: sqlite3.Connection,
    *,
    mrconso_path: str | Path,
    language: str,
    include_suppressed: bool,
    identifier_types: set[str],
    batch_size: int,
) -> int:
    insert_sql = """
        INSERT OR IGNORE INTO current_identifier_keys(identifier_type, sab, identifier)
        VALUES (?, ?, ?)
    """
    count = 0
    batch: list[tuple[str, str, str]] = []
    with Path(mrconso_path).expanduser().open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("|")
            if len(fields) < 18:
                continue
            if fields[1] != language:
                continue
            if not include_suppressed and fields[16] != "N":
                continue
            for row in _current_identifier_values(fields, identifier_types):
                batch.append(row)
            if len(batch) >= batch_size:
                conn.executemany(insert_sql, batch)
                conn.commit()
                count += len(batch)
                batch.clear()
    if batch:
        conn.executemany(insert_sql, batch)
        conn.commit()
        count += len(batch)
    return count


def _prepare_current_identifier_keys(
    conn: sqlite3.Connection,
    *,
    current_mrconso_path: str | Path | None,
    language: str,
    include_suppressed: bool,
    identifier_types: tuple[str, ...],
    batch_size: int,
) -> int:
    conn.execute("PRAGMA temp_store=FILE")
    conn.execute("DROP TABLE IF EXISTS temp.current_identifier_keys")
    conn.execute(
        """
        CREATE TEMP TABLE current_identifier_keys (
            identifier_type TEXT NOT NULL,
            sab TEXT NOT NULL,
            identifier TEXT COLLATE NOCASE NOT NULL,
            PRIMARY KEY(identifier_type, sab, identifier)
        ) WITHOUT ROWID
        """
    )
    wanted = set(identifier_types)
    count = 0
    if "CUI" in wanted:
        conn.execute(
            """
            INSERT OR IGNORE INTO current_identifier_keys(identifier_type, sab, identifier)
            SELECT 'CUI', '', cui
            FROM code_mappings
            WHERE cui <> ''
            """
        )
    if "CODE" in wanted:
        conn.execute(
            """
            INSERT OR IGNORE INTO current_identifier_keys(identifier_type, sab, identifier)
            SELECT 'CODE', sab, code
            FROM code_mappings
            WHERE sab <> '' AND code <> ''
            """
        )
    if "SCUI" in wanted:
        conn.execute(
            """
            INSERT OR IGNORE INTO current_identifier_keys(identifier_type, sab, identifier)
            SELECT 'SCUI', sab, scui
            FROM code_mappings
            WHERE sab <> '' AND scui <> ''
            """
        )
    if "SDUI" in wanted:
        conn.execute(
            """
            INSERT OR IGNORE INTO current_identifier_keys(identifier_type, sab, identifier)
            SELECT 'SDUI', sab, sdui
            FROM code_mappings
            WHERE sab <> '' AND sdui <> ''
            """
        )
    identifier_table_available = _connection_has_table(conn, "identifier_mappings")
    identifier_types_from_current_mrconso = set()
    if identifier_table_available:
        db_identifier_types = wanted & {"AUI"}
        if db_identifier_types:
            placeholders = ",".join("?" for _ in db_identifier_types)
            conn.execute(
                f"""
                INSERT OR IGNORE INTO current_identifier_keys(identifier_type, sab, identifier)
                SELECT identifier_type, '', identifier
                FROM identifier_mappings
                WHERE identifier_type IN ({placeholders})
                  AND identifier <> ''
                """,
                tuple(sorted(db_identifier_types)),
            )
    else:
        identifier_types_from_current_mrconso |= wanted & {"AUI"}
    conn.commit()
    if identifier_types_from_current_mrconso:
        if not current_mrconso_path:
            missing = ", ".join(sorted(identifier_types_from_current_mrconso))
            raise ValueError(
                f"current MRCONSO is required to exclude current {missing} identifiers "
                "when the code index has no identifier_mappings table"
            )
        count += _load_current_identifier_keys_from_mrconso(
            conn,
            mrconso_path=current_mrconso_path,
            language=language,
            include_suppressed=include_suppressed,
            identifier_types=identifier_types_from_current_mrconso,
            batch_size=batch_size,
        )
    row = conn.execute("SELECT COUNT(*) AS count FROM current_identifier_keys").fetchone()
    count = int(row["count"] or 0)
    return count


def add_legacy_identifier_mappings(
    *,
    mrconso_history_path: str | Path,
    out_path: str | Path,
    current_mrconso_path: str | Path | None = None,
    language: str = "ENG",
    include_suppressed: bool = False,
    replace: bool = False,
    batch_size: int = 50_000,
    identifier_types: Iterable[str] | None = None,
) -> int:
    out_path = Path(out_path).expanduser()
    conn = connect(out_path)
    if replace:
        conn.execute("DROP TABLE IF EXISTS legacy_identifier_mappings")
    conn.executescript(TABLE_SCHEMA)
    normalized_identifier_types = _normalize_legacy_identifier_types(identifier_types)
    _prepare_current_identifier_keys(
        conn,
        current_mrconso_path=current_mrconso_path,
        language=language,
        include_suppressed=include_suppressed,
        identifier_types=normalized_identifier_types,
        batch_size=batch_size,
    )
    conn.execute("DROP TABLE IF EXISTS temp.legacy_identifier_stage")
    conn.execute(
        """
        CREATE TEMP TABLE legacy_identifier_stage (
            cui TEXT NOT NULL,
            identifier_type TEXT NOT NULL,
            identifier TEXT COLLATE NOCASE NOT NULL,
            sab TEXT NOT NULL,
            code TEXT NOT NULL,
            aui TEXT NOT NULL,
            scui TEXT NOT NULL,
            sdui TEXT NOT NULL,
            tty TEXT NOT NULL,
            label TEXT NOT NULL,
            ispref TEXT NOT NULL,
            suppress TEXT NOT NULL,
            last_release TEXT NOT NULL
        )
        """
    )
    stage_insert_sql = """
        INSERT INTO legacy_identifier_stage(
            cui, identifier_type, identifier, sab, code, aui, scui, sdui,
            tty, label, ispref, suppress, last_release
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    persist_sql = """
        INSERT OR IGNORE INTO legacy_identifier_mappings(
            cui, identifier_type, identifier, sab, code, aui, scui, sdui,
            tty, label, ispref, suppress, last_release
        )
        SELECT
            s.cui,
            s.identifier_type,
            s.identifier,
            s.sab,
            s.code,
            s.aui,
            s.scui,
            s.sdui,
            s.tty,
            s.label,
            s.ispref,
            s.suppress,
            s.last_release
        FROM legacy_identifier_stage AS s
        WHERE NOT EXISTS (
            SELECT 1
            FROM current_identifier_keys AS c
            WHERE c.identifier_type = s.identifier_type
              AND c.identifier = s.identifier COLLATE NOCASE
              AND (
                s.identifier_type IN ('CUI', 'AUI')
                OR c.sab = s.sab
              )
        )
    """
    wanted = set(normalized_identifier_types)
    batch: list[tuple[str, str, str, str, str, str, str, str, str, str, str, str, str]] = []
    inserted = 0

    def flush() -> None:
        nonlocal inserted
        if not batch:
            return
        conn.execute("DELETE FROM legacy_identifier_stage")
        conn.executemany(stage_insert_sql, batch)
        before = conn.total_changes
        conn.execute(persist_sql)
        inserted += max(0, conn.total_changes - before)
        conn.commit()
        batch.clear()

    with Path(mrconso_history_path).expanduser().open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("|")
            if len(fields) < 19:
                continue
            if fields[1] != language:
                continue
            if not include_suppressed and fields[16] != "N":
                continue
            batch.extend(_legacy_identifier_stage_rows(fields, wanted))
            if len(batch) >= batch_size:
                flush()
    flush()
    conn.executescript(INDEX_SCHEMA)
    conn.commit()
    conn.close()
    return inserted


def build_code_index(
    *,
    mrconso_path: str | Path,
    out_path: str | Path,
    legacy_mrconso_history_path: str | Path | None = None,
    language: str = "ENG",
    include_suppressed: bool = False,
    replace: bool = False,
    batch_size: int = 50_000,
    legacy_identifier_types: Iterable[str] | None = None,
) -> int:
    out_path = Path(out_path).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(out_path)
    if replace:
        conn.execute("DROP TABLE IF EXISTS code_mappings")
        conn.execute("DROP TABLE IF EXISTS preferred_terms")
        conn.execute("DROP TABLE IF EXISTS identifier_mappings")
        conn.execute("DROP TABLE IF EXISTS legacy_identifier_mappings")
    conn.executescript(TABLE_SCHEMA)
    mapping_sql = """
        INSERT INTO code_mappings(cui, sab, code, aui, scui, sdui, tty, label, ispref, suppress)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    aui,
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
    if legacy_mrconso_history_path:
        add_legacy_identifier_mappings(
            mrconso_history_path=legacy_mrconso_history_path,
            out_path=out_path,
            current_mrconso_path=mrconso_path,
            language=language,
            include_suppressed=include_suppressed,
            replace=False,
            batch_size=batch_size,
            identifier_types=legacy_identifier_types,
        )
    return count


def _table_has_column(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    try:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    except sqlite3.OperationalError:
        return False
    return any(str(row[1]).lower() == column_name.lower() for row in rows)


def _code_mapping_label_norms(label: str) -> list[str]:
    return [norm for norm in lexical_variant_keys(label) if norm]


def _populate_runtime_search_labels(conn: sqlite3.Connection, *, batch_size: int = 100_000) -> int:
    conn.executescript(RUNTIME_SEARCH_LABEL_SCHEMA.split("CREATE INDEX", 1)[0])
    conn.execute("DELETE FROM search_labels")
    insert_sql = "INSERT INTO search_labels(norm, atom_id) VALUES (?, ?)"
    rows = conn.execute(
        """
        SELECT atom_id, label
        FROM code_mappings
        WHERE label <> ''
        """
    )
    batch: list[tuple[str, int]] = []
    count = 0
    for row in rows:
        atom_id = int(row["atom_id"])
        for norm in _code_mapping_label_norms(str(row["label"] or "")):
            batch.append((norm, atom_id))
        if len(batch) >= batch_size:
            conn.executemany(insert_sql, batch)
            conn.commit()
            count += len(batch)
            batch.clear()
    if batch:
        conn.executemany(insert_sql, batch)
        conn.commit()
        count += len(batch)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_search_labels_norm ON search_labels(norm)")
    conn.commit()
    return count


def build_runtime_code_index(
    *,
    source_path: str | Path,
    out_path: str | Path,
    replace: bool = False,
) -> dict[str, int | str]:
    source_path = Path(source_path).expanduser()
    out_path = Path(out_path).expanduser()
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    if out_path.exists() and not replace:
        raise FileExistsError(f"{out_path} already exists; pass replace=True to overwrite")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_paths = [Path(f"{out_path}-wal"), Path(f"{out_path}-shm")]
    if out_path.exists():
        out_path.unlink()
    for sidecar_path in sidecar_paths:
        if sidecar_path.exists():
            sidecar_path.unlink()

    conn = sqlite3.connect(str(out_path))
    conn.row_factory = sqlite3.Row
    attached = False
    try:
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("ATTACH DATABASE ? AS source", (str(source_path),))
        attached = True
        source_has_code_aui = conn.execute(
            """
            SELECT 1
            FROM source.pragma_table_info('code_mappings')
            WHERE name = 'aui'
            LIMIT 1
            """
        ).fetchone() is not None
        source_has_identifiers = conn.execute(
            """
            SELECT 1
            FROM source.sqlite_master
            WHERE type = 'table' AND name = 'identifier_mappings'
            LIMIT 1
            """
        ).fetchone() is not None
        if not source_has_code_aui and source_has_identifiers:
            conn.execute(
                """
                CREATE TEMP TABLE runtime_aui_mappings AS
                SELECT
                    cui, sab, code, scui, sdui, tty, label, ispref, suppress,
                    MIN(identifier) AS aui
                FROM source.identifier_mappings
                WHERE identifier_type = 'AUI'
                GROUP BY cui, sab, code, scui, sdui, tty, label, ispref, suppress
                """
            )
            conn.execute(
                """
                CREATE INDEX runtime_aui_mappings_key
                ON runtime_aui_mappings(
                    cui, sab, code, scui, sdui, tty, label, ispref, suppress
                )
                """
            )
            conn.commit()
        conn.execute(
            """
            CREATE TABLE code_mappings (
                atom_id INTEGER PRIMARY KEY,
                cui TEXT NOT NULL,
                sab TEXT NOT NULL,
                code TEXT NOT NULL,
                aui TEXT NOT NULL DEFAULT '',
                scui TEXT NOT NULL,
                sdui TEXT NOT NULL,
                tty TEXT NOT NULL,
                label TEXT NOT NULL,
                ispref TEXT NOT NULL,
                suppress TEXT NOT NULL
            )
            """
        )
        if source_has_code_aui:
            conn.execute(
                """
                INSERT INTO code_mappings(
                    atom_id, cui, sab, code, aui, scui, sdui, tty, label, ispref, suppress
                )
                SELECT rowid, cui, sab, code, aui, scui, sdui, tty, label, ispref, suppress
                FROM source.code_mappings
                """
            )
        elif source_has_identifiers:
            conn.execute(
                """
                INSERT INTO code_mappings(
                    atom_id, cui, sab, code, aui, scui, sdui, tty, label, ispref, suppress
                )
                SELECT
                    cm.rowid,
                    cm.cui,
                    cm.sab,
                    cm.code,
                    COALESCE(aui.aui, ''),
                    cm.scui,
                    cm.sdui,
                    cm.tty,
                    cm.label,
                    cm.ispref,
                    cm.suppress
                FROM source.code_mappings AS cm
                LEFT JOIN runtime_aui_mappings AS aui
                  ON aui.cui = cm.cui
                 AND aui.sab = cm.sab
                 AND aui.code = cm.code
                 AND aui.scui = cm.scui
                 AND aui.sdui = cm.sdui
                 AND aui.tty = cm.tty
                 AND aui.label = cm.label
                 AND aui.ispref = cm.ispref
                 AND aui.suppress = cm.suppress
                """
            )
        else:
            conn.execute(
                """
                INSERT INTO code_mappings(
                    atom_id, cui, sab, code, aui, scui, sdui, tty, label, ispref, suppress
                )
                SELECT rowid, cui, sab, code, '', scui, sdui, tty, label, ispref, suppress
                FROM source.code_mappings
                """
            )
        conn.execute(
            """
            CREATE TABLE preferred_terms AS
            SELECT cui, label, sab, code, tty, suppress
            FROM source.preferred_terms
            """
        )
        source_has_legacy_identifiers = conn.execute(
            """
            SELECT 1
            FROM source.sqlite_master
            WHERE type = 'table' AND name = 'legacy_identifier_mappings'
            LIMIT 1
            """
        ).fetchone() is not None
        if source_has_legacy_identifiers:
            conn.execute(
                """
                CREATE TABLE legacy_identifier_mappings AS
                SELECT
                    cui, identifier_type, identifier, sab, code, aui, scui, sdui,
                    tty, label, ispref, suppress, last_release
                FROM source.legacy_identifier_mappings
                """
            )
        conn.commit()
        conn.executescript(RUNTIME_INDEX_SCHEMA)
        if source_has_legacy_identifiers:
            conn.executescript(RUNTIME_LEGACY_INDEX_SCHEMA)
        conn.commit()
        search_label_rows = _populate_runtime_search_labels(conn)
        code_rows = int(conn.execute("SELECT COUNT(*) FROM code_mappings").fetchone()[0])
        preferred_rows = int(conn.execute("SELECT COUNT(*) FROM preferred_terms").fetchone()[0])
        aui_rows = int(
            conn.execute("SELECT COUNT(*) FROM code_mappings WHERE aui <> ''").fetchone()[0]
        )
        legacy_rows = (
            int(conn.execute("SELECT COUNT(*) FROM legacy_identifier_mappings").fetchone()[0])
            if source_has_legacy_identifiers
            else 0
        )
        conn.execute("PRAGMA optimize")
        conn.execute("VACUUM")
        conn.commit()
    finally:
        if attached:
            conn.execute("DETACH DATABASE source")
        conn.close()
    for sidecar_path in sidecar_paths:
        if sidecar_path.exists():
            sidecar_path.unlink()

    return {
        "source": str(source_path),
        "out": str(out_path),
        "code_mappings": code_rows,
        "preferred_terms": preferred_rows,
        "aui_mappings": aui_rows,
        "search_labels": search_label_rows,
        "legacy_identifier_mappings": legacy_rows,
        "bytes": out_path.stat().st_size,
    }


class CodeIndex:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self._local = threading.local()
        self.cache: dict[tuple, list[dict]] = {}
        self.preferred_cache: dict[str, str] = {}
        self.active_cui_cache: dict[str, bool] = {}
        self.legacy_cui_cache: dict[str, bool] = {}
        self.legacy_label_cache: dict[str, str] = {}
        self._mapping_count: int | None = None
        self._identifier_table_available: bool | None = None
        self._legacy_identifier_table_available: bool | None = None
        self._legacy_identifier_count: int | None = None
        self._code_mappings_has_aui: bool | None = None
        self._search_labels_table_available: bool | None = None

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

    def code_mappings_has_aui(self) -> bool:
        if self._code_mappings_has_aui is None:
            self._code_mappings_has_aui = _table_has_column(
                self.connection(),
                "code_mappings",
                "aui",
            )
        return self._code_mappings_has_aui

    def search_labels_table_available(self) -> bool:
        if self._search_labels_table_available is None:
            row = self.connection().execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table' AND name = 'search_labels'
                LIMIT 1
                """
            ).fetchone()
            self._search_labels_table_available = row is not None
        return self._search_labels_table_available

    def code_mapping_columns(self, alias: str = "") -> str:
        prefix = f"{alias}." if alias else ""
        columns = ["cui", "sab", "code"]
        if self.code_mappings_has_aui():
            columns.append("aui")
        columns.extend(["scui", "sdui", "tty", "label", "ispref", "suppress"])
        return ", ".join(f"{prefix}{column}" for column in columns)

    def legacy_identifier_table_available(self) -> bool:
        if self._legacy_identifier_table_available is None:
            row = self.connection().execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table' AND name = 'legacy_identifier_mappings'
                LIMIT 1
                """
            ).fetchone()
            self._legacy_identifier_table_available = row is not None
        return self._legacy_identifier_table_available

    def legacy_identifier_count(self) -> int:
        if self._legacy_identifier_count is None:
            if not self.legacy_identifier_table_available():
                self._legacy_identifier_count = 0
            else:
                row = self.connection().execute(
                    "SELECT COUNT(*) AS count FROM legacy_identifier_mappings"
                ).fetchone()
                self._legacy_identifier_count = int(row["count"] or 0)
        return self._legacy_identifier_count

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

    def has_legacy_cui(self, cui: str) -> bool:
        cui = cui.strip().upper()
        if not cui or not self.legacy_identifier_table_available():
            return False
        cached = self.legacy_cui_cache.get(cui)
        if cached is not None:
            return cached
        row = self.connection().execute(
            """
            SELECT 1
            FROM legacy_identifier_mappings
            WHERE cui = ?
            LIMIT 1
            """,
            (cui,),
        ).fetchone()
        active = row is not None
        self.legacy_cui_cache[cui] = active
        return active

    def legacy_label(self, cui: str) -> str:
        cui = cui.strip().upper()
        if not cui or not self.legacy_identifier_table_available():
            return ""
        cached = self.legacy_label_cache.get(cui)
        if cached is not None:
            return cached
        rows = list(
            self.connection().execute(
                """
                SELECT
                    cui, identifier_type, identifier, sab, code, aui, scui, sdui,
                    tty, label, ispref, suppress, last_release
                FROM legacy_identifier_mappings
                WHERE cui = ?
                LIMIT 200
                """,
                (cui,),
            )
        )
        label = ""
        if rows:
            label = str(sorted(rows, key=_sort_key)[0]["label"] or "")
        self.legacy_label_cache[cui] = label
        return label

    def lookup_cui(self, cui: str, *, sabs: Iterable[str] | None = None, limit: int = 100) -> list[dict]:
        cui = cui.strip().upper()
        sab_values = tuple(sorted(normalize_sab(sab) for sab in (sabs or []) if sab))
        key = ("cui", cui, sab_values, limit)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        query_limit = max(limit * 4, limit + 50)
        columns = self.code_mapping_columns()
        if sab_values:
            placeholders = ",".join("?" for _ in sab_values)
            rows = self.connection().execute(
                f"""
                SELECT {columns}
                FROM code_mappings
                WHERE cui = ? AND sab IN ({placeholders})
                LIMIT ?
                """,
                (cui, *sab_values, query_limit),
            )
        else:
            rows = self.connection().execute(
                f"""
                SELECT {columns}
                FROM code_mappings
                WHERE cui = ?
                LIMIT ?
                """,
                (cui, query_limit),
            )
        results = _dedupe_rows(rows)[:limit]
        self.cache[key] = results
        return results

    def search_source_atoms(
        self,
        query: str,
        *,
        sabs: Iterable[str],
        include_obsolete: bool = False,
        include_suppressible: bool = False,
        limit: int = 50,
    ) -> list[dict]:
        tokens = _source_atom_query_tokens(query)
        sab_values = tuple(sorted({normalize_sab(sab) for sab in (sabs or []) if sab}))
        if not tokens or not sab_values:
            return []
        key = (
            "source_atoms",
            normalized_key(query),
            sab_values,
            bool(include_obsolete),
            bool(include_suppressible),
            limit,
        )
        cached = self.cache.get(key)
        if cached is not None:
            return [dict(row) for row in cached]

        placeholders = ",".join("?" for _ in sab_values)
        text = str(query or "").strip()
        label_clauses = " AND ".join("label LIKE ? COLLATE NOCASE" for _token in tokens)
        visibility_clause = _suppress_visibility_clause(include_obsolete, include_suppressible)
        columns = self.code_mapping_columns()
        query_limit = max(limit * 20, limit + 250)
        rows: list[sqlite3.Row] = []
        exact_limit = max(limit * 4, limit + 20)
        if text:
            rows.extend(
                self.connection().execute(
                    f"""
                    SELECT {columns}
                    FROM code_mappings
                    WHERE sab IN ({placeholders})
                      AND {visibility_clause}
                      AND label = ? COLLATE NOCASE
                    LIMIT ?
                    """,
                    (*sab_values, text, exact_limit),
                )
            )
            rows.extend(
                self.connection().execute(
                    f"""
                    SELECT {columns}
                    FROM code_mappings
                    WHERE sab IN ({placeholders})
                      AND {visibility_clause}
                      AND label LIKE ? COLLATE NOCASE
                    LIMIT ?
                    """,
                    (*sab_values, f"{text}%", exact_limit),
                )
            )
        rows.extend(
            self.connection().execute(
                    f"""
                    SELECT {columns}
                    FROM code_mappings
                    WHERE sab IN ({placeholders})
                      AND {visibility_clause}
                      AND {label_clauses}
                    LIMIT ?
                    """,
                    (*sab_values, *(f"%{token}%" for token in tokens), query_limit),
            )
        )
        query_norm = normalized_key(query)
        best_by_code: dict[tuple[str, str], sqlite3.Row] = {}
        for row in rows:
            key_by_code = (str(row["sab"] or ""), str(row["code"] or "").upper())
            current = best_by_code.get(key_by_code)
            if current is None:
                best_by_code[key_by_code] = row
                continue
            current_score = _source_atom_row_score(
                current,
                query_norm=query_norm,
                tokens=tokens,
            )
            row_score = _source_atom_row_score(row, query_norm=query_norm, tokens=tokens)
            if row_score > current_score or (
                row_score == current_score and _sort_key(row) < _sort_key(current)
            ):
                best_by_code[key_by_code] = row

        ranked = []
        for row in best_by_code.values():
            item = _row_dict(row)
            item["source_atom_score"] = round(
                _source_atom_row_score(row, query_norm=query_norm, tokens=tokens),
                6,
            )
            item["matched_query_tokens"] = list(tokens)
            ranked.append(item)
        ranked.sort(
            key=lambda item: (
                -float(item.get("source_atom_score") or 0.0),
                SAB_PRIORITY.get(str(item.get("sab") or ""), 99),
                TTY_PRIORITY.get(str(item.get("tty") or ""), 99),
                str(item.get("label") or "").lower(),
                str(item.get("code") or ""),
            )
        )
        results = ranked[:limit]
        self.cache[key] = [dict(row) for row in results]
        return [dict(row) for row in results]

    def search_labels(
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
        if not self.search_labels_table_available():
            return []
        search_type = str(search_type or "words").strip()
        limit = max(1, int(limit or 1))
        sab_values = tuple(sorted(normalize_sab(sab) for sab in (sabs or []) if str(sab or "").strip()))
        key = (
            "search_labels",
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
        rows = self._search_label_rows(
            query,
            search_type=search_type,
            sabs=sab_values,
            include_obsolete=include_obsolete,
            include_suppressible=include_suppressible,
            partial=partial,
            limit=limit,
        )
        results = _dedupe_search_label_rows(rows, query=query, search_type=search_type)[:limit]
        self.cache[key] = [dict(row) for row in results]
        return [dict(row) for row in results]

    def _search_label_rows(
        self,
        query: str,
        *,
        search_type: str,
        sabs: tuple[str, ...],
        include_obsolete: bool,
        include_suppressible: bool,
        partial: bool,
        limit: int,
    ) -> list[dict]:
        norm = normalized_key(query)
        if not norm:
            return []
        if search_type == "normalizedString":
            norms = [key for key in lexical_variant_keys(query) if key]
            if partial:
                clauses = ["sl.norm LIKE ?"]
                values: list[object] = [f"%{lexical_normalized_key(query) or norm}%"]
            else:
                if not norms:
                    return []
                placeholders = ",".join("?" for _ in norms)
                clauses = [f"sl.norm IN ({placeholders})"]
                values = list(norms)
        elif search_type == "exact":
            if partial:
                clauses = ["sl.norm LIKE ?"]
                values = [f"%{norm}%"]
            else:
                clauses = ["sl.norm = ?"]
                values = [norm]
        elif search_type in {"words", "normalizedWords"}:
            tokens = lexical_normalized_tokens(query) if search_type == "normalizedWords" else norm.split()
            tokens = [token for token in tokens if token]
            if not tokens:
                return []
            joiner = " OR " if partial else " AND "
            clauses = [joiner.join("sl.norm LIKE ?" for _ in tokens)]
            values = [f"%{token}%" for token in tokens]
        elif search_type == "rightTruncation":
            clauses = ["sl.norm LIKE ?"]
            values = [f"{norm}%"]
        elif search_type == "leftTruncation":
            clauses = ["sl.norm LIKE ?"]
            values = [f"%{norm}"]
        else:
            return []

        clauses.append(_suppress_visibility_clause(include_obsolete, include_suppressible).replace("suppress", "cm.suppress"))
        if sabs:
            placeholders = ",".join("?" for _ in sabs)
            clauses.append(f"cm.sab IN ({placeholders})")
            values.extend(sabs)

        query_limit = max(limit * 30, limit + 500)
        columns = self.code_mapping_columns("cm")
        sql = f"""
            SELECT sl.norm, {columns}
            FROM search_labels AS sl
            JOIN code_mappings AS cm ON cm.atom_id = sl.atom_id
            WHERE {' AND '.join(f'({clause})' for clause in clauses)}
            LIMIT ?
        """
        db_rows = list(self.connection().execute(sql, (*values, query_limit)))
        if search_type in {"words", "normalizedWords"}:
            wanted_tokens = lexical_normalized_tokens(query) if search_type == "normalizedWords" else norm.split()
            db_rows = [
                row
                for row in db_rows
                if _search_label_word_match(str(row["norm"] or ""), wanted_tokens, partial=partial)
            ]
        rows = []
        for row in db_rows:
            item = _row_dict(row)
            item["norm"] = row["norm"]
            rows.append(item)
        return rows

    def lookup_aui_for_cui(
        self,
        cui: str,
        *,
        sabs: Iterable[str] | None = None,
        include_obsolete: bool = False,
        include_suppressible: bool = False,
        limit: int = 100,
    ) -> list[dict]:
        cui = str(cui or "").strip().upper()
        if not cui:
            return []
        sab_values = tuple(sorted(normalize_sab(sab) for sab in (sabs or []) if sab))
        key = (
            "aui_for_cui",
            cui,
            sab_values,
            bool(include_obsolete),
            bool(include_suppressible),
            limit,
        )
        cached = self.cache.get(key)
        if cached is not None:
            return [dict(row) for row in cached]
        if self.code_mappings_has_aui():
            clauses = ["cui = ?", "aui <> ''", _suppress_visibility_clause(include_obsolete, include_suppressible)]
            values: list[object] = [cui]
            if sab_values:
                placeholders = ",".join("?" for _ in sab_values)
                clauses.append(f"sab IN ({placeholders})")
                values.extend(sab_values)
            columns = self.code_mapping_columns()
            rows = self.connection().execute(
                f"""
                SELECT {columns}
                FROM code_mappings
                WHERE {' AND '.join(f'({clause})' for clause in clauses)}
                LIMIT ?
                """,
                (*values, limit),
            )
            results = _dedupe_rows(rows)[:limit]
            for row in results:
                row["matched_identifier_type"] = "AUI"
                row["matched_identifier"] = row.get("aui") or ""
            self.cache[key] = [dict(row) for row in results]
            return [dict(row) for row in results]
        if not self.identifier_table_available():
            self.cache[key] = []
            return []
        clauses = ["cui = ?", "identifier_type = 'AUI'"]
        values = [cui]
        clauses.append(_suppress_visibility_clause(include_obsolete, include_suppressible))
        if sab_values:
            placeholders = ",".join("?" for _ in sab_values)
            clauses.append(f"sab IN ({placeholders})")
            values.extend(sab_values)
        rows = self.connection().execute(
            f"""
            SELECT
                cui, identifier_type, identifier, sab, code, scui, sdui, tty, label, ispref, suppress
            FROM identifier_mappings
            WHERE {' AND '.join(f'({clause})' for clause in clauses)}
            LIMIT ?
            """,
            (*values, limit),
        )
        results = [dict(row) for row in rows]
        self.cache[key] = [dict(row) for row in results]
        return [dict(row) for row in results]

    def lookup_code(
        self,
        code: str,
        *,
        sab: str | None = None,
        limit: int = 100,
        include_legacy: bool = True,
    ) -> list[dict]:
        code = code.strip()
        sab_value = normalize_sab(sab or "") if sab else ""
        key = ("code", sab_value, code.lower(), limit, bool(include_legacy))
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        query_limit = max(limit * 4, limit + 50)
        columns = self.code_mapping_columns()
        if sab_value:
            rows = self.connection().execute(
                f"""
                SELECT {columns}
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
                f"""
                SELECT {columns}
                FROM code_mappings
                WHERE code = ? COLLATE NOCASE
                   OR scui = ? COLLATE NOCASE
                   OR sdui = ? COLLATE NOCASE
                LIMIT ?
                """,
                (code, code, code, query_limit),
            )
        results = _dedupe_rows(rows)[:limit]
        if not results and include_legacy:
            results = self.lookup_legacy_identifier(
                code,
                identifier_type="CODE",
                sab=sab_value or None,
                limit=limit,
            )
        self.cache[key] = results
        return results

    def lookup_legacy_identifier(
        self,
        identifier: str,
        *,
        identifier_type: str,
        sab: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        identifier = str(identifier or "").strip()
        identifier_type_value = normalize_sab(identifier_type or "")
        sab_value = normalize_sab(sab or "") if sab else ""
        if (
            not identifier
            or identifier_type_value not in LEGACY_IDENTIFIER_TYPES
            or not self.legacy_identifier_table_available()
        ):
            return []
        key = ("legacy_identifier", identifier_type_value, sab_value, identifier.lower(), limit)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        query_limit = max(limit * 4, limit + 50)
        base_select = """
            SELECT
                cui, identifier_type, identifier, sab, code, aui, scui, sdui,
                tty, label, ispref, suppress, last_release
            FROM legacy_identifier_mappings
            WHERE identifier_type = ?
              AND identifier = ? COLLATE NOCASE
        """
        if sab_value:
            rows = self.connection().execute(
                base_select
                + """
                  AND sab = ?
                LIMIT ?
                """,
                (identifier_type_value, identifier, sab_value, query_limit),
            )
        else:
            rows = self.connection().execute(
                base_select + " LIMIT ?",
                (identifier_type_value, identifier, query_limit),
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
        include_legacy: bool = True,
    ) -> list[dict]:
        identifier = str(identifier or "").strip()
        if not identifier:
            return []
        identifier_type_value = normalize_sab(identifier_type or infer_umls_identifier_type(identifier) or "CODE")
        sab_value = normalize_sab(sab or "") if sab else ""
        key = ("identifier", identifier_type_value, sab_value, identifier.lower(), limit, bool(include_legacy))
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        if identifier_type_value == "CUI":
            results = self.lookup_cui(identifier, sabs=[sab_value] if sab_value else None, limit=limit)
            if not results and include_legacy:
                results = self.lookup_legacy_identifier(
                    identifier,
                    identifier_type="CUI",
                    sab=sab_value or None,
                    limit=limit,
                )
            self.cache[key] = results
            return results
        if identifier_type_value in {"CODE", "SCUI", "SDUI"}:
            column = {"CODE": "code", "SCUI": "scui", "SDUI": "sdui"}[identifier_type_value]
            query_limit = max(limit * 4, limit + 50)
            columns = self.code_mapping_columns()
            if sab_value:
                rows = self.connection().execute(
                    f"""
                    SELECT {columns}
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
                    SELECT {columns}
                    FROM code_mappings
                    WHERE {column} = ? COLLATE NOCASE
                    LIMIT ?
                    """,
                    (identifier, query_limit),
                )
            results = _dedupe_rows(rows)[:limit]
            if not results and include_legacy:
                results = self.lookup_legacy_identifier(
                    identifier,
                    identifier_type=identifier_type_value,
                    sab=sab_value or None,
                    limit=limit,
                )
            self.cache[key] = results
            return results
        if identifier_type_value not in {"AUI", "LUI", "SUI"}:
            self.cache[key] = []
            return []
        if identifier_type_value == "AUI" and self.code_mappings_has_aui():
            query_limit = max(limit * 4, limit + 50)
            columns = self.code_mapping_columns()
            if sab_value:
                rows = self.connection().execute(
                    f"""
                    SELECT {columns}
                    FROM code_mappings
                    WHERE sab = ?
                      AND aui = ? COLLATE NOCASE
                    LIMIT ?
                    """,
                    (sab_value, identifier, query_limit),
                )
            else:
                rows = self.connection().execute(
                    f"""
                    SELECT {columns}
                    FROM code_mappings
                    WHERE aui = ? COLLATE NOCASE
                    LIMIT ?
                    """,
                    (identifier, query_limit),
                )
            results = _dedupe_rows(rows)[:limit]
            for row in results:
                row["matched_identifier_type"] = "AUI"
                row["matched_identifier"] = row.get("aui") or identifier
            if not results and include_legacy:
                results = self.lookup_legacy_identifier(
                    identifier,
                    identifier_type="AUI",
                    sab=sab_value or None,
                    limit=limit,
                )
            self.cache[key] = results
            return results
        if not self.identifier_table_available():
            results = (
                self.lookup_legacy_identifier(
                    identifier,
                    identifier_type=identifier_type_value,
                    sab=sab_value or None,
                    limit=limit,
                )
                if include_legacy
                else []
            )
            self.cache[key] = results
            return results
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
        if not results and include_legacy:
            results = self.lookup_legacy_identifier(
                identifier,
                identifier_type=identifier_type_value,
                sab=sab_value or None,
                limit=limit,
            )
        self.cache[key] = results
        return results
