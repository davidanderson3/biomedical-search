from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .schema import iter_jsonl, write_jsonl


MRCONSO_FIELD_NAMES = (
    "cui",
    "lat",
    "ts",
    "lui",
    "stt",
    "sui",
    "ispref",
    "aui",
    "saui",
    "scui",
    "sdui",
    "sab",
    "tty",
    "code",
    "str",
    "srl",
    "suppress",
    "cvf",
)

DEFAULT_ATOM_FINGERPRINT_FIELDS = (
    "lat",
    "sab",
    "tty",
    "code",
    "scui",
    "sdui",
    "str",
    "ispref",
    "suppress",
)
ATOM_ID_FIELDS = ("aui", "saui", "lui", "sui")
FINGERPRINT_SCHEMA = "query-expansion-cui-atom-fingerprints-v1"
DIFF_SCHEMA = "query-expansion-cui-atom-fingerprint-diff-v1"
DOCUMENT_MANIFEST_SCHEMA = "query-expansion-concept-document-manifest-v1"
VECTOR_REUSE_PLAN_SCHEMA = "query-expansion-vector-reuse-plan-v1"
VECTOR_ASSEMBLY_SCHEMA = "query-expansion-incremental-vector-assembly-v1"
VECTOR_SIGNATURE_METADATA_FIELDS = (
    "embedding_provider",
    "embedding_model",
    "embedding_pooling",
)


def normalized_atom_key(fields: list[str], *, include_atom_ids: bool = False) -> str | None:
    if len(fields) < len(MRCONSO_FIELD_NAMES):
        return None
    row = dict(zip(MRCONSO_FIELD_NAMES, fields))
    key_fields = DEFAULT_ATOM_FINGERPRINT_FIELDS
    if include_atom_ids:
        key_fields = (*key_fields, *ATOM_ID_FIELDS)
    values = [str(row.get(name) or "").strip() for name in key_fields]
    return "\t".join(values)


def iter_cui_atom_fingerprints(
    mrconso_path: str | Path,
    *,
    language: str = "ENG",
    include_suppressed: bool = False,
    include_atom_ids: bool = False,
    temp_dir: str | Path | None = None,
    batch_size: int = 100_000,
) -> Iterable[dict[str, str | int]]:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    temp_dir_path = Path(temp_dir).expanduser() if temp_dir else None
    if temp_dir_path:
        temp_dir_path.mkdir(parents=True, exist_ok=True)
    temp_handle = tempfile.NamedTemporaryFile(
        prefix="cui_atom_fingerprints_",
        suffix=".sqlite",
        dir=temp_dir_path,
        delete=False,
    )
    temp_path = Path(temp_handle.name)
    temp_handle.close()
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(temp_path)
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute(
            """
            CREATE TABLE atom_hashes (
                cui TEXT NOT NULL,
                atom_digest TEXT NOT NULL,
                PRIMARY KEY (cui, atom_digest)
            ) WITHOUT ROWID
            """
        )
        batch: list[tuple[str, str]] = []
        with Path(mrconso_path).expanduser().open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                fields = line.rstrip("\n").split("|")
                if len(fields) < len(MRCONSO_FIELD_NAMES):
                    continue
                if fields[1] != language:
                    continue
                if not include_suppressed and fields[16] != "N":
                    continue
                atom_key = normalized_atom_key(fields, include_atom_ids=include_atom_ids)
                if not atom_key:
                    continue
                batch.append((fields[0], hashlib.sha256(atom_key.encode("utf-8")).hexdigest()))
                if len(batch) >= batch_size:
                    conn.executemany("INSERT OR IGNORE INTO atom_hashes VALUES (?, ?)", batch)
                    batch.clear()
        if batch:
            conn.executemany("INSERT OR IGNORE INTO atom_hashes VALUES (?, ?)", batch)
        conn.commit()

        current_cui = ""
        atom_digests: list[str] = []
        for cui, atom_digest in conn.execute("SELECT cui, atom_digest FROM atom_hashes ORDER BY cui, atom_digest"):
            if current_cui and cui != current_cui:
                payload = "\n".join(atom_digests).encode("utf-8")
                yield {
                    "cui": current_cui,
                    "atom_count": len(atom_digests),
                    "atom_hash": hashlib.sha256(payload).hexdigest(),
                }
                atom_digests = []
            current_cui = cui
            atom_digests.append(atom_digest)
        if current_cui:
            payload = "\n".join(atom_digests).encode("utf-8")
            yield {
                "cui": current_cui,
                "atom_count": len(atom_digests),
                "atom_hash": hashlib.sha256(payload).hexdigest(),
            }
    finally:
        if conn is not None:
            conn.close()
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass


