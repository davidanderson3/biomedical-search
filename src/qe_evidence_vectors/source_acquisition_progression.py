from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


METRIC_LIMITS = (5, 10, 20, 60)


@dataclass(frozen=True)
class ProgressionStage:
    group: str
    stage_id: str
    order: int
    label: str
    hypothesis: str
    acquisition_scope: str
    queries: str
    metrics: str
    summary: str
    artifact_paths: tuple[str, ...]
    decision_rule: str
    decision: str
    notes: str


def split_paths(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in str(value or "").split("|") if part.strip())


def read_progression_stages(path: str | Path) -> list[ProgressionStage]:
    path = Path(path).expanduser()
    stages: list[ProgressionStage] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(
            (line for line in handle if line.strip() and not line.lstrip().startswith("#")),
            delimiter="\t",
        )
        for row in reader:
            stages.append(
                ProgressionStage(
                    group=str(row.get("group") or "").strip(),
                    stage_id=str(row.get("stage_id") or "").strip(),
                    order=int(str(row.get("order") or "0")),
                    label=str(row.get("label") or "").strip(),
                    hypothesis=str(row.get("hypothesis") or "").strip(),
                    acquisition_scope=str(row.get("acquisition_scope") or "").strip(),
                    queries=str(row.get("queries") or "").strip(),
                    metrics=str(row.get("metrics") or "").strip(),
                    summary=str(row.get("summary") or "").strip(),
                    artifact_paths=split_paths(str(row.get("artifact_paths") or "")),
                    decision_rule=str(row.get("decision_rule") or "diagnostic").strip() or "diagnostic",
                    decision=str(row.get("decision") or "").strip(),
                    notes=str(row.get("notes") or "").strip(),
                )
            )
    return sorted(stages, key=lambda stage: (stage.group, stage.order, stage.stage_id))


def resolve_path(path: str | Path, *, root: Path) -> Path:
    path = Path(path).expanduser()
    return path if path.is_absolute() else root / path


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def file_manifest(
    path: str | Path,
    *,
    root: Path,
    hash_limit_bytes: int = 5_000_000,
) -> dict[str, Any]:
    resolved = resolve_path(path, root=root)
    try:
        display_path = str(resolved.relative_to(root))
    except ValueError:
        display_path = str(resolved)
    row: dict[str, Any] = {
        "path": display_path,
        "exists": resolved.exists(),
    }
    if not resolved.exists():
        return row
    stat = resolved.stat()
    row["modified_utc"] = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    if resolved.is_dir():
        row["kind"] = "directory"
        row["immediate_entries"] = len(list(resolved.iterdir()))
        return row
    row["kind"] = "file"
    row["bytes"] = stat.st_size
    if stat.st_size <= hash_limit_bytes:
        row["sha256"] = sha256_file(resolved)
        row["hash"] = "sha256"
    else:
        row["hash"] = "skipped_large_file"
    return row


def read_metrics(path: str | Path, *, root: Path) -> dict[str, Any]:
    resolved = resolve_path(path, root=root)
    return json.loads(resolved.read_text(encoding="utf-8"))


def verdict_count(metrics: dict[str, Any], verdict: str) -> int:
    counts = metrics.get("verdict_counts") or {}
    return int(counts.get(verdict, 0) or 0)


def compact_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    expected = int(metrics.get("expected_concepts") or 0)
    row = {
        "paragraphs": int(metrics.get("paragraphs") or 0),
        "expected_concepts": expected,
        "good": verdict_count(metrics, "good"),
        "mixed": verdict_count(metrics, "mixed"),
        "poor": verdict_count(metrics, "poor"),
        "queries_all_expected_at_10": int(metrics.get("queries_all_expected_at_10") or 0),
        "queries_all_expected_at_20": int(metrics.get("queries_all_expected_at_20") or 0),
        "queries_with_disallowed_at_10": int(metrics.get("queries_with_disallowed_at_10") or 0),
        "queries_with_disallowed_at_20": int(metrics.get("queries_with_disallowed_at_20") or 0),
    }
    for limit in METRIC_LIMITS:
        found = int(metrics.get(f"found_at_{limit}") or 0)
        row[f"found_at_{limit}"] = found
        row[f"recall_at_{limit}"] = found / expected if expected else 0.0
    return row


