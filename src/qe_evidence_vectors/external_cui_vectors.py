from __future__ import annotations

import csv
import gzip
import io
import json
import math
import re
import sqlite3
import threading
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, TextIO

from .code_index import SAB_PRIORITY, TTY_PRIORITY, normalize_sab
from .relation_index import display_label, read_doc_labels
from .universal_relationship import attach_universal_edge

try:  # pragma: no cover - exercised in normal environments, fallback is tested indirectly.
    import numpy as np
except ImportError:  # pragma: no cover
    np = None


CUI_RE = re.compile(r"(?<![A-Z0-9])C\d{7}(?!\d)", re.IGNORECASE)
DEFAULT_EAGER_CODE_SABS = ("MSH", "OMIM", "GO", "HGNC", "NCI", "MEDLINEPLUS")

TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS external_cui_neighbors (
    source TEXT NOT NULL,
    source_cui TEXT NOT NULL,
    target_cui TEXT NOT NULL,
    score REAL NOT NULL,
    rank INTEGER NOT NULL,
    label TEXT NOT NULL
);
"""

INDEX_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_external_cui_neighbors_source_rank
ON external_cui_neighbors(source_cui, source, rank);

CREATE INDEX IF NOT EXISTS idx_external_cui_neighbors_source_cui
ON external_cui_neighbors(source_cui);
"""


@dataclass(frozen=True)
class ExternalCuiVector:
    identifier: str
    cui: str
    vector: list[float]


def extract_cui(identifier: str) -> str:
    match = CUI_RE.search(str(identifier).upper())
    return match.group(0) if match else ""


def canonical_source_sab(source: str) -> str:
    return normalize_sab(str(source or "").strip())


def source_code_keys(identifier: str) -> list[tuple[str, str]]:
    identifier = str(identifier or "").strip()
    if not identifier:
        return []
    keys = []
    if ":" in identifier:
        source, code = identifier.split(":", 1)
        sab = canonical_source_sab(source)
        code = code.strip()
        if sab and code:
            keys.append((sab, code))
    parts = identifier.split("_", 2)
    if len(parts) >= 3:
        sab = canonical_source_sab(parts[1])
        code = parts[2].strip()
        if sab and code:
            keys.append((sab, code))
    elif len(parts) == 2:
        sab = canonical_source_sab(parts[0])
        code = parts[1].strip()
        if sab and code:
            keys.append((sab, code))
    deduped = []
    seen = set()
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return deduped


def read_source_code_cui_mappings(
    mrconso_path: str | Path | None,
    *,
    include_sabs: set[str] | None = None,
) -> dict[tuple[str, str], set[str]]:
    if not mrconso_path:
        return {}
    allowed = {canonical_source_sab(sab) for sab in include_sabs} if include_sabs else set()
    mappings: dict[tuple[str, str], set[str]] = {}
    with Path(mrconso_path).expanduser().open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("|")
            if len(fields) < 14:
                continue
            cui = fields[0]
            sab = canonical_source_sab(fields[11])
            code = fields[13].strip()
            if not cui or not sab or not code:
                continue
            if allowed and sab not in allowed:
                continue
            mappings.setdefault((sab, code), set()).add(cui)
    return mappings


