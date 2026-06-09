#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import html
import json
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = ROOT / "config" / "translation_benchmark_lock.json"


def repo_path(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def rel_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def split_pipe(value: object) -> list[str]:
    return [part.strip() for part in str(value or "").split("|") if part.strip()]


def count_expected_cuis(rows: list[dict[str, str]]) -> int:
    return sum(len(split_pipe(row.get("expected_cuis"))) for row in rows)


def count_expected_code_sabs(rows: list[dict[str, str]]) -> int:
    return sum(len(split_pipe(row.get("expected_code_sabs"))) for row in rows)


def pct(numerator: float | int | None, denominator: float | int | None) -> str:
    if numerator is None or denominator in (None, 0):
        return "n/a"
    return f"{100.0 * float(numerator) / float(denominator):.1f}%"


def fmt_float(value: object, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def load_lock(path: Path = DEFAULT_LOCK) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_lock_status(slice_spec: dict[str, Any]) -> dict[str, Any]:
    path = repo_path(slice_spec["path"])
    rows = read_tsv(path)
    status = {
        "path": rel_path(path),
        "exists": path.exists(),
        "locked_rows": slice_spec.get("rows"),
        "actual_rows": len(rows) if path.exists() else None,
        "locked_expected_cuis": slice_spec.get("expected_cuis"),
        "actual_expected_cuis": count_expected_cuis(rows) if path.exists() else None,
        "locked_expected_code_sabs": slice_spec.get("expected_code_sabs"),
        "actual_expected_code_sabs": count_expected_code_sabs(rows) if path.exists() else None,
        "locked_sha256": slice_spec.get("sha256"),
        "actual_sha256": sha256_file(path) if path.exists() else None,
    }
    status["matches"] = bool(
        status["exists"]
        and status["actual_rows"] == status["locked_rows"]
        and status["actual_expected_cuis"] == status["locked_expected_cuis"]
        and (
            status["locked_expected_code_sabs"] is None
            or status["actual_expected_code_sabs"] == status["locked_expected_code_sabs"]
        )
        and status["actual_sha256"] == status["locked_sha256"]
    )
    return status


def summarize_quality_run(run_path_value: str | None) -> dict[str, Any] | None:
    if not run_path_value:
        return None
    run_path = repo_path(run_path_value)
    metrics_path = run_path / "metrics.json"
    summary_path = run_path / "paragraph_quality_summary.tsv"
    if not metrics_path.exists() and not summary_path.exists():
        return {"exists": False, "path": rel_path(run_path)}

    metrics: dict[str, Any] = {}
    if metrics_path.exists():
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))

    rows = read_tsv(summary_path)
    strict_success = sum(1 for row in rows if row.get("strict_success_at_10") == "1")
    missing_rows = [row for row in rows if row.get("missing_at_10")]
    disallowed_rows = [row for row in rows if row.get("disallowed_at_10")]
    result = {
        "exists": True,
        "path": rel_path(run_path),
        "rows": int(metrics.get("paragraphs") or len(rows) or 0),
        "expected_concepts": int(metrics.get("expected_concepts") or 0),
        "score": metrics.get("overall_score"),
        "queries_all_expected_at_10": int(metrics.get("queries_all_expected_at_10") or 0),
        "queries_with_missing_at_10": int(metrics.get("queries_with_missing_at_10") or len(missing_rows)),
        "queries_with_disallowed_at_10": int(
            metrics.get("queries_with_disallowed_at_10") or len(disallowed_rows)
        ),
        "recall_at_10": metrics.get("recall_at_10"),
        "mean_coverage_at_10": metrics.get("mean_coverage_at_10"),
        "all_expected_at_10_rate": metrics.get("all_expected_at_10_rate"),
        "strict_success_at_10": strict_success,
        "missing_examples": [
            {
                "id": row.get("id", ""),
                "missing_at_10": row.get("missing_at_10", ""),
                "top_cui": row.get("top_cui", ""),
                "top_name": row.get("top_name", ""),
            }
            for row in missing_rows[:8]
        ],
    }
    return result


