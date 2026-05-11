from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .mrconso_labels import collect_labels
from .evidence import iter_evidence_jsonl
from .schema import ConceptDocument, EvidenceRecord, iter_jsonl
from .text import normalized_key


QUERY_TYPES = {
    "failed_query",
    "query",
    "clicked_query",
    "search_log",
    "manual_search",
}
PROSE_TYPES = {
    "reviewed_snippet",
    "clinical_snippet",
    "patient_language",
    "prose",
    "note",
}


def evidence_from_jsonl(path: str | Path) -> list[EvidenceRecord]:
    return list(iter_evidence_jsonl(path))


def iter_documents_jsonl(path: str | Path):
    for payload in iter_jsonl(path):
        yield ConceptDocument(
            doc_id=payload["doc_id"],
            cui=payload["cui"],
            view=payload["view"],
            text=payload["text"],
            evidence_count=int(payload["evidence_count"]),
            sources=list(payload.get("sources", [])),
            labels=list(payload.get("labels", [])),
            metadata=payload.get("metadata", {}),
        )


def evidence_view(evidence_type: str) -> str:
    key = normalized_key(evidence_type).replace(" ", "_")
    if key in QUERY_TYPES:
        return "query_language"
    if key in PROSE_TYPES:
        return "prose_evidence"
    return key or "evidence"


def _dedupe_top(records: list[EvidenceRecord], max_items: int) -> list[EvidenceRecord]:
    best_by_text: dict[str, EvidenceRecord] = {}
    for record in records:
        key = normalized_key(record.text)
        current = best_by_text.get(key)
        if current is None or record.weight > current.weight:
            best_by_text[key] = record
    return sorted(best_by_text.values(), key=lambda record: (-record.weight, record.text))[:max_items]


def document_text(cui: str, view: str, labels: list[str], records: list[EvidenceRecord]) -> str:
    lines = [f"CUI: {cui}", f"Evidence view: {view}"]
    if labels:
        lines.append("UMLS labels:")
        lines.extend(f"- {label}" for label in labels)
    lines.append("Real-world evidence:")
    for record in records:
        if record.weight == 1:
            lines.append(f"- {record.text}")
        else:
            lines.append(f"- {record.text} (weight {record.weight:g})")
    return "\n".join(lines)


def build_documents(
    evidence_records: list[EvidenceRecord],
    *,
    mrconso_path: str | Path | None = None,
    max_labels: int = 8,
    max_items_per_doc: int = 100,
) -> list[ConceptDocument]:
    cuis = {record.cui for record in evidence_records}
    labels = collect_labels(mrconso_path, cuis, max_labels=max_labels) if mrconso_path else {}

    grouped: dict[tuple[str, str], list[EvidenceRecord]] = defaultdict(list)
    for record in evidence_records:
        grouped[(record.cui, evidence_view(record.evidence_type))].append(record)

    documents = []
    for (cui, view), records in sorted(grouped.items()):
        top_records = _dedupe_top(records, max_items_per_doc)
        sources = sorted({record.source for record in top_records if record.source})
        doc_labels = labels.get(cui, [])
        documents.append(
            ConceptDocument(
                doc_id=f"{cui}:{view}",
                cui=cui,
                view=view,
                text=document_text(cui, view, doc_labels, top_records),
                evidence_count=len(records),
                sources=sources,
                labels=doc_labels,
                metadata={
                    "max_items_per_doc": max_items_per_doc,
                    "total_weight": sum(record.weight for record in records),
                },
            )
        )
    return documents
