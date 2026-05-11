from __future__ import annotations

import json
import math
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

from .schema import iter_jsonl


TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS relationship_edges (
    source_cui TEXT NOT NULL,
    target_cui TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    relation TEXT NOT NULL,
    rela TEXT NOT NULL,
    relation_group TEXT NOT NULL,
    source TEXT NOT NULL,
    source_class TEXT NOT NULL,
    direction TEXT NOT NULL,
    label TEXT NOT NULL,
    source_label TEXT NOT NULL,
    strength REAL NOT NULL,
    confidence REAL NOT NULL,
    edge_json TEXT NOT NULL,
    context_json TEXT NOT NULL,
    rank INTEGER NOT NULL
);
"""

INDEX_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_relationship_edges_source_rank
ON relationship_edges(source_cui, rank);

CREATE INDEX IF NOT EXISTS idx_relationship_edges_target_rank
ON relationship_edges(target_cui, rank);
"""

RELATION_GROUP_BY_TYPE = {
    "affects_risk_of": "effect_estimate",
    "associated_with": "associated",
    "decreases_risk_of": "effect_estimate",
    "increases_risk_of": "effect_estimate",
    "likely_indication": "treatment",
    "precedes": "temporal_analysis",
    "predicts": "prediction_model",
    "treats": "treatment",
}


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(result):
        return default
    return result


def row_value(row: dict[str, Any], *names: str) -> str:
    lookup = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        value = lookup.get(name.lower())
        if value not in (None, ""):
            return str(value).strip()
    return ""


def edge_payload_from_row(row: dict[str, Any]) -> dict[str, Any]:
    edge = row.get("edge")
    return dict(edge) if isinstance(edge, dict) else {}


def relationship_type_from_row(row: dict[str, Any], edge: dict[str, Any]) -> str:
    return (
        str(edge.get("type") or "").strip()
        or row_value(row, "relationship_type", "type", "rela", "relation")
        or "associated_with"
    )


def relation_group_for_type(relationship_type: str) -> str:
    return RELATION_GROUP_BY_TYPE.get(relationship_type, relationship_type or "associated")


def normalized_edge_row(row: dict[str, Any], *, rank: int) -> tuple | None:
    edge = edge_payload_from_row(row)
    source_cui = (
        str(edge.get("subject") or "").strip().upper()
        or row_value(row, "subject_cui", "source_cui").upper()
    )
    target_cui = (
        str(edge.get("object") or "").strip().upper()
        or row_value(row, "object_cui", "target_cui", "cui").upper()
    )
    if not source_cui or not target_cui or source_cui == target_cui:
        return None
    relationship_type = relationship_type_from_row(row, edge)
    relation = row_value(row, "relation") or relationship_type
    rela = row_value(row, "rela") or relationship_type
    relation_group = row_value(row, "relation_group") or relation_group_for_type(relationship_type)
    evidence = edge.get("evidence") if isinstance(edge.get("evidence"), dict) else {}
    context = edge.get("context") if isinstance(edge.get("context"), dict) else row.get("context")
    source = (
        str(evidence.get("provenance") or "").strip()
        or row_value(row, "source", "source_path", "source_class")
        or "relationship_edge_jsonl"
    )
    source_class = row_value(row, "source_class") or source
    direction = str(edge.get("directionality") or "").strip() or row_value(row, "direction") or "outgoing"
    label = row_value(row, "object_label", "target_label", "label") or target_cui
    source_label = row_value(row, "subject_label", "source_label") or source_cui
    strength = safe_float(edge.get("strength", row.get("strength")), 0.0)
    confidence = safe_float(edge.get("confidence", row.get("confidence")), 0.0)
    return (
        source_cui,
        target_cui,
        relationship_type,
        relation,
        rela,
        relation_group,
        source,
        source_class,
        direction,
        label,
        source_label,
        strength,
        confidence,
        json.dumps(edge, sort_keys=True, separators=(",", ":")) if edge else "",
        json.dumps(context if isinstance(context, dict) else {}, sort_keys=True, separators=(",", ":")),
        rank,
    )


