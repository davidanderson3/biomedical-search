#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import random
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "build" / "private_umls_api_audits" / "20260930T145539Z_uniform_n400_seed20260930"
DEFAULT_LOCAL_URL = "http://127.0.0.1:8766"
INCLUDE_STATUSES = {"include", "included", "yes", "approved", "reviewed"}
EXCLUDE_STATUSES = {"exclude", "excluded", "no"}

COMPARISON_FIELDS = [
    "id",
    "search_term",
    "normalized_token_count",
    "sum_unique_users",
    "umls_complete",
    "vector_complete",
    "umls_hit_count_at_k",
    "vector_hit_count_at_k",
    "overlap_count_at_k",
    "umls_only_count_at_k",
    "vector_only_count_at_k",
    "umls_no_hit_vector_rescue",
    "umls_cuis",
    "vector_cuis",
    "umls_top_cui",
    "umls_top_name",
    "vector_top_cui",
    "vector_top_name",
    "vector_backend",
    "vector_elapsed_ms",
    "umls_error",
    "vector_error",
]

PROVENANCE_FIELDS = [
    "id",
    "search_term",
    "cui",
    "label",
    "in_umls",
    "umls_rank",
    "in_vector",
    "vector_rank",
    "vector_score",
]

JUDGMENT_FIELDS = [
    "relevance_grade",
    "review_note",
    "pool_id",
    "id",
    "search_term",
    "cui",
    "label",
]

QUERY_REVIEW_FIELDS = [
    "query_status",
    "intended_concept_note",
    "id",
    "search_term",
    "normalized_token_count",
    "sum_unique_users",
]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def write_tsv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def preserve_review_columns(
    path: Path,
    rows: list[dict[str, object]],
    *,
    key: str,
    fields: tuple[str, ...],
) -> list[dict[str, object]]:
    if not path.exists():
        return rows
    existing = {row.get(key, ""): row for row in read_tsv(path) if row.get(key, "")}
    merged = []
    for row in rows:
        previous = existing.get(str(row.get(key, ""))) or {}
        merged.append(
            {
                **row,
                **{
                    field: previous.get(field, row.get(field, ""))
                    for field in fields
                    if previous.get(field, "")
                },
            }
        )
    return merged


