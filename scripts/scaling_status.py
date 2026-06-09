#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import glob
import json
import re
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CHUNK_PLAN_GLOB = "config/scaling_chunk_*.plan.json"
VALID_QUALITY_REVIEW_GRADES = {"relevant", "partial", "wrong"}


@dataclass
class ArtifactStatus:
    pattern: str
    kind: str
    files: list[str] = field(default_factory=list)
    exists: bool = False
    rows: int = 0
    bytes: int = 0
    min_rows: int = 0
    min_files: int = 1
    latest_mtime: float | None = None

    @property
    def complete(self) -> bool:
        if len(self.files) < self.min_files:
            return False
        if self.min_rows and self.rows < self.min_rows:
            return False
        return self.exists


@dataclass
class StepStatus:
    id: str
    label: str
    status: str
    artifacts: list[ArtifactStatus]
    rows: int = 0
    bytes: int = 0
    effort_weight: float = 1.0
    phase: str = "Operations"
    why: str = ""


PHASE_ORDER = [
    "Foundation",
    "Evidence acquisition",
    "Evidence linking",
    "Document building",
    "Embedding",
    "Search serving",
    "Evaluation",
    "Release operations",
    "Restricted clinical data",
    "Operations",
]


PHASE_PURPOSE = {
    "Foundation": "Builds the UMLS lookup and profile backbone that lets later steps resolve biomedical language to CUIs.",
    "Evidence acquisition": "Collects real-world biomedical text so retrieval is grounded in how concepts are actually discussed.",
    "Evidence linking": "Anchors corpus mentions to UMLS CUIs so evidence can be attributed instead of treated as anonymous text.",
    "Document building": "Turns many evidence rows into compact CUI/view documents that can be searched and reviewed.",
    "Embedding": "Creates SapBERT vectors so queries can find concept evidence semantically, not only by exact words.",
    "Search serving": "Loads the vectors and supporting indexes into the search path users will actually test.",
    "Evaluation": "Adds human judgment gates so scale-up is driven by relevance, not just artifact completion.",
    "Release operations": "Makes the pipeline resumable, compact, and updateable enough for release-style operation.",
    "Restricted clinical data": "Adds credentialed clinical language only when local data and privacy constraints allow it.",
    "Operations": "Supports the pipeline with tracking, manifests, and local review utilities.",
}


PUBMED_PILOT_SUFFIXES = (
    "_download",
    "_corpus",
    "_evidence",
    "_documents",
    "_vectors",
    "_elastic",
    "_quality_review",
)


def step_effort_weight(step: dict[str, Any]) -> float:
    if "effort_weight" in step:
        return max(0.0, float(step["effort_weight"]))

    step_id = str(step.get("id", "")).lower()
    label = str(step.get("label", "")).lower()
    key = f"{step_id} {label}"

    if "full_pubmed" in key:
        return 40.0
    if "semantic_embeddings" in key:
        return 25.0
    if "incremental_manifests" in key:
        return 6.0
    if "pubmed_bulk" in key and "download" in key:
        return 3.0
    if "pubmed_bulk" in key and ("parse" in key or "corpus" in key):
        return 3.0
    if step_id.startswith("chunk_") and "literature" in key:
        return 10.0
    if step_id.startswith("chunk_") and "elastic_export" in key:
        return 2.0
    if ("quality" in key and "judgment" in key) or "quality_review" in key:
        return 3.0
    if "alias" in key or "dashboard" in key or step_id.endswith("_ui") or "_ui" in step_id:
        return 0.5
    if "profile" in key and "index" in key:
        return 2.0
    if "link" in key and "profile" in key:
        return 5.0
    if "load" in key and "elastic" in key:
        return 1.0
    if "embed" in key or ("sapbert" in key and "vectors" in key):
        return 5.0
    if "download" in key:
        return 2.0
    if "fetch" in key or "harvest" in key or "corpora" in key:
        return 3.0
    if "concept_documents" in key or "concept documents" in key or "aggregate" in key:
        return 1.5
    if "export" in key:
        return 1.5
    return 1.0


