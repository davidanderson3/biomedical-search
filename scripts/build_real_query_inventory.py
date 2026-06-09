#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qe_evidence_vectors.text import clean_text, normalized_key  # noqa: E402


DEFAULT_INPUT_DIR = ROOT / "data" / "local_search_logs" / "umls_query_exports"
DEFAULT_OUT = ROOT / "build" / "local_search_logs" / "query_inventory.tsv"
DEFAULT_SUMMARY_OUT = ROOT / "build" / "local_search_logs" / "query_inventory_summary.json"
DEFAULT_REVIEW_QUEUE_OUT = ROOT / "build" / "local_search_logs" / "query_review_queue.tsv"

FIELDNAMES = [
    "source_file",
    "source_row",
    "token_bucket",
    "search_term",
    "unique_users",
    "normalized_term",
    "normalized_token_count",
    "privacy_flags",
    "server_hit_count",
    "server_top_cui",
    "server_top_label",
    "server_score",
    "server_error",
    "review_status",
    "reviewed_cui",
    "review_note",
]

REVIEW_QUEUE_FIELDNAMES = [
    "review_priority",
    "review_reasons",
    *FIELDNAMES,
]

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})")
URL_RE = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
LONG_DIGIT_RE = re.compile(r"\d{6,}")
CODE_LIKE_RE = re.compile(r"\b[A-Za-z]{1,10}[-_.\s]?\d[A-Za-z0-9_.-]*\b")
PUNCTUATION_RE = re.compile(r"[^\w\s]", re.UNICODE)


@dataclass(frozen=True)
class QueryRow:
    source_file: str
    source_row: int
    token_bucket: str
    search_term: str
    unique_users: int
    normalized_term: str
    normalized_token_count: int
    privacy_flags: tuple[str, ...]


@dataclass(frozen=True)
class SearchResult:
    hit_count: int = 0
    top_cui: str = ""
    top_label: str = ""
    score: float | None = None
    error: str = ""


def token_bucket(path: Path) -> str:
    name = path.name.removesuffix("-real-queries.csv")
    return name.replace("-word", "")


def bucket_sort_key(path: Path) -> tuple[int, str]:
    bucket = token_bucket(path)
    order = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "12-13": 12,
        "14-or-more": 14,
    }
    return order.get(bucket, 999), path.name


def privacy_flags(term: str) -> tuple[str, ...]:
    flags = []
    if EMAIL_RE.search(term):
        flags.append("email_like")
    if PHONE_RE.search(term):
        flags.append("phone_like")
    if URL_RE.search(term):
        flags.append("url_like")
    if LONG_DIGIT_RE.search(term):
        flags.append("long_digit_run")
    if any(ord(char) > 127 for char in term):
        flags.append("non_ascii")
    return tuple(flags)


def int_or_zero(value: str | None) -> int:
    if not value:
        return 0
    try:
        return int(value)
    except ValueError:
        return 0


def row_key(row: QueryRow) -> tuple[str, int]:
    return row.source_file, row.source_row


def iter_query_rows(input_dir: Path) -> Iterable[QueryRow]:
    files = sorted(input_dir.glob("*-word-real-queries.csv"), key=bucket_sort_key)
    for path in files:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = {"search_term", "unique_users"} - set(reader.fieldnames or [])
            if missing:
                missing_list = ", ".join(sorted(missing))
                raise ValueError(f"{path} is missing required column(s): {missing_list}")
            for source_row, row in enumerate(reader, start=2):
                term = clean_text(row.get("search_term") or "")
                if not term:
                    continue
                norm = normalized_key(term)
                yield QueryRow(
                    source_file=path.name,
                    source_row=source_row,
                    token_bucket=token_bucket(path),
                    search_term=term,
                    unique_users=int_or_zero(row.get("unique_users")),
                    normalized_term=norm,
                    normalized_token_count=len(norm.split()) if norm else 0,
                    privacy_flags=privacy_flags(term),
                )


def search_result_from_response(response: dict) -> SearchResult:
    hits = list(response.get("hits") or [])
    if not hits:
        return SearchResult(hit_count=0)
    top = hits[0]
    score_value = top.get("rank_score")
    if score_value is None:
        score_value = top.get("score")
    score = None
    if score_value is not None:
        try:
            score = float(score_value)
        except (TypeError, ValueError):
            score = None
    return SearchResult(
        hit_count=len(hits),
        top_cui=str(top.get("cui") or ""),
        top_label=str(top.get("name") or top.get("label") or ""),
        score=score,
    )


def format_score(score: float | None) -> str:
    if score is None:
        return ""
    return f"{score:.6g}"


