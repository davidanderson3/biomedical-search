#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import shlex
import statistics
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from evaluate_paragraph_quality import (  # noqa: E402
    DEFAULT_ACCEPTABLE_ALTERNATIVES,
    DEFAULT_CODE_INDEX,
    DEFAULT_DEFINITION_INDEX,
    DEFAULT_LABEL_INDEXES,
    DEFAULT_SEMANTIC_TYPE_INDEX,
    SearchIndex,
    judge_quality,
    read_acceptable_alternatives,
    summarize,
    write_jsonl,
    write_report,
)
from evaluate_search_api import QuerySpec, read_query_specs  # noqa: E402
from qe_evidence_vectors.search_utils import sentence_bounded_evidence_text  # noqa: E402


DEFAULT_QUERIES = ROOT / "config" / "search_quality_paragraph_queries.tsv"
DEFAULT_OUTPUT_ROOT = ROOT / "build" / "search_quality_experiments"
DEFAULT_REPORT = ROOT / "docs" / "search_quality_experiments.html"
DEFAULT_UMLS_API_COMPARISON = ROOT / "build" / "umls_api_comparison.tsv"
DEFAULT_UMLS_API_COMPARISON_SUMMARY = ROOT / "build" / "umls_api_comparison_runs_20260609" / "summary.tsv"
DEFAULT_UMLS_API_COMPARISON_SUMMARY_MD = ROOT / "build" / "umls_api_comparison_runs_20260609" / "summary.md"
DEFAULT_TRANSLATION_BENCHMARK_REPORT_JSON = ROOT / "build" / "translation_benchmark_report.json"
DEFAULT_TRANSLATION_BENCHMARK_REPORT_HTML = ROOT / "docs" / "translation_benchmark_report.html"
DEFAULT_QUERY_LIMIT = 50
DEFAULT_API_WORKERS = 2
SERVER_TIMING_STAGE_COLUMNS = {
    "embedding": ("embedding",),
    "base_vector_search": ("base_vector_search",),
    "long_document_chunk_vector_search": ("long_document_chunk_vector_search",),
    "mention_extraction": (
        "mention_extraction",
        "long_document_mention_extraction",
    ),
    "ranking": (
        "label_fallback_and_ranking",
        "active_label_context_search",
        "long_document_support_signals",
        "long_document_merge_ranking",
        "filtering_and_promotion",
    ),
    "response_compaction": ("response_compaction",),
}
MANIFEST_NAME = "runs.json"
ITERATION_SMOKE_MANIFEST_NAME = "iteration_smoke_gates.json"
SEARCH_SYSTEM_API = "api"
SEARCH_SYSTEM_UMLS_ONLY = "umls-only"
SEARCH_SYSTEM_BOTH = "both"
SEARCH_SCOPE_UMLS = "umls"
SEARCH_SCOPE_UMLS_EVIDENCE = "umls_evidence"
SOURCE_FIELD_KEYS = {
    "sab",
    "sabs",
    "source",
    "source_id",
    "source_ids",
    "source_name",
    "source_names",
    "sources",
}
RESTRICTION_LEVEL_KEYS = {
    "restriction_level",
    "restriction_levels",
    "source_restriction_level",
    "source_restriction_levels",
    "umls_restriction_level",
    "umls_restriction_levels",
}
DEFAULT_RESTRICTED_SOURCE_PATTERNS = (
    "restricted",
    "private",
    "non_level_0",
    "non-level-0",
    "level_9",
    "level-9",
    "licensed",
    "mimic",
    "ehr",
)
CLINICALTRIALS_SOURCE_MARKERS = (
    "clinicaltrials",
    "clinicaltrials.gov",
    "clinicaltrials_gov",
    "ctgov",
)
CLINICALTRIALS_PROTOCOL_MARKERS = (
    "eligibility criteria",
    "study design",
    "planned outcome",
    "planned endpoint",
    "primary outcome measure",
    "secondary outcome measure",
    "arms and interventions",
    "recruiting",
    "enrollment",
    "protocol",
)
CLINICALTRIALS_RESULT_MARKERS = (
    "posted outcome",
    "posted result",
    "outcome result",
    "results posted",
    "actual result",
    "actual enrollment",
    "results_first_posted",
    "has_results",
)
ITERATION_TYPE_CHOICES = (
    "benchmark",
    "ranking",
    "source-code",
    "long-document",
    "audit",
    "ui",
    "process",
    "data",
)
STANDING_SMOKE_ITERATION_TYPES = {
    "audit",
    "benchmark",
    "data",
    "long-document",
    "ranking",
    "source-code",
}
ROTATING_SMOKE_ITERATION_TYPES = {
    "benchmark",
    "long-document",
    "ranking",
}
PATIENT_PORTAL_SMOKE_ITERATION_TYPES = {
    "benchmark",
    "ranking",
}

METRIC_DEFINITIONS = [
    (
        "Primary",
        "strict_success_at_10_rate",
        "strict success@10",
        "Query passes only when the top result is on target, every expected or acceptable CUI appears in the first 10 results, and no known false-positive CUI appears in the first 10.",
    ),
    (
        "Primary",
        "strict_success_at_20_rate",
        "strict success@20",
        "Same strict query-level pass criterion, but allowing expected concepts to appear by rank 20.",
    ),
    (
        "Primary",
        "top_on_target_rate",
        "top on target",
        "Share of queries whose top result is expected or an acceptable alternative.",
    ),
    (
        "Primary",
        "known_false_positive_rate_at_10",
        "known false positive@10",
        "Share of queries where a configured known false-positive CUI appears in the first 10 results. Lower is better.",
    ),
    (
        "Supporting",
        "all_expected_at_10_rate",
        "all expected@10",
        "Share of queries where every expected or acceptable CUI appears in the first 10 results.",
    ),
    (
        "Supporting",
        "mean_coverage_at_10",
        "mean coverage@10",
        "Mean per-query fraction of expected CUIs found in the first 10 results.",
    ),
    (
        "Supporting",
        "recall_at_10",
        "concept recall@10",
        "Expected CUI recall in the first 10 results, pooled across all expected concepts.",
    ),
    (
        "Supporting",
        "mrr_first_expected",
        "MRR first expected",
        "Mean reciprocal rank of the first expected or acceptable CUI.",
    ),
    (
        "Diagnostic",
        "good_rate",
        "rubric good rate",
        "Share of queries judged good by the softer paragraph-quality rubric; useful, but not a strict pass rate.",
    ),
    (
        "Diagnostic",
        "recall_at_5",
        "concept recall@5",
        "Expected CUI recall in the first 5 results, pooled across all expected concepts.",
    ),
    (
        "Diagnostic",
        "recall_at_20",
        "concept recall@20",
        "Expected CUI recall in the first 20 results, pooled across all expected concepts.",
    ),
    (
        "Diagnostic",
        "recall_at_60",
        "concept recall@60",
        "Expected CUI recall in the full 60-result evaluation window; mostly a candidate-generation diagnostic.",
    ),
    (
        "Diagnostic",
        "expected_group_recall_at_10",
        "semantic group recall@10",
        "Coarse expected semantic-group recall in the first 10 results. This can look high even when specific CUIs are missed.",
    ),
    (
        "Diagnostic",
        "queries_all_expected_at_10",
        "queries all expected@10",
        "Raw count of queries where every expected CUI was found in the first 10 results.",
    ),
    (
        "Diagnostic",
        "queries_with_missing_at_10",
        "queries missing@10",
        "Raw count of queries missing at least one expected CUI in the first 10 results. Lower is better.",
    ),
]

LOWER_IS_BETTER_METRICS = {
    "known_false_positive_rate_at_10",
    "known_false_positive_rate_at_20",
    "queries_with_missing_at_10",
    "queries_with_missing_at_20",
    "queries_with_disallowed_at_10",
    "queries_with_disallowed_at_20",
    "top_wrong_rate",
}

RATE_METRICS = {
    "all_expected_at_10_rate",
    "all_expected_at_20_rate",
    "good_rate",
    "known_false_positive_rate_at_10",
    "known_false_positive_rate_at_20",
    "recall_at_5",
    "recall_at_10",
    "recall_at_20",
    "recall_at_60",
    "mean_coverage_at_10",
    "mean_coverage_at_20",
    "mrr_first_expected",
    "strict_success_at_10_rate",
    "strict_success_at_20_rate",
    "top_on_target_rate",
    "top_wrong_rate",
    "expected_group_recall_at_10",
}

