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
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
MEDMENTIONS_BASE_URL = "https://raw.githubusercontent.com/chanzuckerberg/MedMentions/master"
CORPUS_URLS = {
    "full": f"{MEDMENTIONS_BASE_URL}/full/data/corpus_pubtator.txt.gz",
    "st21pv": f"{MEDMENTIONS_BASE_URL}/st21pv/data/corpus_pubtator.txt.gz",
}
SPLIT_URLS = {
    "trng": f"{MEDMENTIONS_BASE_URL}/full/data/corpus_pubtator_pmids_trng.txt",
    "dev": f"{MEDMENTIONS_BASE_URL}/full/data/corpus_pubtator_pmids_dev.txt",
    "test": f"{MEDMENTIONS_BASE_URL}/full/data/corpus_pubtator_pmids_test.txt",
}
CUI_RE = re.compile(r"\bC\d{7}\b", re.IGNORECASE)
SENTENCE_BOUNDARY_RE = re.compile(r"[.!?](?:\s+|$)")
QUERY_FIELDS = [
    "id",
    "query",
    "expected_cuis",
    "why",
    "disallowed_cuis",
    "benchmark_type",
    "subset",
    "split",
    "pmid",
    "mention_index",
    "mention_text",
    "start",
    "end",
    "semantic_types",
    "medmentions_category",
]
RESULT_FIELDS = [
    "id",
    "benchmark_type",
    "subset",
    "split",
    "pmid",
    "medmentions_category",
    "expected_cuis",
    "expected_count",
    "found_at_1",
    "found_at_3",
    "found_at_5",
    "found_at_10",
    "found_at_k",
    "recall_at_10",
    "recall_at_k",
    "first_expected_rank",
    "reciprocal_first_expected_rank",
    "top_cui",
    "top_name",
    "linked_expected_found",
    "hit_cuis",
    "linked_cuis",
    "elapsed_ms",
    "server_elapsed_ms",
    "backend",
    "query",
]
CLINICAL_USEFUL_TUIS = {
    "T005",  # Virus
    "T007",  # Bacterium
    "T017",  # Anatomical Structure
    "T022",  # Body System
    "T023",  # Body Part, Organ, or Organ Component
    "T024",  # Tissue
    "T025",  # Cell
    "T026",  # Cell Component
    "T028",  # Gene or Genome
    "T029",  # Body Location or Region
    "T030",  # Body Space or Junction
    "T031",  # Body Substance
    "T033",  # Finding
    "T034",  # Laboratory or Test Result
    "T037",  # Injury or Poisoning
    "T046",  # Pathologic Function
    "T047",  # Disease or Syndrome
    "T048",  # Mental or Behavioral Dysfunction
    "T049",  # Cell or Molecular Dysfunction
    "T050",  # Experimental Model of Disease
    "T059",  # Laboratory Procedure
    "T060",  # Diagnostic Procedure
    "T061",  # Therapeutic or Preventive Procedure
    "T074",  # Medical Device
    "T085",  # Molecular Sequence
    "T086",  # Nucleotide Sequence
    "T087",  # Amino Acid Sequence
    "T103",  # Chemical
    "T104",  # Chemical Viewed Structurally
    "T109",  # Organic Chemical
    "T114",  # Nucleic Acid, Nucleoside, or Nucleotide
    "T116",  # Amino Acid, Peptide, or Protein
    "T121",  # Pharmacologic Substance
    "T122",  # Biomedical or Dental Material
    "T123",  # Biologically Active Substance
    "T125",  # Hormone
    "T126",  # Enzyme
    "T127",  # Vitamin
    "T129",  # Immunologic Factor
    "T130",  # Indicator, Reagent, or Diagnostic Aid
    "T131",  # Hazardous or Poisonous Substance
    "T167",  # Substance
    "T184",  # Sign or Symptom
    "T190",  # Anatomical Abnormality
    "T191",  # Neoplastic Process
    "T192",  # Receptor
    "T194",  # Archaeon
    "T195",  # Antibiotic
    "T196",  # Element, Ion, or Isotope
    "T197",  # Inorganic Chemical
    "T200",  # Clinical Drug
    "T201",  # Clinical Attribute
    "T203",  # Drug Delivery Device
}
BROAD_BIOMEDICAL_TUIS = {
    "T038",  # Biologic Function
    "T039",  # Physiologic Function
    "T040",  # Organism Function
    "T041",  # Mental Process
    "T042",  # Organ or Tissue Function
    "T043",  # Cell Function
    "T044",  # Molecular Function
    "T045",  # Genetic Function
    "T063",  # Molecular Biology Research Technique
    "T067",  # Phenomenon or Process
    "T070",  # Natural Phenomenon or Process
    "T168",  # Food
    "T204",  # Eukaryote
}
SUPPRESSION_AUDIT_TUIS = {
    "T051",  # Event
    "T052",  # Activity
    "T053",  # Behavior
    "T054",  # Social Behavior
    "T055",  # Individual Behavior
    "T056",  # Daily or Recreational Activity
    "T057",  # Occupational Activity
    "T058",  # Health Care Activity
    "T062",  # Research Activity
    "T064",  # Governmental or Regulatory Activity
    "T065",  # Educational Activity
    "T071",  # Entity
    "T072",  # Physical Object
    "T073",  # Manufactured Object
    "T077",  # Conceptual Entity
    "T078",  # Idea or Concept
    "T079",  # Temporal Concept
    "T080",  # Qualitative Concept
    "T081",  # Quantitative Concept
    "T082",  # Spatial Concept
    "T083",  # Geographic Area
    "T089",  # Regulation or Law
    "T090",  # Occupation or Discipline
    "T091",  # Biomedical Occupation or Discipline
    "T092",  # Organization
    "T093",  # Health Care Related Organization
    "T094",  # Professional Society
    "T095",  # Self-help or Relief Organization
    "T096",  # Group
    "T097",  # Professional or Occupational Group
    "T098",  # Population Group
    "T099",  # Family Group
    "T100",  # Age Group
    "T101",  # Patient or Disabled Group
    "T102",  # Group Attribute
    "T169",  # Functional Concept
    "T170",  # Intellectual Product
    "T171",  # Language
    "T185",  # Classification
}
MEDMENTIONS_CATEGORIES = ("clinical_useful", "biomedical_broad", "suppression_audit")
MENTION_QUERY_STYLES = ("mention_context", "mention_only", "anchored_context")


