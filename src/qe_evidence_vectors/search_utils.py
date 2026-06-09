from __future__ import annotations

from array import array
from collections import Counter
import json
import re
from pathlib import Path

from qe_evidence_vectors.documents import evidence_view
from qe_evidence_vectors.evidence import iter_evidence_jsonl
from qe_evidence_vectors.provenance_index import citation_from_evidence
from qe_evidence_vectors.text import normalized_key


WEIGHT_RE = re.compile(r" \(weight ([0-9.]+)\)$")
SENTENCE_BOUNDARY_RE = re.compile(r"[.!?][\"')\]]*(?=\s+|$)")
SENTENCE_BOUNDARY_ABBREVIATIONS = (
    "dr.",
    "mr.",
    "mrs.",
    "ms.",
    "prof.",
    "fig.",
    "ref.",
    "refs.",
    "vs.",
    "etc.",
    "e.g.",
    "i.e.",
    "et al.",
    "u.s.",
    "u.k.",
)


def dot(left: array, right: array) -> float:
    total = 0.0
    for left_value, right_value in zip(left, right):
        total += left_value * right_value
    return total


def sentence_bounded_evidence_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return ""
    for match in SENTENCE_BOUNDARY_RE.finditer(cleaned):
        candidate = cleaned[: match.end()].strip()
        lower = candidate.lower()
        if any(lower.endswith(abbreviation) for abbreviation in SENTENCE_BOUNDARY_ABBREVIATIONS):
            continue
        if re.search(r"(?:\b[a-z]\.){2,}$", lower):
            continue
        return candidate
    return cleaned if cleaned.endswith((".", "!", "?")) else f"{cleaned.rstrip(' ,;:')}."


def _source_name(source: dict | str) -> str:
    if isinstance(source, str):
        return source
    return str(source.get("source") or source.get("label") or source.get("corpus_doc_id") or "").strip()


def source_mix_from_evidence_items(
    evidence_items: list[dict],
    *,
    declared_sources: list[str],
    evidence_count: int,
) -> dict:
    counts: Counter[str] = Counter()
    total_refs = 0
    for item in evidence_items:
        for source in item.get("sources") or []:
            name = _source_name(source)
            if not name:
                continue
            counts[name] += 1
            total_refs += 1
    for source in declared_sources:
        if source:
            counts.setdefault(source, 0)
    items = [
        {
            "source": source,
            "sample_refs": count,
            "sample_pct": round(count / total_refs, 4) if total_refs else None,
        }
        for source, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    ]
    return {
        "basis": "hydrated evidence sample source refs",
        "note": "Counts describe visible/top evidence citations, not an independent source-weighted score.",
        "evidence_count": evidence_count,
        "sample_refs": total_refs,
        "items": items,
    }


def merge_labels(primary: list[str], secondary: list[str]) -> list[str]:
    merged = []
    seen = set()
    for label in [*primary, *secondary]:
        key = str(label).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(str(label))
    return merged


def merge_definition_lists(primary: list[dict], secondary: list[dict]) -> list[dict]:
    merged = []
    seen = set()
    for item in [*primary, *secondary]:
        if not isinstance(item, dict):
            continue
        definition = str(item.get("definition") or "").strip()
        if not definition:
            continue
        key = (str(item.get("source") or ""), normalized_key(definition))
        if key in seen:
            continue
        seen.add(key)
        merged.append(
            {
                "cui": item.get("cui") or "",
                "source": item.get("source") or "",
                "definition": definition,
                "rank": int(item.get("rank") or len(merged) + 1),
            }
        )
    return merged


def concept_display_name(labels: list[str], *, fallback: str) -> str:
    cleaned = merge_labels(labels, [])
    if not cleaned:
        return fallback
    for label in cleaned:
        if "^" not in label and ":" not in label and len(label) <= 120:
            return label
    for label in cleaned:
        if "^" not in label and len(label) <= 160:
            return label
    return cleaned[0]




def load_evidence_provenance(paths: list[Path]) -> dict[tuple[str, str], list[dict]]:
    provenance: dict[tuple[str, str], list[dict]] = {}
    seen: dict[tuple[str, str], set[str]] = {}
    for path in paths:
        if not path.exists():
            continue
        for record in iter_evidence_jsonl(path):
            doc_id = f"{record.cui}:{evidence_view(record.evidence_type)}"
            key = (doc_id, normalized_key(record.text))
            citation = citation_from_evidence(record)
            citation_key = json.dumps(citation, sort_keys=True)
            key_seen = seen.setdefault(key, set())
            if citation_key in key_seen:
                continue
            key_seen.add(citation_key)
            bucket = provenance.setdefault(key, [])
            if len(bucket) < 5:
                bucket.append(citation)
    return provenance


def annotated_evidence_items(
    doc_id: str,
    text: str,
    provenance_by_doc_text: dict[tuple[str, str], list[dict]],
) -> list[dict]:
    items = parse_document_evidence(text)
    for item in items:
        item["sources"] = provenance_by_doc_text.get((doc_id, normalized_key(item["text"])), [])
    return items


def parse_document_evidence(text: str) -> list[dict]:
    items: list[dict] = []
    in_evidence = False
    for line in text.splitlines():
        if line in {"Real-world evidence:", "Open literature evidence:"}:
            in_evidence = True
            continue
        if not in_evidence or not line.startswith("- "):
            continue
        evidence_text = line[2:]
        weight = None
        match = WEIGHT_RE.search(evidence_text)
        if match:
            weight = float(match.group(1))
            evidence_text = evidence_text[: match.start()]
        items.append({"text": evidence_text, "weight": weight, "sources": []})
    return items
