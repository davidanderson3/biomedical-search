#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]

TRACK_ALIASES = {
    "pm": "precision_medicine",
    "precision": "precision_medicine",
    "precision_medicine": "precision_medicine",
    "trec_pm": "precision_medicine",
    "cds": "clinical_decision_support",
    "clinical": "clinical_decision_support",
    "clinical_decision_support": "clinical_decision_support",
    "trec_cds": "clinical_decision_support",
}
TRACK_LABELS = {
    "precision_medicine": "TREC Precision Medicine",
    "clinical_decision_support": "TREC Clinical Decision Support",
}
DEFAULT_CORPUS_GLOBS = (
    "build/pubmed*_corpus.jsonl",
    "build/pubmed*_corpus.jsonl.gz",
    "build/europepmc*_corpus.jsonl",
    "build/europepmc*_corpus.jsonl.gz",
    "build/pmc_oa*_corpus.jsonl",
    "build/pmc_oa*_corpus.jsonl.gz",
    "build/public/clinicaltrials*_corpus.jsonl",
    "build/public/clinicaltrials*_corpus.jsonl.gz",
    "build/source_acquisition/*clinicaltrials*.jsonl",
    "build/source_acquisition/*clinicaltrials*.jsonl.gz",
)

NCT_RE = re.compile(r"\bNCT\d{8}\b", re.IGNORECASE)
PMID_EXPLICIT_RE = re.compile(r"\b(?:PMID|PUBMED)[:\s_/-]*(\d{1,10})\b", re.IGNORECASE)
PMID_URL_RE = re.compile(
    r"(?:pubmed\.ncbi\.nlm\.nih\.gov/|ncbi\.nlm\.nih\.gov/pubmed/)(\d{1,10})",
    re.IGNORECASE,
)
PMID_BARE_RE = re.compile(r"\d{1,10}")
TAG_RE = re.compile(r"<(?P<tag>[A-Za-z0-9_-]+)>\s*(?P<text>.*?)(?=(?:\n\s*<[A-Za-z0-9_-]+>)|\Z)", re.DOTALL)
IDLIKE_KEY_PARTS = (
    "pmid",
    "pubmed",
    "nct",
    "clinicaltrial",
    "clinical_trial",
    "trial_id",
    "doc_id",
    "document_id",
    "source_id",
    "source_doc",
    "external_id",
    "record_id",
    "article_id",
    "url",
    "uri",
    "link",
)
TOPIC_TEXT_FIELDS = (
    "query",
    "title",
    "summary",
    "description",
    "disease",
    "gene",
    "variant",
    "demographic",
    "treatment",
    "intervention",
    "other",
    "note",
    "narrative",
    "text",
)
TOPIC_FIELDS = [
    "track",
    "topic_id",
    "query",
    "title",
    "summary",
    "description",
    "disease",
    "gene",
    "variant",
    "demographic",
    "treatment",
    "intervention",
    "other",
    "note",
    "narrative",
]
QREL_FIELDS = [
    "track",
    "topic_id",
    "doc_id",
    "raw_doc_id",
    "source_type",
    "relevance",
    "is_positive",
]
COVERAGE_FIELDS = [
    "track",
    "topic_id",
    "doc_id",
    "raw_doc_id",
    "source_type",
    "relevance",
    "is_positive",
    "resolved",
    "corpus_doc_ids",
    "corpus_sources",
    "corpus_titles",
]
QUERY_FIELDS = [
    "id",
    "query",
    "expected_doc_ids",
    "expected_pubmed_ids",
    "expected_clinical_trial_ids",
    "why",
    "benchmark_type",
    "track",
    "topic_id",
    "unjudged_policy",
    "coverage_policy",
]
RESULT_FIELDS = [
    "id",
    "benchmark_type",
    "track",
    "topic_id",
    "expected_doc_ids",
    "expected_count",
    "expected_source_types",
    "found_at_1",
    "found_at_3",
    "found_at_5",
    "found_at_10",
    "found_at_k",
    "recall_at_10",
    "recall_at_k",
    "first_expected_rank",
    "reciprocal_first_expected_rank",
    "found_doc_ids",
    "found_doc_id_ranks",
    "hit_doc_ids",
    "unscored_doc_ids_seen",
    "top_cui",
    "top_name",
    "elapsed_ms",
    "server_elapsed_ms",
    "backend",
    "query",
]