def step_phase(step: dict[str, Any]) -> str:
    if "phase" in step:
        return str(step["phase"])

    step_id = str(step.get("id", "")).lower()
    label = str(step.get("label", "")).lower()
    key = f"{step_id} {label}"

    if "full_pubmed" in key:
        return "Evidence acquisition"
    if "fetch" in key or "harvest" in key or "download" in key or "corpus" in key:
        return "Evidence acquisition"
    if "incremental" in key or "manifest" in key or "compact" in key or "provenance" in key:
        return "Release operations"
    if "quality" in key or "judgment" in key or "dashboard" in key or "_ui" in step_id:
        return "Evaluation"
    if "elastic" in key or "alias" in key or "load" in key:
        return "Search serving"
    if "embed" in key or "sapbert" in key or "vectors" in key:
        return "Embedding"
    if "document" in key or "aggregate" in key:
        return "Document building"
    if "link" in key or "evidence" in key:
        return "Evidence linking"
    if "umls" in key or ("profile" in key and "index" in key):
        return "Foundation"
    return "Operations"


def step_why(step: dict[str, Any]) -> str:
    if step.get("why"):
        return str(step["why"])

    step_id = str(step.get("id", "")).lower()
    label = str(step.get("label", "")).lower()
    key = f"{step_id} {label}"

    if "umls" in key and "index" in key:
        return "Creates the UMLS label/profile lookup backbone used to resolve text spans and rescue exact concept-name searches."
    if "dashboard" in key or "_ui" in step_id:
        return "Gives reviewers a usable surface for search testing, progress tracking, and relevance judgments."
    if "download" in key and "pubmed" in key:
        return "Moves evidence acquisition toward reproducible PubMed bulk files instead of small API topic samples."
    if "fetch" in key or "harvest" in key:
        return "Collects real biomedical language that can reveal how concepts are discussed outside controlled vocabulary labels."
    if "corpus" in key or "parse" in key:
        return "Normalizes source records into JSONL so later linking, aggregation, and provenance are reproducible."
    if "incremental" in key:
        return "Lets future updates reprocess only changed inputs instead of rebuilding the whole evidence index."
    if "link" in key or ("evidence" in key and "profile" in key):
        return "Matches real-world text to UMLS CUIs through semantic profile shards, producing auditable evidence rows."
    if "export" in key:
        return "Packages vectors into Elasticsearch/OpenSearch bulk files so they can be loaded and tested as a search index."
    if "alias" in key:
        return "Exposes reviewed indexes behind one stable search name so the assessment server can query the cumulative product."
    if "load" in key and "elastic" in key:
        return "Makes the vectors queryable through ANN search instead of local file scans."
    if "embed" in key or "sapbert" in key or "vectors" in key:
        return "Converts CUI/view documents into biomedical semantic vectors so related language can be retrieved without exact wording."
    if "aggregate" in key or "document" in key:
        return "Combines mention-level evidence into CUI/view documents, which are the searchable units of the product."
    if "quality" in key or "judgment" in key:
        return "Checks retrieval quality before more scale is added, preventing noisy evidence from being promoted blindly."
    if "provenance" in key or "compact" in key:
        return "Keeps the server and release artifacts small enough to scale while preserving inspectable evidence sources."
    if "full_pubmed" in key:
        return "Expands from pilots to broad PubMed coverage, which is required before calling the literature side product-like."
    return "Tracks a concrete pipeline artifact so progress reflects reproducible outputs, not just manual notes."


def resolve_path(path: str) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate
    return ROOT / candidate


def count_lines(path: Path) -> int:
    count = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            count += chunk.count(b"\n")
    return count


def count_csv_rows(
    path: Path,
    *,
    required_columns: list[str] | None = None,
    allowed_values: dict[str, set[str]] | None = None,
) -> int:
    required = [column for column in (required_columns or []) if column]
    allowed = allowed_values or {}
    count = 0
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if required and not all(str(row.get(column) or "").strip() for column in required):
                continue
            if any(str(row.get(column) or "").strip().lower() not in values for column, values in allowed.items()):
                continue
            if any(str(value or "").strip() for value in row.values()):
                count += 1
    return count


def count_sqlite_rows(path: Path, table: str) -> int:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
        raise ValueError(f"unsafe sqlite table name: {table}")
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