def write_atom_fingerprints(
    *,
    mrconso_path: str | Path,
    out_path: str | Path,
    language: str = "ENG",
    include_suppressed: bool = False,
    include_atom_ids: bool = False,
    release: str = "",
    temp_dir: str | Path | None = None,
    batch_size: int = 100_000,
) -> dict[str, object]:
    out_path = Path(out_path).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    atom_total = 0
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(f"# schema={FINGERPRINT_SCHEMA}\n")
        if release:
            handle.write(f"# release={release}\n")
        handle.write(f"# language={language}\n")
        handle.write(f"# include_suppressed={json.dumps(bool(include_suppressed))}\n")
        handle.write(f"# include_atom_ids={json.dumps(bool(include_atom_ids))}\n")
        handle.write("# fingerprint_material=sha256(sorted sha256(normalized_atom_key))\n")
        handle.write(f"# batch_size={batch_size}\n")
        writer = csv.DictWriter(handle, fieldnames=["cui", "atom_count", "atom_hash"], delimiter="\t")
        writer.writeheader()
        for row in iter_cui_atom_fingerprints(
            mrconso_path,
            language=language,
            include_suppressed=include_suppressed,
            include_atom_ids=include_atom_ids,
            temp_dir=temp_dir or out_path.parent,
            batch_size=batch_size,
        ):
            writer.writerow(row)
            count += 1
            atom_total += int(row["atom_count"])
    return {
        "schema": FINGERPRINT_SCHEMA,
        "path": str(out_path),
        "release": release,
        "language": language,
        "include_suppressed": include_suppressed,
        "include_atom_ids": include_atom_ids,
        "batch_size": batch_size,
        "cuis": count,
        "atoms": atom_total,
    }