class SourceCodeResolver:
    def __init__(
        self,
        *,
        mrconso_path: str | Path | None = None,
        code_index_path: str | Path | None = None,
        eager_sabs: Iterable[str] = DEFAULT_EAGER_CODE_SABS,
    ) -> None:
        self.mapping = read_source_code_cui_mappings(mrconso_path) if mrconso_path else {}
        self.code_index_path = Path(code_index_path).expanduser() if code_index_path else None
        self._conn: sqlite3.Connection | None = None
        self.cache: dict[tuple[str, str], list[str]] = {}
        self.sab_exists_cache: dict[str, bool] = {}
        self.eager_loaded_sabs: set[str] = set()
        self.labels_by_cui: dict[str, str] = {}
        self.label_priority_by_cui: dict[str, tuple] = {}
        if self.code_index_path and eager_sabs:
            self.load_code_index_sabs({canonical_source_sab(sab) for sab in eager_sabs if sab})

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def connection(self) -> sqlite3.Connection | None:
        if not self.code_index_path:
            return None
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.code_index_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def load_code_index_sabs(self, sabs: set[str]) -> None:
        sabs = {sab for sab in sabs if sab}
        missing = sabs - self.eager_loaded_sabs
        if not missing:
            return
        conn = self.connection()
        if conn is None:
            return
        placeholders = ",".join("?" for _ in missing)
        rows = conn.execute(
            f"""
            SELECT DISTINCT cui, sab, code, scui, sdui, tty, label, ispref, suppress
            FROM code_mappings
            WHERE sab IN ({placeholders})
            """,
            tuple(sorted(missing)),
        )
        for row in rows:
            sab = canonical_source_sab(str(row["sab"] or ""))
            cui = str(row["cui"] or "")
            if not sab or not cui:
                continue
            self.remember_label(
                cui,
                str(row["label"] or ""),
                sab=sab,
                tty=str(row["tty"] or ""),
                ispref=str(row["ispref"] or ""),
                suppress=str(row["suppress"] or ""),
            )
            for code_field in ("code", "scui", "sdui"):
                code = str(row[code_field] or "").strip()
                if code:
                    self.mapping.setdefault((sab, code), set()).add(cui)
        self.eager_loaded_sabs.update(missing)
        for sab in missing:
            self.sab_exists_cache[sab] = True

    def lookup(self, sab: str, code: str) -> list[str]:
        key = (canonical_source_sab(sab), str(code or "").strip())
        if not key[0] or not key[1]:
            return []
        cached = self.cache.get(key)
        if cached is not None:
            return list(cached)
        cuis = set(self.mapping.get(key) or set())
        if key[0] in self.eager_loaded_sabs:
            results = sorted(cuis)
            self.cache[key] = results
            return list(results)
        conn = self.connection()
        if conn is not None:
            if key[0] not in self.sab_exists_cache:
                row = conn.execute(
                    "SELECT 1 FROM code_mappings WHERE sab = ? LIMIT 1",
                    (key[0],),
                ).fetchone()
                self.sab_exists_cache[key[0]] = row is not None
            if not self.sab_exists_cache[key[0]] and not cuis:
                return []
            rows = conn.execute(
                """
                SELECT DISTINCT cui, sab, tty, label, ispref, suppress
                FROM code_mappings
                WHERE sab = ?
                  AND (
                    code = ? COLLATE NOCASE
                    OR scui = ? COLLATE NOCASE
                    OR sdui = ? COLLATE NOCASE
                  )
                """,
                (key[0], key[1], key[1], key[1]),
            )
            for row in rows:
                cui = str(row["cui"] or "")
                if not cui:
                    continue
                cuis.add(cui)
                self.remember_label(
                    cui,
                    str(row["label"] or ""),
                    sab=str(row["sab"] or ""),
                    tty=str(row["tty"] or ""),
                    ispref=str(row["ispref"] or ""),
                    suppress=str(row["suppress"] or ""),
                )
        results = sorted(cuis)
        self.cache[key] = results
        return list(results)

    def remember_label(
        self,
        cui: str,
        label: str,
        *,
        sab: str = "",
        tty: str = "",
        ispref: str = "",
        suppress: str = "",
    ) -> None:
        cui = str(cui or "").strip().upper()
        label = str(label or "").strip()
        if not cui or not label:
            return
        priority = (
            0 if str(suppress or "N") == "N" else 1,
            0 if str(ispref or "") == "Y" else 1,
            SAB_PRIORITY.get(str(sab or ""), 99),
            TTY_PRIORITY.get(str(tty or ""), 99),
            label.lower(),
        )
        current = self.label_priority_by_cui.get(cui)
        if current is None or priority < current:
            self.labels_by_cui[cui] = label
            self.label_priority_by_cui[cui] = priority

    def label_for_cui(self, cui: str) -> str:
        return self.labels_by_cui.get(str(cui or "").strip().upper(), "")


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def _zip_member_name(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        candidates = [
            name
            for name in archive.namelist()
            if not name.endswith("/")
            and "__MACOSX" not in name
            and Path(name).suffix.lower() in {".csv", ".tsv", ".txt", ".json"}
        ]
        if not candidates:
            raise ValueError(f"{path}: no supported data file found in zip archive")
        return sorted(candidates)[0]


@contextmanager
def _open_text(path: str | Path) -> Iterator[TextIO]:
    path = Path(path).expanduser()
    if path.suffix.lower() == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", errors="replace", newline="") as handle:
            yield handle
        return
    if path.suffix.lower() == ".zip":
        member = _zip_member_name(path)
        with zipfile.ZipFile(path) as archive:
            with archive.open(member) as raw:
                with io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="") as handle:
                    yield handle
        return
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        yield handle