@dataclass(frozen=True)
class TrecTopic:
    track: str
    topic_id: str
    query: str
    fields: dict[str, str]


@dataclass(frozen=True)
class TrecQrel:
    track: str
    topic_id: str
    doc_id: str
    raw_doc_id: str
    relevance: float

    @property
    def source_type(self) -> str:
        return source_type_for_doc_id(self.doc_id)

    @property
    def is_positive(self) -> bool:
        return self.relevance > 0


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_track(value: str) -> str:
    track = TRACK_ALIASES.get(clean_text(value).lower())
    if not track:
        allowed = ", ".join(sorted(TRACK_LABELS))
        raise ValueError(f"unknown TREC track {value!r}; expected one of: {allowed}")
    return track


def source_type_for_doc_id(doc_id: str) -> str:
    if doc_id.startswith("PMID:"):
        return "pubmed"
    if doc_id.startswith("NCT:"):
        return "clinicaltrials_gov"
    return "unknown"


def normalize_pmid_digits(value: str) -> str:
    stripped = value.lstrip("0")
    return stripped or "0"


def extract_doc_ids_from_text(value: object, *, allow_bare_pmid: bool = False) -> set[str]:
    text = clean_text(value)
    if not text:
        return set()
    doc_ids: set[str] = set()
    for match in NCT_RE.finditer(text):
        doc_ids.add(f"NCT:{match.group(0).upper()}")
    for match in PMID_EXPLICIT_RE.finditer(text):
        doc_ids.add(f"PMID:{normalize_pmid_digits(match.group(1))}")
    for match in PMID_URL_RE.finditer(text):
        doc_ids.add(f"PMID:{normalize_pmid_digits(match.group(1))}")
    if allow_bare_pmid and PMID_BARE_RE.fullmatch(text):
        doc_ids.add(f"PMID:{normalize_pmid_digits(text)}")
    return doc_ids


def normalize_doc_id(value: object, *, allow_bare_pmid: bool = True) -> str:
    doc_ids = extract_doc_ids_from_text(value, allow_bare_pmid=allow_bare_pmid)
    if not doc_ids:
        return ""
    return sorted(doc_ids)[0]


def split_doc_ids(value: object) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    doc_ids: list[str] = []
    for part in re.split(r"[|,;]\s*|\s+", text):
        normalized = normalize_doc_id(part, allow_bare_pmid=True)
        if normalized and normalized not in doc_ids:
            doc_ids.append(normalized)
    return doc_ids


def is_identifier_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in IDLIKE_KEY_PARTS)


def collect_identifiers_from_object(value: object, *, parent_key: str = "") -> set[str]:
    ids: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            ids.update(collect_identifiers_from_object(child, parent_key=str(key)))
        return ids
    if isinstance(value, list):
        for child in value:
            ids.update(collect_identifiers_from_object(child, parent_key=parent_key))
        return ids
    if isinstance(value, (str, int, float)) and is_identifier_key(parent_key):
        ids.update(
            extract_doc_ids_from_text(
                value,
                allow_bare_pmid=any(part in parent_key.lower() for part in ("pmid", "pubmed", "doc_id", "source_id")),
            )
        )
    return ids


def xml_tag_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1].lower()


def topic_id_from_text(value: object) -> str:
    text = clean_text(value)
    match = re.search(r"\d+", text)
    return match.group(0) if match else text


def compose_topic_query(fields: dict[str, str]) -> str:
    parts: list[str] = []
    for field in TOPIC_TEXT_FIELDS:
        value = clean_text(fields.get(field))
        if not value:
            continue
        if field in {"query", "title", "summary", "description", "text"}:
            parts.append(value)
        else:
            parts.append(f"{field.replace('_', ' ').title()}: {value}")
    return clean_text(". ".join(parts))


def parse_xml_topics(path: Path, *, track: str) -> list[TrecTopic]:
    root = ET.parse(path).getroot()
    nodes = [root] if xml_tag_name(root) == "topic" else root.findall(".//topic")
    topics: list[TrecTopic] = []
    for index, node in enumerate(nodes, start=1):
        fields: dict[str, str] = {}
        for child in list(node):
            tag = xml_tag_name(child)
            text = clean_text(" ".join(child.itertext()))
            if text:
                fields[tag] = text
        topic_id = clean_text(
            node.attrib.get("number")
            or node.attrib.get("id")
            or node.attrib.get("topic")
            or fields.get("num")
            or fields.get("number")
            or fields.get("id")
            or index
        )
        topic_id = topic_id_from_text(topic_id)
        query = clean_text(fields.get("query")) or compose_topic_query(fields)
        if query:
            topics.append(TrecTopic(track=track, topic_id=topic_id, query=query, fields=fields))
    return topics