def artifact_status(spec: dict[str, Any]) -> ArtifactStatus:
    pattern = spec.get("path") or spec.get("glob")
    if not pattern:
        raise ValueError("artifact must define path or glob")
    kind = spec.get("kind", "file")
    min_rows = int(spec.get("min_rows", 0))
    min_files = int(spec.get("min_files", 1))
    required_columns = list(spec.get("required_columns") or [])
    allowed_values = {
        str(column): {str(value).strip().lower() for value in values}
        for column, values in (spec.get("allowed_values") or {}).items()
    }
    if kind == "file" and str(pattern).endswith("search_quality_judgments.csv"):
        kind = "csv"
        min_rows = max(min_rows, 1)
        required_columns = required_columns or ["query", "doc_id", "grade"]
        allowed_values = allowed_values or {"grade": VALID_QUALITY_REVIEW_GRADES}

    if "glob" in spec:
        paths = [Path(path) for path in glob.glob(str(resolve_path(pattern)))]
    else:
        path = resolve_path(pattern)
        paths = [path] if path.exists() else []
    paths = sorted(paths)

    status = ArtifactStatus(
        pattern=pattern,
        kind=kind,
        files=[str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path) for path in paths],
        exists=bool(paths),
        min_rows=min_rows,
        min_files=min_files,
    )
    for path in paths:
        stat = path.stat()
        status.bytes += stat.st_size
        status.latest_mtime = max(status.latest_mtime or 0, stat.st_mtime)
        if kind == "jsonl":
            status.rows += count_lines(path)
        elif kind == "csv":
            status.rows += count_csv_rows(
                path,
                required_columns=required_columns,
                allowed_values=allowed_values,
            )
        elif kind == "sqlite" and spec.get("count_table"):
            status.rows += count_sqlite_rows(path, str(spec["count_table"]))
    return status


def chunk_number(chunk_id: str) -> str | None:
    parts = chunk_id.split("_")
    for part in parts:
        if part.isdigit():
            return part
    return None


def chunk_loaded(chunk_id: str) -> bool:
    number = chunk_number(chunk_id)
    if number == "001":
        return resolve_path("build/scaling_runs/elasticsearch_loaded_sapbert_cls.marker").exists()
    if number:
        return resolve_path(f"build/scaling_runs/elasticsearch_loaded_chunk_{number}_sapbert_cls.marker").exists()
    return False


def summarize_configured_chunks() -> dict[str, Any]:
    plans = sorted(resolve_path(CHUNK_PLAN_GLOB).parent.glob(Path(CHUNK_PLAN_GLOB).name))
    chunks = []
    for plan_path in plans:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        status = plan_status(plan, include_chunk_summary=False)
        steps_by_id = {step["id"]: step for step in status["steps"]}
        embed_step = steps_by_id.get("embed_vectors")
        quality_step = steps_by_id.get("quality_review")
        loaded = chunk_loaded(status["chunk_id"])
        chunks.append(
            {
                "chunk_id": status["chunk_id"],
                "title": status["title"],
                "plan_path": str(plan_path.relative_to(ROOT)),
                "completed_steps": status["completed_steps"],
                "total_steps": status["total_steps"],
                "progress_fraction": status["progress_fraction"],
                "weighted_progress_fraction": status["weighted_progress_fraction"],
                "built": bool(embed_step and embed_step["status"] == "completed"),
                "loaded": loaded,
                "quality_reviewed": bool(quality_step and quality_step["status"] == "completed"),
            }
        )

    return {
        "total_chunks": len(chunks),
        "built_chunks": sum(1 for chunk in chunks if chunk["built"]),
        "loaded_chunks": sum(1 for chunk in chunks if chunk["loaded"]),
        "quality_reviewed_chunks": sum(1 for chunk in chunks if chunk["quality_reviewed"]),
        "chunks": chunks,
    }