def summarize_umls_comparison(summary_path_value: str | None) -> dict[str, Any] | None:
    if not summary_path_value:
        return None
    summary_path = repo_path(summary_path_value)
    if not summary_path.exists():
        return {"exists": False, "path": rel_path(summary_path)}
    rows = read_tsv(summary_path)
    variants = []
    for row in rows:
        expected_rows = int(row.get("expected_rows") or 0)
        local_expected = int(row.get("expected_in_local_top10") or 0)
        umls_expected = int(row.get("expected_in_umls_top10") or 0)
        variants.append(
            {
                "variant": row.get("variant", ""),
                "label": row.get("label", ""),
                "rows": int(row.get("rows") or 0),
                "expected_rows": expected_rows,
                "local_expected_top10": local_expected,
                "umls_expected_top10": umls_expected,
                "local_expected_top10_rate": (
                    local_expected / expected_rows if expected_rows else None
                ),
                "umls_expected_top10_rate": (
                    umls_expected / expected_rows if expected_rows else None
                ),
                "local_top_equals_umls_top": int(row.get("local_top_equals_umls_top") or 0),
                "mean_overlap_at10": row.get("mean_overlap_at10"),
                "output": row.get("output", ""),
            }
        )
    return {"exists": True, "path": rel_path(summary_path), "variants": variants}


def available_sabs_for_cui(conn: sqlite3.Connection, cui: str) -> set[str]:
    rows = conn.execute(
        """
        select distinct sab
        from code_mappings
        where cui = ? and suppress != 'O'
        """,
        (cui,),
    ).fetchall()
    return {str(row[0] or "") for row in rows if row[0]}


def summarize_code_coverage(query_path_value: str, code_index_value: str | None) -> dict[str, Any]:
    query_path = repo_path(query_path_value)
    rows = read_tsv(query_path)
    code_index = repo_path(code_index_value or "build/cui_code_index.sqlite")
    if not code_index.exists():
        return {"exists": False, "path": rel_path(code_index), "rows": []}

    conn = sqlite3.connect(code_index)
    details = []
    expected_sabs_total = 0
    found_sabs_total = 0
    rows_complete = 0
    try:
        for row in rows:
            expected_cuis = split_pipe(row.get("expected_cuis"))
            expected_sabs = split_pipe(row.get("expected_code_sabs"))
            expected_sabs_total += len(expected_sabs)
            found_sabs: set[str] = set()
            available_sabs: set[str] = set()
            for cui in expected_cuis:
                available_sabs.update(available_sabs_for_cui(conn, cui))
            for sab in expected_sabs:
                if sab in available_sabs:
                    found_sabs.add(sab)
            found_sabs_total += len(found_sabs)
            complete = set(expected_sabs).issubset(found_sabs)
            rows_complete += 1 if complete else 0
            details.append(
                {
                    "id": row.get("id", ""),
                    "query": row.get("query", ""),
                    "expected_cuis": "|".join(expected_cuis),
                    "expected_sabs": "|".join(expected_sabs),
                    "found_sabs": "|".join(sorted(found_sabs)),
                    "missing_sabs": "|".join(
                        sab for sab in expected_sabs if sab not in found_sabs
                    ),
                    "complete": complete,
                }
            )
    finally:
        conn.close()

    return {
        "exists": True,
        "path": rel_path(code_index),
        "rows": details,
        "rows_complete": rows_complete,
        "rows_total": len(details),
        "expected_sabs_total": expected_sabs_total,
        "found_sabs_total": found_sabs_total,
    }


def build_report(lock: dict[str, Any]) -> dict[str, Any]:
    slice_reports = []
    for slice_spec in lock["slices"]:
        file_status = file_lock_status(slice_spec)
        result: dict[str, Any] | None = None
        if slice_spec["group"] in {"clinical", "pubmed"}:
            result = summarize_quality_run(slice_spec.get("result_path"))
        elif slice_spec["group"] == "exact_umls":
            result = summarize_umls_comparison(slice_spec.get("result_path"))
        elif slice_spec["group"] == "code":
            result = summarize_code_coverage(slice_spec["path"], slice_spec.get("result_path"))
        slice_reports.append(
            {
                "id": slice_spec["id"],
                "label": slice_spec["label"],
                "group": slice_spec["group"],
                "split": slice_spec["split"],
                "file": file_status,
                "result": result,
            }
        )
    return {
        "id": lock["id"],
        "locked_at": lock["locked_at"],
        "purpose": lock.get("purpose", ""),
        "smoke_regression": lock.get("smoke_regression", {}),
        "slices": slice_reports,
    }


def h(value: object) -> str:
    return html.escape(str(value if value is not None else ""))


def lock_status_text(file_status: dict[str, Any]) -> str:
    if not file_status["exists"]:
        return "missing"
    return "locked" if file_status["matches"] else "changed"


