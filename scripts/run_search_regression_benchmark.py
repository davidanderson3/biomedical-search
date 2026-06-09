#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path


CUI_RE = re.compile(r"C\d{7}", re.IGNORECASE)
QUERY_COLUMNS = ("query", "q", "term", "search_term", "search terms", "text")
EXPECTED_COLUMNS = (
    "expected_cui",
    "expected_cuis",
    "acceptable_cui",
    "acceptable_cuis",
    "target_cui",
    "target_cuis",
    "gold_cui",
    "gold_cuis",
    "cui",
    "cuis",
)


def split_cuis(value: object) -> list[str]:
    text = str(value or "")
    return sorted({match.group(0).upper() for match in CUI_RE.finditer(text)})


def sniff_dialect(path: Path) -> csv.Dialect:
    sample = path.read_text(encoding="utf-8", errors="replace")[:8192]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t|")
    except csv.Error:
        class DefaultDialect(csv.excel):
            delimiter = "\t" if sample.count("\t") > sample.count(",") else ","

        return DefaultDialect


def read_query_rows(path: Path) -> list[dict]:
    dialect = sniff_dialect(path)
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        raw_rows = list(
            csv.reader(
                (line for line in handle if line.strip() and not line.lstrip().startswith("#")),
                dialect=dialect,
            )
        )
        if not raw_rows:
            return []
        header = [str(value or "").strip().lower() for value in raw_rows[0]]
        has_header = bool(set(header) & (set(QUERY_COLUMNS) | set(EXPECTED_COLUMNS)))
        data_rows = raw_rows[1:] if has_header else raw_rows
        rows = []
        for raw_index, raw_values in enumerate(data_rows, start=2 if has_header else 1):
            if has_header:
                raw_row = {
                    header[index]: raw_values[index] if index < len(raw_values) else ""
                    for index in range(len(header))
                }
            else:
                raw_row = {
                    "query": raw_values[0] if raw_values else "",
                    "expected_cuis": "|".join(raw_values[1:]) if len(raw_values) > 1 else "",
                }
            normalized = {
                str(key or "").strip().lower(): str(value or "").strip()
                for key, value in raw_row.items()
            }
            query = next(
                (normalized[column] for column in QUERY_COLUMNS if normalized.get(column)),
                "",
            )
            if not query:
                first_value = next((value for value in normalized.values() if value), "")
                query = first_value
            if not query:
                continue
            expected = []
            for column in EXPECTED_COLUMNS:
                expected.extend(split_cuis(normalized.get(column)))
            rows.append(
                {
                    "query": query,
                    "expected_cuis": sorted(set(expected)),
                    "source_path": str(path),
                    "source_row": raw_index,
                }
            )
        return rows


def search(
    base_url: str,
    query: str,
    *,
    top_k: int,
    related: bool,
    mode: str,
    scope: str,
    timeout: float,
) -> tuple[dict, float]:
    params = urllib.parse.urlencode(
        {
            "q": query,
            "k": top_k,
            "related": "1" if related else "0",
            "mode": mode,
            "scope": scope,
            "codes": "default",
        }
    )
    url = f"{base_url.rstrip('/')}/api/search?{params}"
    started = time.time()
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = json.load(response)
    return payload, time.time() - started


def reciprocal_rank(hits: list[dict], expected_cuis: list[str]) -> float:
    expected = set(expected_cuis)
    if not expected:
        return 0.0
    for index, hit in enumerate(hits, start=1):
        if str(hit.get("cui") or "").upper() in expected:
            return 1.0 / index
    return 0.0


def evaluate_row(
    row: dict,
    *,
    base_url: str,
    top_k: int,
    related: bool,
    mode: str,
    scope: str,
    timeout: float,
) -> dict:
    payload, elapsed = search(
        base_url,
        row["query"],
        top_k=top_k,
        related=related,
        mode=mode,
        scope=scope,
        timeout=timeout,
    )
    hits = list(payload.get("hits") or [])
    hit_cuis = [str(hit.get("cui") or "").upper() for hit in hits]
    expected = list(row.get("expected_cuis") or [])
    expected_set = set(expected)
    return {
        "query": row["query"],
        "source_path": row["source_path"],
        "source_row": row["source_row"],
        "expected_cuis": expected,
        "top_cui": hit_cuis[0] if hit_cuis else "",
        "top_name": str(hits[0].get("name") or "") if hits else "",
        "top_hit": bool(hit_cuis and hit_cuis[0] in expected_set) if expected else None,
        "top3_hit": bool(expected_set & set(hit_cuis[:3])) if expected else None,
        "topk_hit": bool(expected_set & set(hit_cuis)) if expected else None,
        "reciprocal_rank": reciprocal_rank(hits, expected) if expected else None,
        "hit_cuis": hit_cuis,
        "elapsed_ms": round(elapsed * 1000, 1),
        "server_elapsed_ms": payload.get("elapsed_ms"),
        "backend": payload.get("backend"),
    }


def summarize(rows: list[dict]) -> dict:
    judged = [row for row in rows if row.get("expected_cuis")]

    def rate(key: str) -> float | None:
        if not judged:
            return None
        return round(sum(1 for row in judged if row.get(key)) / len(judged), 6)

    latencies = [float(row.get("elapsed_ms") or 0.0) for row in rows]
    return {
        "queries": len(rows),
        "judged_queries": len(judged),
        "top1_accuracy": rate("top_hit"),
        "top3_accuracy": rate("top3_hit"),
        "topk_accuracy": rate("topk_hit"),
        "mrr": (
            round(sum(float(row.get("reciprocal_rank") or 0.0) for row in judged) / len(judged), 6)
            if judged
            else None
        ),
        "mean_elapsed_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
        "max_elapsed_ms": round(max(latencies), 1) if latencies else 0.0,
    }


def write_rows_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "query",
        "source_path",
        "source_row",
        "expected_cuis",
        "top_cui",
        "top_name",
        "top_hit",
        "top3_hit",
        "topk_hit",
        "reciprocal_rank",
        "hit_cuis",
        "elapsed_ms",
        "server_elapsed_ms",
        "backend",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            output = dict(row)
            output["expected_cuis"] = "|".join(output.get("expected_cuis") or [])
            output["hit_cuis"] = "|".join(output.get("hit_cuis") or [])
            writer.writerow(output)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a search regression benchmark against /api/search.")
    parser.add_argument("query_files", type=Path, nargs="+", help="CSV/TSV files with query rows.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8766")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--mode", choices=["balanced", "exact", "comprehensive"], default="balanced")
    parser.add_argument(
        "--scope",
        choices=["umls", "umls_evidence"],
        default="umls_evidence",
        help="Search scope to request from /api/search. Use umls for reviewed real-query UMLS API regressions.",
    )
    parser.add_argument("--related", action="store_true")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--limit", type=int, help="Limit total query rows for quick smoke runs.")
    parser.add_argument("--rows-out", type=Path, help="Optional CSV path for per-query results.")
    parser.add_argument("--json-out", type=Path, help="Optional JSON summary output path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    query_rows = []
    for path in args.query_files:
        query_rows.extend(read_query_rows(path))
    if args.limit:
        query_rows = query_rows[: max(0, args.limit)]
    results = [
        evaluate_row(
            row,
            base_url=args.base_url,
            top_k=args.top_k,
            related=args.related,
            mode=args.mode,
            scope=args.scope,
            timeout=args.timeout,
        )
        for row in query_rows
    ]
    summary = summarize(results)
    output = {"summary": summary, "rows": results}
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.rows_out:
        write_rows_csv(args.rows_out, results)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
