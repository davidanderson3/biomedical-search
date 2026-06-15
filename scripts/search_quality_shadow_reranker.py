#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_JUDGMENTS = ROOT / "config" / "search_quality_judgments.tsv"
DEFAULT_PARAGRAPH_QUERIES = ROOT / "config" / "search_quality_paragraph_queries.tsv"
DEFAULT_CLINICAL_QUERIES = ROOT / "config" / "search_quality_clinical_queries.tsv"
DEFAULT_PORTAL_QUERIES = ROOT / "config" / "search_quality_patient_portal_queries.tsv"
DEFAULT_USEFUL_EXTRAS = ROOT / "config" / "search_quality_useful_extra_cuis.tsv"
DEFAULT_PRECISION_REVIEW = ROOT / "config" / "search_quality_precision_audit_review.tsv"
DEFAULT_PUBMED_SLICE = ROOT / "config" / "search_quality_pubmed_long_document_slice.tsv"
DEFAULT_PUBMED_QUERIES = (
    ROOT / "build" / "pubmed_literature_benchmark_seed" / "pubmed_long_document_focused_queries.tsv"
)
DEFAULT_OUTPUT_DIR = ROOT / "build" / "search_quality_shadow_reranker"

JUDGMENT_FIELDS = [
    "id",
    "cui",
    "judgment",
    "target",
    "weight",
    "source",
    "label",
    "query",
    "why",
]
FEATURE_META_FIELDS = [
    "payload_path",
    "id",
    "query",
    "current_rank",
    "cui",
    "name",
    "semantic_group",
    "judgment",
    "target",
    "sample_weight",
]
RANK_FIELDS = [
    "outcome",
    "triage_cause",
    "triage_reason",
    "desired_delta",
    "current_rank",
    "ml_rank",
    "id",
    "cui",
    "name",
    "judgment",
    "target",
    "current_rank_score",
    "ml_score",
    "semantic_group",
    "query",
    "payload_path",
]
REGRESSION_TRIAGE_FIELDS = [
    "triage_cause",
    "triage_reason",
    "desired_delta",
    "current_rank",
    "ml_rank",
    "id",
    "cui",
    "name",
    "judgment",
    "target",
    "semantic_group",
    "current_rank_score",
    "ml_score",
    "query",
    "payload_path",
]
EVIDENCE_DECISION_FIELDS = [
    "decision",
    "scope",
    "key",
    "source",
    "evidence_type",
    "item_signature",
    "score",
    "positive_rate",
    "negative_rate",
    "judged_observations",
    "positive_observations",
    "negative_observations",
    "unjudged_observations",
    "total_observations",
    "total_query_count",
    "positive_query_count",
    "negative_query_count",
    "unjudged_query_count",
    "active_expected_observations",
    "expected_observations",
    "context_expected_observations",
    "useful_extra_observations",
    "true_false_positive_observations",
    "disallowed_observations",
    "dev_positive_observations",
    "dev_negative_observations",
    "heldout_positive_observations",
    "heldout_negative_observations",
    "best_rank",
    "mean_rank",
    "worst_rank",
    "quality_flags",
    "item_text",
]
EVIDENCE_EXAMPLE_FIELDS = [
    "decision",
    "scope",
    "key",
    "source",
    "evidence_type",
    "query_id",
    "rank",
    "cui",
    "name",
    "judgment",
    "bucket",
    "query",
    "evidence_text",
    "payload_path",
]
EVIDENCE_POLICY_FIELDS = [
    "policy",
    "scope",
    "key",
    "source",
    "evidence_type",
    "item_signature",
    "rank_effect",
    "shadow_weight",
    "search_usefulness_tier",
    "rationale",
    "decision",
    "score",
    "positive_observations",
    "negative_observations",
    "unjudged_observations",
    "heldout_positive_observations",
    "heldout_negative_observations",
    "quality_flags",
]

TARGET_BY_JUDGMENT = {
    "active_expected": 3.0,
    "expected": 3.0,
    "context_expected": 1.5,
    "useful_extra": 1.0,
    "unlabeled": 0.0,
    "disallowed": -2.0,
    "true_false_positive": -2.0,
}
WEIGHT_BY_JUDGMENT = {
    "active_expected": 4.0,
    "expected": 3.0,
    "context_expected": 2.0,
    "useful_extra": 1.5,
    "unlabeled": 0.15,
    "disallowed": 3.0,
    "true_false_positive": 4.0,
}
POSITIVE_JUDGMENTS = {"active_expected", "expected", "context_expected", "useful_extra"}
NEGATIVE_JUDGMENTS = {"disallowed", "true_false_positive"}
JUDGMENT_PRIORITY = {
    "active_expected": 60,
    "expected": 55,
    "true_false_positive": 50,
    "disallowed": 45,
    "context_expected": 40,
    "useful_extra": 30,
    "unlabeled": 0,
}

TOKEN_RE = re.compile(r"[a-z0-9]+")
SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_]+")
SOURCE_SAFE_RE = re.compile(r"[^a-z0-9_.:-]+")
TRIAL_PROTOCOL_MARKERS = (
    "arms and interventions",
    "eligibility criteria",
    "enrollment",
    "planned endpoint",
    "planned outcome",
    "primary outcome measure",
    "protocol",
    "recruiting",
    "secondary outcome measure",
    "study design",
)
TRIAL_RESULT_MARKERS = (
    "actual enrollment",
    "actual result",
    "has_results",
    "outcome result",
    "posted outcome",
    "posted result",
    "results posted",
    "results_first_posted",
)
ADMIN_MARKERS = (
    "billing",
    "contact",
    "eligibility",
    "enrollment",
    "identifier",
    "protocol",
    "review",
    "schedule",
    "status",
    "withdrawal",
)
REFERENCE_MARKERS = (
    "definition",
    "label",
    "ontology",
    "reference",
    "umls_label",
)


@dataclass
class FeatureRow:
    meta: dict[str, str]
    features: dict[str, float]


def rel_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def split_cuis(value: object) -> list[str]:
    text = str(value or "")
    normalized = text.replace(",", "|").replace(";", "|")
    return [part.strip().upper() for part in normalized.split("|") if part.strip()]


def tokens(text: object) -> set[str]:
    return set(TOKEN_RE.findall(str(text or "").lower()))


def safe_feature_name(value: object) -> str:
    text = SAFE_NAME_RE.sub("_", str(value or "").strip()).strip("_").lower()
    return text or "blank"