def quality_result_text(result: dict[str, Any] | None) -> str:
    if not result:
        return "n/a"
    if not result.get("exists"):
        return "result missing"
    all_expected = result.get("queries_all_expected_at_10")
    rows = result.get("rows")
    recall = result.get("recall_at_10")
    score = result.get("score")
    return (
        f"{all_expected}/{rows} rows found every expected ID in the first 10 answers "
        f"({pct(all_expected, rows)}); {fmt_float(float(recall) * 100 if recall is not None else None, 1)}% of expected IDs found; "
        f"score {fmt_float(score, 1)}"
    )


def exact_result_text(result: dict[str, Any] | None) -> str:
    if not result:
        return "n/a"
    if not result.get("exists"):
        return "result missing"
    variants = result.get("variants") or []
    if not variants:
        return "no variants"
    first = variants[0]
    return (
        f"our search found the expected ID {first['local_expected_top10']}/{first['expected_rows']} times "
        f"({pct(first['local_expected_top10'], first['expected_rows'])}); "
        f"official UMLS found it {first['umls_expected_top10']}/{first['expected_rows']} times "
        f"({pct(first['umls_expected_top10'], first['expected_rows'])})"
    )


def code_result_text(result: dict[str, Any] | None) -> str:
    if not result:
        return "n/a"
    if not result.get("exists"):
        return "code index missing"
    return (
        f"{result['rows_complete']}/{result['rows_total']} concepts had all expected code types; "
        f"{result['found_sabs_total']}/{result['expected_sabs_total']} expected code links found"
    )


def result_for_slice(report: dict[str, Any], slice_id: str) -> dict[str, Any]:
    for slice_report in report.get("slices") or []:
        if slice_report.get("id") == slice_id:
            return dict(slice_report.get("result") or {})
    return {}


def render_plain_explanation(report: dict[str, Any]) -> str:
    clinical = result_for_slice(report, "clinical_smoke")
    pubmed_dev = result_for_slice(report, "pubmed_literature_dev")
    pubmed_heldout = result_for_slice(report, "pubmed_literature_heldout")
    exact = result_for_slice(report, "exact_umls_api_comparison")
    code = result_for_slice(report, "code_coverage")
    exact_variants = list(exact.get("variants") or [])
    exact_default = exact_variants[0] if exact_variants else {}
    return f"""
  <section class="plain-explanation">
    <h2>Plain-Language Read</h2>
    <p>Each check starts with medical text and a list of IDs that should be found. A row passes when those expected IDs appear in the first 10 answers.</p>
    <ul>
      <li><strong>Clinical examples:</strong> {h(clinical.get('queries_all_expected_at_10'))} of {h(clinical.get('rows'))} found every expected ID. This says the clinical-note examples are mostly working.</li>
      <li><strong>PubMed abstracts:</strong> {h(pubmed_dev.get('queries_all_expected_at_10'))} of {h(pubmed_dev.get('rows'))} practice abstracts and {h(pubmed_heldout.get('queries_all_expected_at_10'))} of {h(pubmed_heldout.get('rows'))} locked abstracts found every expected ID. This is the weakest area.</li>
      <li><strong>Official UMLS comparison:</strong> For short phrases, our search found the expected ID {h(exact_default.get('local_expected_top10'))} of {h(exact_default.get('expected_rows'))} times. The official UMLS search found it {h(exact_default.get('umls_expected_top10'))} of {h(exact_default.get('expected_rows'))} times.</li>
      <li><strong>Code mappings:</strong> {h(code.get('rows_complete'))} of {h(code.get('rows_total'))} concepts had all expected code types, and {h(code.get('found_sabs_total'))} of {h(code.get('expected_sabs_total'))} expected links to SNOMED CT, RxNorm, LOINC, or ICD-10-CM were present.</li>
    </ul>
  </section>
    """


def overview_result_text(slice_report: dict[str, Any]) -> str:
    group = slice_report["group"]
    result = slice_report.get("result")
    if group in {"clinical", "pubmed"}:
        return quality_result_text(result)
    if group == "exact_umls":
        return exact_result_text(result)
    if group == "code":
        return code_result_text(result)
    return "n/a"


