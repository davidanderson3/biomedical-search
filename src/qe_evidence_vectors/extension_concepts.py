from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

from .schema import ConceptDocument, EvidenceRecord, iter_jsonl, write_jsonl
from .text import normalized_key


OFFICIAL_CUI_RE = re.compile(r"^C\d{7}$")
NEW_CUI_NAMESPACE = "NEW"
NEW_CUI_DIGITS = 7
DEFAULT_NAMESPACE = NEW_CUI_NAMESPACE
DEFAULT_VIEW = "extension_concept"
DEFAULT_SOURCE = "reviewed_extension_concept"


@dataclass(frozen=True)
class ExtensionConcept:
    concept_id: str
    preferred_label: str
    aliases: list[str] = field(default_factory=list)
    semantic_type: str = ""
    definition: str = ""
    status: str = "candidate"
    broader_cuis: list[str] = field(default_factory=list)
    related_cuis: list[str] = field(default_factory=list)
    close_match_cuis: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def stable_extension_id(
    preferred_label: str,
    *,
    semantic_type: str = "",
    namespace: str = DEFAULT_NAMESPACE,
) -> str:
    seed = "\t".join([normalized_key(semantic_type), normalized_key(preferred_label)])
    digest = hashlib.blake2b(seed.encode("utf-8"), digest_size=8).digest()
    if namespace.upper() == NEW_CUI_NAMESPACE:
        value = int.from_bytes(digest, byteorder="big") % (10**NEW_CUI_DIGITS)
        return f"{NEW_CUI_NAMESPACE}{value:0{NEW_CUI_DIGITS}d}"
    return f"{namespace}{digest.hex().upper()[:12]}"


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split("|") if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def _evidence_items(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    output: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, str):
            text = item.strip()
            if text:
                output.append({"text": text})
            continue
        if not isinstance(item, dict):
            raise ValueError("extension concept evidence entries must be strings or objects")
        text = str(item.get("text") or "").strip()
        if not text:
            raise ValueError("extension concept evidence object is missing text")
        output.append(dict(item, text=text))
    return output


def concept_from_payload(payload: dict[str, Any], *, namespace: str = DEFAULT_NAMESPACE) -> ExtensionConcept:
    preferred_label = str(payload.get("preferred_label") or payload.get("label") or "").strip()
    if not preferred_label:
        raise ValueError("extension concept is missing preferred_label")
    semantic_type = str(payload.get("semantic_type") or "").strip()
    concept_id = str(
        payload.get("concept_id")
        or payload.get("provisional_id")
        or payload.get("cui")
        or stable_extension_id(preferred_label, semantic_type=semantic_type, namespace=namespace)
    ).strip()
    if OFFICIAL_CUI_RE.match(concept_id.upper()):
        raise ValueError(
            f"{concept_id} looks like an official UMLS CUI; use a local extension ID instead"
        )
    aliases = _as_list(payload.get("aliases") or payload.get("synonyms"))
    labels = [preferred_label]
    for alias in aliases:
        if normalized_key(alias) != normalized_key(preferred_label):
            labels.append(alias)
    return ExtensionConcept(
        concept_id=concept_id,
        preferred_label=preferred_label,
        aliases=labels[1:],
        semantic_type=semantic_type,
        definition=str(payload.get("definition") or "").strip(),
        status=str(payload.get("status") or "candidate").strip() or "candidate",
        broader_cuis=_as_list(payload.get("broader_cuis") or payload.get("parents")),
        related_cuis=_as_list(payload.get("related_cuis") or payload.get("related")),
        close_match_cuis=_as_list(payload.get("close_match_cuis") or payload.get("close_matches")),
        evidence=_evidence_items(payload.get("evidence")),
        metadata=dict(payload.get("metadata") or {}),
    )


def iter_extension_concepts(path: str | Path, *, namespace: str = DEFAULT_NAMESPACE) -> Iterator[ExtensionConcept]:
    for payload in iter_jsonl(path):
        yield concept_from_payload(payload, namespace=namespace)


def _document_text(concept: ExtensionConcept, view: str, records: list[EvidenceRecord]) -> str:
    lines = [f"CUI: {concept.concept_id}", f"Evidence view: {view}", "Extension concept:"]
    lines.append(f"- Preferred label: {concept.preferred_label}")
    if concept.semantic_type:
        lines.append(f"- Semantic type: {concept.semantic_type}")
    lines.append(f"- Status: {concept.status}")
    if concept.definition:
        lines.append(f"- Definition: {concept.definition}")
    if concept.broader_cuis:
        lines.append(f"- Broader UMLS CUIs: {', '.join(concept.broader_cuis)}")
    if concept.related_cuis:
        lines.append(f"- Related UMLS CUIs: {', '.join(concept.related_cuis)}")
    if concept.close_match_cuis:
        lines.append(f"- Close-match UMLS CUIs: {', '.join(concept.close_match_cuis)}")
    lines.append("Candidate labels:")
    lines.append(f"- {concept.preferred_label}")
    lines.extend(f"- {alias}" for alias in concept.aliases)
    lines.append("Real-world evidence:")
    for record in records:
        if record.weight == 1:
            lines.append(f"- {record.text}")
        else:
            lines.append(f"- {record.text} (weight {record.weight:g})")
    return "\n".join(lines)