def api_get(base_url: str, query: str, top_k: int, timeout: float) -> dict:
    params = {
        "q": query,
        "k": top_k,
        "limit": top_k,
        "scope": "umls_evidence",
        "mode": "balanced",
        "related": 0,
        "linked": 0,
        "evidence_items": 0,
    }
    request = Request(
        f"{base_url.rstrip('/')}/api/search?{urlencode(params)}",
        headers={"Accept": "application/json", "User-Agent": "umls-vector-head-to-head/1.0"},
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def vector_cache_path(cache_dir: Path, query: str, top_k: int) -> Path:
    digest = hashlib.sha256(f"{top_k}\0{query.casefold()}".encode()).hexdigest()
    return cache_dir / f"{digest}.json"


def get_vector_payload(
    *, cache_dir: Path, base_url: str, query: str, top_k: int, timeout: float
) -> tuple[dict | None, str, bool]:
    path = vector_cache_path(cache_dir, query, top_k)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")), "", True
    try:
        payload = api_get(base_url, query, top_k, timeout)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return payload, "", False
    except Exception as exc:  # noqa: BLE001 - retain failed queries in comparison output
        return None, str(exc)[:500], False


def split_cuis(value: str, top_k: int) -> list[str]:
    cuis = [part.strip().upper() for part in value.split("|") if part.strip()]
    return list(dict.fromkeys(cuis))[:top_k]


def baseline_names(row: dict[str, str]) -> dict[str, str]:
    names = {}
    for chunk in str(row.get("umls_hits") or "").split(" | "):
        match = re.match(r"\d+:(C\d{7})\s+(.*)", chunk.strip(), re.IGNORECASE)
        if match:
            names[match.group(1).upper()] = match.group(2).strip()
    return names


def vector_hits(payload: dict | None, top_k: int) -> list[dict]:
    hits = []
    seen = set()
    for row in (payload or {}).get("hits") or []:
        cui = str(row.get("cui") or "").strip().upper()
        if not cui or cui in seen:
            continue
        seen.add(cui)
        hits.append(
            {
                "cui": cui,
                "name": str(row.get("name") or ""),
                "score": row.get("rank_score", row.get("score", "")),
            }
        )
        if len(hits) >= top_k:
            break
    return hits


def pool_id(query_id: str, cui: str, seed: int) -> str:
    digest = hashlib.sha256(f"{seed}\0{query_id}\0{cui}".encode()).hexdigest()[:12]
    return f"p_{digest}"


def build_outputs(
    base_rows: list[dict[str, str]],
    payloads: dict[str, tuple[dict | None, str]],
    *,
    top_k: int,
    seed: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    comparisons = []
    provenance = []
    judgments = []
    query_review = []
    for row in base_rows:
        query_id = row["id"]
        payload, vector_error = payloads[query_id]
        umls_complete = not bool(row.get("umls_error"))
        vector_complete = not bool(vector_error)
        umls_cuis = split_cuis(row.get("umls_hit_cuis", ""), top_k) if umls_complete else []
        umls_names = baseline_names(row)
        semantic_hits = vector_hits(payload, top_k) if vector_complete else []
        semantic_cuis = [hit["cui"] for hit in semantic_hits]
        semantic_by_cui = {hit["cui"]: hit for hit in semantic_hits}
        umls_set = set(umls_cuis)
        semantic_set = set(semantic_cuis)
        overlap = umls_set & semantic_set
        pool = sorted(umls_set | semantic_set)
        comparisons.append(
            {
                "id": query_id,
                "search_term": row["search_term"],
                "normalized_token_count": row.get("normalized_token_count", ""),
                "sum_unique_users": row.get("sum_unique_users", ""),
                "umls_complete": "1" if umls_complete else "0",
                "vector_complete": "1" if vector_complete else "0",
                "umls_hit_count_at_k": len(umls_cuis),
                "vector_hit_count_at_k": len(semantic_cuis),
                "overlap_count_at_k": len(overlap),
                "umls_only_count_at_k": len(umls_set - semantic_set),
                "vector_only_count_at_k": len(semantic_set - umls_set),
                "umls_no_hit_vector_rescue": "1" if umls_complete and not umls_set and semantic_set else "0",
                "umls_cuis": "|".join(umls_cuis),
                "vector_cuis": "|".join(semantic_cuis),
                "umls_top_cui": umls_cuis[0] if umls_cuis else "",
                "umls_top_name": umls_names.get(umls_cuis[0], "") if umls_cuis else "",
                "vector_top_cui": semantic_cuis[0] if semantic_cuis else "",
                "vector_top_name": semantic_hits[0]["name"] if semantic_hits else "",
                "vector_backend": (payload or {}).get("backend", ""),
                "vector_elapsed_ms": (payload or {}).get("elapsed_ms", ""),
                "umls_error": row.get("umls_error", ""),
                "vector_error": vector_error,
            }
        )
        query_review.append(
            {
                "query_status": "",
                "intended_concept_note": "",
                "id": query_id,
                "search_term": row["search_term"],
                "normalized_token_count": row.get("normalized_token_count", ""),
                "sum_unique_users": row.get("sum_unique_users", ""),
            }
        )
        if not (umls_complete and vector_complete):
            continue
        pool_rows = []
        for cui in pool:
            umls_rank = umls_cuis.index(cui) + 1 if cui in umls_set else ""
            vector_rank = semantic_cuis.index(cui) + 1 if cui in semantic_set else ""
            vector_hit = semantic_by_cui.get(cui) or {}
            label = str(vector_hit.get("name") or umls_names.get(cui) or cui)
            source_row = {
                "id": query_id,
                "search_term": row["search_term"],
                "cui": cui,
                "label": label,
                "in_umls": "1" if cui in umls_set else "0",
                "umls_rank": umls_rank,
                "in_vector": "1" if cui in semantic_set else "0",
                "vector_rank": vector_rank,
                "vector_score": vector_hit.get("score", ""),
            }
            provenance.append(source_row)
            pool_rows.append(
                {
                    "relevance_grade": "",
                    "review_note": "",
                    "pool_id": pool_id(query_id, cui, seed),
                    "id": query_id,
                    "search_term": row["search_term"],
                    "cui": cui,
                    "label": label,
                }
            )
        random.Random(f"{seed}:{query_id}").shuffle(pool_rows)
        judgments.extend(pool_rows)
    return comparisons, provenance, judgments, query_review


def safe_rate(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def preliminary_summary(
    comparisons: list[dict[str, object]], provenance: list[dict[str, object]], *, top_k: int
) -> dict[str, object]:
    complete = [row for row in comparisons if row["umls_complete"] == "1" and row["vector_complete"] == "1"]
    umls_pairs = sum(int(row["umls_hit_count_at_k"]) for row in complete)
    vector_pairs = sum(int(row["vector_hit_count_at_k"]) for row in complete)
    overlap_pairs = sum(int(row["overlap_count_at_k"]) for row in complete)
    vector_only = sum(int(row["vector_only_count_at_k"]) for row in complete)
    umls_only = sum(int(row["umls_only_count_at_k"]) for row in complete)
    rescues = sum(int(row["umls_no_hit_vector_rescue"]) for row in complete)
    no_hits = sum(int(row["umls_hit_count_at_k"]) == 0 for row in complete)
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "status": "preliminary_unjudged_pool",
        "top_k": top_k,
        "sampled_queries": len(comparisons),
        "complete_paired_queries": len(complete),
        "incomplete_queries": len(comparisons) - len(complete),
        "umls_query_cui_pairs_at_k": umls_pairs,
        "vector_query_cui_pairs_at_k": vector_pairs,
        "overlap_query_cui_pairs_at_k": overlap_pairs,
        "vector_only_candidate_pairs_at_k": vector_only,
        "umls_only_candidate_pairs_at_k": umls_only,
        "queries_with_vector_only_candidates": sum(int(row["vector_only_count_at_k"]) > 0 for row in complete),
        "umls_no_hit_queries": no_hits,
        "umls_no_hit_queries_with_vector_candidates": rescues,
        "umls_no_hit_candidate_rescue_rate": safe_rate(rescues, no_hits),
        "pooled_query_cui_pairs_to_judge": len(provenance),
        "interpretation_warning": (
            "System-only CUIs are candidates, not proven relevant results. Judge the blinded top-k union before "
            "using recall, precision, or missed-result language. The semantic prototype is a SapBERT-based "
            "hybrid index over UMLS-linked evidence, not a labels-only vector index."
        ),
    }


def select_pilot(
    comparisons: list[dict[str, object]],
    judgments: list[dict[str, object]],
    query_review: list[dict[str, object]],
    *,
    size: int,
    seed: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[str]]:
    complete_ids = sorted(
        str(row["id"])
        for row in comparisons
        if row["umls_complete"] == "1" and row["vector_complete"] == "1"
    )
    if size <= 0 or size >= len(complete_ids):
        selected = complete_ids
    else:
        selected = sorted(random.Random(seed).sample(complete_ids, size))
    selected_set = set(selected)
    pilot_judgments = [row for row in judgments if str(row["id"]) in selected_set]
    pilot_queries = [row for row in query_review if str(row["id"]) in selected_set]
    return pilot_judgments, pilot_queries, selected


def dcg(grades: list[int]) -> float:
    return sum((2**grade - 1) / math.log2(rank + 2) for rank, grade in enumerate(grades))


def reciprocal_rank(ranked: list[str], relevant: set[str]) -> float:
    for rank, cui in enumerate(ranked, start=1):
        if cui in relevant:
            return 1.0 / rank
    return 0.0


def ndcg(ranked: list[str], grades: dict[str, int]) -> float:
    actual = dcg([grades.get(cui, 0) for cui in ranked])
    ideal = dcg(sorted(grades.values(), reverse=True)[: len(ranked)])
    return actual / ideal if ideal else 0.0


def bootstrap_difference(
    query_stats: list[dict[str, object]], *, iterations: int = 5000, seed: int = 20260930
) -> tuple[float, float]:
    if not query_stats:
        return 0.0, 0.0
    rng = random.Random(seed)
    diffs = []
    count = len(query_stats)
    for _ in range(iterations):
        sample = [query_stats[rng.randrange(count)] for _ in range(count)]
        relevant = sum(int(row["relevant_count"]) for row in sample)
        vector_found = sum(int(row["vector_relevant_count"]) for row in sample)
        umls_found = sum(int(row["umls_relevant_count"]) for row in sample)
        diffs.append((vector_found - umls_found) / relevant if relevant else 0.0)
    diffs.sort()
    return diffs[int(0.025 * iterations)], diffs[min(iterations - 1, int(0.975 * iterations))]


def score_reviewed_pool(
    *, judgments_path: Path, provenance_path: Path, query_review_path: Path
) -> tuple[list[dict[str, object]], dict[str, object]]:
    judgments = read_tsv(judgments_path)
    provenance = read_tsv(provenance_path)
    query_reviews = {row["id"]: row for row in read_tsv(query_review_path)}
    provenance_by_pair = {(row["id"], row["cui"]): row for row in provenance}
    judgments_by_query: dict[str, list[dict[str, str]]] = {}
    for row in judgments:
        judgments_by_query.setdefault(row["id"], []).append(row)
    query_stats = []
    excluded = 0
    pending_queries = 0
    for query_id, rows in judgments_by_query.items():
        query_review = query_reviews.get(query_id) or {}
        status = str(query_review.get("query_status") or "").strip().lower()
        if status in EXCLUDE_STATUSES:
            excluded += 1
            continue
        if status not in INCLUDE_STATUSES:
            pending_queries += 1
            continue
        grades = {}
        invalid = False
        for row in rows:
            raw = str(row.get("relevance_grade") or "").strip()
            if raw not in {"0", "1", "2"}:
                invalid = True
                break
            grades[row["cui"]] = int(raw)
        if invalid:
            pending_queries += 1
            continue
        relevant = {cui for cui, grade in grades.items() if grade >= 1}
        umls_ranked = [
            row["cui"]
            for row in sorted(
                (provenance_by_pair[(query_id, cui)] for cui in grades),
                key=lambda item: int(item["umls_rank"] or 9999),
            )
            if row["in_umls"] == "1"
        ]
        vector_ranked = [
            row["cui"]
            for row in sorted(
                (provenance_by_pair[(query_id, cui)] for cui in grades),
                key=lambda item: int(item["vector_rank"] or 9999),
            )
            if row["in_vector"] == "1"
        ]
        umls_rel = set(umls_ranked) & relevant
        vector_rel = set(vector_ranked) & relevant
        query_stats.append(
            {
                "id": query_id,
                "search_term": rows[0]["search_term"],
                "relevant_count": len(relevant),
                "umls_relevant_count": len(umls_rel),
                "vector_relevant_count": len(vector_rel),
                "umls_missed_relevant_count": len(relevant - set(umls_ranked)),
                "vector_missed_relevant_count": len(relevant - set(vector_ranked)),
                "umls_precision_at_k": safe_rate(len(umls_rel), len(umls_ranked)),
                "vector_precision_at_k": safe_rate(len(vector_rel), len(vector_ranked)),
                "umls_recall_in_pool": safe_rate(len(umls_rel), len(relevant)),
                "vector_recall_in_pool": safe_rate(len(vector_rel), len(relevant)),
                "umls_mrr": round(reciprocal_rank(umls_ranked, relevant), 6),
                "vector_mrr": round(reciprocal_rank(vector_ranked, relevant), 6),
                "umls_ndcg": round(ndcg(umls_ranked, grades), 6),
                "vector_ndcg": round(ndcg(vector_ranked, grades), 6),
            }
        )
    relevant_pairs = sum(int(row["relevant_count"]) for row in query_stats)
    umls_relevant = sum(int(row["umls_relevant_count"]) for row in query_stats)
    vector_relevant = sum(int(row["vector_relevant_count"]) for row in query_stats)
    lower, upper = bootstrap_difference(query_stats)
    evaluable_recall = [row for row in query_stats if int(row["relevant_count"]) > 0]
    vector_wins = sum(float(row["vector_recall_in_pool"]) > float(row["umls_recall_in_pool"]) for row in evaluable_recall)
    umls_wins = sum(float(row["vector_recall_in_pool"]) < float(row["umls_recall_in_pool"]) for row in evaluable_recall)
    ties = len(evaluable_recall) - vector_wins - umls_wins

    def mean(field: str) -> float:
        return round(sum(float(row[field]) for row in query_stats) / len(query_stats), 6) if query_stats else 0.0

    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "status": "reviewed_pooled_evaluation",
        "included_complete_queries": len(query_stats),
        "excluded_queries": excluded,
        "pending_or_incomplete_queries": pending_queries,
        "relevant_pooled_query_cui_pairs": relevant_pairs,
        "umls_relevant_pairs_retrieved": umls_relevant,
        "vector_relevant_pairs_retrieved": vector_relevant,
        "umls_micro_recall_in_judged_pool": safe_rate(umls_relevant, relevant_pairs),
        "vector_micro_recall_in_judged_pool": safe_rate(vector_relevant, relevant_pairs),
        "vector_minus_umls_micro_recall": round(
            safe_rate(vector_relevant - umls_relevant, relevant_pairs), 6
        ),
        "vector_minus_umls_micro_recall_bootstrap_95_ci": [round(lower, 6), round(upper, 6)],
        "umls_missed_relevant_result_percentage": round(100 * (relevant_pairs - umls_relevant) / relevant_pairs, 2)
        if relevant_pairs
        else 0.0,
        "vector_missed_relevant_result_percentage": round(100 * (relevant_pairs - vector_relevant) / relevant_pairs, 2)
        if relevant_pairs
        else 0.0,
        "mean_umls_precision_at_k": mean("umls_precision_at_k"),
        "mean_vector_precision_at_k": mean("vector_precision_at_k"),
        "mean_umls_mrr": mean("umls_mrr"),
        "mean_vector_mrr": mean("vector_mrr"),
        "mean_umls_ndcg": mean("umls_ndcg"),
        "mean_vector_ndcg": mean("vector_ndcg"),
        "vector_recall_wins": vector_wins,
        "umls_recall_wins": umls_wins,
        "recall_ties": ties,
        "evaluation_boundary": (
            "Recall is measured within the pooled top-k union, not against every relevant UMLS concept. "
            "Judgments are blinded to retrieval source and clustered by query for the bootstrap interval."
        ),
    }
    return query_stats, summary


def pct(value: object) -> str:
    return f"{100 * float(value or 0):.1f}%"


def render_report(
    output_path: Path,
    summary: dict[str, object],
    comparisons: list[dict[str, object]],
    *,
    scored: bool,
) -> None:
    if scored:
        ci = summary["vector_minus_umls_micro_recall_bootstrap_95_ci"]
        cards = f"""
        <article class="card hero"><span>UMLS missed relevant results</span><strong>{summary['umls_missed_relevant_result_percentage']:.1f}%</strong><small>Within the blinded, judged top-k union</small></article>
        <article class="card"><span>Semantic prototype missed</span><strong>{summary['vector_missed_relevant_result_percentage']:.1f}%</strong><small>Same queries and judged pool</small></article>
        <article class="card"><span>Recall difference</span><strong>{pct(summary['vector_minus_umls_micro_recall'])}</strong><small>Semantic minus UMLS; clustered 95% interval {pct(ci[0])} to {pct(ci[1])}</small></article>
        <article class="card"><span>Recall wins</span><strong>{summary['vector_recall_wins']}–{summary['umls_recall_wins']}</strong><small>Semantic wins versus UMLS wins; {summary['recall_ties']} ties</small></article>
        <article class="card"><span>Mean reciprocal rank</span><strong>{summary['mean_vector_mrr']:.3f}</strong><small>Semantic prototype versus {summary['mean_umls_mrr']:.3f} UMLS</small></article>
        <article class="card"><span>Mean nDCG</span><strong>{summary['mean_vector_ndcg']:.3f}</strong><small>Semantic prototype versus {summary['mean_umls_ndcg']:.3f} UMLS</small></article>"""
        status = "Reviewed head-to-head result"
        warning = html.escape(str(summary["evaluation_boundary"]))
    else:
        cards = f"""
        <article class="card hero"><span>Vector-only candidates</span><strong>{summary['vector_only_candidate_pairs_at_k']:,}</strong><small>Query–CUI pairs absent from UMLS top {summary['top_k']}; relevance not yet judged</small></article>
        <article class="card"><span>Queries with vector-only candidates</span><strong>{summary['queries_with_vector_only_candidates']}</strong><small>Out of {summary['complete_paired_queries']} complete paired comparisons</small></article>
        <article class="card"><span>UMLS no-hits rescued</span><strong>{pct(summary['umls_no_hit_candidate_rescue_rate'])}</strong><small>{summary['umls_no_hit_queries_with_vector_candidates']} of {summary['umls_no_hit_queries']} no-hit queries gained semantic candidates</small></article>
        <article class="card"><span>Judgments required</span><strong>{summary['pooled_query_cui_pairs_to_judge']:,}</strong><small>Full blinded pool; the uniform {summary.get('pilot_query_count', 0)}-query pilot has {summary.get('pilot_judgment_rows', 0):,} rows</small></article>
        <article class="card"><span>Paired queries</span><strong>{summary['complete_paired_queries']}</strong><small>{summary['incomplete_queries']} incomplete, including UMLS API errors</small></article>
        <article class="card"><span>Top-k</span><strong>{summary['top_k']}</strong><small>Same cutoff for both systems</small></article>"""
        status = "Preliminary candidate-pool report"
        warning = html.escape(str(summary["interpretation_warning"]))
    if scored:
        narrative = (
            f"We ran the same included real queries through released UMLS search and the semantic/hybrid search. "
            f"Among {summary['included_complete_queries']} included queries, the judged pooled results show "
            f"that UMLS missed {summary['umls_missed_relevant_result_percentage']:.1f}% of relevant concepts, "
            f"versus {summary['vector_missed_relevant_result_percentage']:.1f}% missed by the semantic system. "
            "This is the management metric: the percentage of relevant concepts absent from each system's top-k results."
        )
    else:
        narrative = (
            f"We ran {summary['complete_paired_queries']} complete real-query comparisons through both systems. "
            f"The semantic search returned {summary['vector_only_candidate_pairs_at_k']:,} query–concept candidates "
            f"that were absent from released UMLS's top {summary['top_k']} results, across "
            f"{summary['queries_with_vector_only_candidates']} queries. "
            f"UMLS returned no result for {summary['umls_no_hit_queries']} queries; semantic search produced "
            f"candidates for {summary['umls_no_hit_queries_with_vector_candidates']} of them. "
            "These are candidate opportunities, not yet relevance-validated misses."
        )
    complete_comparisons = [
        row
        for row in comparisons
        if str(row.get("umls_complete", "")) == "1" and str(row.get("vector_complete", "")) == "1"
    ]
    # Keep the management-facing HTML compact.  The complete per-query output
    # remains available in query_comparisons.tsv for analysis.
    top_rows = sorted(
        complete_comparisons,
        key=lambda row: (-int(row.get("vector_only_count_at_k", 0)), str(row.get("search_term", ""))),
    )[:12]
    table = "".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('search_term', '')))}</td>"
        f"<td>{row.get('umls_hit_count_at_k', '')}</td>"
        f"<td>{row.get('vector_hit_count_at_k', '')}</td>"
        f"<td>{row.get('overlap_count_at_k', '')}</td>"
        f"<td>{row.get('vector_only_count_at_k', '')}</td>"
        f"<td>{html.escape(str(row.get('vector_top_name', '')))}</td>"
        "</tr>"
        for row in top_rows
    )
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>UMLS vs Semantic Search</title><style>
:root{{--ink:#17232e;--muted:#617180;--paper:#f4f7f6;--card:#fff;--line:#d9e3e0;--teal:#08766e;--blue:#183f60;--amber:#b66d0a}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}header{{background:linear-gradient(120deg,var(--blue),var(--teal));color:#fff;padding:46px max(24px,calc((100% - 1120px)/2))}}h1{{font-size:clamp(30px,5vw,48px);line-height:1.05;margin:8px 0}}header p{{max-width:820px;color:#d9edeb}}main{{max-width:1120px;margin:auto;padding:28px 24px 60px}}.eyebrow{{font-size:12px;text-transform:uppercase;letter-spacing:.12em;font-weight:800}}.status{{display:inline-block;background:#fff0cd;color:#704500;border-radius:999px;padding:6px 11px;font-weight:750}}.metrics{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:15px;margin:24px 0}}.card{{background:#fff;border:1px solid var(--line);border-radius:14px;padding:19px;box-shadow:0 4px 18px #183f600c}}.card.hero{{border-top:5px solid var(--teal)}}.card span,.card small{{display:block;color:var(--muted)}}.card strong{{display:block;color:var(--blue);font-size:33px;margin:7px 0}}.notice{{background:#fff6e5;border-left:5px solid var(--amber);border-radius:8px;padding:16px 18px;margin:24px 0}}.bottom-line{{background:#fff;border-left:5px solid var(--teal);border-radius:8px;padding:18px;margin:12px 0 24px;font-size:17px;line-height:1.6}}h2{{margin:30px 0 8px}}.table-wrap{{overflow:auto;max-height:650px;border:1px solid var(--line);border-radius:12px;background:#fff}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{padding:10px 12px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}}th{{position:sticky;top:0;background:#eaf2f0;color:var(--blue)}}tr:nth-child(even){{background:#fafcfc}}a{{color:var(--teal);font-weight:700}}footer{{margin-top:32px;color:var(--muted);font-size:13px}}@media(max-width:800px){{.metrics{{grid-template-columns:1fr}}}}@media print{{.table-wrap{{max-height:none;overflow:visible}}th{{position:static}}}}
</style></head><body><header><div class="eyebrow">Search quality · Blinded pooled evaluation</div><h1>Released UMLS Search vs SapBERT Semantic Search</h1><p>Paired comparison on the same real-query sample. The candidate replacement is a semantic/hybrid architecture that preserves UMLS CUIs while adding biomedical vector retrieval and evidence-derived language.</p></header><main><p class="status">{status}</p><section class="metrics">{cards}</section><div class="notice"><strong>Do not skip relevance review.</strong> {warning}</div>
<h2>What happened</h2><p class="bottom-line">{narrative}</p><h2>Illustrative candidate-set differences</h2><p>The 12 largest differences are shown here; the complete comparison is in <a href="query_comparisons.tsv">query_comparisons.tsv</a>.</p><div class="table-wrap"><table><thead><tr><th>Query</th><th>UMLS</th><th>Semantic</th><th>Overlap</th><th>Semantic-only</th><th>Semantic top result</th></tr></thead><tbody>{table}</tbody></table></div>
<h2>Review files</h2><ul><li><a href="pilot{summary.get('pilot_query_count', 0)}_query_review.tsv">Pilot query inclusion review</a></li><li><a href="pilot{summary.get('pilot_query_count', 0)}_blinded_relevance_judgments.tsv">Pilot blinded relevance judgments</a></li><li><a href="blinded_relevance_judgments.tsv">Full blinded relevance judgments</a></li><li><a href="pool_provenance_private.tsv">Private system provenance — open only after judging</a></li><li><a href="query_comparisons.tsv">Per-query comparison</a></li></ul>
<h2>Published precedent</h2><ul><li><a href="https://pubmed.ncbi.nlm.nih.gov/31837099/">Performance evaluation of three semantic expansions to query PubMed</a>: three independent reviewers judged the first 20 results; performance varied substantially by descriptor.</li><li><a href="https://pubmed.ncbi.nlm.nih.gov/32496201/">Best semantic expansion across all MeSH descriptors</a>: 239,724 searches across 28,313 MeSH descriptors found UMLS expansion strongest for recall/F-measure, MeSH strongest for precision, and PubMed automatic term mapping weakest overall.</li><li><a href="https://pubmed.ncbi.nlm.nih.gov/26363352/">Automatically finding relevant citations for clinical guideline development</a>: query expansion improved recall from 51.5% to 80.2%, with a small precision reduction.</li><li><a href="https://pubmed.ncbi.nlm.nih.gov/15471753/">Reformulation of consumer health queries with professional terminology</a>: 42% of reformulated searches improved, 19% worsened, and 39% were unchanged—evidence for both semantic benefit and drift controls.</li><li><a href="https://pubmed.ncbi.nlm.nih.gov/37930897/">MedCPT</a>: dense biomedical retrieval trained from 255 million PubMed query–article pairs outperformed lexical and larger-model baselines across six tasks.</li><li><a href="https://pubmed.ncbi.nlm.nih.gov/41921511/">2026 critical evaluation of generative query expansion</a>: eight LLM expansion strategies showed method- and dataset-dependent gains and losses, supporting a paired judged evaluation rather than raw union size alone.</li></ul>
<footer>Generated {html.escape(str(summary['generated_utc']))}. Private log-derived analysis. This evaluates a pooled top-k candidate universe, not every potentially relevant UMLS concept.</footer></main></body></html>"""
    output_path.write_text(document, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a blinded pooled UMLS versus semantic-vector evaluation.")
    parser.add_argument("--baseline-run", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--base-url", default=DEFAULT_LOCAL_URL)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--seed", type=int, default=20260930)
    parser.add_argument(
        "--pilot-size",
        type=int,
        default=100,
        help="Also write a reproducible uniform pilot review subset. Use 0 for the full paired set.",
    )
    parser.add_argument("--score-reviewed", action="store_true")
    parser.add_argument("--judgments-file", type=Path)
    parser.add_argument("--query-review-file", type=Path)
    parser.add_argument("--provenance-file", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir or args.baseline_run / f"vector_comparison_top{args.top_k}"
    comparison_path = output_dir / "query_comparisons.tsv"
    provenance_path = output_dir / "pool_provenance_private.tsv"
    judgments_path = output_dir / "blinded_relevance_judgments.tsv"
    query_review_path = output_dir / "query_review.tsv"
    summary_path = output_dir / "summary.json"
    report_path = output_dir / "management_report.html"
    if args.score_reviewed:
        score_judgments_path = args.judgments_file or judgments_path
        score_query_review_path = args.query_review_file or query_review_path
        score_provenance_path = args.provenance_file or provenance_path
        query_stats, summary = score_reviewed_pool(
            judgments_path=score_judgments_path,
            provenance_path=score_provenance_path,
            query_review_path=score_query_review_path,
        )
        query_stats_path = output_dir / "reviewed_query_metrics.tsv"
        fields = list(query_stats[0]) if query_stats else ["id", "search_term"]
        write_tsv(query_stats_path, query_stats, fields)
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        comparisons = read_tsv(comparison_path)
        render_report(report_path, summary, comparisons, scored=True)
        print(
            f"UMLS missed relevant result percentage: {summary['umls_missed_relevant_result_percentage']}%"
        )
        print(
            f"Semantic prototype missed relevant result percentage: "
            f"{summary['vector_missed_relevant_result_percentage']}%"
        )
        print(f"updated reviewed HTML report at {report_path}")
        return 0 if query_stats else 2

    base_rows = read_tsv(args.baseline_run / "rows.tsv")
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = output_dir / "vector_payload_cache"
    payloads: dict[str, tuple[dict | None, str]] = {}
    cache_hits = 0
    completed = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(
                get_vector_payload,
                cache_dir=cache_dir,
                base_url=args.base_url,
                query=row["search_term"],
                top_k=args.top_k,
                timeout=args.timeout,
            ): row
            for row in base_rows
        }
        for future in as_completed(futures):
            row = futures[future]
            payload, error, cached = future.result()
            payloads[row["id"]] = (payload, error)
            cache_hits += int(cached)
            completed += 1
            if completed == 1 or completed % 25 == 0 or completed == len(base_rows):
                print(f"semantic search {completed}/{len(base_rows)} ({cache_hits} cache hits)", file=sys.stderr)
    comparisons, provenance, judgments, query_review = build_outputs(
        base_rows, payloads, top_k=args.top_k, seed=args.seed
    )
    judgments = preserve_review_columns(
        judgments_path,
        judgments,
        key="pool_id",
        fields=("relevance_grade", "review_note"),
    )
    query_review = preserve_review_columns(
        query_review_path,
        query_review,
        key="id",
        fields=("query_status", "intended_concept_note"),
    )
    pilot_judgments, pilot_queries, pilot_ids = select_pilot(
        comparisons,
        judgments,
        query_review,
        size=args.pilot_size,
        seed=args.seed,
    )
    pilot_judgments_path = output_dir / f"pilot{len(pilot_ids)}_blinded_relevance_judgments.tsv"
    pilot_query_review_path = output_dir / f"pilot{len(pilot_ids)}_query_review.tsv"
    pilot_judgments = preserve_review_columns(
        pilot_judgments_path,
        pilot_judgments,
        key="pool_id",
        fields=("relevance_grade", "review_note"),
    )
    pilot_queries = preserve_review_columns(
        pilot_query_review_path,
        pilot_queries,
        key="id",
        fields=("query_status", "intended_concept_note"),
    )
    write_tsv(comparison_path, comparisons, COMPARISON_FIELDS)
    write_tsv(provenance_path, provenance, PROVENANCE_FIELDS)
    write_tsv(judgments_path, judgments, JUDGMENT_FIELDS)
    write_tsv(query_review_path, query_review, QUERY_REVIEW_FIELDS)
    write_tsv(pilot_judgments_path, pilot_judgments, JUDGMENT_FIELDS)
    write_tsv(pilot_query_review_path, pilot_queries, QUERY_REVIEW_FIELDS)
    summary = preliminary_summary(comparisons, provenance, top_k=args.top_k)
    summary.update(
        {
            "baseline_run": str(args.baseline_run),
            "semantic_search_url": args.base_url,
            "vector_cache_hits_this_run": cache_hits,
            "comparison_tsv": str(comparison_path),
            "blinded_judgments_tsv": str(judgments_path),
            "private_provenance_tsv": str(provenance_path),
            "query_review_tsv": str(query_review_path),
            "pilot_query_count": len(pilot_ids),
            "pilot_judgment_rows": len(pilot_judgments),
            "pilot_blinded_judgments_tsv": str(pilot_judgments_path),
            "pilot_query_review_tsv": str(pilot_query_review_path),
        }
    )
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    render_report(report_path, summary, comparisons, scored=False)
    print(f"wrote blinded pool of {len(judgments)} query-CUI judgments to {judgments_path}")
    print(
        f"wrote uniform {len(pilot_ids)}-query pilot with {len(pilot_judgments)} judgments "
        f"to {pilot_judgments_path}"
    )
    print(f"wrote preliminary HTML report to {report_path}")
    return 1 if summary["incomplete_queries"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