def get_json(base_url: str, path: str, params: dict[str, str | int], *, timeout: float) -> dict:
    url = f"{base_url.rstrip('/')}{path}?{urlencode(params)}"
    with urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def score_query(
    row: QueryRow,
    *,
    base_url: str,
    top_k: int,
    mode: str,
    include_related: bool,
    timeout: float,
) -> SearchResult:
    try:
        response = get_json(
            base_url,
            "/api/search",
            {
                "q": row.search_term,
                "k": top_k,
                "mode": mode,
                "related": 1 if include_related else 0,
            },
            timeout=timeout,
        )
    except HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace").strip()
        return SearchResult(error=f"http_{exc.code}: {message[:240]}")
    except (TimeoutError, URLError, OSError) as exc:
        return SearchResult(error=str(exc)[:240])
    except json.JSONDecodeError as exc:
        return SearchResult(error=f"invalid_json: {exc}")
    return search_result_from_response(response)


def score_rows(
    rows: list[QueryRow],
    *,
    base_url: str,
    top_k: int,
    mode: str,
    include_related: bool,
    timeout: float,
    progress_every: int,
) -> dict[tuple[str, int], SearchResult]:
    results = {}
    total = len(rows)
    for index, row in enumerate(rows, start=1):
        if progress_every > 0 and (index == 1 or index % progress_every == 0 or index == total):
            print(f"scoring {index}/{total}", file=sys.stderr)
        results[row_key(row)] = score_query(
            row,
            base_url=base_url,
            top_k=top_k,
            mode=mode,
            include_related=include_related,
            timeout=timeout,
        )
    return results


def row_payload(
    row: QueryRow,
    server_result: SearchResult | None = None,
) -> dict[str, str | int]:
    was_scored = server_result is not None
    server_result = server_result or SearchResult()
    return {
        "source_file": row.source_file,
        "source_row": row.source_row,
        "token_bucket": row.token_bucket,
        "search_term": row.search_term,
        "unique_users": row.unique_users,
        "normalized_term": row.normalized_term,
        "normalized_token_count": row.normalized_token_count,
        "privacy_flags": "|".join(row.privacy_flags),
        "server_hit_count": server_result.hit_count if was_scored else "",
        "server_top_cui": server_result.top_cui,
        "server_top_label": server_result.top_label,
        "server_score": format_score(server_result.score),
        "server_error": server_result.error,
        "review_status": "",
        "reviewed_cui": "",
        "review_note": "",
    }


def summarize(rows: list[QueryRow]) -> dict[str, object]:
    bucket_counts = Counter(row.token_bucket for row in rows)
    flag_counts = Counter(flag for row in rows for flag in row.privacy_flags)
    return {
        "rows": len(rows),
        "sum_unique_users": sum(row.unique_users for row in rows),
        "max_unique_users": max((row.unique_users for row in rows), default=0),
        "buckets": dict(sorted(bucket_counts.items())),
        "privacy_flags": dict(sorted(flag_counts.items())),
    }


def summarize_server_results(
    server_results: dict[tuple[str, int], SearchResult],
    *,
    low_score_threshold: float,
) -> dict[str, object]:
    scored = list(server_results.values())
    return {
        "scored_rows": len(scored),
        "server_hits": sum(1 for result in scored if result.hit_count > 0),
        "server_no_hits": sum(1 for result in scored if result.hit_count == 0 and not result.error),
        "server_errors": sum(1 for result in scored if result.error),
        "server_low_score_hits": sum(
            1
            for result in scored
            if result.hit_count > 0 and result.score is not None and result.score < low_score_threshold
        ),
    }


def write_inventory(
    rows: list[QueryRow],
    out: Path,
    server_results: dict[tuple[str, int], SearchResult] | None = None,
) -> None:
    server_results = server_results or {}
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row_payload(row, server_results.get(row_key(row))))


def review_reasons(
    row: QueryRow,
    server_result: SearchResult | None,
    *,
    low_score_threshold: float,
    high_demand_min: int,
) -> list[str]:
    reasons = []
    if row.privacy_flags:
        reasons.extend(f"privacy:{flag}" for flag in row.privacy_flags)
    if server_result is not None:
        if server_result.error:
            reasons.append("server_error")
        elif server_result.hit_count == 0:
            reasons.append("no_server_hit")
        elif server_result.score is not None and server_result.score < low_score_threshold:
            reasons.append("low_server_score")
    if row.unique_users >= high_demand_min:
        reasons.append("high_demand")
    if CODE_LIKE_RE.search(row.search_term):
        reasons.append("code_like")
    punctuation_count = len(PUNCTUATION_RE.findall(row.search_term))
    if punctuation_count >= 2 and not row.privacy_flags:
        reasons.append("punctuation_variant")
    if row.normalized_token_count >= 8:
        reasons.append("long_query")
    return reasons


def review_priority(
    row: QueryRow,
    server_result: SearchResult | None,
    *,
    low_score_threshold: float,
    high_demand_min: int,
) -> int:
    reasons = review_reasons(
        row,
        server_result,
        low_score_threshold=low_score_threshold,
        high_demand_min=high_demand_min,
    )
    priority = row.unique_users
    if any(reason.startswith("privacy:") for reason in reasons):
        priority += 100_000
    if "server_error" in reasons:
        priority += 75_000
    if "no_server_hit" in reasons:
        priority += 60_000
    if "low_server_score" in reasons:
        priority += 35_000
    if "code_like" in reasons:
        priority += 5_000
    if "punctuation_variant" in reasons:
        priority += 2_000
    if "long_query" in reasons:
        priority += 1_000
    return priority


