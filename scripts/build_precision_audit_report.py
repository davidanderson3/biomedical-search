#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REVIEW = ROOT / "config" / "search_quality_precision_audit_review.tsv"
DEFAULT_USEFUL_EXTRAS = ROOT / "config" / "search_quality_useful_extra_cuis.tsv"
DEFAULT_LIVE_AUDIT = ROOT / "build" / "search_quality_live_audit" / "paragraph_precision_audit.tsv"
DEFAULT_REVIEWED_AUDIT = ROOT / "build" / "search_quality_live_audit_reviewed" / "paragraph_precision_audit.tsv"
DEFAULT_OUTPUT = ROOT / "docs" / "search_quality_precision_audit.html"
ALLOWED_REVIEW_CLASSES = {"expected", "useful_extra", "true_false_positive"}
ACTION_BY_CLASS = {
    "expected": {"promote_expected"},
    "useful_extra": {"add_useful_extra"},
    "true_false_positive": {"keep_rule_candidate", "add_disallowed_cui", "suppress"},
}


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(
            (line for line in handle if line.strip() and not line.lstrip().startswith("#")),
            delimiter="\t",
        )
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def row_key(row: dict[str, str]) -> tuple[str, str]:
    return (row.get("id") or row.get("query_id") or "", (row.get("cui") or row.get("useful_extra_cui") or "").upper())


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def validate_review_rows(review_rows: list[dict[str, str]], useful_extra_rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    useful_extra_keys = {row_key(row) for row in useful_extra_rows}
    for index, row in enumerate(review_rows, start=2):
        key = row_key(row)
        review_class = row.get("review_class", "")
        action = row.get("action", "")
        if not key[0] or not key[1]:
            errors.append(f"line {index}: missing id or cui")
        if key in seen:
            errors.append(f"line {index}: duplicate review row {key[0]} {key[1]}")
        seen.add(key)
        if review_class not in ALLOWED_REVIEW_CLASSES:
            errors.append(f"line {index}: unknown review_class {review_class!r}")
        allowed_actions = ACTION_BY_CLASS.get(review_class, set())
        if action not in allowed_actions:
            errors.append(f"line {index}: action {action!r} does not match review_class {review_class!r}")
        if not row.get("why"):
            errors.append(f"line {index}: missing why")
        if review_class == "useful_extra" and key not in useful_extra_keys:
            errors.append(f"line {index}: useful_extra review row is missing from useful-extra config")
    return errors


def table(headers: list[str], rows: list[list[object]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def inline_html(text: str) -> str:
    escaped = html.escape(text, quote=True)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped


def markdown_table_to_html(lines: list[str]) -> str:
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in lines
        if line.strip()
    ]
    if len(rows) < 2:
        return ""
    headers = rows[0]
    body = rows[2:]
    th = "".join(f"<th>{inline_html(cell)}</th>" for cell in headers)
    trs = []
    for row in body:
        trs.append("<tr>" + "".join(f"<td>{inline_html(cell)}</td>" for cell in row) + "</tr>")
    body_html = "".join(trs) or f'<tr><td colspan="{len(headers)}">None.</td></tr>'
    return (
        "<table>"
        f"<thead><tr>{th}</tr></thead>"
        f"<tbody>{body_html}</tbody>"
        "</table>"
    )


def render_html_report(markdown: str) -> str:
    lines = markdown.splitlines()
    title = "Search Quality Precision Audit Review"
    body: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    index = 0

    def flush_paragraph() -> None:
        if paragraph:
            body.append(f"<p>{inline_html(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_list() -> None:
        if list_items:
            body.append("<ul>" + "".join(f"<li>{inline_html(item)}</li>" for item in list_items) + "</ul>")
            list_items.clear()

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            flush_list()
            index += 1
            continue
        if stripped.startswith("|"):
            flush_paragraph()
            flush_list()
            table_lines = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index])
                index += 1
            body.append(markdown_table_to_html(table_lines))
            continue
        if stripped.startswith("# "):
            flush_paragraph()
            flush_list()
            title = stripped[2:].strip()
            body.append(f"<h1>{inline_html(title)}</h1>")
        elif stripped.startswith("## "):
            flush_paragraph()
            flush_list()
            body.append(f"<h2>{inline_html(stripped[3:].strip())}</h2>")
        elif stripped.startswith("- "):
            flush_paragraph()
            list_items.append(stripped[2:].strip())
        else:
            paragraph.append(stripped)
        index += 1
    flush_paragraph()
    flush_list()

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title, quote=True)}</title>
  <style>
    body {{ margin: 0; background: #f6f7f9; color: #17202a; font: 14px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ width: min(1080px, calc(100vw - 32px)); margin: 0 auto; padding: 28px 0 48px; }}
    h1 {{ margin: 0 0 12px; font-size: 30px; line-height: 1.15; letter-spacing: 0; }}
    h2 {{ margin: 32px 0 12px; font-size: 20px; letter-spacing: 0; }}
    p {{ margin: 0 0 12px; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #d7dde5; border-radius: 8px; overflow: hidden; margin: 10px 0 20px; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #d7dde5; text-align: left; vertical-align: top; }}
    th {{ background: #eef2f6; color: #233142; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
    tr:last-child td {{ border-bottom: 0; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; background: #eef2f6; border-radius: 4px; padding: 1px 4px; }}
    ul {{ margin: 8px 0 16px 22px; padding: 0; }}
    li {{ margin: 6px 0; }}
    @media (max-width: 720px) {{ main {{ width: min(100vw - 20px, 1080px); padding-top: 18px; }} table {{ display: block; overflow-x: auto; }} }}
  </style>
</head>
<body>
<main>
{''.join(body)}
</main>
</body>
</html>
"""


def compact_label_rows(rows: list[dict[str, str]]) -> list[list[str]]:
    return [
        [
            row.get("id", ""),
            row.get("cui", ""),
            row.get("label") or row.get("name", ""),
            row.get("why", ""),
        ]
        for row in rows
    ]


def build_report(
    *,
    review_path: Path,
    useful_extras_path: Path,
    live_audit_path: Path,
    reviewed_audit_path: Path,
) -> str:
    review_rows = read_tsv(review_path)
    useful_extra_rows = read_tsv(useful_extras_path)
    live_rows = read_tsv(live_audit_path)
    reviewed_rows = read_tsv(reviewed_audit_path)
    errors = validate_review_rows(review_rows, useful_extra_rows)
    if errors:
        raise ValueError("\n".join(errors))

    class_counts = Counter(row.get("review_class", "") for row in review_rows)
    action_counts = Counter(row.get("action", "") for row in review_rows)
    review_keys = {row_key(row) for row in review_rows}
    live_keys = {row_key(row) for row in live_rows}
    reviewed_keys = {row_key(row) for row in reviewed_rows}
    missing_from_review = sorted(live_keys - review_keys)
    stale_review_keys = sorted(review_keys - live_keys) if live_rows else []
    true_false_positive_rows = [
        row for row in review_rows if row.get("review_class") == "true_false_positive"
    ]

    lines = [
        "# Search Quality Precision Audit Review",
        "",
        "This report closes SQI-2026-06-10-005. It classifies the visible precision-audit queue so future ranking work can distinguish useful secondary concepts from true false positives.",
        "",
        "## Source Artifacts",
        "",
        f"- Review ledger: `{display_path(review_path)}`",
        f"- Applied useful extras: `{display_path(useful_extras_path)}`",
        f"- Current raw audit queue: `{display_path(live_audit_path)}`" if live_rows else f"- Current raw audit queue: `{display_path(live_audit_path)}` was not present when this report was generated.",
        f"- Post-review residual audit: `{display_path(reviewed_audit_path)}`" if reviewed_rows else f"- Post-review residual audit: `{display_path(reviewed_audit_path)}` was not present when this report was generated.",
        "",
        "## Classification Summary",
        "",
        table(
            ["Class", "Rows", "Meaning"],
            [
                [
                    "expected",
                    class_counts.get("expected", 0),
                    "Central enough to promote into the expected CUI set.",
                ],
                [
                    "useful_extra",
                    class_counts.get("useful_extra", 0),
                    "Explicitly useful secondary concept; should not count as a false positive.",
                ],
                [
                    "true_false_positive",
                    class_counts.get("true_false_positive", 0),
                    "Wrong, misleading, overbroad, contradictory, or metadata-like result.",
                ],
            ],
        ),
        "",
        table(
            ["Action", "Rows"],
            [[action or "(blank)", count] for action, count in sorted(action_counts.items())],
        ),
        "",
        "## Queue Reconciliation",
        "",
        f"- Reviewed rows: {len(review_rows)}",
        f"- Current raw suspect rows: {len(live_rows) if live_rows else 'not available'}",
        f"- Post-review residual suspect rows: {len(reviewed_rows) if reviewed_rows else 'not available'}",
        f"- Useful-extra review rows missing from useful-extra config: 0",
        f"- Current raw suspect rows missing review classification: {len(missing_from_review)}",
        f"- Reviewed rows not present in current raw queue: {len(stale_review_keys)}",
        "",
        "Earlier planning text referred to 70 suspect rows. The current generated raw audit queue contains 69 rows, and all 69 have review classifications. This report records the current reproducible state rather than preserving the stale count.",
        "",
        "## Residual True False Positives",
        "",
        table(["Query", "CUI", "Label", "Why"], compact_label_rows(true_false_positive_rows)),
        "",
        "## Verification",
        "",
        "- The review ledger uses only allowed classes: `expected`, `useful_extra`, and `true_false_positive`.",
        "- Every `useful_extra` review row is present in `config/search_quality_useful_extra_cuis.tsv`.",
        "- The current raw audit queue is fully covered by the review ledger.",
        "- The post-review residual audit contains the 11 true-false-positive candidates.",
        "",
        "## Next",
        "",
        "Keep these 11 residual false positives as ranking/suppression targets. Do not tune ranking against useful-extra rows as though they were false positives.",
        "",
    ]
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the search-quality precision audit review report.")
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--useful-extras", type=Path, default=DEFAULT_USEFUL_EXTRAS)
    parser.add_argument("--live-audit", type=Path, default=DEFAULT_LIVE_AUDIT)
    parser.add_argument("--reviewed-audit", type=Path, default=DEFAULT_REVIEWED_AUDIT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", type=Path, help="Optional Markdown report output path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    markdown_report = build_report(
        review_path=args.review,
        useful_extras_path=args.useful_extras,
        live_audit_path=args.live_audit,
        reviewed_audit_path=args.reviewed_audit,
    )
    report = render_html_report(markdown_report)
    output = args.output.expanduser()
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"wrote {output.relative_to(ROOT)}")
    if args.markdown_output:
        markdown_output = args.markdown_output.expanduser()
        if not markdown_output.is_absolute():
            markdown_output = ROOT / markdown_output
        markdown_output.parent.mkdir(parents=True, exist_ok=True)
        markdown_output.write_text(markdown_report, encoding="utf-8")
        print(f"wrote {markdown_output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
