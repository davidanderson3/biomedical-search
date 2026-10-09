#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import getpass
import html
import json
import math
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_real_query_inventory import DEFAULT_INPUT_DIR, QueryRow, iter_query_rows  # noqa: E402
from compare_umls_api import QuerySpec, umls_hits, umls_search  # noqa: E402


DEFAULT_OUTPUT_ROOT = ROOT / "build" / "private_umls_api_audits"
DEFAULT_UMLS_BASE_URL = "https://uts-ws.nlm.nih.gov/rest"
VALID_SEARCH_TYPES = (
    "exact",
    "words",
    "normalizedString",
    "normalizedWords",
    "leftTruncation",
    "rightTruncation",
)

ROW_FIELDS = [
    "id",
    "search_term",
    "normalized_term",
    "normalized_token_count",
    "sum_unique_users",
    "source_rows",
    "privacy_flags",
    "search_type",
    "umls_hit_count",
    "umls_no_hit",
    "umls_top_cui",
    "umls_top_name",
    "umls_top_source",
    "umls_hit_cuis",
    "umls_hits",
    "umls_error",
]

REVIEW_FIELDS = [
    "review_status",
    "expected_cuis",
    "failure_class",
    "review_note",
    *ROW_FIELDS,
]

REVIEW_SCORE_FIELDS = [
    *REVIEW_FIELDS,
    "expected_result_count",
    "returned_expected_result_count",
    "missed_expected_result_count",
    "missed_expected_cuis",
    "expected_result_recall",
    "query_total_miss",
]

INCLUDED_REVIEW_STATUSES = {"approved", "include", "included", "relevant", "reviewed", "yes"}
CUI_RE = re.compile(r"\bC\d{7}\b", re.IGNORECASE)


@dataclass(frozen=True)
class AuditQuery:
    query_id: str
    search_term: str
    normalized_term: str
    normalized_token_count: int
    sum_unique_users: int
    source_rows: tuple[str, ...]
    privacy_flags: tuple[str, ...]


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def query_slug(value: str, *, limit: int = 48) -> str:
    text = "-".join(part for part in value.lower().split() if part)
    text = "".join(char if char.isalnum() or char == "-" else "-" for char in text)
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-")[:limit].strip("-") or "query"


def collapse_queries(rows: list[QueryRow]) -> list[AuditQuery]:
    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        normalized = row.normalized_term.strip()
        if not normalized:
            continue
        current = grouped.setdefault(
            normalized,
            {
                "search_term": row.search_term,
                "sum_unique_users": 0,
                "source_rows": [],
                "privacy_flags": set(),
            },
        )
        current["sum_unique_users"] = int(current["sum_unique_users"]) + row.unique_users
        source_rows = current["source_rows"]
        assert isinstance(source_rows, list)
        source_rows.append(f"{row.source_file}:{row.source_row}")
        flags = current["privacy_flags"]
        assert isinstance(flags, set)
        flags.update(row.privacy_flags)

    collapsed = []
    for index, normalized in enumerate(sorted(grouped), start=1):
        current = grouped[normalized]
        flags = current["privacy_flags"]
        source_rows = current["source_rows"]
        assert isinstance(flags, set)
        assert isinstance(source_rows, list)
        collapsed.append(
            AuditQuery(
                query_id=f"q{index:06d}_{query_slug(normalized)}",
                search_term=str(current["search_term"]),
                normalized_term=normalized,
                normalized_token_count=len(normalized.split()),
                sum_unique_users=int(current["sum_unique_users"]),
                source_rows=tuple(source_rows),
                privacy_flags=tuple(sorted(str(flag) for flag in flags)),
            )
        )
    return collapsed


def eligible_queries(
    rows: list[AuditQuery],
    *,
    min_tokens: int,
    max_tokens: int,
    include_privacy_flagged: bool,
) -> list[AuditQuery]:
    selected = []
    for row in rows:
        if row.normalized_token_count < min_tokens:
            continue
        if max_tokens > 0 and row.normalized_token_count > max_tokens:
            continue
        if row.privacy_flags and not include_privacy_flagged:
            continue
        selected.append(row)
    return selected


def weighted_sample_without_replacement(
    rows: list[AuditQuery],
    *,
    size: int,
    seed: int,
) -> list[AuditQuery]:
    if size >= len(rows):
        return list(rows)
    rng = random.Random(seed)
    # Efraimidis-Spirakis exponential keys. Larger per-term user counts make a
    # term more likely to enter the sample without expanding rows in memory.
    keyed = []
    for row in rows:
        weight = max(1, row.sum_unique_users)
        key = -math.log(max(rng.random(), 1e-15)) / weight
        keyed.append((key, row.normalized_term, row))
    keyed.sort(key=lambda item: (item[0], item[1]))
    return [row for _, _, row in keyed[:size]]


