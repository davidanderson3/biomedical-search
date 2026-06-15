from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = ROOT / "build" / "scaling_runs" / "full_pipeline"
SHARD_BATCHES = (
    "1327_1326",
    "1325_1324",
    "1323_1322",
    "1321_1320",
)


def count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(newline="", encoding="utf-8") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def batch_record(batch: str) -> dict:
    run_id = f"pubmed_bulk_recent_{batch}"
    run_dir = ROOT / "build" / "scaling_runs" / run_id
    index_slug = f"qe-scaling-pubmed-bulk-recent-{batch.replace('_', '-')}-sapbert-cls"
    mapping = ROOT / "build" / f"{index_slug}.elastic.mapping.json"
    bulk_files = sorted((ROOT / "build").glob(f"{index_slug}.elastic.bulk*.ndjson"))
    marker = ROOT / "build" / "scaling_runs" / f"elasticsearch_loaded_{run_id}_sapbert_cls.marker"
    summary_path = run_dir / "search_quality_summary.json"
    judgments_path = run_dir / "search_quality_judgments.csv"
    summary = load_json(summary_path)
    return {
        "batch": batch,
        "run_id": run_id,
        "run_dir": str(run_dir.relative_to(ROOT)),
        "summary_path": str(summary_path.relative_to(ROOT)) if summary_path.exists() else "",
        "summary_exists": summary_path.exists(),
        "summary_queries": summary.get("queries", ""),
        "summary_judgments": summary.get("judgments", ""),
        "judgments_path": str(judgments_path.relative_to(ROOT)) if judgments_path.exists() else "",
        "judgments_exists": judgments_path.exists(),
        "judgment_rows": count_csv_rows(judgments_path),
        "elastic_mapping_path": str(mapping.relative_to(ROOT)) if mapping.exists() else "",
        "elastic_mapping_exists": mapping.exists(),
        "elastic_bulk_files": [str(path.relative_to(ROOT)) for path in bulk_files],
        "elastic_bulk_file_count": len(bulk_files),
        "load_marker": str(marker.relative_to(ROOT)) if marker.exists() else "",
        "load_marker_exists": marker.exists(),
    }


def reconcile() -> dict:
    records = [batch_record(batch) for batch in SHARD_BATCHES]
    missing_judgments = [row["batch"] for row in records if not row["judgments_exists"]]
    loaded_without_exports = [
        row["batch"]
        for row in records
        if row["load_marker_exists"] and not (row["elastic_mapping_exists"] and row["elastic_bulk_file_count"])
    ]
    return {
        "batches": records,
        "missing_row_level_judgments": missing_judgments,
        "loaded_without_export_artifacts": loaded_without_exports,
        "safe_next_action": (
            "Regenerate or manually restore row-level search_quality_judgments.csv for missing batches before "
            "marking their review steps complete. Do not reconstruct row-level judgments from aggregate summaries."
        ),
    }


def write_markdown(report: dict, path: Path) -> None:
    lines = [
        "# PubMed Shard Review Reconciliation",
        "",
        "This report reconciles recent PubMed shard review/export artifacts for the full-pipeline gate.",
        "",
        f"- Missing row-level judgments: {', '.join(report['missing_row_level_judgments']) or 'none'}",
        f"- Load markers without export artifacts: {', '.join(report['loaded_without_export_artifacts']) or 'none'}",
        f"- Safe next action: {report['safe_next_action']}",
        "",
        "| Batch | Summary | Row judgments | Rows | Mapping | Bulk files | Load marker |",
        "| --- | --- | --- | ---: | --- | ---: | --- |",
    ]
    for row in report["batches"]:
        lines.append(
            "| {batch} | {summary} | {judgments} | {rows} | {mapping} | {bulk_count} | {marker} |".format(
                batch=row["batch"],
                summary="yes" if row["summary_exists"] else "no",
                judgments="yes" if row["judgments_exists"] else "no",
                rows=row["judgment_rows"],
                mapping="yes" if row["elastic_mapping_exists"] else "no",
                bulk_count=row["elastic_bulk_file_count"],
                marker="yes" if row["load_marker_exists"] else "no",
            )
        )
    lines.extend(
        [
            "",
            "Aggregate `search_quality_summary.json` files are useful status evidence, but they do not contain the reviewed row-level `query`, `doc_id`, `cui`, `score`, and `grade` values needed to recreate missing judgment CSVs.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile recent PubMed shard review/export artifacts.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    report = reconcile()
    json_path = args.out_dir / "pubmed_shard_review_reconciliation.json"
    md_path = args.out_dir / "pubmed_shard_review_reconciliation.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(report, md_path)
    print(f"wrote {json_path.relative_to(ROOT)}")
    print(f"wrote {md_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