def to_float(value: object, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def bool_float(value: object) -> float:
    return 1.0 if value is True or str(value).strip().lower() in {"1", "true", "yes", "y"} else 0.0


def compact_text(value: object, *, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def normalize_evidence_source(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"\s+", "_", text)
    return SOURCE_SAFE_RE.sub("_", text).strip("_")


def normalize_evidence_type(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"\s+", "_", text)
    return SOURCE_SAFE_RE.sub("_", text).strip("_")


def evidence_item_text_signature(text: object) -> str:
    normalized = " ".join(TOKEN_RE.findall(str(text or "").lower()))
    if not normalized:
        return ""
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:14]


def evidence_judgment_bucket(judgment: str) -> str:
    if judgment in POSITIVE_JUDGMENTS:
        return "positive"
    if judgment in NEGATIVE_JUDGMENTS:
        return "negative"
    return "unjudged"


def evidence_split_for_query(query_id: str, *, heldout_pct: int) -> str:
    if heldout_pct <= 0:
        return "dev"
    if heldout_pct >= 100:
        return "heldout"
    digest = hashlib.sha1(str(query_id or "").encode("utf-8")).hexdigest()
    return "heldout" if int(digest[:8], 16) % 100 < heldout_pct else "dev"


def source_name_from_payload(source: object) -> str:
    if isinstance(source, dict):
        return normalize_evidence_source(
            source.get("source")
            or source.get("label")
            or source.get("corpus_doc_id")
            or source.get("matched_label")
        )
    return normalize_evidence_source(source)


def hit_declared_sources(hit: dict) -> list[str]:
    sources: list[str] = []
    raw_sources = hit.get("sources") or []
    if isinstance(raw_sources, (str, dict)):
        raw_sources = [raw_sources]
    for source in raw_sources:
        normalized = source_name_from_payload(source)
        if normalized and normalized not in sources:
            sources.append(normalized)
    source_mix = hit.get("source_mix") or {}
    if isinstance(source_mix, dict):
        for item in source_mix.get("items") or []:
            if not isinstance(item, dict):
                continue
            normalized = source_name_from_payload(item.get("source"))
            if normalized and normalized not in sources:
                sources.append(normalized)
    return sources


def evidence_item_sources(item: dict, *, fallback_sources: list[str]) -> list[str]:
    raw_sources = item.get("sources") or []
    if not isinstance(raw_sources, list):
        raw_sources = [raw_sources]
    sources: list[str] = []
    for raw_source in raw_sources:
        source = source_name_from_payload(raw_source)
        if source and source not in sources:
            sources.append(source)
    if sources:
        return sources
    return list(fallback_sources) or ["unknown"]


def evidence_type_for_item(item: dict, hit: dict) -> str:
    return normalize_evidence_type(
        item.get("evidence_type")
        or item.get("type")
        or hit.get("view")
        or hit.get("match_type")
        or "unknown"
    )


def evidence_quality_flags(
    *,
    source: str,
    evidence_type: str,
    item_text: str,
) -> list[str]:
    haystack = f"{source} {evidence_type} {item_text}".lower()
    flags: list[str] = []
    if (
        ("clinicaltrials" in haystack or "clinical_trials" in haystack)
        and any(marker in haystack for marker in TRIAL_PROTOCOL_MARKERS)
        and not any(marker in haystack for marker in TRIAL_RESULT_MARKERS)
    ):
        flags.append("protocol_only_trial_text")
    if any(marker in haystack for marker in ADMIN_MARKERS):
        flags.append("administrative_or_protocol_context")
    if any(marker in haystack for marker in REFERENCE_MARKERS):
        flags.append("reference_or_label_context")
    if item_text and len(TOKEN_RE.findall(item_text.lower())) < 5:
        flags.append("very_short_text")
    return flags


def evidence_units_for_hit(hit: dict) -> list[dict[str, str]]:
    declared_sources = hit_declared_sources(hit)
    fallback_type = normalize_evidence_type(hit.get("view") or hit.get("match_type") or "unknown")
    units: dict[tuple[str, str, str], dict[str, str]] = {}

    def add_unit(
        scope: str,
        source: str,
        evidence_type: str,
        *,
        item_signature: str = "",
        item_text: str = "",
    ) -> None:
        source = source or "unknown"
        evidence_type = evidence_type or fallback_type or "unknown"
        if scope == "source":
            key = source
            evidence_type = ""
            unit_key = (scope, key, "")
        elif scope == "source_type":
            key = f"{source}|{evidence_type}"
            unit_key = (scope, key, "")
        else:
            if not item_signature:
                return
            key = f"{source}|{evidence_type}|{item_signature}"
            unit_key = (scope, key, item_signature)
        units.setdefault(
            unit_key,
            {
                "scope": scope,
                "key": key,
                "source": source,
                "evidence_type": evidence_type,
                "item_signature": item_signature,
                "item_text": compact_text(item_text, limit=260),
            },
        )

    for source in declared_sources:
        add_unit("source", source, fallback_type)
        add_unit("source_type", source, fallback_type)

    for item in hit.get("evidence_items") or []:
        if not isinstance(item, dict):
            continue
        item_text = str(item.get("text") or "")
        item_signature = evidence_item_text_signature(item_text)
        evidence_type = evidence_type_for_item(item, hit)
        for source in evidence_item_sources(item, fallback_sources=declared_sources):
            add_unit("source", source, evidence_type)
            add_unit("source_type", source, evidence_type)
            add_unit(
                "evidence_item",
                source,
                evidence_type,
                item_signature=item_signature,
                item_text=item_text,
            )

    return sorted(units.values(), key=lambda row: (row["scope"], row["key"]))


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(
            (line for line in handle if line.strip() and not line.lstrip().startswith("#")),
            delimiter="\t",
        )
        return [dict(row) for row in reader]


def write_tsv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def merge_text(left: str, right: str, sep: str = " | ") -> str:
    left = left.strip()
    right = right.strip()
    if not left:
        return right
    if not right or right in left.split(sep):
        return left
    return f"{left}{sep}{right}"


def add_judgment(
    judgments: dict[tuple[str, str], dict[str, str]],
    *,
    query_id: str,
    cui: str,
    judgment: str,
    source: str,
    query: str = "",
    label: str = "",
    why: str = "",
) -> None:
    query_id = query_id.strip()
    cui = cui.strip().upper()
    if not query_id or not cui:
        return
    target = TARGET_BY_JUDGMENT[judgment]
    weight = WEIGHT_BY_JUDGMENT[judgment]
    incoming = {
        "id": query_id,
        "cui": cui,
        "judgment": judgment,
        "target": f"{target:g}",
        "weight": f"{weight:g}",
        "source": source,
        "label": label.strip(),
        "query": query.strip(),
        "why": why.strip(),
    }
    key = (query_id, cui)
    existing = judgments.get(key)
    if not existing:
        judgments[key] = incoming
        return

    existing_priority = JUDGMENT_PRIORITY.get(existing["judgment"], 0)
    incoming_priority = JUDGMENT_PRIORITY.get(judgment, 0)
    if incoming_priority > existing_priority:
        incoming["source"] = merge_text(existing.get("source", ""), incoming["source"])
        incoming["label"] = incoming["label"] or existing.get("label", "")
        incoming["query"] = incoming["query"] or existing.get("query", "")
        incoming["why"] = merge_text(existing.get("why", ""), incoming["why"])
        judgments[key] = incoming
        return

    existing["source"] = merge_text(existing.get("source", ""), source)
    existing["label"] = existing.get("label", "") or label.strip()
    existing["query"] = existing.get("query", "") or query.strip()
    existing["why"] = merge_text(existing.get("why", ""), why.strip())


def add_expected_query_file(
    judgments: dict[tuple[str, str], dict[str, str]],
    path: Path,
    *,
    source: str,
    only_ids: set[str] | None = None,
) -> None:
    for row in read_tsv(path):
        query_id = str(row.get("id") or "").strip()
        if only_ids is not None and query_id not in only_ids:
            continue
        query = str(row.get("query") or "").strip()
        why = str(row.get("why") or "").strip()
        for cui in split_cuis(row.get("expected_cuis")):
            add_judgment(
                judgments,
                query_id=query_id,
                cui=cui,
                judgment="expected",
                source=source,
                query=query,
                why=why,
            )
        for cui in split_cuis(row.get("disallowed_cuis")):
            add_judgment(
                judgments,
                query_id=query_id,
                cui=cui,
                judgment="disallowed",
                source=source,
                query=query,
                why=why,
            )


def add_patient_portal_file(judgments: dict[tuple[str, str], dict[str, str]], path: Path) -> None:
    for row in read_tsv(path):
        query_id = str(row.get("id") or "").strip()
        query = str(row.get("query") or "").strip()
        why = str(row.get("expected_behavior") or row.get("why") or "").strip()
        active = set(split_cuis(row.get("active_cuis")))
        context = set(split_cuis(row.get("context_cuis")))
        expected = set(split_cuis(row.get("expected_cuis")))
        for cui in sorted(active):
            add_judgment(
                judgments,
                query_id=query_id,
                cui=cui,
                judgment="active_expected",
                source="patient_portal_active",
                query=query,
                why=why,
            )
        for cui in sorted(context):
            add_judgment(
                judgments,
                query_id=query_id,
                cui=cui,
                judgment="context_expected",
                source="patient_portal_context",
                query=query,
                why=why,
            )
        for cui in sorted(expected - active - context):
            add_judgment(
                judgments,
                query_id=query_id,
                cui=cui,
                judgment="expected",
                source="patient_portal_expected",
                query=query,
                why=why,
            )
        for cui in split_cuis(row.get("disallowed_cuis")):
            add_judgment(
                judgments,
                query_id=query_id,
                cui=cui,
                judgment="disallowed",
                source="patient_portal_disallowed",
                query=query,
                why=why,
            )


def add_useful_extra_file(judgments: dict[tuple[str, str], dict[str, str]], path: Path) -> None:
    for row in read_tsv(path):
        add_judgment(
            judgments,
            query_id=str(row.get("id") or row.get("query_id") or ""),
            cui=str(row.get("cui") or ""),
            judgment="useful_extra",
            source="useful_extra_config",
            label=str(row.get("label") or ""),
            why=str(row.get("why") or ""),
        )


def add_precision_review_file(judgments: dict[tuple[str, str], dict[str, str]], path: Path) -> None:
    for row in read_tsv(path):
        review_class = str(row.get("review_class") or "").strip()
        if review_class not in {"useful_extra", "true_false_positive", "expected"}:
            continue
        judgment = "expected" if review_class == "expected" else review_class
        add_judgment(
            judgments,
            query_id=str(row.get("id") or ""),
            cui=str(row.get("cui") or ""),
            judgment=judgment,
            source="precision_audit_review",
            label=str(row.get("label") or ""),
            why=str(row.get("why") or ""),
        )


def seed_judgments(
    out_path: Path = DEFAULT_JUDGMENTS,
    *,
    paragraph_queries: Path = DEFAULT_PARAGRAPH_QUERIES,
    clinical_queries: Path = DEFAULT_CLINICAL_QUERIES,
    portal_queries: Path = DEFAULT_PORTAL_QUERIES,
    useful_extras: Path = DEFAULT_USEFUL_EXTRAS,
    precision_review: Path = DEFAULT_PRECISION_REVIEW,
    pubmed_slice: Path = DEFAULT_PUBMED_SLICE,
    pubmed_queries: Path = DEFAULT_PUBMED_QUERIES,
) -> list[dict[str, str]]:
    judgments: dict[tuple[str, str], dict[str, str]] = {}
    add_expected_query_file(judgments, paragraph_queries, source="paragraph_expected")
    add_expected_query_file(judgments, clinical_queries, source="clinical_expected")
    add_patient_portal_file(judgments, portal_queries)
    add_useful_extra_file(judgments, useful_extras)
    add_precision_review_file(judgments, precision_review)

    slice_ids = {str(row.get("id") or "").strip() for row in read_tsv(pubmed_slice)}
    slice_ids.discard("")
    add_expected_query_file(
        judgments,
        pubmed_queries,
        source="pubmed_long_document_slice",
        only_ids=slice_ids or None,
    )

    rows = [judgments[key] for key in sorted(judgments)]
    write_tsv(out_path, rows, JUDGMENT_FIELDS)
    return rows


def payload_objects(path: Path) -> Iterable[tuple[str, dict]]:
    if path.is_dir():
        for payload_path in sorted(path.glob("*.json")):
            with payload_path.open("r", encoding="utf-8") as handle:
                yield str(payload_path), json.load(handle)
        return
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            yield f"{path}:{line_number}", json.loads(line)


def payload_id_and_response(payload: dict, source_name: str) -> tuple[str, str, dict]:
    if isinstance(payload.get("response"), dict):
        query_id = str(payload.get("id") or "").strip()
        query = str(payload.get("query") or payload["response"].get("query") or "").strip()
        return query_id, query, payload["response"]
    query_id = str(payload.get("id") or "").strip()
    if not query_id:
        query_id = Path(source_name.split(":", 1)[0]).stem
    query = str(payload.get("query") or "").strip()
    return query_id, query, payload


def read_judgments(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    rows = read_tsv(path)
    return {
        (str(row.get("id") or "").strip(), str(row.get("cui") or "").strip().upper()): row
        for row in rows
        if str(row.get("id") or "").strip() and str(row.get("cui") or "").strip()
    }


def query_text_by_id(judgments: dict[tuple[str, str], dict[str, str]]) -> dict[str, str]:
    query_text: dict[str, str] = {}
    for (query_id, _cui), row in judgments.items():
        if row.get("query") and query_id not in query_text:
            query_text[query_id] = str(row.get("query") or "")
    return query_text


def read_evidence_policy(path: Path | None) -> dict[tuple[str, str], dict[str, str]]:
    if path is None:
        return {}
    policy_by_key: dict[tuple[str, str], dict[str, str]] = {}
    for row in read_tsv(path):
        scope = str(row.get("scope") or "").strip()
        key = str(row.get("key") or "").strip()
        if scope and key:
            policy_by_key[(scope, key)] = row
    return policy_by_key


def numeric_score_breakdown(hit: dict) -> dict[str, float]:
    features = {}
    for key, value in (hit.get("score_breakdown") or {}).items():
        number = to_float(value, default=math.nan)
        if not math.isnan(number):
            features[f"sb_{safe_feature_name(key)}"] = number
    return features


def evidence_policy_features(
    hit: dict,
    policy_by_key: dict[tuple[str, str], dict[str, str]],
) -> dict[str, float]:
    if not policy_by_key:
        return {}
    policies: Counter[str] = Counter()
    rank_effects: Counter[str] = Counter()
    scopes: Counter[str] = Counter()
    weight_sum = 0.0
    matched = 0
    for unit in evidence_units_for_hit(hit):
        policy = policy_by_key.get((unit["scope"], unit["key"]))
        if not policy:
            continue
        matched += 1
        weight_sum += to_float(policy.get("shadow_weight"))
        policies[str(policy.get("policy") or "unknown")] += 1
        rank_effects[str(policy.get("rank_effect") or "none")] += 1
        scopes[str(unit.get("scope") or "unknown")] += 1
    if not matched:
        return {}

    features: dict[str, float] = {
        "evidence_policy_match_count_log": math.log1p(matched),
        "evidence_policy_shadow_weight_sum": weight_sum,
        "evidence_policy_shadow_weight_positive": max(0.0, weight_sum),
        "evidence_policy_shadow_weight_negative": min(0.0, weight_sum),
    }
    for policy, count in policies.items():
        features[f"evidence_policy_{safe_feature_name(policy)}_count_log"] = math.log1p(count)
    for rank_effect, count in rank_effects.items():
        features[f"evidence_policy_rank_effect_{safe_feature_name(rank_effect)}_count_log"] = math.log1p(count)
    for scope, count in scopes.items():
        features[f"evidence_policy_scope_{safe_feature_name(scope)}_count_log"] = math.log1p(count)
    return features


def hit_features(
    hit: dict,
    *,
    rank: int,
    query: str,
    evidence_policy: dict[tuple[str, str], dict[str, str]] | None = None,
) -> dict[str, float]:
    name = str(hit.get("name") or hit.get("label") or "")
    matched_span = str(hit.get("matched_query_span") or "")
    matched_label = str(hit.get("matched_label") or "")
    query_tokens = tokens(query)
    name_tokens = tokens(name)
    matched_tokens = tokens(matched_span) | tokens(matched_label)
    semantic_group = str(hit.get("semantic_group") or "OTHER").strip() or "OTHER"
    assertion = hit.get("assertion") or {}
    long_doc = hit.get("long_document_support") or {}
    features: dict[str, float] = {
        "rank_inv": 1.0 / max(rank, 1),
        "rank_log_inv": 1.0 / math.log2(rank + 1.0),
        "rank_score": to_float(hit.get("rank_score"), to_float(hit.get("score"))),
        "retrieval_score": to_float(hit.get("score")),
        "label_fallback_score": to_float(hit.get("label_fallback_score")),
        "evidence_count_log": math.log1p(max(0.0, to_float(hit.get("evidence_count")))),
        "source_count_log": math.log1p(len(hit.get("sources") or [])),
        "code_count_log": math.log1p(len(hit.get("codes") or hit.get("source_asserted_codes") or [])),
        "semantic_type_count_log": math.log1p(len(hit.get("semantic_types") or [])),
        "vector_score_preserved": bool_float(hit.get("vector_score_preserved")),
        "mrrel_component": to_float(hit.get("mrrel_component")),
        "confidence_score": to_float(hit.get("confidence_score")),
        "abstain": bool_float(hit.get("abstain")),
        "query_name_overlap": (len(query_tokens & name_tokens) / len(name_tokens)) if name_tokens else 0.0,
        "matched_token_count_log": math.log1p(len(matched_tokens)),
        "matched_query_coverage": (len(query_tokens & matched_tokens) / len(query_tokens)) if query_tokens else 0.0,
        "long_doc_chunk_count_log": math.log1p(max(0.0, to_float(long_doc.get("chunk_count")))),
        "long_doc_mention_count_log": math.log1p(max(0.0, to_float(long_doc.get("mention_count")))),
        "long_doc_best_score": to_float(long_doc.get("best_score")),
        "long_doc_best_rank_inv": 1.0 / max(1.0, to_float(long_doc.get("best_candidate_rank"), 9999.0)),
        "long_doc_best_section_weight": to_float(long_doc.get("best_section_weight")),
    }
    features.update(numeric_score_breakdown(hit))
    features.update(evidence_policy_features(hit, evidence_policy or {}))
    features[f"semantic_group_{safe_feature_name(semantic_group)}"] = 1.0
    if assertion.get("status"):
        features[f"assertion_{safe_feature_name(assertion.get('status'))}"] = 1.0
    if hit.get("match_type"):
        features[f"match_type_{safe_feature_name(hit.get('match_type'))}"] = 1.0
    for source in (hit.get("sources") or [])[:6]:
        features[f"source_{safe_feature_name(source)}"] = 1.0
    for semantic_type in hit.get("semantic_types") or []:
        tui = str(semantic_type.get("tui") or "").strip()
        name_value = str(semantic_type.get("name") or semantic_type.get("sty") or "").strip()
        if tui:
            features[f"tui_{safe_feature_name(tui)}"] = 1.0
        if name_value:
            features[f"semantic_type_{safe_feature_name(name_value)}"] = 1.0
    return features


def extract_features(
    judgments_path: Path,
    payload_paths: list[Path],
    out_path: Path,
    *,
    unlabeled_weight: float = WEIGHT_BY_JUDGMENT["unlabeled"],
    evidence_policy_path: Path | None = None,
) -> list[FeatureRow]:
    judgments = read_judgments(judgments_path)
    query_text = query_text_by_id(judgments)
    evidence_policy = read_evidence_policy(evidence_policy_path)
    rows: list[FeatureRow] = []
    for payload_path in payload_paths:
        for source_name, payload in payload_objects(payload_path):
            query_id, payload_query, response = payload_id_and_response(payload, source_name)
            query = payload_query or query_text.get(query_id, "")
            for rank, hit in enumerate(response.get("hits") or [], start=1):
                cui = str(hit.get("cui") or "").strip().upper()
                if not cui:
                    continue
                judgment = judgments.get((query_id, cui))
                judgment_name = str(judgment.get("judgment") if judgment else "unlabeled")
                target = to_float(judgment.get("target") if judgment else TARGET_BY_JUDGMENT["unlabeled"])
                sample_weight = to_float(
                    judgment.get("weight") if judgment else unlabeled_weight,
                    default=unlabeled_weight,
                )
                meta = {
                    "payload_path": source_name,
                    "id": query_id,
                    "query": query,
                    "current_rank": str(rank),
                    "cui": cui,
                    "name": str(hit.get("name") or hit.get("label") or ""),
                    "semantic_group": str(hit.get("semantic_group") or ""),
                    "judgment": judgment_name,
                    "target": f"{target:g}",
                    "sample_weight": f"{sample_weight:g}",
                }
                rows.append(
                    FeatureRow(
                        meta=meta,
                        features=hit_features(
                            hit,
                            rank=rank,
                            query=query,
                            evidence_policy=evidence_policy,
                        ),
                    )
                )

    feature_names = sorted({feature for row in rows for feature in row.features})
    output_rows: list[dict[str, object]] = []
    for row in rows:
        output = dict(row.meta)
        for feature_name in feature_names:
            output[f"f_{feature_name}"] = f"{row.features.get(feature_name, 0.0):.8g}"
        output_rows.append(output)
    write_tsv(out_path, output_rows, FEATURE_META_FIELDS + [f"f_{name}" for name in feature_names])
    return rows


def evidence_stats_template(unit: dict[str, str]) -> dict[str, object]:
    return {
        "scope": unit["scope"],
        "key": unit["key"],
        "source": unit["source"],
        "evidence_type": unit["evidence_type"],
        "item_signature": unit["item_signature"],
        "item_text": unit["item_text"],
        "total_observations": 0,
        "positive_observations": 0,
        "negative_observations": 0,
        "unjudged_observations": 0,
        "active_expected_observations": 0,
        "expected_observations": 0,
        "context_expected_observations": 0,
        "useful_extra_observations": 0,
        "true_false_positive_observations": 0,
        "disallowed_observations": 0,
        "dev_positive_observations": 0,
        "dev_negative_observations": 0,
        "heldout_positive_observations": 0,
        "heldout_negative_observations": 0,
        "query_ids": set(),
        "positive_query_ids": set(),
        "negative_query_ids": set(),
        "unjudged_query_ids": set(),
        "ranks": [],
        "quality_flags": set(
            evidence_quality_flags(
                source=unit["source"],
                evidence_type=unit["evidence_type"],
                item_text=unit["item_text"],
            )
        ),
        "examples": [],
    }


def evidence_example_sort_key(example: dict[str, object]) -> tuple[object, ...]:
    bucket_priority = {"negative": 0, "positive": 1, "unjudged": 2}
    return (
        bucket_priority.get(str(example.get("bucket") or ""), 9),
        int(to_float(example.get("rank"), 9999.0)),
        str(example.get("query_id") or ""),
        str(example.get("cui") or ""),
    )


def append_evidence_example(stats: dict[str, object], example: dict[str, object], *, limit: int = 8) -> None:
    examples = stats["examples"]
    assert isinstance(examples, list)
    examples.append(example)
    examples.sort(key=evidence_example_sort_key)
    del examples[limit:]


def observe_evidence_unit(
    stats: dict[str, object],
    *,
    query_id: str,
    query: str,
    rank: int,
    hit: dict,
    judgment_name: str,
    payload_path: str,
    heldout_pct: int,
) -> None:
    bucket = evidence_judgment_bucket(judgment_name)
    split = evidence_split_for_query(query_id, heldout_pct=heldout_pct)
    stats["total_observations"] = int(stats["total_observations"]) + 1
    stats[f"{bucket}_observations"] = int(stats[f"{bucket}_observations"]) + 1
    if judgment_name in POSITIVE_JUDGMENTS | NEGATIVE_JUDGMENTS:
        key = f"{judgment_name}_observations"
        stats[key] = int(stats[key]) + 1
    query_ids = stats["query_ids"]
    bucket_query_ids = stats[f"{bucket}_query_ids"]
    ranks = stats["ranks"]
    assert isinstance(query_ids, set)
    assert isinstance(bucket_query_ids, set)
    assert isinstance(ranks, list)
    query_ids.add(query_id)
    bucket_query_ids.add(query_id)
    ranks.append(rank)
    if bucket in {"positive", "negative"}:
        split_key = f"{split}_{bucket}_observations"
        stats[split_key] = int(stats[split_key]) + 1
    append_evidence_example(
        stats,
        {
            "source": stats["source"],
            "evidence_type": stats["evidence_type"],
            "query_id": query_id,
            "rank": rank,
            "cui": str(hit.get("cui") or "").strip().upper(),
            "name": str(hit.get("name") or hit.get("label") or ""),
            "judgment": judgment_name,
            "bucket": bucket,
            "query": compact_text(query, limit=220),
            "evidence_text": stats["item_text"],
            "payload_path": payload_path,
        },
    )


def evidence_decision_for_stats(
    stats: dict[str, object],
    *,
    min_positive: int,
    min_negative: int,
    min_judged: int,
    heldout_pct: int,
) -> str:
    positive = int(stats["positive_observations"])
    negative = int(stats["negative_observations"])
    judged = positive + negative
    if judged < min_judged:
        return "neutral_insufficient"
    if positive >= min_positive and negative == 0:
        if heldout_pct > 0 and int(stats["heldout_positive_observations"]) == 0:
            return "neutral_needs_heldout"
        return "promote_candidate"
    if negative >= min_negative and positive == 0:
        return "demote_candidate"
    if negative >= min_negative and positive > 0 and negative / max(judged, 1) >= 0.35:
        return "quarantine_candidate"
    if positive == 0 or negative == 0:
        return "neutral_insufficient"
    return "neutral_mixed"


def evidence_stats_to_row(
    stats: dict[str, object],
    *,
    min_positive: int,
    min_negative: int,
    min_judged: int,
    heldout_pct: int,
) -> dict[str, object]:
    positive = int(stats["positive_observations"])
    negative = int(stats["negative_observations"])
    judged = positive + negative
    total = int(stats["total_observations"])
    ranks = list(stats["ranks"])
    query_ids = stats["query_ids"]
    positive_query_ids = stats["positive_query_ids"]
    negative_query_ids = stats["negative_query_ids"]
    unjudged_query_ids = stats["unjudged_query_ids"]
    quality_flags = stats["quality_flags"]
    assert isinstance(query_ids, set)
    assert isinstance(positive_query_ids, set)
    assert isinstance(negative_query_ids, set)
    assert isinstance(unjudged_query_ids, set)
    assert isinstance(quality_flags, set)
    mean_rank = sum(ranks) / len(ranks) if ranks else 0.0
    score = (positive - negative) / max(judged, 1)
    return {
        "decision": evidence_decision_for_stats(
            stats,
            min_positive=min_positive,
            min_negative=min_negative,
            min_judged=min_judged,
            heldout_pct=heldout_pct,
        ),
        "scope": stats["scope"],
        "key": stats["key"],
        "source": stats["source"],
        "evidence_type": stats["evidence_type"],
        "item_signature": stats["item_signature"],
        "score": f"{score:.4f}",
        "positive_rate": f"{positive / judged:.4f}" if judged else "",
        "negative_rate": f"{negative / judged:.4f}" if judged else "",
        "judged_observations": judged,
        "positive_observations": positive,
        "negative_observations": negative,
        "unjudged_observations": stats["unjudged_observations"],
        "total_observations": total,
        "total_query_count": len(query_ids),
        "positive_query_count": len(positive_query_ids),
        "negative_query_count": len(negative_query_ids),
        "unjudged_query_count": len(unjudged_query_ids),
        "active_expected_observations": stats["active_expected_observations"],
        "expected_observations": stats["expected_observations"],
        "context_expected_observations": stats["context_expected_observations"],
        "useful_extra_observations": stats["useful_extra_observations"],
        "true_false_positive_observations": stats["true_false_positive_observations"],
        "disallowed_observations": stats["disallowed_observations"],
        "dev_positive_observations": stats["dev_positive_observations"],
        "dev_negative_observations": stats["dev_negative_observations"],
        "heldout_positive_observations": stats["heldout_positive_observations"],
        "heldout_negative_observations": stats["heldout_negative_observations"],
        "best_rank": min(ranks) if ranks else "",
        "mean_rank": f"{mean_rank:.2f}" if ranks else "",
        "worst_rank": max(ranks) if ranks else "",
        "quality_flags": "|".join(sorted(quality_flags)),
        "item_text": stats["item_text"],
    }


def evidence_decision_sort_key(row: dict[str, object]) -> tuple[object, ...]:
    decision_priority = {
        "promote_candidate": 0,
        "demote_candidate": 1,
        "quarantine_candidate": 2,
        "neutral_mixed": 3,
        "neutral_needs_heldout": 4,
        "neutral_insufficient": 5,
    }
    scope_priority = {"source": 0, "source_type": 1, "evidence_item": 2}
    return (
        decision_priority.get(str(row.get("decision") or ""), 9),
        scope_priority.get(str(row.get("scope") or ""), 9),
        -int(to_float(row.get("judged_observations"))),
        -abs(to_float(row.get("score"))),
        str(row.get("key") or ""),
    )


def evidence_example_rows(
    rows: list[dict[str, object]],
    stats_by_key: dict[tuple[str, str], dict[str, object]],
    *,
    limit: int,
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for row in rows:
        if len(output) >= limit:
            break
        stats = stats_by_key.get((str(row.get("scope") or ""), str(row.get("key") or "")))
        if not stats:
            continue
        examples = stats.get("examples")
        if not isinstance(examples, list):
            continue
        for example in examples[:3]:
            if len(output) >= limit:
                break
            output.append(
                {
                    "decision": row.get("decision", ""),
                    "scope": row.get("scope", ""),
                    "key": row.get("key", ""),
                    "source": example.get("source", ""),
                    "evidence_type": example.get("evidence_type", ""),
                    "query_id": example.get("query_id", ""),
                    "rank": example.get("rank", ""),
                    "cui": example.get("cui", ""),
                    "name": example.get("name", ""),
                    "judgment": example.get("judgment", ""),
                    "bucket": example.get("bucket", ""),
                    "query": example.get("query", ""),
                    "evidence_text": example.get("evidence_text", ""),
                    "payload_path": example.get("payload_path", ""),
                }
            )
    return output


def policy_for_evidence_row(row: dict[str, object]) -> dict[str, object] | None:
    decision = str(row.get("decision") or "")
    flags = set(str(row.get("quality_flags") or "").split("|")) - {""}
    is_reference_context = "reference_or_label_context" in flags
    if decision == "promote_candidate":
        if is_reference_context:
            policy = "context_only"
            rank_effect = "none"
            shadow_weight = "0"
            tier = "display_context"
            rationale = "Repeated positive association, but reference/label-like evidence should support display and provenance rather than ranking."
        else:
            policy = "promote_shadow"
            rank_effect = "promote"
            shadow_weight = "0.02"
            tier = "search_useful"
            rationale = "Repeated judged-positive association with no judged-negative observations; shadow-only until benchmark gates pass."
    elif decision == "demote_candidate":
        policy = "demote_shadow"
        rank_effect = "demote"
        shadow_weight = "-0.04"
        tier = "search_harmful"
        rationale = "Repeated judged-negative association with no judged-positive observations; shadow-only until benchmark gates pass."
    elif decision == "quarantine_candidate":
        policy = "quarantine_display_only"
        rank_effect = "none"
        shadow_weight = "0"
        tier = "display_context"
        rationale = "Mixed evidence with repeated negative signal; keep for provenance/display but do not rank from it without review."
    else:
        return None
    return {
        "policy": policy,
        "scope": row.get("scope", ""),
        "key": row.get("key", ""),
        "source": row.get("source", ""),
        "evidence_type": row.get("evidence_type", ""),
        "item_signature": row.get("item_signature", ""),
        "rank_effect": rank_effect,
        "shadow_weight": shadow_weight,
        "search_usefulness_tier": tier,
        "rationale": rationale,
        "decision": decision,
        "score": row.get("score", ""),
        "positive_observations": row.get("positive_observations", ""),
        "negative_observations": row.get("negative_observations", ""),
        "unjudged_observations": row.get("unjudged_observations", ""),
        "heldout_positive_observations": row.get("heldout_positive_observations", ""),
        "heldout_negative_observations": row.get("heldout_negative_observations", ""),
        "quality_flags": row.get("quality_flags", ""),
    }


def evidence_policy_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    policy_rows = [policy for row in rows if (policy := policy_for_evidence_row(row))]
    policy_priority = {
        "demote_shadow": 0,
        "quarantine_display_only": 1,
        "promote_shadow": 2,
        "context_only": 3,
    }
    return sorted(
        policy_rows,
        key=lambda row: (
            policy_priority.get(str(row.get("policy") or ""), 9),
            str(row.get("scope") or ""),
            -int(to_float(row.get("positive_observations")) + to_float(row.get("negative_observations"))),
            str(row.get("key") or ""),
        ),
    )


def evaluate_evidence_promotion(
    judgments_path: Path,
    payload_paths: list[Path],
    out_dir: Path,
    *,
    top_k: int = 20,
    min_positive: int = 3,
    min_negative: int = 2,
    min_judged: int = 2,
    heldout_pct: int = 20,
    example_limit: int = 200,
) -> dict[str, object]:
    judgments = read_judgments(judgments_path)
    query_text = query_text_by_id(judgments)
    stats_by_key: dict[tuple[str, str], dict[str, object]] = {}
    payload_count = 0
    hit_count = 0
    unit_count = 0

    for payload_path in payload_paths:
        for source_name, payload in payload_objects(payload_path):
            payload_count += 1
            query_id, payload_query, response = payload_id_and_response(payload, source_name)
            query = payload_query or query_text.get(query_id, "")
            for rank, hit in enumerate(list(response.get("hits") or [])[:top_k], start=1):
                cui = str(hit.get("cui") or "").strip().upper()
                if not cui:
                    continue
                hit_count += 1
                judgment = judgments.get((query_id, cui))
                judgment_name = str(judgment.get("judgment") if judgment else "unjudged")
                for unit in evidence_units_for_hit(hit):
                    key = (unit["scope"], unit["key"])
                    stats = stats_by_key.setdefault(key, evidence_stats_template(unit))
                    observe_evidence_unit(
                        stats,
                        query_id=query_id,
                        query=query,
                        rank=rank,
                        hit=hit,
                        judgment_name=judgment_name,
                        payload_path=source_name,
                        heldout_pct=heldout_pct,
                    )
                    unit_count += 1

    rows = [
        evidence_stats_to_row(
            stats,
            min_positive=min_positive,
            min_negative=min_negative,
            min_judged=min_judged,
            heldout_pct=heldout_pct,
        )
        for stats in stats_by_key.values()
    ]
    rows.sort(key=evidence_decision_sort_key)
    examples = evidence_example_rows(rows, stats_by_key, limit=example_limit)

    out_dir.mkdir(parents=True, exist_ok=True)
    rows_path = out_dir / "evidence_promotion_rows.tsv"
    examples_path = out_dir / "evidence_promotion_examples.tsv"
    policy_path = out_dir / "evidence_shadow_policy.tsv"
    summary_path = out_dir / "evidence_promotion_summary.json"
    report_path = out_dir / "evidence_promotion_report.html"
    write_tsv(rows_path, rows, EVIDENCE_DECISION_FIELDS)
    write_tsv(examples_path, examples, EVIDENCE_EXAMPLE_FIELDS)
    policies = evidence_policy_rows(rows)
    write_tsv(policy_path, policies, EVIDENCE_POLICY_FIELDS)
    decision_counts = Counter(str(row.get("decision") or "") for row in rows)
    scope_counts = Counter(str(row.get("scope") or "") for row in rows)
    policy_counts = Counter(str(row.get("policy") or "") for row in policies)
    summary = {
        "payload_count": payload_count,
        "hit_count": hit_count,
        "evidence_unit_observations": unit_count,
        "evidence_units": len(rows),
        "top_k": top_k,
        "min_positive": min_positive,
        "min_negative": min_negative,
        "min_judged": min_judged,
        "heldout_pct": heldout_pct,
        "decision_counts": dict(sorted(decision_counts.items())),
        "policy_counts": dict(sorted(policy_counts.items())),
        "scope_counts": dict(sorted(scope_counts.items())),
        "judgments_path": str(judgments_path),
        "payload_paths": [str(path) for path in payload_paths],
        "rows_path": str(rows_path),
        "examples_path": str(examples_path),
        "policy_path": str(policy_path),
        "report_path": str(report_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_evidence_html_report(
        report_path,
        rows=rows,
        examples=examples,
        summary=summary,
        judgment_path=judgments_path,
    )
    return summary


def read_feature_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    rows = read_tsv(path)
    if not rows:
        return [], []
    feature_names = [field for field in rows[0] if field.startswith("f_")]
    return rows, feature_names


def sparse_vector(row: dict[str, str], feature_names: list[str]) -> dict[str, float]:
    vector = {}
    for feature_name in feature_names:
        value = to_float(row.get(feature_name))
        if value:
            vector[feature_name] = value
    return vector


def dot(weights: dict[str, float], vector: dict[str, float]) -> float:
    return sum(weights.get(feature, 0.0) * value for feature, value in vector.items())


def train_pairwise_model(
    rows: list[dict[str, str]],
    feature_names: list[str],
    *,
    epochs: int = 18,
    learning_rate: float = 0.03,
    l2: float = 0.0005,
) -> tuple[dict[str, float], dict[str, object]]:
    vectors = [sparse_vector(row, feature_names) for row in rows]
    groups: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        if to_float(row.get("sample_weight")) > 0:
            groups[str(row.get("id") or "")].append(index)

    pairs: list[tuple[int, int, float]] = []
    for indexes in groups.values():
        for left in indexes:
            left_target = to_float(rows[left].get("target"))
            for right in indexes:
                right_target = to_float(rows[right].get("target"))
                if left_target <= right_target:
                    continue
                diff = left_target - right_target
                left_weight = to_float(rows[left].get("sample_weight"))
                right_weight = to_float(rows[right].get("sample_weight"))
                pair_weight = min(4.0, diff) * (left_weight + right_weight) / 2.0
                if left_target == 0 or right_target == 0:
                    pair_weight *= 0.25
                if pair_weight > 0:
                    pairs.append((left, right, pair_weight))

    weights = {feature_name: 0.0 for feature_name in feature_names}
    updates = 0
    for _epoch in range(max(1, epochs)):
        for high_index, low_index, pair_weight in pairs:
            high_vector = vectors[high_index]
            low_vector = vectors[low_index]
            margin = dot(weights, high_vector) - dot(weights, low_vector)
            if margin >= 1.0:
                continue
            step = learning_rate * pair_weight
            changed_features = set(high_vector) | set(low_vector)
            for feature in changed_features:
                weights[feature] *= 1.0 - learning_rate * l2
                weights[feature] += step * (high_vector.get(feature, 0.0) - low_vector.get(feature, 0.0))
            updates += 1

    model_info = {
        "algorithm": "pairwise_linear_margin",
        "epochs": epochs,
        "learning_rate": learning_rate,
        "l2": l2,
        "feature_count": len(feature_names),
        "training_rows": len(rows),
        "training_pairs": len(pairs),
        "updates": updates,
    }
    return weights, model_info


def rank_rows_with_model(
    rows: list[dict[str, str]],
    feature_names: list[str],
    weights: dict[str, float],
) -> list[dict[str, object]]:
    scored: list[dict[str, object]] = []
    for row in rows:
        vector = sparse_vector(row, feature_names)
        scored.append({**row, "ml_score": dot(weights, vector)})

    by_query: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in scored:
        by_query[str(row.get("id") or "")].append(row)

    ranked: list[dict[str, object]] = []
    for query_id in sorted(by_query):
        query_rows = by_query[query_id]
        for ml_rank, row in enumerate(
            sorted(
                query_rows,
                key=lambda item: (
                    -to_float(item.get("ml_score")),
                    to_float(item.get("current_rank"), 9999.0),
                    str(item.get("cui") or ""),
                ),
            ),
            start=1,
        ):
            row["ml_rank"] = ml_rank
        ranked.extend(sorted(query_rows, key=lambda item: to_float(item.get("current_rank"), 9999.0)))
    return ranked


def outcome_for_row(row: dict[str, object]) -> tuple[str, int]:
    target = to_float(row.get("target"))
    current_rank = int(to_float(row.get("current_rank"), 9999.0))
    ml_rank = int(to_float(row.get("ml_rank"), 9999.0))
    if target > 0:
        desired_delta = current_rank - ml_rank
    elif target < 0:
        desired_delta = ml_rank - current_rank
    else:
        return "unlabeled", 0
    if desired_delta > 0:
        return "win", desired_delta
    if desired_delta < 0:
        return "regression", desired_delta
    return "loss", desired_delta


def feature(row: dict[str, object], name: str) -> float:
    return to_float(row.get(f"f_{name}"))


def regression_triage_for_row(row: dict[str, object], outcome: str) -> tuple[str, str]:
    if outcome != "regression":
        return "", ""
    target = to_float(row.get("target"))
    judgment = str(row.get("judgment") or "")
    semantic_group = str(row.get("semantic_group") or "OTHER") or "OTHER"
    current_rank = int(to_float(row.get("current_rank"), 9999.0))
    exact_signal = max(
        feature(row, "sb_exact_label_component"),
        feature(row, "sb_exact_primary_name_component"),
        feature(row, "sb_exact_span_component"),
        feature(row, "sb_exact_pharmacologic_component"),
        feature(row, "sb_curated_exact_label_component"),
        feature(row, "sb_local_extension_phrase_component"),
    )
    overlap = feature(row, "query_name_overlap")
    matched_coverage = feature(row, "matched_query_coverage")
    rank_score = feature(row, "rank_score")
    confidence = feature(row, "confidence_score")
    label_match = feature(row, "match_type_umls_label") > 0.0

    if target < 0:
        return (
            "label_gap",
            "negative judged row moved toward the top; add more comparable negative labels before trusting the model",
        )
    if exact_signal <= 0.0 and overlap < 0.35 and matched_coverage < 0.06 and not label_match:
        return (
            "feature_issue",
            "positive row has weak explicit text-match features, so the shadow model cannot see why it is relevant",
        )
    if judgment in {"useful_extra", "context_expected"} and current_rank > 10 and exact_signal <= 0.0:
        return (
            "label_gap",
            "lower-priority positive class is underrepresented for this query shape",
        )
    if semantic_group in {"CHEM", "OBS"} and (exact_signal > 0.0 or overlap >= 0.75 or current_rank <= 10):
        return (
            "model_shape_issue",
            f"shadow model demoted a strong {semantic_group} positive row; global weights are overriding current ranker signals",
        )
    if current_rank <= 10 and (rank_score >= 1.0 or confidence >= 0.55 or overlap >= 0.50):
        return (
            "model_shape_issue",
            "shadow model moved a strong current top-10 positive row down",
        )
    return (
        "label_gap",
        "similar judged examples are too sparse to trust this rank movement",
    )


def shadow_rank_rows(ranked_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    output = []
    for row in ranked_rows:
        outcome, desired_delta = outcome_for_row(row)
        if outcome == "unlabeled":
            continue
        triage_cause, triage_reason = regression_triage_for_row(row, outcome)
        output.append(
            {
                "outcome": outcome,
                "triage_cause": triage_cause,
                "triage_reason": triage_reason,
                "desired_delta": desired_delta,
                "current_rank": row.get("current_rank", ""),
                "ml_rank": row.get("ml_rank", ""),
                "id": row.get("id", ""),
                "cui": row.get("cui", ""),
                "name": row.get("name", ""),
                "judgment": row.get("judgment", ""),
                "target": row.get("target", ""),
                "current_rank_score": row.get("f_rank_score", ""),
                "ml_score": f"{to_float(row.get('ml_score')):.6f}",
                "semantic_group": row.get("semantic_group", ""),
                "query": row.get("query", ""),
                "payload_path": row.get("payload_path", ""),
            }
        )
    return sorted(
        output,
        key=lambda row: (
            {"win": 0, "regression": 1, "loss": 2}.get(str(row.get("outcome")), 9),
            -abs(int(row.get("desired_delta") or 0)),
            str(row.get("id") or ""),
            int(to_float(row.get("current_rank"), 9999.0)),
        ),
    )


def shadow_regression_triage_rows(rank_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        [row for row in rank_rows if row.get("outcome") == "regression"],
        key=lambda row: (
            -abs(int(row.get("desired_delta") or 0)),
            str(row.get("triage_cause") or ""),
            str(row.get("id") or ""),
            int(to_float(row.get("current_rank"), 9999.0)),
        ),
    )


def h(value: object) -> str:
    return html.escape(str(value if value is not None else ""))


def metric_box(label: str, value: object, detail: str = "") -> str:
    return (
        "<div class=\"metric\">"
        f"<strong>{h(value)}</strong>"
        f"<span>{h(label)}</span>"
        f"<small>{h(detail)}</small>"
        "</div>"
    )


def render_table(rows: list[dict[str, object]], *, limit: int = 80) -> str:
    if not rows:
        return "<p class=\"empty\">No judged rows in this group.</p>"
    body = []
    for row in rows[:limit]:
        query = str(row.get("query") or "")
        if len(query) > 220:
            query = query[:217] + "..."
        body.append(
            "<tr>"
            f"<td>{h(row.get('id'))}</td>"
            f"<td><strong>{h(row.get('cui'))}</strong><br><span>{h(row.get('name'))}</span></td>"
            f"<td>{h(row.get('judgment'))}</td>"
            f"<td>{h(row.get('triage_cause'))}</td>"
            f"<td>{h(row.get('triage_reason'))}</td>"
            f"<td class=\"num\">{h(row.get('current_rank'))}</td>"
            f"<td class=\"num\">{h(row.get('ml_rank'))}</td>"
            f"<td class=\"num\">{h(row.get('desired_delta'))}</td>"
            f"<td class=\"num\">{h(row.get('current_rank_score'))}</td>"
            f"<td class=\"num\">{h(row.get('ml_score'))}</td>"
            f"<td>{h(query)}</td>"
            "</tr>"
        )
    if len(rows) > limit:
        body.append(
            f"<tr><td colspan=\"11\" class=\"empty\">Showing {limit} of {len(rows)} rows.</td></tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Query</th><th>CUI</th><th>Judgment</th><th>Triage</th><th>Reason</th><th>Current</th><th>ML</th>"
        "<th>Delta</th><th>Current score</th><th>ML score</th><th>Text</th>"
        "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def render_evidence_table(rows: list[dict[str, object]], *, limit: int = 80) -> str:
    if not rows:
        return "<p class=\"empty\">No evidence rows in this group.</p>"
    body = []
    for row in rows[:limit]:
        item_text = str(row.get("item_text") or "")
        if len(item_text) > 180:
            item_text = item_text[:177].rstrip() + "..."
        body.append(
            "<tr>"
            f"<td>{h(row.get('decision'))}</td>"
            f"<td>{h(row.get('scope'))}</td>"
            f"<td><strong>{h(row.get('source'))}</strong><br><span>{h(row.get('evidence_type'))}</span></td>"
            f"<td class=\"num\">{h(row.get('score'))}</td>"
            f"<td class=\"num\">{h(row.get('positive_observations'))}</td>"
            f"<td class=\"num\">{h(row.get('negative_observations'))}</td>"
            f"<td class=\"num\">{h(row.get('unjudged_observations'))}</td>"
            f"<td class=\"num\">{h(row.get('total_query_count'))}</td>"
            f"<td class=\"num\">{h(row.get('mean_rank'))}</td>"
            f"<td>{h(row.get('quality_flags'))}</td>"
            f"<td>{h(item_text)}</td>"
            "</tr>"
        )
    if len(rows) > limit:
        body.append(
            f"<tr><td colspan=\"11\" class=\"empty\">Showing {limit} of {len(rows)} rows.</td></tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Decision</th><th>Scope</th><th>Evidence</th><th>Score</th><th>Positive</th><th>Negative</th>"
        "<th>Unjudged</th><th>Queries</th><th>Mean rank</th><th>Flags</th><th>Text</th>"
        "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def render_evidence_examples_table(rows: list[dict[str, object]], *, limit: int = 120) -> str:
    if not rows:
        return "<p class=\"empty\">No examples were selected.</p>"
    body = []
    for row in rows[:limit]:
        query = str(row.get("query") or "")
        evidence_text = str(row.get("evidence_text") or "")
        if len(query) > 180:
            query = query[:177].rstrip() + "..."
        if len(evidence_text) > 220:
            evidence_text = evidence_text[:217].rstrip() + "..."
        body.append(
            "<tr>"
            f"<td>{h(row.get('decision'))}</td>"
            f"<td>{h(row.get('scope'))}</td>"
            f"<td>{h(row.get('query_id'))}</td>"
            f"<td class=\"num\">{h(row.get('rank'))}</td>"
            f"<td><strong>{h(row.get('cui'))}</strong><br><span>{h(row.get('name'))}</span></td>"
            f"<td>{h(row.get('judgment'))}</td>"
            f"<td>{h(row.get('source'))}<br><span>{h(row.get('evidence_type'))}</span></td>"
            f"<td>{h(query)}</td>"
            f"<td>{h(evidence_text)}</td>"
            "</tr>"
        )
    if len(rows) > limit:
        body.append(
            f"<tr><td colspan=\"9\" class=\"empty\">Showing {limit} of {len(rows)} examples.</td></tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Decision</th><th>Scope</th><th>Query</th><th>Rank</th><th>CUI</th><th>Judgment</th>"
        "<th>Evidence</th><th>Query text</th><th>Evidence text</th>"
        "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def write_evidence_html_report(
    path: Path,
    *,
    rows: list[dict[str, object]],
    examples: list[dict[str, object]],
    summary: dict[str, object],
    judgment_path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    by_decision = {
        decision: [row for row in rows if row.get("decision") == decision]
        for decision in (
            "promote_candidate",
            "demote_candidate",
            "quarantine_candidate",
            "neutral_mixed",
            "neutral_needs_heldout",
            "neutral_insufficient",
        )
    }
    decision_counts = summary.get("decision_counts") or {}
    policy_counts = summary.get("policy_counts") or {}
    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Evidence Promotion and Demotion Shadow Report</title>
  <style>
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #1f2933;
      background: #f6f8fa;
    }}
    header {{
      padding: 28px 32px 18px;
      background: #ffffff;
      border-bottom: 1px solid #d8dee4;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 28px 0 10px;
      font-size: 19px;
      letter-spacing: 0;
    }}
    p {{
      max-width: 1020px;
      line-height: 1.45;
    }}
    main {{
      padding: 20px 32px 36px;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px;
      max-width: 1180px;
    }}
    .metric {{
      background: #ffffff;
      border: 1px solid #d8dee4;
      border-radius: 8px;
      padding: 12px 14px;
    }}
    .metric strong {{
      display: block;
      font-size: 24px;
    }}
    .metric span {{
      display: block;
      font-size: 13px;
      color: #3d4a57;
    }}
    .metric small {{
      display: block;
      min-height: 18px;
      margin-top: 4px;
      color: #6b7280;
    }}
    code {{
      background: #edf2f7;
      padding: 1px 4px;
      border-radius: 4px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: #ffffff;
      border: 1px solid #d8dee4;
      border-radius: 8px;
      overflow: hidden;
    }}
    th, td {{
      padding: 8px 10px;
      border-bottom: 1px solid #edf2f7;
      text-align: left;
      vertical-align: top;
      font-size: 13px;
    }}
    th {{
      background: #e9eef5;
      color: #23303d;
      font-size: 12px;
      text-transform: uppercase;
    }}
    td span, .muted {{
      color: #667085;
    }}
    .num {{
      text-align: right;
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
    }}
    .empty {{
      color: #667085;
      background: #ffffff;
      border: 1px solid #d8dee4;
      border-radius: 8px;
      padding: 12px 14px;
    }}
  </style>
</head>
<body>
  <header>
    <h1>Evidence Promotion and Demotion Shadow Report</h1>
    <p class="muted">Shadow-only attribution over judged search payloads. It classifies evidence sources, source/type pairs, and item text signatures without changing production ranking. Unjudged hits are counted as unknown, not negative.</p>
  </header>
  <main>
    <section class="metrics">
      {metric_box("Evidence units", summary.get("evidence_units", 0))}
      {metric_box("Payloads", summary.get("payload_count", 0))}
      {metric_box("Hits inspected", summary.get("hit_count", 0), f"top {summary.get('top_k')} per query")}
      {metric_box("Unit observations", summary.get("evidence_unit_observations", 0))}
      {metric_box("Promote candidates", decision_counts.get("promote_candidate", 0))}
      {metric_box("Demote candidates", decision_counts.get("demote_candidate", 0))}
      {metric_box("Quarantine candidates", decision_counts.get("quarantine_candidate", 0))}
      {metric_box("Shadow policy rows", sum(int(value) for value in policy_counts.values()), ", ".join(f"{key}: {value}" for key, value in sorted(policy_counts.items())))}
      {metric_box("Neutral", sum(int(decision_counts.get(key, 0)) for key in ("neutral_mixed", "neutral_needs_heldout", "neutral_insufficient")))}
    </section>
    <p>
      Inputs: judgments <code>{h(rel_path(judgment_path))}</code>. Promote candidates require repeated judged-positive observations and no judged-negative observations. Demote candidates require repeated judged negatives and no judged positives. Quarantine candidates are mixed evidence with enough repeated negative signal to keep out of ranking until reviewed.
      The generated shadow policy is an offline review artifact and is not read by production ranking.
    </p>
    <h2>Promote Candidates</h2>
    {render_evidence_table(by_decision["promote_candidate"])}
    <h2>Demote Candidates</h2>
    {render_evidence_table(by_decision["demote_candidate"])}
    <h2>Quarantine Candidates</h2>
    {render_evidence_table(by_decision["quarantine_candidate"])}
    <h2>Mixed Neutral</h2>
    {render_evidence_table(by_decision["neutral_mixed"])}
    <h2>Needs Heldout</h2>
    {render_evidence_table(by_decision["neutral_needs_heldout"])}
    <h2>Insufficient Judged Signal</h2>
    {render_evidence_table(by_decision["neutral_insufficient"])}
    <h2>Examples</h2>
    {render_evidence_examples_table(examples)}
  </main>
</body>
</html>
"""
    path.write_text(html_text, encoding="utf-8")


def write_html_report(
    path: Path,
    *,
    rank_rows: list[dict[str, object]],
    model_info: dict[str, object],
    feature_path: Path,
    judgment_path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    counts = Counter(str(row.get("outcome") or "") for row in rank_rows)
    triage_counts = Counter(
        str(row.get("triage_cause") or "untriaged")
        for row in rank_rows
        if row.get("outcome") == "regression"
    )
    positives = [row for row in rank_rows if to_float(row.get("target")) > 0]
    negatives = [row for row in rank_rows if to_float(row.get("target")) < 0]
    current_positive_top10 = sum(int(to_float(row.get("current_rank"), 9999.0)) <= 10 for row in positives)
    ml_positive_top10 = sum(int(to_float(row.get("ml_rank"), 9999.0)) <= 10 for row in positives)
    current_negative_top10 = sum(int(to_float(row.get("current_rank"), 9999.0)) <= 10 for row in negatives)
    ml_negative_top10 = sum(int(to_float(row.get("ml_rank"), 9999.0)) <= 10 for row in negatives)
    by_outcome = {
        outcome: [row for row in rank_rows if row.get("outcome") == outcome]
        for outcome in ("win", "regression", "loss")
    }
    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Search Quality Shadow Reranker</title>
  <style>
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #1f2933;
      background: #f6f8fa;
    }}
    header {{
      padding: 28px 32px 18px;
      background: #ffffff;
      border-bottom: 1px solid #d8dee4;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 28px 0 10px;
      font-size: 19px;
      letter-spacing: 0;
    }}
    p {{
      max-width: 980px;
      line-height: 1.45;
    }}
    main {{
      padding: 20px 32px 36px;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px;
      max-width: 1180px;
    }}
    .metric {{
      background: #ffffff;
      border: 1px solid #d8dee4;
      border-radius: 8px;
      padding: 12px 14px;
    }}
    .metric strong {{
      display: block;
      font-size: 24px;
    }}
    .metric span {{
      display: block;
      font-size: 13px;
      color: #3d4a57;
    }}
    .metric small {{
      display: block;
      min-height: 18px;
      margin-top: 4px;
      color: #6b7280;
    }}
    code {{
      background: #edf2f7;
      padding: 1px 4px;
      border-radius: 4px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: #ffffff;
      border: 1px solid #d8dee4;
      border-radius: 8px;
      overflow: hidden;
    }}
    th, td {{
      padding: 8px 10px;
      border-bottom: 1px solid #edf2f7;
      text-align: left;
      vertical-align: top;
      font-size: 13px;
    }}
    th {{
      background: #e9eef5;
      color: #23303d;
      font-size: 12px;
      text-transform: uppercase;
    }}
    td span, .muted {{
      color: #667085;
    }}
    .num {{
      text-align: right;
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
    }}
    .empty {{
      color: #667085;
      background: #ffffff;
      border: 1px solid #d8dee4;
      border-radius: 8px;
      padding: 12px 14px;
    }}
  </style>
</head>
<body>
  <header>
    <h1>Search Quality Shadow Reranker</h1>
    <p class="muted">Shadow-only pairwise linear reranker. It compares existing rank against ML rank for judged CUIs and does not change the live search path.</p>
  </header>
  <main>
    <section class="metrics">
      {metric_box("Judged rows scored", len(rank_rows))}
      {metric_box("Wins", counts.get("win", 0), "positive up or negative down")}
      {metric_box("Regressions", counts.get("regression", 0), "positive down or negative up")}
      {metric_box("Losses", counts.get("loss", 0), "no useful rank movement")}
      {metric_box("Regression triage", ", ".join(f"{key}: {value}" for key, value in sorted(triage_counts.items())) or "0")}
      {metric_box("Positive judged @10", f"{current_positive_top10} -> {ml_positive_top10}")}
      {metric_box("Negative judged @10", f"{current_negative_top10} -> {ml_negative_top10}")}
      {metric_box("Training pairs", model_info.get("training_pairs", 0))}
      {metric_box("Features", model_info.get("feature_count", 0))}
    </section>
    <p>
      Inputs: judgments <code>{h(rel_path(judgment_path))}</code>, features
      <code>{h(rel_path(feature_path))}</code>. Win means the shadow rank moved in
      the desired direction. Regression means it moved the wrong way. Loss means
      the judged row did not move in the desired direction.
    </p>
    <h2>Wins</h2>
    {render_table(by_outcome["win"])}
    <h2>Regressions</h2>
    {render_table(by_outcome["regression"])}
    <h2>Losses</h2>
    {render_table(by_outcome["loss"])}
  </main>
</body>
</html>
"""
    path.write_text(html_text, encoding="utf-8")


def train_shadow_reranker(
    feature_path: Path,
    out_dir: Path,
    *,
    judgment_path: Path = DEFAULT_JUDGMENTS,
    epochs: int = 18,
    learning_rate: float = 0.03,
) -> dict[str, object]:
    rows, feature_names = read_feature_rows(feature_path)
    if not rows:
        raise ValueError(f"No feature rows found in {feature_path}")
    weights, model_info = train_pairwise_model(
        rows,
        feature_names,
        epochs=epochs,
        learning_rate=learning_rate,
    )
    ranked_rows = rank_rows_with_model(rows, feature_names, weights)
    judged_rank_rows = shadow_rank_rows(ranked_rows)

    out_dir.mkdir(parents=True, exist_ok=True)
    rank_rows_path = out_dir / "shadow_rank_rows.tsv"
    triage_rows_path = out_dir / "shadow_regression_triage.tsv"
    model_path = out_dir / "shadow_reranker_model.json"
    summary_path = out_dir / "summary.json"
    report_path = out_dir / "search_quality_shadow_reranker.html"
    write_tsv(rank_rows_path, judged_rank_rows, RANK_FIELDS)
    triage_rows = shadow_regression_triage_rows(judged_rank_rows)
    write_tsv(triage_rows_path, triage_rows, REGRESSION_TRIAGE_FIELDS)
    model_payload = {"model": model_info, "weights": dict(sorted(weights.items()))}
    model_path.write_text(json.dumps(model_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    counts = Counter(str(row.get("outcome") or "") for row in judged_rank_rows)
    triage_counts = Counter(str(row.get("triage_cause") or "") for row in triage_rows)
    summary = {
        **model_info,
        "judged_rows": len(judged_rank_rows),
        "outcome_counts": dict(sorted(counts.items())),
        "regression_triage_counts": dict(sorted(triage_counts.items())),
        "judgments_path": str(judgment_path),
        "features_path": str(feature_path),
        "rank_rows_path": str(rank_rows_path),
        "regression_triage_path": str(triage_rows_path),
        "report_path": str(report_path),
        "model_path": str(model_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_html_report(
        report_path,
        rank_rows=judged_rank_rows,
        model_info=model_info,
        feature_path=feature_path,
        judgment_path=judgment_path,
    )
    return summary


def discover_default_payloads() -> list[Path]:
    payloads = sorted((ROOT / "build" / "search_quality_experiments" / "runs").glob("*/payloads.jsonl"))
    selected: dict[str, tuple[float, Path]] = {}
    for path in payloads:
        ids = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for _index in range(5):
                    line = handle.readline()
                    if not line:
                        break
                    ids.append(str(json.loads(line).get("id") or ""))
        except (OSError, json.JSONDecodeError):
            continue
        family = ""
        if any(value.startswith("portal_") for value in ids):
            family = "portal"
        elif any(value.startswith("pubmed_") for value in ids):
            family = "pubmed"
        elif any(value.startswith("paragraph_") for value in ids):
            family = "paragraph"
        if not family:
            continue
        stamp = path.stat().st_mtime
        if family not in selected or stamp > selected[family][0]:
            selected[family] = (stamp, path)
    return [selected[key][1] for key in ("paragraph", "portal", "pubmed") if key in selected]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and evaluate a shadow search-quality reranker.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed = subparsers.add_parser("seed-judgments", help="Write the canonical search quality judgment TSV.")
    seed.add_argument("--out", type=Path, default=DEFAULT_JUDGMENTS)
    seed.add_argument("--paragraph-queries", type=Path, default=DEFAULT_PARAGRAPH_QUERIES)
    seed.add_argument("--clinical-queries", type=Path, default=DEFAULT_CLINICAL_QUERIES)
    seed.add_argument("--portal-queries", type=Path, default=DEFAULT_PORTAL_QUERIES)
    seed.add_argument("--useful-extras", type=Path, default=DEFAULT_USEFUL_EXTRAS)
    seed.add_argument("--precision-review", type=Path, default=DEFAULT_PRECISION_REVIEW)
    seed.add_argument("--pubmed-slice", type=Path, default=DEFAULT_PUBMED_SLICE)
    seed.add_argument("--pubmed-queries", type=Path, default=DEFAULT_PUBMED_QUERIES)

    extract = subparsers.add_parser("extract-features", help="Turn saved search payloads into feature rows.")
    extract.add_argument("--judgments", type=Path, default=DEFAULT_JUDGMENTS)
    extract.add_argument("--payloads", type=Path, nargs="*", default=None)
    extract.add_argument("--out", type=Path, default=DEFAULT_OUTPUT_DIR / "feature_rows.tsv")
    extract.add_argument("--unlabeled-weight", type=float, default=WEIGHT_BY_JUDGMENT["unlabeled"])
    extract.add_argument(
        "--evidence-policy",
        type=Path,
        default=None,
        help="Optional shadow evidence policy TSV to expose as aggregate reranker features.",
    )

    train = subparsers.add_parser("train-shadow", help="Train the shadow reranker and write report artifacts.")
    train.add_argument("--features", type=Path, default=DEFAULT_OUTPUT_DIR / "feature_rows.tsv")
    train.add_argument("--judgments", type=Path, default=DEFAULT_JUDGMENTS)
    train.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    train.add_argument("--epochs", type=int, default=18)
    train.add_argument("--learning-rate", type=float, default=0.03)

    evidence = subparsers.add_parser(
        "evidence-report",
        help="Evaluate evidence source/type/item promotion and demotion candidates.",
    )
    evidence.add_argument("--judgments", type=Path, default=DEFAULT_JUDGMENTS)
    evidence.add_argument("--payloads", type=Path, nargs="*", default=None)
    evidence.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    evidence.add_argument("--top-k", type=int, default=20)
    evidence.add_argument("--min-positive", type=int, default=3)
    evidence.add_argument("--min-negative", type=int, default=2)
    evidence.add_argument("--min-judged", type=int, default=2)
    evidence.add_argument("--heldout-pct", type=int, default=20)
    evidence.add_argument("--example-limit", type=int, default=200)

    run_all = subparsers.add_parser("run-all", help="Seed judgments, extract features, train, and report.")
    run_all.add_argument("--judgments", type=Path, default=DEFAULT_JUDGMENTS)
    run_all.add_argument("--payloads", type=Path, nargs="*", default=None)
    run_all.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    run_all.add_argument("--epochs", type=int, default=18)
    run_all.add_argument("--learning-rate", type=float, default=0.03)
    run_all.add_argument("--unlabeled-weight", type=float, default=WEIGHT_BY_JUDGMENT["unlabeled"])
    run_all.add_argument(
        "--evidence-policy",
        type=Path,
        default=None,
        help="Optional shadow evidence policy TSV to expose as aggregate reranker features.",
    )
    run_all.add_argument("--top-k", type=int, default=20)
    run_all.add_argument("--min-positive", type=int, default=3)
    run_all.add_argument("--min-negative", type=int, default=2)
    run_all.add_argument("--min-judged", type=int, default=2)
    run_all.add_argument("--heldout-pct", type=int, default=20)
    run_all.add_argument("--example-limit", type=int, default=200)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "seed-judgments":
        rows = seed_judgments(
            args.out,
            paragraph_queries=args.paragraph_queries,
            clinical_queries=args.clinical_queries,
            portal_queries=args.portal_queries,
            useful_extras=args.useful_extras,
            precision_review=args.precision_review,
            pubmed_slice=args.pubmed_slice,
            pubmed_queries=args.pubmed_queries,
        )
        print(f"Wrote {len(rows)} judgment rows to {args.out}")
        return 0

    if args.command == "extract-features":
        payloads = args.payloads if args.payloads is not None else discover_default_payloads()
        if not payloads:
            print("No payload paths supplied or discovered.", file=sys.stderr)
            return 2
        rows = extract_features(
            args.judgments,
            payloads,
            args.out,
            unlabeled_weight=args.unlabeled_weight,
            evidence_policy_path=args.evidence_policy,
        )
        print(f"Wrote {len(rows)} feature rows to {args.out}")
        return 0

    if args.command == "train-shadow":
        summary = train_shadow_reranker(
            args.features,
            args.out_dir,
            judgment_path=args.judgments,
            epochs=args.epochs,
            learning_rate=args.learning_rate,
        )
        print(f"Wrote shadow report to {summary['report_path']}")
        return 0

    if args.command == "evidence-report":
        payloads = args.payloads if args.payloads is not None else discover_default_payloads()
        if not payloads:
            print("No payload paths supplied or discovered.", file=sys.stderr)
            return 2
        summary = evaluate_evidence_promotion(
            args.judgments,
            payloads,
            args.out_dir,
            top_k=args.top_k,
            min_positive=args.min_positive,
            min_negative=args.min_negative,
            min_judged=args.min_judged,
            heldout_pct=args.heldout_pct,
            example_limit=args.example_limit,
        )
        print(f"Wrote evidence report to {summary['report_path']}")
        return 0

    if args.command == "run-all":
        judgments = seed_judgments(args.judgments)
        payloads = args.payloads if args.payloads is not None else discover_default_payloads()
        if not payloads:
            print("No payload paths supplied or discovered.", file=sys.stderr)
            return 2
        feature_path = args.out_dir / "feature_rows.tsv"
        feature_rows = extract_features(
            args.judgments,
            payloads,
            feature_path,
            unlabeled_weight=args.unlabeled_weight,
            evidence_policy_path=args.evidence_policy,
        )
        summary = train_shadow_reranker(
            feature_path,
            args.out_dir,
            judgment_path=args.judgments,
            epochs=args.epochs,
            learning_rate=args.learning_rate,
        )
        evidence_summary = evaluate_evidence_promotion(
            args.judgments,
            payloads,
            args.out_dir,
            top_k=args.top_k,
            min_positive=args.min_positive,
            min_negative=args.min_negative,
            min_judged=args.min_judged,
            heldout_pct=args.heldout_pct,
            example_limit=args.example_limit,
        )
        print(f"Wrote {len(judgments)} judgment rows to {args.judgments}")
        print(f"Wrote {len(feature_rows)} feature rows to {feature_path}")
        print(f"Wrote shadow report to {summary['report_path']}")
        print(f"Wrote evidence report to {evidence_summary['report_path']}")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
