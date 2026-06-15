#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "search_quality_test_runs.html"
EXPERIMENT_RUNS = ROOT / "build" / "search_quality_experiments" / "runs"
SUITE_RUNS = ROOT / "build" / "search_quality_suite"
MEDMENTIONS_ROOT = ROOT / "build" / "medmentions"
INACTIVE_SUITE_LAYER_IDS = {"evidence_provenance"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def repo_path(path: str | Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except Exception:
        return str(path)


def html_escape(value: object) -> str:
    text = str(value if value is not None else "")
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def compact_label(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text or "Unnamed test"


def timestamp_from_path(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def score_class(rate: float | None, *, gate_failed: bool = False, wrong: int = 0) -> str:
    if gate_failed:
        return "bad"
    if rate is None:
        return "neutral"
    if rate >= 0.95 and wrong == 0:
        return "good"
    if rate >= 0.75:
        return "warn"
    return "bad"


def experiment_test_name(run: dict[str, Any]) -> str:
    query_file = Path(str(run.get("queries") or "")).name
    family = str(run.get("run_family") or "")
    label = compact_label(run.get("label"))
    limit = int(run.get("query_limit") or 0)
    if query_file == "search_quality_paragraph_queries.tsv" and limit == 0:
        return "Full Clinical Benchmark"
    if query_file == "search_quality_paragraph_queries.tsv" and (limit == 50 or family == "smoke"):
        return "Cycling Clinical Sample"
    if query_file == "search_quality_patient_portal_queries.tsv" or family == "patient_portal":
        return "Patient Message Intent"
    if query_file == "pubmed_literature_approved_queries.tsv":
        return "PubMed Approved Abstracts"
    if query_file == "pubmed_long_document_focused_queries.tsv":
        return "Focused PubMed Abstracts"
    if query_file == "search_quality_real_query_regression.tsv":
        return "Real Short Queries"
    if query_file == "search_quality_source_specific_queries.tsv":
        return "Source-Specific Evidence"
    if "rotating" in label.lower() and "50" in label:
        return "Cycling Clinical Sample"
    if "patient portal" in label.lower():
        return "Patient Message Intent"
    if "pubmed" in label.lower() and "focused" in label.lower():
        return "Focused PubMed Abstracts"
    if "pubmed" in label.lower():
        return "PubMed Probe"
    return label


def experiment_row(run_json: Path) -> dict[str, Any] | None:
    run = load_json(run_json)
    metrics_path = Path(str(run.get("metrics_path") or run_json.with_name("metrics.json")))
    if not metrics_path.is_absolute():
        metrics_path = ROOT / metrics_path
    summary = dict(run.get("summary") or {})
    if metrics_path.exists():
        summary.update(load_json(metrics_path))
    created = str(run.get("created_at") or timestamp_from_path(run_json))
    test_name = experiment_test_name(run)
    examples = int(summary.get("paragraphs") or summary.get("queries") or 0)
    all_expected = int(summary.get("queries_all_expected_at_10") or 0)
    if test_name == "Patient Message Intent":
        all_expected = int(summary.get("top_on_target_count") or all_expected)
    expected = int(summary.get("expected_concepts") or 0)
    found = int(summary.get("found_at_10") or 0)
    wrong = int(summary.get("top_wrong_count") or 0)
    missing = int(summary.get("queries_with_missing_at_10") or max(examples - all_expected, 0))
    rate = (all_expected / examples) if examples else None
    gate_result = run.get("gate_result") or {}
    gate_failed = gate_result.get("passed") is False
    status = score_class(rate, gate_failed=gate_failed, wrong=wrong)
    if gate_failed:
        status_text = "Failed"
    elif status == "good":
        status_text = "Passed"
    elif status == "warn":
        status_text = "Warn"
    elif status == "bad":
        status_text = "Failed"
    else:
        status_text = "Unknown"
    score = f"{all_expected}/{examples}" if examples else ""
    detail_parts = []
    if expected:
        detail_parts.append(f"{found}/{expected} expected at top 10")
    if missing:
        detail_parts.append(f"{missing} missing")
    if wrong:
        detail_parts.append(f"{wrong} wrong-first")
    if gate_failed:
        detail_parts.append("gate failed")
    return {
        "time": created,
        "test": test_name,
        "status": status,
        "statusText": status_text,
        "score": score,
        "detail": "; ".join(detail_parts),
        "duration": float(summary.get("elapsed_seconds") or 0.0),
        "artifact": repo_path(run_json),
        "kind": "experiment",
    }


def command_score(stdout_path: Path | None) -> str:
    if not stdout_path or not stdout_path.exists():
        return ""
    text = stdout_path.read_text(encoding="utf-8", errors="replace")
    matches = re.findall(r"(\d+ failed, \d+ passed|\d+ passed|\d+ failed)", text)
    return matches[-1] if matches else ""


def suite_rows(suite_json: Path) -> list[dict[str, Any]]:
    suite = load_json(suite_json)
    if suite.get("dry_run"):
        return []
    created = str(suite.get("created_at") or timestamp_from_path(suite_json))
    rows = []
    for layer in suite.get("layers") or []:
        if str(layer.get("id") or "") in INACTIVE_SUITE_LAYER_IDS:
            continue
        status_raw = str(layer.get("status") or "unknown")
        if status_raw == "passed":
            status = "good"
            status_text = "Passed"
        elif status_raw == "known_weakness":
            status = "bad"
            status_text = "Known weakness"
        elif status_raw == "failed":
            status = "bad"
            status_text = "Failed"
        else:
            status = "neutral"
            status_text = status_raw.title()
        stdout = layer.get("stdout_path")
        stdout_path = ROOT / stdout if stdout else None
        score = command_score(stdout_path)
        rows.append(
            {
                "time": created,
                "test": compact_label(layer.get("role") or layer.get("id")),
                "status": status,
                "statusText": status_text,
                "score": score,
                "detail": compact_label(layer.get("id")),
                "duration": 0.0,
                "artifact": repo_path(suite_json),
                "kind": "suite",
            }
        )
    return rows


def medmentions_rows() -> list[dict[str, Any]]:
    rows = []
    for summary_path in sorted(MEDMENTIONS_ROOT.glob("**/summary.json")):
        summary = load_json(summary_path)
        queries = int(summary.get("queries") or 0)
        if not queries:
            continue
        rate = float(summary.get("top10_accuracy") or summary.get("top10_hit_rate") or 0.0)
        status = score_class(rate)
        label = "MedMentions"
        path_text = str(summary_path)
        if "suppression" in path_text:
            label = "MedMentions Suppression Audit"
        elif "clinical_useful" in path_text:
            label = "MedMentions Clinical Useful"
        rows.append(
            {
                "time": timestamp_from_path(summary_path),
                "test": label,
                "status": status,
                "statusText": "Passed" if status == "good" else ("Warn" if status == "warn" else "Failed"),
                "score": f"{rate:.0%}",
                "detail": f"{queries} queries; top10 accuracy",
                "duration": float(summary.get("mean_elapsed_ms") or 0.0) / 1000.0,
                "artifact": repo_path(summary_path),
                "kind": "external",
            }
        )
    return rows


def collect_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run_json in sorted(EXPERIMENT_RUNS.glob("*/run.json")):
        row = experiment_row(run_json)
        if row:
            rows.append(row)
    for suite_json in sorted(SUITE_RUNS.glob("*/suite.json")):
        rows.extend(suite_rows(suite_json))
    rows.extend(medmentions_rows())
    return sorted(rows, key=lambda item: str(item["time"]), reverse=True)


def build_html(rows: list[dict[str, Any]]) -> str:
    data_json = json.dumps(rows, ensure_ascii=False, sort_keys=True)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Search Test Runs</title>
  <style>
    :root {{
      --bg: #f6f8fb;
      --panel: #fff;
      --ink: #17202a;
      --muted: #5b6673;
      --line: #d7dee8;
      --good: #166534;
      --good-bg: #ecfdf3;
      --good-line: #bbf7d0;
      --warn: #9a5b05;
      --warn-bg: #fffbeb;
      --warn-line: #fde68a;
      --bad: #b42318;
      --bad-bg: #fef2f2;
      --bad-line: #fecaca;
      --neutral: #475569;
      --neutral-bg: #f8fafc;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 14px;
      line-height: 1.35;
    }}
    header {{
      background: var(--panel);
      border-bottom: 1px solid var(--line);
    }}
    .wrap, main {{
      width: min(1440px, calc(100vw - 32px));
      margin: 0 auto;
    }}
    .topbar {{
      align-items: center;
      display: flex;
      gap: 16px;
      justify-content: space-between;
      padding: 18px 0;
    }}
    h1 {{
      font-size: 24px;
      letter-spacing: 0;
      margin: 0;
    }}
    main {{ padding: 16px 0 42px; }}
    a {{ color: #2457c5; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .nav {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
    }}
    .nav a, .filter button {{
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 999px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 760;
      min-height: 28px;
      padding: 5px 9px;
    }}
    .filter button {{ cursor: pointer; }}
    .filter button.active {{ border-color: #2457c5; color: #2457c5; }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      margin-bottom: 14px;
      padding: 14px;
    }}
    .toolbar {{
      align-items: center;
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      justify-content: space-between;
    }}
    .filter {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}
    .legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 720;
    }}
    .key {{
      align-items: center;
      display: inline-flex;
      gap: 5px;
    }}
    .dot {{
      border-radius: 999px;
      display: inline-block;
      height: 11px;
      width: 11px;
    }}
    .good {{ background: var(--good-bg); border-color: var(--good-line); color: var(--good); }}
    .warn {{ background: var(--warn-bg); border-color: var(--warn-line); color: var(--warn); }}
    .bad {{ background: var(--bad-bg); border-color: var(--bad-line); color: var(--bad); }}
    .neutral {{ background: var(--neutral-bg); border-color: var(--line); color: var(--neutral); }}
    .dot.good {{ background: #16a34a; }}
    .dot.warn {{ background: #f59e0b; }}
    .dot.bad {{ background: #ef4444; }}
    .dot.neutral {{ background: #94a3b8; }}
    .grid {{
      display: grid;
      gap: 8px;
    }}
    .lane {{
      align-items: center;
      display: grid;
      grid-template-columns: minmax(220px, 320px) minmax(0, 1fr);
      gap: 12px;
      min-height: 34px;
    }}
    .lane-name {{
      color: var(--ink);
      font-size: 13px;
      font-weight: 780;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .lane-dots {{
      align-items: center;
      display: flex;
      gap: 5px;
      min-height: 24px;
      overflow-x: auto;
      padding-bottom: 2px;
    }}
    .run-dot {{
      border: 1px solid rgba(0,0,0,0.12);
      border-radius: 4px;
      display: inline-block;
      flex: 0 0 auto;
      height: 18px;
      width: 18px;
    }}
    .run-dot.good {{ background: #22c55e; }}
    .run-dot.warn {{ background: #f59e0b; }}
    .run-dot.bad {{ background: #ef4444; }}
    .run-dot.neutral {{ background: #94a3b8; }}
    .table-wrap {{
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow-x: auto;
    }}
    table {{
      background: #fff;
      border-collapse: collapse;
      min-width: 960px;
      width: 100%;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: #f8fafc;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
    }}
    tr:last-child td {{ border-bottom: 0; }}
    .status {{
      border: 1px solid var(--line);
      border-radius: 999px;
      display: inline-flex;
      font-size: 11px;
      font-weight: 850;
      padding: 3px 8px;
      text-transform: uppercase;
      white-space: nowrap;
    }}
    .score {{
      font-weight: 780;
      white-space: nowrap;
    }}
    .muted {{ color: var(--muted); }}
    code {{
      background: #eef2f7;
      border-radius: 4px;
      padding: 1px 4px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      font-size: 12px;
    }}
    @media (max-width: 820px) {{
      .topbar, .lane {{ display: block; }}
      .nav {{ justify-content: flex-start; margin-top: 10px; }}
      .lane-dots {{ margin-top: 6px; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="wrap topbar">
      <h1>Search Test Runs</h1>
      <nav class="nav" aria-label="Related reports">
        <a href="search_quality_progress_log.html">Progress Log</a>
        <a href="search_quality_experiments.html">Experiment Details</a>
        <a href="search_quality_test_suite.md">Test Suite</a>
      </nav>
    </div>
  </header>
  <main>
    <section class="panel toolbar">
      <div class="filter" aria-label="Status filters">
        <button type="button" class="active" data-filter="all">All</button>
        <button type="button" data-filter="bad">Failed</button>
        <button type="button" data-filter="warn">Warn</button>
        <button type="button" data-filter="good">Passed</button>
        <button type="button" data-filter="neutral">Other</button>
      </div>
      <div class="legend" aria-label="Legend">
        <span class="key"><span class="dot good"></span>Passed</span>
        <span class="key"><span class="dot warn"></span>Warn</span>
        <span class="key"><span class="dot bad"></span>Failed</span>
        <span class="key"><span class="dot neutral"></span>Other</span>
      </div>
    </section>
    <section class="panel">
      <div id="timeline" class="grid"></div>
    </section>
    <section class="panel">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Time UTC</th>
              <th>Test</th>
              <th>Status</th>
              <th>Score</th>
              <th>Details</th>
              <th>Duration</th>
              <th>Artifact</th>
            </tr>
          </thead>
          <tbody id="runs"></tbody>
        </table>
      </div>
    </section>
  </main>
  <script>
    const RUNS = {data_json};
    let activeFilter = "all";

    function fmtTime(value) {{
      if (!value) return "";
      return value.replace("T", " ").replace("Z", " UTC");
    }}

    function fmtDuration(value) {{
      const seconds = Number(value || 0);
      if (!seconds) return "";
      if (seconds >= 60) {{
        const minutes = Math.floor(seconds / 60);
        const rest = Math.round(seconds % 60);
        return `${{minutes}}m ${{rest}}s`;
      }}
      return `${{seconds.toFixed(1)}}s`;
    }}

    function artifactHref(path) {{
      if (!path) return "#";
      if (path.startsWith("docs/")) return path.slice(5);
      if (path.startsWith("http://") || path.startsWith("https://")) return path;
      return `../${{path}}`;
    }}

    function esc(value) {{
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }}

    function visibleRuns() {{
      return RUNS.filter((run) => activeFilter === "all" || run.status === activeFilter);
    }}

    function renderTimeline() {{
      const container = document.getElementById("timeline");
      const byTest = new Map();
      for (const run of visibleRuns().slice().reverse()) {{
        if (!byTest.has(run.test)) byTest.set(run.test, []);
        byTest.get(run.test).push(run);
      }}
      const rows = Array.from(byTest.entries())
        .sort((a, b) => a[0].localeCompare(b[0]))
        .map(([test, runs]) => {{
          const dots = runs.map((run) => {{
            const title = `${{fmtTime(run.time)}} | ${{run.statusText}} | ${{run.score}} | ${{run.detail}}`;
            return `<a class="run-dot ${{run.status}}" href="${{artifactHref(run.artifact)}}" title="${{esc(title)}}" aria-label="${{esc(title)}}"></a>`;
          }}).join("");
          return `<div class="lane"><div class="lane-name">${{esc(test)}}</div><div class="lane-dots">${{dots}}</div></div>`;
        }});
      container.innerHTML = rows.join("") || '<div class="muted">No runs for this filter.</div>';
    }}

    function renderTable() {{
      const body = document.getElementById("runs");
      body.innerHTML = visibleRuns().map((run) => `
        <tr>
          <td>${{fmtTime(run.time)}}</td>
          <td>${{esc(run.test)}}</td>
          <td><span class="status ${{run.status}}">${{esc(run.statusText)}}</span></td>
          <td class="score">${{esc(run.score || "")}}</td>
          <td class="muted">${{esc(run.detail || "")}}</td>
          <td>${{fmtDuration(run.duration)}}</td>
          <td><a href="${{artifactHref(run.artifact)}}"><code>${{esc(run.artifact)}}</code></a></td>
        </tr>
      `).join("");
    }}

    function render() {{
      renderTimeline();
      renderTable();
    }}

    document.querySelectorAll("[data-filter]").forEach((button) => {{
      button.addEventListener("click", () => {{
        activeFilter = button.dataset.filter;
        document.querySelectorAll("[data-filter]").forEach((item) => item.classList.remove("active"));
        button.classList.add("active");
        render();
      }});
    }});

    render();
  </script>
</body>
</html>
"""


def main() -> int:
    rows = collect_rows()
    OUTPUT.write_text(build_html(rows), encoding="utf-8")
    print(f"wrote {repo_path(OUTPUT)} with {len(rows)} runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
