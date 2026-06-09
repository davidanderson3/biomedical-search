from __future__ import annotations

import gzip
import io
import json
import re
import urllib.request
from collections import Counter
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .code_index import CodeIndex, is_cui, normalize_sab
from .schema import write_jsonl
from .universal_relationship import attach_universal_edge


PUBTATOR3_BASE_URL = "https://ftp.ncbi.nlm.nih.gov/pub/lu/PubTator3"
PUBTATOR3_RELATION_URL = f"{PUBTATOR3_BASE_URL}/relation2pubtator3.gz"
PUBTATOR3_README_URL = f"{PUBTATOR3_BASE_URL}/README.txt"

SYSTEM_ALIASES = {
    "MESH": "MSH",
    "MESHID": "MSH",
    "NCBIGENE": "NCBI",
    "GENE": "NCBI",
    "GENEID": "NCBI",
    "TAXONOMY": "NCBI",
}

RELATION_TYPE_MAP = {
    "associate": "associated_with",
    "association": "associated_with",
    "positive_correlation": "associated_with",
    "positive_correlate": "associated_with",
    "negative_correlation": "associated_with",
    "negative_correlate": "associated_with",
    "cause": "causes",
    "treat": "treats",
    "inhibit": "inhibits",
    "stimulate": "stimulates",
    "co_treatment": "co_treatment",
    "drug_interaction": "drug_interaction",
    "comparison": "compared_with",
    "conversion": "converts_to",
    "binding": "binds",
}

RELATION_GROUP_MAP = {
    "associated_with": "associated",
    "binds": "binding",
    "co_treatment": "treatment",
    "compared_with": "comparison",
    "converts_to": "conversion",
    "drug_interaction": "drug_interaction",
    "treats": "treatment",
}

BIDIRECTIONAL_RELATION_TYPES = {
    "associated_with",
    "binds",
    "compared_with",
    "drug_interaction",
}


@dataclass(frozen=True)
class PubTator3Concept:
    raw: str
    entity_type: str
    system: str
    identifier: str


@dataclass(frozen=True)
class PubTator3Relation:
    pmid: str
    relation: str
    subject: PubTator3Concept
    object: PubTator3Concept
    line_number: int


def _relation_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def normalized_pubtator3_relation_type(value: str) -> str:
    key = _relation_key(value)
    return RELATION_TYPE_MAP.get(key, key or "associated_with")


def relation_group_for_pubtator3_type(relationship_type: str) -> str:
    return RELATION_GROUP_MAP.get(relationship_type, relationship_type or "associated")


def direction_for_pubtator3_type(relationship_type: str) -> str:
    if relationship_type in BIDIRECTIONAL_RELATION_TYPES:
        return "bidirectional"
    return "subject_to_object"


def parse_pubtator3_concept(value: str) -> PubTator3Concept | None:
    text = str(value or "").strip()
    if not text or "|" not in text:
        return None
    entity_type, identifier_text = text.split("|", 1)
    entity_type = entity_type.strip()
    identifier_text = identifier_text.strip()
    if not entity_type or not identifier_text:
        return None
    if ":" in identifier_text:
        system, identifier = identifier_text.split(":", 1)
    else:
        system, identifier = "", identifier_text
    system = SYSTEM_ALIASES.get(system.strip().upper(), normalize_sab(system))
    identifier = identifier.strip()
    if not identifier:
        return None
    return PubTator3Concept(
        raw=text,
        entity_type=entity_type,
        system=system,
        identifier=identifier,
    )


def parse_pubtator3_relation_line(line: str, *, line_number: int) -> PubTator3Relation | None:
    parts = line.rstrip("\n").split("\t")
    if len(parts) != 4:
        return None
    pmid, relation, subject_text, object_text = (part.strip() for part in parts)
    if not pmid or not relation:
        return None
    subject = parse_pubtator3_concept(subject_text)
    object_ = parse_pubtator3_concept(object_text)
    if subject is None or object_ is None:
        return None
    return PubTator3Relation(
        pmid=pmid,
        relation=relation,
        subject=subject,
        object=object_,
        line_number=line_number,
    )


def _open_text_lines(source: str | Path, *, timeout: int = 60) -> Iterator[str]:
    text = str(source)
    if text.startswith(("http://", "https://")):
        with urllib.request.urlopen(text, timeout=timeout) as response:
            binary = gzip.GzipFile(fileobj=response) if text.endswith(".gz") else response
            with io.TextIOWrapper(binary, encoding="utf-8", errors="replace") as handle:
                yield from handle
        return

    path = Path(source).expanduser()
    opener = gzip.open if path.suffix == ".gz" else path.open
    context = opener(path, "rt", encoding="utf-8", errors="replace") if path.suffix == ".gz" else opener(
        "r", encoding="utf-8", errors="replace"
    )
    with context:
        yield from context


def resolve_pubtator3_concept(
    concept: PubTator3Concept,
    code_index: CodeIndex | None,
) -> dict[str, str] | None:
    if is_cui(concept.identifier):
        label = code_index.preferred_label(concept.identifier) if code_index else ""
        return {
            "cui": concept.identifier.upper(),
            "label": label or concept.identifier.upper(),
            "sab": "CUI",
            "code": concept.identifier.upper(),
        }
    if code_index is None:
        return None

    rows = []
    if concept.system:
        rows = code_index.lookup_code(concept.identifier, sab=concept.system, limit=5)
    if not rows:
        rows = code_index.lookup_code(concept.identifier, limit=5)
    if not rows:
        return None
    row = rows[0]
    return {
        "cui": str(row.get("cui") or "").upper(),
        "label": str(row.get("label") or row.get("cui") or ""),
        "sab": str(row.get("sab") or concept.system),
        "code": str(row.get("code") or concept.identifier),
        "mapping_count": str(len(rows)),
    }