def build_relationship_edge_index(
    *,
    edge_paths: Iterable[str | Path],
    out_path: str | Path,
    replace: bool = True,
) -> dict[str, int]:
    conn = connect(out_path)
    if replace:
        conn.execute("DROP TABLE IF EXISTS relationship_edges")
    conn.executescript(TABLE_SCHEMA)
    batch = []
    seen = set()
    input_rows = 0
    skipped_rows = 0
    for path in edge_paths:
        for rank, payload in enumerate(iter_jsonl(path), start=1):
            input_rows += 1
            row = normalized_edge_row(payload, rank=rank)
            if row is None:
                skipped_rows += 1
                continue
            key = (row[0], row[1], row[2], row[7], row[13])
            if key in seen:
                continue
            seen.add(key)
            batch.append(row)
    conn.executemany(
        """
        INSERT INTO relationship_edges(
            source_cui, target_cui, relationship_type, relation, rela,
            relation_group, source, source_class, direction, label, source_label,
            strength, confidence, edge_json, context_json, rank
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        batch,
    )
    conn.executescript(INDEX_SCHEMA)
    conn.commit()
    conn.close()
    return {
        "input_rows": input_rows,
        "skipped_rows": skipped_rows,
        "edges": len(batch),
        "source_cuis": len({row[0] for row in batch}),
        "target_cuis": len({row[1] for row in batch}),
    }


def row_to_relation(row: sqlite3.Row, *, incoming: bool = False) -> dict[str, Any]:
    edge = {}
    if row["edge_json"]:
        try:
            edge = json.loads(row["edge_json"])
        except json.JSONDecodeError:
            edge = {}
    context = {}
    if row["context_json"]:
        try:
            context = json.loads(row["context_json"])
        except json.JSONDecodeError:
            context = {}
    relation = {
        "source_cui": row["source_cui"],
        "target_cui": row["target_cui"],
        "cui": row["source_cui"] if incoming else row["target_cui"],
        "relationship_type": row["relationship_type"],
        "relation": row["relation"],
        "rela": row["rela"],
        "relation_group": row["relation_group"],
        "source": row["source"],
        "source_class": row["source_class"],
        "direction": "incoming" if incoming else row["direction"],
        "label": row["source_label"] if incoming else row["label"],
        "strength": float(row["strength"] or 0.0),
        "confidence": float(row["confidence"] or 0.0),
        "rank": int(row["rank"] or 0),
    }
    if edge:
        relation["edge"] = edge
    if context:
        relation["context"] = context
    return relation


class RelationshipEdgeIndex:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self._local = threading.local()
        self.cache: dict[tuple[str, int, str], list[dict]] = {}

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

    def source_count(self) -> int:
        row = self.connection().execute(
            "SELECT COUNT(DISTINCT source_cui) AS count FROM relationship_edges"
        ).fetchone()
        return int(row["count"] or 0)

    def edge_count(self) -> int:
        row = self.connection().execute("SELECT COUNT(*) AS count FROM relationship_edges").fetchone()
        return int(row["count"] or 0)

    def lookup(self, cui: str, *, limit: int = 24) -> list[dict]:
        cui = cui.strip().upper()
        key = (cui, limit, "outgoing")
        cached = self.cache.get(key)
        if cached is not None:
            return [dict(item) for item in cached]
        rows = self.connection().execute(
            """
            SELECT *
            FROM relationship_edges
            WHERE source_cui = ?
            ORDER BY confidence DESC, strength DESC, rank ASC
            LIMIT ?
            """,
            (cui, limit),
        )
        results = [row_to_relation(row) for row in rows]
        self.cache[key] = [dict(item) for item in results]
        return results

    def lookup_incoming(self, cui: str, *, limit: int = 24) -> list[dict]:
        cui = cui.strip().upper()
        key = (cui, limit, "incoming")
        cached = self.cache.get(key)
        if cached is not None:
            return [dict(item) for item in cached]
        rows = self.connection().execute(
            """
            SELECT *
            FROM relationship_edges
            WHERE target_cui = ?
            ORDER BY confidence DESC, strength DESC, rank ASC
            LIMIT ?
            """,
            (cui, limit),
        )
        results = [row_to_relation(row, incoming=True) for row in rows]
        self.cache[key] = [dict(item) for item in results]
        return results