def review_queue_rows(
    rows: list[QueryRow],
    server_results: dict[tuple[str, int], SearchResult] | None = None,
    *,
    limit: int,
    low_score_threshold: float,
    high_demand_min: int,
) -> list[dict[str, str | int]]:
    server_results = server_results or {}
    queued = []
    for row in rows:
        server_result = server_results.get(row_key(row))
        reasons = review_reasons(
            row,
            server_result,
            low_score_threshold=low_score_threshold,
            high_demand_min=high_demand_min,
        )
        priority = review_priority(
            row,
            server_result,
            low_score_threshold=low_score_threshold,
            high_demand_min=high_demand_min,
        )
        if not reasons:
            continue
        payload = row_payload(row, server_result)
        payload["review_priority"] = priority
        payload["review_reasons"] = "|".join(reasons)
        queued.append(payload)
    queued.sort(
        key=lambda item: (
            -int(item["review_priority"]),
            -int(item["unique_users"]),
            str(item["normalized_term"]),
            str(item["source_file"]),
            int(item["source_row"]),
        )
    )
    return queued[:limit]


def write_review_queue(
    rows: list[QueryRow],
    out: Path,
    server_results: dict[tuple[str, int], SearchResult] | None = None,
    *,
    limit: int,
    low_score_threshold: float,
    high_demand_min: int,
) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    queued = review_queue_rows(
        rows,
        server_results,
        limit=limit,
        low_score_threshold=low_score_threshold,
        high_demand_min=high_demand_min,
    )
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_QUEUE_FIELDNAMES, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in queued:
            writer.writerow(row)
    return len(queued)


def write_summary(summary: dict[str, object], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a local TSV inventory from bucketed real UMLS search query CSV exports."
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY_OUT)
    parser.add_argument(
        "--sort",
        choices=("file", "demand"),
        default="file",
        help="Use file order or sort by descending unique_users.",
    )
    parser.add_argument("--max-rows", type=int, help="Limit output rows after sorting.")
    parser.add_argument(
        "--review-queue-out",
        type=Path,
        help=f"Write a prioritized local review queue TSV, for example {DEFAULT_REVIEW_QUEUE_OUT}.",
    )
    parser.add_argument("--review-queue-limit", type=int, default=500)
    parser.add_argument(
        "--high-demand-min",
        type=int,
        default=5,
        help="Minimum per-term unique_users for a high_demand review reason.",
    )
    parser.add_argument(
        "--low-score-threshold",
        type=float,
        default=0.35,
        help="When scoring against the search API, queue hits below this top score for review.",
    )
    parser.add_argument(
        "--score-api",
        action="store_true",
        help="Call the local /api/search endpoint for selected rows and fill server_* columns.",
    )
    parser.add_argument(
        "--score-all",
        action="store_true",
        help="Allow --score-api without --max-rows. This can issue more than 100k local API calls.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8766")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--mode", default="balanced")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--include-related", action="store_true")
    parser.add_argument(
        "--progress-every",
        type=int,
        default=25,
        help="Print API scoring progress every N rows. Use 0 to disable.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.score_api and args.max_rows is None and not args.score_all:
        print("--score-api requires --max-rows or --score-all", file=sys.stderr)
        return 2
    rows = list(iter_query_rows(args.input_dir))
    if args.sort == "demand":
        rows = sorted(rows, key=lambda row: (-row.unique_users, row.normalized_term, row.source_file, row.source_row))
    if args.max_rows is not None:
        rows = rows[: args.max_rows]
    server_results = {}
    if args.score_api:
        server_results = score_rows(
            rows,
            base_url=args.base_url,
            top_k=args.top_k,
            mode=args.mode,
            include_related=args.include_related,
            timeout=args.timeout,
            progress_every=args.progress_every,
        )
    write_inventory(rows, args.out, server_results)
    summary = summarize(rows)
    if server_results:
        summary.update(
            summarize_server_results(
                server_results,
                low_score_threshold=args.low_score_threshold,
            )
        )
    if args.review_queue_out:
        review_queue_count = write_review_queue(
            rows,
            args.review_queue_out,
            server_results,
            limit=args.review_queue_limit,
            low_score_threshold=args.low_score_threshold,
            high_demand_min=args.high_demand_min,
        )
        summary["review_queue_rows"] = review_queue_count
        summary["review_queue_out"] = str(args.review_queue_out)
    write_summary(summary, args.summary_out)
    print(f"wrote {summary['rows']} rows to {args.out}")
    if args.review_queue_out:
        print(f"wrote {summary['review_queue_rows']} rows to {args.review_queue_out}")
    print(f"wrote summary to {args.summary_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