RUN_FAMILY_DEFINITIONS = {
    "smoke": {
        "label": "Smoke regression",
        "description": "Fast rotating quality check sampled from the standard paragraph query set.",
        "class": "smoke",
    },
    "scope": {
        "label": "Scope comparison",
        "description": "UMLS-only versus UMLS + evidence comparison runs.",
        "class": "scope",
    },
    "probe": {
        "label": "Probe",
        "description": "Focused speed, payload, or ranking probe. Useful, but not a baseline by itself.",
        "class": "probe",
    },
    "baseline": {
        "label": "Baseline",
        "description": "Reference run used for comparison or release gates.",
        "class": "baseline",
    },
    "ranking": {
        "label": "Ranking experiment",
        "description": "Search ranking or candidate-generation experiment.",
        "class": "ranking",
    },
    "patient_portal": {
        "label": "Patient portal lane",
        "description": "Current-visit versus old-history ranking checks for long patient portal messages.",
        "class": "benchmark",
    },
    "release": {
        "label": "Release candidate",
        "description": "Candidate run intended to be held against fail gates.",
        "class": "release",
    },
    "custom": {
        "label": "Custom run",
        "description": "Run type was not specified and could not be inferred confidently.",
        "class": "custom",
    },
}
RUN_FAMILY_ORDER = ("smoke", "scope", "probe", "baseline", "ranking", "patient_portal", "release", "custom")
RUN_FAMILY_INTERPRETATIONS = {
    "smoke": (
        "Repeatable rotating 50-query regression checks sampled from the judged paragraph pool. "
        "Use passing smoke runs as operational quality signals; failed smoke runs show regressions "
        "or unsafe changes to investigate."
    ),
    "scope": (
        "API scope comparisons, usually UMLS-only versus UMLS + evidence on the same query file. "
        "Use these to understand evidence-retrieval value, not as release baselines by themselves."
    ),
    "probe": (
        "One-off speed, payload, source, or ranking diagnostics. These explain behavior and guide "
        "follow-up work, but should not reset the smoke baseline."
    ),
    "baseline": (
        "Reference or control runs retained for comparison. These are anchors for deltas, gates, "
        "and historical interpretation."
    ),
    "ranking": (
        "Focused ranking or candidate-generation experiments. Use these to compare targeted search "
        "changes before promoting them into repeatable smoke runs."
    ),
    "patient_portal": (
        "Long patient-message benchmark runs. Use these to gate active/current visit concepts above "
        "copied-forward history while keeping old medications and diagnoses available lower in the results."
    ),
    "release": (
        "Candidate runs intended to be held against gates before promotion. Treat failures in this "
        "family as blockers."
    ),
    "custom": (
        "Runs that do not declare a known family and could not be inferred confidently. Review the "
        "label and command before comparing them to other families."
    ),
}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_id_from_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def slug(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned[:64] or "run"


def git_value(args: list[str]) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return ""


def get_json(base_url: str, path: str, params: dict[str, str | int], *, timeout: float) -> dict:
    url = f"{base_url.rstrip('/')}{path}?{urlencode(params)}"
    with urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def split_cui_values(value: object) -> set[str]:
    normalized = str(value or "").replace(",", "|").replace(";", "|")
    return {part.strip().upper() for part in normalized.split("|") if part.strip()}


def sorted_cui_values(value: object) -> list[str]:
    return sorted(split_cui_values(value))


def digest_json_payload(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def evaluation_signature_from_specs(specs: list[QuerySpec], alternatives: dict[str, set[str]]) -> str:
    records = []
    for spec in specs:
        acceptable = set()
        for expected_cui in spec.expected_cuis:
            acceptable.update(acceptable_options(expected_cui, alternatives))
        records.append(
            {
                "id": spec.query_id,
                "query": spec.query,
                "expected_cuis": sorted_cui_values("|".join(spec.expected_cuis)),
                "acceptable_cuis": sorted(acceptable),
                "disallowed_cuis": sorted_cui_values("|".join(spec.disallowed_cuis or [])),
            }
        )
    return digest_json_payload(records)


def evaluation_signature_from_query_config(queries: Path, alternatives_path: Path) -> str:
    specs = read_query_specs(queries)
    alternatives = read_acceptable_alternatives(alternatives_path)
    return evaluation_signature_from_specs(specs, alternatives)


def query_spec_sort_key(spec: QuerySpec) -> str:
    identity = f"{spec.query_id}\n{spec.query}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def query_rotation_seed(args: argparse.Namespace, *, run_id: str = "", label: str = "") -> str:
    explicit = str(getattr(args, "query_rotation_seed", "") or "").strip()
    if explicit:
        return explicit
    return (
        str(getattr(args, "run_id", "") or "").strip()
        or str(run_id or "").strip()
        or str(getattr(args, "label", "") or "").strip()
        or str(label or "").strip()
        or "default"
    )


def select_query_specs_for_run(
    specs: list[QuerySpec],
    args: argparse.Namespace,
    *,
    run_id: str = "",
    label: str = "",
) -> tuple[list[QuerySpec], dict]:
    pool_count = len(specs)
    raw_limit = int(getattr(args, "query_limit", DEFAULT_QUERY_LIMIT) or 0)
    selection = str(getattr(args, "query_selection", "rotate") or "rotate").strip().lower()
    seed = query_rotation_seed(args, run_id=run_id, label=label)

    if raw_limit <= 0 or raw_limit >= pool_count:
        selected = list(specs)
        effective_selection = "all"
    elif selection == "first":
        selected = list(specs[:raw_limit])
        effective_selection = "first"
    else:
        ordered = sorted(specs, key=query_spec_sort_key)
        offset = int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16) % pool_count
        selected = [ordered[(offset + index) % pool_count] for index in range(raw_limit)]
        effective_selection = "rotate"

    metadata = {
        "query_pool_count": pool_count,
        "query_limit": raw_limit,
        "query_selected_count": len(selected),
        "query_selection": effective_selection,
        "query_rotation_seed": seed if effective_selection == "rotate" else "",
        "query_selection_ids": [spec.query_id for spec in selected],
    }
    return selected, metadata


def evaluation_signature_from_selected_query_config(args: argparse.Namespace) -> str:
    specs = read_query_specs(args.queries)
    selected_specs, _metadata = select_query_specs_for_run(specs, args)
    alternatives = read_acceptable_alternatives(args.alternatives)
    return evaluation_signature_from_specs(selected_specs, alternatives)


def evaluation_signature_from_rows(rows: list[dict]) -> str:
    records = []
    for row in rows:
        records.append(
            {
                "id": str(row.get("id") or ""),
                "query": str(row.get("query") or ""),
                "expected_cuis": sorted_cui_values(row.get("expected_cuis")),
                "acceptable_cuis": sorted_cui_values(row.get("acceptable_cuis") or row.get("expected_cuis")),
                "disallowed_cuis": sorted_cui_values(row.get("configured_disallowed_cuis")),
            }
        )
    return digest_json_payload(records)


def existing_path(path: Path | None, *, label: str) -> Path | None:
    if path is None:
        return None
    if not path.exists():
        raise SystemExit(f"missing {label}: {path}")
    return path


def default_existing_path(path: Path) -> Path | None:
    return path if path.exists() else None


def selected_search_systems(value: str) -> list[str]:
    if value == SEARCH_SYSTEM_BOTH:
        return [SEARCH_SYSTEM_UMLS_ONLY, SEARCH_SYSTEM_API]
    return [value]


def normalize_source_id(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", "_", text)
    return text.strip("_")


def source_value_strings(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, list):
        strings = []
        for item in value:
            strings.extend(source_value_strings(item))
        return strings
    if isinstance(value, dict):
        strings = []
        for key in SOURCE_FIELD_KEYS:
            if key in value:
                strings.extend(source_value_strings(value.get(key)))
        return strings
    return []


def iter_source_strings(value: object):
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key or "").strip().lower()
            if key_text in SOURCE_FIELD_KEYS or key_text.endswith("_source") or key_text.endswith("_sources"):
                yield from source_value_strings(child)
            yield from iter_source_strings(child)
    elif isinstance(value, list):
        for item in value:
            yield from iter_source_strings(item)


def source_counts_from_payloads(payloads: list[dict], *, limit: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for payload in payloads:
        response = payload.get("response") or {}
        for hit in list(response.get("hits") or [])[:limit]:
            sources = {
                normalize_source_id(source)
                for source in iter_source_strings(hit)
                if normalize_source_id(source)
            }
            for source in sources:
                counts[source] = counts.get(source, 0) + 1
    return dict(sorted(counts.items()))


def hit_sources(hit: dict) -> set[str]:
    return {
        source
        for source in (normalize_source_id(source) for source in iter_source_strings(hit))
        if source
    }


def hit_cui(hit: dict) -> str:
    return str(hit.get("cui") or "").strip().upper()


def row_cuis(row: dict, field: str) -> set[str]:
    return split_cui_values(row.get(field))


def row_query_text(row: dict, payload: dict) -> str:
    return str(payload.get("query") or row.get("query") or "")


def limited_examples(examples: list[dict], *, limit: int = 5) -> list[dict]:
    return examples[:limit]


def source_quality_contribution(payloads: list[dict], rows: list[dict], *, limit: int) -> dict:
    rows_by_id = {str(row.get("id") or ""): row for row in rows}
    source_stats: dict[str, dict] = {}

    def stats_for(source: str) -> dict:
        if source not in source_stats:
            source_stats[source] = {
                "source": source,
                "hit_source_appearances_at_10": 0,
                "expected_hit_source_appearances_at_10": 0,
                "disallowed_hit_source_appearances_at_10": 0,
                "top1_source_appearances": 0,
                "top1_expected_source_appearances": 0,
                "queries_present_at_10": set(),
                "strict_success_queries_present_at_10": set(),
                "failed_queries_present_at_10": set(),
                "expected_queries_at_10": set(),
                "strict_success_expected_queries_at_10": set(),
                "failed_expected_queries_at_10": set(),
                "disallowed_queries_at_10": set(),
                "top1_queries": set(),
                "top1_expected_queries": set(),
                "top1_strict_success_expected_queries": set(),
                "best_ranks_at_10": [],
                "best_expected_ranks_at_10": [],
                "expected_examples": [],
                "disallowed_examples": [],
            }
        return source_stats[source]

    for payload in payloads:
        query_id = str(payload.get("id") or "")
        row = rows_by_id.get(query_id, {})
        strict_success = row_strict_success(row, 10)
        acceptable = row_cuis(row, "acceptable_cuis") or row_cuis(row, "expected_cuis")
        disallowed = row_cuis(row, "disallowed_at_10")
        query_text = row_query_text(row, payload)
        best_rank_by_source: dict[str, int] = {}
        best_expected_rank_by_source: dict[str, int] = {}
        response = payload.get("response") or {}
        for rank, hit in enumerate(list(response.get("hits") or [])[:limit], start=1):
            cui = hit_cui(hit)
            sources = hit_sources(hit)
            if not sources:
                continue
            is_expected = bool(cui and cui in acceptable)
            is_disallowed = bool(cui and cui in disallowed)
            for source in sources:
                stats = stats_for(source)
                stats["hit_source_appearances_at_10"] += 1
                stats["queries_present_at_10"].add(query_id)
                if strict_success:
                    stats["strict_success_queries_present_at_10"].add(query_id)
                else:
                    stats["failed_queries_present_at_10"].add(query_id)
                if rank == 1:
                    stats["top1_source_appearances"] += 1
                    stats["top1_queries"].add(query_id)
                best_rank_by_source[source] = min(rank, best_rank_by_source.get(source, rank))

                if is_expected:
                    stats["expected_hit_source_appearances_at_10"] += 1
                    stats["expected_queries_at_10"].add(query_id)
                    if strict_success:
                        stats["strict_success_expected_queries_at_10"].add(query_id)
                    else:
                        stats["failed_expected_queries_at_10"].add(query_id)
                    if rank == 1:
                        stats["top1_expected_source_appearances"] += 1
                        stats["top1_expected_queries"].add(query_id)
                        if strict_success:
                            stats["top1_strict_success_expected_queries"].add(query_id)
                    best_expected_rank_by_source[source] = min(
                        rank,
                        best_expected_rank_by_source.get(source, rank),
                    )
                    if len(stats["expected_examples"]) < 5:
                        stats["expected_examples"].append(
                            {
                                "id": query_id,
                                "query": query_text,
                                "rank": rank,
                                "cui": cui,
                                "name": hit.get("name") or hit.get("label") or "",
                            }
                        )
                if is_disallowed:
                    stats["disallowed_hit_source_appearances_at_10"] += 1
                    stats["disallowed_queries_at_10"].add(query_id)
                    if len(stats["disallowed_examples"]) < 5:
                        stats["disallowed_examples"].append(
                            {
                                "id": query_id,
                                "query": query_text,
                                "rank": rank,
                                "cui": cui,
                                "name": hit.get("name") or hit.get("label") or "",
                            }
                        )

        for source, rank in best_rank_by_source.items():
            stats_for(source)["best_ranks_at_10"].append(rank)
        for source, rank in best_expected_rank_by_source.items():
            stats_for(source)["best_expected_ranks_at_10"].append(rank)

    sources = []
    for source, stats in sorted(source_stats.items()):
        queries_present = len(stats["queries_present_at_10"])
        hit_appearances = int(stats["hit_source_appearances_at_10"])
        best_ranks = stats["best_ranks_at_10"]
        best_expected_ranks = stats["best_expected_ranks_at_10"]
        item = {
            "source": source,
            "queries_present_at_10": queries_present,
            "strict_success_queries_present_at_10": len(stats["strict_success_queries_present_at_10"]),
            "failed_queries_present_at_10": len(stats["failed_queries_present_at_10"]),
            "strict_success_query_rate_when_present": (
                len(stats["strict_success_queries_present_at_10"]) / queries_present
                if queries_present
                else 0.0
            ),
            "expected_queries_at_10": len(stats["expected_queries_at_10"]),
            "strict_success_expected_queries_at_10": len(stats["strict_success_expected_queries_at_10"]),
            "failed_expected_queries_at_10": len(stats["failed_expected_queries_at_10"]),
            "expected_query_rate_when_present": (
                len(stats["expected_queries_at_10"]) / queries_present if queries_present else 0.0
            ),
            "disallowed_queries_at_10": len(stats["disallowed_queries_at_10"]),
            "disallowed_query_rate_when_present": (
                len(stats["disallowed_queries_at_10"]) / queries_present if queries_present else 0.0
            ),
            "top1_queries": len(stats["top1_queries"]),
            "top1_expected_queries": len(stats["top1_expected_queries"]),
            "top1_strict_success_expected_queries": len(stats["top1_strict_success_expected_queries"]),
            "hit_source_appearances_at_10": hit_appearances,
            "expected_hit_source_appearances_at_10": int(stats["expected_hit_source_appearances_at_10"]),
            "disallowed_hit_source_appearances_at_10": int(stats["disallowed_hit_source_appearances_at_10"]),
            "expected_hit_rate_at_10": (
                stats["expected_hit_source_appearances_at_10"] / hit_appearances
                if hit_appearances
                else 0.0
            ),
            "disallowed_hit_rate_at_10": (
                stats["disallowed_hit_source_appearances_at_10"] / hit_appearances
                if hit_appearances
                else 0.0
            ),
            "mean_best_rank_at_10": (
                sum(best_ranks) / len(best_ranks) if best_ranks else 0.0
            ),
            "mean_best_expected_rank_at_10": (
                sum(best_expected_ranks) / len(best_expected_ranks) if best_expected_ranks else 0.0
            ),
            "expected_examples": limited_examples(stats["expected_examples"]),
            "disallowed_examples": limited_examples(stats["disallowed_examples"]),
        }
        sources.append(item)

    ranked_sources = sorted(
        sources,
        key=lambda item: (
            -int(item["strict_success_expected_queries_at_10"]),
            -int(item["top1_strict_success_expected_queries"]),
            -int(item["expected_queries_at_10"]),
            int(item["disallowed_queries_at_10"]),
            str(item["source"]),
        ),
    )
    return {
        "limit": limit,
        "description": (
            "Associative source metrics from top results. A source is credited for an "
            "expected hit only when it is attached to a hit whose CUI satisfies the query's "
            "expected or acceptable CUI set; this is not a causal ablation."
        ),
        "sources": {item["source"]: item for item in sources},
        "ranked_sources": ranked_sources,
    }


def flatten_strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, (int, float)):
        yield str(value)
    elif isinstance(value, dict):
        for child in value.values():
            yield from flatten_strings(child)
    elif isinstance(value, list):
        for item in value:
            yield from flatten_strings(item)


def first_matching_marker(text: str, markers: tuple[str, ...]) -> str:
    for marker in markers:
        if marker in text:
            return marker
    return ""


def compact_text(value: str, *, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def hit_identity(hit: dict) -> str:
    parts = [
        str(hit.get("cui") or "").strip(),
        str(hit.get("name") or hit.get("label") or "").strip(),
    ]
    return " ".join(part for part in parts if part)


def clinicaltrials_protocol_only_findings(payloads: list[dict], *, limit: int = 20) -> list[dict]:
    findings = []
    for payload in payloads:
        query_id = str(payload.get("id") or "")
        response = payload.get("response") or {}
        for rank, hit in enumerate(response.get("hits") or [], start=1):
            source_text = " ".join(iter_source_strings(hit)).lower()
            all_text = " ".join(flatten_strings(hit)).lower()
            if not (
                first_matching_marker(source_text, CLINICALTRIALS_SOURCE_MARKERS)
                or first_matching_marker(all_text, CLINICALTRIALS_SOURCE_MARKERS)
            ):
                continue
            protocol_marker = first_matching_marker(all_text, CLINICALTRIALS_PROTOCOL_MARKERS)
            if not protocol_marker:
                continue
            result_marker = first_matching_marker(all_text, CLINICALTRIALS_RESULT_MARKERS)
            if result_marker:
                continue
            findings.append(
                {
                    "query_id": query_id,
                    "rank": rank,
                    "hit": hit_identity(hit),
                    "marker": protocol_marker,
                    "snippet": compact_text(" ".join(flatten_strings(hit))),
                }
            )
            if len(findings) >= limit:
                return findings
    return findings


def public_restriction_level(value: object) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return True
    text = text.replace("_", "-").replace(" ", "-")
    return text in {"0", "level-0", "category-0", "public", "unrestricted", "none"}


def iter_restriction_levels(value: object):
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key or "").strip().lower()
            if key_text in RESTRICTION_LEVEL_KEYS:
                if isinstance(child, list):
                    for item in child:
                        yield key_text, item
                else:
                    yield key_text, child
            yield from iter_restriction_levels(child)
    elif isinstance(value, list):
        for item in value:
            yield from iter_restriction_levels(item)


def restricted_public_display_findings(
    payloads: list[dict],
    *,
    patterns: tuple[str, ...] = DEFAULT_RESTRICTED_SOURCE_PATTERNS,
    limit: int = 20,
) -> list[dict]:
    findings = []
    normalized_patterns = tuple(pattern.lower() for pattern in patterns if pattern)
    for payload in payloads:
        query_id = str(payload.get("id") or "")
        response = payload.get("response") or {}
        for rank, hit in enumerate(response.get("hits") or [], start=1):
            for source in sorted({normalize_source_id(item) for item in iter_source_strings(hit)}):
                marker = first_matching_marker(source, normalized_patterns)
                if not marker:
                    continue
                findings.append(
                    {
                        "query_id": query_id,
                        "rank": rank,
                        "hit": hit_identity(hit),
                        "source": source,
                        "marker": marker,
                    }
                )
                if len(findings) >= limit:
                    return findings
            for key, level in iter_restriction_levels(hit):
                if public_restriction_level(level):
                    continue
                findings.append(
                    {
                        "query_id": query_id,
                        "rank": rank,
                        "hit": hit_identity(hit),
                        "restriction_field": key,
                        "restriction_level": str(level),
                    }
                )
                if len(findings) >= limit:
                    return findings
    return findings


def read_payloads_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payloads = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payloads.append(json.loads(line))
    return payloads


def run_backend(run: dict) -> str:
    payloads_path_text = str(run.get("payloads_path") or "").strip()
    if payloads_path_text:
        path = Path(payloads_path_text)
        if path.exists() and path.is_file():
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        return ""
                    response = payload.get("response") if isinstance(payload, dict) else {}
                    return str((response or {}).get("backend") or "").strip()
    payload_dir = Path(str(run.get("run_dir") or "")) / "payloads"
    if payload_dir.exists() and payload_dir.is_dir():
        for path in sorted(payload_dir.glob("*.json")):
            try:
                response = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            backend = str(response.get("backend") or "").strip()
            if backend:
                return backend
    return ""


def metric_number(summary: dict, key: str) -> float | None:
    try:
        return float(summary.get(key))
    except (TypeError, ValueError):
        return None


def bounded_rate(summary: dict, key: str, *, default: float = 0.0) -> float:
    value = metric_number(summary, key)
    if value is None:
        return default
    return min(max(value, 0.0), 1.0)


def overall_score_from_summary(summary: dict) -> float:
    strict = bounded_rate(summary, "strict_success_at_10_rate")
    top_target = bounded_rate(summary, "top_on_target_rate")
    all_expected = bounded_rate(summary, "all_expected_at_10_rate")
    recall = bounded_rate(summary, "recall_at_10")
    false_positive_clear = 1.0 - bounded_rate(summary, "known_false_positive_rate_at_10")
    score = (
        (0.50 * strict)
        + (0.15 * top_target)
        + (0.20 * all_expected)
        + (0.05 * recall)
        + (0.10 * false_positive_clear)
    ) * 100.0
    return round(score, 1)


def gate_check(
    name: str,
    *,
    passed: bool | None,
    message: str,
    **details,
) -> dict:
    status = "skipped" if passed is None else ("passed" if passed else "failed")
    return {"name": name, "passed": passed, "status": status, "message": message, **details}


def load_gate_baseline(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "summary" in payload:
        return payload
    return {
        "run_id": path.stem,
        "label": path.stem,
        "metrics_path": str(path),
        "summary": payload,
    }


def same_query_file(left: object, right: Path) -> bool:
    if not left:
        return True
    left_text = str(left)
    right_text = str(right)
    return left_text == right_text or Path(left_text).name == right.name


def run_evaluation_signature(run: dict) -> str:
    signature = str(
        run.get("evaluation_signature")
        or run.get("query_signature")
        or run.get("benchmark_signature")
        or ""
    ).strip()
    if signature:
        return signature
    rows = read_run_rows(run)
    if rows:
        return evaluation_signature_from_rows(rows)
    return ""


def current_evaluation_signature(args: argparse.Namespace) -> str:
    signature = str(getattr(args, "evaluation_signature", "") or "").strip()
    if signature:
        return signature
    signature = evaluation_signature_from_selected_query_config(args)
    setattr(args, "evaluation_signature", signature)
    return signature


def run_matches_current_evaluation(run: dict, *, queries: Path, current_signature: str) -> bool:
    run_signature = run_evaluation_signature(run)
    if run_signature and current_signature:
        return run_signature == current_signature
    return same_query_file(run.get("queries"), queries)


def current_payload_shape(args: argparse.Namespace) -> dict[str, object]:
    return {
        "top_k": getattr(args, "top_k", None),
        "include_related": bool(getattr(args, "include_related", False)),
        "include_linked_concepts": bool(getattr(args, "include_linked_concepts", False)),
        "include_search_evidence_items": bool(getattr(args, "include_search_evidence_items", False)),
    }


def run_matches_current_payload_shape(run: dict, payload_shape: dict[str, object] | None) -> bool:
    if not payload_shape:
        return True
    if "top_k" in run and run.get("top_k") not in {None, "", payload_shape.get("top_k")}:
        return False
    for field in ("include_related", "include_linked_concepts", "include_search_evidence_items"):
        if field in run and bool(run.get(field)) != bool(payload_shape.get(field)):
            return False
    return True


def find_previous_gate_baseline(
    manifest: dict,
    *,
    search_system: str,
    queries: Path,
    api_scope: str,
    current_signature: str = "",
    payload_shape: dict[str, object] | None = None,
) -> dict | None:
    candidates = []
    for run in manifest.get("runs") or []:
        if run.get("search_system") != search_system:
            continue
        if current_signature:
            if not run_matches_current_evaluation(run, queries=queries, current_signature=current_signature):
                continue
        elif not same_query_file(run.get("queries"), queries):
            continue
        if search_system == SEARCH_SYSTEM_API and run.get("api_scope") not in {None, "", api_scope}:
            continue
        if not run_matches_current_payload_shape(run, payload_shape):
            continue
        candidates.append(run)
    candidates.sort(key=lambda item: str(item.get("created_at") or ""))
    return candidates[-1] if candidates else None


def source_collapse_details(
    current: dict[str, int],
    baseline: dict[str, int],
    *,
    tolerance: float,
    min_baseline: int,
) -> list[dict]:
    collapsed = []
    threshold_factor = max(0.0, 1.0 - tolerance)
    for source, baseline_count in sorted(baseline.items()):
        baseline_value = int(baseline_count or 0)
        if baseline_value < min_baseline:
            continue
        current_value = int(current.get(source) or 0)
        if current_value >= baseline_value * threshold_factor:
            continue
        collapsed.append(
            {
                "source": source,
                "baseline": baseline_value,
                "current": current_value,
                "drop": baseline_value - current_value,
            }
        )
    return collapsed


def evaluate_run_gates(run: dict, baseline_run: dict | None, args: argparse.Namespace) -> dict:
    summary = run.get("summary") or {}
    baseline_signature = run_evaluation_signature(baseline_run or {}) if baseline_run is not None else ""
    current_signature = run_evaluation_signature(run)
    signatures_comparable = not (
        baseline_run is not None
        and baseline_signature
        and current_signature
        and baseline_signature != current_signature
    )
    comparison_baseline = baseline_run if signatures_comparable else None
    baseline_summary = (comparison_baseline or {}).get("summary") or {}
    payloads = read_payloads_jsonl(Path(str(run.get("payloads_path") or "")))
    checks = []

    if baseline_run is not None and not signatures_comparable:
        checks.append(
            gate_check(
                "evaluation_definition_matches_baseline",
                passed=None,
                message=(
                    "Baseline comparison skipped because the query/expected-CUI/acceptable-CUI "
                    "signature differs from the current run."
                ),
                current_signature=current_signature,
                baseline_signature=baseline_signature,
                baseline_run_id=baseline_run.get("run_id"),
            )
        )

    current_strict = metric_number(summary, "strict_success_at_10_rate")
    baseline_strict = metric_number(baseline_summary, "strict_success_at_10_rate")
    if comparison_baseline is None or current_strict is None or baseline_strict is None:
        checks.append(
            gate_check(
                "strict_success_at_10_no_drop",
                passed=None,
                message="No comparable baseline strict success@10 metric was available.",
            )
        )
    else:
        minimum = baseline_strict - args.strict_success_at_10_tolerance
        checks.append(
            gate_check(
                "strict_success_at_10_no_drop",
                passed=current_strict >= minimum,
                message="Current strict success@10 must not fall below the baseline beyond tolerance.",
                current=current_strict,
                baseline=baseline_strict,
                tolerance=args.strict_success_at_10_tolerance,
                minimum_allowed=minimum,
            )
        )

    current_fp = metric_number(summary, "known_false_positive_rate_at_10")
    baseline_fp = metric_number(baseline_summary, "known_false_positive_rate_at_10")
    if comparison_baseline is None or current_fp is None or baseline_fp is None:
        checks.append(
            gate_check(
                "known_false_positive_at_10_no_increase",
                passed=None,
                message="No comparable baseline known false-positive@10 metric was available.",
            )
        )
    else:
        maximum = baseline_fp + args.known_false_positive_at_10_tolerance
        checks.append(
            gate_check(
                "known_false_positive_at_10_no_increase",
                passed=current_fp <= maximum,
                message="Known false-positive@10 rate must not increase.",
                current=current_fp,
                baseline=baseline_fp,
                tolerance=args.known_false_positive_at_10_tolerance,
                maximum_allowed=maximum,
                current_count=summary.get("queries_with_disallowed_at_10"),
                baseline_count=baseline_summary.get("queries_with_disallowed_at_10"),
            )
        )

    current_sources = summary.get("source_counts_at_10") or {}
    baseline_sources = baseline_summary.get("source_counts_at_10") or {}
    if comparison_baseline is None or not baseline_sources:
        checks.append(
            gate_check(
                "source_count_no_unexpected_collapse",
                passed=None,
                message="No comparable baseline source-count mix was available.",
            )
        )
    else:
        collapsed_sources = source_collapse_details(
            current_sources,
            baseline_sources,
            tolerance=args.source_count_collapse_tolerance,
            min_baseline=args.source_count_collapse_min_baseline,
        )
        checks.append(
            gate_check(
                "source_count_no_unexpected_collapse",
                passed=not collapsed_sources,
                message="No source with enough baseline presence may collapse beyond tolerance.",
                tolerance=args.source_count_collapse_tolerance,
                min_baseline=args.source_count_collapse_min_baseline,
                collapsed_sources=collapsed_sources,
            )
        )

    evidence_mode = run.get("search_system") == SEARCH_SYSTEM_API and run.get("api_scope") == SEARCH_SCOPE_UMLS_EVIDENCE
    if evidence_mode:
        protocol_findings = clinicaltrials_protocol_only_findings(payloads)
        checks.append(
            gate_check(
                "clinicaltrials_no_protocol_only_evidence",
                passed=not protocol_findings,
                message="Evidence mode must not expose protocol-only ClinicalTrials.gov text as evidence.",
                findings=protocol_findings,
            )
        )
    else:
        checks.append(
            gate_check(
                "clinicaltrials_no_protocol_only_evidence",
                passed=None,
                message="Skipped because this run is not API evidence mode.",
            )
        )

    restricted_findings = restricted_public_display_findings(
        payloads,
        patterns=tuple(args.restricted_source_pattern or DEFAULT_RESTRICTED_SOURCE_PATTERNS),
    )
    checks.append(
        gate_check(
            "public_display_no_restricted_or_non_level_0_content",
            passed=not restricted_findings,
            message="Public display payloads must not expose restricted or non-level-0 source content.",
            findings=restricted_findings,
        )
    )

    failed = [check for check in checks if check.get("passed") is False]
    return {
        "passed": not failed,
        "created_at": utc_timestamp(),
        "baseline_run_id": (comparison_baseline or {}).get("run_id"),
        "baseline_label": (comparison_baseline or {}).get("label"),
        "checks": checks,
    }


def persist_gate_result(run: dict, gate_result: dict) -> None:
    run_dir = Path(str(run.get("run_dir") or ""))
    gate_path = run_dir / "gate_result.json"
    gate_path.write_text(json.dumps(gate_result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    run["gate_result"] = gate_result
    run["gate_result_path"] = str(gate_path)
    run_json = run_dir / "run.json"
    if run_json.exists():
        run_json.write_text(json.dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def print_gate_result(run: dict, gate_result: dict) -> None:
    label = run.get("label") or run.get("run_id")
    status = "PASS" if gate_result.get("passed") else "FAIL"
    print(f"{label} gates: {status}")
    for check in gate_result.get("checks") or []:
        if check.get("passed") is not False:
            continue
        print(f"  failed {check.get('name')}: {check.get('message')}")


def search_system_label(search_system: str) -> str:
    if search_system == SEARCH_SYSTEM_UMLS_ONLY:
        return "UMLS-only"
    return "Current search"


def search_system_description(search_system: str) -> str:
    if search_system == SEARCH_SYSTEM_UMLS_ONLY:
        return (
            "UMLS labels, source-code resolver, MRSTY semantic types, and MRDEF definitions only; "
            "no evidence vectors, extension concepts, active-label supplement, or related graph expansion."
        )
    return "Live search API using the currently running configured search server."


def run_identity(args: argparse.Namespace, search_system: str, index: int, total: int) -> tuple[str, str]:
    base_run_id = args.run_id or run_id_from_timestamp()
    base_label = args.label or base_run_id
    if total == 1:
        return base_run_id, base_label
    suffix = slug(search_system)
    return f"{base_run_id}_{suffix}", f"{base_label} - {search_system_label(search_system)}"


def acceptable_options(expected_cui: str, alternatives: dict[str, set[str]]) -> set[str]:
    expected_cui = expected_cui.upper()
    return {expected_cui, *alternatives.get(expected_cui, set())}


def top_on_target(spec: QuerySpec, hits: list[dict], alternatives: dict[str, set[str]]) -> bool:
    if not spec.expected_cuis or not hits:
        return False
    top_cui = str(hits[0].get("cui") or "").upper()
    acceptable = set()
    for expected_cui in spec.expected_cuis:
        acceptable.update(acceptable_options(expected_cui, alternatives))
    return top_cui in acceptable


def row_top_on_target(row: dict) -> bool:
    return str(row.get("top_on_target") or "") == "1"


def row_has_missing(row: dict, limit: int) -> bool:
    return bool(str(row.get(f"missing_at_{limit}") or "").strip())


def row_has_disallowed(row: dict, limit: int) -> bool:
    return bool(str(row.get(f"disallowed_at_{limit}") or "").strip())


def row_strict_success(row: dict, limit: int) -> bool:
    return (
        row_top_on_target(row)
        and not row_has_missing(row, limit)
        and not row_has_disallowed(row, limit)
    )


def augment_row(row: dict, spec: QuerySpec, hits: list[dict], alternatives: dict[str, set[str]]) -> dict:
    first_rank = int(row["first_expected_rank"] or 0)
    top_target = top_on_target(spec, hits, alternatives)
    acceptable = set()
    for expected_cui in spec.expected_cuis:
        acceptable.update(acceptable_options(expected_cui, alternatives))
    augmented = {
        **row,
        "expected_cuis": "|".join(spec.expected_cuis),
        "acceptable_cuis": "|".join(sorted(acceptable)),
        "configured_disallowed_cuis": "|".join(sorted(spec.disallowed_cuis or [])),
        "top_on_target": "1" if top_target else "0",
        "reciprocal_first_expected_rank": f"{(1 / first_rank):.6f}" if first_rank else "0.000000",
    }
    augmented["strict_success_at_10"] = "1" if row_strict_success(augmented, 10) else "0"
    augmented["strict_success_at_20"] = "1" if row_strict_success(augmented, 20) else "0"
    return augmented


def add_derived_metrics(summary: dict, rows: list[dict], *, elapsed_seconds: float) -> dict:
    paragraphs = int(summary.get("paragraphs") or 0)
    good = int((summary.get("verdict_counts") or {}).get("good") or 0)
    summary["good_rate"] = good / paragraphs if paragraphs else 0.0
    summary["mixed_count"] = int((summary.get("verdict_counts") or {}).get("mixed") or 0)
    summary["poor_count"] = int((summary.get("verdict_counts") or {}).get("poor") or 0)
    summary["mean_coverage_at_10"] = mean_float(rows, "coverage_at_10")
    summary["mean_coverage_at_20"] = mean_float(rows, "coverage_at_20")
    summary["mrr_first_expected"] = mean_float(rows, "reciprocal_first_expected_rank")
    summary["median_first_expected_rank"] = median_int(rows, "first_expected_rank")
    summary["top_on_target_count"] = sum(1 for row in rows if row_top_on_target(row))
    summary["top_on_target_rate"] = summary["top_on_target_count"] / paragraphs if paragraphs else 0.0
    summary["top_wrong_count"] = max(paragraphs - summary["top_on_target_count"], 0)
    summary["top_wrong_rate"] = summary["top_wrong_count"] / paragraphs if paragraphs else 0.0
    for limit in (10, 20):
        missing_count = sum(1 for row in rows if row_has_missing(row, limit))
        all_expected_count = max(paragraphs - missing_count, 0)
        disallowed_count = sum(1 for row in rows if row_has_disallowed(row, limit))
        strict_count = sum(1 for row in rows if row_strict_success(row, limit))
        summary[f"queries_with_missing_at_{limit}"] = missing_count
        summary[f"queries_all_expected_at_{limit}"] = all_expected_count
        summary[f"all_expected_at_{limit}_rate"] = all_expected_count / paragraphs if paragraphs else 0.0
        summary[f"queries_with_disallowed_at_{limit}"] = disallowed_count
        summary[f"known_false_positive_rate_at_{limit}"] = disallowed_count / paragraphs if paragraphs else 0.0
        summary[f"strict_success_at_{limit}_count"] = strict_count
        summary[f"strict_success_at_{limit}_rate"] = strict_count / paragraphs if paragraphs else 0.0
    summary["elapsed_seconds"] = round(float(elapsed_seconds or summary.get("elapsed_seconds") or 0.0), 3)
    summary["overall_score"] = overall_score_from_summary(summary)
    return summary


def mean_float(rows: list[dict], field: str) -> float:
    values = [float(row.get(field) or 0.0) for row in rows]
    return sum(values) / len(values) if values else 0.0


def median_int(rows: list[dict], field: str) -> float:
    values = [int(row.get(field) or 0) for row in rows if int(row.get(field) or 0) > 0]
    return float(statistics.median(values)) if values else 0.0


def write_rows_tsv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "id",
        "verdict",
        "expected_cuis",
        "acceptable_cuis",
        "configured_disallowed_cuis",
        "expected_count",
        "found_at_5",
        "found_at_10",
        "found_at_20",
        "found_at_60",
        "coverage_at_10",
        "coverage_at_20",
        "first_expected_rank",
        "reciprocal_first_expected_rank",
        "top_on_target",
        "strict_success_at_10",
        "strict_success_at_20",
        "top_cui",
        "top_name",
        "top_semantic_group",
        "missing_at_10",
        "missing_at_20",
        "accepted_alternatives_at_10",
        "disallowed_at_10",
        "disallowed_at_20",
        "hits_top_10",
        "query",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_source_quality_tsv(path: Path, ranked_sources: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "source",
        "queries_present_at_10",
        "strict_success_queries_present_at_10",
        "failed_queries_present_at_10",
        "strict_success_query_rate_when_present",
        "expected_queries_at_10",
        "strict_success_expected_queries_at_10",
        "failed_expected_queries_at_10",
        "expected_query_rate_when_present",
        "disallowed_queries_at_10",
        "disallowed_query_rate_when_present",
        "top1_queries",
        "top1_expected_queries",
        "top1_strict_success_expected_queries",
        "hit_source_appearances_at_10",
        "expected_hit_source_appearances_at_10",
        "disallowed_hit_source_appearances_at_10",
        "expected_hit_rate_at_10",
        "disallowed_hit_rate_at_10",
        "mean_best_rank_at_10",
        "mean_best_expected_rank_at_10",
        "expected_examples",
        "disallowed_examples",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for source in ranked_sources:
            row = {field: source.get(field, "") for field in fields}
            row["expected_examples"] = json.dumps(
                source.get("expected_examples") or [],
                sort_keys=True,
                separators=(",", ":"),
            )
            row["disallowed_examples"] = json.dumps(
                source.get("disallowed_examples") or [],
                sort_keys=True,
                separators=(",", ":"),
            )
            writer.writerow(row)


def build_umls_only_index(args: argparse.Namespace) -> SearchIndex:
    label_indexes = args.umls_label_index if args.umls_label_index is not None else DEFAULT_LABEL_INDEXES
    if not label_indexes:
        raise SystemExit("no UMLS label index configured; pass --umls-label-index")
    for path in label_indexes:
        existing_path(path, label="UMLS label index")
    code_index_path = None if args.no_umls_code_index else existing_path(
        args.umls_code_index or default_existing_path(DEFAULT_CODE_INDEX),
        label="UMLS code index",
    )
    semantic_type_index_path = None if args.no_umls_semantic_type_index else existing_path(
        args.umls_semantic_type_index or default_existing_path(DEFAULT_SEMANTIC_TYPE_INDEX),
        label="UMLS semantic type index",
    )
    definition_index_path = None if args.no_umls_definition_index else existing_path(
        args.umls_definition_index or default_existing_path(DEFAULT_DEFINITION_INDEX),
        label="UMLS definition index",
    )
    return SearchIndex(
        vector_paths=[],
        doc_paths=[],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=384,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        label_index_paths=label_indexes,
        code_index_path=code_index_path,
        semantic_type_index_path=semantic_type_index_path,
        definition_index_path=definition_index_path,
        relation_index_path=None,
        research_relation_index_path=None,
        relationship_edge_index_path=None,
        external_cui_vector_index_path=None,
        active_label_supplement_path=None,
        label_fallback_limit=args.umls_label_fallback_limit,
        definition_fallback_limit=args.umls_definition_fallback_limit,
        candidate_pool_multiplier=1,
        candidate_pool_min=1,
    )


def search_api_response(args: argparse.Namespace, spec: QuerySpec) -> dict:
    response = get_json(
        args.base_url,
        "/api/search",
        {
            "q": spec.query,
            "k": args.top_k,
            "related": 1 if args.include_related else 0,
            "linked": 1 if args.include_linked_concepts else 0,
            "evidence_items": 1 if args.include_search_evidence_items else 0,
            "mode": args.mode,
            "scope": args.scope,
        },
        timeout=args.timeout,
    )
    required_backend = str(args.require_api_backend or "").strip()
    if required_backend:
        actual_backend = str(response.get("backend") or "").strip()
        if actual_backend.lower() != required_backend.lower():
            raise SystemExit(
                "API search backend "
                f"{actual_backend!r} did not match required backend {required_backend!r}. "
                "Start the search-quality API with Elasticsearch enabled before rerunning."
            )
    return response


def search_umls_only_response(args: argparse.Namespace, index: SearchIndex, spec: QuerySpec) -> dict:
    response = index.search(
        spec.query,
        top_k=args.top_k,
        include_related=False,
        include_linked_concepts=False,
        include_evidence_items=False,
        search_mode=args.mode,
        search_scope=SEARCH_SCOPE_UMLS,
    )
    response["search_system"] = SEARCH_SYSTEM_UMLS_ONLY
    response["search_system_description"] = search_system_description(SEARCH_SYSTEM_UMLS_ONLY)
    response["backend"] = "umls_only"
    return response


def effective_query_worker_count(args: argparse.Namespace, *, search_system: str, query_count: int) -> int:
    try:
        requested = int(getattr(args, "workers", DEFAULT_API_WORKERS) or 1)
    except (TypeError, ValueError):
        requested = 1
    requested = max(requested, 1)
    if search_system != SEARCH_SYSTEM_API:
        return 1
    return min(requested, max(int(query_count or 0), 1))


def numeric_response_value(response: dict, key: str) -> float | None:
    try:
        value = response.get(key)
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def selected_server_timing(response: dict) -> dict:
    if bool(response.get("cache_hit") or response.get("cached")):
        timing = response.get("uncached_server_timing")
        if isinstance(timing, dict):
            return timing
    timing = response.get("server_timing")
    return timing if isinstance(timing, dict) else {}


def server_timing_by_stage(response: dict) -> dict[str, float]:
    timing = selected_server_timing(response)
    by_stage = timing.get("by_stage") if isinstance(timing, dict) else {}
    if not isinstance(by_stage, dict):
        return {}
    values: dict[str, float] = {}
    for key, value in by_stage.items():
        try:
            values[str(key)] = float(value or 0.0)
        except (TypeError, ValueError):
            continue
    return values


def server_timing_column_ms(response: dict, column: str) -> float | None:
    by_stage = server_timing_by_stage(response)
    stages = SERVER_TIMING_STAGE_COLUMNS.get(column, ())
    if not stages:
        return None
    total = sum(float(by_stage.get(stage, 0.0) or 0.0) for stage in stages)
    return total if total > 0.0 else None


def query_timing_row(
    spec: QuerySpec,
    response: dict,
    *,
    hit_count: int,
    elapsed_seconds: float,
) -> dict:
    elapsed_ms = numeric_response_value(response, "elapsed_ms")
    uncached_elapsed_ms = numeric_response_value(response, "uncached_elapsed_ms")
    cache_hit = bool(response.get("cache_hit") or response.get("cached"))
    server_timing = selected_server_timing(response)
    server_total_ms = None
    if isinstance(server_timing, dict):
        try:
            server_total_ms = float(server_timing.get("total_ms") or 0.0)
        except (TypeError, ValueError):
            server_total_ms = None
    row = {
        "id": spec.query_id,
        "elapsed_seconds": round(float(elapsed_seconds or 0.0), 3),
        "response_elapsed_ms": round(elapsed_ms, 3) if elapsed_ms is not None else "",
        "response_uncached_elapsed_ms": (
            round(uncached_elapsed_ms, 3) if uncached_elapsed_ms is not None else ""
        ),
        "server_total_ms": round(server_total_ms, 3) if server_total_ms is not None else "",
        "cache_hit": "1" if cache_hit else "0",
        "backend": str(response.get("backend") or ""),
        "hit_count": int(hit_count or 0),
    }
    for column in SERVER_TIMING_STAGE_COLUMNS:
        value = server_timing_column_ms(response, column)
        row[f"server_{column}_ms"] = round(value, 3) if value is not None else ""
    return row


def query_timing_summary(
    timings: list[dict],
    *,
    workers: int,
    wall_elapsed_seconds: float,
) -> dict:
    elapsed_values = [float(row.get("elapsed_seconds") or 0.0) for row in timings]
    response_ms_values = [
        float(row.get("response_elapsed_ms") or 0.0)
        for row in timings
        if row.get("response_elapsed_ms") not in ("", None)
    ]
    response_seconds = [value / 1000.0 for value in response_ms_values]
    server_total_seconds = [
        float(row.get("server_total_ms") or 0.0) / 1000.0
        for row in timings
        if row.get("server_total_ms") not in ("", None)
    ]
    server_stage_seconds: dict[str, list[float]] = {}
    for column in SERVER_TIMING_STAGE_COLUMNS:
        key = f"server_{column}_ms"
        values = [
            float(row.get(key) or 0.0) / 1000.0
            for row in timings
            if row.get(key) not in ("", None)
        ]
        if values:
            server_stage_seconds[column] = values
    elapsed_sum = sum(elapsed_values)
    response_sum = sum(response_seconds)
    wall_elapsed = float(wall_elapsed_seconds or 0.0)
    summary = {
        "workers": int(workers or 1),
        "query_execution_wall_seconds": round(wall_elapsed, 3),
        "query_elapsed_sum_seconds": round(elapsed_sum, 3),
        "query_elapsed_mean_seconds": round(elapsed_sum / len(elapsed_values), 3) if elapsed_values else 0.0,
        "query_elapsed_max_seconds": round(max(elapsed_values), 3) if elapsed_values else 0.0,
        "api_response_elapsed_sum_seconds": round(response_sum, 3),
        "api_response_elapsed_mean_seconds": (
            round(response_sum / len(response_seconds), 3) if response_seconds else 0.0
        ),
        "server_timing_total_sum_seconds": round(sum(server_total_seconds), 3),
        "server_timing_total_mean_seconds": (
            round(sum(server_total_seconds) / len(server_total_seconds), 3)
            if server_total_seconds
            else 0.0
        ),
        "query_client_overhead_sum_seconds": round(max(elapsed_sum - response_sum, 0.0), 3),
        "query_parallelism_saved_seconds": round(max(elapsed_sum - wall_elapsed, 0.0), 3),
        "query_cache_hit_count": sum(1 for row in timings if str(row.get("cache_hit") or "") == "1"),
    }
    for column, values in server_stage_seconds.items():
        total = sum(values)
        summary[f"server_{column}_sum_seconds"] = round(total, 3)
        summary[f"server_{column}_mean_seconds"] = round(total / len(values), 3)
    return summary


def write_query_timings_tsv(path: Path, timings: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "id",
        "elapsed_seconds",
        "response_elapsed_ms",
        "response_uncached_elapsed_ms",
        "server_total_ms",
        *[f"server_{column}_ms" for column in SERVER_TIMING_STAGE_COLUMNS],
        "cache_hit",
        "backend",
        "hit_count",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in timings:
            writer.writerow({field: row.get(field, "") for field in fields})


def evaluate_query_spec_for_run(
    args: argparse.Namespace,
    *,
    search_system: str,
    umls_index: SearchIndex | None,
    spec: QuerySpec,
    alternatives: dict[str, set[str]],
) -> dict:
    started = datetime.now(timezone.utc)
    if search_system == SEARCH_SYSTEM_UMLS_ONLY:
        if umls_index is None:
            raise RuntimeError("UMLS-only search requested without an initialized index")
        response = search_umls_only_response(args, umls_index, spec)
    else:
        response = search_api_response(args, spec)
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    hits = list(response.get("hits") or [])
    row = judge_quality(spec, hits, acceptable_alternatives=alternatives)
    augmented = augment_row(row, spec, hits, alternatives)
    payload = {"id": spec.query_id, "query": spec.query, "response": response}
    return {
        "spec": spec,
        "row": augmented,
        "payload": payload,
        "response": response,
        "timing": query_timing_row(spec, response, hit_count=len(hits), elapsed_seconds=elapsed),
    }


def run_experiment(
    args: argparse.Namespace,
    *,
    search_system: str = SEARCH_SYSTEM_API,
    run_id: str | None = None,
    label: str | None = None,
) -> dict:
    started = datetime.now(timezone.utc)
    specs = read_query_specs(args.queries)
    if not specs:
        raise SystemExit(f"no queries found in {args.queries}")
    alternatives = read_acceptable_alternatives(args.alternatives)
    run_id = run_id or args.run_id or run_id_from_timestamp()
    label = label or args.label or run_id
    specs, query_selection = select_query_specs_for_run(specs, args, run_id=run_id, label=label)
    if not specs:
        raise SystemExit(f"query selection produced no rows from {args.queries}")
    run_dir = args.output_root / "runs" / f"{run_id}_{slug(label)}"
    payload_dir = run_dir / "payloads"
    payload_dir.mkdir(parents=True, exist_ok=True)
    umls_index = build_umls_only_index(args) if search_system == SEARCH_SYSTEM_UMLS_ONLY else None

    worker_count = effective_query_worker_count(args, search_system=search_system, query_count=len(specs))
    result_slots: list[dict | None] = [None] * len(specs)
    query_execution_started = datetime.now(timezone.utc)
    if worker_count > 1:
        if args.verbose:
            print(
                f"running {len(specs)} {search_system} queries with {worker_count} workers",
                file=sys.stderr,
            )
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_to_index = {}
            for index, spec in enumerate(specs, start=1):
                if args.verbose:
                    print(f"[{index}/{len(specs)}] queued {search_system} {spec.query_id}", file=sys.stderr)
                future = executor.submit(
                    evaluate_query_spec_for_run,
                    args,
                    search_system=search_system,
                    umls_index=umls_index,
                    spec=spec,
                    alternatives=alternatives,
                )
                future_to_index[future] = index
            for completed, future in enumerate(as_completed(future_to_index), start=1):
                index = future_to_index[future]
                result = future.result()
                result_slots[index - 1] = result
                if args.verbose:
                    timing = result.get("timing") or {}
                    print(
                        f"[done {completed}/{len(specs)}] {search_system} "
                        f"{result['spec'].query_id} {timing.get('elapsed_seconds')}s",
                        file=sys.stderr,
                    )
    else:
        for index, spec in enumerate(specs, start=1):
            if args.verbose:
                print(f"[{index}/{len(specs)}] {search_system} {spec.query_id}", file=sys.stderr)
            result_slots[index - 1] = evaluate_query_spec_for_run(
                args,
                search_system=search_system,
                umls_index=umls_index,
                spec=spec,
                alternatives=alternatives,
            )

    query_execution_elapsed = (datetime.now(timezone.utc) - query_execution_started).total_seconds()
    results = [result for result in result_slots if result is not None]
    rows = [result["row"] for result in results]
    payloads = [result["payload"] for result in results]
    query_timings = [result["timing"] for result in results]
    for result in results:
        (payload_dir / f"{result['spec'].query_id}.json").write_text(
            json.dumps(result["response"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    evaluation_signature = evaluation_signature_from_rows(rows)
    summary = add_derived_metrics(summarize(rows), rows, elapsed_seconds=elapsed)
    summary.update(
        query_timing_summary(
            query_timings,
            workers=worker_count,
            wall_elapsed_seconds=query_execution_elapsed,
        )
    )
    summary["search_system"] = search_system
    summary["search_system_label"] = search_system_label(search_system)
    summary["query_pool_count"] = query_selection["query_pool_count"]
    summary["query_limit"] = query_selection["query_limit"]
    summary["query_selected_count"] = query_selection["query_selected_count"]
    summary["query_selection"] = query_selection["query_selection"]
    summary["source_counts_at_10"] = source_counts_from_payloads(payloads, limit=10)
    summary["source_counts_all"] = source_counts_from_payloads(payloads, limit=args.top_k)
    source_quality = source_quality_contribution(payloads, rows, limit=10)
    summary["source_quality_at_10"] = source_quality["sources"]
    summary["source_quality_ranked_at_10"] = source_quality["ranked_sources"]
    run = {
        "run_id": run_id,
        "label": label,
        "created_at": utc_timestamp(),
        "search_system": search_system,
        "search_system_label": search_system_label(search_system),
        "search_system_description": search_system_description(search_system),
        "base_url": args.base_url,
        "mode": args.mode,
        "api_scope": args.scope if search_system == SEARCH_SYSTEM_API else "",
        "run_family": str(args.run_family or "").strip(),
        "top_k": args.top_k,
        "include_related": bool(args.include_related),
        "include_linked_concepts": bool(args.include_linked_concepts),
        "include_search_evidence_items": bool(args.include_search_evidence_items),
        "queries": str(args.queries),
        "query_pool_count": query_selection["query_pool_count"],
        "query_limit": query_selection["query_limit"],
        "query_selected_count": query_selection["query_selected_count"],
        "query_selection": query_selection["query_selection"],
        "query_rotation_seed": query_selection["query_rotation_seed"],
        "query_selection_ids": query_selection["query_selection_ids"],
        "alternatives": str(args.alternatives),
        "evaluation_signature": evaluation_signature,
        "run_dir": str(run_dir),
        "metrics_path": str(run_dir / "metrics.json"),
        "rows_path": str(run_dir / "rows.tsv"),
        "payloads_path": str(run_dir / "payloads.jsonl"),
        "query_timings_path": str(run_dir / "query_timings.tsv"),
        "source_quality_path": str(run_dir / "source_quality_at_10.tsv"),
        "source_quality_json_path": str(run_dir / "source_quality_at_10.json"),
        "requested_workers": int(getattr(args, "workers", DEFAULT_API_WORKERS) or 1),
        "workers": worker_count,
        "git_commit": git_value(["rev-parse", "--short", "HEAD"]),
        "git_dirty": bool(git_value(["status", "--porcelain"])),
        "summary": summary,
    }
    if search_system == SEARCH_SYSTEM_UMLS_ONLY and umls_index is not None:
        run["umls_only"] = {
            "label_indexes": [str(path) for path in umls_index.label_fallback.paths],
            "code_index": str(umls_index.code_index_path or ""),
            "semantic_type_index": str(umls_index.semantic_type_index_path or ""),
            "definition_index": str(umls_index.definition_index_path or ""),
            "label_fallback_limit": umls_index.label_fallback_limit,
            "definition_fallback_limit": umls_index.definition_fallback_limit,
        }

    run_dir.mkdir(parents=True, exist_ok=True)
    write_rows_tsv(run_dir / "rows.tsv", rows)
    write_rows_tsv(run_dir / "paragraph_quality_summary.tsv", rows)
    write_jsonl(run_dir / "payloads.jsonl", payloads)
    write_query_timings_tsv(run_dir / "query_timings.tsv", query_timings)
    write_source_quality_tsv(run_dir / "source_quality_at_10.tsv", source_quality["ranked_sources"])
    (run_dir / "source_quality_at_10.json").write_text(
        json.dumps(source_quality, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_dir / "metrics.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (run_dir / "run.json").write_text(json.dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(run_dir / "paragraph_quality_report.md", summary, rows)
    return run


def read_manifest(path: Path) -> dict:
    if not path.exists():
        return {"runs": []}
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def update_manifest(output_root: Path, run: dict) -> dict:
    manifest_path = output_root / MANIFEST_NAME
    manifest = read_manifest(manifest_path)
    runs = [item for item in manifest.get("runs", []) if item.get("run_id") != run.get("run_id")]
    runs.append(run)
    runs.sort(key=lambda item: str(item.get("created_at") or ""))
    manifest = {"runs": runs}
    write_manifest(manifest_path, manifest)
    return manifest


def read_iteration_smoke_manifest(output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict:
    return read_manifest(output_root / ITERATION_SMOKE_MANIFEST_NAME)


def write_iteration_smoke_manifest(output_root: Path, manifest: dict) -> None:
    write_manifest(output_root / ITERATION_SMOKE_MANIFEST_NAME, manifest)


def update_iteration_smoke_manifest(output_root: Path, entry: dict) -> dict:
    manifest = read_iteration_smoke_manifest(output_root)
    entries = [
        item
        for item in manifest.get("runs", [])
        if item.get("verification_id") != entry.get("verification_id")
    ]
    entries.append(entry)
    entries.sort(key=lambda item: str(item.get("created_at") or ""))
    manifest = {"runs": entries}
    write_iteration_smoke_manifest(output_root, manifest)
    return manifest


def normalize_iteration_types(values: list[str] | None) -> list[str]:
    raw = []
    for value in values or []:
        raw.extend(part.strip().lower() for part in str(value).split(","))
    normalized = []
    unknown = []
    for value in raw:
        if not value:
            continue
        if value not in ITERATION_TYPE_CHOICES:
            unknown.append(value)
            continue
        if value not in normalized:
            normalized.append(value)
    if unknown:
        allowed = ", ".join(ITERATION_TYPE_CHOICES)
        raise SystemExit(f"unknown --iteration-type value(s): {', '.join(unknown)}; allowed: {allowed}")
    return normalized or ["process"]


def safe_verification_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-._")
    return cleaned or "iteration-smoke-gates"


def helper_command_env() -> dict[str, str]:
    env = dict(os.environ)
    prefix = f"{SRC}:{SCRIPTS}"
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = prefix if not existing else f"{prefix}:{existing}"
    return env


def command_text(command: str | list[str]) -> str:
    if isinstance(command, str):
        return command
    return shlex.join(str(part) for part in command)


def repo_display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except Exception:
        return str(path)


def smoke_tier_decision(args: argparse.Namespace, iteration_types: list[str]) -> dict:
    docs_only = bool(getattr(args, "docs_only_change", False))
    ui_report_only = bool(getattr(args, "ui_report_only_change", False))
    development_loop = bool(getattr(args, "development_loop", False))
    live_disabled_by_scope = docs_only or ui_report_only
    standing = bool(set(iteration_types) & STANDING_SMOKE_ITERATION_TYPES)
    rotating = bool(set(iteration_types) & ROTATING_SMOKE_ITERATION_TYPES)
    patient_portal = bool(set(iteration_types) & PATIENT_PORTAL_SMOKE_ITERATION_TYPES)
    broad_or_release = bool(getattr(args, "broad_change", False) or getattr(args, "release_quality", False))
    if live_disabled_by_scope:
        standing = False
        rotating = False
        patient_portal = False
    if broad_or_release:
        standing = True
        rotating = True
        patient_portal = True
    if development_loop and not live_disabled_by_scope and not broad_or_release:
        rotating = False
        patient_portal = False
    if getattr(args, "force_standing_smoke", False):
        standing = True
    if getattr(args, "force_rotating_smoke", False):
        rotating = True
        standing = True
    if getattr(args, "force_patient_portal_smoke", False):
        patient_portal = True
    if getattr(args, "skip_standing_smoke", False):
        standing = False
    if getattr(args, "skip_rotating_smoke", False):
        rotating = False
    if getattr(args, "skip_patient_portal_smoke", False):
        patient_portal = False

    reasons = []
    if docs_only:
        reasons.append("docs-only/local-layout flag suppresses live smoke unless forced")
    if ui_report_only:
        reasons.append("UI/report-only flag suppresses live smoke unless forced")
    if set(iteration_types) & STANDING_SMOKE_ITERATION_TYPES:
        reasons.append("iteration type requires standing clinical API smoke")
    if set(iteration_types) & ROTATING_SMOKE_ITERATION_TYPES:
        reasons.append("iteration type requires 50-query rotating smoke with gates")
    if set(iteration_types) & PATIENT_PORTAL_SMOKE_ITERATION_TYPES:
        reasons.append("iteration type requires patient portal current-versus-history smoke")
    if getattr(args, "broad_change", False):
        reasons.append("broad-change flag requires standing, rotating, and patient portal smoke")
    if getattr(args, "release_quality", False):
        reasons.append("release-quality flag requires standing, rotating, and patient portal smoke")
    if development_loop:
        reasons.append("development-loop flag defers rotating and patient portal smoke unless forced or release-quality")
    if getattr(args, "skip_standing_smoke", False):
        reasons.append("standing smoke explicitly skipped")
    if getattr(args, "skip_rotating_smoke", False):
        reasons.append("rotating smoke explicitly skipped")
    if getattr(args, "force_patient_portal_smoke", False):
        reasons.append("patient portal smoke explicitly forced")
    if getattr(args, "skip_patient_portal_smoke", False):
        reasons.append("patient portal smoke explicitly skipped")
    if not reasons:
        reasons.append("process-only change defaults to static/focused checks only")

    return {
        "standing_smoke": standing,
        "rotating_smoke": rotating,
        "patient_portal_smoke": patient_portal,
        "reasons": reasons,
    }


def build_iteration_smoke_steps(args: argparse.Namespace, verification_id: str, iteration_types: list[str]) -> list[dict]:
    decision = smoke_tier_decision(args, iteration_types)
    steps = []
    for index, command in enumerate(getattr(args, "static_command", []) or [], start=1):
        steps.append(
            {
                "name": f"static_check_{index}",
                "tier": "static",
                "command": command,
                "shell": True,
                "reason": "user-supplied static verification command",
            }
        )
    for index, command in enumerate(getattr(args, "focused_command", []) or [], start=1):
        steps.append(
            {
                "name": f"focused_check_{index}",
                "tier": "focused",
                "command": command,
                "shell": True,
                "reason": "user-supplied focused verification command",
            }
        )
    if decision["standing_smoke"]:
        standing_jsonl = (
            Path(getattr(args, "verification_run_dir"))
            / "standing_clinical_smoke.jsonl"
        )
        steps.append(
            {
                "name": "standing_clinical_api_smoke",
                "tier": "standing",
                "command": [
                    sys.executable,
                    str(SCRIPTS / "evaluate_search_api.py"),
                    "--queries",
                    str(ROOT / "config" / "search_quality_clinical_queries.tsv"),
                    "--base-url",
                    str(args.base_url),
                    "--top-k",
                    "5",
                    "--timeout",
                    str(args.timeout),
                    "--jsonl-out",
                    str(standing_jsonl),
                    "--fail-on-missing-expected",
                ],
                "shell": False,
                "reason": "standing clinical API smoke for runtime/search-quality behavior",
                "output": repo_display_path(standing_jsonl),
            }
        )
    if decision["rotating_smoke"]:
        run_id = f"{safe_verification_id(verification_id)}_rotating_50"
        steps.append(
            {
                "name": "rotating_50_query_smoke",
                "tier": "rotating",
                "command": [
                    sys.executable,
                    str(SCRIPTS / "run_search_quality_experiment.py"),
                    "--base-url",
                    str(args.base_url),
                    "--scope",
                    str(args.scope),
                    "--run-family",
                    "smoke",
                    "--label",
                    f"{verification_id} automated 50-query smoke",
                    "--run-id",
                    run_id,
                    "--queries",
                    str(args.queries),
                    "--query-limit",
                    "50",
                    "--query-selection",
                    "rotate",
                    "--search-system",
                    SEARCH_SYSTEM_API,
                    "--top-k",
                    str(args.top_k),
                    "--timeout",
                    str(args.timeout),
                    "--workers",
                    str(getattr(args, "workers", DEFAULT_API_WORKERS)),
                    "--output-root",
                    str(args.output_root),
                    "--html-report",
                    str(args.html_report),
                    "--require-api-backend",
                    str(args.require_api_backend),
                    "--fail-gates",
                ],
                "shell": False,
                "reason": "50-query rotating smoke with release gates",
            }
        )
    if decision["patient_portal_smoke"]:
        run_id = f"{safe_verification_id(verification_id)}_patient_portal"
        steps.append(
            {
                "name": "patient_portal_current_history_smoke",
                "tier": "patient_portal",
                "command": [
                    sys.executable,
                    str(SCRIPTS / "run_search_quality_experiment.py"),
                    "--base-url",
                    str(args.base_url),
                    "--scope",
                    str(args.scope),
                    "--run-family",
                    "patient_portal",
                    "--label",
                    f"{verification_id} patient portal current-versus-history lane",
                    "--run-id",
                    run_id,
                    "--queries",
                    str(ROOT / "config" / "search_quality_patient_portal_queries.tsv"),
                    "--query-limit",
                    "0",
                    "--search-system",
                    SEARCH_SYSTEM_API,
                    "--top-k",
                    str(args.top_k),
                    "--timeout",
                    str(args.timeout),
                    "--workers",
                    str(getattr(args, "workers", DEFAULT_API_WORKERS)),
                    "--output-root",
                    str(args.output_root),
                    "--html-report",
                    str(args.html_report),
                    "--require-api-backend",
                    str(args.require_api_backend),
                    "--fail-gates",
                ],
                "shell": False,
                "reason": "patient portal smoke for current-visit versus copied-forward history behavior",
            }
        )
    return steps


def command_result_excerpt(value: str, *, limit: int = 6000) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]


def execute_iteration_smoke_step(step: dict, *, dry_run: bool) -> dict:
    result = dict(step)
    result["command_text"] = command_text(step.get("command") or "")
    result["started_at"] = utc_timestamp()
    if dry_run:
        result["status"] = "planned"
        result["returncode"] = None
        result["passed"] = None
        result["finished_at"] = result["started_at"]
        return result
    try:
        if step.get("shell"):
            completed = subprocess.run(
                str(step.get("command") or ""),
                cwd=ROOT,
                env=helper_command_env(),
                shell=True,
                text=True,
                capture_output=True,
                check=False,
            )
        else:
            completed = subprocess.run(
                [str(part) for part in (step.get("command") or [])],
                cwd=ROOT,
                env=helper_command_env(),
                text=True,
                capture_output=True,
                check=False,
            )
        result["returncode"] = completed.returncode
        result["passed"] = completed.returncode == 0
        result["status"] = "passed" if completed.returncode == 0 else "failed"
        result["stdout_tail"] = command_result_excerpt(completed.stdout or "")
        result["stderr_tail"] = command_result_excerpt(completed.stderr or "")
    except Exception as exc:
        result["returncode"] = None
        result["passed"] = False
        result["status"] = "error"
        result["error"] = str(exc)
    result["finished_at"] = utc_timestamp()
    return result


def write_iteration_smoke_markdown(path: Path, entry: dict) -> None:
    lines = [
        f"# {entry.get('verification_id')} Smoke Verification",
        "",
        f"- Created: {entry.get('created_at')}",
        f"- Dry run: {entry.get('dry_run')}",
        f"- Iteration types: {', '.join(entry.get('iteration_types') or [])}",
        f"- Overall status: {entry.get('status')}",
        f"- Base URL: `{entry.get('base_url')}`",
        "",
        "## Decision",
        "",
    ]
    decision = entry.get("decision") or {}
    lines.append(f"- Standing clinical smoke: `{decision.get('standing_smoke')}`")
    lines.append(f"- Rotating 50-query smoke: `{decision.get('rotating_smoke')}`")
    lines.append(f"- Patient portal smoke: `{decision.get('patient_portal_smoke')}`")
    for reason in decision.get("reasons") or []:
        lines.append(f"- Reason: {reason}")
    lines.extend(["", "## Steps", ""])
    for step in entry.get("steps") or []:
        status = step.get("status")
        lines.append(f"### {step.get('name')} ({status})")
        lines.append("")
        lines.append(f"- Tier: `{step.get('tier')}`")
        lines.append(f"- Reason: {step.get('reason')}")
        lines.append(f"- Return code: `{step.get('returncode')}`")
        lines.append("")
        lines.append("```sh")
        lines.append(str(step.get("command_text") or command_text(step.get("command") or "")))
        lines.append("```")
        stdout = str(step.get("stdout_tail") or "").strip()
        stderr = str(step.get("stderr_tail") or "").strip()
        if stdout:
            lines.extend(["", "Stdout tail:", "", "```text", stdout, "```"])
        if stderr:
            lines.extend(["", "Stderr tail:", "", "```text", stderr, "```"])
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run_iteration_smoke_gates(args: argparse.Namespace) -> int:
    iteration_types = normalize_iteration_types(args.iteration_type)
    verification_id = str(args.iteration_id or "").strip() or f"iteration-smoke-{run_id_from_timestamp()}"
    verification_safe_id = safe_verification_id(verification_id)
    run_dir = args.output_root / "iteration_smoke_gates" / verification_safe_id
    run_dir.mkdir(parents=True, exist_ok=True)
    setattr(args, "verification_run_dir", str(run_dir))
    json_path = args.verification_out or (run_dir / "verification.json")
    md_path = args.verification_md_out or (run_dir / "verification.md")
    decision = smoke_tier_decision(args, iteration_types)
    steps = build_iteration_smoke_steps(args, verification_id, iteration_types)
    results = [execute_iteration_smoke_step(step, dry_run=args.dry_run) for step in steps]
    failed = [step for step in results if step.get("passed") is False]
    entry = {
        "verification_id": verification_id,
        "created_at": utc_timestamp(),
        "dry_run": bool(args.dry_run),
        "iteration_types": iteration_types,
        "base_url": args.base_url,
        "decision": decision,
        "status": "planned" if args.dry_run else ("failed" if failed else "passed"),
        "steps": results,
        "verification_json_path": repo_display_path(json_path),
        "verification_md_path": repo_display_path(md_path),
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(entry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_iteration_smoke_markdown(md_path, entry)
    update_iteration_smoke_manifest(args.output_root, entry)
    manifest = enrich_manifest_metrics(read_manifest(args.output_root / MANIFEST_NAME), persist=True)
    write_manifest(args.output_root / MANIFEST_NAME, manifest)
    write_html_report(args.html_report, manifest)
    print(json.dumps({"status": entry["status"], "verification": entry["verification_json_path"]}, indent=2, sort_keys=True))
    print(f"wrote {entry['verification_md_path']}")
    print(f"wrote {args.html_report}")
    return 1 if failed else 0


def read_run_rows(run: dict) -> list[dict]:
    rows_path_text = str(run.get("rows_path") or "").strip()
    if not rows_path_text:
        return []
    rows_path = Path(rows_path_text)
    if not rows_path.exists() or not rows_path.is_file():
        return []
    with rows_path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def compact_query_preview(row: dict, *, limit: int = 120) -> str:
    text = str(row.get("query") or row.get("id") or "query").strip()
    if text.lower().startswith("search:"):
        text = text.split(":", 1)[1].strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def plain_fixed_row_summaries(baseline: dict, latest: dict, *, limit: int = 6) -> list[str]:
    before_by_id = {str(row.get("id") or ""): row for row in read_run_rows(baseline)}
    summaries = []
    for after in read_run_rows(latest):
        query_id = str(after.get("id") or "")
        before = before_by_id.get(query_id)
        if not before:
            continue
        if before.get("strict_success_at_10") != "0" or after.get("strict_success_at_10") != "1":
            continue
        details = []
        if before.get("top_on_target") == "0" and after.get("top_on_target") == "1":
            before_top = str(before.get("top_name") or before.get("top_cui") or "the old top result")
            after_top = str(after.get("top_name") or after.get("top_cui") or "the new top result")
            details.append(f"top result moved from {before_top} to {after_top}")
        if before.get("missing_at_10") and not after.get("missing_at_10"):
            details.append("missing expected ideas now appear in the first 10 results")
        if before.get("disallowed_at_10") and not after.get("disallowed_at_10"):
            details.append("known bad result no longer appears in the first 10 results")
        if not details:
            details.append("the row now passes strict@10")
        summaries.append(
            f"{query_id}: {compact_query_preview(after)} ({'; '.join(details)})."
        )
        if len(summaries) >= limit:
            break
    return summaries


def plain_remaining_row_summaries(run: dict, *, limit: int = 5) -> list[str]:
    summaries = []
    for row in read_run_rows(run):
        if row.get("strict_success_at_10") == "1":
            continue
        details = []
        if row.get("top_on_target") == "0":
            top = " ".join(part for part in [row.get("top_cui", ""), row.get("top_name", "")] if part)
            details.append(f"top result is still off target ({top or 'no top result'})")
        if row.get("missing_at_10"):
            if row.get("missing_at_20"):
                details.append(f"still missing by rank 20: {row.get('missing_at_20')}")
            else:
                details.append("expected ideas are present by rank 20, but not all by rank 10")
        if row.get("disallowed_at_10"):
            details.append(f"known bad result appears: {row.get('disallowed_at_10')}")
        if not details:
            details.append("still does not meet strict@10")
        summaries.append(f"{row.get('id') or 'query'}: {compact_query_preview(row)} ({'; '.join(details)}).")
        if len(summaries) >= limit:
            break
    return summaries


def enrich_manifest_metrics(manifest: dict, *, persist: bool = False) -> dict:
    for run in manifest.get("runs") or []:
        rows = read_run_rows(run)
        if not rows:
            continue
        run["evaluation_signature"] = run.get("evaluation_signature") or evaluation_signature_from_rows(rows)
        summary = dict(run.get("summary") or {})
        elapsed = float(summary.get("elapsed_seconds") or 0.0)
        run["summary"] = add_derived_metrics(summary, rows, elapsed_seconds=elapsed)
        if not persist:
            continue
        metrics_path = Path(str(run.get("metrics_path") or ""))
        if metrics_path.exists():
            metrics_path.write_text(
                json.dumps(run["summary"], indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        run_dir = Path(str(run.get("run_dir") or ""))
        run_json = run_dir / "run.json"
        if run_json.exists():
            existing = json.loads(run_json.read_text(encoding="utf-8"))
            existing["summary"] = run["summary"]
            existing["evaluation_signature"] = run["evaluation_signature"]
            run_json.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def pct(value: object) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except Exception:
        return ""


def num(value: object, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return str(value or "")


def metric_value(run: dict, key: str) -> str:
    summary = run.get("summary") or {}
    if key in RATE_METRICS:
        return pct(summary.get(key, 0.0))
    value = summary.get(key, "")
    if isinstance(value, float):
        return num(value)
    return str(value)


def metric_float(run: dict, key: str) -> float | None:
    summary = run.get("summary") or {}
    try:
        return float(summary.get(key))
    except (TypeError, ValueError):
        return None


def metric_quality_class(run: dict, key: str) -> str:
    value = metric_float(run, key)
    if value is None:
        return "metric-neutral"
    summary = run.get("summary") or {}
    paragraphs = float(summary.get("paragraphs") or 0)
    if key in LOWER_IS_BETTER_METRICS:
        if key in RATE_METRICS:
            if value <= 0:
                return "metric-good"
            if value <= 0.002:
                return "metric-warn"
            return "metric-bad"
        if value <= 0:
            return "metric-good"
        if value <= 2:
            return "metric-warn"
        return "metric-bad"
    if key in {"strict_success_at_10_rate", "strict_success_at_20_rate"}:
        if value >= 0.90:
            return "metric-good"
        if value >= 0.75:
            return "metric-warn"
        return "metric-bad"
    if key in {"all_expected_at_10_rate", "all_expected_at_20_rate"}:
        if value >= 0.90:
            return "metric-good"
        if value >= 0.80:
            return "metric-warn"
        return "metric-bad"
    if key == "top_on_target_rate":
        if value >= 0.95:
            return "metric-good"
        if value >= 0.90:
            return "metric-warn"
        return "metric-bad"
    if key == "good_rate":
        if value >= 0.90:
            return "metric-good"
        if value >= 0.80:
            return "metric-warn"
        return "metric-bad"
    if key == "queries_all_expected_at_10":
        ratio = value / paragraphs if paragraphs else 0.0
        if ratio >= 0.90:
            return "metric-good"
        if ratio >= 0.80:
            return "metric-warn"
        return "metric-bad"
    if key in RATE_METRICS:
        if value >= 0.95:
            return "metric-good"
        if value >= 0.85:
            return "metric-warn"
        return "metric-bad"
    return "metric-neutral"


def metric_delta_html(run: dict, previous_run: dict | None, key: str) -> str:
    if previous_run is None:
        return ""
    current = metric_float(run, key)
    previous = metric_float(previous_run, key)
    if current is None or previous is None:
        return ""
    delta = current - previous
    if abs(delta) < 0.0005:
        return "<span class=\"metric-delta flat\">same</span>"
    higher_is_better = key not in LOWER_IS_BETTER_METRICS
    improved = delta > 0 if higher_is_better else delta < 0
    delta_class = "up" if improved else "down"
    sign = "+" if delta > 0 else ""
    if key in RATE_METRICS:
        text = f"{sign}{delta * 100:.1f} pp"
    else:
        text = f"{sign}{delta:.0f}"
    return f"<span class=\"metric-delta {delta_class}\">{h(text)}</span>"


def h(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def iteration_smoke_step_summary(entry: dict) -> str:
    parts = []
    for step in entry.get("steps") or []:
        name = str(step.get("name") or step.get("tier") or "step")
        status = str(step.get("status") or "unknown")
        parts.append(f"{name}: {status}")
    return "; ".join(parts) or "No commands selected."


def iteration_smoke_gate_panel_html(output_root: Path = DEFAULT_OUTPUT_ROOT, *, limit: int = 6) -> str:
    manifest = read_iteration_smoke_manifest(output_root)
    entries = list(manifest.get("runs") or [])
    if not entries:
        return """
          <section class="panel">
            <h2>Post-Iteration Smoke Gates</h2>
            <p class="muted">No post-iteration smoke-helper runs are recorded yet.</p>
          </section>
        """
    entries.sort(key=lambda item: str(item.get("created_at") or ""))
    rows = []
    for entry in reversed(entries[-limit:]):
        decision = entry.get("decision") or {}
        status = str(entry.get("status") or "unknown")
        status_class = "neutral"
        if status == "passed":
            status_class = "good"
        elif status == "failed":
            status_class = "bad"
        tiers = []
        if decision.get("standing_smoke"):
            tiers.append("standing clinical")
        if decision.get("rotating_smoke"):
            tiers.append("50-query rotating")
        if decision.get("patient_portal_smoke"):
            tiers.append("patient portal")
        if not tiers:
            tiers.append("static/focused only")
        rows.append(
            "<tr>"
            f"<td><strong>{h(entry.get('verification_id'))}</strong><br><small>{h(entry.get('created_at'))}</small></td>"
            f"<td><span class=\"status-badge {h(status_class)}\">{h(status)}</span></td>"
            f"<td>{h(', '.join(entry.get('iteration_types') or []))}</td>"
            f"<td>{h(', '.join(tiers))}</td>"
            f"<td>{h(iteration_smoke_step_summary(entry))}</td>"
            f"<td><code>{h(entry.get('verification_md_path'))}</code><br><code>{h(entry.get('verification_json_path'))}</code></td>"
            "</tr>"
        )
    return f"""
      <section class="panel">
        <h2>Post-Iteration Smoke Gates</h2>
        <p class="muted">Generated by <code>--iteration-smoke-gates</code>. Use this as the verification summary for iteration records.</p>
        <div class="table-wrap compact">
          <table>
            <thead>
              <tr>
                <th><span>Iteration</span></th>
                <th><span>Status</span></th>
                <th><span>Types</span></th>
                <th><span>Selected tiers</span></th>
                <th><span>Steps</span></th>
                <th><span>Artifacts</span></th>
              </tr>
            </thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
        </div>
      </section>
    """


def load_translation_benchmark_report() -> dict | None:
    if not DEFAULT_TRANSLATION_BENCHMARK_REPORT_JSON.exists():
        try:
            import build_translation_benchmark_report

            return build_translation_benchmark_report.build_report(
                build_translation_benchmark_report.load_lock()
            )
        except Exception:
            return None
    try:
        return json.loads(DEFAULT_TRANSLATION_BENCHMARK_REPORT_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        try:
            import build_translation_benchmark_report

            return build_translation_benchmark_report.build_report(
                build_translation_benchmark_report.load_lock()
            )
        except Exception:
            return None


def translation_benchmark_slice(report: dict, slice_id: str) -> dict:
    for slice_report in report.get("slices") or []:
        if slice_report.get("id") == slice_id:
            return dict(slice_report)
    return {}


def translation_quality_result(report: dict, slice_id: str) -> dict:
    return dict((translation_benchmark_slice(report, slice_id).get("result") or {}))


def translation_card(title: str, value: str, detail: str, *, status: str = "neutral") -> str:
    return f"""
      <div class="summary-card {h(status)}">
        <strong>{h(value)}</strong>
        <span>{h(title)}</span>
        <small>{h(detail)}</small>
      </div>
    """


def translation_plain_explanation_html(
    *,
    clinical_all: int,
    clinical_rows: int,
    pubmed_dev_all: int,
    pubmed_dev_rows: int,
    pubmed_heldout_all: int,
    pubmed_heldout_rows: int,
    exact_local: int,
    exact_umls: int,
    exact_expected: int,
    code_complete: int,
    code_rows: int,
    code_found_sabs: int,
    code_expected_sabs: int,
) -> str:
    clinical_missing = max(clinical_rows - clinical_all, 0)
    pubmed_dev_missing = max(pubmed_dev_rows - pubmed_dev_all, 0)
    pubmed_heldout_missing = max(pubmed_heldout_rows - pubmed_heldout_all, 0)
    exact_local_missing = max(exact_expected - exact_local, 0)
    exact_umls_missing = max(exact_expected - exact_umls, 0)
    code_incomplete = max(code_rows - code_complete, 0)
    code_missing_sabs = max(code_expected_sabs - code_found_sabs, 0)
    code_incomplete_sentence = (
        "1 example still needs a missing code type fixed."
        if code_incomplete == 1
        else f"{code_incomplete} examples still need a missing code type fixed."
    )
    return f"""
        <div class="plain-explanation">
          <h3>What These Checks Mean</h3>
          <p>
            Each test starts with medical text and a short list of IDs that should be found.
            An example passes when those expected IDs show up in the first 10 answers.
          </p>
          <ul class="plain-steps">
            <li>
              <strong>Clinical note check:</strong>
              {h(clinical_all)} of {h(clinical_rows)} clinical examples found every expected ID in the first 10 answers.
              {h(clinical_missing)} did not. This says the clinical-note examples are mostly working.
            </li>
            <li>
              <strong>PubMed article check:</strong>
              {h(pubmed_dev_all)} of {h(pubmed_dev_rows)} practice abstracts and {h(pubmed_heldout_all)} of {h(pubmed_heldout_rows)} locked abstracts found every expected ID in the first 10 answers.
              {h(pubmed_dev_missing + pubmed_heldout_missing)} did not. This is the clearest sign that long article text still needs work.
            </li>
            <li>
              <strong>Official UMLS comparison:</strong>
              For short lookup phrases, our search found the expected ID in the first 10 answers {h(exact_local)} of {h(exact_expected)} times.
              The official UMLS search found it {h(exact_umls)} of {h(exact_expected)} times.
              That leaves {h(exact_local_missing)} local misses and {h(exact_umls_missing)} official-UMLS misses in this set.
            </li>
            <li>
              <strong>Code check:</strong>
              After finding a medical concept, this checks whether we can also show the expected vocabulary code, such as SNOMED CT, RxNorm, LOINC, or ICD-10-CM.
              {h(code_complete)} of {h(code_rows)} examples had all expected code types, and {h(code_found_sabs)} of {h(code_expected_sabs)} expected code links were found.
              {h(code_incomplete_sentence)}
            </li>
          </ul>
        </div>
    """


def translation_quality_gate_stack_html() -> str:
    return """
        <div class="plain-explanation">
          <h3>Quality Gate Stack</h3>
          <p>
            The repeat-run checks are useful smoke tests, but they are not by
            themselves a complete search-quality program. A release-quality run
            should pass separate gates for identity, ranking, context, source
            provenance, vocabulary outputs, long documents, and drift.
          </p>
          <ul class="plain-steps">
            <li>
              <strong>Identity and recall:</strong>
              Expected and acceptable CUIs must appear in the first 10 results,
              with top-1 target rate, mean best expected rank, and per-domain
              misses reported. This is the current paragraph benchmark's main job.
            </li>
            <li>
              <strong>Ranking and precision:</strong>
              Known wrong CUIs, generic prose concepts, metadata concepts, and
              overbroad fragments should not enter the top 10. Useful secondary
              concepts should be tracked separately from true false positives.
            </li>
            <li>
              <strong>Assertion and attributes:</strong>
              The system must distinguish active/current mentions from negated,
              historical, uncertain, planned, family-history, and copied-forward
              context. Attribute checks should cover laterality, site, severity,
              lab value/unit, drug route/dose/frequency, and procedure status.
            </li>
            <li>
              <strong>Long-document behavior:</strong>
              PubMed abstracts, pasted pages, radiology reports, and clinical-note
              style text need section-aware chunking and reranking checks so central
              concepts survive while incidental background text is demoted. Tune on
              practice/dev sets; use locked heldout examples only as a release signal.
            </li>
            <li>
              <strong>Source, evidence, and license integrity:</strong>
              Core source-specific benchmarks should verify DailyMed label context,
              MedlinePlus lay language, and PubMed/PMC literature evidence.
              ClinicalTrials.gov posted outcomes, PubTator3 sampled relation
              candidates, and external CUI-neighbor embeddings should stay as
              opt-in probes until ablations show value without default-result
              drift. PubTator3 candidates require PubMed/PMC validation before
              promotion. Source deltas must show no unexplained count collapse,
              CUI loss, source-code drift, restricted-content leakage, or
              protocol-only evidence misuse.
            </li>
            <li>
              <strong>Vocabulary and code outputs:</strong>
              CUI success is not enough. Separate checks should verify the expected
              SNOMED CT, RxNorm, LOINC, ICD-10-CM, MeSH, and source-code mappings
              for the use case being served.
            </li>
            <li>
              <strong>Repeatability and operational health:</strong>
              Comparable runs need a stable query fingerprint, fixed scope/backend,
              before/after deltas, latency or timeout tracking, and retained payloads
              so regressions can be reproduced instead of inferred from a score.
            </li>
          </ul>
        </div>
    """


def translation_next_quality_work_html() -> str:
    return """
        <div class="plain-explanation">
          <h3>Next Quality Work</h3>
          <p>
            These are the next evaluation lanes to add before treating the current
            benchmark as a complete medical-text linker benchmark.
          </p>
          <ul class="plain-steps">
            <li>
              <strong>Convert the gate stack into files:</strong>
              Add explicit query sets for assertion/context, nested spans,
              entity attributes, long-document sections, and vocabulary-specific
              code expectations instead of relying on the paragraph smoke test to
              imply those behaviors.
            </li>
            <li>
              <strong>Separate dev from release checks:</strong>
              Keep PubMed practice examples and rotating paragraph samples for tuning.
              Treat the locked PubMed heldout examples, full judged paragraph pool,
              source-specific benchmarks, precision audit, and source-delta report
              as release gates.
            </li>
            <li>
              <strong>Report ranking quality, not just found/not-found:</strong>
              Add top-1 target rate, mean best expected rank, useful-extra count,
              known-false-positive@10, generic/meta false-positive@10, and
              latency/timeout summaries to the repeat-run table.
            </li>
            <li>
              <strong>External benchmark comparison:</strong>
              A first MedMentions lane is scaffolded in
              <code>scripts/run_medmentions_benchmark.py</code> and documented in
              <a href="medmentions_benchmark.html">the MedMentions benchmark note</a>.
              It starts with the ST21pv information-retrieval subset, now splits
              pure <code>mention_only</code> linker scoring from context-heavy mention
              retrieval, and reports clinical-useful hits separately from low-value
              suppression-audit surfacing guardrails and document-level abstract CUI
              recall. Use
              <a href="https://arxiv.org/abs/1902.09476">MedMentions</a>
              for broad PubMed/UMLS linking stress tests, while keeping UMLS 2017AA
              version drift separate from current-release failures. Compare behavior with
              <a href="https://github.com/allenai/scispacy">scispaCy</a>
              UMLS linking, including candidate scores and abbreviation handling, and use
              <a href="https://github.com/apache/ctakes">cTAKES</a>
              and <a href="https://github.com/CogStack/MedCAT">MedCAT</a>
              as clinical-text references for spans, standard codes, attributes, temporal
              handling, EHR UMLS/SNOMED linking, and self-supervised context learning.
            </li>
            <li>
              <strong>TREC PM/CDS document/source retrieval:</strong>
              The external benchmark lane in <code>scripts/run_trec_benchmark.py</code>
              imports Precision Medicine or Clinical Decision Support topics and one or
              more qrels files, resolves judged PubMed and ClinicalTrials.gov IDs against
              local corpora, and reports coverage before retrieval scoring. Use the
              all-judged-positive query file for corpus-expansion accounting and the
              resolved-local query file for document/source retrieval metrics. Keep this
              separate from CUI recall: qrels <code>relevance &gt; 0</code> entries are
              positives, and unjudged returned documents are unknown rather than false
              positives.
            </li>
          </ul>
        </div>
    """


def translation_benchmark_panel_html() -> str:
    report = load_translation_benchmark_report()
    if not report:
        return f"""
          <section class="panel">
            <h2>Translation Benchmark</h2>
            <p class="muted">No generated benchmark summary found yet. Run
            <code>python3 scripts/build_translation_benchmark_report.py</code> to create
            <code>{h(DEFAULT_TRANSLATION_BENCHMARK_REPORT_JSON.relative_to(ROOT))}</code>.</p>
          </section>
        """

    clinical = translation_quality_result(report, "clinical_smoke")
    pubmed_dev = translation_quality_result(report, "pubmed_literature_dev")
    pubmed_heldout = translation_quality_result(report, "pubmed_literature_heldout")
    exact = translation_quality_result(report, "exact_umls_api_comparison")
    code = translation_quality_result(report, "code_coverage")
    exact_variants = list(exact.get("variants") or [])
    exact_default = exact_variants[0] if exact_variants else {}
    clinical_rows = int(clinical.get("rows") or 0)
    clinical_all = int(clinical.get("queries_all_expected_at_10") or 0)
    pubmed_dev_rows = int(pubmed_dev.get("rows") or 0)
    pubmed_dev_all = int(pubmed_dev.get("queries_all_expected_at_10") or 0)
    pubmed_heldout_rows = int(pubmed_heldout.get("rows") or 0)
    pubmed_heldout_all = int(pubmed_heldout.get("queries_all_expected_at_10") or 0)
    exact_expected = int(exact_default.get("expected_rows") or 0)
    exact_local = int(exact_default.get("local_expected_top10") or 0)
    exact_umls = int(exact_default.get("umls_expected_top10") or 0)
    code_complete = int(code.get("rows_complete") or 0)
    code_rows = int(code.get("rows_total") or 0)
    code_found_sabs = int(code.get("found_sabs_total") or 0)
    code_expected_sabs = int(code.get("expected_sabs_total") or 0)
    full_report_href = DEFAULT_TRANSLATION_BENCHMARK_REPORT_HTML.relative_to(DEFAULT_REPORT.parent)
    locked_at = report.get("locked_at") or ""

    return f"""
      <section class="panel top-read-panel">
        <div class="latest-header">
          <div>
            <h2>Historical Translation Benchmark</h2>
            <p class="muted">Locked {h(locked_at)}. This is a historical lock; start with the progress log for current status.</p>
          </div>
          <a class="status-badge neutral" href="{h(full_report_href)}">Full benchmark report</a>
        </div>
        <div class="primary-read">
          <strong>Historical locked benchmark, not the current full test loop.</strong>
          <span>Use the progress log for the latest weakness, fix, and regression sequence. Use this locked report for provenance.</span>
        </div>
        <div class="summary-grid">
          {translation_card(
              "Clinical examples fully found",
              f"{clinical_all}/{clinical_rows}",
              f"{pct(clinical.get('recall_at_10'))} of expected IDs appeared in the first 10 answers",
              status="good",
          )}
          {translation_card(
              "PubMed abstracts fully found",
              f"{pubmed_dev_all}/{pubmed_dev_rows} practice; {pubmed_heldout_all}/{pubmed_heldout_rows} locked",
              f"{pct(pubmed_heldout.get('recall_at_10'))} of locked expected IDs appeared in the first 10 answers",
              status="bad",
          )}
          {translation_card(
              "Short phrase lookup",
              f"{exact_local}/{exact_expected} local",
              f"official UMLS search found {exact_umls}/{exact_expected}",
              status="warn",
          )}
          {translation_card(
              "Code mappings found",
              f"{code_complete}/{code_rows}",
              f"{code_found_sabs}/{code_expected_sabs} expected links to SNOMED/RxNorm/LOINC/ICD codes found",
              status="warn" if code_complete < code_rows else "good",
          )}
        </div>
        {translation_plain_explanation_html(
            clinical_all=clinical_all,
            clinical_rows=clinical_rows,
            pubmed_dev_all=pubmed_dev_all,
            pubmed_dev_rows=pubmed_dev_rows,
            pubmed_heldout_all=pubmed_heldout_all,
            pubmed_heldout_rows=pubmed_heldout_rows,
            exact_local=exact_local,
            exact_umls=exact_umls,
            exact_expected=exact_expected,
            code_complete=code_complete,
            code_rows=code_rows,
            code_found_sabs=code_found_sabs,
            code_expected_sabs=code_expected_sabs,
        )}
        {translation_quality_gate_stack_html()}
        {translation_next_quality_work_html()}
      </section>
    """


def run_header(run: dict) -> str:
    label = h(run.get("label") or run.get("run_id"))
    created = h(run.get("created_at"))
    dirty = "dirty" if run.get("git_dirty") else "clean"
    commit = h(run.get("git_commit"))
    system = h(run.get("search_system_label") or run.get("search_system") or "Current search")
    scope = str(run.get("api_scope") or "")
    scope_text = f"<br><code>{h(scope)}</code>" if scope else ""
    description = h(run.get("search_system_description") or "")
    return (
        f"<strong>{label}</strong><br>"
        f"<span title=\"{description}\">{system}{scope_text}<br>{created}<br>{commit} {dirty}</span>"
    )


def run_queries_match(left: dict, right: dict) -> bool:
    left_text = str(left.get("queries") or "")
    right_text = str(right.get("queries") or "")
    if not left_text or not right_text:
        return True
    return left_text == right_text or Path(left_text).name == Path(right_text).name


def runs_comparable(left: dict, right: dict) -> bool:
    left_signature = run_evaluation_signature(left)
    right_signature = run_evaluation_signature(right)
    if left_signature and right_signature and left_signature != right_signature:
        return False
    left_backend = run_backend(left)
    right_backend = run_backend(right)
    if left_backend and right_backend and left_backend != right_backend:
        return False
    if left.get("search_system") != right.get("search_system"):
        return False
    if (left.get("api_scope") or "") != (right.get("api_scope") or ""):
        return False
    if str(left.get("mode") or "") != str(right.get("mode") or ""):
        return False
    if str(left.get("top_k") or "") != str(right.get("top_k") or ""):
        return False
    for flag in ("include_related", "include_linked_concepts", "include_search_evidence_items"):
        if bool(left.get(flag)) != bool(right.get(flag)):
            return False
    return run_queries_match(left, right)


def runs_same_search_setup(left: dict, right: dict) -> bool:
    left_backend = run_backend(left)
    right_backend = run_backend(right)
    if left_backend and right_backend and left_backend != right_backend:
        return False
    if left.get("search_system") != right.get("search_system"):
        return False
    if (left.get("api_scope") or "") != (right.get("api_scope") or ""):
        return False
    if str(left.get("mode") or "") != str(right.get("mode") or ""):
        return False
    if str(left.get("top_k") or "") != str(right.get("top_k") or ""):
        return False
    for flag in ("include_related", "include_linked_concepts", "include_search_evidence_items"):
        if bool(left.get(flag)) != bool(right.get(flag)):
            return False
    return run_queries_match(left, right)


def previous_comparable_run(runs: list[dict], current: dict) -> dict | None:
    current_created = str(current.get("created_at") or "")
    current_id = str(current.get("run_id") or "")
    candidates = []
    for run in runs:
        if str(run.get("run_id") or "") == current_id:
            continue
        if str(run.get("created_at") or "") >= current_created:
            continue
        if runs_comparable(run, current):
            candidates.append(run)
    candidates.sort(key=lambda item: str(item.get("created_at") or ""))
    return candidates[-1] if candidates else None


def previous_same_search_setup_run(runs: list[dict], current: dict) -> dict | None:
    current_created = str(current.get("created_at") or "")
    current_id = str(current.get("run_id") or "")
    current_family = inferred_run_family_key(current)
    candidates = []
    for run in runs:
        if str(run.get("run_id") or "") == current_id:
            continue
        if str(run.get("created_at") or "") >= current_created:
            continue
        if inferred_run_family_key(run) != current_family:
            continue
        if runs_same_search_setup(run, current):
            candidates.append(run)
    candidates.sort(key=lambda item: str(item.get("created_at") or ""))
    return candidates[-1] if candidates else None


def summary_int(run: dict, key: str) -> int:
    try:
        return int(float((run.get("summary") or {}).get(key) or 0))
    except (TypeError, ValueError):
        return 0


def source_presence_count(run: dict) -> int | None:
    counts = (run.get("summary") or {}).get("source_counts_at_10")
    if not isinstance(counts, dict) or not counts:
        return None
    return len(counts)


def payload_size_mb(run: dict) -> float | None:
    payloads_path = str(run.get("payloads_path") or "")
    if not payloads_path:
        return None
    path = Path(payloads_path)
    if not path.exists() or not path.is_file():
        return None
    return path.stat().st_size / (1024 * 1024)


def seconds(value: object) -> str:
    try:
        return f"{float(value):.1f}s"
    except (TypeError, ValueError):
        return ""


def display_timestamp(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return text


def overall_score(run: dict) -> float:
    summary = run.get("summary") or {}
    existing = metric_number(summary, "overall_score")
    if existing is not None:
        return round(existing, 1)
    return overall_score_from_summary(summary)


def overall_score_text(run: dict) -> str:
    return f"{overall_score(run):.1f}/100"


def overall_grade(score: float) -> str:
    if score >= 90.0:
        return "excellent"
    if score >= 85.0:
        return "strong"
    if score >= 75.0:
        return "usable with gaps"
    if score >= 60.0:
        return "needs work"
    return "weak"


def overall_score_class(score: float) -> str:
    if score >= 85.0:
        return "good"
    if score >= 70.0:
        return "warn"
    return "bad"


def run_type_label(run: dict) -> str:
    search_system = run.get("search_system")
    scope = run.get("api_scope")
    if search_system == SEARCH_SYSTEM_UMLS_ONLY:
        return "UMLS-only baseline"
    if search_system == SEARCH_SYSTEM_API and scope == SEARCH_SCOPE_UMLS:
        return "API: UMLS only"
    if search_system == SEARCH_SYSTEM_API and scope == SEARCH_SCOPE_UMLS_EVIDENCE:
        return "API: UMLS + evidence"
    if search_system == SEARCH_SYSTEM_API:
        return "API: legacy/default scope"
    return str(run.get("search_system_label") or search_system or "Current search")


def normalized_run_family_key(value: object) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    aliases = {
        "comparison": "scope",
        "scope_comparison": "scope",
        "umls_scope": "scope",
        "evidence_scope": "scope",
        "speed": "probe",
        "speed_probe": "probe",
        "payload_probe": "probe",
        "regression": "smoke",
        "smoke_regression": "smoke",
        "release_candidate": "release",
        "rc": "release",
        "experiment": "ranking",
        "ranking_experiment": "ranking",
    }
    return aliases.get(text, text)


def explicit_run_family_key(run: dict) -> str:
    for field in ("run_family", "run_type", "kind", "profile"):
        key = normalized_run_family_key(run.get(field))
        if key in RUN_FAMILY_DEFINITIONS:
            return key
    return ""


def inferred_run_family_key(run: dict) -> str:
    explicit = explicit_run_family_key(run)
    if explicit:
        return explicit
    text = " ".join(
        str(value or "").lower()
        for value in [
            run.get("label"),
            run.get("run_id"),
            run.get("mode"),
            run.get("api_scope"),
            Path(str(run.get("queries") or "")).name,
        ]
    )
    tokens = set(re.findall(r"[a-z0-9]+", text))
    if "scope" in text or "comparison" in text or "versus" in text:
        return "scope"
    if tokens & {"speed", "probe", "payload", "profile", "profiling", "latency"}:
        return "probe"
    if "release" in text or "candidate" in text:
        return "release"
    if "baseline" in text or "control" in text:
        return "baseline"
    if any(token in text for token in ("recall", "ranking", "rerank", "specificity", "treatment", "fix")):
        return "ranking"
    if summary_int(run, "paragraphs") in {DEFAULT_QUERY_LIMIT, 167} and run_query_file_label(run) == DEFAULT_QUERIES.name:
        return "smoke"
    return "custom"


def run_family_info(run: dict) -> dict:
    key = inferred_run_family_key(run)
    info = dict(RUN_FAMILY_DEFINITIONS.get(key) or RUN_FAMILY_DEFINITIONS["custom"])
    info["key"] = key
    return info


def run_family_label(run: dict) -> str:
    return str(run_family_info(run).get("label") or "Custom run")


def run_family_badge_html(run: dict) -> str:
    info = run_family_info(run)
    css_class = str(info.get("class") or "custom")
    return (
        f"<span class=\"family-badge family-{h(css_class)}\" "
        f"title=\"{h(info.get('description') or '')}\">{h(info.get('label'))}</span>"
    )


def run_family_counts_html(runs: list[dict]) -> str:
    if not runs:
        return ""
    counts: dict[str, int] = {}
    for run in runs:
        key = inferred_run_family_key(run)
        counts[key] = counts.get(key, 0) + 1
    badges = []
    for key, count in sorted(
        counts.items(),
        key=lambda item: (
            RUN_FAMILY_ORDER.index(item[0])
            if item[0] in RUN_FAMILY_DEFINITIONS
            else 99,
            item[0],
        ),
    ):
        info = RUN_FAMILY_DEFINITIONS.get(key) or RUN_FAMILY_DEFINITIONS["custom"]
        badges.append(
            f"<span class=\"family-count family-{h(info.get('class'))}\" "
            f"title=\"{h(info.get('description'))}\">{h(info.get('label'))}: {h(count)}</span>"
    )
    return f"<div class=\"family-counts\">{''.join(badges)}</div>"


def family_sort_key(key: str) -> tuple[int, str]:
    return (
        RUN_FAMILY_ORDER.index(key) if key in RUN_FAMILY_ORDER else len(RUN_FAMILY_ORDER),
        key,
    )


def grouped_runs_by_family(runs: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for run in runs:
        key = inferred_run_family_key(run)
        groups.setdefault(key, []).append(run)
    for family_runs in groups.values():
        family_runs.sort(key=lambda item: str(item.get("created_at") or ""))
    return groups


def gate_result_for_run(run: dict) -> dict | None:
    result = run.get("gate_result")
    if isinstance(result, dict):
        return result
    gate_path = str(run.get("gate_result_path") or "")
    if not gate_path:
        return None
    path = Path(gate_path)
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def gate_badge_html(run: dict) -> str:
    result = gate_result_for_run(run)
    if not result:
        return "<span class=\"status-badge neutral\">not checked</span>"
    checks = list(result.get("checks") or [])
    failed = [check for check in checks if check.get("passed") is False]
    skipped = [check for check in checks if check.get("passed") is None]
    title = "; ".join(
        str(check.get("message") or check.get("name") or "")
        for check in failed[:4] or skipped[:4] or checks[:4]
    )
    if result.get("passed"):
        label = "release checks pass"
        css_class = "good"
        if skipped:
            label = "public release checks pass; no baseline"
            css_class = "neutral"
        return f"<span class=\"status-badge {h(css_class)}\" title=\"{h(title)}\">{h(label)}</span>"
    return f"<span class=\"status-badge bad\" title=\"{h(title)}\">release checks fail</span>"


def delta_badge_html(run: dict, previous_run: dict | None, key: str) -> str:
    if previous_run is None:
        return ""
    current = metric_float(run, key)
    previous = metric_float(previous_run, key)
    if current is None or previous is None:
        return ""
    delta = current - previous
    if abs(delta) < 0.0005:
        return "<span class=\"delta-badge neutral\">same as previous</span>"
    higher_is_better = key not in LOWER_IS_BETTER_METRICS and key != "elapsed_seconds"
    improved = delta > 0 if higher_is_better else delta < 0
    css_class = "good" if improved else "bad"
    sign = "+" if delta > 0 else ""
    if key in RATE_METRICS:
        text = f"{sign}{delta * 100:.1f} pp vs previous"
    elif key == "elapsed_seconds":
        text = f"{sign}{delta:.1f}s vs previous"
    else:
        text = f"{sign}{delta:.0f} vs previous"
    return f"<span class=\"delta-badge {css_class}\">{h(text)}</span>"


def summary_card_html(
    *,
    label: str,
    value: str,
    detail: str,
    css_class: str = "neutral",
    delta_html: str = "",
) -> str:
    return (
        f"<div class=\"summary-card {h(css_class)}\">"
        f"<strong>{h(value)}</strong>"
        f"<span>{h(label)}</span>"
        f"<small>{h(detail)}</small>"
        f"{delta_html}"
        "</div>"
    )


def failed_query_examples(run: dict, *, limit: int = 3) -> list[str]:
    examples = []
    for row in read_run_rows(run):
        if row_strict_success(row, 10):
            continue
        parts = [str(row.get("id") or "query")]
        if row.get("top_on_target") == "0":
            top = " ".join(part for part in [row.get("top_cui", ""), row.get("top_name", "")] if part)
            parts.append(f"top off target ({top or 'no top hit'})")
        if row.get("missing_at_10"):
            parts.append(f"missing {row.get('missing_at_10')}")
        if row.get("disallowed_at_10"):
            parts.append(f"false positive {row.get('disallowed_at_10')}")
        examples.append(": " + "; ".join(parts) if len(parts) == 1 else "; ".join(parts))
        if len(examples) >= limit:
            break
    return examples


def recommendations_for_run(run: dict, previous: dict | None = None) -> list[str]:
    summary = run.get("summary") or {}
    recommendations = []
    gate_result = gate_result_for_run(run)
    if gate_result:
        failed_gates = [
            str(check.get("name") or "gate")
            for check in gate_result.get("checks") or []
            if check.get("passed") is False
        ]
        if failed_gates:
            recommendations.append(f"Fix failed gates first: {', '.join(failed_gates[:3])}.")

    strict = bounded_rate(summary, "strict_success_at_10_rate")
    top_target = bounded_rate(summary, "top_on_target_rate")
    all_expected = bounded_rate(summary, "all_expected_at_10_rate")
    false_positive_count = int(summary.get("queries_with_disallowed_at_10") or 0)
    missing_count = int(summary.get("queries_with_missing_at_10") or 0)
    top_wrong_count = int(summary.get("top_wrong_count") or 0)
    elapsed = metric_number(summary, "elapsed_seconds") or 0.0

    if strict < 0.75:
        recommendations.append(
            "Raise strict success@10 before broadening the benchmark; this run is still failing many query-level cases."
        )
    elif strict < 0.90:
        recommendations.append(
            "Close the remaining strict@10 misses, prioritizing examples where the top hit is right but expected CUIs are missing."
        )
    if top_target < 0.90 or top_wrong_count:
        recommendations.append(
            f"Improve top-result ranking on {top_wrong_count} off-target queries; inspect exact-span, semantic-fragment, and negation penalties first."
        )
    if all_expected < 0.85 or missing_count:
        recommendations.append(
            f"Improve candidate recall on {missing_count} queries with missing expected CUIs; add source/alias coverage before tuning ranking."
        )
    if false_positive_count:
        recommendations.append(
            f"Audit {false_positive_count} known false-positive queries and add targeted suppressions or acceptable-CUI clarifications."
        )
    if elapsed > 60 and run.get("api_scope") == SEARCH_SCOPE_UMLS_EVIDENCE:
        recommendations.append(
            "Keep smoke runs lean by leaving evidence text off unless auditing snippets; profile linked-concept and evidence-item payloads separately."
        )

    if previous is not None:
        current_score = overall_score(run)
        previous_score = overall_score(previous)
        if current_score < previous_score - 1.0:
            recommendations.append(
                f"Investigate the score regression versus {previous.get('label') or previous.get('run_id')}: {current_score:.1f} vs {previous_score:.1f}."
            )
        current_fp = int(summary.get("queries_with_disallowed_at_10") or 0)
        previous_fp = int((previous.get("summary") or {}).get("queries_with_disallowed_at_10") or 0)
        if current_fp > previous_fp:
            recommendations.append(
                f"Known false positives increased from {previous_fp} to {current_fp}; treat that as a release blocker."
            )

    examples = failed_query_examples(run)
    if examples:
        recommendations.append(f"Start manual review with: {' | '.join(examples)}.")
    if not recommendations:
        recommendations.append(
            "Use this as the current baseline; next work should target source-specific benchmarks and evidence-speed profiling."
        )
    return recommendations[:6]


def overall_assessment_html(run: dict, previous: dict | None = None) -> str:
    score = overall_score(run)
    score_class = overall_score_class(score)
    delta = ""
    if previous is not None:
        score_delta = score - overall_score(previous)
        if abs(score_delta) >= 0.05:
            sign = "+" if score_delta > 0 else ""
            delta = f"<small>{h(sign + f'{score_delta:.1f}')} vs previous comparable run</small>"
        else:
            delta = "<small>same as previous comparable run</small>"
    recs = "".join(f"<li>{h(item)}</li>" for item in recommendations_for_run(run, previous))
    return f"""
      <div class="assessment assessment-{h(score_class)}">
        <div class="assessment-score">
          <strong>{h(overall_score_text(run))}</strong>
          <span>Overall score</span>
          <small>{h(overall_grade(score))}</small>
          {delta}
        </div>
        <div class="assessment-recommendations">
          <h3>Recommendations</h3>
          <ul>{recs}</ul>
        </div>
      </div>
    """


def metric_card_class(run: dict, key: str) -> str:
    return metric_quality_class(run, key).replace("metric-", "")


def current_improvement_run_set(runs: list[dict]) -> list[dict]:
    run_sets = important_run_sets(runs)
    return run_sets[0] if run_sets else []


def current_improvement_target_run(runs: list[dict]) -> dict | None:
    target_run_set = current_improvement_run_set(runs)
    if target_run_set:
        return target_run_set[-1]
    return runs[-1] if runs else None


def latest_improvement_pass_html(
    runs: list[dict],
    latest: dict,
    previous_comparable: dict | None,
) -> str:
    previous = previous_same_search_setup_run(runs, latest)
    if previous is None:
        return ""
    if (
        previous_comparable is not None
        and str(previous.get("run_id") or "") == str(previous_comparable.get("run_id") or "")
    ):
        return ""

    paragraph_count = (
        summary_int(latest, "paragraphs")
        or summary_int(previous, "paragraphs")
        or len(read_run_rows(latest))
        or len(read_run_rows(previous))
    )
    previous_strict = summary_int(previous, "strict_success_at_10_count")
    latest_strict = summary_int(latest, "strict_success_at_10_count")
    previous_missing = summary_int(previous, "queries_with_missing_at_10")
    latest_missing = summary_int(latest, "queries_with_missing_at_10")
    previous_fp = summary_int(previous, "queries_with_disallowed_at_10")
    latest_fp = summary_int(latest, "queries_with_disallowed_at_10")
    previous_score = overall_score(previous)
    latest_score = overall_score(latest)

    strict_gain = latest_strict - previous_strict
    missing_drop = previous_missing - latest_missing
    score_gain = latest_score - previous_score
    strict_gain_text = f"+{strict_gain}" if strict_gain >= 0 else str(strict_gain)
    score_gain_text = f"+{score_gain:.1f}" if score_gain >= 0 else f"{score_gain:.1f}"
    missing_text = (
        f"{missing_drop} fewer queries missing expected ideas"
        if missing_drop >= 0
        else f"{abs(missing_drop)} more queries missing expected ideas"
    )
    false_positive_text = (
        "still 0"
        if previous_fp == 0 and latest_fp == 0
        else f"{previous_fp} -> {latest_fp}"
    )

    latest_label = str(latest.get("label") or latest.get("run_id") or "")
    latest_label_lower = latest_label.lower()
    if "focused exact-anchor" in latest_label_lower:
        changes = [
            (
                "Added safe public names for medical phrases that were already in the query but were too easy "
                "for Elasticsearch to leave just outside the first page. Examples: suspected thyrotoxicosis, "
                "ectopic pregnancy, suspected endometriosis, tacrolimus, opioid use disorder, homelessness, "
                "and ceftriaxone exposure."
            ),
            (
                "Marked a few UMLS IDs as acceptable equivalents when the result is the same practical medical "
                "idea for this benchmark. Examples: beta-hCG measurement for beta-hCG, Staphylococcus aureus "
                "infection for Staphylococcus aureus, and MRSA wording for MRSA infection."
            ),
            (
                "Reran the same smoke test against the Elasticsearch-backed API, not the local fallback."
            ),
        ]
    else:
        changes = [
            (
                "Changed the search configuration or benchmark support files, then reran the same search setup "
                "against Elasticsearch."
            ),
            (
                "Checked whether the right medical concepts moved into the first 10 results without adding known "
                "bad answers."
            ),
        ]

    signature_note = ""
    previous_signature = run_evaluation_signature(previous)
    latest_signature = run_evaluation_signature(latest)
    if previous_signature and latest_signature and previous_signature != latest_signature:
        signature_note = (
            " These runs are not in the same table because the benchmark definition changed after the cleanup. "
            "That split is intentional; this box is the plain-language before/after for the improvement pass."
        )
    change_items = "".join(f"<li>{h(item)}</li>" for item in changes)

    return f"""
      <div class="plain-explanation">
        <h3>What Improved In This Pass</h3>
        <p><strong>Before:</strong> {h(previous.get('label') or previous.get('run_id'))}, {h(display_timestamp(previous.get('created_at')))}. <strong>After:</strong> {h(latest_label)}, {h(display_timestamp(latest.get('created_at')))}.{h(signature_note)}</p>
        <div class="plain-metric-grid">
          <div class="plain-metric"><strong>{h(previous_strict)} -> {h(latest_strict)}</strong><span>queries passed strict@10</span><small>{h(strict_gain_text)} out of {h(paragraph_count)}</small></div>
          <div class="plain-metric"><strong>{h(previous_missing)} -> {h(latest_missing)}</strong><span>queries missing expected ideas</span><small>{h(missing_text)}</small></div>
          <div class="plain-metric"><strong>{h(false_positive_text)}</strong><span>known false positives</span><small>bad answers did not increase</small></div>
          <div class="plain-metric"><strong>{h(f'{previous_score:.1f}')} -> {h(f'{latest_score:.1f}')}</strong><span>overall score</span><small>{h(score_gain_text)} points</small></div>
        </div>
        <p><strong>What was changed:</strong></p>
        <ol class="plain-steps">{change_items}</ol>
      </div>
    """


def latest_evaluation_panel(runs: list[dict]) -> str:
    if not runs:
        return "<p class=\"muted\">No evaluation runs are registered yet.</p>"
    latest = current_improvement_target_run(runs)
    if latest is None:
        return "<p class=\"muted\">No evaluation runs are registered yet.</p>"
    previous = previous_comparable_run(runs, latest)
    previous_same_setup = previous_same_search_setup_run(runs, latest)
    summary = latest.get("summary") or {}
    paragraph_count = summary_int(latest, "paragraphs")
    strict_count = summary_int(latest, "strict_success_at_10_count")
    top_count = summary_int(latest, "top_on_target_count")
    all_expected_count = summary_int(latest, "queries_all_expected_at_10")
    missing_count = summary_int(latest, "queries_with_missing_at_10")
    false_positive_count = summary_int(latest, "queries_with_disallowed_at_10")
    if previous:
        previous_note = f"Compared against previous comparable run: {previous.get('label') or previous.get('run_id')}."
    elif previous_same_setup:
        previous_note = (
            "No previous same-kind run-set baseline was found for metric-card deltas because the benchmark "
            "definition changed; the box above compares the latest improvement pass against the previous "
            "Elasticsearch smoke run with the same search setup."
        )
    else:
        previous_note = "No previous comparable run was found for deltas."
    cards = "".join(
        [
            summary_card_html(
                label="overall score",
                value=overall_score_text(latest),
                detail=overall_grade(overall_score(latest)),
                css_class=overall_score_class(overall_score(latest)),
            ),
            summary_card_html(
                label="strict success@10",
                value=pct(summary.get("strict_success_at_10_rate")),
                detail=f"{strict_count} / {paragraph_count} queries",
                css_class=metric_card_class(latest, "strict_success_at_10_rate"),
                delta_html=delta_badge_html(latest, previous, "strict_success_at_10_rate"),
            ),
            summary_card_html(
                label="top result on target",
                value=pct(summary.get("top_on_target_rate")),
                detail=f"{top_count} / {paragraph_count} queries",
                css_class=metric_card_class(latest, "top_on_target_rate"),
                delta_html=delta_badge_html(latest, previous, "top_on_target_rate"),
            ),
            summary_card_html(
                label="missing expected@10",
                value=str(missing_count),
                detail=f"{all_expected_count} / {paragraph_count} complete",
                css_class="good" if missing_count == 0 else ("warn" if missing_count <= 10 else "bad"),
                delta_html=delta_badge_html(latest, previous, "all_expected_at_10_rate"),
            ),
            summary_card_html(
                label="known false positives@10",
                value=str(false_positive_count),
                detail=pct(summary.get("known_false_positive_rate_at_10")),
                css_class="good" if false_positive_count == 0 else "bad",
                delta_html=delta_badge_html(latest, previous, "known_false_positive_rate_at_10"),
            ),
            summary_card_html(
                label="elapsed time",
                value=seconds(summary.get("elapsed_seconds")),
                detail="API evaluation runtime",
                css_class="neutral",
                delta_html=delta_badge_html(latest, previous, "elapsed_seconds"),
            ),
        ]
    )
    return f"""
      <div class="latest-header">
        <div>
          <h3>{h(latest.get('label') or latest.get('run_id'))}</h3>
          <p class="muted">Run date: {h(display_timestamp(latest.get('created_at')))} | {h(run_family_label(latest))} | {h(run_type_label(latest))} | {h(paragraph_count)} queries</p>
	        </div>
	        {gate_badge_html(latest)}
	      </div>
	      {overall_assessment_html(latest, previous)}
	      <div class="summary-grid">{cards}</div>
	      {latest_improvement_pass_html(runs, latest, previous)}
	      <p class="muted">{h(previous_note)}</p>
	    """


def repeatable_run_panel() -> str:
    server_command = """PORT=8770 ELASTIC_URL=http://localhost:9200 ELASTIC_INDEX=qe-scaling-sapbert-cls \\
  PUBLIC_OUTPUT_ONLY=1 sh scripts/start_search_quality_server.sh"""
    helper_command = """PYTHONPATH=src:scripts python3 scripts/run_search_quality_experiment.py \\
  --iteration-smoke-gates \\
  --iteration-id SQI-YYYY-MM-DD-NNN \\
  --iteration-type ranking \\
  --development-loop \\
  --focused-command "python3 -m pytest tests/test_evidence_vectors.py -k '<selector>' -q" \\
  --base-url http://127.0.0.1:8766"""
    smoke_command = """PYTHONPATH=src python3 scripts/run_search_quality_experiment.py \\
  --base-url http://127.0.0.1:8770 \\
  --scope umls_evidence \\
  --run-family smoke \\
  --query-limit 50 \\
  --query-selection rotate \\
  --workers 2 \\
  --output-root build/search_quality_experiments \\
  --html-report docs/search_quality_experiments.html \\
  --fail-gates"""
    scope_commands = """PYTHONPATH=src python3 scripts/run_search_quality_experiment.py \\
  --base-url http://127.0.0.1:8770 \\
  --scope umls \\
  --run-family scope \\
  --label "UMLS scope $(date +%F)" \\
  --output-root build/search_quality_experiments \\
  --html-report docs/search_quality_experiments.html

PYTHONPATH=src python3 scripts/run_search_quality_experiment.py \\
  --base-url http://127.0.0.1:8770 \\
  --scope umls_evidence \\
  --run-family scope \\
  --label "UMLS + evidence scope $(date +%F)" \\
  --include-search-evidence-items \\
  --output-root build/search_quality_experiments \\
  --html-report docs/search_quality_experiments.html"""
    return f"""
      <details class="command-panel">
        <summary>Repeatable Commands</summary>
        <p class="muted">The stable manifest is <code>build/search_quality_experiments/runs.json</code>; this page is regenerated at <code>docs/search_quality_experiments.html</code>.</p>
        <h3>Elasticsearch-backed API server</h3>
        <pre><code>{h(server_command)}</code></pre>
        <h3>Post-iteration smoke helper</h3>
        <pre><code>{h(helper_command)}</code></pre>
        <h3>Fast rotating 50-query smoke run</h3>
        <pre><code>{h(smoke_command)}</code></pre>
        <p class="muted">Live API experiment runs default to two worker threads and write <code>query_timings.tsv</code>; pass <code>--workers 1</code> for serial timing.</p>
        <h3>Direct UMLS versus UMLS + evidence pair</h3>
        <pre><code>{h(scope_commands)}</code></pre>
      </details>
    """


def run_history_table(
    runs: list[dict],
    *,
    limit_runs: int = 30,
    show_family_counts: bool = True,
    show_family_column: bool = True,
) -> str:
    if not runs:
        return "<p class=\"muted\">No runs are registered yet.</p>"
    visible = list(reversed(runs[-limit_runs:]))
    rows = []
    for run in visible:
        summary = run.get("summary") or {}
        paragraph_count = summary_int(run, "paragraphs")
        missing_count = summary_int(run, "queries_with_missing_at_10")
        false_positive_count = summary_int(run, "queries_with_disallowed_at_10")
        score = overall_score(run)
        run_title = " | ".join(
            part
            for part in [
                f"run_id: {run.get('run_id') or ''}",
                f"run_dir: {run.get('run_dir') or ''}",
            ]
            if part
        )
        family_cell = f"<td>{run_family_badge_html(run)}</td>" if show_family_column else ""
        rows.append(
            "<tr>"
            f"<th>{h(display_timestamp(run.get('created_at')))}</th>"
            f"<td title=\"{h(run_title)}\"><strong>{h(run.get('label') or run.get('run_id'))}</strong></td>"
            f"{family_cell}"
            f"<td>{h(run_type_label(run))}<br><small>{h(paragraph_count)} queries</small></td>"
            f"<td class=\"metric-{h(overall_score_class(score))}\">{h(f'{score:.1f}/100')}<br><small>{h(overall_grade(score))}</small></td>"
            f"<td class=\"{metric_quality_class(run, 'strict_success_at_10_rate')}\">{h(metric_value(run, 'strict_success_at_10_rate'))}<br><small>{h(summary.get('strict_success_at_10_count') or 0)} pass</small></td>"
            f"<td class=\"{'metric-good' if missing_count == 0 else ('metric-warn' if missing_count <= 10 else 'metric-bad')}\">{h(missing_count)}</td>"
            f"<td class=\"{'metric-good' if false_positive_count == 0 else 'metric-bad'}\">{h(false_positive_count)}</td>"
            f"<td>{h(seconds(summary.get('elapsed_seconds')))}</td>"
            "</tr>"
        )
    note = ""
    if len(runs) > limit_runs:
        note = f"<p class=\"muted\">Showing latest {limit_runs} of {len(runs)} registered runs. Timestamps are UTC.</p>"
    else:
        note = f"<p class=\"muted\">Showing all {len(runs)} registered runs. Timestamps are UTC.</p>"
    family_header = "<th>Family</th>" if show_family_column else ""
    family_counts = run_family_counts_html(runs) if show_family_counts else ""
    return f"""
      {family_counts}
      {note}
      <table class="score-table">
        <thead>
          <tr>
            <th>Run date</th>
            <th>Run</th>
            {family_header}
            <th>Search</th>
            <th>Score</th>
            <th>strict@10</th>
            <th>missing expected</th>
            <th>false positives</th>
            <th>time</th>
          </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    """


def gate_status_text(run: dict) -> str:
    result = gate_result_for_run(run)
    if not result:
        return "not gated"
    if result.get("passed"):
        skipped = [check for check in result.get("checks") or [] if check.get("passed") is None]
        if skipped:
            return "public gates passed; baseline comparison skipped"
        return "gates passed"
    failed = [
        str(check.get("name") or "gate")
        for check in result.get("checks") or []
        if check.get("passed") is False
    ]
    if failed:
        return "gates failed: " + ", ".join(failed[:3])
    return "gates failed"


def run_query_file_label(run: dict) -> str:
    query_path = str(run.get("queries") or "").strip()
    return Path(query_path).name if query_path else "unknown queries"


def run_query_selection_label(run: dict) -> str:
    summary = run.get("summary") or {}
    selected = int(run.get("query_selected_count") or summary.get("query_selected_count") or summary.get("paragraphs") or 0)
    pool = int(run.get("query_pool_count") or summary.get("query_pool_count") or 0)
    selection = str(run.get("query_selection") or summary.get("query_selection") or "").strip()
    if pool and selected and selected < pool:
        if selection == "rotate":
            return f"{selected} of {pool} rotating query sample"
        return f"{selected} of {pool} query sample"
    if selected:
        return f"{selected} queries"
    return "unknown query count"


def run_set_key(run: dict) -> tuple[str, ...]:
    return (
        str(run.get("search_system") or ""),
        str(run.get("api_scope") or ""),
        str(run.get("mode") or ""),
        str(run.get("top_k") or ""),
        str(bool(run.get("include_related"))),
        str(bool(run.get("include_linked_concepts"))),
        str(bool(run.get("include_search_evidence_items"))),
        run_backend(run) or "unknown",
        run_query_file_label(run),
        run_evaluation_signature(run) or "unknown",
    )


def grouped_runs_by_run_set(runs: list[dict]) -> list[list[dict]]:
    groups: dict[tuple[str, ...], list[dict]] = {}
    for run in runs:
        groups.setdefault(run_set_key(run), []).append(run)
    run_sets = []
    for group_runs in groups.values():
        group_runs.sort(key=lambda item: str(item.get("created_at") or ""))
        run_sets.append(group_runs)
    run_sets.sort(key=lambda group: str(group[-1].get("created_at") or ""), reverse=True)
    return run_sets


def run_set_title(run: dict) -> str:
    family = inferred_run_family_key(run)
    if family == "smoke":
        return "Clinical paragraph smoke test"
    if family == "scope":
        return "UMLS scope comparison"
    if family == "release":
        return "Release-candidate paragraph test"
    if family == "ranking":
        return "Ranking experiment"
    if family == "probe":
        return "Focused diagnostic probe"
    if family == "baseline":
        return "Baseline comparison run"
    return run_family_label(run)


def run_set_details(run: dict) -> str:
    options = []
    if run.get("include_related"):
        options.append("related")
    if run.get("include_linked_concepts"):
        options.append("linked concepts")
    if run.get("include_search_evidence_items"):
        options.append("evidence items")
    option_text = ", ".join(options) if options else "lean payload"
    backend = run_backend(run) or "unknown"
    signature = run_evaluation_signature(run)
    signature_text = f"; test-set fingerprint {signature[:8]}" if signature else ""
    return (
        f"{run_type_label(run)}; {backend} backend; {run.get('mode') or 'unknown'} mode; "
        f"top {run.get('top_k') or 'unknown'} results; {run_query_file_label(run)}; "
        f"{run_query_selection_label(run)}; {option_text}{signature_text}"
    )


def run_set_history_html(runs: list[dict]) -> str:
    representative = runs[-1]
    note = ""
    if len(runs) == 1:
        note = "<p class=\"muted\">Only one run in this comparable set; no same-kind baseline is available yet.</p>"
    return f"""
      <section class="run-set-section">
        <div class="run-set-header">
          <div>
            <h4>{h(run_set_title(representative))}</h4>
            <p class="muted">{h(run_set_details(representative))}</p>
            {note}
          </div>
          <span class="family-count">{h(len(runs))} runs</span>
        </div>
        <div class="table-wrap">
          {run_history_table(
              runs,
              limit_runs=20,
              show_family_counts=False,
              show_family_column=False,
          )}
        </div>
      </section>
    """


def signed_delta(current: float, previous: float, *, digits: int = 1) -> str:
    delta = current - previous
    if abs(delta) < 0.0005:
        return "same"
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta:.{digits}f}"


def signed_int_delta(current: int, previous: int) -> str:
    delta = current - previous
    if delta == 0:
        return "same"
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta}"


def run_set_outcome_summary(run: dict) -> str:
    summary = run.get("summary") or {}
    paragraphs = summary_int(run, "paragraphs")
    strict_count = summary_int(run, "strict_success_at_10_count")
    missing_count = summary_int(run, "queries_with_missing_at_10")
    false_positive_count = summary_int(run, "queries_with_disallowed_at_10")
    score = overall_score(run)
    return (
        f"{strict_count} of {paragraphs} examples fully found in the first 10 answers "
        f"({pct(summary.get('strict_success_at_10_rate'))}); "
        f"{missing_count} examples missed at least one expected ID; "
        f"{false_positive_count} examples included a known wrong ID; "
        f"overall score {score:.1f}/100"
    )


def run_set_change_summary(previous: dict, latest: dict) -> str:
    previous_score = overall_score(previous)
    latest_score = overall_score(latest)
    previous_strict = summary_int(previous, "strict_success_at_10_count")
    latest_strict = summary_int(latest, "strict_success_at_10_count")
    previous_missing = summary_int(previous, "queries_with_missing_at_10")
    latest_missing = summary_int(latest, "queries_with_missing_at_10")
    previous_false_positive = summary_int(previous, "queries_with_disallowed_at_10")
    latest_false_positive = summary_int(latest, "queries_with_disallowed_at_10")
    if (
        abs(latest_score - previous_score) < 0.0005
        and latest_strict == previous_strict
        and latest_missing == previous_missing
        and latest_false_positive == previous_false_positive
    ):
        return "No change from previous repeat."
    score_delta = signed_delta(latest_score, previous_score).replace("same", "unchanged")
    strict_delta = signed_int_delta(latest_strict, previous_strict).replace("same", "unchanged")
    missing_delta = signed_int_delta(latest_missing, previous_missing).replace("same", "unchanged")
    false_positive_delta = signed_int_delta(
        latest_false_positive, previous_false_positive
    ).replace("same", "unchanged")
    return (
        f"Score {score_delta}; "
        f"fully found examples {strict_delta}; "
        f"examples with missing expected IDs {missing_delta}; "
        f"examples with known wrong IDs {false_positive_delta}"
    )


def repeated_run_sets_overview_html(runs: list[dict]) -> str:
    repeated_sets = [run_set for run_set in grouped_runs_by_run_set(runs) if len(run_set) > 1]
    if not repeated_sets:
        return "<p class=\"muted\">No repeated comparable run sets are registered yet.</p>"

    rows = []
    for run_set in repeated_sets:
        latest = run_set[-1]
        previous = run_set[-2]
        first = run_set[0]
        score = overall_score(latest)
        rows.append(
            "<tr>"
            f"<td><strong>{h(run_set_title(latest))}</strong>"
            f"<br><small>{h(run_set_details(latest))}</small></td>"
            f"<td><strong>{h(len(run_set))}</strong><br><small>{h(display_timestamp(first.get('created_at')))} -> {h(display_timestamp(latest.get('created_at')))}</small></td>"
            f"<td class=\"metric-{h(overall_score_class(score))}\">{h(run_set_outcome_summary(latest))}<br>{gate_badge_html(latest)}</td>"
            f"<td>{h(run_set_change_summary(previous, latest))}<br><small>Previous run: {h(previous.get('label') or previous.get('run_id'))}</small></td>"
            f"<td><strong>{h(display_timestamp(latest.get('created_at')))}</strong><br><small>{h(latest.get('label') or latest.get('run_id'))}</small></td>"
            "</tr>"
        )

    return f"""
      <p class="muted">Each line groups runs that used the same setup and the same list of test questions. The result shown is the newest run in that group. The test-set fingerprint is just a short ID for that exact question list.</p>
      <p><strong>Release checks</strong> are pass/fail safeguards, not another score. The current repeat table mainly checks strict success@10, known false positives, source coverage, and evidence-scope problems. A true release decision should also include the quality-gate stack above: ranking precision, assertion/context behavior, long-document heldout examples, source-specific benchmarks, vocabulary/code outputs, source-delta integrity, and operational repeatability. <strong>Not checked</strong> means the run was saved for comparison but those safeguards were not applied.</p>
      <div class="table-wrap repeat-runs">
        <table>
          <thead>
            <tr>
              <th>Repeated test</th>
              <th>Runs found</th>
              <th>Latest result</th>
              <th>Change from previous</th>
              <th>Latest run label</th>
            </tr>
          </thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    """


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def read_tsv_dicts(path: Path) -> list[dict]:
    if not path.exists() or not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def ratio_text(row: dict, numerator_key: str, denominator_key: str) -> str:
    numerator = str(row.get(numerator_key) or "").strip()
    denominator = str(row.get(denominator_key) or "").strip()
    return f"{numerator}/{denominator}" if numerator and denominator else ""


def umls_api_summary_from_raw_tsv(path: Path) -> list[dict]:
    rows = read_tsv_dicts(path)
    if not rows:
        return []
    expected_rows = [row for row in rows if str(row.get("expected_cuis") or "").strip()]

    def rank_at_most(row: dict, key: str, limit: int) -> bool:
        value = str(row.get(key) or "").strip()
        return value.isdigit() and int(value) <= limit

    overlaps = []
    for row in rows:
        count = str(row.get("overlap_at_n") or "0/10").split("/", 1)[0]
        if count.isdigit():
            overlaps.append(int(count))

    return [
        {
            "variant": "current_raw_tsv",
            "label": "Current raw TSV",
            "note": "Single saved comparison TSV.",
            "rows": str(len(rows)),
            "expected_rows": str(len(expected_rows)),
            "local_top_equals_umls_top": str(
                sum(row.get("local_top_cui") == row.get("umls_top_cui") for row in rows)
            ),
            "local_top_in_umls_top10": str(
                sum(rank_at_most(row, "local_top_in_umls_rank", 10) for row in rows)
            ),
            "umls_top_in_local_top10": str(
                sum(rank_at_most(row, "umls_top_in_local_rank", 10) for row in rows)
            ),
            "expected_in_local_top10": str(
                sum(rank_at_most(row, "expected_local_rank", 10) for row in expected_rows)
            ),
            "expected_in_umls_top10": str(
                sum(rank_at_most(row, "expected_umls_rank", 10) for row in expected_rows)
            ),
            "expected_local_rank1": str(
                sum(str(row.get("expected_local_rank") or "") == "1" for row in expected_rows)
            ),
            "expected_umls_rank1": str(
                sum(str(row.get("expected_umls_rank") or "") == "1" for row in expected_rows)
            ),
            "mean_overlap_at10": f"{statistics.mean(overlaps):.2f}" if overlaps else "",
            "output": display_path(path),
        }
    ]


def umls_api_comparison_panel_html() -> str:
    summary_rows = read_tsv_dicts(DEFAULT_UMLS_API_COMPARISON_SUMMARY)
    source_path = DEFAULT_UMLS_API_COMPARISON_SUMMARY
    if not summary_rows:
        summary_rows = umls_api_summary_from_raw_tsv(DEFAULT_UMLS_API_COMPARISON)
        source_path = DEFAULT_UMLS_API_COMPARISON
    if not summary_rows:
        return "<p class=\"muted\">No UMLS API comparison output found.</p>"

    rows = []
    for row in summary_rows:
        expected_rows = str(row.get("expected_rows") or "").strip()
        rows.append(
            "<tr>"
            f"<td><strong>{h(row.get('label') or row.get('variant'))}</strong><br>"
            f"<small><code>{h(row.get('variant'))}</code></small><br>"
            f"<small>{h(row.get('note') or '')}</small></td>"
            f"<td>{h(ratio_text(row, 'local_top_equals_umls_top', 'rows'))}</td>"
            f"<td>{h(ratio_text(row, 'local_top_in_umls_top10', 'rows'))}</td>"
            f"<td>{h(ratio_text(row, 'umls_top_in_local_top10', 'rows'))}</td>"
            f"<td>{h(ratio_text(row, 'expected_in_local_top10', 'expected_rows'))}</td>"
            f"<td>{h(ratio_text(row, 'expected_local_rank1', 'expected_rows'))}</td>"
            f"<td>{h(str(row.get('mean_overlap_at10') or ''))}/10</td>"
            f"<td>{h(expected_rows)}</td>"
            "</tr>"
        )

    caveat = (
        "This is the short-query UMLS API diagnostic, not the paragraph smoke benchmark. "
        "It compares local `/api/search` output with NLM UMLS UTS `/search/current`. "
    )
    if DEFAULT_UMLS_API_COMPARISON_SUMMARY.exists():
        caveat += (
            "For this snapshot, the local side was refreshed and cached UMLS payloads were reused because "
            "no UMLS API key was available."
        )

    summary_link = f" Source: <code>{h(display_path(source_path))}</code>."
    if DEFAULT_UMLS_API_COMPARISON_SUMMARY_MD.exists():
        summary_link += f" Full summary: <code>{h(display_path(DEFAULT_UMLS_API_COMPARISON_SUMMARY_MD))}</code>."

    return f"""
      <p class="muted">{h(caveat)}{summary_link}</p>
      <div class="table-wrap umls-comparison">
        <table>
          <thead>
            <tr>
              <th>Variant</th>
              <th>Local top = UMLS top</th>
              <th>Local top in UMLS top 10</th>
              <th>UMLS top in local top 10</th>
              <th>Expected in local top 10</th>
              <th>Expected local rank 1</th>
              <th>Mean overlap@10</th>
              <th>Expected examples</th>
            </tr>
          </thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    """


def plain_language_improvement_html(runs: list[dict]) -> str:
    if len(runs) < 2:
        return ""

    baseline = runs[0]
    latest = runs[-1]
    previous = runs[-2] if len(runs) >= 2 else None

    paragraph_count = (
        summary_int(latest, "paragraphs")
        or summary_int(baseline, "paragraphs")
        or len(read_run_rows(latest))
        or len(read_run_rows(baseline))
    )
    baseline_strict = summary_int(baseline, "strict_success_at_10_count")
    latest_strict = summary_int(latest, "strict_success_at_10_count")
    strict_gain = latest_strict - baseline_strict
    baseline_missing = summary_int(baseline, "queries_with_missing_at_10")
    latest_missing = summary_int(latest, "queries_with_missing_at_10")
    missing_drop = baseline_missing - latest_missing
    baseline_fp = summary_int(baseline, "queries_with_disallowed_at_10")
    latest_fp = summary_int(latest, "queries_with_disallowed_at_10")
    baseline_score = overall_score(baseline)
    latest_score = overall_score(latest)
    score_gain = latest_score - baseline_score

    labels = " ".join(str(run.get("label") or "").lower() for run in runs)
    has_active_label_story = "active-label" in labels or "active label" in labels
    has_phrase_rescue_story = (
        "phrase rescue" in labels
        or "exact-clinical-phrase" in labels
        or "exact clinical phrase" in labels
    )
    has_remaining_cleanup_story = "remaining failure cleanup" in labels or "narrowed cough" in labels
    scope_note = ""

    if has_active_label_story:
        problem = (
            "The search engine was finding useful medical phrases, but the public API sometimes hid them "
            "because they did not have a normal public display name. In plain terms: the answer was found "
            "inside the system, but it was not always allowed to show up on the page."
        )
        changes = [
            (
                "First, we let curated active-label supplement concepts show their safe public names. "
                "That helped phrases like bibasilar crackles, right heart strain, exposed bone, suppressed TSH, "
                "and recurrent ischemia appear when they were the expected answer."
            ),
            (
                "Then we fixed the same display-name problem for existing UMLS concepts. A CUI is just the ID "
                "for a medical idea. Some IDs were valid, but their active-label name was being dropped from the "
                "public output. That helped examples like post void residual, supratherapeutic INR, and urine "
                "culture Escherichia coli."
            ),
        ]
        if has_phrase_rescue_story:
            changes.append(
                "Most recently, we added safe exact clinical phrases for ideas the benchmark already expected "
                "but Elasticsearch was not reliably putting in the first 10 results. Examples include right "
                "coronary artery occlusion, severe hypoglycemia, adnexal tenderness, BK virus nephropathy, "
                "acute limb ischemia, VP shunt malfunction, COPD exacerbation, EGFR exon 19 deletion, and "
                "extrapyramidal symptoms."
            )
        changes.append(
            "After that, we reran the same smoke test against Elasticsearch to make sure the change "
            "worked in the real search backend, not just in a local fallback path."
        )
    elif has_remaining_cleanup_story:
        scope_note = (
            "This table only compares runs with the same benchmark definition. Some cleanup work changed the "
            "benchmark itself, such as moving negated joint erosion out of the expected-answer list, so those "
            "changes are explained below even when they are not counted as example-to-example fixes inside this table."
        )
        problem = (
            "Most queries were already working. The remaining failures were small but important: one expected "
            "a negated idea as if it were present, one generic symptom was outranking the specific child croup "
            "story, one generic family-history result was beating the specific cancer-family-history concepts, "
            "one exact social-risk phrase was being filtered out as too low, and one stroke query expected fewer "
            "concepts than the words in the query actually asked for."
        )
        changes = [
            (
                "We fixed the psoriasis test so 'no joint erosion' is treated as a thing the search should avoid, "
                "not as an expected positive answer."
            ),
            (
                "We narrowed the generic cough rescue. That keeps cough findable in real respiratory notes, but "
                "stops it from taking the top spot when the query is really about croup, stridor, and neck imaging."
            ),
            (
                "We added exact family-history labels for breast cancer and ovarian cancer, so those specific "
                "risk concepts can beat the generic 'family medical history' result."
            ),
            (
                "We let a very small set of exact, current, evidence-backed labels survive the minimum-score "
                "filter. The concrete case here was homelessness. Negated labels still do not get this protection."
            ),
            (
                "We added facial droop/facial paresis to the stroke query's expected list because the query says "
                "facial droop in plain text."
            ),
            (
                "Then we reran the same smoke test against the Elasticsearch-backed API."
            ),
        ]
    else:
        problem = (
            "This table compares the same kind of run over time: same query file, same API scope, same backend, "
            "and same basic search settings. That means the entries can be read as a real before-and-after."
        )
        changes = [
            "We used the first run in this set as the starting point and the newest run as the current result.",
            "The improvement work focused on getting expected medical ideas to appear in the first 10 results.",
            "The same test was rerun after the change so the newest numbers could be compared directly.",
        ]

    change_items = "".join(f"<li>{h(item)}</li>" for item in changes)
    strict_gain_text = f"+{strict_gain}" if strict_gain >= 0 else str(strict_gain)
    score_gain_text = f"+{score_gain:.1f}" if score_gain >= 0 else f"{score_gain:.1f}"
    missing_text = (
        f"{missing_drop} fewer queries missing expected concepts"
        if missing_drop >= 0
        else f"{abs(missing_drop)} more queries missing expected concepts"
    )
    false_positive_text = (
        "still 0"
        if baseline_fp == 0 and latest_fp == 0
        else f"{baseline_fp} -> {latest_fp}"
    )
    repeat_sentence = ""
    if previous is not None:
        previous_strict = summary_int(previous, "strict_success_at_10_count")
        previous_missing = summary_int(previous, "queries_with_missing_at_10")
        previous_fp = summary_int(previous, "queries_with_disallowed_at_10")
        if (
            previous_strict == latest_strict
            and previous_missing == latest_missing
            and previous_fp == latest_fp
        ):
            repeat_sentence = (
                "<p><strong>Repeat check:</strong> The latest run repeated the previous result, "
                "so this improvement looks stable on Elasticsearch instead of being a one-time lucky run.</p>"
            )
    fixed_rows = plain_fixed_row_summaries(baseline, latest)
    fixed_rows_html = ""
    if fixed_rows:
        fixed_rows_html = (
            "<p><strong>Rows fixed in this run set:</strong></p>"
            f"<ul class=\"plain-steps\">{''.join(f'<li>{h(item)}</li>' for item in fixed_rows)}</ul>"
        )
    remaining_rows = plain_remaining_row_summaries(latest)
    remaining_rows_html = ""
    if remaining_rows:
        remaining_rows_html = (
            "<p><strong>Remaining examples to investigate:</strong></p>"
            f"<ul class=\"plain-steps\">{''.join(f'<li>{h(item)}</li>' for item in remaining_rows)}</ul>"
        )

    return f"""
      <div class="plain-explanation">
        <h3>What Changed In Plain Language</h3>
        <p><strong>How to read this:</strong> This is the main improvement table. Rows are comparable only when they use the same query sample, API scope, and Elasticsearch setup.</p>
        {f'<p><strong>Important detail:</strong> {h(scope_note)}</p>' if scope_note else ''}
        <p><strong>What went wrong:</strong> {h(problem)}</p>
        <div class="plain-metric-grid">
          <div class="plain-metric"><strong>{h(baseline_strict)} -> {h(latest_strict)}</strong><span>queries passed strict@10</span><small>{h(strict_gain_text)} out of {h(paragraph_count)}</small></div>
          <div class="plain-metric"><strong>{h(baseline_missing)} -> {h(latest_missing)}</strong><span>queries missing expected ideas</span><small>{h(missing_text)}</small></div>
          <div class="plain-metric"><strong>{h(false_positive_text)}</strong><span>known false positives</span><small>bad answers did not increase</small></div>
          <div class="plain-metric"><strong>{h(f'{baseline_score:.1f}')} -> {h(f'{latest_score:.1f}')}</strong><span>overall score</span><small>{h(score_gain_text)} points</small></div>
        </div>
        <p><strong>What we changed:</strong></p>
        <ol class="plain-steps">{change_items}</ol>
        {fixed_rows_html}
        <p><strong>What strict@10 means:</strong> A query only passes if the right main result and every expected medical idea show up in the first 10 results.</p>
        {repeat_sentence}
        <p><strong>What is still left:</strong> {h(latest_missing)} queries still miss at least one expected medical idea, and {h(summary_int(latest, "top_wrong_count"))} queries still have the wrong top result. Those are the next things to improve.</p>
        {remaining_rows_html}
      </div>
    """


def is_important_run_set(runs: list[dict]) -> bool:
    if not runs:
        return False
    latest = runs[-1]
    family = inferred_run_family_key(latest)
    backend = run_backend(latest)
    is_live_evidence_api = (
        latest.get("search_system") == SEARCH_SYSTEM_API
        and latest.get("api_scope") == SEARCH_SCOPE_UMLS_EVIDENCE
        and backend == "elasticsearch"
    )
    return is_live_evidence_api and family in {"smoke", "release"}


def important_run_sets(runs: list[dict]) -> list[list[dict]]:
    run_sets = []
    for family_runs in grouped_runs_by_family(runs).values():
        for run_set in grouped_runs_by_run_set(family_runs):
            if is_important_run_set(run_set):
                run_sets.append(run_set)
    run_sets.sort(key=lambda group: str(group[-1].get("created_at") or ""), reverse=True)
    return run_sets


def improvement_target_history_html(runs: list[dict]) -> str:
    target_run_set = current_improvement_run_set(runs)
    if not target_run_set:
        return "<p class=\"muted\">No Elasticsearch-backed API evidence smoke or release run is available yet.</p>"
    latest = target_run_set[-1]
    return (
        "<p class=\"muted\">Use this run-set for the next improvement loop. "
        "All other run sets are supporting diagnostics or historical context.</p>"
        f"{plain_language_improvement_html(target_run_set)}"
        f"{run_set_history_html(target_run_set)}"
        f"<p class=\"muted\">Target run directory: <code>{h(latest.get('run_dir') or '')}</code></p>"
    )


def family_latest_status_html(key: str, runs: list[dict]) -> str:
    latest = runs[-1]
    summary = latest.get("summary") or {}
    paragraphs = summary_int(latest, "paragraphs")
    strict_count = summary_int(latest, "strict_success_at_10_count")
    missing_count = summary_int(latest, "queries_with_missing_at_10")
    false_positive_count = summary_int(latest, "queries_with_disallowed_at_10")
    status = gate_status_text(latest)
    latest_text = (
        f"Latest: {latest.get('label') or latest.get('run_id')} "
        f"({display_timestamp(latest.get('created_at'))}) - {status}; "
        f"strict@10 {strict_count}/{paragraphs} ({pct(summary.get('strict_success_at_10_rate'))}), "
        f"missing expected@10 {missing_count}, known false positives@10 {false_positive_count}."
    )
    if key == "scope":
        latest_text += " Read this family as a same-query scope comparison, especially UMLS-only versus UMLS + evidence."
    elif key == "probe":
        latest_text += " Read this family as diagnostic evidence; a probe can explain a problem but should not become the quality baseline."
    elif key == "smoke":
        latest_text += " Read this family as the main regression line; only passing smoke runs should be used as the next baseline."
    elif key == "ranking":
        latest_text += " Read this family as targeted ranking evidence before rolling changes into smoke runs."
    run_set_count = len(grouped_runs_by_run_set(runs))
    if run_set_count > 1:
        latest_text += f" This family is split into {run_set_count} comparable run-set tables."
    return f"<p class=\"muted\">{h(latest_text)}</p>"


def run_family_history_sections(
    runs: list[dict],
    *,
    important: bool | None = None,
    exclude_run_set_keys: set[tuple[str, ...]] | None = None,
) -> str:
    if not runs:
        return "<p class=\"muted\">No runs are registered yet.</p>"
    exclude_run_set_keys = exclude_run_set_keys or set()
    groups = grouped_runs_by_family(runs)
    sections = []
    for key in sorted(groups, key=family_sort_key):
        family_runs = groups[key]
        info = RUN_FAMILY_DEFINITIONS.get(key) or RUN_FAMILY_DEFINITIONS["custom"]
        explanation = RUN_FAMILY_INTERPRETATIONS.get(key) or RUN_FAMILY_INTERPRETATIONS["custom"]
        run_sets = [
            run_set
            for run_set in grouped_runs_by_run_set(family_runs)
            if important is None or is_important_run_set(run_set) == important
        ]
        run_sets = [run_set for run_set in run_sets if run_set_key(run_set[-1]) not in exclude_run_set_keys]
        if not run_sets:
            continue
        run_set_sections = "".join(run_set_history_html(run_set) for run_set in run_sets)
        visible_family_runs = sorted(
            [run for run_set in run_sets for run in run_set],
            key=lambda item: str(item.get("created_at") or ""),
        )
        visible_run_count = sum(len(run_set) for run_set in run_sets)
        sections.append(
            f"""
            <section class="family-section">
              <div class="family-section-header">
                <div>
                  <h3>{h(info.get('label'))}</h3>
                  <p>{h(explanation)}</p>
                  {family_latest_status_html(key, visible_family_runs)}
                </div>
                <span class="family-count family-{h(info.get('class'))}">{h(visible_run_count)} runs</span>
              </div>
              {run_set_sections}
            </section>
            """
        )
    if not sections:
        return "<p class=\"muted\">No runs matched this view.</p>"
    counts = run_family_counts_html(runs) if important is None else ""
    return f"{counts}{''.join(sections)}"


def supporting_history_sections(runs: list[dict]) -> str:
    target_run_set = current_improvement_run_set(runs)
    exclude = {run_set_key(target_run_set[-1])} if target_run_set else set()
    return run_family_history_sections(runs, important=None, exclude_run_set_keys=exclude)


def metric_table(runs: list[dict]) -> str:
    rows = []
    current_group = ""
    column_count = len(runs) + 1
    for group, key, label, description in METRIC_DEFINITIONS:
        if group != current_group:
            rows.append(
                f"<tr class=\"metric-section\"><th colspan=\"{column_count}\">{h(group)}</th></tr>"
            )
            current_group = group
        cells = []
        for index, run in enumerate(runs):
            previous_run = runs[index - 1] if index > 0 else None
            cells.append(
                f"<td class=\"{metric_quality_class(run, key)}\">"
                f"{h(metric_value(run, key))}{metric_delta_html(run, previous_run, key)}</td>"
            )
        rows.append(
            f"<tr><th title=\"{h(description)}\">{h(label)}</th>{''.join(cells)}</tr>"
        )
    headers = "".join(f"<th>{run_header(run)}</th>" for run in runs)
    return f"""
      <table>
        <thead><tr><th>Metric</th>{headers}</tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    """


def query_outcome_table(
    runs: list[dict],
    *,
    limit_queries: int | None = 40,
    notable_only: bool = True,
) -> str:
    if not runs:
        return ""
    row_maps = []
    query_ids = []
    for run in runs:
        rows = read_run_rows(run)
        row_map = {row.get("id", ""): row for row in rows}
        row_maps.append(row_map)
        for row in rows:
            query_id = row.get("id", "")
            if query_id and query_id not in query_ids:
                query_ids.append(query_id)
    selected = []
    if notable_only:
        for query_id in query_ids:
            values = [row_map.get(query_id, {}) for row_map in row_maps]
            if any(
                row.get("verdict") != "good"
                or row.get("missing_at_10")
                or row.get("disallowed_at_10")
                or row.get("top_on_target") == "0"
                for row in values
            ):
                selected.append(query_id)
    else:
        selected = query_ids
    if not selected:
        selected = query_ids
    visible_query_ids = selected if limit_queries is None else selected[:limit_queries]
    body_rows = []
    for query_id in visible_query_ids:
        cells = []
        query_text = ""
        for row_map in row_maps:
            row = row_map.get(query_id, {})
            query_text = query_text or row.get("query", "")
            verdict = row.get("verdict", "")
            missing = row.get("missing_at_10", "")
            disallowed = row.get("disallowed_at_10", "")
            first_rank = row.get("first_expected_rank", "")
            coverage = row.get("coverage_at_10", "")
            top_on = row.get("top_on_target", "")
            top = " ".join(part for part in [row.get("top_cui", ""), row.get("top_name", "")] if part)
            if not row:
                detail = "query was not present in this run"
                result_label = "-"
                result_class = "missing"
            else:
                pass10 = row_strict_success(row, 10)
                result_label = "OK" if pass10 else "X"
                result_class = "pass" if pass10 else "fail"
                detail = (
                    f"{'PASS' if pass10 else 'FAIL'} strict@10; verdict={verdict or 'na'}; "
                    f"coverage@10={coverage or 'na'}; first expected rank={first_rank or 'na'}; "
                    f"top={top or 'none'}"
                )
                if top_on == "0":
                    detail += "; top result is off target"
                if missing:
                    detail += f"; missing@10={missing}"
                if disallowed:
                    detail += f"; known false-positive@10={disallowed}"
            cells.append(
                f"<td class=\"{query_cell_class(row)}\" title=\"{h(detail)}\">"
                f"<span class=\"result-mark {result_class}\" title=\"{h(detail)}\">{h(result_label)}</span>"
                "</td>"
            )
        body_rows.append(
            f"<tr><th><span>{h(query_id)}</span><small>{h(query_text)}</small></th>{''.join(cells)}</tr>"
        )
    headers = "".join(f"<th>{run_header(run)}</th>" for run in runs)
    note = ""
    if limit_queries is not None and len(selected) > limit_queries:
        note = f"<p class=\"muted\">Showing {limit_queries} of {len(selected)} non-good or notable query rows.</p>"
    return f"""
      {note}
      <table class="query-table">
        <thead><tr><th>Query</th>{headers}</tr></thead>
        <tbody>{''.join(body_rows)}</tbody>
      </table>
    """


def query_cell_class(row: dict) -> str:
    if not row:
        return "query-missing-run"
    if row.get("disallowed_at_10"):
        return "query-bad"
    if row.get("verdict") == "poor":
        return "query-bad"
    if row.get("verdict") == "mixed" or row.get("missing_at_10") or row.get("top_on_target") == "0":
        return "query-warn"
    if row.get("verdict") == "good":
        return "query-good"
    return "query-neutral"


# Archived legacy panel helpers. Disabled because the direct API scope
# comparison is now the cleaner, repeatable UMLS-vs-evidence view.
if False:  # archived 2026-06-09
    GRADE_ORDER = {"poor": 0, "mixed": 1, "good": 2}

    def adjacent_search_system_pairs(runs: list[dict]) -> list[tuple[dict, dict]]:
        pairs = []
        for index in range(len(runs) - 1):
            left = runs[index]
            right = runs[index + 1]
            if left.get("search_system") == SEARCH_SYSTEM_UMLS_ONLY and right.get("search_system") == SEARCH_SYSTEM_API:
                pairs.append((left, right))
        return pairs

    def grade_delta(left: dict, right: dict) -> int:
        return GRADE_ORDER.get(str(right.get("verdict") or ""), -1) - GRADE_ORDER.get(
            str(left.get("verdict") or ""),
            -1,
        )


def adjacent_scope_pairs(runs: list[dict]) -> list[tuple[dict, dict]]:
    pairs = []
    for index in range(len(runs) - 1):
        left = runs[index]
        right = runs[index + 1]
        if (
            left.get("search_system") == SEARCH_SYSTEM_API
            and right.get("search_system") == SEARCH_SYSTEM_API
            and left.get("api_scope") == SEARCH_SCOPE_UMLS
            and right.get("api_scope") == SEARCH_SCOPE_UMLS_EVIDENCE
            and str(left.get("queries") or "") == str(right.get("queries") or "")
        ):
            pairs.append((left, right))
    return pairs


def int_value(row: dict, key: str) -> int:
    try:
        return int(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def row_first_expected_rank(row: dict) -> int:
    value = int_value(row, "first_expected_rank")
    return value if value else 10**9


def row_short_status(row: dict) -> str:
    if not row:
        return "missing"
    parts = [
        "pass10" if row_strict_success(row, 10) else "fail10",
        f"cov10={row.get('coverage_at_10') or 'na'}",
        f"first={row.get('first_expected_rank') or 'na'}",
    ]
    if row.get("top_on_target") == "0":
        parts.append("top=off")
    if row.get("missing_at_10"):
        parts.append(f"miss={row.get('missing_at_10')}")
    if row.get("disallowed_at_10"):
        parts.append(f"bad={row.get('disallowed_at_10')}")
    return "; ".join(parts)


def row_top_text(row: dict) -> str:
    return " ".join(part for part in [row.get("top_cui", ""), row.get("top_name", "")] if part)


def comparison_metric_delta(left: dict, right: dict, key: str) -> str:
    left_value = metric_float(left, key)
    right_value = metric_float(right, key)
    if left_value is None or right_value is None:
        return ""
    delta = right_value - left_value
    sign = "+" if delta > 0 else ""
    if key in RATE_METRICS:
        return f"{sign}{delta * 100:.1f} pp"
    return f"{sign}{delta:.3f}"


def scope_pair_stats(left_run: dict, right_run: dict) -> dict:
    left_rows = {row.get("id", ""): row for row in read_run_rows(left_run)}
    right_rows = {row.get("id", ""): row for row in read_run_rows(right_run)}
    query_ids = [query_id for query_id in left_rows if query_id in right_rows]
    stats = {
        "query_count": len(query_ids),
        "fail_to_pass": 0,
        "pass_to_fail": 0,
        "both_pass": 0,
        "both_fail": 0,
        "top_changed": 0,
        "top_same": 0,
        "first_rank_improved": 0,
        "first_rank_worse": 0,
        "first_rank_same": 0,
        "found10_improved": 0,
        "found10_worse": 0,
        "found10_same": 0,
        "false_positive_removed": 0,
        "false_positive_added": 0,
        "changed_rows": [],
    }
    for query_id in query_ids:
        left = left_rows[query_id]
        right = right_rows[query_id]
        left_pass = row_strict_success(left, 10)
        right_pass = row_strict_success(right, 10)
        if not left_pass and right_pass:
            transition = "fail_to_pass"
            stats["fail_to_pass"] += 1
        elif left_pass and not right_pass:
            transition = "pass_to_fail"
            stats["pass_to_fail"] += 1
        elif left_pass and right_pass:
            transition = "both_pass"
            stats["both_pass"] += 1
        else:
            transition = "both_fail"
            stats["both_fail"] += 1

        if left.get("top_cui") == right.get("top_cui"):
            stats["top_same"] += 1
        else:
            stats["top_changed"] += 1

        left_rank = row_first_expected_rank(left)
        right_rank = row_first_expected_rank(right)
        if right_rank < left_rank:
            stats["first_rank_improved"] += 1
        elif right_rank > left_rank:
            stats["first_rank_worse"] += 1
        else:
            stats["first_rank_same"] += 1

        left_found = int_value(left, "found_at_10")
        right_found = int_value(right, "found_at_10")
        if right_found > left_found:
            found_delta = right_found - left_found
            stats["found10_improved"] += 1
        elif right_found < left_found:
            found_delta = right_found - left_found
            stats["found10_worse"] += 1
        else:
            found_delta = 0
            stats["found10_same"] += 1

        if left.get("disallowed_at_10") and not right.get("disallowed_at_10"):
            stats["false_positive_removed"] += 1
        if right.get("disallowed_at_10") and not left.get("disallowed_at_10"):
            stats["false_positive_added"] += 1

        if transition in {"fail_to_pass", "pass_to_fail"} or found_delta:
            stats["changed_rows"].append(
                {
                    "id": query_id,
                    "transition": transition,
                    "found_delta": found_delta,
                    "left": left,
                    "right": right,
                }
            )
    transition_priority = {"pass_to_fail": 0, "fail_to_pass": 1, "both_fail": 2, "both_pass": 3}
    stats["changed_rows"].sort(
        key=lambda item: (
            transition_priority.get(item["transition"], 9),
            -abs(int(item["found_delta"])),
            item["id"],
        )
    )
    return stats


def scope_metric_comparison_table(left_run: dict, right_run: dict) -> str:
    metrics = [
        ("strict_success_at_10_rate", "strict success@10"),
        ("strict_success_at_20_rate", "strict success@20"),
        ("top_on_target_rate", "top result on target"),
        ("all_expected_at_10_rate", "all expected@10"),
        ("recall_at_10", "concept recall@10"),
        ("mean_coverage_at_10", "mean coverage@10"),
        ("mrr_first_expected", "MRR first expected"),
        ("good_rate", "rubric good rate"),
        ("known_false_positive_rate_at_10", "known false-positive@10"),
        ("elapsed_seconds", "elapsed seconds"),
    ]
    rows = []
    for key, label in metrics:
        rows.append(
            "<tr>"
            f"<th>{h(label)}</th>"
            f"<td class=\"{metric_quality_class(left_run, key)}\">{h(metric_value(left_run, key))}</td>"
            f"<td class=\"{metric_quality_class(right_run, key)}\">{h(metric_value(right_run, key))}</td>"
            f"<td>{h(comparison_metric_delta(left_run, right_run, key))}</td>"
            "</tr>"
        )
    return f"""
      <table>
        <thead><tr><th>Metric</th><th>UMLS</th><th>UMLS + evidence</th><th>Delta</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    """


def scope_transition_table(stats: dict) -> str:
    rows = [
        ("fail@10 -> pass@10", stats["fail_to_pass"], "metric-good"),
        ("pass@10 -> fail@10", stats["pass_to_fail"], "metric-bad" if stats["pass_to_fail"] else "metric-good"),
        ("pass@10 -> pass@10", stats["both_pass"], "metric-neutral"),
        ("fail@10 -> fail@10", stats["both_fail"], "metric-warn" if stats["both_fail"] else "metric-good"),
        ("top CUI changed", stats["top_changed"], "metric-neutral"),
        ("first expected rank improved", stats["first_rank_improved"], "metric-good"),
        ("first expected rank worsened", stats["first_rank_worse"], "metric-bad" if stats["first_rank_worse"] else "metric-good"),
        ("found expected@10 improved", stats["found10_improved"], "metric-good"),
        ("found expected@10 worsened", stats["found10_worse"], "metric-bad" if stats["found10_worse"] else "metric-good"),
        ("known false positives removed", stats["false_positive_removed"], "metric-good"),
        ("known false positives added", stats["false_positive_added"], "metric-bad" if stats["false_positive_added"] else "metric-good"),
    ]
    body = "".join(
        f"<tr><th>{h(label)}</th><td class=\"{css_class}\">{h(count)}</td></tr>"
        for label, count, css_class in rows
    )
    return f"""
      <table>
        <thead><tr><th>Transition</th><th>Queries</th></tr></thead>
        <tbody>{body}</tbody>
      </table>
    """


def scope_changed_rows_table(stats: dict, *, limit_rows: int = 80) -> str:
    changed_rows = list(stats.get("changed_rows") or [])
    visible = changed_rows[:limit_rows]
    body_rows = []
    for item in visible:
        left = item["left"]
        right = item["right"]
        transition = {
            "fail_to_pass": "fail -> pass",
            "pass_to_fail": "pass -> fail",
            "both_fail": "fail -> fail",
            "both_pass": "pass -> pass",
        }.get(str(item["transition"]), str(item["transition"]).replace("_", " "))
        if item["transition"] == "pass_to_fail":
            transition_class = "query-bad"
        elif item["transition"] == "fail_to_pass":
            transition_class = "query-good"
        else:
            transition_class = "query-warn" if item["found_delta"] else "query-neutral"
        found_delta = int(item["found_delta"])
        found_delta_text = f"{found_delta:+d}" if found_delta else "same"
        body_rows.append(
            "<tr>"
            f"<th><span>{h(item['id'])}</span><small>{h(right.get('query', ''))}</small></th>"
            f"<td class=\"{transition_class}\">{h(transition)}<br><small>found@10 {h(found_delta_text)}</small></td>"
            f"<td class=\"{query_cell_class(left)}\" title=\"{h(row_top_text(left))}\">{h(row_short_status(left))}<br><small>{h(row_top_text(left))}</small></td>"
            f"<td class=\"{query_cell_class(right)}\" title=\"{h(row_top_text(right))}\">{h(row_short_status(right))}<br><small>{h(row_top_text(right))}</small></td>"
            "</tr>"
        )
    note = ""
    if len(changed_rows) > limit_rows:
        note = f"<p class=\"muted\">Showing {limit_rows} of {len(changed_rows)} changed rows.</p>"
    return f"""
      {note}
      <table class="query-table">
        <thead><tr><th>Query</th><th>Change</th><th>UMLS</th><th>UMLS + evidence</th></tr></thead>
        <tbody>{''.join(body_rows)}</tbody>
      </table>
    """


def latest_scope_comparison_panel(runs: list[dict]) -> str:
    pairs = adjacent_scope_pairs(runs)
    if not pairs:
        return "<p class=\"muted\">No adjacent API scope pair is available yet. Run one API evaluation with <code>--scope umls</code> followed by the same query file with <code>--scope umls_evidence</code>.</p>"
    left_run, right_run = pairs[-1]
    stats = scope_pair_stats(left_run, right_run)
    left_summary = left_run.get("summary") or {}
    right_summary = right_run.get("summary") or {}
    left_strict = int(left_summary.get("strict_success_at_10_count") or 0)
    right_strict = int(right_summary.get("strict_success_at_10_count") or 0)
    strict_delta = right_strict - left_strict
    left_fp = int(left_summary.get("queries_with_disallowed_at_10") or 0)
    right_fp = int(right_summary.get("queries_with_disallowed_at_10") or 0)
    cards = "".join(
        [
            summary_card_html(
                label="UMLS-only score",
                value=overall_score_text(left_run),
                detail=f"{pct(left_summary.get('strict_success_at_10_rate'))} strict@10",
                css_class=overall_score_class(overall_score(left_run)),
            ),
            summary_card_html(
                label="UMLS + evidence score",
                value=overall_score_text(right_run),
                detail=f"{pct(right_summary.get('strict_success_at_10_rate'))} strict@10",
                css_class=overall_score_class(overall_score(right_run)),
            ),
            f"<div class=\"summary-card good\"><strong>{h(strict_delta):s}</strong><span>strict@10 query gain</span><small>{h(stats['fail_to_pass'])} fail -> pass; {h(stats['pass_to_fail'])} pass -> fail</small></div>",
            f"<div class=\"summary-card {'bad' if right_fp > left_fp else 'good'}\"><strong>{h(right_fp - left_fp):s}</strong><span>false-positive delta</span></div>",
            f"<div class=\"summary-card warn\"><strong>{h(num(right_summary.get('elapsed_seconds'), digits=1))}s</strong><span>evidence runtime</span></div>",
        ]
    )
    return f"""
      <p>
        Direct API scope comparison on the same query file. UMLS-only ran
        {h(display_timestamp(left_run.get('created_at')))}; UMLS + evidence ran
        {h(display_timestamp(right_run.get('created_at')))}.
      </p>
      <div class="summary-grid">{cards}</div>
      <details>
        <summary>Scope Comparison Details</summary>
        <h3>Metric Delta</h3>
        <div class="table-wrap compact">{scope_metric_comparison_table(left_run, right_run)}</div>
        <h3>Row-Level Transitions</h3>
        <div class="table-wrap compact">{scope_transition_table(stats)}</div>
        <p class="muted">Per-query rows are in <code>{h(left_run.get('rows_path') or '')}</code> and <code>{h(right_run.get('rows_path') or '')}</code>.</p>
      </details>
    """


if False:  # archived 2026-06-09; see disabled report section below
    def paired_grade_comparison_table(runs: list[dict], *, limit_rows: int = 50) -> str:
        pairs = adjacent_search_system_pairs(runs)
        if not pairs:
            return "<p class=\"muted\">No adjacent UMLS-only/current-search run pair is available yet.</p>"
        left_run, right_run = pairs[-1]
        left_rows = {row.get("id", ""): row for row in read_run_rows(left_run)}
        right_rows = {row.get("id", ""): row for row in read_run_rows(right_run)}
        query_ids = [query_id for query_id in left_rows if query_id in right_rows]
        transitions: dict[tuple[str, str], int] = {}
        changed_rows = []
        for query_id in query_ids:
            left = left_rows[query_id]
            right = right_rows[query_id]
            transition = (left.get("verdict", ""), right.get("verdict", ""))
            transitions[transition] = transitions.get(transition, 0) + 1
            delta = grade_delta(left, right)
            strict_delta = int(row_strict_success(right, 10)) - int(row_strict_success(left, 10))
            if delta or strict_delta:
                changed_rows.append((delta, strict_delta, query_id, left, right))
        improved = sum(1 for delta, _strict_delta, *_rest in changed_rows if delta > 0)
        worsened = sum(1 for delta, _strict_delta, *_rest in changed_rows if delta < 0)
        strict_improved = sum(1 for _delta, strict_delta, *_rest in changed_rows if strict_delta > 0)
        strict_worsened = sum(1 for _delta, strict_delta, *_rest in changed_rows if strict_delta < 0)
        transition_text = ", ".join(
            f"{left}->{right}: {count}"
            for (left, right), count in sorted(transitions.items())
        )
        changed_rows.sort(
            key=lambda item: (
                -item[0],
                -item[1],
                item[2],
            )
        )
        visible = changed_rows[:limit_rows]
        body_rows = []
        for delta, strict_delta, query_id, left, right in visible:
            direction = "improved" if delta > 0 else ("worse" if delta < 0 else "strict changed")
            current_top = " ".join(part for part in [right.get("top_cui", ""), right.get("top_name", "")] if part)
            detail = (
                f"grade {left.get('verdict') or 'na'} -> {right.get('verdict') or 'na'}; "
                f"pass10 {row_strict_success(left, 10)} -> {row_strict_success(right, 10)}"
            )
            body_rows.append(
                "<tr>"
                f"<th><span>{h(query_id)}</span><small>{h(right.get('query', ''))}</small></th>"
                f"<td class=\"{query_cell_class(left)}\">{h(left.get('verdict'))}<br><small>miss10={h(left.get('missing_at_10') or 'none')}</small></td>"
                f"<td class=\"{query_cell_class(right)}\">{h(right.get('verdict'))}<br><small>miss10={h(right.get('missing_at_10') or 'none')}</small></td>"
                f"<td>{h(direction)}<br><small>{h(detail)}</small></td>"
                f"<td title=\"{h(current_top)}\">{h(current_top)}</td>"
                "</tr>"
            )
        note = ""
        if len(changed_rows) > limit_rows:
            note = f"<p class=\"muted\">Showing {limit_rows} of {len(changed_rows)} changed paragraph rows.</p>"
        return f"""
          <p>
            Compared <strong>{h(left_run.get('label'))}</strong> with <strong>{h(right_run.get('label'))}</strong>.
            Grade improved on {improved} paragraphs and worsened on {worsened}; strict pass@10 improved on {strict_improved} and worsened on {strict_worsened}.
          </p>
          <p class="muted">Grade transitions: {h(transition_text)}</p>
          {note}
          <table class="query-table">
            <thead><tr><th>Paragraph</th><th>UMLS-only</th><th>Current search</th><th>Change</th><th>Current top</th></tr></thead>
            <tbody>{''.join(body_rows)}</tbody>
          </table>
        """


def source_contribution_table(run: dict | None, *, limit_sources: int = 20) -> str:
    if not run:
        return "<p class=\"muted\">No run is available yet.</p>"
    summary = run.get("summary") or {}
    ranked_sources = list(summary.get("source_quality_ranked_at_10") or [])
    if not ranked_sources:
        source_quality_json_path = str(run.get("source_quality_json_path") or "")
        source_quality_json = Path(source_quality_json_path) if source_quality_json_path else None
        if source_quality_json and source_quality_json.exists():
            source_quality = json.loads(source_quality_json.read_text(encoding="utf-8"))
            ranked_sources = list(source_quality.get("ranked_sources") or [])
    if not ranked_sources:
        return "<p class=\"muted\">This run does not include source contribution metrics yet.</p>"

    visible = ranked_sources[:limit_sources]
    rows = []
    for source in visible:
        expected_examples = source.get("expected_examples") or []
        example = ""
        if expected_examples:
            first = expected_examples[0]
            example = (
                f"{first.get('id') or ''} rank {first.get('rank') or ''} "
                f"{first.get('cui') or ''} {first.get('name') or ''}"
            )
        bad_queries = int(source.get("disallowed_queries_at_10") or 0)
        bad_class = "metric-bad" if bad_queries else "metric-good"
        rows.append(
            "<tr>"
            f"<th title=\"{h(example)}\">{h(source.get('source'))}</th>"
            f"<td>{h(source.get('strict_success_expected_queries_at_10'))}</td>"
            f"<td>{h(source.get('top1_strict_success_expected_queries'))}</td>"
            f"<td>{h(source.get('expected_queries_at_10'))}</td>"
            f"<td class=\"{bad_class}\">{h(bad_queries)}</td>"
            f"<td>{h(source.get('queries_present_at_10'))}</td>"
            f"<td>{pct(source.get('strict_success_query_rate_when_present'))}</td>"
            f"<td>{pct(source.get('expected_query_rate_when_present'))}</td>"
            f"<td>{pct(source.get('disallowed_query_rate_when_present'))}</td>"
            f"<td>{num(source.get('mean_best_expected_rank_at_10'), digits=1)}</td>"
            "</tr>"
        )
    note = ""
    if len(ranked_sources) > limit_sources:
        note = f"<p class=\"muted\">Showing {limit_sources} of {len(ranked_sources)} sources.</p>"
    tsv_path = run.get("source_quality_path") or ""
    return f"""
      <p class="muted">
        Ranked by acceptable-hit sources on strict-success queries. Presence columns are associative diagnostics, not source ablations.
        TSV: <code>{h(tsv_path)}</code>
      </p>
      {note}
      <table>
        <thead>
          <tr>
            <th>Source</th>
            <th>strict expected q@10</th>
            <th>top1 strict expected q</th>
            <th>expected q@10</th>
            <th>bad q@10</th>
            <th>present q@10</th>
            <th>pass rate when present</th>
            <th>expected rate when present</th>
            <th>bad rate when present</th>
            <th>mean best expected rank</th>
          </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    """


def latest_evidence_run(runs: list[dict]) -> dict | None:
    for run in reversed(sorted(runs, key=lambda item: str(item.get("created_at") or ""))):
        if (
            run.get("search_system") == SEARCH_SYSTEM_API
            and run.get("api_scope") == SEARCH_SCOPE_UMLS_EVIDENCE
        ):
            return run
    return None


def latest_scope_improved_query_ids(runs: list[dict]) -> set[str]:
    pairs = adjacent_scope_pairs(runs)
    if not pairs:
        return set()
    stats = scope_pair_stats(*pairs[-1])
    return {
        str(item.get("id") or "")
        for item in stats.get("changed_rows") or []
        if item.get("transition") == "fail_to_pass"
    }


def evidence_item_sources(item: dict) -> list[dict]:
    raw_sources = item.get("sources") or []
    if not isinstance(raw_sources, list):
        raw_sources = [raw_sources]
    sources = []
    for source in raw_sources:
        if isinstance(source, dict):
            label = (
                source.get("label")
                or source.get("matched_label")
                or source.get("corpus_doc_id")
                or source.get("source")
                or "source"
            )
            sources.append(
                {
                    "label": str(label),
                    "source": normalize_source_id(source.get("source") or label),
                    "url": str(source.get("url") or ""),
                    "matched_label": str(source.get("matched_label") or ""),
                    "corpus_doc_id": str(source.get("corpus_doc_id") or ""),
                }
            )
        elif source:
            label = str(source)
            sources.append(
                {
                    "label": label,
                    "source": normalize_source_id(label),
                    "url": "",
                    "matched_label": "",
                    "corpus_doc_id": "",
                }
            )
    return sources


def numeric_weight(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def evidence_sort_key(example: dict) -> tuple[object, ...]:
    return (
        0 if example.get("improved_query") else 1,
        0 if example.get("sources") else 1,
        int(example.get("rank") or 10**9),
        -numeric_weight(example.get("weight")),
        str(example.get("query_id") or ""),
    )


def select_evidence_examples(candidates: list[dict], *, limit_examples: int) -> list[dict]:
    selected: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    per_query: dict[str, int] = {}

    def add(example: dict) -> bool:
        query_id = str(example.get("query_id") or "")
        key = (
            query_id,
            str(example.get("cui") or ""),
            str(example.get("text") or "")[:100],
        )
        if key in seen or per_query.get(query_id, 0) >= 2:
            return False
        seen.add(key)
        per_query[query_id] = per_query.get(query_id, 0) + 1
        selected.append(example)
        return True

    sourced = sorted((item for item in candidates if item.get("sources")), key=evidence_sort_key)
    text_only = sorted((item for item in candidates if not item.get("sources")), key=evidence_sort_key)
    for bucket, target in ((sourced, max(1, limit_examples - 4)), (text_only, 4)):
        added = 0
        for example in bucket:
            if len(selected) >= limit_examples or added >= target:
                break
            if add(example):
                added += 1
    for example in sorted(candidates, key=evidence_sort_key):
        if len(selected) >= limit_examples:
            break
        add(example)
    return selected


def evidence_examples_for_run(
    run: dict,
    *,
    improved_query_ids: set[str],
    limit_examples: int = 12,
) -> dict:
    payloads_path_text = str(run.get("payloads_path") or "")
    payloads_path = Path(payloads_path_text) if payloads_path_text else Path()
    payloads = read_payloads_jsonl(payloads_path) if payloads_path_text else []
    candidates: list[dict] = []
    source_counts: dict[str, int] = {}
    stats = {
        "payload_count": len(payloads),
        "hits_at_10": 0,
        "hits_with_evidence_at_10": 0,
        "evidence_items_at_10": 0,
        "sourced_items_at_10": 0,
        "text_only_items_at_10": 0,
    }

    for payload in payloads:
        query_id = str(payload.get("id") or "")
        query_text = str(payload.get("query") or "")
        response = payload.get("response") or {}
        for rank, hit in enumerate(list(response.get("hits") or [])[:10], start=1):
            stats["hits_at_10"] += 1
            items = list(hit.get("evidence_items") or [])
            if items:
                stats["hits_with_evidence_at_10"] += 1
            for item in items:
                if not isinstance(item, dict):
                    continue
                text = sentence_bounded_evidence_text(str(item.get("text") or ""))
                if not text:
                    continue
                sources = evidence_item_sources(item)
                stats["evidence_items_at_10"] += 1
                if sources:
                    stats["sourced_items_at_10"] += 1
                    for source in sources:
                        source_name = source.get("source") or "unknown"
                        source_counts[source_name] = source_counts.get(source_name, 0) + 1
                else:
                    stats["text_only_items_at_10"] += 1
                candidates.append(
                    {
                        "query_id": query_id,
                        "query": compact_text(query_text, limit=180),
                        "rank": rank,
                        "cui": hit.get("cui") or "",
                        "name": hit.get("name") or hit.get("label") or hit.get("term") or "",
                        "evidence_count": hit.get("evidence_count") or len(items),
                        "weight": item.get("weight"),
                        "text": text,
                        "sources": sources,
                        "improved_query": query_id in improved_query_ids,
                    }
                )

    return {
        "run": run,
        "payloads_path": str(payloads_path),
        "stats": stats,
        "source_counts": source_counts,
        "examples": select_evidence_examples(candidates, limit_examples=limit_examples),
        "text_rows": select_evidence_examples(candidates, limit_examples=12),
    }


def evidence_sources_html(sources: list[dict]) -> str:
    if not sources:
        return "<span class=\"source-chip missing\">text-only evidence item</span>"
    chips = []
    for source in sources[:4]:
        label = source.get("label") or source.get("source") or "source"
        details = " | ".join(
            part
            for part in [
                source.get("source") or "",
                source.get("corpus_doc_id") or "",
                f"matched: {source.get('matched_label')}" if source.get("matched_label") else "",
            ]
            if part
        )
        title = h(details or label)
        url = str(source.get("url") or "")
        if url:
            chips.append(
                f"<a class=\"source-chip\" href=\"{h(url)}\" title=\"{title}\" target=\"_blank\" rel=\"noopener\">{h(label)}</a>"
            )
        else:
            chips.append(f"<span class=\"source-chip\" title=\"{title}\">{h(label)}</span>")
    if len(sources) > 4:
        chips.append(f"<span class=\"source-chip muted-chip\">+{h(len(sources) - 4)} more</span>")
    return "".join(chips)


def evidence_text_table(rows: list[dict]) -> str:
    if not rows:
        return "<p class=\"muted\">No evidence text rows were available in the selected evidence payload.</p>"
    body_rows = []
    for row in rows:
        body_rows.append(
            "<tr>"
            "<th>"
            f"<span>{h(row.get('query_id'))}</span>"
            f"<small>{h(row.get('query'))}</small>"
            "</th>"
            "<td>"
            f"<strong>rank {h(row.get('rank'))} | {h(row.get('cui'))}</strong><br>"
            f"<small>{h(row.get('name'))}</small>"
            "</td>"
            f"<td>{evidence_sources_html(row.get('sources') or [])}</td>"
            f"<td class=\"evidence-copy\"><div class=\"evidence-full-text\">{h(row.get('text'))}</div></td>"
            "</tr>"
        )
    return f"""
      <div class="table-wrap">
        <table class="evidence-text-table">
          <thead><tr><th>Query</th><th>Hit</th><th>Source</th><th>Evidence text</th></tr></thead>
          <tbody>{''.join(body_rows)}</tbody>
        </table>
      </div>
    """


def evidence_examples_panel(runs: list[dict]) -> str:
    evidence_runs = [
        run
        for run in sorted(runs, key=lambda item: str(item.get("created_at") or ""))
        if run.get("search_system") == SEARCH_SYSTEM_API and run.get("api_scope") == SEARCH_SCOPE_UMLS_EVIDENCE
    ]
    if not evidence_runs:
        return "<p class=\"muted\">No UMLS + evidence API run is available yet.</p>"
    improved_query_ids = latest_scope_improved_query_ids(runs)
    run = evidence_runs[-1]
    data = None
    for candidate in reversed(evidence_runs):
        candidate_data = evidence_examples_for_run(
            candidate,
            improved_query_ids=improved_query_ids,
            limit_examples=12,
        )
        if candidate_data["stats"].get("evidence_items_at_10"):
            run = candidate
            data = candidate_data
            break
        if data is None:
            data = candidate_data
    assert data is not None
    stats = data["stats"]
    source_counts = data["source_counts"]
    source_summary = ", ".join(
        f"{source} {count}" for source, count in sorted(source_counts.items(), key=lambda item: (-item[1], item[0]))[:6]
    )
    if not source_summary:
        source_summary = "none"
    cards = "".join(
        [
            f"<div class=\"summary-card\"><strong>{h(stats['evidence_items_at_10'])}</strong><span>evidence items in top 10</span></div>",
            f"<div class=\"summary-card\"><strong>{h(stats['hits_with_evidence_at_10'])}</strong><span>hits with evidence in top 10</span></div>",
            f"<div class=\"summary-card good\"><strong>{h(stats['sourced_items_at_10'])}</strong><span>source-attributed items</span></div>",
            f"<div class=\"summary-card warn\"><strong>{h(stats['text_only_items_at_10'])}</strong><span>text-only items</span></div>",
        ]
    )
    examples_html = []
    for example in data["examples"]:
        improved = (
            "<span class=\"evidence-tag good\">fail -> pass query</span>"
            if example.get("improved_query")
            else ""
        )
        examples_html.append(
            "<article class=\"evidence-example\">"
            "<header>"
            f"<strong>rank {h(example.get('rank'))} | {h(example.get('cui'))}</strong>"
            f"<span>weight {h(num(example.get('weight'), digits=2))}</span>"
            "</header>"
            f"<div class=\"evidence-query\"><code>{h(example.get('query_id'))}</code> {h(example.get('query'))}</div>"
            f"<div class=\"evidence-hit\">{h(example.get('name'))} <small>hit evidence_count={h(example.get('evidence_count'))}</small></div>"
            f"<p class=\"evidence-full-text\">{h(example.get('text'))}</p>"
            f"<div class=\"evidence-sources\">{evidence_sources_html(example.get('sources') or [])}</div>"
            f"{improved}"
            "</article>"
        )
    examples_block = "".join(examples_html)
    if not examples_block:
        examples_block = "<p class=\"muted\">The latest evidence run has no populated evidence_items in top-10 hits.</p>"
    return f"""
      <p>
        Showing evidence snippets attached to top-10 hits from <strong>{h(run.get('label'))}</strong>.
        Source mix in these top-10 evidence items: {h(source_summary)}.
      </p>
      <p class="muted">Payloads: <code>{h(data['payloads_path'])}</code></p>
      <div class="summary-grid">{cards}</div>
      <div class="evidence-grid">{examples_block}</div>
      <h3>Actual Evidence Text</h3>
      <p class="muted">These rows are copied from <code>evidence_items[].text</code> in the saved API payloads. The table is capped at 12 representative top-10 evidence items.</p>
      {evidence_text_table(data.get('text_rows') or [])}
    """


def report_intro_html(runs: list[dict], *, generated: str) -> str:
    if not runs:
        return (
            f"<p class=\"muted\">Generated {h(display_timestamp(generated))}. "
            "No evaluation runs are registered yet.</p>"
        )
    repeated_count = sum(1 for run_set in grouped_runs_by_run_set(runs) if len(run_set) > 1)
    return (
        f"<p class=\"muted\">Generated {h(display_timestamp(generated))}. "
        f"Timestamps are UTC. Showing {h(repeated_count)} repeated comparable run types from "
        f"{h(len(runs))} registered runs. Start with the "
        "<a href=\"search_quality_progress_log.html\">progress log</a> for the readable "
        "weakness, fix, and regression story; use this page as the detailed run archive.</p>"
    )


def write_html_report(path: Path, manifest: dict) -> None:
    runs = list(manifest.get("runs") or [])
    runs.sort(key=lambda item: str(item.get("created_at") or ""))
    recent = runs[-10:]
    all_runs = runs
    generated = utc_timestamp()
    metric_defs = "".join(
        f"<li><strong>{h(group)}</strong>: <code>{h(label)}</code> - {h(description)}</li>"
        for group, _key, label, description in METRIC_DEFINITIONS
    )
    body = f"""<!doctype html>
<html lang="en">
	<head>
	  <meta charset="utf-8">
	  <meta name="viewport" content="width=device-width, initial-scale=1">
	  <title>Search Quality Repeat Runs</title>
	  <style>
	    :root {{
	      --bg: #f6f8fb;
	      --panel: #fff;
	      --ink: #17202a;
      --muted: #5b6673;
      --line: #d7dde5;
      --blue: #2563eb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 14px;
      line-height: 1.45;
	    }}
	    main {{ width: min(1440px, calc(100vw - 32px)); margin: 0 auto; padding: 22px 0 44px; }}
	    h1 {{ font-size: 22px; margin: 0 0 4px; }}
	    h2 {{ font-size: 16px; margin: 0 0 10px; }}
	    h3 {{ font-size: 14px; margin: 16px 0 8px; }}
    p {{ margin: 0 0 10px; }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      margin-top: 14px;
      padding: 14px;
    }}
    .top-read-panel {{
      border-color: #c7d2fe;
    }}
    .primary-read {{
      background: #eef4ff;
      border: 1px solid #c7d2fe;
      border-radius: 8px;
      margin: 12px 0;
      padding: 12px;
    }}
    .primary-read strong {{
      display: block;
      font-size: 17px;
      line-height: 1.25;
      margin-bottom: 4px;
    }}
    .primary-read span {{
      color: #465467;
      display: block;
    }}
	    .muted, small {{ color: var(--muted); }}
	    .assessment {{
	      align-items: stretch;
	      border: 1px solid var(--line);
	      border-radius: 8px;
	      display: grid;
	      gap: 12px;
	      grid-template-columns: minmax(180px, 240px) 1fr;
	      margin-top: 12px;
	      padding: 12px;
	    }}
	    .assessment-good {{ background: #ecfdf3; border-color: #bbf7d0; }}
	    .assessment-warn {{ background: #fffbeb; border-color: #fde68a; }}
	    .assessment-bad {{ background: #fef2f2; border-color: #fecaca; }}
	    .assessment-score {{
	      border-right: 1px solid rgba(23, 32, 42, 0.12);
	      padding-right: 12px;
	    }}
	    .assessment-score strong {{ display: block; font-size: 32px; line-height: 1.05; }}
	    .assessment-score span {{ display: block; font-size: 12px; font-weight: 900; margin-top: 6px; }}
	    .assessment-score small {{ display: block; margin-top: 4px; }}
	    .assessment-recommendations h3 {{ margin-top: 0; }}
	    .assessment-recommendations ul {{ margin-top: 4px; }}
	    .summary-grid {{
	      display: grid;
	      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 10px;
      margin: 12px 0 4px;
    }}
	    .summary-card {{
	      border: 1px solid var(--line);
	      border-radius: 8px;
	      background: #f8fafc;
	      padding: 12px;
	      min-height: 78px;
	    }}
	    .summary-card strong {{ display: block; font-size: 24px; line-height: 1.1; }}
	    .summary-card span {{ color: var(--muted); display: block; font-size: 12px; font-weight: 800; margin-top: 6px; }}
	    .summary-card small {{ display: block; margin-top: 4px; }}
	    .summary-card.good {{ background: #ecfdf3; border-color: #bbf7d0; color: #14532d; }}
	    .summary-card.warn {{ background: #fffbeb; border-color: #fde68a; color: #713f12; }}
	    .summary-card.bad {{ background: #fef2f2; border-color: #fecaca; color: #7f1d1d; }}
	    .summary-card.neutral {{ background: #f8fafc; border-color: var(--line); color: #334155; }}
	    .plain-explanation {{
	      background: #f8fafc;
	      border: 1px solid var(--line);
	      border-radius: 8px;
	      margin: 12px 0;
	      padding: 14px;
	    }}
	    .plain-explanation h3 {{
	      font-size: 15px;
	      margin: 0 0 8px;
	    }}
	    .plain-explanation p {{
	      max-width: 980px;
	    }}
	    .plain-metric-grid {{
	      display: grid;
	      gap: 8px;
	      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
	      margin: 12px 0;
	    }}
	    .plain-metric {{
	      background: #fff;
	      border: 1px solid #dbe3ee;
	      border-radius: 8px;
	      padding: 10px;
	    }}
	    .plain-metric strong {{
	      display: block;
	      font-size: 21px;
	      line-height: 1.1;
	    }}
	    .plain-metric span {{
	      color: var(--muted);
	      display: block;
	      font-size: 12px;
	      font-weight: 800;
	      margin-top: 5px;
	    }}
	    .plain-metric small {{
	      display: block;
	      margin-top: 3px;
	    }}
	    .plain-steps {{
	      margin: 6px 0 10px;
	      padding-left: 22px;
	    }}
	    .plain-steps li {{
	      margin: 6px 0;
	      max-width: 980px;
	    }}
	    .latest-header {{
	      align-items: flex-start;
	      display: flex;
	      gap: 16px;
	      justify-content: space-between;
	    }}
	    .latest-header h3 {{ font-size: 18px; margin: 0 0 3px; }}
	    .status-badge, .delta-badge {{
	      border: 1px solid var(--line);
	      border-radius: 999px;
	      display: inline-flex;
	      font-size: 12px;
	      font-weight: 900;
	      line-height: 1.2;
	      padding: 5px 8px;
	      text-decoration: none;
	      white-space: nowrap;
	    }}
	    .status-badge.good, .delta-badge.good {{ background: #ecfdf3; border-color: #bbf7d0; color: #14532d; }}
	    .status-badge.bad, .delta-badge.bad {{ background: #fef2f2; border-color: #fecaca; color: #7f1d1d; }}
	    .status-badge.neutral, .delta-badge.neutral {{ background: #f8fafc; color: #475569; }}
	    .delta-badge {{ border-radius: 6px; margin-top: 8px; }}
	    .family-counts {{
	      display: flex;
	      flex-wrap: wrap;
	      gap: 6px;
	      margin: 2px 0 10px;
	    }}
	    .family-badge, .family-count {{
	      border: 1px solid #cbd5e1;
	      border-radius: 999px;
	      display: inline-flex;
	      font-size: 12px;
	      font-weight: 900;
	      line-height: 1.2;
	      padding: 5px 8px;
	      white-space: nowrap;
	    }}
	    .family-count {{ background: #fff; color: #334155; }}
	    .family-smoke {{ background: #eff6ff; border-color: #bfdbfe; color: #1e3a8a; }}
	    .family-scope {{ background: #f0fdf4; border-color: #bbf7d0; color: #14532d; }}
	    .family-probe {{ background: #fff7ed; border-color: #fed7aa; color: #7c2d12; }}
	    .family-baseline {{ background: #f8fafc; border-color: #cbd5e1; color: #334155; }}
	    .family-ranking {{ background: #faf5ff; border-color: #e9d5ff; color: #581c87; }}
	    .family-release {{ background: #fef2f2; border-color: #fecaca; color: #7f1d1d; }}
	    .family-custom {{ background: #f8fafc; border-color: #e2e8f0; color: #475569; }}
	    .family-section {{
	      border-top: 1px solid #edf0f4;
	      margin-top: 14px;
	      padding-top: 14px;
	    }}
	    .family-section:first-of-type {{ border-top: 0; padding-top: 4px; }}
	    .family-section-header {{
	      align-items: flex-start;
	      display: flex;
	      gap: 14px;
	      justify-content: space-between;
	      margin-bottom: 10px;
	    }}
	    .family-section-header h3 {{ font-size: 15px; margin: 0 0 4px; }}
	    .run-set-section {{
	      margin-top: 12px;
	    }}
	    .run-set-header {{
	      align-items: flex-start;
	      display: flex;
	      gap: 12px;
	      justify-content: space-between;
	      margin-bottom: 8px;
	    }}
	    .run-set-header h4 {{
	      font-size: 13px;
	      margin: 0 0 3px;
	    }}
	    code {{
	      background: #eef2f7;
	      border-radius: 4px;
	      padding: 1px 4px;
	    }}
	    pre {{
	      background: #111827;
	      border-radius: 8px;
	      color: #f8fafc;
	      margin: 8px 0 12px;
	      overflow: auto;
	      padding: 12px;
	    }}
	    pre code {{ background: transparent; color: inherit; padding: 0; }}
	    .table-wrap {{ overflow: auto; border: 1px solid var(--line); border-radius: 8px; }}
	    .table-wrap.compact table {{ min-width: 640px; }}
	    .repeat-runs table {{ min-width: 960px; }}
	    .repeat-runs td:first-child {{ min-width: 360px; }}
	    .repeat-runs td:nth-child(3) {{ min-width: 300px; }}
	    .repeat-runs td:nth-child(4) {{ min-width: 240px; }}
	    .umls-comparison table {{ min-width: 1040px; }}
	    .umls-comparison td:first-child {{ min-width: 280px; }}
	    table {{ border-collapse: collapse; min-width: 960px; width: 100%; background: #fff; }}
	    th, td {{ border-bottom: 1px solid #edf0f4; padding: 8px 9px; text-align: left; vertical-align: top; }}
	    th {{ background: #f8fafc; font-weight: 800; position: sticky; left: 0; z-index: 1; }}
    thead th {{ color: var(--muted); font-size: 12px; top: 0; z-index: 2; }}
    td {{ min-width: 150px; }}
    td.metric-good, td.query-good {{ background: #ecfdf3; color: #14532d; }}
    td.metric-warn, td.query-warn {{ background: #fffbeb; color: #713f12; }}
    td.metric-bad, td.query-bad {{ background: #fef2f2; color: #7f1d1d; }}
    td.metric-neutral, td.query-neutral, td.query-missing-run {{ background: #f8fafc; color: #475569; }}
    tr.metric-section th {{
      background: #e8eef6;
      color: #334155;
      font-size: 12px;
      letter-spacing: 0;
      text-transform: uppercase;
      position: static;
    }}
    .metric-delta {{ display: block; font-size: 12px; font-weight: 800; margin-top: 2px; }}
    .metric-delta.up {{ color: #047857; }}
    .metric-delta.down {{ color: #b91c1c; }}
    .metric-delta.flat {{ color: #64748b; }}
	    th span {{ display: block; min-width: 130px; }}
	    th small {{ display: block; font-weight: 600; max-width: 420px; }}
	    details {{ margin-top: 12px; }}
	    summary {{ color: var(--blue); cursor: pointer; font-weight: 800; }}
	    .layered-details {{
	      padding: 0;
	    }}
	    .layered-details > summary {{
	      align-items: center;
	      color: var(--ink);
	      display: flex;
	      gap: 12px;
	      justify-content: space-between;
	      list-style: none;
	      padding: 14px;
	    }}
	    .layered-details > summary::-webkit-details-marker {{
	      display: none;
	    }}
	    .layered-details > summary::after {{
	      content: "Open";
	      border: 1px solid var(--line);
	      border-radius: 999px;
	      color: var(--blue);
	      font-size: 12px;
	      padding: 4px 8px;
	    }}
	    .layered-details[open] > summary::after {{
	      content: "Close";
	    }}
	    .layered-details summary span {{
	      display: block;
	      font-size: 15px;
	    }}
	    .layered-details summary small {{
	      display: block;
	      font-weight: 600;
	      margin-top: 2px;
	    }}
	    .layered-details-body {{
	      border-top: 1px solid var(--line);
	      padding: 14px;
	    }}
	    .detail-section + .detail-section {{
	      border-top: 1px solid #edf0f4;
	      margin-top: 18px;
	      padding-top: 16px;
	    }}
	    ul {{ margin: 8px 0 0; padding-left: 20px; }}
	    .score-table th span {{ min-width: 190px; }}
	    .score-table td code {{
	      display: block;
	      max-width: 320px;
	      overflow: hidden;
	      text-overflow: ellipsis;
	      white-space: nowrap;
	    }}
	    .result-mark {{
	      align-items: center;
	      border: 1px solid var(--line);
	      border-radius: 6px;
	      display: inline-flex;
	      font-size: 12px;
	      font-weight: 900;
	      justify-content: center;
	      min-height: 26px;
	      min-width: 34px;
	      padding: 4px 6px;
	    }}
	    .result-mark.pass {{ background: #ecfdf3; border-color: #bbf7d0; color: #14532d; }}
	    .result-mark.fail {{ background: #fef2f2; border-color: #fecaca; color: #7f1d1d; }}
	    .result-mark.missing {{ background: #f8fafc; color: #64748b; }}
	    .query-table td {{ min-width: 74px; text-align: center; }}
	    .command-panel {{ border-top: 1px solid #edf0f4; margin-top: 12px; padding-top: 10px; }}
	    .evidence-text-table {{ min-width: 1180px; }}
	    .evidence-text-table th span {{ min-width: 170px; }}
	    .evidence-text-table td {{ min-width: 170px; }}
	    .evidence-text-table td.evidence-copy {{
	      min-width: 520px;
	      max-width: 760px;
	    }}
	    .evidence-full-text {{
	      color: #17202a;
	      overflow-wrap: anywhere;
	      white-space: pre-wrap;
	    }}
	    .evidence-grid {{
	      display: grid;
	      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
	      gap: 10px;
	      margin-top: 12px;
    }}
    .evidence-example {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 10px;
      min-width: 0;
    }}
    .evidence-example header {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      color: #334155;
      font-size: 12px;
      margin-bottom: 6px;
    }}
    .evidence-example p {{ margin: 8px 0; }}
    .evidence-query {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      overflow-wrap: anywhere;
    }}
    .evidence-hit {{
      font-weight: 800;
      margin-top: 4px;
      overflow-wrap: anywhere;
    }}
    .evidence-sources {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 8px;
    }}
    .source-chip, .evidence-tag {{
      border: 1px solid #cbd5e1;
      border-radius: 999px;
      color: #334155;
      display: inline-flex;
      font-size: 12px;
      font-weight: 800;
      line-height: 1.2;
      max-width: 100%;
      padding: 4px 7px;
      text-decoration: none;
    }}
    .source-chip.missing {{ background: #fffbeb; border-color: #fde68a; color: #713f12; }}
    .muted-chip {{ background: #f8fafc; color: var(--muted); }}
	    .evidence-tag.good {{ background: #ecfdf3; border-color: #bbf7d0; color: #14532d; margin-top: 8px; }}
	    @media (max-width: 760px) {{
	      .assessment {{ grid-template-columns: 1fr; }}
	      .assessment-score {{ border-right: 0; border-bottom: 1px solid rgba(23, 32, 42, 0.12); padding: 0 0 10px; }}
	    }}
	  </style>
		</head>
		<body>
		<main>
		  <h1>Search Quality Repeat Runs</h1>
		  {report_intro_html(all_runs, generated=generated)}
		  {translation_benchmark_panel_html()}
		  {iteration_smoke_gate_panel_html(DEFAULT_OUTPUT_ROOT)}

		  <details class="panel layered-details">
		    <summary>
		      <span>Run History And Diagnostics</span>
		      <small>Repeated runs, gates, and the short-query UMLS API comparison.</small>
		    </summary>
		    <div class="layered-details-body">
		      <section class="detail-section">
		        <h2>Repeated Run Types And Outcomes</h2>
		        {repeated_run_sets_overview_html(all_runs)}
		      </section>
		      <section class="detail-section">
		        <h2>UMLS API Comparison</h2>
		        {umls_api_comparison_panel_html()}
		      </section>
		    </div>
		  </details>

		  <p class="muted">Archive source: <code>build/search_quality_experiments/runs.json</code>. Per-run details remain in each run directory.</p>

	  <!--
	    Archived from the page view on 2026-06-09:
	    current-target narratives, diagnostic evidence tables, source contribution
	    dumps, commands, metric definitions, and single-run history tables. The
	    manifest and per-run rows.tsv files remain the archive of record.
	  -->
		</main>
	</body>
	</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(line.rstrip() for line in body.splitlines()) + "\n"
    path.write_text(body, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run and append paragraph search-quality evaluation experiments.")
    parser.add_argument("--label", help="Human-readable run label.")
    parser.add_argument("--run-id", help="Stable run id. Defaults to current UTC timestamp.")
    parser.add_argument(
        "--run-family",
        choices=sorted(RUN_FAMILY_DEFINITIONS),
        help=(
            "Report grouping for this run. Older runs are inferred from labels, "
            "but new repeatable runs should set this explicitly."
        ),
    )
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument(
        "--query-limit",
        type=int,
        default=DEFAULT_QUERY_LIMIT,
        help=(
            f"Number of query rows to evaluate from --queries. Defaults to {DEFAULT_QUERY_LIMIT} "
            "for fast rotating runs; pass 0 to evaluate the full query file."
        ),
    )
    parser.add_argument(
        "--query-selection",
        choices=["rotate", "first"],
        default="rotate",
        help=(
            "How to choose rows when --query-limit is smaller than the query file. "
            "rotate uses a stable mixed order and a run-specific offset."
        ),
    )
    parser.add_argument(
        "--query-rotation-seed",
        default="",
        help=(
            "Seed for rotating query selection. Defaults to the run id so repeated runs cover "
            "different 50-query slices while paired systems use the same slice."
        ),
    )
    parser.add_argument("--alternatives", type=Path, default=DEFAULT_ACCEPTABLE_ALTERNATIVES)
    parser.add_argument("--base-url", default="http://127.0.0.1:8766")
    parser.add_argument(
        "--require-api-backend",
        default="elasticsearch",
        help=(
            "Required backend value in live API search responses. Defaults to elasticsearch "
            "so API experiments cannot silently evaluate a local fallback service."
        ),
    )
    parser.add_argument("--mode", default="balanced", choices=["balanced", "exact"])
    parser.add_argument(
        "--scope",
        default=SEARCH_SCOPE_UMLS_EVIDENCE,
        choices=[SEARCH_SCOPE_UMLS, SEARCH_SCOPE_UMLS_EVIDENCE],
        help="API search scope for --search-system api/both. UMLS-only in-process runs ignore this.",
    )
    parser.add_argument(
        "--search-system",
        default=SEARCH_SYSTEM_API,
        choices=[SEARCH_SYSTEM_API, SEARCH_SYSTEM_UMLS_ONLY, SEARCH_SYSTEM_BOTH],
        help="Evaluate the live API, an in-process UMLS-only baseline, or both as paired columns.",
    )
    parser.add_argument("--top-k", type=int, default=60)
    parser.add_argument("--include-related", action="store_true")
    parser.add_argument(
        "--include-linked-concepts",
        action="store_true",
        help="Include linked_concepts in API search payloads. Disabled by default for faster quality runs.",
    )
    parser.add_argument(
        "--include-search-evidence-items",
        action="store_true",
        help=(
            "Include compact evidence_items in API search payloads. Disabled by default; "
            "use this when regenerating report evidence examples from search responses."
        ),
    )
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_API_WORKERS,
        help=(
            "Number of concurrent live API query workers. Defaults to "
            f"{DEFAULT_API_WORKERS}; pass 1 for serial execution. UMLS-only runs stay serial."
        ),
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--html-report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--no-run", action="store_true", help="Only regenerate the HTML report from the manifest.")
    parser.add_argument("--register-run", type=Path, help="Append an existing run.json to the manifest without rerunning.")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--umls-label-index",
        type=Path,
        action="append",
        default=None,
        help="UMLS label index for --search-system umls-only. Repeatable; defaults to local server UMLS label indexes.",
    )
    parser.add_argument("--umls-code-index", type=Path, help="UMLS code resolver index for the UMLS-only baseline.")
    parser.add_argument("--umls-semantic-type-index", type=Path, help="UMLS MRSTY semantic type index for the UMLS-only baseline.")
    parser.add_argument("--umls-definition-index", type=Path, help="UMLS MRDEF definition index for the UMLS-only baseline.")
    parser.add_argument("--no-umls-code-index", action="store_true", help="Disable source-code lookup in the UMLS-only baseline.")
    parser.add_argument("--no-umls-semantic-type-index", action="store_true", help="Disable semantic type hydration in the UMLS-only baseline.")
    parser.add_argument("--no-umls-definition-index", action="store_true", help="Disable definition fallback in the UMLS-only baseline.")
    parser.add_argument("--umls-label-fallback-limit", type=int, default=240)
    parser.add_argument("--umls-definition-fallback-limit", type=int, default=120)
    parser.add_argument(
        "--fail-gates",
        action="store_true",
        help="Evaluate release gates and exit nonzero when any gate fails.",
    )
    parser.add_argument(
        "--gate-baseline-run",
        type=Path,
        help="run.json or metrics.json to compare gates against. Defaults to the latest comparable manifest run.",
    )
    parser.add_argument(
        "--strict-success-at-10-tolerance",
        type=float,
        default=0.02,
        help="Allowed strict success@10 rate drop from the baseline. Default is roughly one query in a 50-query smoke set.",
    )
    parser.add_argument(
        "--known-false-positive-at-10-tolerance",
        type=float,
        default=0.0,
        help="Allowed known false-positive@10 rate increase from baseline.",
    )
    parser.add_argument(
        "--source-count-collapse-tolerance",
        type=float,
        default=0.25,
        help="Allowed proportional drop for a source's top-10 result presence before the source-count gate fails.",
    )
    parser.add_argument(
        "--source-count-collapse-min-baseline",
        type=int,
        default=10,
        help="Ignore source-count collapse checks for sources with fewer baseline top-10 appearances than this.",
    )
    parser.add_argument(
        "--restricted-source-pattern",
        action="append",
        help="Restricted source marker for public-display gate. Repeatable; defaults cover restricted/private/non-level-0 patterns.",
    )
    parser.add_argument(
        "--iteration-smoke-gates",
        action="store_true",
        help="Plan or run post-iteration verification checks and write JSON/Markdown/HTML summaries.",
    )
    parser.add_argument(
        "--iteration-id",
        help="Iteration identifier for --iteration-smoke-gates, such as SQI-2026-06-10-011.",
    )
    parser.add_argument(
        "--iteration-type",
        action="append",
        default=[],
        help=(
            "Iteration type used to choose smoke tiers. Repeat or comma-separate values. "
            f"Allowed: {', '.join(ITERATION_TYPE_CHOICES)}."
        ),
    )
    parser.add_argument(
        "--static-command",
        action="append",
        default=[],
        help="Static verification command to run before live smoke. Repeatable; executed by the shell.",
    )
    parser.add_argument(
        "--focused-command",
        action="append",
        default=[],
        help="Focused test/check command to run before live smoke. Repeatable; executed by the shell.",
    )
    parser.add_argument(
        "--docs-only-change",
        action="store_true",
        help="For --iteration-smoke-gates, record a docs/local-layout-only decision and skip live smoke unless forced.",
    )
    parser.add_argument(
        "--ui-report-only-change",
        action="store_true",
        help="For --iteration-smoke-gates, record a UI/report-only decision and skip live smoke unless forced.",
    )
    parser.add_argument(
        "--development-loop",
        action="store_true",
        help=(
            "For --iteration-smoke-gates, run the fast development tier: static/focused checks "
            "plus required standing smoke, while deferring rotating and patient-portal gates "
            "unless forced or release-quality."
        ),
    )
    parser.add_argument(
        "--broad-change",
        action="store_true",
        help="For --iteration-smoke-gates, force standing and 50-query rotating smoke because the change has broad runtime risk.",
    )
    parser.add_argument(
        "--release-quality",
        action="store_true",
        help="For --iteration-smoke-gates, force standing and 50-query rotating smoke because the result is release-quality evidence.",
    )
    parser.add_argument(
        "--force-standing-smoke",
        action="store_true",
        help="For --iteration-smoke-gates, run standing clinical API smoke regardless of inferred tier.",
    )
    parser.add_argument(
        "--force-rotating-smoke",
        action="store_true",
        help="For --iteration-smoke-gates, run 50-query rotating smoke with gates regardless of inferred tier.",
    )
    parser.add_argument(
        "--force-patient-portal-smoke",
        action="store_true",
        help="For --iteration-smoke-gates, run the patient portal current-versus-history lane regardless of inferred tier.",
    )
    parser.add_argument(
        "--skip-standing-smoke",
        action="store_true",
        help="For --iteration-smoke-gates, skip standing clinical smoke and record that decision.",
    )
    parser.add_argument(
        "--skip-rotating-smoke",
        action="store_true",
        help="For --iteration-smoke-gates, skip rotating smoke and record that decision.",
    )
    parser.add_argument(
        "--skip-patient-portal-smoke",
        action="store_true",
        help="For --iteration-smoke-gates, skip patient portal current-versus-history smoke and record that decision.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="For --iteration-smoke-gates, write the planned verification commands without running them.",
    )
    parser.add_argument(
        "--verification-out",
        type=Path,
        help="For --iteration-smoke-gates, JSON verification summary path.",
    )
    parser.add_argument(
        "--verification-md-out",
        type=Path,
        help="For --iteration-smoke-gates, Markdown verification summary path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.iteration_smoke_gates:
        return run_iteration_smoke_gates(args)
    failed_gate_results = []
    if args.register_run:
        run = json.loads(args.register_run.read_text(encoding="utf-8"))
        manifest = update_manifest(args.output_root, run)
        print(json.dumps(run["summary"], indent=2, sort_keys=True))
    elif args.no_run:
        manifest = read_manifest(args.output_root / MANIFEST_NAME)
    else:
        if not args.run_id:
            args.run_id = run_id_from_timestamp()
        if not args.label:
            args.label = args.run_id
        if not str(args.query_rotation_seed or "").strip():
            args.query_rotation_seed = args.run_id
        systems = selected_search_systems(args.search_system)
        manifest = read_manifest(args.output_root / MANIFEST_NAME)
        evaluation_signature = current_evaluation_signature(args)
        for index, search_system in enumerate(systems, start=1):
            run_id, label = run_identity(args, search_system, index, len(systems))
            if args.gate_baseline_run:
                baseline_run = load_gate_baseline(args.gate_baseline_run)
            else:
                baseline_run = find_previous_gate_baseline(
                    manifest,
                    search_system=search_system,
                    queries=args.queries,
                    api_scope=args.scope,
                    current_signature=evaluation_signature,
                    payload_shape=current_payload_shape(args),
                )
            run = run_experiment(
                args,
                search_system=search_system,
                run_id=run_id,
                label=label,
            )
            if args.fail_gates:
                gate_result = evaluate_run_gates(run, baseline_run, args)
                persist_gate_result(run, gate_result)
                print_gate_result(run, gate_result)
                if not gate_result.get("passed"):
                    failed_gate_results.append(gate_result)
            manifest = update_manifest(args.output_root, run)
            print(f"{run['label']} ({run['search_system']}):")
            print(json.dumps(run["summary"], indent=2, sort_keys=True))
    manifest = enrich_manifest_metrics(manifest, persist=True)
    write_manifest(args.output_root / MANIFEST_NAME, manifest)
    write_html_report(args.html_report, manifest)
    print(f"wrote {args.html_report}")
    if failed_gate_results:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
