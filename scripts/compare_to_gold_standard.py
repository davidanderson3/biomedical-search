#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
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

from build_translation_benchmark_report import (  # noqa: E402
    build_report,
    file_lock_status,
    load_lock,
    rel_path,
    repo_path,
)
from evaluate_paragraph_quality import (  # noqa: E402
    DEFAULT_ACCEPTABLE_ALTERNATIVES,
    judge_quality,
    read_acceptable_alternatives,
    summarize,
    write_report,
    write_tsv,
)
from evaluate_search_api import QuerySpec, read_query_specs  # noqa: E402


DEFAULT_LOCK = ROOT / "config" / "translation_benchmark_lock.json"
DEFAULT_OUTPUT_ROOT = ROOT / "build" / "gold_standard_comparison"
DEFAULT_LIVE_SLICES = (
    "clinical_smoke",
    "pubmed_literature_dev",
    "pubmed_literature_heldout",
)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_id_from_timestamp(timestamp: str) -> str:
    return timestamp.replace("-", "").replace(":", "").replace("T", "T").replace("Z", "Z")


def pct(value: object) -> str:
    try:
        return f"{100.0 * float(value):.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def pct_count(numerator: object, denominator: object) -> str:
    try:
        den = float(denominator)
        if den == 0.0:
            return "n/a"
        return f"{100.0 * float(numerator) / den:.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def get_json(base_url: str, path: str, params: dict[str, str | int], *, timeout: float) -> dict:
    url = f"{base_url.rstrip('/')}{path}?{urlencode(params)}"
    with urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def search_api_response(
    *,
    base_url: str,
    spec: QuerySpec,
    top_k: int,
    mode: str,
    scope: str,
    timeout: float,
) -> dict:
    return get_json(
        base_url,
        "/api/search",
        {
            "q": spec.query,
            "k": top_k,
            "related": 0,
            "linked": 0,
            "evidence_items": 0,
            "mode": mode,
            "scope": scope,
            "codes": "default",
        },
        timeout=timeout,
    )


def add_current_quality_metrics(summary: dict, rows: list[dict]) -> dict:
    rows_total = len(rows)
    expected_total = int(summary.get("expected_concepts") or 0)
    found_10 = int(summary.get("found_at_10") or 0)
    queries_all_10 = int(summary.get("queries_all_expected_at_10") or 0)
    queries_all_20 = int(summary.get("queries_all_expected_at_20") or 0)
    summary["queries_with_missing_at_10"] = sum(1 for row in rows if row.get("missing_at_10"))
    summary["queries_with_missing_at_20"] = sum(1 for row in rows if row.get("missing_at_20"))
    summary["all_expected_at_10_rate"] = queries_all_10 / rows_total if rows_total else 0.0
    summary["all_expected_at_20_rate"] = queries_all_20 / rows_total if rows_total else 0.0
    summary["mean_coverage_at_10"] = (
        sum(float(row.get("coverage_at_10") or 0.0) for row in rows) / rows_total
        if rows_total
        else 0.0
    )
    summary["strict_success_at_10"] = queries_all_10
    summary["recall_at_10_text"] = f"{found_10}/{expected_total} ({pct(summary.get('recall_at_10'))})"
    return summary


def missing_examples(rows: list[dict], *, limit: int = 10) -> list[dict]:
    examples = []
    for row in rows:
        if not row.get("missing_at_10"):
            continue
        examples.append(
            {
                "id": row.get("id", ""),
                "missing_at_10": row.get("missing_at_10", ""),
                "top_cui": row.get("top_cui", ""),
                "top_name": row.get("top_name", ""),
            }
        )
        if len(examples) >= limit:
            break
    return examples


