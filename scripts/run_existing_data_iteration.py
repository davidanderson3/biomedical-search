#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qe_evidence_vectors.extension_concepts import (  # noqa: E402
    build_extension_concept_artifacts,
    iter_extension_concepts,
    stable_extension_id,
)
from qe_evidence_vectors.schema import write_jsonl  # noqa: E402
from qe_evidence_vectors.text import clean_text, normalized_key  # noqa: E402
from scripts.generate_typical_sentences import TOPIC_FIELDS, TOPIC_ROWS  # noqa: E402


DEFAULT_DOC_PATHS = [
    "build/scaling_chunk_001_gap_topics_concept_documents.jsonl",
    "build/scaling_chunk_002_common_clinical_concept_documents.jsonl",
    "build/scaling_chunk_003_abbreviation_language_concept_documents.jsonl",
    "build/scaling_chunk_004_drug_safety_therapeutics_concept_documents.jsonl",
    "build/scaling_chunk_005_diagnostics_procedures_devices_concept_documents.jsonl",
    "build/pubmed_bulk_recent_1321_1320_concept_documents.jsonl",
]

PROMOTABLE_FIELDS = {
    "condition",
    "symptom",
    "finding",
    "test",
    "result",
    "procedure",
    "complication",
}

COMBINATION_RE = re.compile(r"\b(?:and|or|with)\b", re.IGNORECASE)
GENERIC_RE = re.compile(
    r"\b(?:"
    r"follow up|referral|monitoring|evaluation|assessment|counseling|"
    r"history|education|control|questionnaire|diary|technique|operative fixation"
    r")\b",
    re.IGNORECASE,
)
RISK_RE = re.compile(r"\brisk\b", re.IGNORECASE)
SEVERITY_ONLY_RE = re.compile(r"^(?:mild|moderate|severe)\b", re.IGNORECASE)
NORMAL_OR_ABSENT_RE = re.compile(
    r"^(?:normal|no acute|negative|unremarkable|without)\b",
    re.IGNORECASE,
)
NEGATION_PREFIX_RE = re.compile(
    r"(?:"
    r"\bno\b|\bnot\b|\bwithout\b|\bnegative for\b|\babsence of\b|"
    r"\bfree of\b|\brule out\b|\bruled out\b|\bdenies\b|\bdenied\b"
    r")(?:\W+\w+){0,8}\W*$",
    re.IGNORECASE,
)

BROADER_ANCHOR_TERMS = {
    "bibasilar crackles": ["crackles"],
    "recurrent ischemia": ["ischemia"],
    "right heart strain": ["right ventricular dysfunction"],
    "poorly controlled type 2 diabetes mellitus": ["type 2 diabetes"],
    "persistent neurologic deficit": ["neurologic deficit"],
    "epileptiform discharges": ["abnormal electroencephalogram"],
    "joint erosion": ["bone erosion"],
    "acute deep vein thrombosis": ["deep vein thrombosis"],
    "diabetic foot osteomyelitis": ["osteomyelitis", "diabetic foot"],
    "silvery scale": ["scaly skin"],
}

CLOSE_MATCH_ANCHOR_TERMS = {
    "suppressed TSH": ["low thyroid stimulating hormone"],
    "inability to bear weight": ["weight bearing difficulty"],
}

SEMANTIC_COVERAGE_ANCHOR_TERMS = {
    "acute gout flare": ["gout flare"],
    "insulin dose adjustment": ["dose adjustment"],
    "localized abdominal tenderness": ["abdominal tenderness"],
    "rising creatinine": ["creatinine increased"],
    "substernal chest pressure": ["chest pressure"],
}

LOINC_NAME_FIELDS = (
    "DisplayName",
    "LONG_COMMON_NAME",
    "SHORTNAME",
    "CONSUMER_NAME",
    "COMPONENT",
)