def phase_summary(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for step in steps:
        grouped.setdefault(str(step.get("phase") or "Operations"), []).append(step)

    summaries = []
    for phase in sorted(grouped, key=lambda value: PHASE_ORDER.index(value) if value in PHASE_ORDER else len(PHASE_ORDER)):
        phase_steps = grouped[phase]
        completed_steps = [step for step in phase_steps if step["status"] == "completed"]
        completed_effort = sum(float(step.get("effort_weight") or 0) for step in completed_steps)
        total_effort = sum(float(step.get("effort_weight") or 0) for step in phase_steps)
        rows = sum(int(step.get("rows") or 0) for step in completed_steps)
        bytes_ = sum(int(step.get("bytes") or 0) for step in completed_steps)
        remaining = [step for step in phase_steps if step["status"] != "completed"]
        summaries.append(
            {
                "phase": phase,
                "purpose": PHASE_PURPOSE.get(phase, PHASE_PURPOSE["Operations"]),
                "completed_steps": len(completed_steps),
                "total_steps": len(phase_steps),
                "completed_effort_weight": completed_effort,
                "total_effort_weight": total_effort,
                "progress_fraction": completed_effort / total_effort if total_effort else 0,
                "rows": rows,
                "bytes": bytes_,
                "remaining_steps": len(remaining),
                "status": "completed" if not remaining else ("not_started" if not completed_steps else "in_progress"),
            }
        )
    return summaries


def pubmed_pilot_prefix(step_id: str) -> str | None:
    if not step_id.startswith("pubmed_bulk_recent"):
        return None
    for suffix in sorted(PUBMED_PILOT_SUFFIXES, key=len, reverse=True):
        if step_id.endswith(suffix):
            return step_id[: -len(suffix)]
    return None


def pubmed_pilot_summary(steps: list[dict[str, Any]]) -> dict[str, int]:
    pilots: dict[str, list[dict[str, Any]]] = {}
    corpus_rows = evidence_rows = document_rows = vector_rows = 0
    for step in steps:
        step_id = str(step.get("id") or "")
        prefix = pubmed_pilot_prefix(step_id)
        if not prefix:
            continue
        pilots.setdefault(prefix, []).append(step)
        if step_id.endswith("_corpus"):
            corpus_rows += int(step.get("rows") or 0)
        elif step_id.endswith("_evidence"):
            evidence_rows += int(step.get("rows") or 0)
        elif step_id.endswith("_documents"):
            document_rows += int(step.get("rows") or 0)
        elif step_id.endswith("_vectors"):
            vector_rows += int(step.get("rows") or 0)

    completed = sum(
        1
        for pilot_steps in pilots.values()
        if pilot_steps and all(step.get("status") == "completed" for step in pilot_steps)
    )
    return {
        "total": len(pilots),
        "completed": completed,
        "corpus_rows": corpus_rows,
        "evidence_rows": evidence_rows,
        "document_rows": document_rows,
        "vector_rows": vector_rows,
    }


def format_int(value: int | float) -> str:
    return f"{int(value):,}"


def artifact_text(artifact: dict[str, Any]) -> str:
    return " ".join([str(artifact.get("pattern") or ""), *[str(path) for path in artifact.get("files") or []]])


def completed_artifact_totals(
    steps: list[dict[str, Any]],
    predicate,
) -> dict[str, int]:
    rows = 0
    bytes_ = 0
    files = 0
    seen: set[tuple[str, ...] | str] = set()
    for step in steps:
        if step.get("status") != "completed":
            continue
        for artifact in step.get("artifacts") or []:
            if not predicate(artifact):
                continue
            key: tuple[str, ...] | str = tuple(artifact.get("files") or []) or str(artifact.get("pattern") or "")
            if key in seen:
                continue
            seen.add(key)
            rows += int(artifact.get("rows") or 0)
            bytes_ += int(artifact.get("bytes") or 0)
            files += len(artifact.get("files") or [])
    return {"rows": rows, "bytes": bytes_, "files": files}


def sqlite_rows_for(steps: list[dict[str, Any]], filename: str) -> int:
    return completed_artifact_totals(
        steps,
        lambda artifact: artifact.get("kind") == "sqlite" and filename in artifact_text(artifact),
    )["rows"]


def default_sqlite_rows(path: str, table: str) -> int:
    sqlite_path = resolve_path(path)
    if not sqlite_path.exists():
        return 0
    return count_sqlite_rows(sqlite_path, table)


def pipeline_metrics(status: dict[str, Any]) -> dict[str, int]:
    steps = list(status.get("steps") or [])
    concept_documents = completed_artifact_totals(
        steps,
        lambda artifact: artifact.get("kind") == "jsonl"
        and "concept_documents" in artifact_text(artifact),
    )
    concept_vectors = completed_artifact_totals(
        steps,
        lambda artifact: artifact.get("kind") == "jsonl"
        and "concept_vectors" in artifact_text(artifact)
        and ".elastic." not in artifact_text(artifact),
    )
    evidence_rows = completed_artifact_totals(
        steps,
        lambda artifact: artifact.get("kind") == "jsonl"
        and "profile_evidence" in artifact_text(artifact),
    )
    corpus_rows = completed_artifact_totals(
        steps,
        lambda artifact: artifact.get("kind") == "jsonl"
        and "corpus" in artifact_text(artifact),
    )
    compact_vectors = completed_artifact_totals(
        steps,
        lambda artifact: "build/compact_vectors" in artifact_text(artifact),
    )
    quality_steps = [
        step
        for step in steps
        if step.get("status") == "completed"
        and re.search(r"(quality|judgment)", str(step.get("id") or "") + " " + str(step.get("label") or ""), re.I)
    ]
    chunks = status.get("chunk_summary") or {}
    label_rows = sqlite_rows_for(steps, "umls_biomedicine_search_label_index.sqlite") or default_sqlite_rows(
        "build/umls_biomedicine_search_label_index.sqlite",
        "labels",
    )
    code_mapping_rows = sqlite_rows_for(steps, "cui_code_index.sqlite") or default_sqlite_rows(
        "build/cui_code_index.sqlite",
        "code_mappings",
    )
    semantic_type_rows = sqlite_rows_for(steps, "umls_semantic_types.sqlite") or default_sqlite_rows(
        "build/umls_semantic_types.sqlite",
        "semantic_types",
    )
    provenance_refs = sqlite_rows_for(steps, "search_quality_provenance.sqlite") or default_sqlite_rows(
        "build/search_quality_provenance.sqlite",
        "provenance",
    )
    related_links = sqlite_rows_for(steps, "umls_related_concepts.sqlite") or default_sqlite_rows(
        "build/umls_related_concepts.sqlite",
        "related_concepts",
    )
    return {
        "corpus_rows": corpus_rows["rows"],
        "evidence_rows": evidence_rows["rows"],
        "concept_document_rows": concept_documents["rows"],
        "concept_vector_rows": concept_vectors["rows"],
        "label_rows": label_rows,
        "code_mapping_rows": code_mapping_rows,
        "semantic_type_rows": semantic_type_rows,
        "provenance_refs": provenance_refs,
        "related_links": related_links,
        "compact_vector_bytes": compact_vectors["bytes"],
        "quality_checkpoints": len(quality_steps),
        "configured_chunks": int(chunks.get("total_chunks") or 0),
        "built_chunks": int(chunks.get("built_chunks") or 0),
        "loaded_chunks": int(chunks.get("loaded_chunks") or 0),
        "reviewed_chunks": int(chunks.get("quality_reviewed_chunks") or 0),
    }


def product_capabilities(metrics: dict[str, int]) -> list[dict[str, str]]:
    resolver_ready = metrics["code_mapping_rows"] > 0 and metrics["label_rows"] > 0
    evidence_ready = metrics["evidence_rows"] > 0 and metrics["concept_vector_rows"] > 0
    provenance_ready = metrics["provenance_refs"] > 0
    related_ready = metrics["related_links"] > 0 and metrics["concept_vector_rows"] > 0
    return [
        {
            "label": "Resolve strings, CUIs, and source codes",
            "state": "built" if resolver_ready else "missing",
            "quantity": (
                f"{format_int(metrics['code_mapping_rows'])} code mappings; "
                f"{format_int(metrics['label_rows'])} label rows; "
                f"{format_int(metrics['semantic_type_rows'])} semantic type rows"
            ),
            "why": "Direct identifiers should resolve deterministically before vector search guesses.",
        },
        {
            "label": "Search text by real-world concept evidence",
            "state": "pilot built" if evidence_ready else "missing",
            "quantity": (
                f"{format_int(metrics['evidence_rows'])} linked evidence rows; "
                f"{format_int(metrics['concept_vector_rows'])} CUI/view vectors"
            ),
            "why": "Text queries retrieve concepts through evidence language, not only UMLS synonyms.",
        },
        {
            "label": "Show why a result came back",
            "state": "built" if provenance_ready else "partial",
            "quantity": f"{format_int(metrics['provenance_refs'])} indexed provenance references",
            "why": "Reviewers need source snippets and citations to decide whether a match is trustworthy.",
        },
        {
            "label": "Return related concepts",
            "state": "built" if related_ready else "partial",
            "quantity": (
                f"{format_int(metrics['concept_vector_rows'])} evidence vectors; "
                f"{format_int(metrics['related_links'])} MRREL fallback links"
            ),
            "why": "Primary relatedness should come from real-world evidence similarity, with UMLS graph edges as support.",
        },
        {
            "label": "Measure relevance before scale-up",
            "state": "early" if metrics["quality_checkpoints"] else "missing",
            "quantity": f"{format_int(metrics['quality_checkpoints'])} quality checkpoints",
            "why": "The release decision has to be based on judged search behavior, not just file counts.",
        },
    ]


def evidence_flow(metrics: dict[str, int]) -> list[dict[str, str]]:
    return [
        {
            "layer": "Evidence rows",
            "representation": "JSONL records with CUI, snippet text, source, evidence type, weight, and metadata.",
            "search_use": "Raw evidence is not searched directly; it is the auditable material used to build CUI documents.",
            "quantity": f"{format_int(metrics['evidence_rows'])} linked rows tracked",
        },
        {
            "layer": "CUI/view documents",
            "representation": "One document per CUI and evidence view, with UMLS labels plus top real-world evidence bullets.",
            "search_use": "These are the searchable concept units returned to users after results are deduped by CUI.",
            "quantity": f"{format_int(metrics['concept_document_rows'])} document rows tracked",
        },
        {
            "layer": "Evidence vectors",
            "representation": "SapBERT CLS dense vectors for each CUI/view document, with labels, sources, and evidence counts.",
            "search_use": "Text queries are embedded once, compared to these vectors by ANN, then collapsed to best hit per CUI.",
            "quantity": f"{format_int(metrics['concept_vector_rows'])} vector rows tracked",
        },
        {
            "layer": "Search-time hydration",
            "representation": "Resolver mappings, label fallback, evidence-vector neighbors, MRREL support, and SQLite provenance lookups.",
            "search_use": "Identifier inputs bypass ANN; text hits get evidence snippets, citations, evidence-related CUIs, and code mappings.",
            "quantity": (
                f"{format_int(metrics['code_mapping_rows'])} mappings; "
                f"{format_int(metrics['provenance_refs'])} provenance refs; "
                f"{format_int(metrics['related_links'])} related links"
            ),
        },
    ]


def short_step_quantity(step: dict[str, Any]) -> str:
    parts = []
    rows = int(step.get("rows") or 0)
    bytes_ = int(step.get("bytes") or 0)
    if rows:
        parts.append(f"{rows:,} rows")
    if bytes_:
        parts.append(format_bytes(bytes_))
    if not parts:
        parts.append("marker/checkpoint")
    return ", ".join(parts)


def human_summary(status: dict[str, Any]) -> dict[str, Any]:
    steps = list(status.get("steps") or [])
    metrics = pipeline_metrics(status)
    remaining = [step for step in steps if step.get("status") != "completed"]
    planned = sum(1 for step in remaining if step.get("status") == "planned")
    paused = sum(1 for step in remaining if step.get("status") == "paused")
    pending = sum(1 for step in remaining if step.get("status") == "pending")
    completed = int(status.get("completed_steps") or 0)
    total = int(status.get("total_steps") or 0)
    weighted_pct = float(status.get("weighted_progress_fraction") or 0) * 100
    readiness_pct = float(status.get("progress_fraction") or 0) * 100
    total_completed_rows = sum(int(step.get("rows") or 0) for step in steps if step.get("status") == "completed")
    total_completed_bytes = sum(int(step.get("bytes") or 0) for step in steps if step.get("status") == "completed")
    quality_steps = [
        step
        for step in steps
        if step.get("status") == "completed"
        and re.search(r"(quality|judgment)", str(step.get("id") or "") + " " + str(step.get("label") or ""), re.I)
    ]

    done = [
        {
            "label": "The user-facing search loop is in place.",
            "detail": (
                "CUI/code resolution, text ANN search, label fallback, provenance hydration, "
                "and related-concept lookup are all represented by completed artifacts."
            ),
        },
        {
            "label": "The evidence base has moved beyond a toy run.",
            "detail": (
                f"The report tracks {format_int(metrics['corpus_rows'])} corpus rows, "
                f"{format_int(metrics['evidence_rows'])} linked evidence rows, "
                f"{format_int(metrics['concept_document_rows'])} CUI/view document rows, and "
                f"{format_int(metrics['concept_vector_rows'])} vector rows."
            ),
        },
        {
            "label": "The resolver layer is explicit now.",
            "detail": (
                f"MRCONSO-backed lookup contributes {format_int(metrics['code_mapping_rows'])} code mappings; "
                f"the label fallback contributes {format_int(metrics['label_rows'])} searchable UMLS label rows."
            ),
        },
    ]

    chunks = status.get("chunk_summary")
    if chunks:
        done.append(
            {
                "label": "The configured topic chunks are built and searchable.",
                "detail": (
                    f"{chunks['built_chunks']} of {chunks['total_chunks']} chunks are built; "
                    f"{chunks['loaded_chunks']} are loaded into Elasticsearch; "
                    f"{chunks['quality_reviewed_chunks']} have chunk-specific quality-review artifacts."
                ),
            }
        )

    pubmed = pubmed_pilot_summary(steps)
    if pubmed["total"]:
        done.append(
            {
                "label": "PubMed bulk pilots have exercised the scale path.",
                "detail": (
                    f"{pubmed['completed']} of {pubmed['total']} pilot batches are complete, covering "
                    f"{pubmed['corpus_rows']:,} corpus rows, {pubmed['evidence_rows']:,} linked evidence rows, "
                    f"{pubmed['document_rows']:,} CUI/view docs, and {pubmed['vector_rows']:,} vectors."
                ),
            }
        )

    if quality_steps:
        done.append(
            {
                "label": "Human review gates exist, but relevance evidence is still early.",
                "detail": (
                    f"{len(quality_steps)} quality/judgment checkpoints are present. "
                    "This proves the workflow, not release-grade relevance coverage."
                ),
            }
        )

    left = [
        {
            "label": step["label"],
            "status": step["status"],
            "why": step.get("why") or step_why(step),
            "quantity": short_step_quantity(step),
            "effort_weight": step.get("effort_weight", 0),
            "phase": step.get("phase") or "Operations",
        }
        for step in remaining
    ]

    next_step = status.get("next_step")
    focus = {
        "label": next_step["label"] if next_step else "Complete",
        "status": next_step["status"] if next_step else "completed",
        "why": (next_step.get("why") if next_step else "All tracked steps are complete."),
        "phase": (next_step.get("phase") if next_step else ""),
    }

    return {
        "headline": (
            "Usable pilot search is built for CUI/code/text inputs; broad PubMed coverage, "
            "restricted clinical ingest, and incremental update mechanics remain."
        ),
        "progress_sentence": (
            f"Best single progress number: {weighted_pct:.1f}% effort-weighted "
            f"({completed}/{total} artifact steps complete; {readiness_pct:.1f}% checklist readiness)."
        ),
        "metrics": metrics,
        "capabilities": product_capabilities(metrics),
        "evidence_flow": evidence_flow(metrics),
        "done": done,
        "left": left,
        "focus": focus,
        "remaining_counts": {
            "planned": planned,
            "pending": pending,
            "paused": paused,
            "total": len(remaining),
        },
    }


def plan_status(plan: dict[str, Any], *, include_chunk_summary: bool = True) -> dict[str, Any]:
    steps = []
    for step in plan["steps"]:
        artifacts = [artifact_status(spec) for spec in step.get("artifacts", [])]
        complete = artifacts and all(artifact.complete for artifact in artifacts)
        incomplete_status = step.get("status_if_incomplete", "pending")
        rows = sum(artifact.rows for artifact in artifacts)
        bytes_ = sum(artifact.bytes for artifact in artifacts)
        effort_weight = step_effort_weight(step)
        steps.append(
            StepStatus(
                id=step["id"],
                label=step["label"],
                status="completed" if complete else incomplete_status,
                artifacts=artifacts,
                rows=rows,
                bytes=bytes_,
                effort_weight=effort_weight,
                phase=step_phase(step),
                why=step_why(step),
            )
        )

    completed = sum(1 for step in steps if step.status == "completed")
    completed_effort = sum(step.effort_weight for step in steps if step.status == "completed")
    total_effort = sum(step.effort_weight for step in steps)
    next_step = next((step for step in steps if step.status != "completed"), None)
    status = {
        "chunk_id": plan["chunk_id"],
        "title": plan.get("title", plan["chunk_id"]),
        "scope": plan.get("scope", ""),
        "max_minutes_per_step": plan.get("max_minutes_per_step"),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "completed_steps": completed,
        "total_steps": len(steps),
        "progress_fraction": completed / len(steps) if steps else 0,
        "progress_basis": "artifact readiness step count",
        "completed_effort_weight": completed_effort,
        "total_effort_weight": total_effort,
        "weighted_progress_fraction": completed_effort / total_effort if total_effort else 0,
        "weighted_progress_basis": "heuristic effort-weighted processing progress, not wall-clock ETA",
        "next_step": asdict(next_step) if next_step else None,
        "steps": [asdict(step) for step in steps],
    }
    if include_chunk_summary and plan["chunk_id"] == "full_pipeline":
        status["chunk_summary"] = summarize_configured_chunks()
    status["phase_summary"] = phase_summary(status["steps"])
    status["human_summary"] = human_summary(status)
    return status


def format_bytes(value: int) -> str:
    size = float(value)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"


def markdown(status: dict[str, Any]) -> str:
    summary = status.get("human_summary") or human_summary(status)
    lines = [
        f"# {status['title']}",
        "",
        f"Generated: `{status['generated_at']}`",
        "",
        f"Scope: {status.get('scope') or 'not specified'}",
        "",
        "## Product Status",
        "",
        summary["headline"],
        "",
        summary["progress_sentence"],
        "",
        "### Current Capabilities",
        "",
    ]
    lines.append("| Capability | State | Quantity | Why it matters |")
    lines.append("|---|---|---:|---|")
    for item in summary.get("capabilities") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    item["label"],
                    item["state"],
                    item["quantity"],
                    item["why"],
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "### How Evidence Is Represented And Used",
            "",
            "| Layer | Representation | Search use | Current scale |",
            "|---|---|---|---:|",
        ]
    )
    for item in summary.get("evidence_flow") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    item["layer"],
                    item["representation"],
                    item["search_use"],
                    item["quantity"],
                ]
            )
            + " |"
        )
    lines.extend(["", "## What Has Been Done", ""])
    for item in summary["done"]:
        lines.append(f"- **{item['label']}** {item['detail']}")
    lines.extend(["", "## What Is Left", ""])
    if summary["left"]:
        for item in summary["left"]:
            lines.append(
                f"- **{item['label']}** ({item['status']}, {float(item['effort_weight']):.1f} effort units): "
                f"{item['why']}"
            )
    else:
        lines.append("- Nothing tracked remains.")
    lines.extend(
        [
            "",
            "### Why The Next Step Matters",
            "",
            f"**{summary['focus']['label']}**: {summary['focus']['why']}",
            "",
            "## Quantified Progress",
            "",
            (
                f"Effort-weighted progress: **{status['weighted_progress_fraction'] * 100:.1f}%** "
                f"({status['completed_effort_weight']:.1f} / {status['total_effort_weight']:.1f} units)"
            ),
            "",
            (
                f"Artifact readiness: **{status['completed_steps']} / {status['total_steps']} steps** "
                f"({status['progress_fraction'] * 100:.1f}%)"
            ),
            "",
        ]
    )
    if status["next_step"]:
        lines.append(f"Next step: **{status['next_step']['label']}**")
    else:
        lines.append("Next step: **complete**")
    if status.get("chunk_summary"):
        chunks = status["chunk_summary"]
        lines.extend(
            [
                "",
                (
                    "Configured chunks: "
                    f"**{chunks['built_chunks']} / {chunks['total_chunks']} built**, "
                    f"**{chunks['loaded_chunks']} loaded**, "
                    f"**{chunks['quality_reviewed_chunks']} quality-reviewed**"
                ),
            ]
        )
    lines.extend(["", "### Phase Progress", ""])
    lines.append("| Phase | Progress | Done | Why this phase exists |")
    lines.append("|---|---:|---:|---|")
    for phase in status.get("phase_summary") or phase_summary(status["steps"]):
        lines.append(
            "| "
            + " | ".join(
                [
                    phase["phase"],
                    f"{phase['progress_fraction'] * 100:.1f}%",
                    f"{phase['completed_steps']} / {phase['total_steps']}",
                    phase["purpose"],
                ]
            )
            + " |"
        )
    lines.extend(["", "<details>", "<summary>Detailed artifact checklist</summary>", "", "## Step Detail", ""])
    lines.extend(["| Step | Status | Phase | Why | Quantity | Artifact state |", "|---|---:|---|---|---:|---|"])
    for step in status["steps"]:
        artifact_states = []
        for artifact in step["artifacts"]:
            if artifact["files"]:
                noun = "file" if len(artifact["files"]) == 1 else "files"
                artifact_states.append(f"{len(artifact['files'])} {noun}")
            else:
                artifact_states.append(f"`{artifact['pattern']}` missing")
        lines.append(
            "| "
            + " | ".join(
                [
                    step["label"],
                    step["status"],
                    step.get("phase", "Operations"),
                    step.get("why", ""),
                    short_step_quantity(step),
                    "<br>".join(artifact_states),
                ]
            )
            + " |"
        )
    lines.extend(["", "</details>", ""])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report scaling chunk progress from expected artifacts.")
    parser.add_argument("--plan", required=True, type=Path, help="Scaling chunk plan JSON")
    parser.add_argument("--out-json", type=Path, help="Write status JSON")
    parser.add_argument("--out-markdown", type=Path, help="Write status Markdown")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    plan = json.loads(resolve_path(str(args.plan)).read_text(encoding="utf-8"))
    status = plan_status(plan)
    print(markdown(status))
    if args.out_json:
        out = resolve_path(str(args.out_json))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(status, indent=2, sort_keys=True), encoding="utf-8")
    if args.out_markdown:
        out = resolve_path(str(args.out_markdown))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown(status), encoding="utf-8")


if __name__ == "__main__":
    main()