def run_live_quality_slice(
    slice_spec: dict,
    *,
    base_url: str,
    top_k: int,
    mode: str,
    scope: str,
    timeout: float,
    limit: int,
    output_dir: Path,
    alternatives: dict[str, set[str]],
    verbose: bool,
) -> dict:
    query_path = repo_path(slice_spec["path"])
    specs = read_query_specs(query_path)
    if limit > 0:
        specs = specs[:limit]
    if not specs:
        raise SystemExit(f"no queries found for {slice_spec['id']} at {query_path}")

    rows = []
    payload_dir = output_dir / slice_spec["id"] / "payloads"
    payload_dir.mkdir(parents=True, exist_ok=True)
    for index, spec in enumerate(specs, start=1):
        if verbose:
            print(f"[{slice_spec['id']} {index}/{len(specs)}] {spec.query_id}", file=sys.stderr)
        response = search_api_response(
            base_url=base_url,
            spec=spec,
            top_k=top_k,
            mode=mode,
            scope=scope,
            timeout=timeout,
        )
        hits = list(response.get("hits") or [])
        row = judge_quality(spec, hits, acceptable_alternatives=alternatives)
        rows.append(row)
        (payload_dir / f"{spec.query_id}.json").write_text(
            json.dumps(response, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    summary = add_current_quality_metrics(summarize(rows), rows)
    slice_dir = output_dir / slice_spec["id"]
    write_tsv(slice_dir / "rows.tsv", rows)
    write_report(slice_dir / "report.md", summary, rows)
    (slice_dir / "metrics.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "id": slice_spec["id"],
        "label": slice_spec["label"],
        "group": slice_spec["group"],
        "split": slice_spec["split"],
        "source": "live_api",
        "path": rel_path(query_path),
        "rows_path": rel_path(slice_dir / "rows.tsv"),
        "metrics_path": rel_path(slice_dir / "metrics.json"),
        "report_path": rel_path(slice_dir / "report.md"),
        "payloads_path": rel_path(payload_dir),
        "summary": summary,
        "missing_examples": missing_examples(rows),
    }


def result_for_slice(report: dict, slice_id: str) -> dict:
    for slice_report in report.get("slices") or []:
        if slice_report.get("id") == slice_id:
            return dict(slice_report.get("result") or {})
    return {}


def diagnostic_slice_from_locked_report(slice_spec: dict, locked_report: dict) -> dict:
    return {
        "id": slice_spec["id"],
        "label": slice_spec["label"],
        "group": slice_spec["group"],
        "split": slice_spec["split"],
        "source": "captured_locked_report",
        "path": slice_spec.get("result_path", ""),
        "summary": result_for_slice(locked_report, slice_spec["id"]),
    }


def table_line(cells: list[object]) -> str:
    return "| " + " | ".join(str(cell) for cell in cells) + " |"


def quality_summary_cells(slice_result: dict) -> list[str]:
    summary = slice_result.get("summary") or {}
    rows = int(summary.get("paragraphs") or summary.get("rows") or 0)
    expected = int(summary.get("expected_concepts") or 0)
    all_10 = int(summary.get("queries_all_expected_at_10") or 0)
    missing_10 = int(summary.get("queries_with_missing_at_10") or max(rows - all_10, 0))
    disallowed_10 = int(summary.get("queries_with_disallowed_at_10") or 0)
    recall = summary.get("recall_at_10")
    return [
        f"{all_10}/{rows} ({pct_count(all_10, rows)})",
        f"{pct(recall)} ({expected} expected IDs)",
        str(missing_10),
        str(disallowed_10),
    ]


def render_markdown(comparison: dict) -> str:
    lines = [
        "# Gold Standard Comparison",
        "",
        f"Generated: {comparison['created_at']}",
        f"Live API: `{comparison['base_url']}`",
        f"Locked benchmark: `{comparison['lock_path']}`",
        "",
        "This compares current search output against locked expected CUI sets. A row is complete when every expected CUI, or an accepted alternative, appears in the first 10 answers.",
        "",
        "## Current Live Results",
        "",
        table_line(["Slice", "Complete rows at 10", "Expected ID recall at 10", "Rows missing IDs", "Known false positives"]),
        table_line(["---", "---:", "---:", "---:", "---:"]),
    ]
    for slice_result in comparison["live_slices"]:
        lines.append(table_line([slice_result["label"], *quality_summary_cells(slice_result)]))

    lines.extend(["", "## Captured Diagnostic Slices", ""])
    exact = next((item for item in comparison["diagnostic_slices"] if item["id"] == "exact_umls_api_comparison"), None)
    if exact:
        variants = (exact.get("summary") or {}).get("variants") or []
        if variants:
            lines.append(
                "- Short exact phrase comparison: "
                f"local search found the expected ID {variants[0]['local_expected_top10']}/{variants[0]['expected_rows']} times; "
                f"official UMLS found it {variants[0]['umls_expected_top10']}/{variants[0]['expected_rows']} times."
            )
    code = next((item for item in comparison["diagnostic_slices"] if item["id"] == "code_coverage"), None)
    if code:
        summary = code.get("summary") or {}
        if summary.get("exists"):
            lines.append(
                "- Code coverage: "
                f"{summary['rows_complete']}/{summary['rows_total']} concepts had all expected code systems; "
                f"{summary['found_sabs_total']}/{summary['expected_sabs_total']} expected code links were present."
            )

    lines.extend(["", "## First Misses To Inspect", ""])
    any_examples = False
    for slice_result in comparison["live_slices"]:
        examples = slice_result.get("missing_examples") or []
        if not examples:
            continue
        any_examples = True
        lines.append(f"### {slice_result['label']}")
        for example in examples[:6]:
            lines.append(
                f"- `{example['id']}` missing `{example['missing_at_10']}`; "
                f"top answer was `{example['top_cui']}` {example['top_name']}"
            )
        lines.append("")
    if not any_examples:
        lines.append("- No top-10 misses in the live slices that were run.")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Clinical smoke checks whether recent clinical examples still work.",
            "- PubMed checks whether longer biomedical text still returns secondary concepts, treatments, outcomes, genes, and study entities.",
            "- Exact/UMLS checks short phrase lookup against official UMLS search behavior.",
            "- Code coverage checks whether found CUIs also expose expected standard vocabulary mappings.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_latest_copy(source: Path, latest: Path) -> None:
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare the current search API against the locked translation gold-standard slices."
    )
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--base-url", default="http://127.0.0.1:8766")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--top-k", type=int, default=60)
    parser.add_argument("--mode", choices=["balanced", "exact"], default="balanced")
    parser.add_argument("--scope", choices=["umls", "umls_evidence"], default="umls_evidence")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument(
        "--slice",
        action="append",
        dest="slices",
        help="Slice id to run live. Defaults to clinical_smoke and the PubMed dev/locked slices.",
    )
    parser.add_argument(
        "--limit-per-slice",
        type=int,
        default=0,
        help="Optional row limit for a quick starter run. Default 0 means run each selected slice fully.",
    )
    parser.add_argument("--alternatives", type=Path, default=DEFAULT_ACCEPTABLE_ALTERNATIVES)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    lock = load_lock(args.lock)
    locked_report = build_report(lock)
    selected_ids = set(args.slices or DEFAULT_LIVE_SLICES)
    selected_slices = [
        slice_spec
        for slice_spec in lock["slices"]
        if slice_spec["id"] in selected_ids and slice_spec["group"] in {"clinical", "pubmed"}
    ]
    missing_selected = selected_ids - {slice_spec["id"] for slice_spec in selected_slices}
    if missing_selected:
        raise SystemExit(f"unknown or non-live slice ids: {', '.join(sorted(missing_selected))}")

    created_at = utc_timestamp()
    run_id = run_id_from_timestamp(created_at)
    output_dir = args.output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    alternatives = read_acceptable_alternatives(args.alternatives)

    live_slices = [
        run_live_quality_slice(
            slice_spec,
            base_url=args.base_url,
            top_k=args.top_k,
            mode=args.mode,
            scope=args.scope,
            timeout=args.timeout,
            limit=args.limit_per_slice,
            output_dir=output_dir,
            alternatives=alternatives,
            verbose=args.verbose,
        )
        for slice_spec in selected_slices
    ]
    diagnostic_slices = [
        diagnostic_slice_from_locked_report(slice_spec, locked_report)
        for slice_spec in lock["slices"]
        if slice_spec["group"] in {"exact_umls", "code"}
    ]
    comparison = {
        "id": run_id,
        "created_at": created_at,
        "base_url": args.base_url,
        "mode": args.mode,
        "scope": args.scope,
        "top_k": args.top_k,
        "lock_path": rel_path(repo_path(args.lock)),
        "lock_status": [file_lock_status(slice_spec) for slice_spec in lock["slices"]],
        "live_slices": live_slices,
        "diagnostic_slices": diagnostic_slices,
    }

    json_path = output_dir / "gold_standard_comparison.json"
    md_path = output_dir / "gold_standard_comparison.md"
    json_path.write_text(json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(comparison), encoding="utf-8")
    write_latest_copy(json_path, args.output_root / "latest.json")
    write_latest_copy(md_path, args.output_root / "latest.md")
    print(f"Wrote {rel_path(md_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
