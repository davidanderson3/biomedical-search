from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .documents import evidence_view, iter_documents_jsonl
from .evidence import iter_evidence_jsonl
from .text import normalized_key


SCHEMA = """
CREATE TABLE IF NOT EXISTS provenance (
    doc_id TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    citation_hash TEXT NOT NULL,
    rank INTEGER NOT NULL,
    citation_json TEXT NOT NULL,
    PRIMARY KEY (doc_id, text_hash, citation_hash)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

INDEX_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_provenance_lookup
ON provenance(doc_id, text_hash);
"""

WEIGHT_RE = re.compile(r" \(weight ([0-9.]+)\)$")


def iter_document_evidence_texts(text: str):
    in_evidence = False
    for line in text.splitlines():
        if line in {"Real-world evidence:", "Open literature evidence:"}:
            in_evidence = True
            continue
        if not in_evidence or not line.startswith("- "):
            continue
        evidence_text = line[2:]
        match = WEIGHT_RE.search(evidence_text)
        if match:
            evidence_text = evidence_text[: match.start()]
        yield evidence_text


def load_document_evidence_keys(
    document_paths: list[str | Path],
    *,
    max_items_per_doc: int | None = None,
) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for path in document_paths:
        for document in iter_documents_jsonl(path):
            for index, text in enumerate(iter_document_evidence_texts(document.text), start=1):
                if max_items_per_doc is not None and index > max_items_per_doc:
                    break
                keys.add((document.doc_id, evidence_text_hash(text)))
    return keys


