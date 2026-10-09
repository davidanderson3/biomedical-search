#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import getpass
import hashlib
import html
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from compare_umls_api import QuerySpec, umls_hits, umls_search  # noqa: E402


EXPANSION_SEPARATOR = " || "
VALID_DECISIONS = {"include", "exclude"}
QUERY_FIELDS = [
    "id",
    "search_term",
    "decision",
    "expansion_queries",
    "expansion_classes",
    "expansion_note",
    "sum_unique_users",
    "baseline_hit_count",
    "expansion_query_count",
    "successful_expansion_query_count",
    "union_hit_count",
    "expansion_only_hit_count",
    "candidate_missed_result_rate",
    "baseline_no_hit_rescued",
    "partial_result_gain",
    "baseline_at_api_cap",
    "baseline_truncated_at_k",
    "complete_comparison",
    "errors",
]
CANDIDATE_FIELDS = [
    "review_status",
    "relevance_note",
    "id",
    "search_term",
    "sum_unique_users",
    "baseline_hit_count",
    "union_hit_count",
    "expansion_only_cui",
    "expansion_name",
    "expansion_root_source",
    "triggering_expansions",
    "expansion_class",
]
RELEVANT_STATUSES = {"include", "included", "relevant", "yes", "approved"}
IRRELEVANT_STATUSES = {"exclude", "excluded", "irrelevant", "no", "reject", "rejected"}


@dataclass(frozen=True)
class Expansion:
    query: str
    strategy: str
    note: str


@dataclass(frozen=True)
class ExpansionSpec:
    query_id: str
    search_term: str
    decision: str
    expansions: tuple[Expansion, ...]
    note: str


def normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def split_expansions(value: str) -> tuple[str, ...]:
    seen: set[str] = set()
    expansions = []
    for raw in value.split(EXPANSION_SEPARATOR):
        item = " ".join(raw.split()).strip()
        key = normalize(item)
        if item and key not in seen:
            seen.add(key)
            expansions.append(item)
    return tuple(expansions)


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


def load_manifest(path: Path) -> dict[str, ExpansionSpec]:
    grouped: dict[str, dict[str, object]] = {}
    for line_number, row in enumerate(read_tsv(path), start=2):
        query_id = str(row.get("id") or "").strip()
        decision = str(row.get("decision") or "").strip().lower()
        if not query_id:
            raise ValueError(f"{path}:{line_number}: missing id")
        if decision not in VALID_DECISIONS:
            raise ValueError(
                f"{path}:{line_number}: decision must be one of {sorted(VALID_DECISIONS)}"
            )
        search_term = str(row.get("search_term") or "").strip()
        current = grouped.setdefault(
            query_id,
            {
                "search_term": search_term,
                "decision": decision,
                "expansions": [],
                "notes": [],
            },
        )
        if normalize(str(current["search_term"])) != normalize(search_term) or current["decision"] != decision:
            raise ValueError(f"{path}:{line_number}: inconsistent repeated row for id {query_id}")
        expansions = current["expansions"]
        notes = current["notes"]
        assert isinstance(expansions, list)
        assert isinstance(notes, list)
        expansion_queries = split_expansions(str(row.get("expansion_query") or ""))
        strategy = str(row.get("expansion_strategy") or "").strip().lower()
        note = str(row.get("expansion_note") or "").strip()
        if expansion_queries:
            if not strategy:
                raise ValueError(f"{path}:{line_number}: expansion_query requires expansion_strategy")
            for expansion_query in expansion_queries:
                if normalize(expansion_query) == normalize(search_term):
                    continue
                expansion = Expansion(query=expansion_query, strategy=strategy, note=note)
                if expansion not in expansions:
                    expansions.append(expansion)
        if note and note not in notes:
            notes.append(note)
    specs = {
        query_id: ExpansionSpec(
            query_id=query_id,
            search_term=str(values["search_term"]),
            decision=str(values["decision"]),
            expansions=tuple(values["expansions"]),
            note=" | ".join(str(note) for note in values["notes"]),
        )
        for query_id, values in grouped.items()
    }
    return specs