@dataclass(frozen=True)
class Mention:
    pmid: str
    start: int
    end: int
    text: str
    semantic_types: str
    cuis: tuple[str, ...]


@dataclass(frozen=True)
class Document:
    pmid: str
    title: str
    abstract: str
    mentions: tuple[Mention, ...]

    @property
    def text(self) -> str:
        return " ".join(part for part in (self.title, self.abstract) if part).strip()

    @property
    def unique_cuis(self) -> tuple[str, ...]:
        cuis: set[str] = set()
        for mention in self.mentions:
            cuis.update(mention.cuis)
        return tuple(sorted(cuis))


def split_cuis(value: object) -> tuple[str, ...]:
    return tuple(sorted({match.group(0).upper() for match in CUI_RE.finditer(str(value or ""))}))


def split_tuis(value: object) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                part.strip().upper()
                for part in str(value or "").replace("|", ",").replace(";", ",").split(",")
                if re.fullmatch(r"T\d{3}", part.strip(), flags=re.IGNORECASE)
            }
        )
    )


def medmentions_category_for_tuis(value: object) -> str:
    tuis = set(split_tuis(value))
    if tuis & CLINICAL_USEFUL_TUIS:
        return "clinical_useful"
    if tuis & BROAD_BIOMEDICAL_TUIS:
        return "biomedical_broad"
    return "suppression_audit"


def category_matches(category: str, selected_categories: set[str]) -> bool:
    if not selected_categories:
        return True
    return category in selected_categories


def category_label(selected_categories: set[str]) -> str:
    if not selected_categories:
        return "all"
    return "_".join(sorted(selected_categories))


def download_file(url: str, path: Path, *, force: bool = False) -> bool:
    if path.exists() and path.stat().st_size > 0 and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/octet-stream,text/plain",
            "User-Agent": "query-expansion-medmentions-benchmark/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        path.write_bytes(response.read())
    return True