def _format_for_path(path: str | Path, data_format: str = "auto") -> str:
    if data_format != "auto":
        return data_format
    path = Path(path).expanduser()
    suffix = path.suffix.lower()
    if suffix == ".gz":
        suffix = Path(path.stem).suffix.lower()
    elif suffix == ".zip":
        suffix = Path(_zip_member_name(path)).suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix == ".csv":
        return "csv"
    if suffix == ".tsv":
        return "tsv"
    return "word2vec"


class _CharStream:
    def __init__(self, handle: TextIO) -> None:
        self.handle = handle
        self.buffer: list[str] = []

    def read(self) -> str:
        if self.buffer:
            return self.buffer.pop()
        return self.handle.read(1)

    def unread(self, char: str) -> None:
        if char:
            self.buffer.append(char)

    def skip_ws(self) -> str:
        while True:
            char = self.read()
            if not char or not char.isspace():
                return char


def _read_json_string_after_quote(reader: _CharStream) -> str:
    pieces = ['"']
    escaped = False
    while True:
        char = reader.read()
        if not char:
            raise ValueError("unterminated JSON string")
        pieces.append(char)
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            return str(json.loads("".join(pieces)))


def _read_json_number_array_after_bracket(reader: _CharStream) -> list[float]:
    values: list[float] = []
    token: list[str] = []
    while True:
        char = reader.read()
        if not char:
            raise ValueError("unterminated JSON number array")
        if char in "-+0123456789.eE":
            token.append(char)
            continue
        if char.isspace():
            continue
        if char in ",]":
            if token:
                values.append(float("".join(token)))
                token = []
            if char == "]":
                return values
            continue
        raise ValueError(f"unexpected character in JSON number array: {char!r}")


def _skip_json_value(reader: _CharStream, first: str) -> None:
    if first == '"':
        _read_json_string_after_quote(reader)
        return
    if first not in "[{":
        while True:
            char = reader.read()
            if not char:
                return
            if char in ",]}":
                reader.unread(char)
                return

    stack = [first]
    while stack:
        char = reader.read()
        if not char:
            raise ValueError("unterminated JSON value")
        if char == '"':
            _read_json_string_after_quote(reader)
        elif char in "[{":
            stack.append(char)
        elif char == "]":
            if stack[-1] != "[":
                raise ValueError("mismatched JSON brackets")
            stack.pop()
        elif char == "}":
            if stack[-1] != "{":
                raise ValueError("mismatched JSON braces")
            stack.pop()


def _iter_json_object_vectors(handle: TextIO) -> Iterator[ExternalCuiVector]:
    reader = _CharStream(handle)
    first = reader.skip_ws()
    if first == "[":
        payload = json.loads("[" + handle.read())
        yield from _iter_loaded_json_vectors(payload)
        return
    if first != "{":
        raise ValueError("expected BioConceptVec-style JSON object")

    while True:
        char = reader.skip_ws()
        if char == "}":
            return
        if char == ",":
            char = reader.skip_ws()
        if char != '"':
            raise ValueError(f"expected JSON object key, got {char!r}")
        key = _read_json_string_after_quote(reader)
        if reader.skip_ws() != ":":
            raise ValueError("expected ':' after JSON object key")
        value_start = reader.skip_ws()
        cui = extract_cui(key)
        if cui and value_start == "[":
            vector = _read_json_number_array_after_bracket(reader)
            if vector:
                yield ExternalCuiVector(identifier=key, cui=cui, vector=vector)
        elif value_start == "[":
            vector = _read_json_number_array_after_bracket(reader)
            if vector:
                yield ExternalCuiVector(identifier=key, cui="", vector=vector)
        else:
            _skip_json_value(reader, value_start)
        separator = reader.skip_ws()
        if separator == "}":
            return
        if separator != ",":
            raise ValueError(f"expected JSON object separator, got {separator!r}")
        reader.unread(separator)


