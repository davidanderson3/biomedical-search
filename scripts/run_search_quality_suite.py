from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUITE = ROOT / "config" / "search_quality_suite.json"
DEFAULT_SUITE_OUTPUT_ROOT = ROOT / "build" / "search_quality_suite"
RUNNER = ROOT / "scripts" / "run_search_quality_experiment.py"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_suite_id() -> str:
    return datetime.now(timezone.utc).strftime("SQS-%Y%m%dT%H%M%SZ")


def hpath(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def repo_path(path: str | Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except Exception:
        return str(path)


def safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-._") or "suite"


def command_text(command: list[str] | str) -> str:
    if isinstance(command, str):
        return command
    return shlex.join(str(part) for part in command)


def format_command_template(command: list[str] | str, *, suite_id: str, layer: dict[str, Any]) -> list[str] | str:
    if isinstance(command, str):
        return format_template(command, suite_id=suite_id, layer=layer)
    return [format_template(str(part), suite_id=suite_id, layer=layer) for part in command]


def load_suite(path: Path) -> dict[str, Any]:
    suite = json.loads(path.read_text(encoding="utf-8"))
    if int(suite.get("version") or 0) != 1:
        raise SystemExit(f"unsupported suite version in {repo_path(path)}")
    layers = suite.get("layers")
    if not isinstance(layers, list) or not layers:
        raise SystemExit(f"suite has no layers: {repo_path(path)}")
    ids = [str(layer.get("id") or "") for layer in layers]
    if len(ids) != len(set(ids)):
        raise SystemExit(f"suite layer ids must be unique: {repo_path(path)}")
    return suite


def layer_selected(layer: dict[str, Any], selected_ids: set[str]) -> bool:
    return not selected_ids or str(layer.get("id") or "") in selected_ids


def format_template(value: str, *, suite_id: str, layer: dict[str, Any]) -> str:
    replacements = {
        "{suite_id}": safe_id(suite_id),
        "{layer_id}": safe_id(str(layer.get("id") or "layer")),
    }
    for placeholder, replacement in replacements.items():
        value = value.replace(placeholder, replacement)
    return value


def build_experiment_command(
    layer: dict[str, Any],
    *,
    suite: dict[str, Any],
    suite_id: str,
    base_url: str,
    output_root: Path,
    html_report: Path,
) -> list[str]:
    layer_id = safe_id(str(layer["id"]))
    label = str(layer.get("label") or f"{suite.get('name', 'Search Quality Test Suite')} - {layer_id}")
    run_id = f"{safe_id(suite_id)}-{layer_id}"
    command = [
        sys.executable,
        str(RUNNER),
        "--label",
        label,
        "--run-id",
        run_id,
        "--run-family",
        str(layer.get("run_family") or "custom"),
        "--queries",
        str(hpath(layer["queries"])),
        "--query-limit",
        str(int(layer.get("query_limit", 0))),
        "--query-selection",
        str(layer.get("query_selection") or "first"),
        "--search-system",
        str(layer.get("search_system") or "api"),
        "--scope",
        str(layer.get("scope") or "umls_evidence"),
        "--base-url",
        base_url,
        "--require-api-backend",
        str(layer.get("require_api_backend") or "elasticsearch"),
        "--top-k",
        str(int(layer.get("top_k", 60))),
        "--timeout",
        str(float(layer.get("timeout", 90))),
        "--output-root",
        str(output_root),
        "--html-report",
        str(html_report),
    ]
    seed = str(layer.get("query_rotation_seed") or "").strip()
    if seed:
        command.extend(["--query-rotation-seed", format_template(seed, suite_id=suite_id, layer=layer)])
    if layer.get("include_related"):
        command.append("--include-related")
    if layer.get("include_linked_concepts"):
        command.append("--include-linked-concepts")
    if layer.get("include_search_evidence_items"):
        command.append("--include-search-evidence-items")
    if layer.get("fail_gates"):
        command.append("--fail-gates")
    if layer.get("gate_baseline_run"):
        command.extend(["--gate-baseline-run", str(hpath(layer["gate_baseline_run"]))])
    return command


def command_for_layer(
    layer: dict[str, Any],
    *,
    suite: dict[str, Any],
    suite_id: str,
    base_url: str,
    output_root: Path,
    html_report: Path,
) -> list[str] | str:
    kind = str(layer.get("kind") or "")
    if kind == "command":
        command = layer.get("command")
        if not isinstance(command, (list, str)) or not command:
            raise SystemExit(f"command layer {layer.get('id')} has no command")
        return format_command_template(command, suite_id=suite_id, layer=layer)
    if kind == "search_quality_experiment":
        return build_experiment_command(
            layer,
            suite=suite,
            suite_id=suite_id,
            base_url=base_url,
            output_root=output_root,
            html_report=html_report,
        )
    raise SystemExit(f"unsupported suite layer kind for {layer.get('id')}: {kind}")


def run_command(command: list[str] | str, *, cwd: Path, timeout: float | None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        shell=isinstance(command, str),
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def find_run_json(output_root: Path, run_id: str) -> Path | None:
    manifest_path = output_root / "runs.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for run in reversed(manifest.get("runs") or []):
            if run.get("run_id") == run_id and run.get("run_dir"):
                candidate = Path(run["run_dir"]) / "run.json"
                if candidate.exists():
                    return candidate
    matches = sorted((output_root / "runs").glob(f"{run_id}_*/run.json"))
    return matches[-1] if matches else None


def numeric_value(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate_thresholds(summary: dict[str, Any], thresholds: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for key, expected in sorted(thresholds.items()):
        if key == "source_min_counts_at_10":
            counts = summary.get("source_counts_at_10") or {}
            for source, minimum in sorted((expected or {}).items()):
                actual = int(counts.get(source) or 0)
                passed = actual >= int(minimum)
                checks.append(
                    {
                        "name": f"source_counts_at_10.{source}",
                        "operator": ">=",
                        "expected": int(minimum),
                        "actual": actual,
                        "passed": passed,
                    }
                )
            continue
        if key.startswith("min_"):
            metric = key[4:]
            actual = numeric_value(summary.get(metric))
            expected_value = float(expected)
            checks.append(
                {
                    "name": metric,
                    "operator": ">=",
                    "expected": expected,
                    "actual": actual,
                    "passed": actual is not None and actual >= expected_value,
                }
            )
            continue
        if key.startswith("max_"):
            metric = key[4:]
            actual = numeric_value(summary.get(metric))
            expected_value = float(expected)
            checks.append(
                {
                    "name": metric,
                    "operator": "<=",
                    "expected": expected,
                    "actual": actual,
                    "passed": actual is not None and actual <= expected_value,
                }
            )
            continue
        checks.append(
            {
                "name": key,
                "operator": "unsupported",
                "expected": expected,
                "actual": None,
                "passed": False,
            }
        )
    return checks


def summarize_experiment_run(run: dict[str, Any]) -> str:
    summary = run.get("summary") or {}
    examples = summary.get("paragraphs", "?")
    all_expected = summary.get("queries_all_expected_at_10", "?")
    found = summary.get("found_at_10", "?")
    expected = summary.get("expected_concepts", "?")
    missing = summary.get("queries_with_missing_at_10", "?")
    wrong = summary.get("top_wrong_count", "?")
    return (
        f"{all_expected}/{examples} examples fully found; "
        f"{found}/{expected} expected concepts at top 10; "
        f"{missing} examples missing; {wrong} wrong first results"
    )


def write_text_outputs(suite_dir: Path, result: dict[str, Any]) -> None:
    suite_dir.mkdir(parents=True, exist_ok=True)
    (suite_dir / "suite.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        f"# {result['suite_name']}",
        "",
        f"- Suite ID: `{result['suite_id']}`",
        f"- Created: `{result['created_at']}`",
        f"- Status: `{result['status']}`",
        f"- Fail mode: `{result['fail_on']}`",
        "",
        "## Layers",
        "",
    ]
    for layer in result["layers"]:
        lines.extend(
            [
                f"### {layer['id']}",
                "",
                f"- Signal: {layer.get('signal') or ''}",
                f"- Role: {layer.get('role') or ''}",
                f"- Status: `{layer['status']}`",
                f"- Blocking: `{str(layer.get('blocking')).lower()}`",
                f"- Known weakness: `{str(layer.get('known_weakness')).lower()}`",
                f"- Command: `{layer['command_text']}`",
            ]
        )
        if layer.get("summary_text"):
            lines.append(f"- Result: {layer['summary_text']}")
        if layer.get("weakness_found"):
            lines.append(f"- Weakness found: {layer['weakness_found']}")
        if layer.get("recommended_solution"):
            lines.append(f"- Recommended solution: {layer['recommended_solution']}")
        if layer.get("artifact"):
            lines.append(f"- Artifact: `{layer['artifact']}`")
        failed_checks = [check for check in layer.get("threshold_checks", []) if not check.get("passed")]
        if failed_checks:
            lines.append("- Failed checks:")
            for check in failed_checks:
                lines.append(
                    f"  - `{check['name']}` actual `{check.get('actual')}` "
                    f"{check['operator']} expected `{check.get('expected')}`"
                )
        lines.append("")
    (suite_dir / "suite.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run_suite(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    suite_path = hpath(args.suite)
    suite = load_suite(suite_path)
    suite_id = safe_id(args.suite_id or default_suite_id())
    selected_ids = set(args.only or [])
    suite_layer_ids = {str(layer.get("id") or "") for layer in suite["layers"]}
    unknown_ids = sorted(selected_ids - suite_layer_ids)
    if unknown_ids:
        allowed = ", ".join(sorted(suite_layer_ids))
        raise SystemExit(f"unknown suite layer id(s): {', '.join(unknown_ids)}; allowed: {allowed}")
    base_url = args.base_url or suite.get("default_base_url") or "http://127.0.0.1:8766"
    experiment_output_root = hpath(
        args.experiment_output_root or suite.get("default_output_root") or "build/search_quality_experiments"
    )
    html_report = hpath(args.html_report or suite.get("default_html_report") or "docs/search_quality_experiments.html")
    suite_dir = hpath(args.output_root) / suite_id

    result: dict[str, Any] = {
        "suite_id": suite_id,
        "suite_name": suite.get("name") or "Search Quality Test Suite",
        "suite_path": repo_path(suite_path),
        "created_at": utc_timestamp(),
        "base_url": base_url,
        "dry_run": bool(args.dry_run),
        "fail_on": args.fail_on,
        "status": "planned" if args.dry_run else "passed",
        "layers": [],
    }

    for layer in suite["layers"]:
        if not layer_selected(layer, selected_ids):
            continue
        if args.skip_static and layer.get("kind") == "command":
            continue
        command = command_for_layer(
            layer,
            suite=suite,
            suite_id=suite_id,
            base_url=base_url,
            output_root=experiment_output_root,
            html_report=html_report,
        )
        layer_id = safe_id(str(layer["id"]))
        layer_result: dict[str, Any] = {
            "id": layer_id,
            "kind": layer.get("kind"),
            "signal": layer.get("signal"),
            "role": layer.get("role"),
            "blocking": bool(layer.get("blocking", True)),
            "known_weakness": bool(layer.get("known_weakness", False)),
            "weakness_found": layer.get("weakness_found"),
            "recommended_solution": layer.get("recommended_solution"),
            "command": command if isinstance(command, list) else [command],
            "command_text": command_text(command),
            "status": "planned" if args.dry_run else "running",
        }
        if args.dry_run:
            result["layers"].append(layer_result)
            continue

        stdout_path = suite_dir / f"{layer_id}.stdout.txt"
        stderr_path = suite_dir / f"{layer_id}.stderr.txt"
        suite_dir.mkdir(parents=True, exist_ok=True)
        try:
            completed = run_command(command, cwd=ROOT, timeout=args.command_timeout)
        except subprocess.TimeoutExpired as exc:
            stdout_path.write_text(exc.stdout or "", encoding="utf-8")
            stderr_path.write_text(exc.stderr or "", encoding="utf-8")
            layer_result.update(
                {
                    "exit_code": None,
                    "status": "failed",
                    "error": f"timed out after {args.command_timeout}s",
                    "stdout_path": repo_path(stdout_path),
                    "stderr_path": repo_path(stderr_path),
                }
            )
            result["layers"].append(layer_result)
            continue

        stdout_path.write_text(completed.stdout or "", encoding="utf-8")
        stderr_path.write_text(completed.stderr or "", encoding="utf-8")
        layer_result.update(
            {
                "exit_code": completed.returncode,
                "stdout_path": repo_path(stdout_path),
                "stderr_path": repo_path(stderr_path),
            }
        )

        threshold_checks: list[dict[str, Any]] = []
        if layer.get("kind") == "search_quality_experiment":
            run_id = f"{suite_id}-{layer_id}"
            run_json_path = find_run_json(experiment_output_root, run_id)
            if run_json_path:
                run = json.loads(run_json_path.read_text(encoding="utf-8"))
                threshold_checks = evaluate_thresholds(run.get("summary") or {}, layer.get("thresholds") or {})
                layer_result["artifact"] = repo_path(run_json_path)
                layer_result["summary_text"] = summarize_experiment_run(run)
                layer_result["threshold_checks"] = threshold_checks
            else:
                layer_result["error"] = f"run artifact not found for {run_id}"
                threshold_checks = [{"name": "run_artifact", "operator": "exists", "expected": True, "actual": False, "passed": False}]
                layer_result["threshold_checks"] = threshold_checks
        command_passed = completed.returncode == 0
        thresholds_passed = all(check.get("passed") for check in threshold_checks) if threshold_checks else True
        layer_passed = command_passed and thresholds_passed
        if layer_passed:
            layer_result["status"] = "passed"
        elif layer_result["known_weakness"] and completed.returncode == 0:
            layer_result["status"] = "known_weakness"
        else:
            layer_result["status"] = "failed"
        result["layers"].append(layer_result)

    failed_layers = [layer for layer in result["layers"] if layer["status"] == "failed"]
    known_layers = [layer for layer in result["layers"] if layer["status"] == "known_weakness"]
    if args.dry_run:
        result["status"] = "planned"
        exit_code = 0
    elif args.fail_on == "never":
        result["status"] = "failed" if failed_layers else ("known_weakness" if known_layers else "passed")
        exit_code = 0
    elif args.fail_on == "any":
        result["status"] = "failed" if (failed_layers or known_layers) else "passed"
        exit_code = 1 if failed_layers or known_layers else 0
    else:
        blocking_failures = [layer for layer in failed_layers if layer.get("blocking")]
        result["status"] = (
            "failed"
            if blocking_failures
            else ("nonblocking_failed" if failed_layers else ("known_weakness" if known_layers else "passed"))
        )
        exit_code = 1 if blocking_failures else 0

    write_text_outputs(suite_dir, result)
    print(f"wrote {repo_path(suite_dir / 'suite.json')}")
    print(f"wrote {repo_path(suite_dir / 'suite.md')}")
    print(f"status: {result['status']}")
    return result, exit_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the search quality test suite.")
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--suite-id", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_SUITE_OUTPUT_ROOT)
    parser.add_argument("--experiment-output-root", type=Path)
    parser.add_argument("--html-report", type=Path)
    parser.add_argument("--only", action="append", help="Run only a named suite layer. Repeatable.")
    parser.add_argument("--skip-static", action="store_true", help="Skip command/static layers.")
    parser.add_argument("--dry-run", action="store_true", help="Write the planned suite without executing commands.")
    parser.add_argument(
        "--fail-on",
        choices=["blocking", "any", "never"],
        default="blocking",
        help="Exit nonzero on blocking failures, any failed/known-weakness layer, or never.",
    )
    parser.add_argument("--command-timeout", type=float, default=None)
    return parser.parse_args()


def main() -> int:
    _result, exit_code = run_suite(parse_args())
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