def render_overview_table(report: dict[str, Any]) -> str:
    rows = []
    for slice_report in report["slices"]:
        file_status = slice_report["file"]
        rows.append(
            "<tr>"
            f"<td>{h(slice_report['label'])}</td>"
            f"<td>{h(slice_report['split'])}</td>"
            f"<td>{h(file_status['actual_rows'])}</td>"
            f"<td>{h(file_status['actual_expected_cuis'])}</td>"
            f"<td><span class=\"status {h(lock_status_text(file_status))}\">{h(lock_status_text(file_status))}</span></td>"
            f"<td>{h(overview_result_text(slice_report))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_quality_detail(slice_report: dict[str, Any]) -> str:
    result = slice_report.get("result") or {}
    if not result.get("exists"):
        return f"<p class=\"muted\">No captured result at <code>{h(result.get('path', ''))}</code>.</p>"
    examples = result.get("missing_examples") or []
    example_rows = "\n".join(
        "<tr>"
        f"<td>{h(example['id'])}</td>"
        f"<td>{h(example['missing_at_10'])}</td>"
        f"<td>{h(example['top_cui'])}</td>"
        f"<td>{h(example['top_name'])}</td>"
        "</tr>"
        for example in examples
    )
    examples_html = (
        "<table><thead><tr><th>Row</th><th>Missing at top 10</th><th>Top CUI</th><th>Top name</th></tr></thead>"
        f"<tbody>{example_rows}</tbody></table>"
        if examples
        else "<p class=\"muted\">No top-10 missing examples in this captured run.</p>"
    )
    return f"""
    <div class="metric-grid">
      <div><strong>{h(result.get('queries_all_expected_at_10'))}/{h(result.get('rows'))}</strong><span>rows where every expected ID was in the first 10 answers</span></div>
      <div><strong>{h(fmt_float(float(result.get('recall_at_10')) * 100 if result.get('recall_at_10') is not None else None, 1))}%</strong><span>expected IDs found in the first 10 answers</span></div>
      <div><strong>{h(result.get('queries_with_missing_at_10'))}</strong><span>rows missing at least one expected ID</span></div>
      <div><strong>{h(fmt_float(result.get('score'), 1))}</strong><span>overall score</span></div>
    </div>
    {examples_html}
    """


def render_exact_detail(slice_report: dict[str, Any]) -> str:
    result = slice_report.get("result") or {}
    if not result.get("exists"):
        return f"<p class=\"muted\">No UMLS comparison summary at <code>{h(result.get('path', ''))}</code>.</p>"
    rows = []
    for variant in result.get("variants") or []:
        rows.append(
            "<tr>"
            f"<td>{h(variant['label'])}</td>"
            f"<td>{h(variant['rows'])}</td>"
            f"<td>{h(variant['local_expected_top10'])}/{h(variant['expected_rows'])} ({h(pct(variant['local_expected_top10'], variant['expected_rows']))})</td>"
            f"<td>{h(variant['umls_expected_top10'])}/{h(variant['expected_rows'])} ({h(pct(variant['umls_expected_top10'], variant['expected_rows']))})</td>"
            f"<td>{h(variant['local_top_equals_umls_top'])}/{h(variant['rows'])}</td>"
            f"<td>{h(variant['mean_overlap_at10'])}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Run</th><th>Rows</th><th>Our search found expected ID</th>"
        "<th>Official UMLS found expected ID</th><th>Same first answer</th><th>Shared first-10 answers</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_code_detail(slice_report: dict[str, Any]) -> str:
    result = slice_report.get("result") or {}
    if not result.get("exists"):
        return f"<p class=\"muted\">No code index at <code>{h(result.get('path', ''))}</code>.</p>"
    rows = []
    for row in result.get("rows") or []:
        rows.append(
            "<tr>"
            f"<td>{h(row['id'])}</td>"
            f"<td>{h(row['expected_cuis'])}</td>"
            f"<td>{h(row['expected_sabs'])}</td>"
            f"<td>{h(row['found_sabs'])}</td>"
            f"<td>{h(row['missing_sabs'])}</td>"
            "</tr>"
        )
    return (
        f"<p>{h(code_result_text(result))}.</p>"
        "<table><thead><tr><th>Row</th><th>ID</th><th>Expected code systems</th><th>Found</th><th>Missing</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_details(report: dict[str, Any]) -> str:
    parts = []
    for slice_report in report["slices"]:
        group = slice_report["group"]
        if group in {"clinical", "pubmed"}:
            body = render_quality_detail(slice_report)
        elif group == "exact_umls":
            body = render_exact_detail(slice_report)
        elif group == "code":
            body = render_code_detail(slice_report)
        else:
            body = ""
        parts.append(f"<section><h2>{h(slice_report['label'])}</h2>{body}</section>")
    return "\n".join(parts)


def render_html(report: dict[str, Any]) -> str:
    generated = "2026-06-09"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Translation Benchmark Report</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #1b2430;
      --muted: #637083;
      --line: #d9e0e8;
      --panel: #f6f8fb;
      --ok: #0f7a3f;
      --warn: #a15c00;
      --bad: #a32929;
    }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: #fff;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 32px 24px 56px;
    }}
    h1, h2 {{
      margin: 0;
      letter-spacing: 0;
    }}
    h1 {{
      font-size: 30px;
      line-height: 1.15;
    }}
    h2 {{
      font-size: 19px;
      margin-top: 34px;
      margin-bottom: 12px;
    }}
    p {{
      line-height: 1.5;
    }}
    .muted {{
      color: var(--muted);
    }}
    code {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 4px;
      padding: 1px 4px;
      font-size: 0.92em;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      margin: 12px 0 22px;
      font-size: 14px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 9px 8px;
      vertical-align: top;
      text-align: left;
      overflow-wrap: anywhere;
    }}
    th {{
      color: #344154;
      font-size: 12px;
      text-transform: uppercase;
      background: var(--panel);
    }}
    .status {{
      display: inline-block;
      border-radius: 4px;
      padding: 2px 7px;
      font-weight: 650;
    }}
    .status.locked {{
      color: var(--ok);
      background: #e8f5ed;
    }}
    .status.changed, .status.missing {{
      color: var(--bad);
      background: #fdeaea;
    }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px;
      margin: 10px 0 16px;
    }}
    .metric-grid > div {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px;
    }}
    .metric-grid strong {{
      display: block;
      font-size: 20px;
      margin-bottom: 4px;
    }}
    .metric-grid span {{
      color: var(--muted);
      font-size: 13px;
    }}
    ul {{
      padding-left: 20px;
      line-height: 1.45;
    }}
    .plain-explanation {{
      background: #f8fafc;
      border: 1px solid var(--line);
      border-radius: 8px;
      margin: 14px 0;
      padding: 14px;
    }}
    .plain-explanation h2 {{
      margin-top: 0;
    }}
    .plain-explanation p,
    .plain-explanation li {{
      max-width: 980px;
    }}
  </style>
