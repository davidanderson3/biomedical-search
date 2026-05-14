from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qe_evidence_vectors.source_acquisition_progression import (
    build_progression_manifest,
    evaluate_rule,
    read_progression_stages,
    write_progression_json,
    write_progression_markdown,
)


def _write_metrics(path: Path, *, good: int, mixed: int, found_10: int, found_20: int) -> None:
    metrics = {
        "paragraphs": 2,
        "expected_concepts": 4,
        "verdict_counts": {"good": good, "mixed": mixed, "poor": 0},
        "queries_all_expected_at_10": 1,
        "queries_all_expected_at_20": 1,
        "queries_with_disallowed_at_10": 0,
        "queries_with_disallowed_at_20": 0,
        "found_at_5": 2,
        "found_at_10": found_10,
        "found_at_20": found_20,
        "found_at_60": found_20,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics) + "\n", encoding="utf-8")


def test_source_acquisition_progression_manifest_is_reproducible(tmp_path: Path) -> None:
    queries = tmp_path / "queries.tsv"
    summary = tmp_path / "summary.tsv"
    source_artifact = tmp_path / "source.jsonl"
    baseline_metrics = tmp_path / "baseline_metrics.json"
    rejected_metrics = tmp_path / "rejected_metrics.json"
    acquired_metrics = tmp_path / "acquired_metrics.json"
    stages_tsv = tmp_path / "stages.tsv"

    queries.write_text("paragraph_id\tquery\np1\ttest\n", encoding="utf-8")
    summary.write_text("paragraph_id\tverdict\np1\tgood\n", encoding="utf-8")
    source_artifact.write_text('{"source":"test"}\n', encoding="utf-8")
    _write_metrics(baseline_metrics, good=1, mixed=1, found_10=3, found_20=3)
    _write_metrics(rejected_metrics, good=1, mixed=1, found_10=2, found_20=3)
    _write_metrics(acquired_metrics, good=2, mixed=0, found_10=4, found_20=4)

    stages_tsv.write_text(
        "\t".join(
            [
                "group",
                "stage_id",
                "order",
                "label",
                "hypothesis",
                "acquisition_scope",
                "queries",
                "metrics",
                "summary",
                "artifact_paths",
                "decision_rule",
                "decision",
                "notes",
            ]
        )
        + "\n"
        + "\t".join(
            [
                "toy",
                "baseline",
                "0",
                "Toy baseline",
                "Establish a floor.",
                "none",
                "queries.tsv",
                "baseline_metrics.json",
                "summary.tsv",
                "",
                "diagnostic",
                "baseline",
                "",
            ]
        )
        + "\n"
        + "\t".join(
            [
                "toy",
                "rejected_probe",
                "1",
                "Rejected probe",
                "A probe can be recorded without becoming the next reference.",
                "narrow test source",
                "queries.tsv",
                "rejected_metrics.json",
                "summary.tsv",
                "",
                "diagnostic",
                "reject",
                "negative control",
            ]
        )
        + "\n"
        + "\t".join(
            [
                "toy",
                "acquired",
                "2",
                "Toy acquisition",
                "Evidence should improve recall.",
                "test source",
                "queries.tsv",
                "acquired_metrics.json",
                "summary.tsv",
                "source.jsonl",
                "promote",
                "accept",
                "accepted in test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    stages = read_progression_stages(stages_tsv)
    manifest = build_progression_manifest(stages, root=tmp_path, stage_config_path=stages_tsv)

    assert manifest["summary"] == {
        "groups": 1,
        "stages": 3,
        "skipped_stages": 0,
        "rule_failures": 0,
        "missing_artifacts": 0,
    }
    assert manifest["stage_config"]["sha256"]
    acquired = manifest["stages"][2]
    assert acquired["reference_stage_id"] == "baseline"
    assert acquired["delta_vs_reference"]["found_at_20"] == 1
    assert acquired["delta_vs_group_baseline"]["good"] == 1
    assert acquired["rule_evaluation"]["passed"] is True
    assert all(artifact["exists"] for artifact in acquired["artifacts"])

    out_json = tmp_path / "progression.json"
    out_md = tmp_path / "progression.md"
    write_progression_json(manifest, out_json)
    write_progression_markdown(manifest, out_md)

    written = json.loads(out_json.read_text(encoding="utf-8"))
    assert written["groups"][0]["final_stage_id"] == "acquired"
    report = out_md.read_text(encoding="utf-8")
    assert "Decision gates compare each stage with the previous retained stage" in report
    assert "Gate delta vs reference" in report


def test_progression_rules_fail_on_incremental_recall_or_false_positive_regression() -> None:
    previous = {
        "good": 2,
        "mixed": 0,
        "poor": 0,
        "found_at_5": 3,
        "found_at_10": 4,
        "found_at_20": 4,
        "found_at_60": 4,
        "recall_at_5": 0.75,
        "recall_at_10": 1.0,
        "recall_at_20": 1.0,
        "recall_at_60": 1.0,
        "queries_with_disallowed_at_10": 0,
        "queries_with_disallowed_at_20": 0,
    }
    current = dict(previous)
    current["found_at_10"] = 3
    current["found_at_20"] = 3
    current["queries_with_disallowed_at_10"] = 1
    current["queries_with_disallowed_at_20"] = 1
    delta = {
        "good": 0,
        "mixed": 0,
        "poor": 0,
        "found_at_5": 0,
        "found_at_10": -1,
        "found_at_20": -1,
        "found_at_60": -1,
        "recall_at_5": 0.0,
        "recall_at_10": -0.25,
        "recall_at_20": -0.25,
        "recall_at_60": -0.25,
        "queries_with_disallowed_at_10": 1,
        "queries_with_disallowed_at_20": 1,
    }

    result = evaluate_rule(rule="no_regression", current=current, baseline=previous, delta=delta)

    assert result["passed"] is False
    failed_checks = {check["name"] for check in result["checks"] if not check["passed"]}
    assert {
        "no_recall_at_10_regression",
        "no_recall_at_20_regression",
        "no_disallowed_at_10_regression",
        "no_disallowed_at_20_regression",
    } <= failed_checks


def test_progression_manifest_can_skip_missing_metrics_for_fresh_clone(tmp_path: Path) -> None:
    stages_tsv = tmp_path / "stages.tsv"
    stages_tsv.write_text(
        "\t".join(
            [
                "group",
                "stage_id",
                "order",
                "label",
                "hypothesis",
                "acquisition_scope",
                "queries",
                "metrics",
                "summary",
                "artifact_paths",
                "decision_rule",
                "decision",
                "notes",
            ]
        )
        + "\n"
        + "\t".join(
            [
                "toy",
                "missing",
                "0",
                "Missing local stage",
                "Fresh clones do not have build artifacts yet.",
                "none",
                "missing_queries.tsv",
                "missing_metrics.json",
                "missing_summary.tsv",
                "",
                "diagnostic",
                "baseline",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    manifest = build_progression_manifest(
        read_progression_stages(stages_tsv),
        root=tmp_path,
        stage_config_path=stages_tsv,
        allow_missing_metrics=True,
    )

    assert manifest["summary"]["groups"] == 0
    assert manifest["summary"]["stages"] == 0
    assert manifest["summary"]["skipped_stages"] == 1
    assert manifest["skipped_stages"][0]["skip_reason"] == "missing_metrics"
    report_path = tmp_path / "report.md"
    write_progression_markdown(manifest, report_path)
    assert "## Skipped Stages" in report_path.read_text(encoding="utf-8")