def metric_delta(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    delta: dict[str, Any] = {
        "good": current["good"] - baseline["good"],
        "mixed": current["mixed"] - baseline["mixed"],
        "poor": current["poor"] - baseline["poor"],
        "queries_with_disallowed_at_10": (
            current["queries_with_disallowed_at_10"] - baseline["queries_with_disallowed_at_10"]
        ),
        "queries_with_disallowed_at_20": (
            current["queries_with_disallowed_at_20"] - baseline["queries_with_disallowed_at_20"]
        ),
    }
    for limit in METRIC_LIMITS:
        delta[f"found_at_{limit}"] = current[f"found_at_{limit}"] - baseline[f"found_at_{limit}"]
        delta[f"recall_at_{limit}"] = current[f"recall_at_{limit}"] - baseline[f"recall_at_{limit}"]
    return delta


def evaluate_rule(
    *,
    rule: str,
    current: dict[str, Any],
    baseline: dict[str, Any],
    delta: dict[str, Any],
) -> dict[str, Any]:
    rule = (rule or "diagnostic").strip().lower()
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    if rule == "diagnostic":
        return {"rule": rule, "passed": True, "checks": [{"name": "diagnostic", "passed": True, "detail": "Recorded for learning; not a promotion gate."}]}

    add(
        "no_recall_at_10_regression",
        delta["found_at_10"] >= 0,
        f"found@10 delta {delta['found_at_10']}",
    )
    add(
        "no_disallowed_at_10_regression",
        delta["queries_with_disallowed_at_10"] <= 0,
        f"disallowed@10 query delta {delta['queries_with_disallowed_at_10']}",
    )
    add(
        "no_disallowed_at_20_regression",
        delta["queries_with_disallowed_at_20"] <= 0,
        f"disallowed@20 query delta {delta['queries_with_disallowed_at_20']}",
    )

    if rule in {"no_regression", "promote"}:
        add(
            "no_recall_at_20_regression",
            delta["found_at_20"] >= 0,
            f"found@20 delta {delta['found_at_20']}",
        )

    if rule == "promote":
        add(
            "useful_improvement",
            delta["found_at_20"] > 0 or delta["good"] > 0 or current["mixed"] < baseline["mixed"],
            (
                f"found@20 delta {delta['found_at_20']}, "
                f"good delta {delta['good']}, mixed delta {delta['mixed']}"
            ),
        )
    elif rule != "no_regression":
        add("known_rule", False, f"Unknown decision_rule {rule!r}")

    return {"rule": rule, "passed": all(item["passed"] for item in checks), "checks": checks}


def group_baselines(stage_payloads: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    baselines: dict[str, dict[str, Any]] = {}
    for payload in sorted(stage_payloads, key=lambda item: (item["group"], item["order"])):
        baselines.setdefault(payload["group"], payload)
    return baselines


def is_rejected_decision(decision: str) -> bool:
    return decision.strip().lower() in {"reject", "rejected"}


def build_progression_manifest(
    stages: Iterable[ProgressionStage],
    *,
    root: str | Path,
    stage_config_path: str | Path | None = None,
    hash_limit_bytes: int = 5_000_000,
    allow_missing_metrics: bool = False,
) -> dict[str, Any]:
    root_path = Path(root).expanduser().resolve()
    payloads: list[dict[str, Any]] = []
    skipped_payloads: list[dict[str, Any]] = []
    for stage in stages:
        metrics_path = resolve_path(stage.metrics, root=root_path)
        artifacts = [
            file_manifest(path, root=root_path, hash_limit_bytes=hash_limit_bytes)
            for path in (
                stage.queries,
                stage.metrics,
                stage.summary,
                *stage.artifact_paths,
            )
            if path
        ]
        if not metrics_path.exists() and allow_missing_metrics:
            skipped_payloads.append(
                {
                    "group": stage.group,
                    "stage_id": stage.stage_id,
                    "order": stage.order,
                    "label": stage.label,
                    "hypothesis": stage.hypothesis,
                    "acquisition_scope": stage.acquisition_scope,
                    "decision_rule": stage.decision_rule,
                    "decision": stage.decision,
                    "notes": stage.notes,
                    "metrics_path": stage.metrics,
                    "skip_reason": "missing_metrics",
                    "artifacts": artifacts,
                }
            )
            continue
        raw_metrics = read_metrics(stage.metrics, root=root_path)
        metrics = compact_metrics(raw_metrics)
        payloads.append(
            {
                "group": stage.group,
                "stage_id": stage.stage_id,
                "order": stage.order,
                "label": stage.label,
                "hypothesis": stage.hypothesis,
                "acquisition_scope": stage.acquisition_scope,
                "decision_rule": stage.decision_rule,
                "decision": stage.decision,
                "notes": stage.notes,
                "metrics": metrics,
                "artifacts": artifacts,
            }
        )

    baselines = group_baselines(payloads)
    reference_by_group: dict[str, dict[str, Any]] = {}
    for payload in sorted(payloads, key=lambda item: (item["group"], item["order"])):
        baseline = baselines[payload["group"]]
        previous = reference_by_group.get(payload["group"], baseline)
        baseline_delta = metric_delta(payload["metrics"], baseline["metrics"])
        reference_delta = metric_delta(payload["metrics"], previous["metrics"])
        payload["baseline_stage_id"] = baseline["stage_id"]
        payload["delta_vs_group_baseline"] = baseline_delta
        payload["reference_stage_id"] = previous["stage_id"]
        payload["delta_vs_reference"] = reference_delta
        payload["rule_evaluation"] = evaluate_rule(
            rule=payload["decision_rule"],
            current=payload["metrics"],
            baseline=previous["metrics"],
            delta=reference_delta,
        )
        if not is_rejected_decision(payload["decision"]):
            reference_by_group[payload["group"]] = payload

    stage_config_manifest = (
        file_manifest(stage_config_path, root=root_path, hash_limit_bytes=hash_limit_bytes)
        if stage_config_path
        else None
    )

    groups = []
    for group in sorted({payload["group"] for payload in payloads}):
        group_stages = [payload for payload in payloads if payload["group"] == group]
        final = sorted(group_stages, key=lambda item: item["order"])[-1]
        baseline = baselines[group]
        groups.append(
            {
                "group": group,
                "baseline_stage_id": baseline["stage_id"],
                "final_stage_id": final["stage_id"],
                "stages": len(group_stages),
                "final_delta": final["delta_vs_group_baseline"],
                "final_metrics": final["metrics"],
                "accepted_stages": [
                    item["stage_id"]
                    for item in group_stages
                    if item["decision"].lower() in {"accept", "accepted", "promote", "promoted"}
                ],
                "rejected_stages": [
                    item["stage_id"]
                    for item in group_stages
                    if item["decision"].lower() in {"reject", "rejected"}
                ],
            }
        )

    return {
        "schema": "query-expansion-source-acquisition-progression-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "root": str(root_path),
        "stage_config": stage_config_manifest,
        "summary": {
            "groups": len(groups),
            "stages": len(payloads),
            "skipped_stages": len(skipped_payloads),
            "rule_failures": sum(1 for item in payloads if not item["rule_evaluation"]["passed"]),
            "missing_artifacts": sum(
                1
                for item in payloads
                for artifact in item["artifacts"]
                if not artifact.get("exists")
            )
            + sum(
                1
                for item in skipped_payloads
                for artifact in item["artifacts"]
                if not artifact.get("exists")
            )
            + (1 if stage_config_manifest is not None and not stage_config_manifest.get("exists") else 0),
        },
        "groups": groups,
        "stages": payloads,
        "skipped_stages": skipped_payloads,
    }


def write_progression_json(manifest: dict[str, Any], path: str | Path) -> None:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def progression_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# Source Acquisition Progression",
        "",
        "This report records the measured evidence-acquisition sequence. Each stage has a hypothesis, artifact inventory, benchmark metrics, and a decision gate.",
        "",
        "## Summary",
        "",
        f"- Groups: {manifest['summary']['groups']}",
        f"- Stages: {manifest['summary']['stages']}",
        f"- Skipped stages: {manifest['summary'].get('skipped_stages', 0)}",
        f"- Rule failures: {manifest['summary']['rule_failures']}",
        f"- Missing artifacts: {manifest['summary']['missing_artifacts']}",
        *(
            [f"- Stage config: {manifest['stage_config']['path']}"]
            if manifest.get("stage_config")
            else []
        ),
        "",
        "Decision gates compare each stage with the previous retained stage in the same group. Rejected diagnostic stages are recorded without lowering the next gate. Final group deltas are reported against the group's baseline.",
        "",
        "## Groups",
        "",
        "| Group | Baseline | Final | Final Good/Mixed/Poor | Final Recall@10 | Final Recall@20 | Final Disallowed@10 | Final Found@20 Delta |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for group in manifest["groups"]:
        metrics = group["final_metrics"]
        delta = group["final_delta"]
        lines.append(
            "| {group} | {baseline} | {final} | {good}/{mixed}/{poor} | {recall10:.3f} | {recall20:.3f} | {disallowed10} | {found20_delta:+d} |".format(
                group=group["group"],
                baseline=group["baseline_stage_id"],
                final=group["final_stage_id"],
                good=metrics["good"],
                mixed=metrics["mixed"],
                poor=metrics["poor"],
                recall10=metrics["recall_at_10"],
                recall20=metrics["recall_at_20"],
                disallowed10=metrics["queries_with_disallowed_at_10"],
                found20_delta=delta["found_at_20"],
            )
        )
    lines.extend(["", "## Stages", ""])
    for stage in sorted(manifest["stages"], key=lambda item: (item["group"], item["order"])):
        metrics = stage["metrics"]
        delta = stage["delta_vs_group_baseline"]
        rule = stage["rule_evaluation"]
        lines.extend(
            [
                f"### {stage['group']} / {stage['stage_id']}",
                "",
                f"- Label: {stage['label']}",
                f"- Hypothesis: {stage['hypothesis']}",
                f"- Acquisition scope: {stage['acquisition_scope'] or 'none'}",
                f"- Decision: {stage['decision'] or 'not set'}",
                f"- Rule: {rule['rule']} ({'pass' if rule['passed'] else 'fail'}) vs {stage['reference_stage_id']}",
                f"- Metrics: good/mixed/poor {metrics['good']}/{metrics['mixed']}/{metrics['poor']}; recall@10 {metrics['recall_at_10']:.3f}; recall@20 {metrics['recall_at_20']:.3f}; disallowed@10 {metrics['queries_with_disallowed_at_10']}",
                f"- Delta vs baseline: found@10 {delta['found_at_10']:+d}; found@20 {delta['found_at_20']:+d}; good {delta['good']:+d}; disallowed@10 {delta['queries_with_disallowed_at_10']:+d}",
                f"- Gate delta vs reference: found@10 {stage['delta_vs_reference']['found_at_10']:+d}; found@20 {stage['delta_vs_reference']['found_at_20']:+d}; good {stage['delta_vs_reference']['good']:+d}; disallowed@10 {stage['delta_vs_reference']['queries_with_disallowed_at_10']:+d}",
            ]
        )
        if stage["notes"]:
            lines.append(f"- Notes: {stage['notes']}")
        missing = [artifact["path"] for artifact in stage["artifacts"] if not artifact.get("exists")]
        if missing:
            lines.append(f"- Missing artifacts: {', '.join(missing)}")
        lines.append("")
    skipped_stages = manifest.get("skipped_stages") or []
    if skipped_stages:
        lines.extend(["## Skipped Stages", ""])
        for stage in sorted(skipped_stages, key=lambda item: (item["group"], item["order"])):
            missing = [artifact["path"] for artifact in stage["artifacts"] if not artifact.get("exists")]
            lines.extend(
                [
                    f"### {stage['group']} / {stage['stage_id']}",
                    "",
                    f"- Label: {stage['label']}",
                    f"- Skip reason: {stage['skip_reason']}",
                    f"- Metrics path: {stage['metrics_path']}",
                    f"- Missing artifacts: {', '.join(missing) if missing else 'none'}",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def write_progression_markdown(manifest: dict[str, Any], path: str | Path) -> None:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(progression_markdown(manifest), encoding="utf-8")