def parse_delimited_topics(path: Path, *, track: str) -> list[TrecTopic]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        sample = handle.readline()
        handle.seek(0)
        delimiter = "\t" if "\t" in sample else ","
        reader = csv.DictReader(handle, delimiter=delimiter)
        topics: list[TrecTopic] = []
        for index, row in enumerate(reader, start=1):
            fields = {str(key or "").lower(): clean_text(value) for key, value in row.items()}
            topic_id = clean_text(
                fields.get("topic_id")
                or fields.get("topic")
                or fields.get("number")
                or fields.get("num")
                or fields.get("id")
                or index
            )
            topic_id = topic_id_from_text(topic_id)
            query = clean_text(fields.get("query") or fields.get("question") or fields.get("text"))
            query = query or compose_topic_query(fields)
            if query:
                topics.append(TrecTopic(track=track, topic_id=topic_id, query=query, fields=fields))
    return topics


def parse_tagged_text_topics(path: Path, *, track: str) -> list[TrecTopic]:
    text = path.read_text(encoding="utf-8")
    blocks = [block for block in re.split(r"\n\s*\n", text) if block.strip()]
    topics: list[TrecTopic] = []
    for index, block in enumerate(blocks, start=1):
        fields = {
            match.group("tag").lower(): clean_text(match.group("text"))
            for match in TAG_RE.finditer(block)
        }
        if not fields:
            pieces = block.strip().split(None, 1)
            if len(pieces) == 2:
                fields = {"num": pieces[0], "query": pieces[1]}
        topic_id = topic_id_from_text(
            fields.get("num") or fields.get("number") or fields.get("id") or index
        )
        query = clean_text(fields.get("query") or fields.get("title")) or compose_topic_query(fields)
        if query:
            topics.append(TrecTopic(track=track, topic_id=topic_id, query=query, fields=fields))
    return topics


def parse_topics(path: Path, *, track: str) -> list[TrecTopic]:
    track = normalize_track(track)
    prefix = path.read_text(encoding="utf-8", errors="ignore")[:512].lstrip()
    if prefix.startswith("<") and "<topic" in prefix.lower():
        topics = parse_xml_topics(path, track=track)
    elif "\t" in prefix.splitlines()[0] or "," in prefix.splitlines()[0]:
        topics = parse_delimited_topics(path, track=track)
    else:
        topics = parse_tagged_text_topics(path, track=track)
    if not topics:
        raise ValueError(f"no TREC topics could be parsed from {path}")
    return topics


def parse_qrels(path: Path, *, track: str) -> list[TrecQrel]:
    track = normalize_track(track)
    qrels: list[TrecQrel] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if len(parts) >= 4:
                topic_id, raw_doc_id, relevance = parts[0], parts[2], parts[3]
            elif len(parts) == 3:
                topic_id, raw_doc_id, relevance = parts
            else:
                raise ValueError(f"malformed qrels line {line_number} in {path}: {line.rstrip()}")
            try:
                rel_value = float(relevance)
            except ValueError as exc:
                raise ValueError(f"invalid relevance value on line {line_number}: {relevance!r}") from exc
            doc_id = normalize_doc_id(raw_doc_id, allow_bare_pmid=True) or clean_text(raw_doc_id)
            qrels.append(
                TrecQrel(
                    track=track,
                    topic_id=topic_id_from_text(topic_id),
                    doc_id=doc_id,
                    raw_doc_id=raw_doc_id,
                    relevance=rel_value,
                )
            )
    if not qrels:
        raise ValueError(f"no TREC qrels could be parsed from {path}")
    return qrels


def merge_qrels(qrels: Iterable[TrecQrel]) -> list[TrecQrel]:
    merged: dict[tuple[str, str], TrecQrel] = {}
    for qrel in qrels:
        key = (qrel.topic_id, qrel.doc_id)
        previous = merged.get(key)
        if previous is None or qrel.relevance > previous.relevance:
            merged[key] = qrel
    return sorted(merged.values(), key=lambda row: (row.topic_id, row.source_type, row.doc_id))


def default_corpus_paths() -> list[Path]:
    paths: set[Path] = set()
    for pattern in DEFAULT_CORPUS_GLOBS:
        paths.update(path for path in ROOT.glob(pattern) if path.is_file())
    return sorted(paths)


