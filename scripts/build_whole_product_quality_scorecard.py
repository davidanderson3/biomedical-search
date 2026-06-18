#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "whole_product_quality_scorecard.json"
DEFAULT_RUN_ROOT = ROOT / "build" / "search_quality_experiments" / "runs"
DEFAULT_OUTPUT = ROOT / "build" / "whole_product_quality_scorecard.json"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_timestamp(value: object) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def repo_path(path: str | Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except Exception:
        return str(path)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_runs(run_root: Path) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for path in sorted(run_root.glob("*/run.json")):
        try:
            run = load_json(path)
        except Exception:
            continue
        run["_run_json_path"] = str(path)
        runs.append(run)
    return runs


def basename(value: object) -> str:
    return Path(str(value or "")).name


def string_contains(value: object, needle: object) -> bool:
    text = str(value or "")
    target = str(needle or "").strip()
    return not target or target in text


def list_value(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def run_matches_lane(run: dict[str, Any], lane: dict[str, Any]) -> bool:
    query_file = str(lane.get("query_file") or "").strip()
    if query_file and basename(run.get("queries")) != basename(query_file):
        return False

    if "query_limit" in lane:
        try:
            if int(run.get("query_limit") or 0) != int(lane["query_limit"]):
                return False
        except (TypeError, ValueError):
            return False

    families = list_value(lane.get("run_family"))
    if families and str(run.get("run_family") or "") not in families:
        return False

    paragraphs = lane.get("paragraphs")
    if paragraphs is not None:
        summary = run.get("summary") or {}
        try:
            actual = int(summary.get("paragraphs") or summary.get("queries") or 0)
            if actual != int(paragraphs):
                return False
        except (TypeError, ValueError):
            return False

    if not string_contains(run.get("run_id"), lane.get("run_id_contains")):
        return False
    if not string_contains(run.get("label"), lane.get("label_contains")):
        return False

    return True


def metric_number(summary: dict[str, Any], key: str) -> float | None:
    try:
        return float(summary.get(key))
    except (TypeError, ValueError):
        return None


def score_from_summary(summary: dict[str, Any], metric: str) -> float:
    value = metric_number(summary, metric)
    if value is None:
        return 0.0
    if metric.endswith("_rate") or 0.0 <= value <= 1.0 and metric != "overall_score":
        value *= 100.0
    return max(0.0, min(100.0, value))


def optional_int(summary: dict[str, Any], key: str) -> int | None:
    value = summary.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def reference_run_for_lane(lane: dict[str, Any]) -> dict[str, Any] | None:
    reference = lane.get("reference_run")
    if not isinstance(reference, dict):
        return None
    summary = reference.get("summary")
    if not isinstance(summary, dict):
        return None
    run = {
        "run_id": reference.get("run_id") or f"{lane.get('id')}_configured_reference",
        "created_at": reference.get("created_at") or "",
        "queries": reference.get("queries") or lane.get("query_file") or "",
        "query_limit": reference.get("query_limit", lane.get("query_limit", 0)),
        "run_family": reference.get("run_family") or lane.get("run_family") or "",
        "label": reference.get("label") or lane.get("label") or lane.get("id") or "",
        "summary": summary,
        "_run_json_path": reference.get("artifact") or "",
        "_reference_source": "configured_reference",
    }
    return run


def latest_matching_run(runs: list[dict[str, Any]], lane: dict[str, Any]) -> dict[str, Any] | None:
    matches = [run for run in runs if run_matches_lane(run, lane)]
    reference = reference_run_for_lane(lane)
    if reference is not None:
        matches.append(reference)
    if not matches:
        return None
    return max(matches, key=lambda run: parse_timestamp(run.get("created_at")))


def lane_result(lane: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    run = latest_matching_run(runs, lane)
    weight = float(lane.get("weight") or 0.0)
    metric = str(lane.get("score_metric") or "overall_score")
    if run is None:
        return {
            "id": lane.get("id"),
            "label": lane.get("label"),
            "weight": weight,
            "score_metric": metric,
            "score": 0.0,
            "weighted_points": 0.0,
            "status": "missing_run",
        }

    summary = run.get("summary") or {}
    score = score_from_summary(summary, metric)
    found_at_10 = optional_int(summary, "found_at_10") or 0
    found_at_20 = optional_int(summary, "found_at_20")
    found_at_60 = optional_int(summary, "found_at_60")
    expected_concepts = optional_int(summary, "expected_concepts") or 0
    result = {
        "id": lane.get("id"),
        "label": lane.get("label"),
        "weight": weight,
        "score_metric": metric,
        "score": round(score, 1),
        "weighted_points": round(score * weight / 100.0, 3),
        "status": "scored",
        "source": run.get("_reference_source") or "artifact",
        "run_id": run.get("run_id"),
        "created_at": run.get("created_at"),
        "artifact": repo_path(run.get("_run_json_path") or ""),
        "query_file": basename(run.get("queries")),
        "paragraphs": int(summary.get("paragraphs") or summary.get("queries") or 0),
        "strict_success_at_10": int(summary.get("strict_success_at_10_count") or 0),
        "queries_all_expected_at_10": int(summary.get("queries_all_expected_at_10") or 0),
        "top_on_target": int(summary.get("top_on_target_count") or 0),
        "top_wrong": int(summary.get("top_wrong_count") or 0),
        "found_at_10": found_at_10,
        "expected_concepts": expected_concepts,
        "overall_score": metric_number(summary, "overall_score"),
    }
    for key in (
        "measurement_status",
        "promotion_status",
        "metric_focus",
        "risk_note",
    ):
        if key in lane:
            result[key] = lane[key]
    for key in (
        "found_at_20",
        "found_at_60",
        "queries_all_expected_at_20",
        "strict_success_at_20_count",
        "queries_with_missing_at_10",
        "queries_with_missing_at_20",
        "queries_with_disallowed_at_10",
        "queries_with_disallowed_at_20",
    ):
        value = optional_int(summary, key)
        if value is not None:
            result[key] = value
    if expected_concepts:
        result["missing_concepts_at_10"] = max(0, expected_concepts - found_at_10)
        if found_at_20 is not None:
            result["recovered_by_20"] = max(0, found_at_20 - found_at_10)
            result["missing_concepts_at_20"] = max(0, expected_concepts - found_at_20)
        if found_at_60 is not None:
            result["missing_concepts_at_60"] = max(0, expected_concepts - found_at_60)
    return result


def apply_caps(score: float, lanes: list[dict[str, Any]], caps: list[dict[str, Any]]) -> tuple[float, list[dict[str, Any]]]:
    lane_by_id = {str(lane.get("id")): lane for lane in lanes}
    applied: list[dict[str, Any]] = []
    current = score
    for cap in caps:
        ids = [str(item) for item in cap.get("lane_ids") or []]
        threshold = float(cap.get("below_score") or 0.0)
        minimum = int(cap.get("minimum_count") or len(ids))
        weak = [
            lane_by_id[lane_id]
            for lane_id in ids
            if lane_id in lane_by_id and float(lane_by_id[lane_id].get("score") or 0.0) < threshold
        ]
        if len(weak) < minimum:
            continue
        max_score = float(cap.get("max_score") or current)
        before = current
        current = min(current, max_score)
        applied.append(
            {
                "id": cap.get("id"),
                "label": cap.get("label"),
                "reason": cap.get("reason"),
                "max_score": max_score,
                "active": True,
                "changed_score": current < before,
                "before": round(before, 1),
                "after": round(current, 1),
                "weak_lanes": [lane.get("id") for lane in weak],
            }
        )
    return current, applied


def grade_for_score(score: float) -> str:
    if score >= 90.0:
        return "dependable in reviewed lanes"
    if score >= 80.0:
        return "usable with gaps"
    if score >= 70.0:
        return "usable with material gaps"
    if score >= 60.0:
        return "needs focused repair"
    return "not dependable yet"


def build_scorecard(config: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    lanes = [lane_result(lane, runs) for lane in config.get("lanes") or []]
    total_weight = sum(float(lane.get("weight") or 0.0) for lane in lanes)
    raw_score = (
        sum(float(lane.get("score") or 0.0) * float(lane.get("weight") or 0.0) for lane in lanes) / total_weight
        if total_weight
        else 0.0
    )
    capped_score, caps_applied = apply_caps(raw_score, lanes, config.get("caps") or [])
    score = round(capped_score)
    return {
        "created_at": utc_timestamp(),
        "name": config.get("name") or "Whole Product Quality Scorecard",
        "score": score,
        "score_percent": f"{score}%",
        "grade": grade_for_score(score),
        "raw_weighted_score": round(raw_score, 1),
        "total_weight": round(total_weight, 3),
        "caps_applied": caps_applied,
        "lanes": lanes,
    }


def print_summary(scorecard: dict[str, Any]) -> None:
    print(
        f"{scorecard['name']}: {scorecard['score_percent']} "
        f"({scorecard['grade']}; raw {scorecard['raw_weighted_score']}/100)"
    )
    for lane in scorecard.get("lanes") or []:
        print(
            f"- {lane['id']}: {lane['score']:.1f}/100 x {lane['weight']:.1f}% "
            f"from {lane.get('run_id') or lane['status']}"
        )
    for cap in scorecard.get("caps_applied") or []:
        changed = "capped" if cap.get("changed_score") else "active"
        print(f"- {changed}: {cap['id']} max {cap['max_score']:.1f} ({cap['reason']})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the whole-product quality scorecard from saved run artifacts.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-write", action="store_true", help="Print only; do not write JSON output.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_json(args.config)
    scorecard = build_scorecard(config, iter_runs(args.run_root))
    print_summary(scorecard)
    if not args.no_write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(scorecard, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {repo_path(args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