</head>
<body>
<main>
  <h1>Translation Benchmark Report</h1>
  <p class="muted">Generated {h(generated)} from <code>config/translation_benchmark_lock.json</code>. The lock date is {h(report['locked_at'])}.</p>
  <p>{h(report['purpose'])}</p>

  {render_plain_explanation(report)}

  <h2>Overview</h2>
  <table>
    <thead>
      <tr>
        <th>Benchmark part</th>
        <th>Split</th>
        <th>Rows</th>
        <th>Expected CUIs</th>
        <th>Input lock</th>
        <th>Captured outcome</th>
      </tr>
    </thead>
    <tbody>
      {render_overview_table(report)}
    </tbody>
  </table>

  {render_details(report)}

  <section>
    <h2>Failure-Driven Work Queue</h2>
    <ul>
      <li>Use the PubMed dev failures for tuning and keep the PubMed held-out rows untouched for final checks.</li>
      <li>Validate the new long-literature path that chunks abstracts into title, background, methods, results, and conclusion spans, then aggregates concepts across chunks.</li>
      <li>Tune the span-level support score separately from ranked hits so treatments, outcomes, genes, organisms, and study entities are not lost behind the main topic.</li>
      <li>Improve exact-label ranking where the local result chooses a broad parent over the exact UMLS concept.</li>
      <li>Make code mapping coverage part of translation output checks, separate from whether the CUI ranked highly.</li>
    </ul>
  </section>
</main>
</body>
</html>
"""


def write_report(report: dict[str, Any], lock: dict[str, Any]) -> None:
    report_paths = lock.get("report", {})
    json_path = repo_path(report_paths.get("json", "build/translation_benchmark_report.json"))
    html_path = repo_path(report_paths.get("html", "docs/translation_benchmark_report.html"))
    json_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")


def main() -> int:
    lock = load_lock()
    report = build_report(lock)
    write_report(report, lock)
    html_path = repo_path(lock.get("report", {}).get("html", "docs/translation_benchmark_report.html"))
    print(f"Wrote {rel_path(html_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
