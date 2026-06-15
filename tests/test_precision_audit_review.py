from __future__ import annotations

import csv
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_precision_audit_report import (  # noqa: E402
    ALLOWED_REVIEW_CLASSES,
    build_report,
    read_tsv,
    row_key,
    validate_review_rows,
)


def test_precision_audit_review_rows_are_classified_and_applied() -> None:
    review_rows = read_tsv(ROOT / "config" / "search_quality_precision_audit_review.tsv")
    useful_extra_rows = read_tsv(ROOT / "config" / "search_quality_useful_extra_cuis.tsv")
    errors = validate_review_rows(review_rows, useful_extra_rows)

    assert errors == []
    assert len(review_rows) == 69
    assert {row["review_class"] for row in review_rows} <= ALLOWED_REVIEW_CLASSES
    assert sum(1 for row in review_rows if row["review_class"] == "useful_extra") == 58
    assert sum(1 for row in review_rows if row["review_class"] == "true_false_positive") == 11
    assert sum(1 for row in review_rows if row["review_class"] == "expected") == 0


def test_precision_audit_useful_extra_review_rows_are_in_useful_extra_config() -> None:
    review_rows = read_tsv(ROOT / "config" / "search_quality_precision_audit_review.tsv")
    useful_extra_rows = read_tsv(ROOT / "config" / "search_quality_useful_extra_cuis.tsv")
    useful_extra_keys = {row_key(row) for row in useful_extra_rows}
    reviewed_useful = {
        row_key(row)
        for row in review_rows
        if row.get("review_class") == "useful_extra"
    }

    assert reviewed_useful
    assert reviewed_useful <= useful_extra_keys


def test_current_live_precision_audit_queue_is_fully_classified_when_present() -> None:
    live_audit = ROOT / "build" / "search_quality_live_audit" / "paragraph_precision_audit.tsv"
    if not live_audit.exists():
        return
    live_rows = read_tsv(live_audit)
    review_rows = read_tsv(ROOT / "config" / "search_quality_precision_audit_review.tsv")

    assert {row_key(row) for row in live_rows} <= {row_key(row) for row in review_rows}


def test_precision_audit_report_can_be_generated(tmp_path: Path) -> None:
    output = tmp_path / "precision_audit.md"
    report = build_report(
        review_path=ROOT / "config" / "search_quality_precision_audit_review.tsv",
        useful_extras_path=ROOT / "config" / "search_quality_useful_extra_cuis.tsv",
        live_audit_path=ROOT / "build" / "search_quality_live_audit" / "paragraph_precision_audit.tsv",
        reviewed_audit_path=ROOT / "build" / "search_quality_live_audit_reviewed" / "paragraph_precision_audit.tsv",
    )
    output.write_text(report, encoding="utf-8")

    with (ROOT / "config" / "search_quality_precision_audit_review.tsv").open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        row_count = sum(1 for _row in csv.DictReader(handle, delimiter="\t"))

    assert row_count == 69
    assert "Reviewed rows: 69" in report
    assert "Current raw suspect rows missing review classification: 0" in report
    assert "Residual True False Positives" in report