def validate_manifest(base_rows: list[dict[str, str]], specs: dict[str, ExpansionSpec]) -> None:
    base_ids = {row["id"] for row in base_rows}
    spec_ids = set(specs)
    missing = sorted(base_ids - spec_ids)
    extra = sorted(spec_ids - base_ids)
    mismatched = sorted(
        row["id"]
        for row in base_rows
        if row["id"] in specs and normalize(row["search_term"]) != normalize(specs[row["id"]].search_term)
    )
    problems = []
    if missing:
        problems.append(f"missing {len(missing)} base ids (first: {', '.join(missing[:5])})")
    if extra:
        problems.append(f"contains {len(extra)} unknown ids (first: {', '.join(extra[:5])})")
    if mismatched:
        problems.append(f"contains {len(mismatched)} term/id mismatches (first: {', '.join(mismatched[:5])})")
    if problems:
        raise ValueError("Manifest does not cover the baseline exactly: " + "; ".join(problems))


def resolve_api_key() -> str:
    key = (os.environ.get("UMLS_API_KEY") or os.environ.get("APIKEY") or "").strip()
    if key:
        return key
    try:
        return getpass.getpass("Enter UMLS API key (input hidden): ").strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def cache_path(cache_dir: Path, query: str, search_type: str) -> Path:
    digest = hashlib.sha256(f"{search_type}\0{normalize(query)}".encode()).hexdigest()
    return cache_dir / f"{digest}.json"


def cached_umls_search(
    *,
    cache_dir: Path,
    query: str,
    api_key: str,
    base_url: str,
    search_type: str,
    page_size: int,
    timeout: float,
    retries: int,
    retry_backoff: float,
) -> tuple[list[dict], str, bool]:
    path = cache_path(cache_dir, query, search_type)
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        return list(cached.get("hits") or []), "", True
    error = ""
    for attempt in range(retries + 1):
        try:
            payload = umls_search(
                base_url=base_url,
                api_key=api_key,
                spec=QuerySpec(query_id="expansion", query=query, search_type=search_type, sabs=""),
                page_size=page_size,
                search_type=search_type,
                sabs="",
                timeout=timeout,
            )
            hits = umls_hits(payload)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "query": query,
                        "search_type": search_type,
                        "generated_utc": datetime.now(timezone.utc).isoformat(),
                        "hits": hits,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            return hits, "", False
        except Exception as exc:  # noqa: BLE001 - preserve the failed request in audit output
            error = str(exc)[:500]
            if attempt < retries:
                time.sleep(max(0.0, retry_backoff) * (2**attempt))
    return [], error, False


def cuis_from_row(row: dict[str, str], top_k: int) -> list[str]:
    cuis = [part.strip().upper() for part in str(row.get("umls_hit_cuis") or "").split("|") if part.strip()]
    return cuis[:top_k] if top_k else cuis


def hits_by_cui(hits: list[dict], top_k: int) -> dict[str, dict]:
    selected = hits[:top_k] if top_k else hits
    result = {}
    for hit in selected:
        cui = str(hit.get("cui") or "").upper()
        if cui and cui not in result:
            result[cui] = hit
    return result


def safe_rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def compare_sets(
    baseline: set[str],
    expansion_maps: list[tuple[Expansion, dict[str, dict]]],
) -> tuple[set[str], dict[str, list[str]], dict[str, set[str]], dict[str, dict]]:
    union = set(baseline)
    triggers: dict[str, list[str]] = defaultdict(list)
    strategies: dict[str, set[str]] = defaultdict(set)
    metadata: dict[str, dict] = {}
    for expansion, hits in expansion_maps:
        for cui, hit in hits.items():
            union.add(cui)
            if cui not in baseline:
                triggers[cui].append(expansion.query)
                strategies[cui].add(expansion.strategy)
                metadata.setdefault(cui, hit)
    return union, triggers, strategies, metadata


def build_summary(query_rows: list[dict[str, object]], candidate_rows: list[dict[str, object]]) -> dict[str, object]:
    included = [row for row in query_rows if row["decision"] == "include"]
    complete = [row for row in included if row["complete_comparison"] == "1"]
    baseline_pairs = sum(int(row["baseline_hit_count"]) for row in complete)
    union_pairs = sum(int(row["union_hit_count"]) for row in complete)
    novel_pairs = sum(int(row["expansion_only_hit_count"]) for row in complete)
    rescued = sum(int(row["baseline_no_hit_rescued"]) for row in complete)
    baseline_no_hits = sum(int(row["baseline_hit_count"]) == 0 for row in complete)
    partial_gains = sum(int(row["partial_result_gain"]) for row in complete)
    any_gains = rescued + partial_gains
    by_strategy: dict[str, dict[str, object]] = {}
    strategy_pairs: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for row in candidate_rows:
        for strategy in str(row.get("expansion_class") or "").split("|"):
            if strategy:
                strategy_pairs[strategy].add((str(row["id"]), str(row["expansion_only_cui"])))
    for strategy, pairs in sorted(strategy_pairs.items()):
        by_strategy[strategy] = {
            "expansion_only_query_cui_pairs": len(pairs),
            "queries_with_gain": len({query_id for query_id, _ in pairs}),
        }
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_queries": len(query_rows),
        "included_queries": len(included),
        "excluded_queries": len(query_rows) - len(included),
        "complete_comparisons": len(complete),
        "incomplete_comparisons": len(included) - len(complete),
        "baseline_query_cui_pairs": baseline_pairs,
        "union_query_cui_pairs": union_pairs,
        "expansion_only_query_cui_pairs": novel_pairs,
        "candidate_missed_result_rate": safe_rate(novel_pairs, union_pairs),
        "candidate_missed_result_percentage": round(100 * novel_pairs / union_pairs, 2)
        if union_pairs
        else 0.0,
        "queries_with_expansion_gain": any_gains,
        "queries_with_expansion_gain_rate": safe_rate(any_gains, len(complete)),
        "baseline_no_hit_queries": baseline_no_hits,
        "baseline_no_hit_queries_rescued": rescued,
        "baseline_no_hit_rescue_rate": safe_rate(rescued, baseline_no_hits),
        "queries_with_partial_result_gain": partial_gains,
        "partial_result_gain_rate": safe_rate(partial_gains, len(complete)),
        "baseline_queries_at_api_cap": sum(int(row["baseline_at_api_cap"]) for row in complete),
        "baseline_queries_truncated_at_k": sum(int(row["baseline_truncated_at_k"]) for row in complete),
        "candidate_rows": len(candidate_rows),
        "by_expansion_strategy": by_strategy,
        "metric_warning": (
            "Expansion-only CUIs are candidate missed results, not adjudicated relevant results. "
            "The candidate percentage is expansion-only query-CUI pairs divided by all query-CUI pairs "
            "in the baseline-plus-expansion union for complete included comparisons."
        ),
    }


def percent(value: object) -> str:
    try:
        return f"{100 * float(value):.1f}%"
    except (TypeError, ValueError):
        return "0.0%"


