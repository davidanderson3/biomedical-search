from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_whole_product_quality_scorecard.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("build_whole_product_quality_scorecard", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_json(
    root: Path,
    name: str,
    *,
    created_at: str,
    query_file: str,
    query_limit: int,
    run_family: str,
    paragraphs: int,
    overall_score: float,
    top_on_target_rate: float = 1.0,
) -> None:
    run_dir = root / name
    run_dir.mkdir(parents=True)
    payload = {
        "run_id": name,
        "created_at": created_at,
        "queries": f"/tmp/{query_file}",
        "query_limit": query_limit,
        "run_family": run_family,
        "summary": {
            "paragraphs": paragraphs,
            "overall_score": overall_score,
            "top_on_target_rate": top_on_target_rate,
            "top_on_target_count": round(top_on_target_rate * paragraphs),
            "strict_success_at_10_count": round(overall_score / 100 * paragraphs),
        },
    }
    (run_dir / "run.json").write_text(json.dumps(payload), encoding="utf-8")


def test_default_scorecard_has_expected_weights_and_cap() -> None:
    config = json.loads((ROOT / "config" / "whole_product_quality_scorecard.json").read_text(encoding="utf-8"))
    lanes = {lane["id"]: lane for lane in config["lanes"]}

    assert len(config["lanes"]) == 8
    assert len(config["measurement_dimensions"]) == 8
    assert round(sum(lane["weight"] for lane in config["lanes"]), 6) == 100
    assert lanes["realistic_note_formats"]["weight"] == 22
    assert lanes["pubmed_long_abstracts"]["weight"] == 22
    assert lanes["patient_portal_current_issue"]["score_metric"] == "top_on_target_rate"
    assert lanes["broad_clinical_paragraphs"]["metric_focus"]
    assert config["caps"][0]["max_score"] == 76


def test_scorecard_uses_latest_matching_run_and_major_weakness_cap(tmp_path: Path) -> None:
    module = load_script_module()
    run_root = tmp_path / "runs"
    run_json(
        run_root,
        "old-note-run",
        created_at="2026-06-17T10:00:00Z",
        query_file="notes.tsv",
        query_limit=0,
        run_family="probe",
        paragraphs=24,
        overall_score=90,
    )
    run_json(
        run_root,
        "new-note-run",
        created_at="2026-06-17T20:00:00Z",
        query_file="notes.tsv",
        query_limit=0,
        run_family="probe",
        paragraphs=24,
        overall_score=50,
    )
    run_json(
        run_root,
        "pubmed-run",
        created_at="2026-06-17T20:05:00Z",
        query_file="pubmed.tsv",
        query_limit=0,
        run_family="probe",
        paragraphs=23,
        overall_score=55,
    )
    run_json(
        run_root,
        "portal-run",
        created_at="2026-06-17T20:10:00Z",
        query_file="portal.tsv",
        query_limit=0,
        run_family="patient_portal",
        paragraphs=12,
        overall_score=25,
        top_on_target_rate=1.0,
    )
    config = {
        "name": "Test Product Score",
        "lanes": [
            {
                "id": "realistic_note_formats",
                "label": "Notes",
                "weight": 40,
                "query_file": "notes.tsv",
                "query_limit": 0,
                "run_family": "probe",
                "score_metric": "overall_score",
                "metric_focus": ["near-miss severity", "first-page drift"],
            },
            {
                "id": "pubmed_long_abstracts",
                "label": "PubMed",
                "weight": 40,
                "query_file": "pubmed.tsv",
                "query_limit": 0,
                "run_family": "probe",
                "score_metric": "overall_score",
            },
            {
                "id": "patient_portal_current_issue",
                "label": "Portal",
                "weight": 20,
                "query_file": "portal.tsv",
                "query_limit": 0,
                "run_family": "patient_portal",
                "score_metric": "top_on_target_rate",
            },
        ],
        "caps": [
            {
                "id": "major_known_weakness_cap",
                "lane_ids": ["realistic_note_formats", "pubmed_long_abstracts"],
                "below_score": 60,
                "minimum_count": 2,
                "max_score": 65,
                "reason": "test cap",
            }
        ],
    }

    scorecard = module.build_scorecard(config, module.iter_runs(run_root))
    lanes = {lane["id"]: lane for lane in scorecard["lanes"]}

    assert lanes["realistic_note_formats"]["run_id"] == "new-note-run"
    assert lanes["realistic_note_formats"]["metric_focus"] == ["near-miss severity", "first-page drift"]
    assert scorecard["raw_weighted_score"] == 62.0
    assert scorecard["score"] == 62
    assert scorecard["caps_applied"][0]["active"] is True
    assert scorecard["caps_applied"][0]["changed_score"] is False


def test_scorecard_cap_lowers_inflated_weighted_score(tmp_path: Path) -> None:
    module = load_script_module()
    run_root = tmp_path / "runs"
    run_json(
        run_root,
        "note-run",
        created_at="2026-06-17T20:00:00Z",
        query_file="notes.tsv",
        query_limit=0,
        run_family="probe",
        paragraphs=24,
        overall_score=50,
    )
    run_json(
        run_root,
        "pubmed-run",
        created_at="2026-06-17T20:05:00Z",
        query_file="pubmed.tsv",
        query_limit=0,
        run_family="probe",
        paragraphs=23,
        overall_score=55,
    )
    run_json(
        run_root,
        "green-run",
        created_at="2026-06-17T20:10:00Z",
        query_file="green.tsv",
        query_limit=0,
        run_family="release",
        paragraphs=20,
        overall_score=100,
    )
    config = {
        "name": "Test Product Score",
        "lanes": [
            {"id": "realistic_note_formats", "weight": 10, "query_file": "notes.tsv", "query_limit": 0, "run_family": "probe", "score_metric": "overall_score"},
            {"id": "pubmed_long_abstracts", "weight": 10, "query_file": "pubmed.tsv", "query_limit": 0, "run_family": "probe", "score_metric": "overall_score"},
            {"id": "green_lane", "weight": 80, "query_file": "green.tsv", "query_limit": 0, "run_family": "release", "score_metric": "overall_score"},
        ],
        "caps": [
            {
                "id": "major_known_weakness_cap",
                "lane_ids": ["realistic_note_formats", "pubmed_long_abstracts"],
                "below_score": 60,
                "minimum_count": 2,
                "max_score": 76,
                "reason": "test cap",
            }
        ],
    }

    scorecard = module.build_scorecard(config, module.iter_runs(run_root))

    assert scorecard["raw_weighted_score"] == 90.5
    assert scorecard["score"] == 76
    assert scorecard["caps_applied"][0]["changed_score"] is True