def balanced_sample(
    rows: list[AuditQuery],
    *,
    size: int,
    seed: int,
) -> list[AuditQuery]:
    if size >= len(rows):
        return list(rows)
    by_length: dict[int, list[AuditQuery]] = defaultdict(list)
    for row in rows:
        by_length[row.normalized_token_count].append(row)
    lengths = sorted(by_length)
    rng = random.Random(seed)
    chosen: list[AuditQuery] = []
    remaining = size
    active = list(lengths)
    while remaining and active:
        next_active = []
        quota = max(1, remaining // len(active))
        for token_count in active:
            pool = [row for row in by_length[token_count] if row not in chosen]
            take = min(quota, len(pool), remaining)
            if take:
                chosen.extend(rng.sample(pool, take))
                remaining -= take
            if len(pool) > take:
                next_active.append(token_count)
            if not remaining:
                break
        active = next_active
    return chosen


def select_sample(
    rows: list[AuditQuery],
    *,
    size: int,
    method: str,
    seed: int,
) -> list[AuditQuery]:
    if size < 1:
        raise ValueError("sample size must be at least 1")
    if not rows:
        return []
    if size >= len(rows):
        return list(rows)
    if method == "uniform":
        return random.Random(seed).sample(rows, size)
    if method == "demand":
        return weighted_sample_without_replacement(rows, size=size, seed=seed)
    if method == "balanced":
        return balanced_sample(rows, size=size, seed=seed)
    raise ValueError(f"unsupported sampling method: {method}")


def resolve_api_key() -> str:
    api_key = (os.environ.get("UMLS_API_KEY") or os.environ.get("APIKEY") or "").strip()
    if api_key:
        return api_key
    try:
        return getpass.getpass("Enter UMLS API key (input hidden): ").strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def compact_hits(hits: list[dict], *, limit: int = 10) -> str:
    return " | ".join(
        f"{index}:{hit.get('cui', '')} {hit.get('name', '')}"
        for index, hit in enumerate(hits[:limit], start=1)
    )


def call_umls(
    row: AuditQuery,
    *,
    api_key: str,
    base_url: str,
    search_type: str,
    sabs: str,
    page_size: int,
    timeout: float,
    retries: int,
    retry_backoff: float,
) -> tuple[dict | None, str]:
    spec = QuerySpec(
        query_id=row.query_id,
        query=row.search_term,
        search_type=search_type,
        sabs=sabs,
    )
    error = ""
    for attempt in range(retries + 1):
        try:
            return (
                umls_search(
                    base_url=base_url,
                    api_key=api_key,
                    spec=spec,
                    page_size=page_size,
                    search_type=search_type,
                    sabs=sabs,
                    timeout=timeout,
                ),
                "",
            )
        except Exception as exc:  # noqa: BLE001 - retain an audit row for failed calls
            error = str(exc)[:500]
            if attempt < retries:
                time.sleep(retry_backoff * (2**attempt))
    return None, error


def result_row(row: AuditQuery, payload: dict | None, error: str, *, search_type: str) -> dict[str, object]:
    hits = umls_hits(payload or {})
    top = hits[0] if hits else {}
    return {
        "id": row.query_id,
        "search_term": row.search_term,
        "normalized_term": row.normalized_term,
        "normalized_token_count": row.normalized_token_count,
        "sum_unique_users": row.sum_unique_users,
        "source_rows": "|".join(row.source_rows),
        "privacy_flags": "|".join(row.privacy_flags),
        "search_type": search_type,
        "umls_hit_count": len(hits),
        "umls_no_hit": "" if error else ("1" if not hits else "0"),
        "umls_top_cui": top.get("cui", ""),
        "umls_top_name": top.get("name", ""),
        "umls_top_source": top.get("root_source", ""),
        "umls_hit_cuis": "|".join(str(hit.get("cui") or "") for hit in hits if hit.get("cui")),
        "umls_hits": compact_hits(hits),
        "umls_error": error,
    }


def safe_rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def distribution(rows: list[AuditQuery]) -> dict[str, dict[str, int]]:
    counts: dict[int, dict[str, int]] = defaultdict(lambda: {"queries": 0, "sum_unique_users": 0})
    for row in rows:
        current = counts[row.normalized_token_count]
        current["queries"] += 1
        current["sum_unique_users"] += row.sum_unique_users
    return {str(key): counts[key] for key in sorted(counts)}


def summarize(
    result_rows: list[dict[str, object]],
    *,
    all_queries: list[AuditQuery],
    eligible: list[AuditQuery],
    sample: list[AuditQuery],
    args: argparse.Namespace,
    run_id: str,
) -> dict[str, object]:
    scored = [row for row in result_rows if not row["umls_error"]]
    no_hits = [row for row in scored if row["umls_no_hit"] == "1"]
    scored_users = sum(int(row["sum_unique_users"]) for row in scored)
    no_hit_users = sum(int(row["sum_unique_users"]) for row in no_hits)
    by_length: dict[int, dict[str, int | float]] = defaultdict(
        lambda: {"scored_queries": 0, "no_hit_queries": 0, "sum_unique_users": 0, "no_hit_sum_unique_users": 0}
    )
    for row in scored:
        token_count = int(row["normalized_token_count"])
        current = by_length[token_count]
        current["scored_queries"] = int(current["scored_queries"]) + 1
        current["sum_unique_users"] = int(current["sum_unique_users"]) + int(row["sum_unique_users"])
        if row["umls_no_hit"] == "1":
            current["no_hit_queries"] = int(current["no_hit_queries"]) + 1
            current["no_hit_sum_unique_users"] = int(current["no_hit_sum_unique_users"]) + int(
                row["sum_unique_users"]
            )
    for current in by_length.values():
        current["no_hit_query_rate"] = safe_rate(
            int(current["no_hit_queries"]), int(current["scored_queries"])
        )
        current["no_hit_demand_rate"] = safe_rate(
            int(current["no_hit_sum_unique_users"]), int(current["sum_unique_users"])
        )
    return {
        "run_id": run_id,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "private_raw_query_audit": True,
        "umls_base_url": args.umls_base_url,
        "search_type": args.search_type,
        "sabs": args.sabs,
        "sampling_method": args.sampling,
        "random_seed": args.seed,
        "requested_sample_size": args.sample_size,
        "min_tokens": args.min_tokens,
        "max_tokens": args.max_tokens,
        "privacy_flagged_queries_excluded": not args.include_privacy_flagged,
        "all_normalized_queries": len(all_queries),
        "eligible_queries": len(eligible),
        "sampled_queries": len(sample),
        "scored_queries": len(scored),
        "api_error_queries": len(result_rows) - len(scored),
        "umls_no_hit_queries": len(no_hits),
        "umls_no_hit_query_rate": safe_rate(len(no_hits), len(scored)),
        "scored_sum_unique_users": scored_users,
        "umls_no_hit_sum_unique_users": no_hit_users,
        "umls_no_hit_demand_rate": safe_rate(no_hit_users, scored_users),
        "population_by_normalized_token_count": distribution(all_queries),
        "eligible_by_normalized_token_count": distribution(eligible),
        "sample_by_normalized_token_count": distribution(sample),
        "results_by_normalized_token_count": {str(key): by_length[key] for key in sorted(by_length)},
        "interpretation_warning": (
            "The source exports are descending-frequency, token-length buckets capped at 10,000 rows for "
            "one through eight words. This audit estimates behavior only for the selected exported population; "
            "it is not an unweighted random sample of all production searches. unique_users is a per-term count "
            "and is not globally deduplicated. UMLS results are comparison evidence, not automatic clinical ground truth."
        ),
    }


def write_tsv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_review_queue(path: Path, rows: list[dict[str, object]]) -> None:
    # Review every successfully scored query. A query that returned results may
    # still have omitted the expected CUI, or may have returned only some of the
    # expected CUIs. Restricting review to API no-hits would therefore bias the
    # expected-result false-negative rate.
    reviewable = [row for row in rows if not row["umls_error"] and not row["privacy_flags"]]
    reviewable.sort(
        key=lambda row: (
            0 if row["umls_no_hit"] == "1" else 1,
            -int(row["sum_unique_users"]),
            int(row["normalized_token_count"]),
            str(row["normalized_term"]),
        )
    )
    review = [
        {
            "review_status": "",
            "expected_cuis": "",
            "failure_class": "",
            "review_note": "",
            **row,
        }
        for row in reviewable
    ]
    write_tsv(path, review, REVIEW_FIELDS)


def split_cuis(value: object) -> tuple[str, ...]:
    return tuple(dict.fromkeys(match.upper() for match in CUI_RE.findall(str(value or ""))))


def read_review_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        delimiter = "\t" if "\t" in sample else ","
        return [dict(row) for row in csv.DictReader(handle, delimiter=delimiter)]


def percent(value: object) -> str:
    try:
        return f"{100 * float(value):.1f}%"
    except (TypeError, ValueError):
        return "0.0%"


def html_table(headers: list[str], rows: list[list[object]], *, empty: str) -> str:
    if not rows:
        return f'<p class="empty">{html.escape(empty)}</p>'
    head = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def write_html_report(run_dir: Path, output_path: Path | None = None) -> Path:
    summary_path = run_dir / "summary.json"
    rows_path = run_dir / "rows.tsv"
    review_path = run_dir / "expected_result_review_queue.tsv"
    if not summary_path.exists() or not rows_path.exists():
        raise FileNotFoundError(f"Expected summary.json and rows.tsv under {run_dir}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rows = read_review_rows(rows_path)
    review_rows = read_review_rows(review_path) if review_path.exists() else []
    reviewed_summary_path = run_dir / "expected_result_review_queue.scored.summary.json"
    reviewed_summary = (
        json.loads(reviewed_summary_path.read_text(encoding="utf-8"))
        if reviewed_summary_path.exists()
        else None
    )
    misses_path = run_dir / "expected_result_review_queue.scored.misses.tsv"
    missed_rows = read_review_rows(misses_path) if misses_path.exists() else []
    output_path = output_path or run_dir / "management_report.html"

    statuses = Counter(str(row.get("review_status") or "").strip().lower() or "blank" for row in review_rows)
    included = sum(statuses[status] for status in INCLUDED_REVIEW_STATUSES)
    excluded = sum(statuses[status] for status in ("exclude", "excluded", "no"))
    pending = len(review_rows) - included - excluded
    api_errors = [row for row in rows if row.get("umls_error")]
    error_counts = Counter(str(row.get("umls_error") or "unknown error") for row in api_errors)
    no_hits = [row for row in rows if row.get("umls_no_hit") == "1" and not row.get("umls_error")]
    no_hits.sort(
        key=lambda row: (
            -int(str(row.get("sum_unique_users") or "0") or 0),
            int(str(row.get("normalized_token_count") or "0") or 0),
            str(row.get("normalized_term") or ""),
        )
    )
    has_reviewed_result = bool(
        reviewed_summary and int(reviewed_summary.get("included_reviewed_queries", 0)) > 0
    )
    is_final = bool(
        has_reviewed_result
        and pending == 0
        and int(reviewed_summary.get("included_rows_missing_expected_cuis", 0)) == 0
    )
    if is_final:
        status_label = "Reviewed result"
    elif has_reviewed_result:
        status_label = f"Partial reviewed result — {pending} adjudications pending"
    else:
        status_label = "Preliminary — adjudication pending"
    status_class = "final" if is_final else "preliminary"

    result_by_length = summary.get("results_by_normalized_token_count") or {}
    length_rows = []
    length_bars = []
    for token_count in sorted(result_by_length, key=lambda value: int(value)):
        item = result_by_length[token_count]
        rate = float(item.get("no_hit_query_rate") or 0)
        length_rows.append(
            [
                token_count,
                item.get("scored_queries", 0),
                item.get("no_hit_queries", 0),
                percent(rate),
                percent(item.get("no_hit_demand_rate", 0)),
            ]
        )
        length_bars.append(
            '<div class="bar-row">'
            f'<span class="bar-label">{html.escape(str(token_count))} word</span>'
            '<span class="bar-track">'
            f'<span class="bar-fill" style="width:{min(100, 100 * rate):.2f}%"></span>'
            "</span>"
            f'<span class="bar-value">{percent(rate)}</span>'
            "</div>"
        )

    if has_reviewed_result:
        lower, upper = reviewed_summary.get("query_total_miss_rate_approx_95_ci", [0, 0])
        primary_cards = f"""
          <article class="metric hero"><span>Missed expected results</span><strong>{reviewed_summary['missed_expected_result_percentage']:.2f}%</strong><small>{reviewed_summary['missed_expected_query_cui_results']} of {reviewed_summary['expected_query_cui_results']} expected query–CUI results</small></article>
          <article class="metric"><span>Queries missing any expected result</span><strong>{reviewed_summary['queries_with_any_expected_result_missed_percentage']:.1f}%</strong><small>{reviewed_summary['queries_with_any_expected_result_missed']} of {reviewed_summary['included_reviewed_queries']} reviewed queries, including partial and complete misses</small></article>
          <article class="metric"><span>Partial-result failures</span><strong>{reviewed_summary['query_partial_miss_percentage']:.1f}%</strong><small>{reviewed_summary['queries_with_partial_expected_results']} queries returned at least one expected CUI but omitted another</small></article>
          <article class="metric"><span>Complete query misses</span><strong>{reviewed_summary['query_total_miss_percentage']:.1f}%</strong><small>{reviewed_summary['queries_with_all_expected_results_missed']} of {reviewed_summary['included_reviewed_queries']} reviewed queries; approximate 95% interval {percent(lower)}–{percent(upper)}</small></article>
          <article class="metric"><span>Demand-weighted complete misses</span><strong>{reviewed_summary['demand_weighted_query_total_miss_percentage']:.1f}%</strong><small>Weighted by per-term unique_users within the reviewed sample</small></article>
        """
        example_rows = [
            [
                row.get("search_term", ""),
                row.get("expected_cuis", ""),
                row.get("missed_expected_cuis", ""),
                "Complete miss"
                if int(str(row.get("returned_expected_result_count") or "0") or 0) == 0
                else "Partial miss",
                row.get("expected_result_recall", ""),
                row.get("umls_top_name", "") or "No result",
                row.get("failure_class", "") or "unclassified",
                row.get("review_note", ""),
            ]
            for row in missed_rows
        ]
        examples_title = "Every reviewed missed example"
        examples_note = (
            "These are adjudicated query–CUI omissions. The downloadable TSV retains all returned CUIs and audit fields."
        )
        examples_table = html_table(
            [
                "Query",
                "Expected CUIs",
                "Missed CUIs",
                "Outcome",
                "Expected-result recall",
                "Top UMLS result",
                "Failure class",
                "Review note",
            ],
            example_rows,
            empty="No reviewed missed examples.",
        )
    else:
        primary_cards = f"""
          <article class="metric hero"><span>Observed API no-hit rate</span><strong>{percent(summary.get('umls_no_hit_query_rate', 0))}</strong><small>{summary.get('umls_no_hit_queries', 0)} of {summary.get('scored_queries', 0)} successful requests; this is not yet the missed-result rate</small></article>
          <article class="metric"><span>Review progress</span><strong>{included + excluded}/{len(review_rows)}</strong><small>{pending} queries still need expected-CUI adjudication</small></article>
          <article class="metric"><span>API retrieval failures</span><strong>{summary.get('api_error_queries', 0)}</strong><small>Excluded from the no-hit denominator and requiring a retry</small></article>
        """
        example_rows = [
            [
                row.get("search_term", ""),
                row.get("normalized_token_count", ""),
                row.get("sum_unique_users", ""),
                "No result",
            ]
            for row in no_hits
        ]
        examples_title = "UMLS no-hit candidates — not yet adjudicated"
        examples_note = (
            "A no-hit query is only a candidate miss. It becomes a true missed result only after a reviewer records at least one expected CUI."
        )
        examples_table = html_table(
            ["Query", "Words", "Per-term unique users", "API outcome"],
            example_rows,
            empty="No successful API requests returned zero results.",
        )

    error_rows = [[count, message] for message, count in error_counts.most_common()]
    report_generated = datetime.now(timezone.utc).isoformat()
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>UMLS Search Missed-Result Audit</title>
  <style>
    :root {{ --ink:#16202a; --muted:#607080; --paper:#f5f7f6; --card:#fff; --line:#dce4e2; --teal:#0b6f69; --navy:#173b57; --amber:#b86b09; --red:#a23b3b; }}
    * {{ box-sizing:border-box; }} body {{ margin:0; background:var(--paper); color:var(--ink); font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    header {{ color:white; background:linear-gradient(120deg,var(--navy),var(--teal)); padding:48px max(24px,calc((100% - 1120px)/2)); }}
    header h1 {{ margin:8px 0; font-size:clamp(30px,5vw,48px); line-height:1.05; }} header p {{ max-width:760px; margin:10px 0 0; color:#dcebea; }}
    .eyebrow {{ text-transform:uppercase; letter-spacing:.12em; font-size:12px; font-weight:800; }} .status {{ display:inline-block; padding:5px 10px; border-radius:999px; font-weight:750; background:#fff3d8; color:#6c4104; }} .status.final {{ background:#d8f1e9; color:#174f40; }}
    main {{ max-width:1120px; margin:auto; padding:28px 24px 64px; }} section {{ margin:28px 0; }} h2 {{ margin:0 0 8px; font-size:24px; }} .lede {{ color:var(--muted); max-width:900px; }}
    .metrics {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; }} .metric {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:20px; box-shadow:0 4px 18px #173b570d; }} .metric.hero {{ border-top:5px solid var(--teal); }} .metric span,.metric small {{ display:block; color:var(--muted); }} .metric strong {{ display:block; font-size:34px; margin:8px 0; color:var(--navy); }}
    .notice {{ background:#fff7e8; border-left:5px solid var(--amber); padding:16px 18px; border-radius:8px; }} .notice.error {{ background:#fff1f1; border-color:var(--red); }}
    .split {{ display:grid; grid-template-columns:1fr 1fr; gap:24px; align-items:start; }} .panel {{ background:white; border:1px solid var(--line); border-radius:14px; padding:20px; }}
    .bar-row {{ display:grid; grid-template-columns:72px 1fr 54px; gap:10px; align-items:center; margin:14px 0; }} .bar-label,.bar-value {{ font-variant-numeric:tabular-nums; }} .bar-track {{ height:13px; background:#e9efee; border-radius:20px; overflow:hidden; }} .bar-fill {{ display:block; height:100%; background:linear-gradient(90deg,var(--teal),#41a39a); border-radius:20px; }}
    .table-wrap {{ overflow:auto; border:1px solid var(--line); border-radius:12px; background:white; max-height:620px; }} table {{ border-collapse:collapse; width:100%; font-size:14px; }} th,td {{ text-align:left; padding:10px 12px; border-bottom:1px solid var(--line); vertical-align:top; }} th {{ position:sticky; top:0; background:#edf3f2; color:var(--navy); }} tbody tr:nth-child(even) {{ background:#fafcfc; }}
    code {{ background:#e9efee; padding:2px 5px; border-radius:4px; }} a {{ color:var(--teal); }} .downloads {{ display:flex; flex-wrap:wrap; gap:10px; }} .downloads a {{ background:white; border:1px solid var(--line); padding:9px 12px; border-radius:8px; text-decoration:none; font-weight:700; }} .empty {{ color:var(--muted); font-style:italic; }} footer {{ color:var(--muted); margin-top:36px; font-size:13px; }}
    @media (max-width:800px) {{ .metrics,.split {{ grid-template-columns:1fr; }} }} @media print {{ header {{ padding:24px; }} main {{ padding:15px; }} .table-wrap {{ max-height:none; overflow:visible; }} th {{ position:static; }} }}
  </style>
</head>
<body>
<header>
  <div class="eyebrow">Search quality · Private log-derived analysis</div>
  <h1>UMLS Search Missed-Result Audit</h1>
  <p>Uniform sample of short, real search-log queries tested against the official UMLS <code>words</code> search endpoint.</p>
</header>
<main>
  <p class="status {status_class}">{status_label}</p>
  <section class="metrics">{primary_cards}</section>
  <section class="notice"><strong>Interpretation boundary.</strong> The requested missed-result percentage requires human-approved expected CUIs. API no-hits alone are not ground truth, and API hits can still omit the right concept. The exported query files are frequency-sorted and capped, so this sample estimates distinct terms in the exported one-to-four-word population—not all production searches.</section>
  <section>
    <h2>Audit coverage</h2>
    <div class="metrics">
      <article class="metric"><span>Sample</span><strong>{summary.get('sampled_queries', 0)}</strong><small>Uniform sample from {summary.get('eligible_queries', 0):,} eligible exported terms; seed {summary.get('random_seed', '')}</small></article>
      <article class="metric"><span>Successful API requests</span><strong>{summary.get('scored_queries', 0)}</strong><small>{percent(int(summary.get('scored_queries', 0)) / max(1, int(summary.get('sampled_queries', 0))))} of sampled queries</small></article>
      <article class="metric"><span>Summed user signal</span><strong>{summary.get('scored_sum_unique_users', 0):,}</strong><small>Per-term unique-user counts; not globally deduplicated users</small></article>
    </div>
  </section>
  <section class="split">
    <div class="panel"><h2>No-hit rate by query length</h2>{''.join(length_bars)}</div>
    <div><h2>Detailed length breakdown</h2>{html_table(['Words','Successful','No hit','No-hit rate','User-weighted no-hit rate'], length_rows, empty='No length data.')}</div>
  </section>
  <section>
    <h2>{html.escape(examples_title)}</h2>
    <p class="lede">{html.escape(examples_note)}</p>
    {examples_table}
  </section>
  <section class="notice error">
    <h2>API retrieval errors</h2>
    <p>{len(api_errors)} requests failed and are excluded from the no-hit denominator. Retry them before presenting the audit as complete.</p>
    {html_table(['Count','Error'], error_rows, empty='No API retrieval errors.')}
  </section>
  <section>
    <h2>Metric definition</h2>
    <p><strong>Missed expected-result percentage</strong> = expected query–CUI pairs absent from the UMLS response ÷ all human-approved expected query–CUI pairs × 100.</p>
    <p class="lede">This counts both complete misses and partial-result failures. For example, if three CUIs are expected and one is returned, that query contributes two missed results out of three expected results. The UMLS endpoint returns a single page of up to 200 CUIs. Reviewers should record every medically reasonable expected CUI for the query, including queries for which UMLS returned one or more results.</p>
  </section>
  <section>
    <h2>Audit files</h2>
    <div class="downloads"><a href="rows.tsv">All API rows</a><a href="expected_result_review_queue.tsv">Expected-result review queue</a>{'<a href="expected_result_review_queue.scored.misses.tsv">Reviewed misses</a>' if misses_path.exists() else ''}<a href="summary.json">Run summary</a></div>
  </section>
  <footer>Run <code>{html.escape(str(summary.get('run_id', run_dir.name)))}</code> · Generated {html.escape(report_generated)} · Keep private because it contains raw log-derived queries.</footer>
</main>
</body>
</html>
"""
    output_path.write_text(document, encoding="utf-8")
    return output_path


def wilson_interval(successes: int, total: int, *, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
    proportion = successes / total
    denominator = 1 + (z * z / total)
    centre = (proportion + (z * z / (2 * total))) / denominator
    spread = (
        z
        * math.sqrt((proportion * (1 - proportion) / total) + (z * z / (4 * total * total)))
        / denominator
    )
    return max(0.0, centre - spread), min(1.0, centre + spread)


def score_reviewed_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, object]], dict[str, object]]:
    scored_rows: list[dict[str, object]] = []
    status_counts = Counter(str(row.get("review_status") or "").strip().lower() or "blank" for row in rows)
    approved_without_expected = 0
    expected_results = 0
    returned_expected_results = 0
    total_miss_queries = 0
    partial_miss_queries = 0
    complete_coverage_queries = 0
    queries_with_any_miss = 0
    reviewed_users = 0
    total_miss_users = 0
    by_failure_class: dict[str, dict[str, int]] = defaultdict(
        lambda: {"queries": 0, "expected_results": 0, "missed_expected_results": 0}
    )

    for row in rows:
        status = str(row.get("review_status") or "").strip().lower()
        if status not in INCLUDED_REVIEW_STATUSES:
            continue
        expected = split_cuis(row.get("expected_cuis"))
        if not expected:
            approved_without_expected += 1
            continue
        returned = set(split_cuis(row.get("umls_hit_cuis")))
        if not returned:
            returned = set(split_cuis(row.get("umls_hits")))
        expected_set = set(expected)
        found = expected_set & returned
        missed = expected_set - returned
        users = int(str(row.get("sum_unique_users") or "0") or 0)
        total_miss = not found
        expected_results += len(expected_set)
        returned_expected_results += len(found)
        queries_with_any_miss += int(bool(missed))
        total_miss_queries += int(total_miss)
        partial_miss_queries += int(bool(found) and bool(missed))
        complete_coverage_queries += int(not missed)
        reviewed_users += users
        total_miss_users += users if total_miss else 0
        failure_class = str(row.get("failure_class") or "").strip() or "unclassified"
        class_summary = by_failure_class[failure_class]
        class_summary["queries"] += 1
        class_summary["expected_results"] += len(expected_set)
        class_summary["missed_expected_results"] += len(missed)
        scored_rows.append(
            {
                **row,
                "expected_result_count": len(expected_set),
                "returned_expected_result_count": len(found),
                "missed_expected_result_count": len(missed),
                "missed_expected_cuis": "|".join(sorted(missed)),
                "expected_result_recall": round(len(found) / len(expected_set), 6),
                "query_total_miss": "1" if total_miss else "0",
            }
        )

    reviewed_queries = len(scored_rows)
    missed_results = expected_results - returned_expected_results
    lower, upper = wilson_interval(total_miss_queries, reviewed_queries)
    summary = {
        "review_rows": len(rows),
        "review_status_counts": dict(sorted(status_counts.items())),
        "included_reviewed_queries": reviewed_queries,
        "included_rows_missing_expected_cuis": approved_without_expected,
        "expected_query_cui_results": expected_results,
        "returned_expected_query_cui_results": returned_expected_results,
        "missed_expected_query_cui_results": missed_results,
        "missed_expected_result_rate": safe_rate(missed_results, expected_results),
        "missed_expected_result_percentage": round(100 * missed_results / expected_results, 2)
        if expected_results
        else 0.0,
        "queries_with_any_expected_result_missed": queries_with_any_miss,
        "queries_with_any_expected_result_missed_rate": safe_rate(queries_with_any_miss, reviewed_queries),
        "queries_with_any_expected_result_missed_percentage": round(
            100 * queries_with_any_miss / reviewed_queries, 2
        )
        if reviewed_queries
        else 0.0,
        "queries_with_partial_expected_results": partial_miss_queries,
        "query_partial_miss_rate": safe_rate(partial_miss_queries, reviewed_queries),
        "query_partial_miss_percentage": round(100 * partial_miss_queries / reviewed_queries, 2)
        if reviewed_queries
        else 0.0,
        "queries_with_complete_expected_result_coverage": complete_coverage_queries,
        "query_complete_coverage_rate": safe_rate(complete_coverage_queries, reviewed_queries),
        "query_complete_coverage_percentage": round(
            100 * complete_coverage_queries / reviewed_queries, 2
        )
        if reviewed_queries
        else 0.0,
        "queries_with_all_expected_results_missed": total_miss_queries,
        "query_total_miss_rate": safe_rate(total_miss_queries, reviewed_queries),
        "query_total_miss_percentage": round(100 * total_miss_queries / reviewed_queries, 2)
        if reviewed_queries
        else 0.0,
        "query_total_miss_rate_approx_95_ci": [round(lower, 6), round(upper, 6)],
        "reviewed_sum_unique_users": reviewed_users,
        "total_miss_sum_unique_users": total_miss_users,
        "demand_weighted_query_total_miss_rate": safe_rate(total_miss_users, reviewed_users),
        "demand_weighted_query_total_miss_percentage": round(100 * total_miss_users / reviewed_users, 2)
        if reviewed_users
        else 0.0,
        "by_failure_class": {key: by_failure_class[key] for key in sorted(by_failure_class)},
        "metric_definition": (
            "missed_expected_result_percentage = expected query-CUI pairs absent from all returned UMLS "
            "results / all human-approved expected query-CUI pairs"
        ),
    }
    return scored_rows, summary


def summarize_review_file(path: Path, *, summary_out: Path | None, rows_out: Path | None) -> int:
    rows = read_review_rows(path)
    scored_rows, summary = score_reviewed_rows(rows)
    if summary_out is None:
        summary_out = path.with_name(f"{path.stem}.scored.summary.json")
    if rows_out is None:
        rows_out = path.with_name(f"{path.stem}.scored.tsv")
    misses_out = path.with_name(f"{path.stem}.scored.misses.tsv")
    write_tsv(rows_out, scored_rows, REVIEW_SCORE_FIELDS)
    missed_rows = [row for row in scored_rows if int(row["missed_expected_result_count"]) > 0]
    write_tsv(misses_out, missed_rows, REVIEW_SCORE_FIELDS)
    summary["review_file"] = str(path)
    summary["scored_rows_tsv"] = str(rows_out)
    summary["missed_examples_tsv"] = str(misses_out)
    summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path = None
    if (path.parent / "summary.json").exists() and (path.parent / "rows.tsv").exists():
        html_path = write_html_report(path.parent)
    print(
        "Missed expected result percentage: "
        f"{summary['missed_expected_result_percentage']}% "
        f"({summary['missed_expected_query_cui_results']}/{summary['expected_query_cui_results']})"
    )
    print(
        "Queries with every expected result missed: "
        f"{summary['query_total_miss_percentage']}% "
        f"({summary['queries_with_all_expected_results_missed']}/{summary['included_reviewed_queries']})"
    )
    print(f"wrote {len(missed_rows)} missed-query examples to {misses_out}")
    print(f"wrote reviewed score summary to {summary_out}")
    if html_path:
        print(f"updated HTML report at {html_path}")
    return 0 if scored_rows else 2


def write_report(path: Path, summary: dict[str, object], rows_path: Path, review_path: Path) -> None:
    report = f"""# Private UMLS API Real-Query Audit

This output contains raw search-log terms and must remain private.

## Result

- Sampled queries: {summary['sampled_queries']}
- Successfully scored: {summary['scored_queries']}
- API errors: {summary['api_error_queries']}
- UMLS no-hit queries: {summary['umls_no_hit_queries']}
- UMLS no-hit query rate: {summary['umls_no_hit_query_rate']}
- No-hit summed per-term user rate: {summary['umls_no_hit_demand_rate']}

## Sampling

- Method: `{summary['sampling_method']}`
- Seed: `{summary['random_seed']}`
- Token range: {summary['min_tokens']} to {summary['max_tokens'] or 'unbounded'}
- Eligible queries: {summary['eligible_queries']}

{summary['interpretation_warning']}

## Private outputs

- All API rows: `{rows_path}`
- Expected-result manual-review queue (all successfully scored queries): `{review_path}`

The API key was read from an environment variable or hidden terminal prompt and was not saved.
"""
    path.write_text(report, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Sample private real-query exports and test them against the official UMLS UTS search API. "
            "If UMLS_API_KEY/APIKEY is unset, the script prompts for the key without echoing it."
        )
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", help="Output directory name; defaults to a timestamped name.")
    parser.add_argument("--sample-size", type=int, default=250)
    parser.add_argument(
        "--sampling",
        choices=("demand", "uniform", "balanced"),
        default="uniform",
        help=(
            "demand weights selection by per-term unique_users; uniform samples distinct exported terms; "
            "balanced allocates similar counts to each query length. Default: uniform."
        ),
    )
    parser.add_argument("--seed", type=int, default=20260930)
    parser.add_argument("--min-tokens", type=int, default=1)
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=4,
        help="Default focuses on short concept-lookup queries. Use 0 for no maximum.",
    )
    parser.add_argument(
        "--include-privacy-flagged",
        action="store_true",
        help="Include identifier-shaped rows. Off by default; use only in an approved private environment.",
    )
    parser.add_argument("--search-type", choices=VALID_SEARCH_TYPES, default="words")
    parser.add_argument("--sabs", default="")
    parser.add_argument("--umls-base-url", default=DEFAULT_UMLS_BASE_URL)
    parser.add_argument("--page-size", type=int, default=200)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--sleep", type=float, default=0.15)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--retry-backoff", type=float, default=1.0)
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--save-payloads", action="store_true")
    parser.add_argument(
        "--summarize-reviewed",
        type=Path,
        help=(
            "Do not call UMLS. Score a completed expected_result_review_queue.tsv after review_status and "
            "expected_cuis have been filled in."
        ),
    )
    parser.add_argument("--review-summary-out", type=Path)
    parser.add_argument("--review-rows-out", type=Path)
    parser.add_argument(
        "--generate-html",
        type=Path,
        metavar="RUN_DIR",
        help="Generate or refresh management_report.html for an existing audit run without calling UMLS.",
    )
    parser.add_argument("--html-out", type=Path)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Select the reproducible sample and write its private manifest without calling UMLS.",
    )
    parser.add_argument("--fail-on-error", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.generate_html:
        html_path = write_html_report(args.generate_html, args.html_out)
        print(f"wrote HTML report to {html_path}")
        return 0
    if args.summarize_reviewed:
        return summarize_review_file(
            args.summarize_reviewed,
            summary_out=args.review_summary_out,
            rows_out=args.review_rows_out,
        )
    if args.min_tokens < 1:
        print("--min-tokens must be at least 1", file=sys.stderr)
        return 2
    if args.max_tokens and args.max_tokens < args.min_tokens:
        print("--max-tokens must be 0 or at least --min-tokens", file=sys.stderr)
        return 2
    if args.sample_size < 1:
        print("--sample-size must be at least 1", file=sys.stderr)
        return 2

    all_queries = collapse_queries(list(iter_query_rows(args.input_dir)))
    eligible = eligible_queries(
        all_queries,
        min_tokens=args.min_tokens,
        max_tokens=args.max_tokens,
        include_privacy_flagged=args.include_privacy_flagged,
    )
    sample = select_sample(eligible, size=args.sample_size, method=args.sampling, seed=args.seed)
    run_id = args.run_id or f"{utc_stamp()}_{args.sampling}_n{len(sample)}_seed{args.seed}"
    run_dir = args.output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        manifest_rows = [
            result_row(row, None, "dry_run_not_scored", search_type=args.search_type) for row in sample
        ]
        rows_path = run_dir / "sample_manifest.tsv"
        write_tsv(rows_path, manifest_rows, ROW_FIELDS)
        print(f"wrote private dry-run sample of {len(sample)} queries to {rows_path}")
        print("No API key was requested and no UMLS requests were made.")
        return 0

    api_key = resolve_api_key()
    if not api_key:
        print("A UMLS API key is required.", file=sys.stderr)
        return 2

    result_rows = []
    payload_dir = run_dir / "payloads"
    total = len(sample)
    for index, row in enumerate(sample, start=1):
        if args.progress_every > 0 and (index == 1 or index % args.progress_every == 0 or index == total):
            print(f"calling UMLS API {index}/{total}", file=sys.stderr)
        payload, error = call_umls(
            row,
            api_key=api_key,
            base_url=args.umls_base_url,
            search_type=args.search_type,
            sabs=args.sabs,
            page_size=args.page_size,
            timeout=args.timeout,
            retries=max(0, args.retries),
            retry_backoff=max(0.0, args.retry_backoff),
        )
        if args.save_payloads and payload is not None:
            payload_dir.mkdir(parents=True, exist_ok=True)
            (payload_dir / f"{row.query_id}.json").write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        result_rows.append(result_row(row, payload, error, search_type=args.search_type))
        if index < total and args.sleep > 0:
            time.sleep(args.sleep)

    rows_path = run_dir / "rows.tsv"
    review_path = run_dir / "expected_result_review_queue.tsv"
    summary_path = run_dir / "summary.json"
    report_path = run_dir / "README.md"
    write_tsv(rows_path, result_rows, ROW_FIELDS)
    write_review_queue(review_path, result_rows)
    summary = summarize(
        result_rows,
        all_queries=all_queries,
        eligible=eligible,
        sample=sample,
        args=args,
        run_id=run_id,
    )
    summary["rows_tsv"] = str(rows_path)
    summary["expected_result_review_queue_tsv"] = str(review_path)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(report_path, summary, rows_path, review_path)
    html_path = write_html_report(run_dir)

    print(f"wrote {len(result_rows)} private API audit rows to {rows_path}")
    print(f"UMLS no-hit rate: {summary['umls_no_hit_query_rate']}")
    print(f"UMLS no-hit summed per-term user rate: {summary['umls_no_hit_demand_rate']}")
    print(f"wrote summary to {summary_path}")
    print(f"wrote HTML report to {html_path}")
    had_error = bool(summary["api_error_queries"])
    return 1 if had_error and args.fail_on_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