def topic_rows(topics: Iterable[TrecTopic]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for topic in topics:
        row = {"track": topic.track, "topic_id": topic.topic_id, "query": topic.query}
        for field in TOPIC_FIELDS:
            row.setdefault(field, topic.fields.get(field, ""))
        rows.append(row)
    return rows


def qrel_rows(qrels: Iterable[TrecQrel]) -> list[dict[str, str]]:
    return [
        {
            "track": qrel.track,
            "topic_id": qrel.topic_id,
            "doc_id": qrel.doc_id,
            "raw_doc_id": qrel.raw_doc_id,
            "source_type": qrel.source_type,
            "relevance": f"{qrel.relevance:g}",
            "is_positive": "1" if qrel.is_positive else "0",
        }
        for qrel in qrels
    ]


def corpus_input_files(paths: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.rglob("*.jsonl")))
            files.extend(sorted(path.rglob("*.jsonl.gz")))
            files.extend(sorted(path.rglob("*.ndjson")))
            files.extend(sorted(path.rglob("*.json")))
        elif path.exists():
            files.append(path)
    return files


def open_text(path: Path):
    if path.name.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def iter_corpus_records(paths: Iterable[Path]) -> Iterable[tuple[dict, Path, int]]:
    for path in corpus_input_files(paths):
        if path.suffix == ".json" and not path.name.endswith(".jsonl.gz"):
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                records = data
            elif isinstance(data, dict) and isinstance(data.get("documents"), list):
                records = data["documents"]
            elif isinstance(data, dict):
                records = [data]
            else:
                records = []
            for index, record in enumerate(records, start=1):
                if isinstance(record, dict):
                    yield record, path, index
            continue
        with open_text(path) as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                record = json.loads(stripped)
                if isinstance(record, dict):
                    yield record, path, line_number


def corpus_record_ref(record: dict, path: Path, line_number: int) -> dict[str, str]:
    doc_id = clean_text(record.get("doc_id") or record.get("id") or record.get("source_id"))
    source = clean_text(record.get("source") or record.get("source_name") or record.get("dataset"))
    title = clean_text(record.get("title") or record.get("name") or record.get("label"))
    return {
        "doc_id": doc_id or f"{path}:{line_number}",
        "source": source,
        "title": title,
        "path": str(path),
        "line": str(line_number),
    }


def build_corpus_index(paths: Iterable[Path]) -> tuple[dict[str, list[dict[str, str]]], dict[str, object]]:
    files = corpus_input_files(paths)
    index: dict[str, list[dict[str, str]]] = {}
    records = 0
    for record, path, line_number in iter_corpus_records(files):
        records += 1
        ids = collect_identifiers_from_object(record)
        if not ids:
            continue
        ref = corpus_record_ref(record, path, line_number)
        for doc_id in sorted(ids):
            bucket = index.setdefault(doc_id, [])
            if ref not in bucket:
                bucket.append(ref)
    summary = {
        "corpus_inputs": [str(path) for path in paths],
        "corpus_files": [str(path) for path in files],
        "corpus_records": records,
        "indexed_identifiers": len(index),
    }
    return index, summary


