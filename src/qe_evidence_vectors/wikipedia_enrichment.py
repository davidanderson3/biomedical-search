from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .schema import ConceptDocument

DEFAULT_SOURCE = "wikipedia"
DEFAULT_VIEW = "wikipedia_summary"
DEFAULT_LICENSE = "CC BY-SA 4.0"


def load_wikipedia_specs(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        concepts = payload.get("concepts")
    else:
        concepts = payload
    if not isinstance(concepts, list):
        raise ValueError("Wikipedia enrichment config must be a list or contain a concepts list")
    return [dict(item) for item in concepts if isinstance(item, dict)]


def build_wikipedia_documents(specs: Iterable[dict[str, Any]]) -> list[ConceptDocument]:
    return [wikipedia_document_from_spec(spec) for spec in specs]


def wikipedia_document_from_spec(spec: dict[str, Any]) -> ConceptDocument:
    cui = required_string(spec, "cui").upper()
    title = required_string(spec, "title")
    url = required_string(spec, "url")
    accessed = required_string(spec, "accessed")
    labels = string_list(spec.get("labels")) or [title]
    evidence = string_list(spec.get("evidence"))
    relations = relation_specs(spec)
    summary = str(spec.get("summary") or "").strip()
    source = str(spec.get("source") or DEFAULT_SOURCE).strip() or DEFAULT_SOURCE
    view = str(spec.get("view") or DEFAULT_VIEW).strip() or DEFAULT_VIEW
    weight = float(spec.get("weight") or 1.0)

    lines = [
        f"CUI: {cui}",
        f"Evidence view: {view}",
        "Wikipedia source:",
        f"- Title: {title}",
        f"- URL: {url}",
        f"- Accessed: {accessed}",
        "UMLS labels:",
    ]
    lines.extend(f"- {label}" for label in labels)
    if summary:
        lines.extend(["Summary:", f"- {summary}"])
    if relations:
        lines.append("Linked CUI relationships:")
        for relation in relations:
            label = relation.get("label") or relation["cui"]
            relation_text = relation.get("rela") or relation.get("relation") or "related_to"
            lines.append(f"- {label} ({relation['cui']}): {relation_text}")
    if evidence:
        lines.append("Open literature evidence:")
        lines.extend(f"- {item} (weight {weight:g})" for item in evidence)

    metadata = {
        "document_builder": "wikipedia_enrichment",
        "source": source,
        "source_title": title,
        "source_url": url,
        "source_accessed": accessed,
        "source_license": str(spec.get("license") or DEFAULT_LICENSE),
        "relations": relations,
    }
    for key in ("semantic_type", "field", "domain", "notes"):
        value = spec.get(key)
        if value:
            metadata[key] = value

    return ConceptDocument(
        doc_id=str(spec.get("doc_id") or f"{cui}:{view}"),
        cui=cui,
        view=view,
        text="\n".join(lines),
        evidence_count=len(evidence),
        sources=[source],
        labels=labels,
        metadata=metadata,
    )


def relation_specs(spec: dict[str, Any]) -> list[dict[str, Any]]:
    raw_relations = spec.get("relations") or []
    if not isinstance(raw_relations, list):
        raise ValueError(f"{spec.get('cui') or '<missing cui>'}: relations must be a list")
    source = str(spec.get("source") or DEFAULT_SOURCE).strip() or DEFAULT_SOURCE
    relations: list[dict[str, Any]] = []
    for rank, raw_relation in enumerate(raw_relations, start=1):
        if not isinstance(raw_relation, dict):
            raise ValueError(f"{spec.get('cui') or '<missing cui>'}: relation must be an object")
        target_cui = str(raw_relation.get("cui") or "").strip().upper()
        if not target_cui:
            raise ValueError(f"{spec.get('cui') or '<missing cui>'}: relation missing cui")
        relation = {
            "cui": target_cui,
            "label": str(raw_relation.get("label") or "").strip(),
            "category": str(raw_relation.get("category") or "").strip(),
            "relation_group": str(raw_relation.get("relation_group") or "associated").strip()
            or "associated",
            "relation": str(raw_relation.get("relation") or "related_to").strip() or "related_to",
            "rela": str(raw_relation.get("rela") or raw_relation.get("relation") or "related_to").strip()
            or "related_to",
            "source": str(raw_relation.get("source") or source).strip() or source,
            "direction": str(raw_relation.get("direction") or "outgoing").strip() or "outgoing",
            "rank": int(raw_relation.get("rank") or rank),
        }
        relations.append(relation)
    relations.sort(key=lambda item: int(item.get("rank") or 0))
    return relations


def required_string(spec: dict[str, Any], key: str) -> str:
    value = str(spec.get(key) or "").strip()
    if not value:
        raise ValueError(f"Wikipedia enrichment concept missing required field: {key}")
    return value


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        raise ValueError("expected a string or list of strings")
    items = []
    seen = set()
    for item in value:
        text = str(item or "").strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        items.append(text)
    return items
