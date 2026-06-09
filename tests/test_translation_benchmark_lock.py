from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_SCRIPT = ROOT / "scripts" / "build_translation_benchmark_report.py"
EXPERIMENT_SCRIPT = ROOT / "scripts" / "run_search_quality_experiment.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_translation_benchmark_lock_inputs_match_current_files() -> None:
    module = load_module(REPORT_SCRIPT, "build_translation_benchmark_report")
    lock = module.load_lock()

    mismatches = []
    for slice_spec in lock["slices"]:
        status = module.file_lock_status(slice_spec)
        if not status["matches"]:
            mismatches.append(
                {
                    "id": slice_spec["id"],
                    "path": status["path"],
                    "locked_rows": status["locked_rows"],
                    "actual_rows": status["actual_rows"],
                    "locked_sha256": status["locked_sha256"],
                    "actual_sha256": status["actual_sha256"],
                }
            )

    assert mismatches == []


def test_translation_benchmark_report_keeps_slices_separate() -> None:
    module = load_module(REPORT_SCRIPT, "build_translation_benchmark_report")
    report = module.build_report(module.load_lock())
    slices = {slice_report["id"]: slice_report for slice_report in report["slices"]}

    assert set(slices) == {
        "clinical_smoke",
        "pubmed_literature_dev",
        "pubmed_literature_heldout",
        "exact_umls_api_comparison",
        "code_coverage",
    }
    assert slices["clinical_smoke"]["group"] == "clinical"
    assert slices["pubmed_literature_heldout"]["group"] == "pubmed"
    assert slices["exact_umls_api_comparison"]["group"] == "exact_umls"
    assert slices["code_coverage"]["group"] == "code"

    assert slices["clinical_smoke"]["result"]["queries_all_expected_at_10"] == 164
    assert slices["pubmed_literature_heldout"]["result"]["queries_all_expected_at_10"] == 1
    assert slices["exact_umls_api_comparison"]["result"]["variants"][0]["local_expected_top10"] == 11


def test_translation_benchmark_code_coverage_reports_vocab_gaps() -> None:
    module = load_module(REPORT_SCRIPT, "build_translation_benchmark_report")
    report = module.build_report(module.load_lock())
    code_result = next(
        slice_report["result"]
        for slice_report in report["slices"]
        if slice_report["id"] == "code_coverage"
    )
    rows = {row["id"]: row for row in code_result["rows"]}

    assert code_result["rows_complete"] == 7
    assert code_result["found_sabs_total"] == 12
    assert rows["code_atrial_fibrillation"]["missing_sabs"] == "ICD10CM"
    assert rows["code_electrolytes_outside_reference_range"]["complete"] is True


def test_search_quality_experiments_page_includes_translation_benchmark_panel(tmp_path: Path) -> None:
    module = load_module(EXPERIMENT_SCRIPT, "run_search_quality_experiment")
    module.DEFAULT_TRANSLATION_BENCHMARK_REPORT_JSON = tmp_path / "missing_report.json"

    panel = module.translation_benchmark_panel_html()

    assert "Translation Benchmark" in panel
    assert "2/7 practice; 1/6 locked" in panel
    assert "translation_benchmark_report.html" in panel