def build_coverage_rows(
    qrels: Iterable[TrecQrel],
    corpus_index: dict[str, list[dict[str, str]]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for qrel in qrels:
        hits = corpus_index.get(qrel.doc_id, [])
        rows.append(
            {
                "track": qrel.track,
                "topic_id": qrel.topic_id,
                "doc_id": qrel.doc_id,
                "raw_doc_id": qrel.raw_doc_id,
                "source_type": qrel.source_type,
                "relevance": f"{qrel.relevance:g}",
                "is_positive": "1" if qrel.is_positive else "0",
                "resolved": "1" if hits else "0",
                "corpus_doc_ids": "|".join(ref.get("doc_id", "") for ref in hits),
                "corpus_sources": "|".join(sorted({ref.get("source", "") for ref in hits if ref.get("source")})),
                "corpus_titles": "|".join(ref.get("title", "") for ref in hits if ref.get("title")),
            }
        )
    return rows


def summarize_coverage(
    qrels: Iterable[TrecQrel],
    rows: list[dict[str, str]],
    corpus_summary: dict[str, object],
) -> dict[str, object]:
    qrel_list = list(qrels)
    positive_rows = [row for row in rows if row["is_positive"] == "1"]
    all_resolved = sum(1 for row in rows if row["resolved"] == "1")
    positive_resolved = sum(1 for row in positive_rows if row["resolved"] == "1")
    by_source_type: dict[str, dict[str, object]] = {}
    for source_type in sorted({row["source_type"] for row in rows}):
        source_rows = [row for row in rows if row["source_type"] == source_type]
        source_positive = [row for row in source_rows if row["is_positive"] == "1"]
        by_source_type[source_type] = {
            "judgments": len(source_rows),
            "positive_judgments": len(source_positive),
            "resolved": sum(1 for row in source_rows if row["resolved"] == "1"),
            "positive_resolved": sum(1 for row in source_positive if row["resolved"] == "1"),
        }
    return {
        **corpus_summary,
        "judgments": len(qrel_list),
        "positive_judgments": len(positive_rows),
        "resolved_judgments": all_resolved,
        "positive_resolved": positive_resolved,
        "coverage_rate": round(all_resolved / len(rows), 6) if rows else 0.0,
        "positive_coverage_rate": round(positive_resolved / len(positive_rows), 6) if positive_rows else 0.0,
        "by_source_type": by_source_type,
    }


def document_query_rows(
    topics: Iterable[TrecTopic],
    qrels: Iterable[TrecQrel],
    *,
    allowed_doc_ids: set[str] | None = None,
    coverage_policy: str = "all_judged_positives",
) -> list[dict[str, str]]:
    positives_by_topic: dict[str, list[str]] = {}
    for qrel in qrels:
        if not qrel.is_positive:
            continue
        if allowed_doc_ids is not None and qrel.doc_id not in allowed_doc_ids:
            continue
        positives_by_topic.setdefault(qrel.topic_id, [])
        if qrel.doc_id not in positives_by_topic[qrel.topic_id]:
            positives_by_topic[qrel.topic_id].append(qrel.doc_id)
    rows: list[dict[str, str]] = []
    for topic in topics:
        expected = sorted(positives_by_topic.get(topic.topic_id, []))
        if not expected:
            continue
        pmids = [doc_id.removeprefix("PMID:") for doc_id in expected if doc_id.startswith("PMID:")]
        ncts = [doc_id.removeprefix("NCT:") for doc_id in expected if doc_id.startswith("NCT:")]
        rows.append(
            {
                "id": f"trec_{topic.track}_{topic.topic_id}_document_source",
                "query": topic.query,
                "expected_doc_ids": "|".join(expected),
                "expected_pubmed_ids": "|".join(pmids),
                "expected_clinical_trial_ids": "|".join(ncts),
                "why": (
                    f"{TRACK_LABELS[topic.track]} topic {topic.topic_id}; qrels relevance>0 "
                    "documents/trials are positives. Unjudged returned documents are unknown, not false positives. "
                    f"Coverage policy: {coverage_policy}."
                ),
                "benchmark_type": "document_source_retrieval",
                "track": topic.track,
                "topic_id": topic.topic_id,
                "unjudged_policy": "unknown_not_false_positive",
                "coverage_policy": coverage_policy,
            }
        )
    return rows


def write_tsv(path: Path, rows: list[dict[str, str]], *, fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def read_query_rows(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(
                (line for line in handle if line.strip() and not line.lstrip().startswith("#")),
                delimiter="\t",
            )
            for index, row in enumerate(reader, start=1):
                query = clean_text(row.get("query"))
                expected = split_doc_ids(row.get("expected_doc_ids"))
                if not query or not expected:
                    continue
                rows.append(
                    {
                        **{str(key): clean_text(value) for key, value in row.items()},
                        "id": clean_text(row.get("id") or f"{path.stem}_{index}"),
                        "query": query,
                        "expected_doc_ids": "|".join(expected),
                    }
                )
    return rows


def search_api(
    base_url: str,
    query: str,
    *,
    top_k: int,
    mode: str,
    scope: str,
    related: bool,
    timeout: float,
) -> tuple[dict, float]:
    params = urllib.parse.urlencode(
        {
            "q": query,
            "k": top_k,
            "mode": mode,
            "scope": scope,
            "related": "1" if related else "0",
            "linked": "0",
            "evidence_items": "1",
            "codes": "default",
        }
    )
    url = f"{base_url.rstrip('/')}/api/search?{params}"
    started = time.time()
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = json.load(response)
    return payload, time.time() - started


def score_payload(row: dict[str, str], payload: dict, *, elapsed_seconds: float, top_k: int) -> dict[str, str]:
    expected = set(split_doc_ids(row.get("expected_doc_ids")))
    hits = list(payload.get("hits") or [])
    found_ranks: dict[str, int] = {}
    ranked_doc_ids: list[str] = []
    for rank, hit in enumerate(hits[:top_k], start=1):
        hit_ids = sorted(collect_identifiers_from_object(hit))
        for doc_id in hit_ids:
            if doc_id not in ranked_doc_ids:
                ranked_doc_ids.append(doc_id)
            if doc_id in expected and doc_id not in found_ranks:
                found_ranks[doc_id] = rank

    def found_count(limit: int) -> int:
        return sum(1 for rank in found_ranks.values() if rank <= limit)

    first_rank = min(found_ranks.values()) if found_ranks else 0
    expected_source_types = sorted({source_type_for_doc_id(doc_id) for doc_id in expected})
    unscored_seen = [doc_id for doc_id in ranked_doc_ids if doc_id not in expected]
    found_doc_ids = sorted(found_ranks, key=lambda doc_id: (found_ranks[doc_id], doc_id))
    top = hits[0] if hits else {}
    expected_count = len(expected)
    found_at_10 = found_count(min(10, top_k))
    found_at_k = found_count(top_k)
    return {
        "id": row.get("id", ""),
        "benchmark_type": row.get("benchmark_type", "document_source_retrieval"),
        "track": row.get("track", ""),
        "topic_id": row.get("topic_id", ""),
        "expected_doc_ids": "|".join(sorted(expected)),
        "expected_count": str(expected_count),
        "expected_source_types": "|".join(expected_source_types),
        "found_at_1": str(found_count(1)),
        "found_at_3": str(found_count(min(3, top_k))),
        "found_at_5": str(found_count(min(5, top_k))),
        "found_at_10": str(found_at_10),
        "found_at_k": str(found_at_k),
        "recall_at_10": f"{found_at_10 / expected_count:.6f}" if expected_count else "0.000000",
        "recall_at_k": f"{found_at_k / expected_count:.6f}" if expected_count else "0.000000",
        "first_expected_rank": str(first_rank),
        "reciprocal_first_expected_rank": f"{1 / first_rank:.6f}" if first_rank else "0.000000",
        "found_doc_ids": "|".join(found_doc_ids),
        "found_doc_id_ranks": "|".join(f"{doc_id}:{found_ranks[doc_id]}" for doc_id in found_doc_ids),
        "hit_doc_ids": "|".join(ranked_doc_ids),
        "unscored_doc_ids_seen": "|".join(unscored_seen),
        "top_cui": clean_text(top.get("cui") or ""),
        "top_name": clean_text(top.get("name") or top.get("label") or ""),
        "elapsed_ms": f"{elapsed_seconds * 1000:.1f}",
        "server_elapsed_ms": clean_text(payload.get("elapsed_ms") or ""),
        "backend": clean_text(payload.get("backend") or ""),
        "query": row.get("query", ""),
    }


def float_field(row: dict[str, str], field: str) -> float:
    try:
        return float(row.get(field) or 0.0)
    except ValueError:
        return 0.0


def summarize_results(rows: list[dict[str, str]], *, top_k: int) -> dict[str, object]:
    if not rows:
        return {
            "queries": 0,
            "top_k": top_k,
            "document_source_retrieval": True,
            "unjudged_policy": "unknown_not_false_positive",
        }

    def rate(field: str) -> float:
        return round(sum(1 for row in rows if int(row.get(field) or 0) > 0) / len(rows), 6)

    summary: dict[str, object] = {
        "queries": len(rows),
        "top_k": top_k,
        "document_source_retrieval": True,
        "unjudged_policy": "unknown_not_false_positive",
        "top1_hit_rate": rate("found_at_1"),
        "top3_hit_rate": rate("found_at_3"),
        "top5_hit_rate": rate("found_at_5"),
        "top10_hit_rate": rate("found_at_10"),
        "topk_hit_rate": rate("found_at_k"),
        "mean_recall_at_10": round(sum(float_field(row, "recall_at_10") for row in rows) / len(rows), 6),
        "mean_recall_at_k": round(sum(float_field(row, "recall_at_k") for row in rows) / len(rows), 6),
        "mrr": round(sum(float_field(row, "reciprocal_first_expected_rank") for row in rows) / len(rows), 6),
        "mean_elapsed_ms": round(sum(float_field(row, "elapsed_ms") for row in rows) / len(rows), 1),
    }
    by_track: dict[str, dict[str, object]] = {}
    for track in sorted({row.get("track") or "unknown" for row in rows}):
        track_rows = [row for row in rows if (row.get("track") or "unknown") == track]
        by_track[track] = {
            "queries": len(track_rows),
            "top10_hit_rate": round(
                sum(1 for row in track_rows if int(row.get("found_at_10") or 0) > 0) / len(track_rows),
                6,
            ),
            "mean_recall_at_10": round(
                sum(float_field(row, "recall_at_10") for row in track_rows) / len(track_rows),
                6,
            ),
        }
    summary["by_track"] = by_track
    by_source_type: dict[str, dict[str, object]] = {}
    source_types = sorted(
        {
            source_type_for_doc_id(doc_id)
            for row in rows
            for doc_id in split_doc_ids(row.get("expected_doc_ids"))
        }
    )
    for source_type in source_types:
        expected_total = 0
        found_total_at_10 = 0
        found_total_at_k = 0
        queries_with_expected = 0
        queries_with_hit_at_10 = 0
        for row in rows:
            expected_docs = [
                doc_id
                for doc_id in split_doc_ids(row.get("expected_doc_ids"))
                if source_type_for_doc_id(doc_id) == source_type
            ]
            if not expected_docs:
                continue
            queries_with_expected += 1
            expected_total += len(expected_docs)
            found_ranks: dict[str, int] = {}
            for part in str(row.get("found_doc_id_ranks") or "").split("|"):
                if not part or ":" not in part:
                    continue
                doc_id, rank_text = part.rsplit(":", 1)
                if source_type_for_doc_id(doc_id) != source_type:
                    continue
                try:
                    found_ranks[doc_id] = int(rank_text)
                except ValueError:
                    continue
            found_at_10 = sum(1 for doc_id in expected_docs if found_ranks.get(doc_id, top_k + 1) <= min(10, top_k))
            found_at_k = sum(1 for doc_id in expected_docs if found_ranks.get(doc_id, top_k + 1) <= top_k)
            found_total_at_10 += found_at_10
            found_total_at_k += found_at_k
            if found_at_10:
                queries_with_hit_at_10 += 1
        by_source_type[source_type] = {
            "queries_with_expected": queries_with_expected,
            "expected_documents": expected_total,
            "found_documents_at_10": found_total_at_10,
            "found_documents_at_k": found_total_at_k,
            "document_recall_at_10": round(found_total_at_10 / expected_total, 6) if expected_total else 0.0,
            "document_recall_at_k": round(found_total_at_k / expected_total, 6) if expected_total else 0.0,
            "query_hit_rate_at_10": round(queries_with_hit_at_10 / queries_with_expected, 6)
            if queries_with_expected
            else 0.0,
        }
    summary["by_source_type"] = by_source_type
    return summary


def prepare(args: argparse.Namespace) -> int:
    track = normalize_track(args.track)
    topics = parse_topics(args.topics, track=track)
    qrel_paths = list(args.qrels or [])
    qrels = merge_qrels(qrel for path in qrel_paths for qrel in parse_qrels(path, track=track))
    corpus_paths = list(args.corpus or []) or default_corpus_paths()
    corpus_index, corpus_summary = build_corpus_index(corpus_paths)
    coverage = build_coverage_rows(qrels, corpus_index)
    coverage_summary = summarize_coverage(qrels, coverage, corpus_summary)
    queries = document_query_rows(topics, qrels)
    resolved_positive_doc_ids = {
        row["doc_id"]
        for row in coverage
        if row.get("is_positive") == "1" and row.get("resolved") == "1"
    }
    resolved_queries = document_query_rows(
        topics,
        qrels,
        allowed_doc_ids=resolved_positive_doc_ids,
        coverage_policy="resolved_local_judged_positives",
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"trec_{track}"
    topics_path = args.output_dir / f"{prefix}_topics.tsv"
    qrels_path = args.output_dir / f"{prefix}_qrels.tsv"
    coverage_path = args.output_dir / f"{prefix}_corpus_coverage.tsv"
    queries_path = args.output_dir / f"{prefix}_document_queries.tsv"
    resolved_queries_path = args.output_dir / f"{prefix}_resolved_document_queries.tsv"
    manifest_path = args.output_dir / f"{prefix}_manifest.json"
    write_tsv(topics_path, topic_rows(topics), fields=TOPIC_FIELDS)
    write_tsv(qrels_path, qrel_rows(qrels), fields=QREL_FIELDS)
    write_tsv(coverage_path, coverage, fields=COVERAGE_FIELDS)
    write_tsv(queries_path, queries, fields=QUERY_FIELDS)
    write_tsv(resolved_queries_path, resolved_queries, fields=QUERY_FIELDS)

    manifest = {
        "track": track,
        "track_label": TRACK_LABELS[track],
        "topics_path": str(args.topics),
        "qrels_paths": [str(path) for path in qrel_paths],
        "topics": len(topics),
        "qrels": len(qrels),
        "positive_qrels": sum(1 for qrel in qrels if qrel.is_positive),
        "document_query_rows": len(queries),
        "resolved_document_query_rows": len(resolved_queries),
        "coverage": coverage_summary,
        "corpus_source": "user_supplied" if args.corpus else "default_local_discovery",
        "unjudged_policy": "unknown_not_false_positive",
        "outputs": {
            "topics": str(topics_path),
            "qrels": str(qrels_path),
            "coverage": str(coverage_path),
            "document_queries": str(queries_path),
            "resolved_document_queries": str(resolved_queries_path),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


def evaluate(args: argparse.Namespace) -> int:
    rows = read_query_rows(args.queries)
    if args.limit > 0:
        rows = rows[: args.limit]
    results: list[dict[str, str]] = []
    payload_path = args.output_dir / "payloads.jsonl" if args.output_dir else None
    payload_handle = None
    if payload_path:
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        payload_handle = payload_path.open("w", encoding="utf-8")
    try:
        for row in rows:
            payload, elapsed = search_api(
                args.base_url,
                row["query"],
                top_k=args.top_k,
                mode=args.mode,
                scope=args.scope,
                related=args.related,
                timeout=args.timeout,
            )
            if payload_handle:
                payload_handle.write(
                    json.dumps(
                        {
                            "id": row.get("id"),
                            "query": row.get("query"),
                            "expected_doc_ids": row.get("expected_doc_ids"),
                            "response": payload,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
            results.append(score_payload(row, payload, elapsed_seconds=elapsed, top_k=args.top_k))
    finally:
        if payload_handle:
            payload_handle.close()

    summary = summarize_results(results, top_k=args.top_k)
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        write_tsv(args.output_dir / "rows.tsv", results, fields=RESULT_FIELDS)
        (args.output_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare and run local TREC Precision Medicine / Clinical Decision "
            "Support document-source benchmarks."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare", help="Import topics/qrels and report corpus coverage.")
    prepare_parser.add_argument("--track", required=True, choices=sorted(TRACK_ALIASES))
    prepare_parser.add_argument("--topics", required=True, type=Path)
    prepare_parser.add_argument(
        "--qrels",
        required=True,
        action="append",
        type=Path,
        help=(
            "TREC qrels file. Repeat for separate abstract and clinical-trial qrels "
            "so PubMed IDs and NCT IDs are imported into one lane."
        ),
    )
    prepare_parser.add_argument(
        "--corpus",
        action="append",
        default=[],
        type=Path,
        help=(
            "Local JSON/JSONL corpus path or directory to resolve judged PubMed/NCT IDs. "
            "Repeat as needed. Defaults to discovered local PubMed/Europe PMC/PMC OA and "
            "ClinicalTrials.gov corpus artifacts under build/."
        ),
    )
    prepare_parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "build" / "trec_benchmark",
    )
    prepare_parser.set_defaults(func=prepare)

    eval_parser = subparsers.add_parser("evaluate", help="Score prepared document-query TSVs against /api/search.")
    eval_parser.add_argument("queries", type=Path, nargs="+")
    eval_parser.add_argument("--base-url", default="http://127.0.0.1:8766")
    eval_parser.add_argument("--top-k", type=int, default=10)
    eval_parser.add_argument("--mode", choices=["balanced", "exact", "comprehensive"], default="balanced")
    eval_parser.add_argument("--scope", choices=["umls", "umls_evidence"], default="umls_evidence")
    eval_parser.add_argument("--related", action="store_true")
    eval_parser.add_argument("--timeout", type=float, default=60.0)
    eval_parser.add_argument("--limit", type=int, default=0)
    eval_parser.add_argument("--output-dir", type=Path)
    eval_parser.set_defaults(func=evaluate)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