def pubtator3_relation_edge(
    relation: PubTator3Relation,
    *,
    code_index: CodeIndex | None,
) -> dict | None:
    subject = resolve_pubtator3_concept(relation.subject, code_index)
    object_ = resolve_pubtator3_concept(relation.object, code_index)
    if not subject or not object_:
        return None
    subject_cui = subject["cui"]
    object_cui = object_["cui"]
    if not subject_cui or not object_cui or subject_cui == object_cui:
        return None

    relationship_type = normalized_pubtator3_relation_type(relation.relation)
    relation_group = relation_group_for_pubtator3_type(relationship_type)
    direction = direction_for_pubtator3_type(relationship_type)
    source_url = f"https://pubmed.ncbi.nlm.nih.gov/{relation.pmid}/"
    row = {
        "source": "pubtator3",
        "source_class": "pubtator3_relation_sample",
        "subject_cui": subject_cui,
        "subject_label": subject["label"],
        "object_cui": object_cui,
        "object_label": object_["label"],
        "relationship_type": relationship_type,
        "relation": relationship_type,
        "rela": relationship_type,
        "relation_group": relation_group,
        "direction": direction,
        "support_count": 1,
        "supporting_pmids": [relation.pmid],
        "supporting_doc_ids": [f"PMID:{relation.pmid}"],
        "rank": relation.line_number,
        "pubtator3": {
            "pmid": relation.pmid,
            "relation": relation.relation,
            "subject": relation.subject.__dict__,
            "object": relation.object.__dict__,
            "subject_mapping": subject,
            "object_mapping": object_,
            "source_url": source_url,
        },
    }
    return attach_universal_edge(
        row,
        subject_cui=subject_cui,
        object_cui=object_cui,
        context={
            "pmid": relation.pmid,
            "source_url": source_url,
            "pubtator3_relation": relation.relation,
            "pubtator3_relation_line": relation.line_number,
            "automated_text_mining": True,
        },
    )


def iter_pubtator3_relation_edges(
    source: str | Path = PUBTATOR3_RELATION_URL,
    *,
    code_index_path: str | Path | None = None,
    max_records: int = 1000,
    max_input_lines: int = 0,
    include_relation_types: set[str] | None = None,
    timeout: int = 60,
) -> Iterator[dict]:
    code_index = CodeIndex(code_index_path) if code_index_path else None
    emitted = 0
    include_keys = {_relation_key(item) for item in include_relation_types or set() if item}
    try:
        for line_number, line in enumerate(_open_text_lines(source, timeout=timeout), start=1):
            if max_input_lines and line_number > max_input_lines:
                break
            parsed = parse_pubtator3_relation_line(line, line_number=line_number)
            if parsed is None:
                continue
            if include_keys and _relation_key(parsed.relation) not in include_keys:
                continue
            edge = pubtator3_relation_edge(parsed, code_index=code_index)
            if edge is None:
                continue
            yield edge
            emitted += 1
            if max_records and emitted >= max_records:
                break
    finally:
        if code_index is not None:
            code_index.close()


def write_pubtator3_relation_sample(
    *,
    source: str | Path = PUBTATOR3_RELATION_URL,
    out_path: str | Path,
    manifest_path: str | Path | None = None,
    code_index_path: str | Path | None = None,
    max_records: int = 1000,
    max_input_lines: int = 0,
    include_relation_types: set[str] | None = None,
    timeout: int = 60,
) -> dict[str, object]:
    out_path = Path(out_path).expanduser()
    records = list(
        iter_pubtator3_relation_edges(
            source,
            code_index_path=code_index_path,
            max_records=max_records,
            max_input_lines=max_input_lines,
            include_relation_types=include_relation_types,
            timeout=timeout,
        )
    )
    count = write_jsonl(out_path, records)
    relation_counts = Counter(str(record.get("relationship_type") or "") for record in records)
    entity_pair_counts = Counter(
        f"{record.get('pubtator3', {}).get('subject', {}).get('entity_type')}->"
        f"{record.get('pubtator3', {}).get('object', {}).get('entity_type')}"
        for record in records
    )
    manifest = {
        "source": "pubtator3",
        "source_url": str(source),
        "readme_url": PUBTATOR3_README_URL,
        "code_index": str(code_index_path or ""),
        "output": str(out_path),
        "max_records": max_records,
        "max_input_lines": max_input_lines,
        "records": count,
        "relation_counts": dict(sorted(relation_counts.items())),
        "entity_pair_counts": dict(sorted(entity_pair_counts.items())),
        "notes": [
            "Small sampled PubTator3 relation extract.",
            "Rows are automated text-mined relation annotations mapped to UMLS CUIs when possible.",
            "Treat as candidate relationship evidence, not as manually reviewed truth.",
        ],
    }
    if manifest_path:
        manifest_target = Path(manifest_path).expanduser()
        manifest_target.parent.mkdir(parents=True, exist_ok=True)
        manifest_target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