def concept_to_records(
    concept: ExtensionConcept,
    *,
    view: str = DEFAULT_VIEW,
    default_source: str = DEFAULT_SOURCE,
    max_items_per_doc: int = 100,
) -> tuple[ConceptDocument, list[EvidenceRecord]]:
    evidence_records: list[EvidenceRecord] = []
    for index, item in enumerate(concept.evidence, start=1):
        metadata = dict(item.get("metadata") or {})
        metadata.update(
            {
                "extension_concept_id": concept.concept_id,
                "preferred_label": concept.preferred_label,
                "status": concept.status,
            }
        )
        evidence_records.append(
            EvidenceRecord(
                evidence_id=str(item.get("evidence_id") or f"{concept.concept_id}:{view}:{index:06d}"),
                cui=concept.concept_id,
                text=str(item["text"]),
                source=str(item.get("source") or default_source),
                evidence_type=str(item.get("evidence_type") or view),
                weight=float(item.get("weight", 1.0)),
                metadata=metadata,
            )
        )
    best_by_text: dict[str, EvidenceRecord] = {}
    for record in evidence_records:
        key = normalized_key(record.text)
        current = best_by_text.get(key)
        if current is None or record.weight > current.weight:
            best_by_text[key] = record
    top_records = sorted(best_by_text.values(), key=lambda record: (-record.weight, record.text))[
        :max_items_per_doc
    ]
    labels = [concept.preferred_label, *concept.aliases]
    sources = sorted({record.source for record in top_records if record.source})
    document = ConceptDocument(
        doc_id=f"{concept.concept_id}:{view}",
        cui=concept.concept_id,
        view=view,
        text=_document_text(concept, view, top_records),
        evidence_count=len(evidence_records),
        sources=sources,
        labels=labels,
        metadata={
            "concept_origin": "extension",
            "status": concept.status,
            "semantic_type": concept.semantic_type,
            "definition": concept.definition,
            "broader_cuis": concept.broader_cuis,
            "related_cuis": concept.related_cuis,
            "close_match_cuis": concept.close_match_cuis,
            "max_items_per_doc": max_items_per_doc,
            **concept.metadata,
        },
    )
    return document, evidence_records


def build_extension_concept_artifacts(
    *,
    input_path: str | Path,
    out_docs: str | Path,
    out_evidence: str | Path,
    out_registry: str | Path | None = None,
    namespace: str = DEFAULT_NAMESPACE,
    view: str = DEFAULT_VIEW,
    default_source: str = DEFAULT_SOURCE,
    max_items_per_doc: int = 100,
    min_evidence: int = 1,
    include_status: set[str] | None = None,
) -> tuple[int, int]:
    documents: list[ConceptDocument] = []
    evidence_records: list[EvidenceRecord] = []
    registry_rows: list[dict[str, Any]] = []
    seen_concept_ids: dict[str, str] = {}
    for concept in iter_extension_concepts(input_path, namespace=namespace):
        if include_status is not None and concept.status not in include_status:
            continue
        if len(concept.evidence) < min_evidence:
            continue
        existing_label = seen_concept_ids.get(concept.concept_id)
        if existing_label is not None:
            raise ValueError(
                f"duplicate extension concept id {concept.concept_id} for "
                f"{existing_label!r} and {concept.preferred_label!r}"
            )
        seen_concept_ids[concept.concept_id] = concept.preferred_label
        document, records = concept_to_records(
            concept,
            view=view,
            default_source=default_source,
            max_items_per_doc=max_items_per_doc,
        )
        documents.append(document)
        evidence_records.extend(records)
        registry_rows.append(
            {
                "concept_id": concept.concept_id,
                "preferred_label": concept.preferred_label,
                "aliases": concept.aliases,
                "semantic_type": concept.semantic_type,
                "definition": concept.definition,
                "status": concept.status,
                "broader_cuis": concept.broader_cuis,
                "related_cuis": concept.related_cuis,
                "close_match_cuis": concept.close_match_cuis,
                "evidence_count": len(records),
                "metadata": concept.metadata,
            }
        )
    doc_count = write_jsonl(out_docs, documents)
    evidence_count = write_jsonl(out_evidence, evidence_records)
    if out_registry:
        write_jsonl(out_registry, registry_rows)
    return doc_count, evidence_count
