from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_source_rebuild_delta.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("check_source_rebuild_delta", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def args(**overrides):
    values = {
        "allow_missing_required": False,
        "source_count_collapse_tolerance": 0.25,
        "source_count_collapse_min_baseline": 10,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def complete_source(records_fetched: int = 100) -> dict:
    return {
        "source_id": "dailymed",
        "source_url": "https://dailymed.nlm.nih.gov/",
        "source_version": "2026-06-01",
        "source_date": "2026-06-01",
        "source_hash": "abc123",
        "records_fetched": records_fetched,
        "records_changed": 3,
        "cuis_gained": 2,
        "cuis_lost": 1,
        "relationship_edges_gained": 4,
        "relationship_edges_lost": 0,
        "top_source_changes_for_benchmark_queries": [{"query_id": "dailymed_label_01"}],
    }


def test_source_delta_report_passes_complete_manifest() -> None:
    module = load_script_module()
    current = {"sources": [complete_source(records_fetched=100)]}
    previous = {"sources": [complete_source(records_fetched=110)]}

    report = module.build_delta_report(previous, current, args())

    assert report["passed"] is True
    assert report["summary"] == {"sources": 1, "failures": 0}


def test_source_delta_report_fails_missing_required_fields() -> None:
    module = load_script_module()
    current = {"sources": [{"source_id": "pubtator3", "records_fetched": 50}]}

    report = module.build_delta_report(None, current, args())

    assert report["passed"] is False
    assert report["failures"][0]["check"] == "required_source_delta_fields_present"
    assert "source_url" in report["failures"][0]["missing_fields"]
    assert "relationship_edges_lost" in report["failures"][0]["missing_fields"]


def test_source_delta_report_fails_unexpected_record_collapse() -> None:
    module = load_script_module()
    current = {"sources": [complete_source(records_fetched=50)]}
    previous = {"sources": [complete_source(records_fetched=100)]}

    report = module.build_delta_report(previous, current, args())

    assert report["passed"] is False
    assert report["failures"][0]["check"] == "records_fetched_no_unexpected_collapse"
    assert report["failures"][0]["minimum_allowed"] == 75.0