def default_corpus_path(data_dir: Path, subset: str) -> Path:
    return data_dir / subset / "corpus_pubtator.txt.gz"


def default_split_path(data_dir: Path, split: str) -> Path:
    return data_dir / "splits" / f"corpus_pubtator_pmids_{split}.txt"


def ensure_medmentions_files(data_dir: Path, *, subset: str, force: bool = False) -> dict[str, str]:
    if subset not in CORPUS_URLS:
        raise ValueError(f"unknown MedMentions subset: {subset}")
    corpus_path = default_corpus_path(data_dir, subset)
    downloaded = {
        str(corpus_path): download_file(CORPUS_URLS[subset], corpus_path, force=force)
    }
    for split, url in SPLIT_URLS.items():
        split_path = default_split_path(data_dir, split)
        downloaded[str(split_path)] = download_file(url, split_path, force=force)
    return {path: "downloaded" if did_download else "cached" for path, did_download in downloaded.items()}


def open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return path.open("r", encoding="utf-8", errors="replace")


def parse_pubtator(path: Path) -> list[Document]:
    documents: list[Document] = []
    with open_text(path) as handle:
        block: list[str] = []
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            if not line.strip():
                if block:
                    document = parse_pubtator_block(block)
                    if document:
                        documents.append(document)
                    block = []
                continue
            block.append(line)
        if block:
            document = parse_pubtator_block(block)
            if document:
                documents.append(document)
    return documents


def parse_pubtator_block(lines: list[str]) -> Document | None:
    pmid = ""
    title = ""
    abstract = ""
    mentions: list[Mention] = []
    for line in lines:
        if "|t|" in line:
            left, title_text = line.split("|t|", 1)
            pmid = left.strip()
            title = title_text.strip()
            continue
        if "|a|" in line:
            left, abstract_text = line.split("|a|", 1)
            pmid = pmid or left.strip()
            abstract = abstract_text.strip()
            continue
        fields = line.split("\t")
        if len(fields) < 6:
            continue
        row_pmid, start, end, mention_text, semantic_types, entity_id = fields[:6]
        cuis = split_cuis(entity_id)
        if not cuis:
            continue
        try:
            mention_start = int(start)
            mention_end = int(end)
        except ValueError:
            continue
        mentions.append(
            Mention(
                pmid=row_pmid.strip(),
                start=mention_start,
                end=mention_end,
                text=mention_text.strip(),
                semantic_types=semantic_types.strip(),
                cuis=cuis,
            )
        )
        pmid = pmid or row_pmid.strip()
    if not pmid or not (title or abstract):
        return None
    return Document(pmid=pmid, title=title, abstract=abstract, mentions=tuple(mentions))


def read_split_pmids(data_dir: Path) -> dict[str, str]:
    pmid_to_split: dict[str, str] = {}
    for split in ("trng", "dev", "test"):
        path = default_split_path(data_dir, split)
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                pmid = line.strip()
                if pmid:
                    pmid_to_split[pmid] = split
    return pmid_to_split


def sentence_context(text: str, start: int, end: int, *, chars: int) -> str:
    text = str(text or "")
    start = max(0, min(int(start or 0), len(text)))
    end = max(start, min(int(end or start), len(text)))
    left = max(0, start - max(0, chars))
    right = min(len(text), end + max(0, chars))
    while left > 0 and text[left - 1] not in ".!?\n\r":
        left -= 1
    while right < len(text) and text[right - 1] not in ".!?\n\r":
        right += 1
    return re.sub(r"\s+", " ", text[left:right]).strip()


def split_filter_matches(split: str, selected_splits: set[str]) -> bool:
    if not selected_splits:
        return True
    return split in selected_splits


def limited_rows(rows: Iterable[dict[str, str]], *, limit: int) -> list[dict[str, str]]:
    output = list(rows)
    if limit <= 0:
        return output
    return output[:limit]