def render_html(
    *,
    output_path: Path,
    summary: dict[str, object],
    query_rows: list[dict[str, object]],
    candidates_path: Path,
) -> None:
    gain_rows = [row for row in query_rows if int(row["expansion_only_hit_count"]) > 0]
    gain_rows.sort(
        key=lambda row: (
            -int(row["expansion_only_hit_count"]),
            -int(row["sum_unique_users"]),
            str(row["search_term"]),
        )
    )
    table_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row['search_term']))}</td>"
        f"<td>{row['baseline_hit_count']}</td>"
        f"<td>{row['expansion_only_hit_count']}</td>"
        f"<td>{row['union_hit_count']}</td>"
        f"<td>{percent(row['candidate_missed_result_rate'])}</td>"
        f"<td>{html.escape(str(row['expansion_queries']))}</td>"
        "</tr>"
        for row in gain_rows
    ) or '<tr><td colspan="6">No completed query has expansion-only CUIs.</td></tr>'
    error_rows = [row for row in query_rows if row["errors"]]
    excluded_rows = [row for row in query_rows if row["decision"] == "exclude"]
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>UMLS Language-Expansion Audit</title>
<style>
:root{{--ink:#17232e;--muted:#617180;--paper:#f4f7f6;--card:#fff;--line:#d9e3e0;--teal:#08766e;--blue:#183f60;--amber:#b66d0a}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}header{{background:linear-gradient(120deg,var(--blue),var(--teal));color:#fff;padding:46px max(24px,calc((100% - 1120px)/2))}}h1{{font-size:clamp(30px,5vw,48px);line-height:1.05;margin:8px 0}}header p{{max-width:800px;color:#d9edeb}}main{{max-width:1120px;margin:auto;padding:28px 24px 60px}}.eyebrow{{font-size:12px;text-transform:uppercase;letter-spacing:.12em;font-weight:800}}.metrics{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:15px;margin:24px 0}}.card{{background:#fff;border:1px solid var(--line);border-radius:14px;padding:19px;box-shadow:0 4px 18px #183f600c}}.card.hero{{border-top:5px solid var(--teal)}}.card span,.card small{{display:block;color:var(--muted)}}.card strong{{display:block;color:var(--blue);font-size:33px;margin:7px 0}}.notice{{background:#fff6e5;border-left:5px solid var(--amber);border-radius:8px;padding:16px 18px;margin:24px 0}}h2{{margin:30px 0 8px}}.table-wrap{{overflow:auto;max-height:650px;border:1px solid var(--line);border-radius:12px;background:#fff}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{padding:10px 12px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}}th{{position:sticky;top:0;background:#eaf2f0;color:var(--blue)}}tr:nth-child(even){{background:#fafcfc}}code{{background:#e7eeec;padding:2px 5px;border-radius:4px}}a{{color:var(--teal);font-weight:700}}footer{{margin-top:32px;color:var(--muted);font-size:13px}}@media(max-width:800px){{.metrics{{grid-template-columns:1fr}}}}@media print{{.table-wrap{{max-height:none;overflow:visible}}th{{position:static}}}}
</style></head><body><header><div class="eyebrow">Search quality · Query expansion proxy</div><h1>UMLS Language-Expansion Audit</h1><p>Compares CUIs returned for each original query with the deduplicated union returned by conservative spelling, abbreviation, brand/generic, lay/clinical, and equivalent-phrasing expansions.</p></header><main>
<section class="metrics">
<article class="card hero"><span>Candidate missed-result share</span><strong>{summary['candidate_missed_result_percentage']:.2f}%</strong><small>{summary['expansion_only_query_cui_pairs']:,} expansion-only query–CUI pairs out of {summary['union_query_cui_pairs']:,} union pairs</small></article>
<article class="card"><span>Queries gaining results</span><strong>{percent(summary['queries_with_expansion_gain_rate'])}</strong><small>{summary['queries_with_expansion_gain']} of {summary['complete_comparisons']} complete comparisons</small></article>
<article class="card"><span>No-hit queries rescued</span><strong>{percent(summary['baseline_no_hit_rescue_rate'])}</strong><small>{summary['baseline_no_hit_queries_rescued']} of {summary['baseline_no_hit_queries']} baseline no-hits</small></article>
<article class="card"><span>Queries with partial-result gain</span><strong>{percent(summary['partial_result_gain_rate'])}</strong><small>{summary['queries_with_partial_result_gain']} queries already had results and gained additional CUIs</small></article>
<article class="card"><span>Complete comparisons</span><strong>{summary['complete_comparisons']}</strong><small>{summary['incomplete_comparisons']} incomplete because of API errors</small></article>
<article class="card"><span>Excluded ambiguous/noisy queries</span><strong>{summary['excluded_queries']}</strong><small>Represented in the manifest but omitted from the proxy denominator</small></article>
</section>
<div class="notice"><strong>Proxy, not ground truth.</strong> {html.escape(str(summary['metric_warning']))} Review expansion-only CUIs before describing them as relevant missed results. Queries that reached the 200-result UMLS cap are also censored.</div>
<h2>Expansion gains by query</h2><p>Includes complete comparisons with at least one expansion-only CUI, ordered by incremental result count.</p>
<div class="table-wrap"><table><thead><tr><th>Original query</th><th>Baseline</th><th>Expansion-only</th><th>Union</th><th>Candidate miss share</th><th>Expansion queries</th></tr></thead><tbody>{table_rows}</tbody></table></div>
<h2>Coverage and quality controls</h2><ul><li>{summary['included_queries']} queries included; {len(excluded_rows)} excluded as ambiguous, non-concept, or unsafe to paraphrase.</li><li>{summary['baseline_queries_at_api_cap']} baseline queries reached the 200-result API cap; {summary['baseline_queries_truncated_at_k']} had more results than the comparison depth.</li><li>{len(error_rows)} included queries have incomplete comparisons due to API errors.</li><li><a href="{html.escape(candidates_path.name)}">Review every expansion-only CUI</a> and set <code>review_status</code> to <code>relevant</code> or <code>irrelevant</code>.</li></ul>
<footer>Generated {html.escape(str(summary['generated_utc']))}. Private log-derived report; do not publish raw queries without review.</footer></main></body></html>"""
    output_path.write_text(document, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare UMLS results for original queries with the union from human-authored language expansions."
    )
    parser.add_argument("--baseline-run", type=Path, required=True)
    parser.add_argument("--expansions", type=Path, help="Defaults to <baseline-run>/language_expansions.tsv")
    parser.add_argument("--output-dir", type=Path, help="Defaults to <baseline-run>/expansion_audit")
    parser.add_argument("--umls-base-url", default="https://uts-ws.nlm.nih.gov/rest")
    parser.add_argument("--search-type", default="words")
    parser.add_argument("--page-size", type=int, default=200)
    parser.add_argument(
        "--top-k",
        type=int,
        default=20,
        help="Compare the first K CUIs. Default 20 supports feasible relevance review; 0 uses all 200.",
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--retry-backoff", type=float, default=1.5)
    parser.add_argument("--sleep", type=float, default=0.15)
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--dry-run", action="store_true", help="Validate coverage and count API calls without calling UMLS.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    baseline_path = args.baseline_run / "rows.tsv"
    manifest_path = args.expansions or args.baseline_run / "language_expansions.tsv"
    output_dir = args.output_dir or args.baseline_run / "expansion_audit"
    base_rows = read_tsv(baseline_path)
    specs = load_manifest(manifest_path)
    validate_manifest(base_rows, specs)
    included_specs = [specs[row["id"]] for row in base_rows if specs[row["id"]].decision == "include"]
    requested_expansions = sum(len(spec.expansions) for spec in included_specs)
    baseline_retries = sum(bool(row.get("umls_error")) for row in base_rows if specs[row["id"]].decision == "include")
    if args.dry_run:
        print(f"validated {len(specs)} expansion decisions for {len(base_rows)} baseline queries")
        print(f"included queries: {len(included_specs)}")
        print(f"excluded queries: {len(base_rows) - len(included_specs)}")
        print(f"expansion query requests before cache: {requested_expansions}")
        print(f"baseline error retries before cache: {baseline_retries}")
        return 0

    api_key = resolve_api_key()
    if not api_key:
        print("A UMLS API key is required.", file=sys.stderr)
        return 2
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = output_dir / "cache"
    query_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    total_calls = requested_expansions + baseline_retries
    completed_calls = 0
    cache_hits = 0

    def run_search(query: str) -> tuple[list[dict], str]:
        nonlocal completed_calls, cache_hits
        hits, error, cached = cached_umls_search(
            cache_dir=cache_dir,
            query=query,
            api_key=api_key,
            base_url=args.umls_base_url,
            search_type=args.search_type,
            page_size=args.page_size,
            timeout=args.timeout,
            retries=max(0, args.retries),
            retry_backoff=max(0.0, args.retry_backoff),
        )
        completed_calls += 1
        cache_hits += int(cached)
        if args.progress_every > 0 and (
            completed_calls == 1
            or completed_calls % args.progress_every == 0
            or completed_calls == total_calls
        ):
            print(
                f"UMLS request {completed_calls}/{total_calls} ({cache_hits} cache hits)",
                file=sys.stderr,
            )
        if not cached and completed_calls < total_calls and args.sleep > 0:
            time.sleep(args.sleep)
        return hits, error

    for base_row in base_rows:
        spec = specs[base_row["id"]]
        baseline_cuis: set[str] = set()
        baseline_raw_count = 0
        expansion_maps: list[tuple[Expansion, dict[str, dict]]] = []
        errors = []
        if spec.decision == "include":
            if base_row.get("umls_error"):
                fresh_hits, error = run_search(base_row["search_term"])
                if error:
                    errors.append(f"baseline: {error}")
                baseline_raw_count = len(fresh_hits)
                baseline_map = hits_by_cui(fresh_hits, args.top_k)
                baseline_cuis = set(baseline_map)
            else:
                baseline_raw_count = int(str(base_row.get("umls_hit_count") or "0") or 0)
                baseline_cuis = set(cuis_from_row(base_row, args.top_k))
            for expansion in spec.expansions:
                hits, error = run_search(expansion.query)
                if error:
                    errors.append(f"{expansion.query}: {error}")
                    continue
                expansion_maps.append((expansion, hits_by_cui(hits, args.top_k)))
        union, triggers, strategies, metadata = compare_sets(baseline_cuis, expansion_maps)
        novel = union - baseline_cuis
        complete = spec.decision == "include" and not errors
        query_row: dict[str, object] = {
            "id": base_row["id"],
            "search_term": base_row["search_term"],
            "decision": spec.decision,
            "expansion_queries": EXPANSION_SEPARATOR.join(expansion.query for expansion in spec.expansions),
            "expansion_classes": "|".join(sorted({expansion.strategy for expansion in spec.expansions})),
            "expansion_note": spec.note,
            "sum_unique_users": base_row.get("sum_unique_users", "0"),
            "baseline_hit_count": len(baseline_cuis),
            "expansion_query_count": len(spec.expansions),
            "successful_expansion_query_count": len(expansion_maps),
            "union_hit_count": len(union),
            "expansion_only_hit_count": len(novel),
            "candidate_missed_result_rate": safe_rate(len(novel), len(union)),
            "baseline_no_hit_rescued": "1" if not baseline_cuis and novel else "0",
            "partial_result_gain": "1" if baseline_cuis and novel else "0",
            "baseline_at_api_cap": "1" if baseline_raw_count >= 200 else "0",
            "baseline_truncated_at_k": "1"
            if args.top_k and baseline_raw_count > args.top_k
            else "0",
            "complete_comparison": "1" if complete else "0",
            "errors": " | ".join(errors),
        }
        query_rows.append(query_row)
        if complete:
            for cui in sorted(novel):
                hit = metadata.get(cui) or {}
                candidate_rows.append(
                    {
                        "review_status": "",
                        "relevance_note": "",
                        "id": base_row["id"],
                        "search_term": base_row["search_term"],
                        "sum_unique_users": base_row.get("sum_unique_users", "0"),
                        "baseline_hit_count": len(baseline_cuis),
                        "union_hit_count": len(union),
                        "expansion_only_cui": cui,
                        "expansion_name": hit.get("name", ""),
                        "expansion_root_source": hit.get("root_source", ""),
                        "triggering_expansions": EXPANSION_SEPARATOR.join(triggers.get(cui, [])),
                        "expansion_class": "|".join(sorted(strategies.get(cui, set()))),
                    }
                )

    query_path = output_dir / "query_comparisons.tsv"
    candidate_path = output_dir / "expansion_only_cui_review.tsv"
    summary_path = output_dir / "summary.json"
    report_path = output_dir / "management_report.html"
    write_tsv(query_path, query_rows, QUERY_FIELDS)
    write_tsv(candidate_path, candidate_rows, CANDIDATE_FIELDS)
    summary = build_summary(query_rows, candidate_rows)
    summary.update(
        {
            "baseline_run": str(args.baseline_run),
            "expansion_manifest": str(manifest_path),
            "search_type": args.search_type,
            "result_depth": args.top_k or 200,
            "cache_hits_this_run": cache_hits,
            "query_comparisons_tsv": str(query_path),
            "candidate_review_tsv": str(candidate_path),
        }
    )
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    render_html(output_path=report_path, summary=summary, query_rows=query_rows, candidates_path=candidate_path)
    print(
        "Candidate missed-result percentage: "
        f"{summary['candidate_missed_result_percentage']}% "
        f"({summary['expansion_only_query_cui_pairs']}/{summary['union_query_cui_pairs']})"
    )
    print(f"wrote query comparisons to {query_path}")
    print(f"wrote expansion-only CUI review queue to {candidate_path}")
    print(f"wrote HTML report to {report_path}")
    return 1 if summary["incomplete_comparisons"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