def read_atom_fingerprints(path: str | Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with Path(path).expanduser().open("r", encoding="utf-8", newline="") as handle:
        filtered = (line for line in handle if not line.startswith("#"))
        reader = csv.DictReader(filtered, delimiter="\t")
        for row in reader:
            cui = str(row.get("cui") or "").strip()
            if not cui:
                continue
            rows[cui] = {
                "atom_count": str(row.get("atom_count") or "0"),
                "atom_hash": str(row.get("atom_hash") or ""),
            }
    return rows


def diff_atom_fingerprints(
    old_rows: dict[str, dict[str, str]],
    new_rows: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    changed = []
    old_cuis = set(old_rows)
    new_cuis = set(new_rows)
    for cui in sorted(old_cuis | new_cuis):
        old = old_rows.get(cui)
        new = new_rows.get(cui)
        if old is None:
            change_type = "added_cui"
        elif new is None:
            change_type = "removed_cui"
        elif old["atom_hash"] != new["atom_hash"] or old["atom_count"] != new["atom_count"]:
            change_type = "atoms_changed"
        else:
            continue
        changed.append(
            {
                "cui": cui,
                "change_type": change_type,
                "old_atom_count": old["atom_count"] if old else "0",
                "new_atom_count": new["atom_count"] if new else "0",
                "old_atom_hash": old["atom_hash"] if old else "",
                "new_atom_hash": new["atom_hash"] if new else "",
                "reembed_reason": change_type,
            }
        )
    return changed


def write_atom_fingerprint_diff(
    *,
    old_path: str | Path,
    new_path: str | Path,
    out_path: str | Path,
    summary_path: str | Path | None = None,
    old_release: str = "",
    new_release: str = "",
) -> dict[str, object]:
    old_rows = read_atom_fingerprints(old_path)
    new_rows = read_atom_fingerprints(new_path)
    changed = diff_atom_fingerprints(old_rows, new_rows)
    out_path = Path(out_path).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "cui",
        "change_type",
        "old_atom_count",
        "new_atom_count",
        "old_atom_hash",
        "new_atom_hash",
        "reembed_reason",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(f"# schema={DIFF_SCHEMA}\n")
        if old_release:
            handle.write(f"# old_release={old_release}\n")
        if new_release:
            handle.write(f"# new_release={new_release}\n")
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(changed)

    by_type: dict[str, int] = defaultdict(int)
    for row in changed:
        by_type[row["change_type"]] += 1
    summary = {
        "schema": DIFF_SCHEMA,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "old_path": str(Path(old_path).expanduser()),
        "new_path": str(Path(new_path).expanduser()),
        "out_path": str(out_path),
        "old_release": old_release,
        "new_release": new_release,
        "old_cuis": len(old_rows),
        "new_cuis": len(new_rows),
        "changed_cuis": len(changed),
        "change_counts": dict(sorted(by_type.items())),
    }
    if summary_path:
        summary_path = Path(summary_path).expanduser()
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json_hash(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def concept_document_manifest_row(payload: dict[str, Any]) -> dict[str, str]:
    doc_id = str(payload.get("doc_id") or "").strip()
    cui = str(payload.get("cui") or "").strip()
    view = str(payload.get("view") or "").strip()
    text = str(payload.get("text") or "")
    if not doc_id:
        raise ValueError("concept document is missing doc_id")
    if not cui:
        raise ValueError(f"{doc_id}: concept document is missing cui")
    if not view:
        raise ValueError(f"{doc_id}: concept document is missing view")
    stable_payload = {
        "doc_id": doc_id,
        "cui": cui,
        "view": view,
        "text": text,
        "evidence_count": int(payload.get("evidence_count") or 0),
        "sources": list(payload.get("sources") or []),
        "labels": list(payload.get("labels") or []),
        "metadata": payload.get("metadata") or {},
    }
    return {
        "doc_id": doc_id,
        "cui": cui,
        "view": view,
        "text_hash": _sha256_text(text),
        "document_hash": _canonical_json_hash(stable_payload),
        "text_chars": str(len(text)),
        "evidence_count": str(stable_payload["evidence_count"]),
    }


def iter_concept_document_manifest(docs_path: str | Path) -> Iterable[dict[str, str]]:
    for payload in iter_jsonl(docs_path):
        yield concept_document_manifest_row(payload)


def write_concept_document_manifest(
    *,
    docs_path: str | Path,
    out_path: str | Path,
    release: str = "",
) -> dict[str, object]:
    out_path = Path(out_path).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    fieldnames = [
        "doc_id",
        "cui",
        "view",
        "text_hash",
        "document_hash",
        "text_chars",
        "evidence_count",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(f"# schema={DOCUMENT_MANIFEST_SCHEMA}\n")
        if release:
            handle.write(f"# release={release}\n")
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in iter_concept_document_manifest(docs_path):
            writer.writerow(row)
            count += 1
    return {
        "schema": DOCUMENT_MANIFEST_SCHEMA,
        "path": str(out_path),
        "release": release,
        "docs": count,
    }


def read_concept_document_manifest(path: str | Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with Path(path).expanduser().open("r", encoding="utf-8", newline="") as handle:
        filtered = (line for line in handle if not line.startswith("#"))
        reader = csv.DictReader(filtered, delimiter="\t")
        for row in reader:
            doc_id = str(row.get("doc_id") or "").strip()
            if doc_id:
                rows[doc_id] = {key: str(value or "") for key, value in row.items()}
    return rows


def _carry_forward_vector(
    *,
    old_vector: dict[str, Any],
    new_doc: dict[str, Any],
    manifest_row: dict[str, str],
    old_manifest_row: dict[str, str],
    omit_text: bool = False,
    include_document_metadata: bool = False,
) -> dict[str, Any]:
    metadata = dict(old_vector.get("metadata") or {})
    metadata["evidence_count"] = int(new_doc.get("evidence_count") or 0)
    metadata["sources"] = list(new_doc.get("sources") or [])
    metadata["labels"] = list(new_doc.get("labels") or [])
    metadata["document_text_hash"] = manifest_row.get("text_hash", "")
    if include_document_metadata or "document_metadata" in metadata:
        metadata["document_metadata"] = new_doc.get("metadata") or {}
    metadata["incremental_reuse"] = {
        "carried_forward": True,
        "old_document_hash": old_manifest_row.get("document_hash", ""),
        "new_document_hash": manifest_row.get("document_hash", ""),
        "text_hash": manifest_row.get("text_hash", ""),
        "metadata_changed": old_manifest_row.get("document_hash") != manifest_row.get("document_hash"),
    }
    return {
        "doc_id": str(new_doc.get("doc_id") or ""),
        "cui": str(new_doc.get("cui") or ""),
        "view": str(new_doc.get("view") or ""),
        "vector": old_vector.get("vector") or [],
        "text": "" if omit_text else str(new_doc.get("text") or ""),
        "metadata": metadata,
    }


def _vector_signature(vector_record: dict[str, Any], vector_values: list[Any]) -> dict[str, object]:
    metadata = vector_record.get("metadata") or {}
    signature: dict[str, object] = {"dims": len(vector_values)}
    for field in VECTOR_SIGNATURE_METADATA_FIELDS:
        signature[field] = str(metadata.get(field) or "")
    return signature


def _vector_text_hash(vector_record: dict[str, Any]) -> tuple[str, str]:
    metadata = vector_record.get("metadata") or {}
    direct_hash = str(metadata.get("document_text_hash") or "").strip()
    if direct_hash:
        return direct_hash, "metadata.document_text_hash"
    legacy_hash = str(metadata.get("text_hash") or "").strip()
    if legacy_hash:
        return legacy_hash, "metadata.text_hash"
    incremental_reuse = metadata.get("incremental_reuse") or {}
    if isinstance(incremental_reuse, dict):
        reuse_hash = str(incremental_reuse.get("text_hash") or "").strip()
        if reuse_hash:
            return reuse_hash, "metadata.incremental_reuse.text_hash"
    text = str(vector_record.get("text") or "")
    if text:
        return _sha256_text(text), "text"
    return "", ""


def write_vector_reuse_plan(
    *,
    old_manifest_path: str | Path,
    new_docs_path: str | Path,
    old_vector_paths: Iterable[str | Path],
    out_plan_path: str | Path,
    out_reused_vectors_path: str | Path,
    out_docs_to_embed_path: str | Path,
    out_new_manifest_path: str | Path | None = None,
    summary_path: str | Path | None = None,
    old_release: str = "",
    new_release: str = "",
    omit_text: bool = False,
    include_document_metadata: bool = False,
    require_old_vector_text_hash: bool = False,
) -> dict[str, object]:
    old_vector_paths = list(old_vector_paths)
    old_manifest = read_concept_document_manifest(old_manifest_path)
    plan_rows_by_doc_id: dict[str, dict[str, str]] = {}
    reuse_candidates: dict[str, tuple[dict[str, Any], dict[str, str], dict[str, str], str]] = {}
    docs_to_embed: list[dict[str, Any]] = []
    new_manifest_rows: list[dict[str, str]] = []

    for new_doc in iter_jsonl(new_docs_path):
        manifest_row = concept_document_manifest_row(new_doc)
        new_manifest_rows.append(manifest_row)
        doc_id = manifest_row["doc_id"]
        old_row = old_manifest.get(doc_id)
        if old_row is None:
            action = "embed"
            reason = "new_doc"
        elif old_row.get("cui") != manifest_row["cui"] or old_row.get("view") != manifest_row["view"]:
            action = "embed"
            reason = "identity_changed"
        elif old_row.get("text_hash") != manifest_row["text_hash"]:
            action = "embed"
            reason = "text_changed"
        else:
            action = "reuse_vector"
            reason = "document_unchanged" if old_row.get("document_hash") == manifest_row["document_hash"] else "text_unchanged_metadata_changed"
            reuse_candidates[doc_id] = (new_doc, manifest_row, old_row, reason)
        if action == "embed":
            docs_to_embed.append(new_doc)
            plan_rows_by_doc_id[doc_id] = {
                "doc_id": doc_id,
                "cui": manifest_row["cui"],
                "view": manifest_row["view"],
                "action": action,
                "reason": reason,
                "old_document_hash": old_row.get("document_hash", "") if old_row else "",
                "new_document_hash": manifest_row["document_hash"],
                "old_text_hash": old_row.get("text_hash", "") if old_row else "",
                "new_text_hash": manifest_row["text_hash"],
            }

    out_reused_vectors_path = Path(out_reused_vectors_path).expanduser()
    out_reused_vectors_path.parent.mkdir(parents=True, exist_ok=True)
    reused_doc_ids: set[str] = set()
    reuse_block_reasons: dict[str, str] = {}
    old_vector_records_scanned = 0
    reused_count = 0
    with out_reused_vectors_path.open("w", encoding="utf-8") as handle:
        for path in reversed(old_vector_paths):
            for old_vector in iter_jsonl(path):
                old_vector_records_scanned += 1
                doc_id = str(old_vector.get("doc_id") or "").strip()
                if (
                    doc_id not in reuse_candidates
                    or doc_id in reused_doc_ids
                    or doc_id in reuse_block_reasons
                ):
                    continue
                new_doc, manifest_row, old_row, reason = reuse_candidates[doc_id]
                vector_text_hash, _vector_text_hash_source = _vector_text_hash(old_vector)
                if not vector_text_hash:
                    if require_old_vector_text_hash:
                        reuse_block_reasons[doc_id] = "missing_old_vector_text_hash"
                        continue
                elif vector_text_hash != old_row.get("text_hash", ""):
                    reuse_block_reasons[doc_id] = "old_vector_text_hash_mismatch"
                    continue
                carried = _carry_forward_vector(
                    old_vector=old_vector,
                    new_doc=new_doc,
                    manifest_row=manifest_row,
                    old_manifest_row=old_row,
                    omit_text=omit_text,
                    include_document_metadata=include_document_metadata,
                )
                handle.write(json.dumps(carried, ensure_ascii=False, separators=(",", ":")))
                handle.write("\n")
                reused_doc_ids.add(doc_id)
                reused_count += 1
                plan_rows_by_doc_id[doc_id] = {
                    "doc_id": doc_id,
                    "cui": manifest_row["cui"],
                    "view": manifest_row["view"],
                    "action": "reuse_vector",
                    "reason": reason,
                    "old_document_hash": old_row.get("document_hash", ""),
                    "new_document_hash": manifest_row["document_hash"],
                    "old_text_hash": old_row.get("text_hash", ""),
                    "new_text_hash": manifest_row["text_hash"],
                }

    for doc_id in sorted(set(reuse_candidates) - reused_doc_ids):
        new_doc, manifest_row, old_row, _reason = reuse_candidates[doc_id]
        reason = reuse_block_reasons.get(doc_id, "missing_old_vector")
        docs_to_embed.append(new_doc)
        plan_rows_by_doc_id[doc_id] = {
            "doc_id": doc_id,
            "cui": manifest_row["cui"],
            "view": manifest_row["view"],
            "action": "embed",
            "reason": reason,
            "old_document_hash": old_row.get("document_hash", ""),
            "new_document_hash": manifest_row["document_hash"],
            "old_text_hash": old_row.get("text_hash", ""),
            "new_text_hash": manifest_row["text_hash"],
        }

    old_doc_ids = set(old_manifest)
    new_doc_ids = {row["doc_id"] for row in new_manifest_rows}
    removed_doc_ids = old_doc_ids - new_doc_ids
    for doc_id in sorted(removed_doc_ids):
        old_row = old_manifest[doc_id]
        plan_rows_by_doc_id[doc_id] = {
            "doc_id": doc_id,
            "cui": old_row.get("cui", ""),
            "view": old_row.get("view", ""),
            "action": "drop",
            "reason": "removed_doc",
            "old_document_hash": old_row.get("document_hash", ""),
            "new_document_hash": "",
            "old_text_hash": old_row.get("text_hash", ""),
            "new_text_hash": "",
        }

    out_plan_path = Path(out_plan_path).expanduser()
    out_plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_rows = sorted(plan_rows_by_doc_id.values(), key=lambda row: (row["doc_id"], row["action"]))
    counts: dict[str, int] = defaultdict(int)
    for row in plan_rows:
        counts[row["reason"]] += 1
    fieldnames = [
        "doc_id",
        "cui",
        "view",
        "action",
        "reason",
        "old_document_hash",
        "new_document_hash",
        "old_text_hash",
        "new_text_hash",
    ]
    with out_plan_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(f"# schema={VECTOR_REUSE_PLAN_SCHEMA}\n")
        if old_release:
            handle.write(f"# old_release={old_release}\n")
        if new_release:
            handle.write(f"# new_release={new_release}\n")
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(plan_rows)

    embed_count = write_jsonl(out_docs_to_embed_path, docs_to_embed)

    if out_new_manifest_path:
        out_new_manifest_path = Path(out_new_manifest_path).expanduser()
        out_new_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_fieldnames = [
            "doc_id",
            "cui",
            "view",
            "text_hash",
            "document_hash",
            "text_chars",
            "evidence_count",
        ]
        with out_new_manifest_path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(f"# schema={DOCUMENT_MANIFEST_SCHEMA}\n")
            if new_release:
                handle.write(f"# release={new_release}\n")
            writer = csv.DictWriter(handle, fieldnames=manifest_fieldnames, delimiter="\t")
            writer.writeheader()
            writer.writerows(new_manifest_rows)

    summary = {
        "schema": VECTOR_REUSE_PLAN_SCHEMA,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "old_manifest_path": str(Path(old_manifest_path).expanduser()),
        "new_docs_path": str(Path(new_docs_path).expanduser()),
        "old_vector_paths": [str(Path(path).expanduser()) for path in old_vector_paths],
        "out_plan_path": str(out_plan_path),
        "out_reused_vectors_path": str(out_reused_vectors_path),
        "out_docs_to_embed_path": str(Path(out_docs_to_embed_path).expanduser()),
        "out_new_manifest_path": str(Path(out_new_manifest_path).expanduser()) if out_new_manifest_path else "",
        "old_release": old_release,
        "new_release": new_release,
        "old_manifest_docs": len(old_manifest),
        "old_vector_records_scanned": old_vector_records_scanned,
        "require_old_vector_text_hash": require_old_vector_text_hash,
        "new_docs": len(new_manifest_rows),
        "reused_vectors": reused_count,
        "docs_to_embed": embed_count,
        "removed_docs": len(removed_doc_ids),
        "reason_counts": dict(sorted(counts.items())),
    }
    if summary_path:
        summary_path = Path(summary_path).expanduser()
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def write_incremental_vector_assembly(
    *,
    manifest_path: str | Path,
    vector_paths: Iterable[str | Path],
    out_path: str | Path,
    summary_path: str | Path | None = None,
    release: str = "",
    expect_dims: int | None = None,
    expect_provider: str = "",
    expect_model: str = "",
    expect_pooling: str = "",
    require_text_hash: bool = False,
) -> dict[str, object]:
    vector_paths = [Path(path).expanduser() for path in vector_paths]
    if not vector_paths:
        raise ValueError("at least one vector path is required")
    if expect_dims is not None and expect_dims <= 0:
        raise ValueError("expect_dims must be positive")

    out_path = Path(out_path).expanduser()
    summary_path = Path(summary_path).expanduser() if summary_path else None
    required_vector_signature: dict[str, object] = {}
    if expect_dims is not None:
        required_vector_signature["dims"] = expect_dims
    if expect_provider:
        required_vector_signature["embedding_provider"] = expect_provider
    if expect_model:
        required_vector_signature["embedding_model"] = expect_model
    if expect_pooling:
        required_vector_signature["embedding_pooling"] = expect_pooling
    manifest = read_concept_document_manifest(manifest_path)
    expected_doc_ids = set(manifest)
    seen_doc_ids: dict[str, str] = {}
    duplicate_doc_ids: dict[str, list[str]] = {}
    extra_doc_ids: set[str] = set()
    identity_mismatches: list[dict[str, str]] = []
    empty_vectors: list[dict[str, str]] = []
    dimension_mismatches: list[dict[str, object]] = []
    embedding_signature_mismatches: list[dict[str, object]] = []
    expected_signature_mismatches: list[dict[str, object]] = []
    missing_text_hashes: list[dict[str, str]] = []
    text_hash_mismatches: list[dict[str, str]] = []
    expected_vector_signature: dict[str, object] | None = None
    source_record_counts: dict[str, int] = defaultdict(int)
    empty_doc_id_records = 0
    vector_records_scanned = 0

    for path in vector_paths:
        path_label = str(path)
        for vector in iter_jsonl(path):
            vector_records_scanned += 1
            source_record_counts[path_label] += 1
            doc_id = str(vector.get("doc_id") or "").strip()
            vector_values = vector.get("vector")
            if not doc_id:
                empty_doc_id_records += 1
                continue
            if not isinstance(vector_values, list) or not vector_values:
                empty_vectors.append({"doc_id": doc_id, "path": path_label})
            else:
                signature = _vector_signature(vector, vector_values)
                if expected_vector_signature is None:
                    expected_vector_signature = signature
                else:
                    if signature["dims"] != expected_vector_signature["dims"]:
                        dimension_mismatches.append(
                            {
                                "doc_id": doc_id,
                                "path": path_label,
                                "expected": expected_vector_signature,
                                "actual": signature,
                            }
                        )
                    if any(
                        signature[field] != expected_vector_signature[field]
                        for field in VECTOR_SIGNATURE_METADATA_FIELDS
                    ):
                        embedding_signature_mismatches.append(
                            {
                                "doc_id": doc_id,
                                "path": path_label,
                                "expected": expected_vector_signature,
                                "actual": signature,
                            }
                        )
                if required_vector_signature:
                    mismatched_required_fields = {
                        field: expected
                        for field, expected in required_vector_signature.items()
                        if signature.get(field) != expected
                    }
                    if mismatched_required_fields:
                        expected_signature_mismatches.append(
                            {
                                "doc_id": doc_id,
                                "path": path_label,
                                "expected": required_vector_signature,
                                "actual": signature,
                                "mismatched_fields": sorted(mismatched_required_fields),
                            }
                        )
            if doc_id in seen_doc_ids:
                duplicate_doc_ids.setdefault(doc_id, [seen_doc_ids[doc_id]]).append(path_label)
            else:
                seen_doc_ids[doc_id] = path_label

            manifest_row = manifest.get(doc_id)
            if manifest_row is None:
                extra_doc_ids.add(doc_id)
                continue
            vector_text_hash, vector_text_hash_source = _vector_text_hash(vector)
            expected_text_hash = manifest_row.get("text_hash", "")
            if not vector_text_hash:
                if require_text_hash:
                    missing_text_hashes.append({"doc_id": doc_id, "path": path_label})
            elif vector_text_hash != expected_text_hash:
                text_hash_mismatches.append(
                    {
                        "doc_id": doc_id,
                        "path": path_label,
                        "expected_text_hash": expected_text_hash,
                        "actual_text_hash": vector_text_hash,
                        "actual_text_hash_source": vector_text_hash_source,
                    }
                )
            vector_cui = str(vector.get("cui") or "").strip()
            vector_view = str(vector.get("view") or "").strip()
            if vector_cui != manifest_row.get("cui") or vector_view != manifest_row.get("view"):
                identity_mismatches.append(
                    {
                        "doc_id": doc_id,
                        "expected_cui": manifest_row.get("cui", ""),
                        "actual_cui": vector_cui,
                        "expected_view": manifest_row.get("view", ""),
                        "actual_view": vector_view,
                        "path": path_label,
                    }
                )

    missing_doc_ids = sorted(expected_doc_ids - set(seen_doc_ids))
    duplicate_doc_id_list = sorted(duplicate_doc_ids)
    extra_doc_id_list = sorted(extra_doc_ids)
    validation_counts = {
        "missing_doc_ids": len(missing_doc_ids),
        "duplicate_doc_ids": len(duplicate_doc_id_list),
        "extra_doc_ids": len(extra_doc_id_list),
        "identity_mismatches": len(identity_mismatches),
        "empty_doc_id_records": empty_doc_id_records,
        "empty_vectors": len(empty_vectors),
        "dimension_mismatches": len(dimension_mismatches),
        "embedding_signature_mismatches": len(embedding_signature_mismatches),
        "expected_signature_mismatches": len(expected_signature_mismatches),
        "missing_text_hashes": len(missing_text_hashes),
        "text_hash_mismatches": len(text_hash_mismatches),
    }
    summary = {
        "schema": VECTOR_ASSEMBLY_SCHEMA,
        "status": "failed" if any(validation_counts.values()) else "ok",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_path": str(Path(manifest_path).expanduser()),
        "vector_paths": [str(path) for path in vector_paths],
        "out_path": str(out_path),
        "summary_path": str(summary_path) if summary_path else "",
        "release": release,
        "manifest_docs": len(manifest),
        "vector_records_scanned": vector_records_scanned,
        "vectors_written": 0,
        "vector_signature": expected_vector_signature or {},
        "required_vector_signature": required_vector_signature,
        "require_text_hash": require_text_hash,
        "source_record_counts": dict(sorted(source_record_counts.items())),
        "validation_counts": validation_counts,
        "validation_samples": {
            "missing_doc_ids": missing_doc_ids[:20],
            "duplicate_doc_ids": duplicate_doc_id_list[:20],
            "extra_doc_ids": extra_doc_id_list[:20],
            "identity_mismatches": identity_mismatches[:20],
            "empty_vectors": empty_vectors[:20],
            "dimension_mismatches": dimension_mismatches[:20],
            "embedding_signature_mismatches": embedding_signature_mismatches[:20],
            "expected_signature_mismatches": expected_signature_mismatches[:20],
            "missing_text_hashes": missing_text_hashes[:20],
            "text_hash_mismatches": text_hash_mismatches[:20],
        },
    }
    if any(validation_counts.values()):
        if summary_path:
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        details = " ".join(f"{key}={value}" for key, value in validation_counts.items())
        raise ValueError(f"incremental vector assembly validation failed: {details}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    vectors_written = 0
    with out_path.open("w", encoding="utf-8") as handle:
        for path in vector_paths:
            for vector in iter_jsonl(path):
                doc_id = str(vector.get("doc_id") or "").strip()
                if doc_id not in expected_doc_ids:
                    continue
                handle.write(json.dumps(vector, ensure_ascii=False, separators=(",", ":")))
                handle.write("\n")
                vectors_written += 1

    summary["vectors_written"] = vectors_written
    if summary_path:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary
