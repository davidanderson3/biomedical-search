#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qe_evidence_vectors.documents import document_text, evidence_view
from qe_evidence_vectors.embeddings import HashingEmbedder, embed_documents
from qe_evidence_vectors.schema import ConceptDocument, CorpusDocument, EvidenceRecord, write_jsonl
from qe_evidence_vectors.text import clean_text, normalized_key
from qe_evidence_vectors.trie_linker import LabelTrie, iter_linked_corpus_evidence_trie


OPENALEX_WORKS_URL = "https://api.openalex.org/works"
DEFAULT_LABEL_INDEX = ROOT / "build" / "umls_biomedicine_search_label_index.sqlite"
DEFAULT_SEMANTIC_TYPE_INDEX = ROOT / "build" / "umls_semantic_types.sqlite"
DEFAULT_OUT_DIR = ROOT / "build" / "openalex_cited_evidence"
DEFAULT_QUERIES = [
    "clinical medicine",
    "diagnosis treatment disease",
    "drug therapy adverse effects",
    "biomarkers genomics disease",
    "surgery procedure outcomes",
    "laboratory diagnostics biomarkers",
]
GENERIC_MATCH_NORMS = {
    "analysis",
    "associated",
    "associated with",
    "association",
    "at a",
    "based",
    "care",
    "cases",
    "clinical",
    "close",
    "consideration",
    "control",
    "data",
    "diagnosis",
    "diagnosed",
    "diagnostic",
    "disease",
    "diseases",
    "estimate",
    "estimated",
    "estimates",
    "evidence",
    "global",
    "guideline",
    "guidelines",
    "health",
    "immune",
    "improve",
    "in a",
    "incidence",
    "management",
    "medical",
    "medicine",
    "life",
    "million",
    "model",
    "models",
    "mortality",
    "outcome",
    "outcomes",
    "patient",
    "patients",
    "population",
    "prevalence",
    "present",
    "prevention",
    "rate",
    "rates",
    "result",
    "results",
    "response",
    "responsible",
    "review",
    "risk",
    "risks",
    "score",
    "specific",
    "studies",
    "study",
    "surgery",
    "surgical",
    "therapies",
    "therapy",
    "time",
    "treatment",
    "treatments",
    "updated",
    "used",
    "using",
    "version",
    "without",
}
LOW_VALUE_STYS = {
    "Classification",
    "Functional Concept",
    "Idea or Concept",
    "Intellectual Product",
    "Quantitative Concept",
    "Qualitative Concept",
    "Regulation or Law",
    "Spatial Concept",
    "Temporal Concept",
}
ALLOW_SINGLE_TOKEN_STYS = {
    "Amino Acid, Peptide, or Protein",
    "Anatomical Abnormality",
    "Antibiotic",
    "Biologically Active Substance",
    "Clinical Drug",
    "Congenital Abnormality",
    "Diagnostic Procedure",
    "Disease or Syndrome",
    "Finding",
    "Gene or Genome",
    "Injury or Poisoning",
    "Laboratory Procedure",
    "Medical Device",
    "Mental or Behavioral Dysfunction",
    "Neoplastic Process",
    "Organic Chemical",
    "Pathologic Function",
    "Pharmacologic Substance",
    "Sign or Symptom",
    "Therapeutic or Preventive Procedure",
}
SELECT_FIELDS = ",".join(
    [
        "id",
        "doi",
        "display_name",
        "publication_date",
        "publication_year",
        "cited_by_count",
        "abstract_inverted_index",
        "authorships",
        "primary_location",
        "open_access",
        "ids",
        "type",
        "is_retracted",
    ]
)
TTY_PRIORITY = {
    "PT": 0,
    "MH": 1,
    "PN": 2,
    "FN": 3,
    "SY": 4,
}


def default_from_date(today: date | None = None) -> str:
    today = today or date.today()
    try:
        return today.replace(year=today.year - 5).isoformat()
    except ValueError:
        return today.replace(year=today.year - 5, day=28).isoformat()