def _iter_loaded_json_vectors(payload: object) -> Iterator[ExternalCuiVector]:
    if isinstance(payload, dict):
        for key, value in payload.items():
            cui = extract_cui(str(key))
            if cui and isinstance(value, list):
                yield ExternalCuiVector(identifier=str(key), cui=cui, vector=[float(item) for item in value])
            elif isinstance(value, list):
                yield ExternalCuiVector(identifier=str(key), cui="", vector=[float(item) for item in value])
        return
    if not isinstance(payload, list):
        return
    for item in payload:
        identifier = ""
        cui = ""
        vector = None
        if isinstance(item, dict):
            for key in ("cui", "id", "concept_id", "identifier"):
                if key in item:
                    identifier = str(item[key])
                    cui = extract_cui(identifier)
                    break
            vector = item.get("vector") or item.get("embedding")
        elif isinstance(item, list) and len(item) >= 2:
            identifier = str(item[0])
            cui = extract_cui(identifier)
            vector = item[1]
        if isinstance(vector, list):
            yield ExternalCuiVector(
                identifier=identifier or cui,
                cui=cui,
                vector=[float(value) for value in vector],
            )


def _row_vector(row: list[str]) -> ExternalCuiVector | None:
    cui_index = -1
    cui = ""
    for index, cell in enumerate(row[:4]):
        cui = extract_cui(cell)
        if cui:
            cui_index = index
            break
    if cui_index < 0:
        return None
    try:
        vector = [float(value) for value in row[cui_index + 1 :] if str(value).strip()]
    except ValueError:
        return None
    if not vector:
        return None
    return ExternalCuiVector(identifier=str(row[cui_index]), cui=cui, vector=vector)


def _iter_delimited_vectors(handle: TextIO, *, delimiter: str) -> Iterator[ExternalCuiVector]:
    csv.field_size_limit(2**31 - 1)
    reader = csv.reader(handle, delimiter=delimiter)
    for row in reader:
        if not row:
            continue
        record = _row_vector(row)
        if record:
            yield record