EXTENSION_RELATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS related_concepts (
    source_cui TEXT NOT NULL,
    target_cui TEXT NOT NULL,
    relation TEXT NOT NULL,
    rela TEXT NOT NULL,
    sab TEXT NOT NULL,
    direction TEXT NOT NULL,
    label TEXT NOT NULL,
    rank INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_related_source_rank
ON related_concepts(source_cui, rank);
"""


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def existing_paths(paths: Iterable[str | Path]) -> list[Path]:
    output = []
    for path in paths:
        candidate = (ROOT / path).resolve() if not Path(path).is_absolute() else Path(path)
        if candidate.exists():
            output.append(candidate)
    return output


def connect_label_index(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def connect_sqlite(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def label_matches(conn: sqlite3.Connection, term: str, *, limit: int = 5) -> list[dict[str, str]]:
    rows = conn.execute(
        """
        SELECT cui, label, sab, tty
        FROM labels
        WHERE norm = ?
        LIMIT ?
        """,
        (normalized_key(term), limit),
    ).fetchall()
    return [
        {
            "cui": str(row["cui"]),
            "label": str(row["label"]),
            "sab": str(row["sab"]),
            "tty": str(row["tty"]),
        }
        for row in rows
    ]


def best_match(matches: list[dict[str, str]]) -> dict[str, str] | None:
    if not matches:
        return None
    sab_priority = {
        "MTH": 0,
        "MSH": 1,
        "SNOMEDCT_US": 2,
        "NCI": 3,
        "MEDLINEPLUS": 4,
        "MDR": 5,
    }
    tty_priority = {
        "PT": 0,
        "PN": 1,
        "MH": 2,
        "PM": 3,
        "ET": 4,
        "SY": 5,
        "LLT": 6,
    }
    return sorted(
        matches,
        key=lambda row: (
            sab_priority.get(str(row.get("sab") or ""), 99),
            tty_priority.get(str(row.get("tty") or ""), 99),
            str(row.get("label") or "").lower(),
        ),
    )[0]


def code_label_matches(conn: sqlite3.Connection | None, term: str, *, limit: int = 5) -> list[dict[str, str]]:
    if conn is None:
        return []
    rows = conn.execute(
        """
        SELECT cui, label, sab, tty
        FROM preferred_terms
        WHERE lower(label) = lower(?)
        UNION
        SELECT cui, label, sab, tty
        FROM code_mappings
        WHERE lower(label) = lower(?)
        LIMIT ?
        """,
        (term, term, limit),
    ).fetchall()
    return [
        {
            "cui": str(row["cui"]),
            "label": str(row["label"]),
            "sab": str(row["sab"]),
            "tty": str(row["tty"]),
        }
        for row in rows
    ]


def load_code_label_lookup(
    conn: sqlite3.Connection | None,
    terms: Iterable[str],
    *,
    limit: int = 5,
) -> dict[str, list[dict[str, str]]]:
    wanted = {normalized_key(term): term for term in terms}
    lookup: dict[str, list[dict[str, str]]] = {term: [] for term in wanted.values()}
    if conn is None or not wanted:
        return lookup
    seen: set[tuple[str, str, str, str]] = set()
    for table in ("preferred_terms", "code_mappings"):
        for row in conn.execute(f"SELECT cui, label, sab, tty FROM {table}"):
            term = wanted.get(normalized_key(str(row["label"] or "")))
            if not term:
                continue
            key = (str(row["cui"]), str(row["label"]), str(row["sab"]), str(row["tty"]))
            if key in seen or len(lookup[term]) >= limit:
                continue
            seen.add(key)
            lookup[term].append(
                {
                    "cui": str(row["cui"]),
                    "label": str(row["label"]),
                    "sab": str(row["sab"]),
                    "tty": str(row["tty"]),
                }
            )
    return lookup


def load_extension_label_lookup(
    paths: list[Path],
    terms: Iterable[str],
    *,
    limit: int = 5,
) -> tuple[dict[str, list[dict[str, str]]], dict[str, Any]]:
    wanted = {normalized_key(term): term for term in terms}
    lookup: dict[str, list[dict[str, str]]] = {term: [] for term in wanted.values()}
    stats = {
        "paths": [str(path.relative_to(ROOT)) for path in paths],
        "concepts_read": 0,
        "promoted_concepts_read": 0,
        "labels_read": 0,
        "matched_terms": 0,
    }
    if not paths or not wanted:
        return lookup, stats
    seen: set[tuple[str, str, str]] = set()
    for path in paths:
        if not path.exists():
            continue
        for concept in iter_extension_concepts(path):
            stats["concepts_read"] += 1
            if concept.status.lower() != "promoted":
                continue
            stats["promoted_concepts_read"] += 1
            for label in [concept.preferred_label, *concept.aliases]:
                stats["labels_read"] += 1
                term = wanted.get(normalized_key(label))
                if not term:
                    continue
                key = (term, concept.concept_id, label)
                if key in seen or len(lookup[term]) >= limit:
                    continue
                seen.add(key)
                lookup[term].append(
                    {
                        "cui": concept.concept_id,
                        "label": label,
                        "sab": "MTH",
                        "tty": "NEW",
                        "status": concept.status,
                        "source": str(path.relative_to(ROOT)),
                    }
                )
    stats["matched_terms"] = sum(1 for values in lookup.values() if values)
    return lookup, stats


def loinc_table_path(loinc_root: Path | None) -> Path | None:
    if loinc_root is None:
        return None
    candidates = [
        loinc_root / "LoincTable" / "Loinc.csv",
        loinc_root / "LoincTableCore" / "LoincTableCore.csv",
        loinc_root / "AccessoryFiles" / "PanelsAndForms" / "Loinc.csv",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def best_loinc_display_name(row: dict[str, str]) -> tuple[str, str]:
    for field in ("DisplayName", "LONG_COMMON_NAME", "CONSUMER_NAME", "SHORTNAME", "COMPONENT"):
        value = clean_text(row.get(field) or "")
        if value:
            return value, field
    return "", ""


def load_loinc_lookup(
    loinc_path: Path | None,
    terms: Iterable[str],
    *,
    limit: int = 5,
) -> tuple[dict[str, list[dict[str, str]]], dict[str, Any]]:
    wanted = {normalized_key(term): term for term in terms}
    lookup: dict[str, list[dict[str, str]]] = {term: [] for term in wanted.values()}
    stats = {
        "loinc_path": str(loinc_path.relative_to(ROOT)) if loinc_path and loinc_path.exists() else "",
        "rows": 0,
        "active_rows": 0,
        "matched_terms": 0,
    }
    if loinc_path is None or not loinc_path.exists() or not wanted:
        return lookup, stats
    seen: set[tuple[str, str, str]] = set()
    with loinc_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            stats["rows"] += 1
            if str(row.get("STATUS") or "").upper() == "ACTIVE":
                stats["active_rows"] += 1
            loinc_num = str(row.get("LOINC_NUM") or "").strip()
            for field in LOINC_NAME_FIELDS:
                label = clean_text(row.get(field) or "")
                term = wanted.get(normalized_key(label))
                if not term:
                    continue
                key = (term, loinc_num, field)
                if key in seen or len(lookup[term]) >= limit:
                    continue
                seen.add(key)
                lookup[term].append(
                    {
                        "loinc_num": loinc_num,
                        "label": label,
                        "field": field,
                        "long_common_name": clean_text(row.get("LONG_COMMON_NAME") or ""),
                        "display_name": clean_text(row.get("DisplayName") or ""),
                        "component": clean_text(row.get("COMPONENT") or ""),
                        "property": clean_text(row.get("PROPERTY") or ""),
                        "system": clean_text(row.get("SYSTEM") or ""),
                        "scale": clean_text(row.get("SCALE_TYP") or ""),
                        "class": clean_text(row.get("CLASS") or ""),
                        "status": clean_text(row.get("STATUS") or ""),
                    }
                )
    stats["matched_terms"] = sum(1 for values in lookup.values() if values)
    return lookup, stats


def write_loinc_display_names(
    *,
    loinc_path: Path | None,
    out_path: Path,
    max_rows: int = 0,
) -> dict[str, Any]:
    stats = {
        "loinc_path": str(loinc_path.relative_to(ROOT)) if loinc_path and loinc_path.exists() else "",
        "rows_read": 0,
        "rows_written": 0,
        "active_rows_written": 0,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "loinc_num",
        "display_label",
        "display_label_source",
        "long_common_name",
        "component",
        "property",
        "time_aspect",
        "system",
        "scale",
        "method",
        "class",
        "status",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as out_handle:
        writer = csv.DictWriter(out_handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        if loinc_path is None or not loinc_path.exists():
            return stats
        with loinc_path.open("r", encoding="utf-8-sig", newline="") as in_handle:
            reader = csv.DictReader(in_handle)
            for row in reader:
                stats["rows_read"] += 1
                display_label, source = best_loinc_display_name(row)
                if not display_label:
                    continue
                status = clean_text(row.get("STATUS") or "")
                writer.writerow(
                    {
                        "loinc_num": clean_text(row.get("LOINC_NUM") or ""),
                        "display_label": display_label,
                        "display_label_source": source,
                        "long_common_name": clean_text(row.get("LONG_COMMON_NAME") or ""),
                        "component": clean_text(row.get("COMPONENT") or ""),
                        "property": clean_text(row.get("PROPERTY") or ""),
                        "time_aspect": clean_text(row.get("TIME_ASPCT") or ""),
                        "system": clean_text(row.get("SYSTEM") or ""),
                        "scale": clean_text(row.get("SCALE_TYP") or ""),
                        "method": clean_text(row.get("METHOD_TYP") or ""),
                        "class": clean_text(row.get("CLASS") or ""),
                        "status": status,
                    }
                )
                stats["rows_written"] += 1
                if status.upper() == "ACTIVE":
                    stats["active_rows_written"] += 1
                if max_rows and stats["rows_written"] >= max_rows:
                    break
    return stats


def resolve_anchor(
    term: str,
    *,
    label_conn: sqlite3.Connection,
    code_lookup: dict[str, list[dict[str, str]]],
) -> dict[str, str] | None:
    matches = label_matches(label_conn, term, limit=10)
    matches.extend(code_lookup.get(term, []))
    return best_match(matches)


def topic_terms() -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    rows = []
    for values in TOPIC_ROWS:
        topic = dict(zip(TOPIC_FIELDS, values))
        for field in (
            "focus",
            "condition",
            "symptom",
            "finding",
            "test",
            "result",
            "treatment",
            "procedure",
            "complication",
        ):
            term = clean_text(topic[field])
            key = (normalized_key(term), field)
            if not term or key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "term": term,
                    "field": field,
                    "domain": topic["domain"],
                    "focus": topic["focus"],
                }
            )
    return rows


def synthetic_term_counts(path: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    if not path.exists():
        return counts
    terms = {normalized_key(row["term"]): row["term"] for row in topic_terms()}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            query_norm = normalized_key(row.get("query") or "")
            padded = f" {query_norm} "
            for norm, term in terms.items():
                if f" {norm} " in padded:
                    counts[term] += 1
    return counts


def compile_term_regex(terms: list[str]) -> re.Pattern[str] | None:
    if not terms:
        return None
    escaped = [re.escape(term) for term in sorted(terms, key=len, reverse=True)]
    return re.compile(r"(?<![A-Za-z0-9])(" + "|".join(escaped) + r")(?![A-Za-z0-9])", re.IGNORECASE)


def evidence_snippet(text: str, start: int, end: int, *, width: int = 180) -> str:
    left = max(0, start - width)
    right = min(len(text), end + width)
    snippet = clean_text(text[left:right])
    return snippet[: width * 2 + 80]


def locally_negated(text: str, start: int) -> bool:
    prefix = text[max(0, start - 90) : start]
    return bool(NEGATION_PREFIX_RE.search(prefix))


def scan_existing_documents(
    doc_paths: list[Path],
    missing_terms: list[str],
    *,
    max_examples_per_term: int,
) -> dict[str, dict[str, Any]]:
    support = {
        term: {
            "existing_doc_hits": 0,
            "support_cuis": Counter(),
            "support_sources": Counter(),
            "examples": [],
        }
        for term in missing_terms
    }
    pattern = compile_term_regex(missing_terms)
    if pattern is None:
        return support
    canonical = {normalized_key(term): term for term in missing_terms}
    for path in doc_paths:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = str(record.get("text") or "")
                matched_terms: set[str] = set()
                for match in pattern.finditer(text):
                    term = canonical.get(normalized_key(match.group(1)))
                    if not term or term in matched_terms:
                        continue
                    if locally_negated(text, match.start()):
                        continue
                    matched_terms.add(term)
                    bucket = support[term]
                    bucket["existing_doc_hits"] += 1
                    cui = str(record.get("cui") or "")
                    if cui:
                        bucket["support_cuis"][cui] += 1
                    for source in record.get("sources") or []:
                        if source:
                            bucket["support_sources"][str(source)] += 1
                    examples = bucket["examples"]
                    if len(examples) < max_examples_per_term:
                        examples.append(
                            {
                                "source_path": str(path.relative_to(ROOT)),
                                "line": line_number,
                                "doc_id": str(record.get("doc_id") or ""),
                                "cui": cui,
                                "labels": list(record.get("labels") or [])[:5],
                                "text": evidence_snippet(text, match.start(), match.end()),
                            }
                        )
    return support


def infer_semantic_type(field: str, term: str) -> str:
    if field == "test":
        return "Laboratory Procedure"
    if field == "procedure":
        return "Therapeutic or Preventive Procedure"
    if field == "treatment":
        return "Therapeutic or Preventive Procedure"
    if field == "complication":
        return "Pathologic Function"
    if field == "symptom":
        return "Sign or Symptom"
    if field in {"finding", "result"}:
        return "Finding"
    if "infection" in normalized_key(term):
        return "Disease or Syndrome"
    return "Clinical Concept"


def clearer_label(term: str) -> str:
    replacements = {
        "paO2": "PaO2",
        "tsh": "TSH",
        "a1c": "A1c",
        "mca": "MCA",
        "mcp": "MCP",
        "ccp": "CCP",
        "ciwa": "CIWA",
        "phq": "PHQ",
        "mri": "MRI",
    }
    words = term.split()
    output = []
    for word in words:
        key = word.lower()
        output.append(replacements.get(key, word))
    return " ".join(output)


def evaluate_decision(
    row: dict[str, str],
    *,
    exact_matches: list[dict[str, str]],
    code_matches: list[dict[str, str]],
    loinc_matches: list[dict[str, str]],
    extension_matches: list[dict[str, str]],
    semantic_coverage_anchors: list[dict[str, str]],
    synthetic_count: int,
    support: dict[str, Any],
    min_support_docs: int,
    min_support_cuis: int,
) -> tuple[str, str]:
    term = row["term"]
    field = row["field"]
    support_docs = int(support["existing_doc_hits"])
    support_cuis = len(support["support_cuis"])
    if exact_matches:
        return "covered_exact", "Existing label index has an exact normalized label."
    if code_matches:
        return "covered_code_index", "Existing code resolver index has an exact label/code mapping."
    if loinc_matches:
        return "covered_direct_loinc", "Direct LOINC file has an exact display/name match."
    if extension_matches:
        return "covered_extension", "Prior promoted local extension concept has an exact label match."
    if semantic_coverage_anchors:
        anchor = semantic_coverage_anchors[0]
        return (
            "covered_semantic_anchor",
            f"Existing concept {anchor['cui']} ({anchor['label']}) is a curated semantic-equivalent coverage anchor.",
        )
    if support_docs < min_support_docs or support_cuis < min_support_cuis:
        return (
            "insufficient_existing_support",
            f"Missing exact label, but support is only {support_docs} docs across {support_cuis} CUIs.",
        )
    if field not in PROMOTABLE_FIELDS:
        return "defer_non_core_field", f"{field} is useful context but not a first-pass concept boundary."
    if RISK_RE.search(term):
        return "defer_risk_relation_phrase", "Risk phrases should be modeled as relations or risk states after a stricter pass."
    if SEVERITY_ONLY_RE.search(term):
        return "defer_severity_modifier_phrase", "Severity-only modifiers are not first-pass concept boundaries."
    if NORMAL_OR_ABSENT_RE.search(term):
        return "defer_normal_or_absent_result_phrase", "Normal/absent-result phrases should be modeled as result states before CUI promotion."
    if COMBINATION_RE.search(term):
        return "defer_composite_phrase", "Composite phrase should be split or modeled as a relation first."
    if GENERIC_RE.search(term):
        return "defer_generic_workflow_phrase", "Phrase is workflow-like or display cleanup, not a concept yet."
    if synthetic_count < 4:
        return "defer_low_query_pressure", "Existing support exists, but generated query pressure is low."
    return (
        "create_new_cui",
        "No exact level-0 label match; repeated generated-query pressure and existing local evidence support a distinct clinically useful concept.",
    )


def write_tsv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def cumulative_extension_payloads(
    previous_paths: list[Path],
    new_payloads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_payload(payload: dict[str, Any]) -> None:
        concept_id = str(payload.get("concept_id") or payload.get("cui") or "").strip()
        if not concept_id or concept_id in seen:
            return
        seen.add(concept_id)
        output.append(payload)

    for path in previous_paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if str(payload.get("status") or "").lower() != "promoted":
                    continue
                add_payload(payload)
    for payload in new_payloads:
        add_payload(payload)
    return output


def anchor_summary(anchors: list[dict[str, str]]) -> str:
    return "|".join(f"{anchor['cui']}:{anchor['label']}" for anchor in anchors)


def review_flags(row: dict[str, Any]) -> list[str]:
    flags = []
    if not row.get("broader_anchors") and not row.get("close_match_anchors"):
        flags.append("missing_anchor")
    if not row.get("broader_anchors") and row.get("close_match_anchors"):
        flags.append("close_match_only")
    if int(row.get("existing_doc_hits") or 0) < 15:
        flags.append("low_support_doc_count")
    if int(row.get("support_cui_count") or 0) < 12:
        flags.append("low_support_cui_diversity")
    if row.get("field") == "condition" and row.get("close_match_anchors"):
        flags.append("condition_close_match")
    return flags


def candidate_review_rows(created_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in created_rows:
        examples = row.get("examples") or []
        rows.append(
            {
                "concept_id": row["concept_id"],
                "preferred_label": row["preferred_label"],
                "semantic_type": row["semantic_type"],
                "field": row["field"],
                "domain": row["domain"],
                "focus": row["focus"],
                "synthetic_query_mentions": row["synthetic_query_mentions"],
                "existing_doc_hits": row["existing_doc_hits"],
                "support_cui_count": row["support_cui_count"],
                "broader_anchors": anchor_summary(row.get("broader_anchors", [])),
                "close_match_anchors": anchor_summary(row.get("close_match_anchors", [])),
                "top_support_cuis": "|".join(
                    f"{item['cui']}:{item['count']}" for item in row.get("top_support_cuis", [])[:5]
                ),
                "review_flags": "|".join(review_flags(row)),
                "example": examples[0]["text"] if examples else "",
            }
        )
    return rows


def relation_quality_rows(relation_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in relation_rows:
        if row["relation"] != "RB":
            continue
        rows.append(
            {
                "source_cui": row["source_cui"],
                "source_label": row["source_label"],
                "relation": row["relation"],
                "target_cui": row["target_cui"],
                "target_label": row["target_label"],
                "sab": row["sab"],
                "quality_status": "needs_human_spot_check",
                "quality_note": (
                    "Local Codex assertion from curated anchor map; use as extension relation, "
                    "not as official MRREL."
                ),
            }
        )
    return rows


def write_candidate_review(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Candidate Review",
        "",
        "This review table is generated from existing local artifacts only.",
        "",
        "| CUI | Label | Anchors | Flags |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        anchors = []
        if row["broader_anchors"]:
            anchors.append(f"broader: {row['broader_anchors']}")
        if row["close_match_anchors"]:
            anchors.append(f"close: {row['close_match_anchors']}")
        lines.append(
            f"| `{row['concept_id']}` | {row['preferred_label']} | "
            f"{'; '.join(anchors) or 'none'} | {row['review_flags'] or 'none'} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_report(path: Path, manifest: dict[str, Any], created_rows: list[dict[str, Any]]) -> None:
    lines = [
        f"# Existing-Data New UMLS {manifest['iteration']}",
        "",
        f"Created: {manifest['created_at']}",
        "",
        "## Scope",
        "",
        "This iteration used only existing local artifacts. It did not fetch new data.",
        "",
        "Inputs:",
    ]
    for doc_path in manifest["inputs"]["concept_document_paths"]:
        lines.append(f"- `{doc_path}`")
    lines.extend(
        [
            f"- Label index: `{manifest['inputs']['label_index']}`",
            f"- Code resolver index: `{manifest['inputs']['code_index']}`",
            f"- Direct LOINC table: `{manifest['inputs']['loinc_table'] or 'not found'}`",
            f"- Prior extension concepts: `{len(manifest['inputs'].get('previous_extension_concept_paths', []))}` file(s)",
            f"- Synthetic sentence set: `{manifest['inputs']['sentences']}`",
            "",
            "## Summary",
            "",
        ]
    )
    summary = manifest["summary"]
    lines.extend(
        [
            f"- Terms evaluated: `{summary['terms_evaluated']}`",
            f"- Exact-label covered terms: `{summary['exact_label_covered']}`",
            f"- Code-index covered terms: `{summary['exact_code_index_covered']}`",
            f"- Direct-LOINC covered terms: `{summary['exact_direct_loinc_covered']}`",
            f"- Prior-extension covered terms: `{summary.get('exact_extension_covered', 0)}`",
            f"- Semantic-anchor covered terms: `{summary.get('semantic_anchor_covered', 0)}`",
            f"- Remaining exact-coverage gaps: `{summary['missing_exact_coverage']}`",
            f"- New local CUIs created: `{summary['new_cuis_created']}`",
            f"- Cumulative local CUIs available: `{summary.get('cumulative_extension_concepts', summary['new_cuis_created'])}`",
            f"- Candidate-review flags: `{summary.get('candidate_review_flags', 0)}`",
            "",
            "Decision counts:",
        ]
    )
    for decision, count in summary["decisions"].items():
        lines.append(f"- `{decision}`: `{count}`")
    lines.extend(["", "## Created Local CUIs", ""])
    if not created_rows:
        lines.append("No `NEW#######` CUIs were created in this iteration.")
    else:
        lines.append("| CUI | Label | Semantic type | Support docs | Support CUIs |")
        lines.append("| --- | --- | --- | ---: | ---: |")
        for row in created_rows:
            lines.append(
                f"| `{row['concept_id']}` | {row['preferred_label']} | "
                f"{row['semantic_type']} | {row['existing_doc_hits']} | {row['support_cui_count']} |"
            )
    lines.extend(["", "## MTH Broader/Narrower Relations", ""])
    relation_count = manifest["summary"].get("mth_broader_narrower_relations", 0)
    if not relation_count:
        lines.append("No MTH broader/narrower relation rows were emitted.")
    else:
        lines.append(f"Emitted `{relation_count}` MTH broader/narrower relation rows.")
        lines.append("")
        lines.append("| NEW CUI | Label | Broader CUI | Broader label |")
        lines.append("| --- | --- | --- | --- |")
        for row in created_rows:
            for anchor in row.get("broader_anchors", []):
                lines.append(
                    f"| `{row['concept_id']}` | {row['preferred_label']} | "
                    f"`{anchor['cui']}` | {anchor['label']} |"
                )
    lines.extend(
        [
            "",
            "## Review Artifacts",
            "",
            f"- Candidate review: `{manifest['outputs']['candidate_review_markdown']}`",
            f"- Candidate review TSV: `{manifest['outputs']['candidate_review_tsv']}`",
            f"- Relation quality TSV: `{manifest['outputs']['relation_quality_tsv']}`",
            f"- Direct LOINC display names: `{manifest['outputs']['loinc_display_names_tsv']}`",
            f"- Cumulative extension registry: `{manifest['outputs'].get('extension_concept_registry_cumulative', '')}`",
            f"- Release decision: `{manifest['outputs'].get('release_decision', '')}`",
            "",
            "## Vector/Reindex Decision",
            "",
            "This iteration emitted concept documents and registries but did not load vectors into the active search alias.",
            "The cumulative extension concept documents can be embedded and loaded as the next versioned extension shard.",
            "",
            "## Guardrails Applied",
            "",
            "- Exact UMLS label matches, exact code-resolver labels, and exact direct-LOINC names were treated as covered.",
            "- Prior promoted `NEW#######` concepts and curated semantic-equivalent anchors were treated as covered.",
            "- Candidate creation required generated-query pressure plus support in existing concept documents.",
            "- Support snippets with local negation cues were skipped.",
            "- Composite phrases, risk phrases, severity-only phrases, generic workflow phrases, and treatment-only context were deferred.",
            "- Created CUIs are local `NEW#######` concepts, not official NLM UMLS CUIs.",
            "- MTH `RB`/`RN` rows are local extension assertions and should not be treated as NLM MRREL rows.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_release_decision(path: Path, manifest: dict[str, Any]) -> None:
    summary = manifest["summary"]
    outputs = manifest["outputs"]
    lines = [
        f"# Release Decision: {manifest['iteration']}",
        "",
        f"Created: {manifest['created_at']}",
        "",
        "Decision: do not move an active search alias in this run.",
        "",
        "Reason:",
        "- This was an existing-data concept-extension iteration.",
        "- Extension concept documents were emitted, but vectors were not generated or loaded into Elasticsearch.",
        "- Search-interface evaluation should run after the cumulative extension documents are embedded and loaded into a versioned extension shard.",
        "",
        "Available for the next vector pass:",
        f"- Incremental concepts: `{outputs['extension_concepts']}`",
        f"- Incremental concept documents: `{outputs['extension_concept_documents']}`",
        f"- Cumulative concepts: `{outputs['extension_concepts_cumulative']}`",
        f"- Cumulative concept documents: `{outputs['extension_concept_documents_cumulative']}`",
        "",
        "Run summary:",
        f"- New local CUIs: `{summary['new_cuis_created']}`",
        f"- Cumulative local CUIs: `{summary.get('cumulative_extension_concepts', summary['new_cuis_created'])}`",
        f"- MTH broader/narrower rows: `{summary['mth_broader_narrower_relations']}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def concept_payload(row: dict[str, Any], *, iteration: str) -> dict[str, Any]:
    support_cuis = [item["cui"] for item in row["top_support_cuis"]]
    evidence = []
    for index, example in enumerate(row["examples"], start=1):
        evidence.append(
            {
                "evidence_id": f"{row['concept_id']}:{iteration}:{index:03d}",
                "text": example["text"],
                "source": "existing_concept_documents",
                "evidence_type": "existing_data_iteration_support",
                "weight": 1.25,
                "metadata": {
                    "source_path": example["source_path"],
                    "source_doc_id": example["doc_id"],
                    "source_cui": example["cui"],
                    "source_labels": example["labels"],
                    "line": example["line"],
                },
            }
        )
    return {
        "concept_id": row["concept_id"],
        "preferred_label": row["preferred_label"],
        "aliases": [row["term"]] if row["preferred_label"] != row["term"] else [],
        "semantic_type": row["semantic_type"],
        "definition": (
            f"Clinically useful local concept for {row['term']} identified from existing "
            f"search-test phrases and existing local evidence documents."
        ),
        "status": "promoted",
        "broader_cuis": [anchor["cui"] for anchor in row.get("broader_anchors", [])],
        "close_match_cuis": [anchor["cui"] for anchor in row.get("close_match_anchors", [])],
        "related_cuis": [
            cui
            for cui in support_cuis
            if cui not in {anchor["cui"] for anchor in row.get("broader_anchors", [])}
            and cui not in {anchor["cui"] for anchor in row.get("close_match_anchors", [])}
        ][:8],
        "evidence": evidence,
        "metadata": {
            "iteration": iteration,
            "evaluator": "Codex",
            "source": "existing local artifacts only",
            "field": row["field"],
            "domain": row["domain"],
            "focus": row["focus"],
            "synthetic_query_mentions": row["synthetic_query_mentions"],
            "existing_doc_hits": row["existing_doc_hits"],
            "support_cui_count": row["support_cui_count"],
            "decision_rationale": row["decision_rationale"],
        },
}


def extension_relation_rows(created_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for concept in created_rows:
        source_cui = concept["concept_id"]
        source_label = concept["preferred_label"]
        for rank, anchor in enumerate(concept.get("broader_anchors", []), start=1):
            target_cui = anchor["cui"]
            target_label = anchor["label"]
            rows.append(
                {
                    "source_cui": source_cui,
                    "source_label": source_label,
                    "target_cui": target_cui,
                    "target_label": target_label,
                    "relation": "RB",
                    "rela": "",
                    "sab": "MTH",
                    "direction": "outgoing",
                    "rank": rank,
                    "assertion": "source_has_broader_target",
                    "rationale": f"Local extension concept is narrower than existing UMLS concept {target_cui}.",
                }
            )
            rows.append(
                {
                    "source_cui": target_cui,
                    "source_label": target_label,
                    "target_cui": source_cui,
                    "target_label": source_label,
                    "relation": "RN",
                    "rela": "",
                    "sab": "MTH",
                    "direction": "inverse",
                    "rank": rank,
                    "assertion": "source_has_narrower_target",
                    "rationale": f"Existing UMLS concept {target_cui} has local extension narrower concept {source_cui}.",
                }
            )
    return rows


def write_extension_relation_sqlite(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("DROP TABLE IF EXISTS related_concepts")
    conn.executescript(EXTENSION_RELATION_SCHEMA)
    conn.executemany(
        """
        INSERT INTO related_concepts(
            source_cui, target_cui, relation, rela, sab, direction, label, rank
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row["source_cui"],
                row["target_cui"],
                row["relation"],
                row["rela"],
                row["sab"],
                row["direction"],
                row["target_label"],
                row["rank"],
            )
            for row in rows
        ],
    )
    conn.commit()
    conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a bounded new-UMLS iteration using only existing local data."
    )
    parser.add_argument(
        "--iteration",
        default="",
        help="Iteration identifier to write into manifests and concept metadata. Defaults to the output directory name.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("build/new_umls_iterations/iteration_001_existing_data"),
    )
    parser.add_argument(
        "--label-index",
        type=Path,
        default=Path("build/umls_biomedicine_search_label_index.sqlite"),
    )
    parser.add_argument(
        "--code-index",
        type=Path,
        default=Path("build/cui_code_index.sqlite"),
    )
    parser.add_argument(
        "--sentences",
        type=Path,
        default=Path("config/typical_clinical_research_sentences.tsv"),
    )
    parser.add_argument(
        "--loinc-root",
        type=Path,
        default=Path("Loinc_2.82"),
        help="Direct LOINC release root. If present, LoincTable/Loinc.csv is used for coverage and display-name artifacts.",
    )
    parser.add_argument(
        "--max-loinc-display-rows",
        type=int,
        default=0,
        help="Maximum direct LOINC display rows to write. Default 0 writes all rows.",
    )
    parser.add_argument("--docs", action="append", default=[], help="Concept-document JSONL path.")
    parser.add_argument(
        "--previous-extension-concepts",
        action="append",
        default=[],
        help="Prior extension concept JSONL files to treat as existing local coverage.",
    )
    parser.add_argument("--min-support-docs", type=int, default=8)
    parser.add_argument("--min-support-cuis", type=int, default=2)
    parser.add_argument("--max-examples-per-term", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = (ROOT / args.out_dir).resolve() if not args.out_dir.is_absolute() else args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    iteration_name = args.iteration or out_dir.name
    label_index = (ROOT / args.label_index).resolve() if not args.label_index.is_absolute() else args.label_index
    code_index = (ROOT / args.code_index).resolve() if not args.code_index.is_absolute() else args.code_index
    sentence_path = (ROOT / args.sentences).resolve() if not args.sentences.is_absolute() else args.sentences
    loinc_root = (ROOT / args.loinc_root).resolve() if not args.loinc_root.is_absolute() else args.loinc_root
    loinc_path = loinc_table_path(loinc_root)
    docs = existing_paths(args.docs or DEFAULT_DOC_PATHS)
    previous_extension_paths = existing_paths(args.previous_extension_concepts)
    if not label_index.exists():
        raise SystemExit(f"missing label index: {label_index}")
    code_conn = connect_sqlite(code_index) if code_index.exists() else None
    if not docs:
        raise SystemExit("no existing concept-document paths found")

    conn = connect_label_index(label_index)
    topic_rows = topic_terms()
    synthetic_counts = synthetic_term_counts(sentence_path)
    anchor_terms = {
        term
        for values in [
            *BROADER_ANCHOR_TERMS.values(),
            *CLOSE_MATCH_ANCHOR_TERMS.values(),
            *SEMANTIC_COVERAGE_ANCHOR_TERMS.values(),
        ]
        for term in values
    }
    code_lookup = load_code_label_lookup(
        code_conn,
        [row["term"] for row in topic_rows] + sorted(anchor_terms),
    )
    extension_lookup, extension_lookup_stats = load_extension_label_lookup(
        previous_extension_paths,
        [row["term"] for row in topic_rows],
    )
    loinc_lookup, loinc_lookup_stats = load_loinc_lookup(
        loinc_path,
        [row["term"] for row in topic_rows] + sorted(anchor_terms),
    )
    loinc_display_stats = write_loinc_display_names(
        loinc_path=loinc_path,
        out_path=out_dir / "loinc_display_names.tsv",
        max_rows=args.max_loinc_display_rows,
    )
    rows = []
    missing_rows = []
    for row in topic_rows:
        matches = label_matches(conn, row["term"])
        code_matches = code_lookup.get(row["term"], [])
        loinc_matches = loinc_lookup.get(row["term"], [])
        extension_matches = extension_lookup.get(row["term"], [])
        semantic_coverage_anchors = [
            anchor
            for anchor in (
                resolve_anchor(term, label_conn=conn, code_lookup=code_lookup)
                for term in SEMANTIC_COVERAGE_ANCHOR_TERMS.get(row["term"], [])
            )
            if anchor
        ]
        synthetic_count = synthetic_counts.get(row["term"], 0)
        item = {
            **row,
            "synthetic_query_mentions": synthetic_count,
            "exact_label_matches": matches,
            "exact_code_matches": code_matches,
            "exact_loinc_matches": loinc_matches,
            "exact_extension_matches": extension_matches,
            "semantic_coverage_anchors": semantic_coverage_anchors,
            "exact_label_match_count": len(matches),
            "exact_code_match_count": len(code_matches),
            "exact_loinc_match_count": len(loinc_matches),
            "exact_extension_match_count": len(extension_matches),
            "semantic_coverage_anchor_count": len(semantic_coverage_anchors),
        }
        rows.append(item)
        if not matches and not code_matches and not loinc_matches and not extension_matches and not semantic_coverage_anchors:
            missing_rows.append(item)

    missing_terms = [row["term"] for row in missing_rows]
    support_by_term = scan_existing_documents(
        docs,
        missing_terms,
        max_examples_per_term=args.max_examples_per_term,
    )

    evaluated = []
    for row in rows:
        support = support_by_term.get(
            row["term"],
            {"existing_doc_hits": 0, "support_cuis": Counter(), "support_sources": Counter(), "examples": []},
        )
        decision, rationale = evaluate_decision(
            row,
            exact_matches=row["exact_label_matches"],
            code_matches=row["exact_code_matches"],
            loinc_matches=row["exact_loinc_matches"],
            extension_matches=row["exact_extension_matches"],
            semantic_coverage_anchors=row["semantic_coverage_anchors"],
            synthetic_count=int(row["synthetic_query_mentions"]),
            support=support,
            min_support_docs=args.min_support_docs,
            min_support_cuis=args.min_support_cuis,
        )
        top_cuis = [
            {"cui": cui, "count": count}
            for cui, count in support["support_cuis"].most_common(8)
        ]
        semantic_type = infer_semantic_type(row["field"], row["term"])
        broader_anchors = [
            anchor
            for anchor in (
                resolve_anchor(term, label_conn=conn, code_lookup=code_lookup)
                for term in BROADER_ANCHOR_TERMS.get(row["term"], [])
            )
            if anchor
        ]
        close_match_anchors = [
            anchor
            for anchor in (
                resolve_anchor(term, label_conn=conn, code_lookup=code_lookup)
                for term in CLOSE_MATCH_ANCHOR_TERMS.get(row["term"], [])
            )
            if anchor
        ]
        evaluated.append(
            {
                **row,
                "concept_id": (
                    stable_extension_id(row["term"], semantic_type=semantic_type)
                    if decision == "create_new_cui"
                    else ""
                ),
                "preferred_label": clearer_label(row["term"]),
                "semantic_type": semantic_type,
                "existing_doc_hits": int(support["existing_doc_hits"]),
                "support_cui_count": len(support["support_cuis"]),
                "top_support_cuis": top_cuis,
                "support_sources": [
                    {"source": source, "count": count}
                    for source, count in support["support_sources"].most_common(6)
                ],
                "broader_anchors": broader_anchors if decision == "create_new_cui" else [],
                "close_match_anchors": close_match_anchors if decision == "create_new_cui" else [],
                "examples": support["examples"],
                "decision": decision,
                "decision_rationale": rationale,
            }
        )

    create_rows = [row for row in evaluated if row["decision"] == "create_new_cui"]
    concept_payloads = [concept_payload(row, iteration=iteration_name) for row in create_rows]
    cumulative_payloads = cumulative_extension_payloads(previous_extension_paths, concept_payloads)
    relation_rows = extension_relation_rows(create_rows)
    review_rows = candidate_review_rows(create_rows)
    quality_rows = relation_quality_rows(relation_rows)

    write_jsonl(out_dir / "term_evaluation.jsonl", evaluated)
    write_jsonl(out_dir / "extension_concepts.new.jsonl", concept_payloads)
    write_jsonl(out_dir / "extension_concepts.cumulative.jsonl", cumulative_payloads)
    write_jsonl(out_dir / "extension_mth_relations.jsonl", relation_rows)
    write_extension_relation_sqlite(out_dir / "extension_mth_relations.sqlite", relation_rows)
    write_candidate_review(out_dir / "candidate_review.md", review_rows)
    write_tsv(
        out_dir / "candidate_review.tsv",
        review_rows,
        [
            "concept_id",
            "preferred_label",
            "semantic_type",
            "field",
            "domain",
            "focus",
            "synthetic_query_mentions",
            "existing_doc_hits",
            "support_cui_count",
            "broader_anchors",
            "close_match_anchors",
            "top_support_cuis",
            "review_flags",
            "example",
        ],
    )
    write_tsv(
        out_dir / "relation_quality.tsv",
        quality_rows,
        [
            "source_cui",
            "source_label",
            "relation",
            "target_cui",
            "target_label",
            "sab",
            "quality_status",
            "quality_note",
        ],
    )
    if concept_payloads:
        build_extension_concept_artifacts(
            input_path=out_dir / "extension_concepts.new.jsonl",
            out_docs=out_dir / "extension_concept_documents.jsonl",
            out_evidence=out_dir / "extension_concept_evidence.jsonl",
            out_registry=out_dir / "extension_concept_registry.jsonl",
            include_status={"promoted"},
        )
    else:
        write_jsonl(out_dir / "extension_concept_documents.jsonl", [])
        write_jsonl(out_dir / "extension_concept_evidence.jsonl", [])
        write_jsonl(out_dir / "extension_concept_registry.jsonl", [])
    if cumulative_payloads:
        build_extension_concept_artifacts(
            input_path=out_dir / "extension_concepts.cumulative.jsonl",
            out_docs=out_dir / "extension_concept_documents.cumulative.jsonl",
            out_evidence=out_dir / "extension_concept_evidence.cumulative.jsonl",
            out_registry=out_dir / "extension_concept_registry.cumulative.jsonl",
            include_status={"promoted"},
        )
    else:
        write_jsonl(out_dir / "extension_concept_documents.cumulative.jsonl", [])
        write_jsonl(out_dir / "extension_concept_evidence.cumulative.jsonl", [])
        write_jsonl(out_dir / "extension_concept_registry.cumulative.jsonl", [])

    tsv_rows = []
    for row in evaluated:
        tsv_rows.append(
            {
                "term": row["term"],
                "field": row["field"],
                "domain": row["domain"],
                "focus": row["focus"],
                "synthetic_query_mentions": row["synthetic_query_mentions"],
                "exact_label_match_count": row["exact_label_match_count"],
                "exact_code_match_count": row["exact_code_match_count"],
                "exact_loinc_match_count": row["exact_loinc_match_count"],
                "exact_extension_match_count": row["exact_extension_match_count"],
                "semantic_coverage_anchor_count": row["semantic_coverage_anchor_count"],
                "existing_doc_hits": row["existing_doc_hits"],
                "support_cui_count": row["support_cui_count"],
                "decision": row["decision"],
                "concept_id": row["concept_id"] if row["decision"] == "create_new_cui" else "",
                "rationale": row["decision_rationale"],
            }
        )
    write_tsv(
        out_dir / "term_evaluation.tsv",
        tsv_rows,
        [
            "term",
            "field",
            "domain",
            "focus",
            "synthetic_query_mentions",
            "exact_label_match_count",
            "exact_code_match_count",
            "exact_loinc_match_count",
            "exact_extension_match_count",
            "semantic_coverage_anchor_count",
            "existing_doc_hits",
            "support_cui_count",
            "decision",
            "concept_id",
            "rationale",
        ],
    )

    decisions = Counter(row["decision"] for row in evaluated)
    covered_decisions = {
        "covered_exact",
        "covered_code_index",
        "covered_direct_loinc",
        "covered_extension",
        "covered_semantic_anchor",
    }
    manifest = {
        "iteration": iteration_name,
        "created_at": now_utc(),
        "mode": "existing_data_only",
        "inputs": {
            "label_index": str(label_index.relative_to(ROOT)),
            "sentences": str(sentence_path.relative_to(ROOT)) if sentence_path.exists() else str(sentence_path),
            "concept_document_paths": [str(path.relative_to(ROOT)) for path in docs],
            "previous_extension_concept_paths": [
                str(path.relative_to(ROOT)) for path in previous_extension_paths
            ],
            "code_index": str(code_index.relative_to(ROOT)) if code_index.exists() else str(code_index),
            "loinc_root": str(loinc_root.relative_to(ROOT)) if loinc_root.exists() else str(loinc_root),
            "loinc_table": str(loinc_path.relative_to(ROOT)) if loinc_path and loinc_path.exists() else "",
        },
        "loinc": {
            "lookup": loinc_lookup_stats,
            "display_names": loinc_display_stats,
        },
        "extension_coverage": extension_lookup_stats,
        "thresholds": {
            "min_support_docs": args.min_support_docs,
            "min_support_cuis": args.min_support_cuis,
            "max_examples_per_term": args.max_examples_per_term,
        },
        "summary": {
            "terms_evaluated": len(evaluated),
            "exact_label_covered": decisions.get("covered_exact", 0),
            "exact_code_index_covered": decisions.get("covered_code_index", 0),
            "exact_direct_loinc_covered": decisions.get("covered_direct_loinc", 0),
            "exact_extension_covered": decisions.get("covered_extension", 0),
            "semantic_anchor_covered": decisions.get("covered_semantic_anchor", 0),
            "missing_exact_coverage": len(evaluated)
            - sum(decisions.get(decision, 0) for decision in covered_decisions),
            "new_cuis_created": len(create_rows),
            "cumulative_extension_concepts": len(cumulative_payloads),
            "mth_broader_narrower_relations": len(relation_rows),
            "candidate_review_flags": sum(1 for row in review_rows if row["review_flags"]),
            "decisions": dict(sorted(decisions.items())),
        },
        "outputs": {
            "candidate_review_markdown": str((out_dir / "candidate_review.md").relative_to(ROOT)),
            "candidate_review_tsv": str((out_dir / "candidate_review.tsv").relative_to(ROOT)),
            "iteration_report": str((out_dir / "iteration_report.md").relative_to(ROOT)),
            "term_evaluation_jsonl": str((out_dir / "term_evaluation.jsonl").relative_to(ROOT)),
            "term_evaluation_tsv": str((out_dir / "term_evaluation.tsv").relative_to(ROOT)),
            "extension_concepts": str((out_dir / "extension_concepts.new.jsonl").relative_to(ROOT)),
            "extension_concepts_cumulative": str(
                (out_dir / "extension_concepts.cumulative.jsonl").relative_to(ROOT)
            ),
            "extension_concept_documents": str((out_dir / "extension_concept_documents.jsonl").relative_to(ROOT)),
            "extension_concept_evidence": str((out_dir / "extension_concept_evidence.jsonl").relative_to(ROOT)),
            "extension_concept_registry": str((out_dir / "extension_concept_registry.jsonl").relative_to(ROOT)),
            "extension_concept_documents_cumulative": str(
                (out_dir / "extension_concept_documents.cumulative.jsonl").relative_to(ROOT)
            ),
            "extension_concept_evidence_cumulative": str(
                (out_dir / "extension_concept_evidence.cumulative.jsonl").relative_to(ROOT)
            ),
            "extension_concept_registry_cumulative": str(
                (out_dir / "extension_concept_registry.cumulative.jsonl").relative_to(ROOT)
            ),
            "extension_mth_relations_jsonl": str((out_dir / "extension_mth_relations.jsonl").relative_to(ROOT)),
            "extension_mth_relations_sqlite": str((out_dir / "extension_mth_relations.sqlite").relative_to(ROOT)),
            "loinc_display_names_tsv": str((out_dir / "loinc_display_names.tsv").relative_to(ROOT)),
            "relation_quality_tsv": str((out_dir / "relation_quality.tsv").relative_to(ROOT)),
            "release_decision": str((out_dir / "release_decision.md").relative_to(ROOT)),
        },
    }
    write_report(out_dir / "iteration_report.md", manifest, create_rows)
    write_release_decision(out_dir / "release_decision.md", manifest)
    (out_dir / "iteration_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