def read_json_url(url: str, *, timeout: int = 45, retries: int = 3, delay: float = 1.0) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "umls-2.0-openalex-cited-evidence/0.1"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # pragma: no cover - exercised only during network failure.
            last_error = exc
            if attempt < retries:
                time.sleep(delay * attempt)
    raise RuntimeError(f"failed to fetch {url}: {last_error}") from last_error


def abstract_from_inverted_index(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    positions: dict[int, str] = {}
    for word, offsets in index.items():
        for offset in offsets:
            positions[int(offset)] = word
    if not positions:
        return ""
    return clean_text(" ".join(positions[position] for position in sorted(positions)))


def openalex_short_id(openalex_id: str) -> str:
    return str(openalex_id or "").rstrip("/").split("/")[-1]


def normalize_identifier(value: Any, *, prefix: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace("https://doi.org/", "")
    text = text.replace("https://pubmed.ncbi.nlm.nih.gov/", "")
    text = text.replace("https://pmc.ncbi.nlm.nih.gov/articles/", "").strip("/")
    text = text.lower()
    return f"{prefix}:{text}" if prefix else text


def document_identity_keys_from_values(
    *,
    doc_id: str,
    title: str,
    metadata: dict[str, Any],
) -> set[str]:
    keys: set[str] = set()
    for field, prefix in [
        ("openalex_id", "openalex"),
        ("doi", "doi"),
        ("pmid", "pmid"),
        ("pmcid", "pmcid"),
    ]:
        key = normalize_identifier(metadata.get(field), prefix=prefix)
        if key:
            keys.add(key)
    doc_id_text = str(doc_id or "").strip()
    if doc_id_text.upper().startswith("PMID:"):
        keys.add(normalize_identifier(doc_id_text.split(":", 1)[1], prefix="pmid"))
    if doc_id_text.upper().startswith("OPENALEX:"):
        keys.add(normalize_identifier(doc_id_text.split(":", 1)[1], prefix="openalex"))
    title_key = normalized_key(title)
    if title_key:
        keys.add(f"title:{title_key}")
    return keys


def document_identity_keys(document: CorpusDocument) -> set[str]:
    return document_identity_keys_from_values(
        doc_id=document.doc_id,
        title=document.title,
        metadata=document.metadata or {},
    )


def load_existing_document_keys(paths: Iterable[str | Path]) -> set[str]:
    keys: set[str] = set()
    for path in paths:
        path = Path(path).expanduser()
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                payload = json.loads(line)
                keys.update(
                    document_identity_keys_from_values(
                        doc_id=str(payload.get("doc_id") or ""),
                        title=str(payload.get("title") or ""),
                        metadata=payload.get("metadata") or {},
                    )
                )
    return keys


def filter_existing_documents(
    documents: Iterable[CorpusDocument],
    existing_keys: set[str],
) -> tuple[list[CorpusDocument], int]:
    if not existing_keys:
        return list(documents), 0
    kept: list[CorpusDocument] = []
    excluded = 0
    for document in documents:
        if document_identity_keys(document).intersection(existing_keys):
            excluded += 1
            continue
        kept.append(document)
    return kept, excluded


def read_query_file(path: str | Path) -> list[str]:
    path = Path(path).expanduser()
    text = path.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if not lines:
        return []
    if "\t" in lines[0]:
        reader = csv.DictReader(lines, delimiter="\t")
        if reader.fieldnames and "query" in reader.fieldnames:
            return [str(row.get("query") or "").strip() for row in reader if str(row.get("query") or "").strip()]
    return [line.strip() for line in lines]


def write_article_report(path: str | Path, documents: list[CorpusDocument]) -> int:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "rank",
        "doc_id",
        "title",
        "publication_date",
        "cited_by_count",
        "source_name",
        "doi",
        "pmid",
        "openalex_id",
        "query",
        "query_rank",
        "url",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for rank, document in enumerate(documents, start=1):
            metadata = document.metadata or {}
            writer.writerow(
                {
                    "rank": rank,
                    "doc_id": document.doc_id,
                    "title": document.title,
                    "publication_date": metadata.get("publication_date") or "",
                    "cited_by_count": metadata.get("cited_by_count") or 0,
                    "source_name": metadata.get("source_name") or "",
                    "doi": metadata.get("doi") or "",
                    "pmid": metadata.get("pmid") or "",
                    "openalex_id": metadata.get("openalex_id") or "",
                    "query": metadata.get("query") or "",
                    "query_rank": metadata.get("query_rank") or "",
                    "url": metadata.get("url") or "",
                }
            )
    return len(documents)


def first_author_names(work: dict[str, Any], limit: int = 6) -> list[str]:
    names: list[str] = []
    for authorship in work.get("authorships") or []:
        author = authorship.get("author") or {}
        name = str(author.get("display_name") or "").strip()
        if name:
            names.append(name)
        if len(names) >= limit:
            break
    return names


def primary_source_name(work: dict[str, Any]) -> str:
    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    return str(source.get("display_name") or "").strip()


def openalex_url(work: dict[str, Any]) -> str:
    location = work.get("primary_location") or {}
    landing = str(location.get("landing_page_url") or "").strip()
    return landing or str(work.get("id") or "").strip()


def work_to_document(work: dict[str, Any], *, query: str, rank: int) -> CorpusDocument | None:
    title = clean_text(work.get("display_name") or "")
    abstract = abstract_from_inverted_index(work.get("abstract_inverted_index"))
    text = clean_text(" ".join(part for part in [title, abstract] if part))
    if not title or not text:
        return None
    ids = work.get("ids") or {}
    openalex_id = str(work.get("id") or ids.get("openalex") or "").strip()
    short_id = openalex_short_id(openalex_id)
    if not short_id:
        return None
    open_access = work.get("open_access") or {}
    location = work.get("primary_location") or {}
    return CorpusDocument(
        doc_id=f"OPENALEX:{short_id}",
        source="openalex_top_cited",
        title=title,
        text=text,
        metadata={
            "openalex_id": openalex_id,
            "doi": str(work.get("doi") or ids.get("doi") or "").replace("https://doi.org/", ""),
            "pmid": str(ids.get("pmid") or "").replace("https://pubmed.ncbi.nlm.nih.gov/", ""),
            "pmcid": str(ids.get("pmcid") or "").replace("https://pmc.ncbi.nlm.nih.gov/articles/", "").strip("/"),
            "publication_date": work.get("publication_date") or "",
            "publication_year": work.get("publication_year") or "",
            "cited_by_count": int(work.get("cited_by_count") or 0),
            "query": query,
            "query_rank": rank,
            "source_name": primary_source_name(work),
            "url": openalex_url(work),
            "is_oa": bool(open_access.get("is_oa")),
            "oa_status": open_access.get("oa_status") or "",
            "license": location.get("license") or "",
            "authors": first_author_names(work),
        },
    )


def fetch_openalex_documents(
    *,
    query: str,
    from_date: str,
    to_date: str,
    max_records: int,
    per_page: int,
    mailto: str,
) -> list[CorpusDocument]:
    filters = [
        f"from_publication_date:{from_date}",
        f"to_publication_date:{to_date}",
        "type:types/article",
        "is_retracted:false",
    ]
    params = {
        "search": query,
        "filter": ",".join(filters),
        "sort": "cited_by_count:desc",
        "per-page": str(min(max_records, per_page)),
        "select": SELECT_FIELDS,
    }
    if mailto:
        params["mailto"] = mailto
    url = f"{OPENALEX_WORKS_URL}?{urllib.parse.urlencode(params)}"
    payload = read_json_url(url)
    documents: list[CorpusDocument] = []
    for rank, work in enumerate(payload.get("results") or [], start=1):
        document = work_to_document(work, query=query, rank=rank)
        if document is not None:
            documents.append(document)
        if len(documents) >= max_records:
            break
    return documents


def dedupe_documents(documents: Iterable[CorpusDocument]) -> list[CorpusDocument]:
    best_by_key: dict[str, CorpusDocument] = {}
    for document in documents:
        metadata = document.metadata or {}
        key = (
            str(metadata.get("openalex_id") or "").lower()
            or str(metadata.get("doi") or "").lower()
            or normalized_key(document.title)
            or document.doc_id
        )
        current = best_by_key.get(key)
        if current is None or int(metadata.get("cited_by_count") or 0) > int(current.metadata.get("cited_by_count") or 0):
            best_by_key[key] = document
    return sorted(
        best_by_key.values(),
        key=lambda item: (-int(item.metadata.get("cited_by_count") or 0), item.doc_id),
    )


def citation_boost(record: EvidenceRecord) -> float:
    cited_by = int((record.metadata or {}).get("cited_by_count") or 0)
    if cited_by <= 0:
        return 0.0
    return min(1.0, math.log10(cited_by + 1) / 4.0)


def with_citation_weight(records: Iterable[EvidenceRecord]) -> list[EvidenceRecord]:
    weighted: list[EvidenceRecord] = []
    for record in records:
        weighted.append(replace(record, weight=round(record.weight + citation_boost(record), 3)))
    return weighted


def is_generic_match(record: EvidenceRecord) -> bool:
    metadata = record.metadata or {}
    matched_norm = normalized_key(metadata.get("matched_norm") or metadata.get("matched_label") or "")
    return matched_norm in GENERIC_MATCH_NORMS


def load_semantic_types(path: str | Path, cuis: set[str]) -> dict[str, set[str]]:
    if not path or not Path(path).expanduser().exists() or not cuis:
        return {}
    semantic_types: dict[str, set[str]] = {}
    conn = sqlite3.connect(str(Path(path).expanduser()))
    conn.row_factory = sqlite3.Row
    try:
        for cui in sorted(cuis):
            rows = conn.execute(
                "SELECT sty FROM semantic_types WHERE cui = ?",
                (cui,),
            )
            semantic_types[cui] = {str(row["sty"] or "") for row in rows if row["sty"]}
    finally:
        conn.close()
    return semantic_types


def is_low_value_match(record: EvidenceRecord, semantic_types_by_cui: dict[str, set[str]]) -> bool:
    if is_generic_match(record):
        return True
    metadata = record.metadata or {}
    matched_norm = normalized_key(metadata.get("matched_norm") or metadata.get("matched_label") or "")
    if not matched_norm or len(matched_norm) < 4:
        return True
    semantic_types = semantic_types_by_cui.get(record.cui, set())
    if semantic_types and semantic_types.issubset(LOW_VALUE_STYS):
        return True
    if len(matched_norm.split()) == 1 and semantic_types and not semantic_types.intersection(ALLOW_SINGLE_TOKEN_STYS):
        return True
    return False


def filter_low_value_matches(
    records: Iterable[EvidenceRecord],
    semantic_types_by_cui: dict[str, set[str]],
) -> list[EvidenceRecord]:
    return [record for record in records if not is_low_value_match(record, semantic_types_by_cui)]


def label_sort_key(row: sqlite3.Row) -> tuple[int, int, int, str]:
    return (
        0 if row["ispref"] == "Y" else 1,
        TTY_PRIORITY.get(str(row["tty"] or ""), 99),
        0 if row["suppress"] == "N" else 1,
        str(row["label"] or "").lower(),
    )


def collect_labels_from_label_index(
    label_index: str | Path,
    cuis: set[str],
    *,
    max_labels: int = 8,
) -> dict[str, list[str]]:
    labels: dict[str, list[str]] = {}
    conn = sqlite3.connect(str(Path(label_index).expanduser()))
    conn.row_factory = sqlite3.Row
    try:
        for cui in sorted(cuis):
            rows = list(
                conn.execute(
                    """
                    SELECT label, tty, ispref, suppress
                    FROM labels
                    WHERE cui = ?
                    """,
                    (cui,),
                )
            )
            seen: set[str] = set()
            values: list[str] = []
            for row in sorted(rows, key=label_sort_key):
                label = str(row["label"] or "").strip()
                key = label.lower()
                if not label or key in seen:
                    continue
                values.append(label)
                seen.add(key)
                if len(values) >= max_labels:
                    break
            labels[cui] = values
    finally:
        conn.close()
    return labels


def dedupe_top(records: list[EvidenceRecord], max_items: int) -> list[EvidenceRecord]:
    best_by_text: dict[str, EvidenceRecord] = {}
    for record in records:
        key = normalized_key(record.text)
        current = best_by_text.get(key)
        if current is None or record.weight > current.weight:
            best_by_text[key] = record
    return sorted(best_by_text.values(), key=lambda item: (-item.weight, item.text))[:max_items]


def build_documents_with_labels(
    evidence_records: list[EvidenceRecord],
    *,
    label_index: str | Path,
    max_labels: int,
    max_items_per_doc: int,
) -> list[ConceptDocument]:
    labels_by_cui = collect_labels_from_label_index(
        label_index,
        {record.cui for record in evidence_records},
        max_labels=max_labels,
    )
    grouped: dict[tuple[str, str], list[EvidenceRecord]] = defaultdict(list)
    for record in evidence_records:
        grouped[(record.cui, evidence_view(record.evidence_type))].append(record)
    documents: list[ConceptDocument] = []
    for (cui, view), records in sorted(grouped.items()):
        top_records = dedupe_top(records, max_items_per_doc)
        labels = labels_by_cui.get(cui, [])
        documents.append(
            ConceptDocument(
                doc_id=f"{cui}:{view}",
                cui=cui,
                view=view,
                text=document_text(cui, view, labels, top_records),
                evidence_count=len(records),
                sources=sorted({record.source for record in top_records if record.source}),
                labels=labels,
                metadata={
                    "source": "openalex_top_cited",
                    "evidence_window": "last_5_years",
                    "max_items_per_doc": max_items_per_doc,
                    "total_weight": round(sum(record.weight for record in records), 3),
                    "max_cited_by_count": max(
                        int((record.metadata or {}).get("cited_by_count") or 0)
                        for record in records
                    ),
                },
            )
        )
    return documents


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch highly cited recent OpenAlex papers and build a local CUI evidence/vector shard."
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--label-index", type=Path, default=DEFAULT_LABEL_INDEX)
    parser.add_argument("--semantic-type-index", type=Path, default=DEFAULT_SEMANTIC_TYPE_INDEX)
    parser.add_argument("--query", action="append", default=[], help="OpenAlex search query. Repeatable.")
    parser.add_argument(
        "--query-file",
        type=Path,
        action="append",
        default=[],
        help="Plain text or TSV file with a query column. Repeatable; values are appended before --query.",
    )
    parser.add_argument("--from-date", default=default_from_date())
    parser.add_argument("--to-date", default=date.today().isoformat())
    parser.add_argument("--max-per-query", type=int, default=40)
    parser.add_argument("--per-page", type=int, default=50)
    parser.add_argument(
        "--min-cited-by-count",
        type=int,
        default=0,
        help="Drop fetched works below this citation count after query deduplication.",
    )
    parser.add_argument(
        "--exclude-corpus",
        type=Path,
        action="append",
        default=[],
        help="Existing corpus JSONL to exclude by OpenAlex ID, DOI, PMID/PMCID, doc ID, or normalized title.",
    )
    parser.add_argument(
        "--articles-tsv",
        type=Path,
        help="Optional TSV inventory of selected articles after citation and existing-corpus filters.",
    )
    parser.add_argument("--max-label-tokens", type=int, default=8)
    parser.add_argument("--context-chars", type=int, default=360)
    parser.add_argument("--max-ambiguity", type=int, default=1)
    parser.add_argument("--max-mentions-per-cui", type=int, default=6)
    parser.add_argument("--max-labels", type=int, default=8)
    parser.add_argument("--max-items-per-doc", type=int, default=60)
    parser.add_argument("--dim", type=int, default=384)
    parser.add_argument("--mailto", default="", help="Optional email for OpenAlex polite pool.")
    parser.add_argument(
        "--keep-generic-matches",
        action="store_true",
        help="Keep broad single-word matches such as global, estimates, study, treatment, and disease.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    query_file_values: list[str] = []
    for query_file in args.query_file:
        query_file_values.extend(read_query_file(query_file))
    query_values = [*query_file_values, *args.query]
    queries = list(dict.fromkeys(query_values or DEFAULT_QUERIES))
    fetched: list[CorpusDocument] = []
    for query in queries:
        fetched.extend(
            fetch_openalex_documents(
                query=query,
                from_date=args.from_date,
                to_date=args.to_date,
                max_records=args.max_per_query,
                per_page=args.per_page,
                mailto=args.mailto,
            )
        )
    candidate_documents = dedupe_documents(fetched)
    if args.min_cited_by_count > 0:
        citation_filtered_documents = [
            document
            for document in candidate_documents
            if int((document.metadata or {}).get("cited_by_count") or 0) >= args.min_cited_by_count
        ]
    else:
        citation_filtered_documents = candidate_documents
    existing_keys = load_existing_document_keys(args.exclude_corpus)
    corpus_documents, excluded_existing_count = filter_existing_documents(
        citation_filtered_documents,
        existing_keys,
    )
    if args.articles_tsv:
        write_article_report(args.articles_tsv, corpus_documents)

    trie = LabelTrie.from_sqlite(args.label_index, max_label_tokens=args.max_label_tokens)
    evidence_records = with_citation_weight(
        iter_linked_corpus_evidence_trie(
            corpus_documents,
            trie,
            max_label_tokens=args.max_label_tokens,
            context_chars=args.context_chars,
            max_ambiguity=args.max_ambiguity,
            max_mentions_per_cui=args.max_mentions_per_cui,
            evidence_tag="recent_high_citation",
        )
    )
    raw_evidence_count = len(evidence_records)
    if not args.keep_generic_matches:
        semantic_types_by_cui = load_semantic_types(
            args.semantic_type_index,
            {record.cui for record in evidence_records},
        )
        evidence_records = filter_low_value_matches(evidence_records, semantic_types_by_cui)
    concept_documents = build_documents_with_labels(
        evidence_records,
        label_index=args.label_index,
        max_labels=args.max_labels,
        max_items_per_doc=args.max_items_per_doc,
    )
    vectors = embed_documents(
        concept_documents,
        HashingEmbedder(dim=args.dim),
        include_document_metadata=True,
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = args.out_dir / "evidence"
    corpus_path = args.out_dir / "openalex_top_cited_corpus.jsonl"
    evidence_path = evidence_dir / "openalex_top_cited_evidence.jsonl"
    docs_path = args.out_dir / "openalex_top_cited_concept_documents.jsonl"
    vectors_path = args.out_dir / "openalex_top_cited_concept_vectors.hashing.jsonl"
    manifest_path = args.out_dir / "manifest.json"
    corpus_count = write_jsonl(corpus_path, corpus_documents)
    evidence_count = write_jsonl(evidence_path, evidence_records)
    doc_count = write_jsonl(docs_path, concept_documents)
    vector_count = write_jsonl(vectors_path, vectors)
    cited_counts = [int(document.metadata.get("cited_by_count") or 0) for document in corpus_documents]
    manifest = {
        "source": "openalex_top_cited",
        "date_window": {"from": args.from_date, "to": args.to_date},
        "queries": queries,
        "query_files": [str(path) for path in args.query_file],
        "label_index": str(args.label_index),
        "semantic_type_index": str(args.semantic_type_index),
        "exclude_corpora": [str(path) for path in args.exclude_corpus],
        "existing_document_identity_keys": len(existing_keys),
        "candidate_documents": len(candidate_documents),
        "min_cited_by_count": args.min_cited_by_count,
        "below_min_cited_by_count_removed": len(candidate_documents) - len(citation_filtered_documents),
        "existing_documents_removed": excluded_existing_count,
        "corpus": str(corpus_path),
        "evidence": str(evidence_path),
        "documents": str(docs_path),
        "vectors": str(vectors_path),
        "articles_tsv": str(args.articles_tsv) if args.articles_tsv else "",
        "corpus_documents": corpus_count,
        "raw_evidence_records": raw_evidence_count,
        "low_value_evidence_records_removed": raw_evidence_count - evidence_count,
        "evidence_records": evidence_count,
        "concept_documents": doc_count,
        "vectors_count": vector_count,
        "max_cited_by_count": max(cited_counts) if cited_counts else 0,
        "min_cited_by_count": min(cited_counts) if cited_counts else 0,
        "vector_dim": args.dim,
        "embedding_provider": "hashing",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"Wrote {corpus_count:,} OpenAlex paper(s), {evidence_count:,} evidence record(s), "
        f"{doc_count:,} concept document(s), and {vector_count:,} vector(s) to {args.out_dir}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