def _iter_word2vec_vectors(handle: TextIO) -> Iterator[ExternalCuiVector]:
    for line_number, line in enumerate(handle, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if line_number == 1 and len(parts) == 2 and all(part.isdigit() for part in parts):
            continue
        record = _row_vector(parts)
        if record:
            yield record


def iter_external_cui_vectors(
    path: str | Path,
    *,
    data_format: str = "auto",
) -> Iterator[ExternalCuiVector]:
    resolved_format = _format_for_path(path, data_format)
    with _open_text(path) as handle:
        if resolved_format == "json":
            yield from _iter_json_object_vectors(handle)
        elif resolved_format == "csv":
            yield from _iter_delimited_vectors(handle, delimiter=",")
        elif resolved_format == "tsv":
            yield from _iter_delimited_vectors(handle, delimiter="\t")
        elif resolved_format == "word2vec":
            yield from _iter_word2vec_vectors(handle)
        else:
            raise ValueError(f"unsupported external CUI vector format: {resolved_format}")


def _l2_normalize_rows(vectors: list[list[float]]) -> list[list[float]]:
    normalized = []
    for vector in vectors:
        norm = math.sqrt(sum(value * value for value in vector))
        normalized.append([value / norm for value in vector] if norm else vector)
    return normalized


def _insert_neighbors(
    conn: sqlite3.Connection,
    *,
    source: str,
    source_cui: str,
    neighbors: list[tuple[str, float]],
    labels: dict[str, str],
) -> int:
    rows = [
        (
            source,
            source_cui,
            target_cui,
            float(score),
            rank,
            labels.get(target_cui) or target_cui,
        )
        for rank, (target_cui, score) in enumerate(neighbors, start=1)
    ]
    conn.executemany(
        """
        INSERT INTO external_cui_neighbors(source, source_cui, target_cui, score, rank, label)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def _build_neighbors_numpy(
    conn: sqlite3.Connection,
    *,
    source: str,
    cuis: list[str],
    vectors: list[list[float]],
    source_indices: list[int],
    labels: dict[str, str],
    top_k: int,
    block_size: int,
    commit_every: int,
) -> int:
    assert np is not None
    if not vectors or not source_indices:
        return 0
    matrix = np.asarray(vectors, dtype=np.float64)
    norms = np.linalg.norm(matrix, axis=1)
    norms[~np.isfinite(norms) | (norms == 0)] = 1.0
    matrix = np.nan_to_num(matrix / norms[:, None], nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
    target_matrix_t = matrix.T
    inserted = 0
    pending = 0
    neighbor_count = min(top_k, max(0, len(cuis) - 1))
    if neighbor_count <= 0:
        return 0
    for offset in range(0, len(source_indices), block_size):
        block_indices = source_indices[offset : offset + block_size]
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            scores = matrix[block_indices] @ target_matrix_t
        scores = np.nan_to_num(scores, nan=-np.inf, posinf=-np.inf, neginf=-np.inf)
        for row_number, source_index in enumerate(block_indices):
            scores[row_number, source_index] = -np.inf
        candidate_indices = np.argpartition(-scores, neighbor_count - 1, axis=1)[:, :neighbor_count]
        for row_number, source_index in enumerate(block_indices):
            row_candidates = candidate_indices[row_number]
            row_scores = scores[row_number, row_candidates]
            order = np.argsort(-row_scores)
            neighbors = [
                (cuis[int(row_candidates[item])], float(row_scores[item]))
                for item in order[:neighbor_count]
                if math.isfinite(float(row_scores[item]))
            ]
            inserted += _insert_neighbors(
                conn,
                source=source,
                source_cui=cuis[source_index],
                neighbors=neighbors,
                labels=labels,
            )
            pending += 1
        if pending >= commit_every:
            conn.commit()
            pending = 0
    conn.commit()
    return inserted


def _build_neighbors_stdlib(
    conn: sqlite3.Connection,
    *,
    source: str,
    cuis: list[str],
    vectors: list[list[float]],
    source_indices: list[int],
    labels: dict[str, str],
    top_k: int,
    commit_every: int,
) -> int:
    if not vectors or not source_indices:
        return 0
    normalized = _l2_normalize_rows(vectors)
    inserted = 0
    pending = 0
    for source_index in source_indices:
        source_vector = normalized[source_index]
        scored = []
        for target_index, target_vector in enumerate(normalized):
            if target_index == source_index:
                continue
            score = sum(left * right for left, right in zip(source_vector, target_vector))
            scored.append((cuis[target_index], score))
        neighbors = sorted(scored, key=lambda item: item[1], reverse=True)[:top_k]
        inserted += _insert_neighbors(
            conn,
            source=source,
            source_cui=cuis[source_index],
            neighbors=neighbors,
            labels=labels,
        )
        pending += 1
        if pending >= commit_every:
            conn.commit()
            pending = 0
    conn.commit()
    return inserted


def _load_vectors_for_source(
    path: str | Path,
    *,
    data_format: str,
    source_cuis: set[str],
    source_code_resolver: SourceCodeResolver,
    max_vectors: int | None,
    max_source_cuis: int | None,
) -> tuple[list[str], list[list[float]], list[int], dict[str, int]]:
    seen: set[str] = set()
    cuis: list[str] = []
    vectors: list[list[float]] = []
    dimensions: int | None = None
    skipped_dimension = 0
    skipped_nonfinite = 0
    duplicate_cuis = 0
    unmapped_rows = 0
    total_rows = 0
    for record in iter_external_cui_vectors(path, data_format=data_format):
        total_rows += 1
        resolved_cuis = []
        if record.cui:
            resolved_cuis.append(record.cui)
        for sab, code in source_code_keys(record.identifier):
            resolved_cuis.extend(source_code_resolver.lookup(sab, code))
        resolved_cuis = sorted({cui for cui in resolved_cuis if cui})
        if not resolved_cuis:
            unmapped_rows += 1
            continue
        if dimensions is None:
            dimensions = len(record.vector)
        if len(record.vector) != dimensions:
            skipped_dimension += 1
            continue
        if not all(math.isfinite(value) for value in record.vector):
            skipped_nonfinite += 1
            continue
        added = 0
        for cui in resolved_cuis:
            if cui in seen:
                duplicate_cuis += 1
                continue
            seen.add(cui)
            cuis.append(cui)
            vectors.append(record.vector)
            added += 1
        if not added:
            continue
        if max_vectors and len(cuis) >= max_vectors:
            break
    source_indices = [
        index for index, cui in enumerate(cuis) if not source_cuis or cui in source_cuis
    ]
    if max_source_cuis is not None:
        source_indices = source_indices[:max_source_cuis]
    return (
        cuis,
        vectors,
        source_indices,
        {
            "total_rows": total_rows,
            "vectors": len(cuis),
            "source_cuis": len(source_indices),
            "dimensions": dimensions or 0,
            "duplicate_cuis": duplicate_cuis,
            "skipped_dimension": skipped_dimension,
            "skipped_nonfinite": skipped_nonfinite,
            "unmapped_rows": unmapped_rows,
        },
    )


def build_external_cui_vector_index(
    *,
    inputs: Iterable[tuple[str | Path, str, str]],
    out_path: str | Path,
    doc_paths: Iterable[str | Path] = (),
    mrconso_path: str | Path | None = None,
    code_index_path: str | Path | None = None,
    eager_code_sabs: Iterable[str] = DEFAULT_EAGER_CODE_SABS,
    top_k: int = 8,
    block_size: int = 64,
    max_vectors: int | None = None,
    max_source_cuis: int | None = None,
    replace: bool = True,
    commit_every: int = 500,
) -> dict[str, int]:
    doc_labels, doc_cuis = read_doc_labels(doc_paths)
    conn = connect(out_path)
    if replace:
        conn.execute("DROP TABLE IF EXISTS external_cui_neighbors")
    conn.executescript(TABLE_SCHEMA)
    source_code_resolver = SourceCodeResolver(
        mrconso_path=mrconso_path,
        code_index_path=code_index_path,
        eager_sabs=eager_code_sabs,
    )

    total_inserted = 0
    total_vectors = 0
    total_source_cuis = 0
    source_count = 0
    try:
        for path, source, data_format in inputs:
            labels = dict(doc_labels)
            cuis, vectors, source_indices, source_stats = _load_vectors_for_source(
                path,
                data_format=data_format,
                source_cuis=doc_cuis,
                source_code_resolver=source_code_resolver,
                max_vectors=max_vectors,
                max_source_cuis=max_source_cuis,
            )
            for cui in cuis:
                label = source_code_resolver.label_for_cui(cui)
                if label:
                    labels.setdefault(cui, label)
                labels.setdefault(cui, cui)
            if np is not None:
                inserted = _build_neighbors_numpy(
                    conn,
                    source=source,
                    cuis=cuis,
                    vectors=vectors,
                    source_indices=source_indices,
                    labels=labels,
                    top_k=top_k,
                    block_size=block_size,
                    commit_every=commit_every,
                )
            else:
                inserted = _build_neighbors_stdlib(
                    conn,
                    source=source,
                    cuis=cuis,
                    vectors=vectors,
                    source_indices=source_indices,
                    labels=labels,
                    top_k=top_k,
                    commit_every=commit_every,
                )
            source_count += 1
            total_inserted += inserted
            total_vectors += source_stats["vectors"]
            total_source_cuis += source_stats["source_cuis"]
    finally:
        source_code_resolver.close()
    conn.executescript(INDEX_SCHEMA)
    conn.commit()
    conn.close()
    return {
        "sources": source_count,
        "vectors": total_vectors,
        "source_cuis": total_source_cuis,
        "neighbors": total_inserted,
    }


class ExternalCuiVectorIndex:
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

    def sources(self) -> list[str]:
        rows = self.connection().execute(
            "SELECT DISTINCT source FROM external_cui_neighbors ORDER BY source"
        )
        return [str(row["source"]) for row in rows]

    def source_count(self) -> int:
        row = self.connection().execute(
            "SELECT COUNT(DISTINCT source_cui) AS count FROM external_cui_neighbors"
        ).fetchone()
        return int(row["count"] or 0)

    def neighbor_count(self) -> int:
        row = self.connection().execute(
            "SELECT COUNT(*) AS count FROM external_cui_neighbors"
        ).fetchone()
        return int(row["count"] or 0)

    def lookup(self, cui: str, *, limit_per_source: int = 8) -> list[dict]:
        key = (cui, limit_per_source)
        cached = self.cache.get(key)
        if cached is not None:
            return [dict(item) for item in cached]
        rows = self.connection().execute(
            """
            SELECT source, target_cui, score, rank, label
            FROM external_cui_neighbors
            WHERE source_cui = ?
            ORDER BY source ASC, rank ASC, score DESC
            """,
            (cui,),
        )
        source_counts: dict[str, int] = {}
        results = []
        for row in rows:
            source = str(row["source"] or "")
            if source_counts.get(source, 0) >= limit_per_source:
                continue
            source_counts[source] = source_counts.get(source, 0) + 1
            results.append(
                attach_universal_edge(
                    {
                        "cui": row["target_cui"],
                        "label": display_label(str(row["label"] or row["target_cui"])),
                        "relation": "external_embedding",
                        "relation_group": "embedding_similarity",
                        "rela": "embedding similarity",
                        "source": source,
                        "score": round(float(row["score"] or 0.0), 6),
                        "rank": int(row["rank"] or 0),
                    },
                    subject_cui=cui,
                    object_cui=row["target_cui"],
                )
            )
        self.cache[key] = [dict(item) for item in results]
        return results