def mention_query_rows(
    documents: list[Document],
    *,
    subset: str,
    pmid_to_split: dict[str, str],
    selected_splits: set[str],
    selected_categories: set[str],
    context_chars: int,
    query_style: str = "mention_context",
    limit: int = 0,
) -> list[dict[str, str]]:
    if query_style not in MENTION_QUERY_STYLES:
        raise ValueError(f"unknown MedMentions mention query style: {query_style}")
    rows: list[dict[str, str]] = []
    for document in documents:
        split = pmid_to_split.get(document.pmid, "unknown")
        if not split_filter_matches(split, selected_splits):
            continue
        doc_text = document.text
        for index, mention in enumerate(document.mentions, start=1):
            category = medmentions_category_for_tuis(mention.semantic_types)
            if not category_matches(category, selected_categories):
                continue
            context = sentence_context(doc_text, mention.start, mention.end, chars=context_chars)
            query = mention_query_text(
                mention.text,
                context=context,
                query_style=query_style,
            )
            rows.append(
                {
                    "id": f"medmentions_{subset}_{split}_{document.pmid}_m{index:04d}",
                    "query": query,
                    "expected_cuis": "|".join(mention.cuis),
                    "why": (
                        "MedMentions PubTator mention linked this span to "
                        f"{'|'.join(mention.cuis)} in PMID {document.pmid}."
                    ),
                    "disallowed_cuis": "",
                    "benchmark_type": query_style,
                    "subset": subset,
                    "split": split,
                    "pmid": document.pmid,
                    "mention_index": str(index),
                    "mention_text": mention.text,
                    "start": str(mention.start),
                    "end": str(mention.end),
                    "semantic_types": mention.semantic_types,
                    "medmentions_category": category,
                }
            )
    return limited_rows(rows, limit=limit)


def mention_query_text(mention_text: str, *, context: str, query_style: str) -> str:
    mention = str(mention_text or "").strip()
    context = str(context or "").strip()
    if query_style == "mention_only":
        return mention
    if query_style == "anchored_context":
        return f"Mention: {mention}. Context: {context}" if context else f"Mention: {mention}"
    if query_style == "mention_context":
        return f"{mention}. Context: {context}" if context else mention
    raise ValueError(f"unknown MedMentions mention query style: {query_style}")