def evidence_text_hash(text: str) -> str:
    normalized = normalized_key(text)
    return hashlib.blake2b(normalized.encode("utf-8"), digest_size=16).hexdigest()


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(Path(path).expanduser()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-200000")
    return conn


def init_store(conn: sqlite3.Connection, *, replace: bool = False) -> None:
    if replace:
        conn.execute("DROP TABLE IF EXISTS provenance")
        conn.execute("DROP TABLE IF EXISTS metadata")
    conn.executescript(SCHEMA)
    conn.commit()


def create_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript(INDEX_SCHEMA)
    conn.commit()


def citation_from_evidence(record) -> dict:
    metadata = record.metadata or {}
    source = record.source or ""
    pmid = str(metadata.get("pmid") or "")
    pmcid = str(metadata.get("pmcid") or "")
    doi = str(metadata.get("doi") or "")
    corpus_doc_id = str(metadata.get("corpus_doc_id") or "")
    table = str(metadata.get("table") or "")
    itemid = str(metadata.get("itemid") or "")
    event_count = metadata.get("event_count")
    label = str(metadata.get("label") or "")
    matched_label = str(metadata.get("matched_label") or "")

    if source == "pubmed" and pmid:
        return {
            "label": f"PubMed PMID:{pmid}",
            "source": source,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "corpus_doc_id": corpus_doc_id,
            "matched_label": matched_label,
        }
    if source == "europepmc":
        epmc_source = str(metadata.get("source") or ("PMC" if pmcid else "MED"))
        epmc_id = str(metadata.get("id") or pmcid or pmid)
        url = f"https://europepmc.org/article/{epmc_source}/{epmc_id}" if epmc_id else ""
        if pmcid:
            label_text = f"Europe PMC {pmcid}"
        elif pmid:
            label_text = f"Europe PMC PMID:{pmid}"
        elif doi:
            label_text = f"Europe PMC DOI:{doi}"
        else:
            label_text = corpus_doc_id or "Europe PMC"
        return {
            "label": label_text,
            "source": source,
            "url": url,
            "pmid": pmid,
            "pmcid": pmcid,
            "doi": doi,
            "corpus_doc_id": corpus_doc_id,
            "matched_label": matched_label,
        }
    if source == "pmc_oa":
        url = str(metadata.get("source_url") or "")
        if not url and pmcid:
            url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
        if pmcid:
            label_text = f"PMC OA {pmcid}"
        elif pmid:
            label_text = f"PMC OA PMID:{pmid}"
        elif doi:
            label_text = f"PMC OA DOI:{doi}"
        else:
            label_text = corpus_doc_id or "PMC OA"
        return {
            "label": label_text,
            "source": source,
            "url": url,
            "pmid": pmid,
            "pmcid": pmcid,
            "doi": doi,
            "corpus_doc_id": corpus_doc_id,
            "license": metadata.get("license"),
            "matched_label": matched_label,
        }
    if source == "openalex_top_cited":
        openalex_id = str(metadata.get("openalex_id") or "")
        url = str(metadata.get("url") or openalex_id)
        cited_by_count = metadata.get("cited_by_count")
        publication_date = str(metadata.get("publication_date") or "")
        source_name = str(metadata.get("source_name") or "")
        label_bits = ["OpenAlex highly cited"]
        if publication_date:
            label_bits.append(publication_date)
        if cited_by_count not in (None, ""):
            label_bits.append(f"{cited_by_count} citations")
        return {
            "label": " | ".join(label_bits),
            "source": source,
            "url": url,
            "pmid": pmid,
            "pmcid": pmcid,
            "doi": doi,
            "openalex_id": openalex_id,
            "corpus_doc_id": corpus_doc_id,
            "source_name": source_name,
            "publication_date": publication_date,
            "cited_by_count": cited_by_count,
            "matched_label": matched_label,
        }
    return {
        "label": corpus_doc_id or source or "source unavailable",
        "source": source,
        "corpus_doc_id": corpus_doc_id,
        "pmid": pmid,
        "pmcid": pmcid,
        "doi": doi,
        "matched_label": matched_label,
    }


def _insert_metadata(conn: sqlite3.Connection, values: dict[str, object]) -> None:
    conn.executemany(
        """
        INSERT INTO metadata(key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        [(key, json.dumps(value, ensure_ascii=False, separators=(",", ":"))) for key, value in values.items()],
    )
    conn.commit()


def _index_stats(conn: sqlite3.Connection) -> dict:
    source_refs = int(conn.execute("SELECT COUNT(*) FROM provenance").fetchone()[0])
    doc_text_keys = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT 1
                FROM provenance
                GROUP BY doc_id, text_hash
            )
            """
        ).fetchone()[0]
    )
    docs = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT 1
                FROM provenance
                GROUP BY doc_id
            )
            """
        ).fetchone()[0]
    )
    return {
        "source_refs": source_refs,
        "doc_text_keys": doc_text_keys,
        "docs": docs,
    }


def build_provenance_index(
    *,
    evidence_paths: list[str | Path],
    sqlite_path: str | Path,
    document_paths: list[str | Path] | None = None,
    replace: bool = False,
    batch_size: int = 25_000,
    sources_per_text: int = 5,
    max_document_items: int | None = None,
) -> dict:
    if sources_per_text <= 0:
        raise ValueError("sources_per_text must be positive")
    sqlite_path = Path(sqlite_path).expanduser()
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(sqlite_path)
    input_rows = 0
    skipped_not_in_documents = 0
    skipped_after_cap = 0
    counts_by_key: dict[tuple[str, str], int] = {}
    inserted_hashes: set[tuple[str, str, str]] = set()
    allowed_keys = (
        load_document_evidence_keys(document_paths or [], max_items_per_doc=max_document_items)
        if document_paths
        else None
    )
    try:
        init_store(conn, replace=replace)
        sql = """
            INSERT OR IGNORE INTO provenance(doc_id, text_hash, citation_hash, rank, citation_json)
            VALUES (?, ?, ?, ?, ?)
        """
        batch = []
        for path in evidence_paths:
            for record in iter_evidence_jsonl(path):
                doc_id = f"{record.cui}:{evidence_view(record.evidence_type)}"
                text_hash = evidence_text_hash(record.text)
                key = (doc_id, text_hash)
                input_rows += 1
                if allowed_keys is not None and key not in allowed_keys:
                    skipped_not_in_documents += 1
                    continue
                if counts_by_key.get(key, 0) >= sources_per_text:
                    skipped_after_cap += 1
                    continue
                citation = citation_from_evidence(record)
                citation_json = json.dumps(citation, ensure_ascii=False, separators=(",", ":"))
                citation_hash = hashlib.blake2b(citation_json.encode("utf-8"), digest_size=16).hexdigest()
                dedupe_key = (doc_id, text_hash, citation_hash)
                if dedupe_key in inserted_hashes:
                    continue
                rank = counts_by_key.get(key, 0)
                inserted_hashes.add(dedupe_key)
                counts_by_key[key] = rank + 1
                batch.append((doc_id, text_hash, citation_hash, rank, citation_json))
                if len(batch) >= batch_size:
                    conn.executemany(sql, batch)
                    conn.commit()
                    batch.clear()
        if batch:
            conn.executemany(sql, batch)
            conn.commit()
        create_indexes(conn)
        stats = _index_stats(conn)
        stats.update(
            {
                "input_rows": input_rows,
                "document_key_filter": allowed_keys is not None,
                "document_keys": len(allowed_keys or ()),
                "max_document_items": max_document_items,
                "skipped_not_in_documents": skipped_not_in_documents,
                "skipped_after_cap": skipped_after_cap,
                "sources_per_text": sources_per_text,
                "text_key": "blake2b-128-normalized-text",
                "path": str(sqlite_path),
                "built_at": datetime.now(timezone.utc).isoformat(),
                "evidence_paths": [str(Path(path).expanduser()) for path in evidence_paths],
                "document_paths": [str(Path(path).expanduser()) for path in document_paths or []],
            }
        )
        _insert_metadata(conn, stats)
        return stats
    finally:
        conn.close()


class ProvenanceIndex:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self._local = threading.local()

    def connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = connect(self.path)
            self._local.conn = conn
        return conn

    def source_count(self) -> int:
        return int(self.connect().execute("SELECT COUNT(*) FROM provenance").fetchone()[0])

    def lookup_sources(self, doc_id: str, text: str, *, limit: int = 5) -> list[dict]:
        rows = self.connect().execute(
            """
            SELECT citation_json
            FROM provenance
            WHERE doc_id = ? AND text_hash = ?
            ORDER BY rank, citation_hash
            LIMIT ?
            """,
            (doc_id, evidence_text_hash(text), limit),
        )
        return [json.loads(row["citation_json"]) for row in rows]