def document_query_rows(
    documents: list[Document],
    *,
    subset: str,
    pmid_to_split: dict[str, str],
    selected_splits: set[str],
    selected_categories: set[str],
    limit: int = 0,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    category_name = category_label(selected_categories)
    for document in documents:
        expected_cuis = tuple(
            sorted(
                {
                    cui
                    for mention in document.mentions
                    if category_matches(
                        medmentions_category_for_tuis(mention.semantic_types),
                        selected_categories,
                    )
                    for cui in mention.cuis
                }
            )
        )
        if not expected_cuis:
            continue
        split = pmid_to_split.get(document.pmid, "unknown")
        if not split_filter_matches(split, selected_splits):
            continue
        id_suffix = "document" if category_name == "all" else f"{category_name}_document"
        rows.append(
            {
                "id": f"medmentions_{subset}_{split}_{document.pmid}_{id_suffix}",
                "query": f"PubMed PMID {document.pmid}. {document.text}",
                "expected_cuis": "|".join(expected_cuis),
                "why": (
                    "MedMentions document-level CUI set from annotated title/abstract "
                    f"mentions in PMID {document.pmid}; category={category_name}."
                ),
                "disallowed_cuis": "",
                "benchmark_type": "document_cui_recall",
                "subset": subset,
                "split": split,
                "pmid": document.pmid,
                "mention_index": "",
                "mention_text": "",
                "start": "",
                "end": "",
                "semantic_types": "",
                "medmentions_category": category_name,
            }
        )
    return limited_rows(rows, limit=limit)


def write_tsv(path: Path, rows: list[dict[str, str]], *, fields: list[str] = QUERY_FIELDS) -> None:
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
                query = (row.get("query") or "").strip()
                expected = split_cuis(row.get("expected_cuis") or "")
                if not query or not expected:
                    continue
                rows.append(
                    {
                        **{key: str(value or "") for key, value in row.items()},
                        "id": (row.get("id") or f"{path.stem}_{index}").strip(),
                        "query": query,
                        "expected_cuis": "|".join(expected),
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
    linked: bool,
    timeout: float,
) -> tuple[dict, float]:
    params = urllib.parse.urlencode(
        {
            "q": query,
            "k": top_k,
            "mode": mode,
            "scope": scope,
            "related": "1" if related else "0",
            "linked": "1" if linked else "0",
            "evidence_items": "0",
            "codes": "default",
        }
    )
    url = f"{base_url.rstrip('/')}/api/search?{params}"
    started = time.time()
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = json.load(response)
    return payload, time.time() - started


def cuis_from_items(items: Iterable[dict]) -> list[str]:
    cuis = []
    for item in items:
        cui = str(item.get("cui") or "").strip().upper()
        if cui and cui not in cuis:
            cuis.append(cui)
    return cuis


def first_expected_rank(cuis: list[str], expected: set[str]) -> int:
    for index, cui in enumerate(cuis, start=1):
        if cui in expected:
            return index
    return 0


def score_payload(row: dict[str, str], payload: dict, *, elapsed_seconds: float, top_k: int) -> dict[str, str]:
    expected = set(split_cuis(row.get("expected_cuis") or ""))
    hits = list(payload.get("hits") or [])
    linked = list(payload.get("linked_concepts") or [])
    hit_cuis = cuis_from_items(hits)
    linked_cuis = cuis_from_items(linked)
    first_rank = first_expected_rank(hit_cuis, expected)
    expected_count = len(expected)

    def found_count(limit: int) -> int:
        return len(expected & set(hit_cuis[:limit]))

    found_at_10 = found_count(min(10, top_k))
    found_at_k = found_count(top_k)
    top = hits[0] if hits else {}
    return {
        "id": row.get("id", ""),
        "benchmark_type": row.get("benchmark_type", ""),
        "subset": row.get("subset", ""),
        "split": row.get("split", ""),
        "pmid": row.get("pmid", ""),
        "medmentions_category": row.get("medmentions_category", ""),
        "expected_cuis": "|".join(sorted(expected)),
        "expected_count": str(expected_count),
        "found_at_1": str(found_count(1)),
        "found_at_3": str(found_count(min(3, top_k))),
        "found_at_5": str(found_count(min(5, top_k))),
        "found_at_10": str(found_at_10),
        "found_at_k": str(found_at_k),
        "recall_at_10": f"{found_at_10 / expected_count:.6f}" if expected_count else "0.000000",
        "recall_at_k": f"{found_at_k / expected_count:.6f}" if expected_count else "0.000000",
        "first_expected_rank": str(first_rank),
        "reciprocal_first_expected_rank": f"{1 / first_rank:.6f}" if first_rank else "0.000000",
        "top_cui": str(top.get("cui") or ""),
        "top_name": str(top.get("name") or top.get("label") or ""),
        "linked_expected_found": "1" if expected & set(linked_cuis) else "0",
        "hit_cuis": "|".join(hit_cuis),
        "linked_cuis": "|".join(linked_cuis),
        "elapsed_ms": f"{elapsed_seconds * 1000:.1f}",
        "server_elapsed_ms": str(payload.get("elapsed_ms") or ""),
        "backend": str(payload.get("backend") or ""),
        "query": row.get("query", ""),
    }


def float_field(row: dict[str, str], field: str) -> float:
    try:
        return float(row.get(field) or 0.0)
    except ValueError:
        return 0.0


def summarize_results(
    rows: list[dict[str, str]],
    *,
    top_k: int,
    include_by_type: bool = True,
) -> dict[str, object]:
    if not rows:
        return {
            "queries": 0,
            "top_k": top_k,
            "top1_accuracy": 0.0,
            "top3_accuracy": 0.0,
            "top5_accuracy": 0.0,
            "top10_accuracy": 0.0,
            "topk_accuracy": 0.0,
            "mean_recall_at_10": 0.0,
            "mean_recall_at_k": 0.0,
            "mrr": 0.0,
            "linked_expected_rate": 0.0,
            "mean_elapsed_ms": 0.0,
        }

    def rate(field: str) -> float:
        return round(sum(1 for row in rows if int(row.get(field) or 0) > 0) / len(rows), 6)

    summary = {
        "queries": len(rows),
        "top_k": top_k,
        "top1_accuracy": rate("found_at_1"),
        "top3_accuracy": rate("found_at_3"),
        "top5_accuracy": rate("found_at_5"),
        "top10_accuracy": rate("found_at_10"),
        "topk_accuracy": rate("found_at_k"),
        "mean_recall_at_10": round(sum(float_field(row, "recall_at_10") for row in rows) / len(rows), 6),
        "mean_recall_at_k": round(sum(float_field(row, "recall_at_k") for row in rows) / len(rows), 6),
        "mrr": round(
            sum(float_field(row, "reciprocal_first_expected_rank") for row in rows) / len(rows),
            6,
        ),
        "linked_expected_rate": rate("linked_expected_found"),
        "mean_elapsed_ms": round(sum(float_field(row, "elapsed_ms") for row in rows) / len(rows), 1),
    }
    if include_by_type:
        by_type: dict[str, dict[str, object]] = {}
        for benchmark_type in sorted({row.get("benchmark_type") or "unknown" for row in rows}):
            type_rows = [
                row for row in rows if (row.get("benchmark_type") or "unknown") == benchmark_type
            ]
            by_type[benchmark_type] = summarize_results(
                type_rows,
                top_k=top_k,
                include_by_type=False,
            )
        summary["by_benchmark_type"] = by_type
        by_category: dict[str, dict[str, object]] = {}
        for category in sorted({row.get("medmentions_category") or "unknown" for row in rows}):
            category_rows = [
                row for row in rows if (row.get("medmentions_category") or "unknown") == category
            ]
            by_category[category] = summarize_results(
                category_rows,
                top_k=top_k,
                include_by_type=False,
            )
        summary["by_medmentions_category"] = by_category
        clinical_summary = by_category.get("clinical_useful")
        if clinical_summary:
            summary["clinical_useful_target"] = {
                "top1_hit_rate": clinical_summary["top1_accuracy"],
                "top10_hit_rate": clinical_summary["top10_accuracy"],
                "mrr": clinical_summary["mrr"],
            }
        suppression_summary = by_category.get("suppression_audit")
        if suppression_summary:
            summary["suppression_audit_guardrail"] = {
                "top1_surfacing_rate": suppression_summary["top1_accuracy"],
                "top10_surfacing_rate": suppression_summary["top10_accuracy"],
                "interpretation": "Lower is safer for default clinical search; do not optimize this as recall.",
            }
    return summary


def prepare(args: argparse.Namespace) -> int:
    data_dir = args.data_dir
    downloaded = ensure_medmentions_files(data_dir, subset=args.subset, force=args.force_download)
    corpus_path = args.corpus or default_corpus_path(data_dir, args.subset)
    documents = parse_pubtator(corpus_path)
    pmid_to_split = read_split_pmids(data_dir)
    selected_splits = {split.strip() for split in args.split if split.strip()}
    selected_categories = {category.strip() for category in args.category if category.strip()}
    mention_rows = mention_query_rows(
        documents,
        subset=args.subset,
        pmid_to_split=pmid_to_split,
        selected_splits=selected_splits,
        selected_categories=selected_categories,
        context_chars=args.context_chars,
        query_style=args.query_style,
        limit=args.mention_limit,
    )
    document_rows = document_query_rows(
        documents,
        subset=args.subset,
        pmid_to_split=pmid_to_split,
        selected_splits=selected_splits,
        selected_categories=selected_categories,
        limit=args.document_limit,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    category_name = category_label(selected_categories)
    name_parts = ["medmentions", args.subset]
    if category_name != "all":
        name_parts.append(category_name)
    if args.query_style != "mention_context":
        name_parts.append(args.query_style)
    output_prefix = "_".join(name_parts)
    mention_path = args.output_dir / f"{output_prefix}_mention_queries.tsv"
    document_path = args.output_dir / f"{output_prefix}_document_queries.tsv"
    combined_path = args.output_dir / f"{output_prefix}_combined_queries.tsv"
    write_tsv(mention_path, mention_rows)
    write_tsv(document_path, document_rows)
    write_tsv(combined_path, [*mention_rows, *document_rows])
    for split in sorted({row["split"] for row in [*mention_rows, *document_rows] if row.get("split")}):
        split_rows = [row for row in mention_rows if row.get("split") == split]
        write_tsv(args.output_dir / f"{output_prefix}_{split}_mention_queries.tsv", split_rows)
        split_docs = [row for row in document_rows if row.get("split") == split]
        write_tsv(args.output_dir / f"{output_prefix}_{split}_document_queries.tsv", split_docs)
    category_counts = {
        category: sum(1 for row in mention_rows if row.get("medmentions_category") == category)
        for category in MEDMENTIONS_CATEGORIES
    }
    manifest = {
        "subset": args.subset,
        "categories": sorted(selected_categories) if selected_categories else ["all"],
        "corpus_path": str(corpus_path),
        "documents": len(documents),
        "mentions": sum(len(document.mentions) for document in documents),
        "unique_cuis": len({cui for document in documents for cui in document.unique_cuis}),
        "selected_splits": sorted(selected_splits) if selected_splits else ["all"],
        "mention_query_rows": len(mention_rows),
        "document_query_rows": len(document_rows),
        "mention_query_rows_by_category": category_counts,
        "context_chars": args.context_chars,
        "mention_query_style": args.query_style,
        "downloads": downloaded,
        "outputs": {
            "mention_queries": str(mention_path),
            "document_queries": str(document_path),
            "combined_queries": str(combined_path),
        },
    }
    manifest_path = args.output_dir / "medmentions_manifest.json"
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
                linked=args.linked,
                timeout=args.timeout,
            )
            if payload_handle:
                payload_handle.write(
                    json.dumps(
                        {
                            "id": row.get("id"),
                            "query": row.get("query"),
                            "expected_cuis": row.get("expected_cuis"),
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
        description="Prepare and run MedMentions UMLS linking benchmarks."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare", help="Download and convert MedMentions.")
    prepare_parser.add_argument("--subset", choices=sorted(CORPUS_URLS), default="st21pv")
    prepare_parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "medmentions")
    prepare_parser.add_argument("--corpus", type=Path, help="Use an existing PubTator corpus file.")
    prepare_parser.add_argument("--output-dir", type=Path, default=ROOT / "build" / "medmentions" / "st21pv")
    prepare_parser.add_argument(
        "--split",
        action="append",
        default=[],
        choices=["trng", "dev", "test", "unknown"],
        help="Limit output to one split. Repeat for multiple splits. Defaults to all splits.",
    )
    prepare_parser.add_argument(
        "--category",
        action="append",
        default=[],
        choices=list(MEDMENTIONS_CATEGORIES),
        help=(
            "Limit output to a MedMentions semantic-type category. Repeat for multiple "
            "categories. clinical_useful is the product-improvement target; "
            "suppression_audit is for concepts that should usually stay low-ranked."
        ),
    )
    prepare_parser.add_argument("--context-chars", type=int, default=180)
    prepare_parser.add_argument(
        "--query-style",
        choices=list(MENTION_QUERY_STYLES),
        default="mention_context",
        help=(
            "How to build mention-level queries. mention_context is the original broad "
            "retrieval probe; mention_only isolates linker quality; anchored_context keeps "
            "nearby text but marks the span being evaluated."
        ),
    )
    prepare_parser.add_argument("--mention-limit", type=int, default=0)
    prepare_parser.add_argument("--document-limit", type=int, default=0)
    prepare_parser.add_argument("--force-download", action="store_true")
    prepare_parser.set_defaults(func=prepare)

    eval_parser = subparsers.add_parser("evaluate", help="Score prepared query TSVs against /api/search.")
    eval_parser.add_argument("queries", type=Path, nargs="+")
    eval_parser.add_argument("--base-url", default="http://127.0.0.1:8766")
    eval_parser.add_argument("--top-k", type=int, default=10)
    eval_parser.add_argument("--mode", choices=["balanced", "exact", "comprehensive"], default="balanced")
    eval_parser.add_argument("--scope", choices=["umls", "umls_evidence"], default="umls_evidence")
    eval_parser.add_argument("--related", action="store_true")
    eval_parser.add_argument("--linked", action="store_true")
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
