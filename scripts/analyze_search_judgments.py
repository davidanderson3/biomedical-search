#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class FeatureSpec:
    key: str
    label: str
    kind: str
    polarity: int


@dataclass(frozen=True)
class JoinedJudgment:
    run: str
    query: str
    doc_id: str
    cui: str
    grade: str
    name: str
    rank: int | None
    features: dict[str, float]


@dataclass(frozen=True)
class JoinStats:
    judgment_rows: int
    matched_rows: int
    missing_rows: int
    payload_files: int


FEATURES = [
    FeatureSpec("rank_score", "Rank score", "score", 1),
    FeatureSpec("retrieval_score", "Retrieval score", "score", 1),
    FeatureSpec("lexical_component", "Lexical", "boost", 1),
    FeatureSpec("definition_component", "Definition", "boost", 1),
    FeatureSpec("vector_component", "Vector", "boost", 1),
    FeatureSpec("evidence_component", "Evidence", "boost/gap", 1),
    FeatureSpec("evidence_context_component", "Evidence context", "boost", 1),
    FeatureSpec("exact_label_component", "Exact label", "boost", 1),
    FeatureSpec("exact_primary_name_component", "Exact primary name", "boost", 1),
    FeatureSpec("label_fallback_component", "Label match", "boost", 1),
    FeatureSpec("primary_name_component", "Primary name", "boost", 1),
    FeatureSpec("negated_finding_component", "Negated finding", "boost", 1),
    FeatureSpec("semantic_component", "Semantic type", "boost", 1),
    FeatureSpec("mrrel_component", "MRREL relation", "boost", 1),
    FeatureSpec("composite_intent_component", "Composite intent", "boost", 1),
    FeatureSpec("first_statement_component", "First statement", "boost", 1),
    FeatureSpec("local_extension_phrase_component", "Local exact phrase", "boost", 1),
    FeatureSpec("specificity_component", "Specificity", "boost", 1),
    FeatureSpec("generic_penalty", "Generic concept", "penalty", -1),
    FeatureSpec("role_mismatch_penalty", "Role mismatch", "penalty", -1),
    FeatureSpec("numeric_specificity_penalty", "Numeric specificity", "penalty", -1),
    FeatureSpec("numeric_context_fragment_penalty", "Numeric fragment", "penalty", -1),
    FeatureSpec("action_observation_penalty", "Action mismatch", "penalty", -1),
    FeatureSpec("denied_positive_finding_penalty", "Denied positive finding", "penalty", -1),
    FeatureSpec("denied_context_mismatch_penalty", "Denied context mismatch", "penalty", -1),
    FeatureSpec("composite_component_penalty", "Composite component", "penalty", -1),
    FeatureSpec("comparator_arm_penalty", "Comparator arm", "penalty", -1),
    FeatureSpec("sepsis_subtype_penalty", "Subtype mismatch", "penalty", -1),
    FeatureSpec("semantic_fragment_penalty", "Semantic fragment", "penalty", -1),
    FeatureSpec("generic_fragment_penalty", "Generic fragment", "penalty", -1),
    FeatureSpec("normal_exam_fragment_penalty", "Exam fragment", "penalty", -1),
    FeatureSpec("evidence_count", "Evidence count", "diagnostic", 1),
]


GRADE_ORDER = ("relevant", "partial", "wrong")


def normalize_space(value: object) -> str:
    return " ".join(str(value or "").split())


def query_key(value: object) -> str:
    return normalize_space(value).casefold()


def doc_key(value: object) -> str:
    return normalize_space(value)


def cui_key(value: object) -> str:
    return normalize_space(value).upper()


def normalize_grade(value: object) -> str:
    grade = normalize_space(value).casefold()
    if grade in {"relevant", "partial", "wrong"}:
        return grade
    if grade.startswith("rel"):
        return "relevant"
    if grade.startswith("part"):
        return "partial"
    if grade.startswith("wrong") or grade.startswith("no"):
        return "wrong"
    return grade


def json_payloads(path: Path) -> Iterable[dict]:
    if path.suffix == ".jsonl":
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    print(f"warning: skipped malformed JSON in {path}:{line_number}: {exc}", file=sys.stderr)
                    continue
                if isinstance(payload, dict):
                    yield payload
        return

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"warning: skipped malformed JSON in {path}: {exc}", file=sys.stderr)
        return
    if isinstance(payload, dict):
        yield payload


def payload_paths_for_run(run_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for name in ("search_quality_payloads.jsonl", "legacy_search_quality_payloads.jsonl"):
        path = run_dir / name
        if path.exists():
            paths.append(path)
    for dirname in ("review_payloads", "legacy_review_payloads"):
        payload_dir = run_dir / dirname
        if payload_dir.exists():
            paths.extend(sorted(payload_dir.glob("*.json")))
    return paths


def default_judgment_paths(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(root.rglob("*judgments.csv"))


def parse_judgment_paths(args: argparse.Namespace) -> list[Path]:
    paths: list[Path] = []
    for value in args.judgments or []:
        paths.append(Path(value))
    for value in args.runs or []:
        run_dir = Path(value)
        paths.extend(sorted(run_dir.glob("*judgments.csv")))
    if not paths:
        paths = default_judgment_paths(Path(args.root))
    unique: dict[Path, None] = {}
    for path in paths:
        unique[path] = None
    return list(unique)


def build_hit_indexes(payload_paths: Iterable[Path]) -> tuple[dict[tuple[str, str], tuple[dict, int]], dict[tuple[str, str], tuple[dict, int]], int]:
    by_doc: dict[tuple[str, str], tuple[dict, int]] = {}
    by_cui: dict[tuple[str, str], tuple[dict, int]] = {}
    file_count = 0
    for path in payload_paths:
        file_count += 1
        for payload in json_payloads(path):
            query = query_key(payload.get("query"))
            if not query:
                continue
            for rank, hit in enumerate(payload.get("hits") or [], start=1):
                if not isinstance(hit, dict):
                    continue
                doc_id = doc_key(hit.get("doc_id"))
                cui = cui_key(hit.get("cui"))
                if doc_id:
                    by_doc.setdefault((query, doc_id), (hit, rank))
                if cui:
                    by_cui.setdefault((query, cui), (hit, rank))
    return by_doc, by_cui, file_count


def feature_values(hit: dict) -> dict[str, float]:
    breakdown = hit.get("score_breakdown") or {}
    values: dict[str, float] = {}
    for spec in FEATURES:
        if spec.key == "rank_score":
            raw_value = breakdown.get("rank_score", hit.get("rank_score"))
        elif spec.key == "retrieval_score":
            raw_value = breakdown.get("retrieval_score", hit.get("score"))
        elif spec.key == "evidence_count":
            raw_value = hit.get("evidence_count")
        else:
            raw_value = breakdown.get(spec.key)
        try:
            values[spec.key] = float(raw_value or 0.0)
        except (TypeError, ValueError):
            values[spec.key] = 0.0
    return values


def join_judgments(judgment_paths: Iterable[Path]) -> tuple[list[JoinedJudgment], JoinStats]:
    joined: list[JoinedJudgment] = []
    judgment_rows = 0
    missing_rows = 0
    payload_file_count = 0

    for path in judgment_paths:
        if not path.exists():
            print(f"warning: judgment file not found: {path}", file=sys.stderr)
            continue
        payload_paths = payload_paths_for_run(path.parent)
        by_doc, by_cui, file_count = build_hit_indexes(payload_paths)
        payload_file_count += file_count
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                query = normalize_space(row.get("query"))
                grade = normalize_grade(row.get("grade"))
                if not query or grade not in GRADE_ORDER:
                    continue
                judgment_rows += 1
                doc_id = doc_key(row.get("doc_id"))
                cui = cui_key(row.get("cui"))
                hit_and_rank = by_doc.get((query_key(query), doc_id))
                if hit_and_rank is None and cui:
                    hit_and_rank = by_cui.get((query_key(query), cui))
                if hit_and_rank is None:
                    missing_rows += 1
                    continue
                hit, rank = hit_and_rank
                joined.append(
                    JoinedJudgment(
                        run=path.parent.name,
                        query=query,
                        doc_id=doc_id,
                        cui=cui,
                        grade=grade,
                        name=normalize_space(hit.get("name") or hit.get("label") or ""),
                        rank=rank,
                        features=feature_values(hit),
                    )
                )

    return joined, JoinStats(
        judgment_rows=judgment_rows,
        matched_rows=len(joined),
        missing_rows=missing_rows,
        payload_files=payload_file_count,
    )


def mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def summarize(rows: list[JoinedJudgment]) -> list[dict]:
    summaries = []
    for spec in FEATURES:
        values_by_grade = {
            grade: [row.features.get(spec.key, 0.0) for row in rows if row.grade == grade]
            for grade in GRADE_ORDER
        }
        nonwrong_values = values_by_grade["relevant"] + values_by_grade["partial"]
        nonwrong_mean = mean(nonwrong_values)
        wrong_mean = mean(values_by_grade["wrong"])
        raw_gap = nonwrong_mean - wrong_mean
        directional_gap = raw_gap if spec.polarity > 0 else -raw_gap
        nonzero = sum(1 for row in rows if abs(row.features.get(spec.key, 0.0)) > 1e-12)
        summaries.append(
            {
                "key": spec.key,
                "label": spec.label,
                "kind": spec.kind,
                "polarity": spec.polarity,
                "judged": len(rows),
                "nonzero": nonzero,
                "mean_relevant": mean(values_by_grade["relevant"]),
                "mean_partial": mean(values_by_grade["partial"]),
                "mean_wrong": wrong_mean,
                "mean_nonwrong": nonwrong_mean,
                "raw_gap": raw_gap,
                "directional_gap": directional_gap,
            }
        )
    return summaries


def sorted_summaries(summaries: list[dict], sort_mode: str) -> list[dict]:
    if sort_mode == "component":
        return summaries
    if sort_mode == "risky":
        return sorted(summaries, key=lambda row: (row["directional_gap"], -row["mean_wrong"], row["label"]))
    return sorted(summaries, key=lambda row: (-row["directional_gap"], row["label"]))


def fmt(value: float) -> str:
    return f"{value:.3f}"


def print_tsv(summaries: list[dict], stats: JoinStats, *, show_zero: bool) -> None:
    writer = csv.writer(sys.stdout, delimiter="\t", lineterminator="\n")
    writer.writerow(["judgment_rows", stats.judgment_rows])
    writer.writerow(["matched_rows", stats.matched_rows])
    writer.writerow(["missing_rows", stats.missing_rows])
    writer.writerow(["payload_files", stats.payload_files])
    writer.writerow([])
    writer.writerow(
        [
            "feature",
            "kind",
            "judged",
            "nonzero",
            "mean_relevant",
            "mean_partial",
            "mean_wrong",
            "mean_nonwrong",
            "nonwrong_minus_wrong",
            "directional_gap",
        ]
    )
    for row in summaries:
        if not show_zero and row["nonzero"] == 0:
            continue
        writer.writerow(
            [
                row["label"],
                row["kind"],
                row["judged"],
                row["nonzero"],
                fmt(row["mean_relevant"]),
                fmt(row["mean_partial"]),
                fmt(row["mean_wrong"]),
                fmt(row["mean_nonwrong"]),
                fmt(row["raw_gap"]),
                fmt(row["directional_gap"]),
            ]
        )


def examples_for_feature(
    rows: list[JoinedJudgment],
    key: str,
    *,
    grades: set[str],
    limit: int,
) -> list[JoinedJudgment]:
    candidates = [
        row
        for row in rows
        if row.grade in grades and abs(row.features.get(key, 0.0)) > 1e-12
    ]
    return sorted(candidates, key=lambda row: row.features.get(key, 0.0), reverse=True)[:limit]


def example_text(row: JoinedJudgment, key: str) -> str:
    value = row.features.get(key, 0.0)
    rank = "" if row.rank is None else f" rank {row.rank},"
    name = row.name or row.cui or row.doc_id
    return f"{fmt(value)} - {row.grade},{rank} {row.cui} {name} | {row.query}"


def print_markdown(
    summaries: list[dict],
    rows: list[JoinedJudgment],
    stats: JoinStats,
    *,
    examples: int,
    max_example_features: int,
    show_zero: bool,
) -> None:
    print("# Search Judgment Signal Report")
    print()
    print(
        f"Loaded {stats.judgment_rows} judged rows; matched {stats.matched_rows} to saved payload hits; "
        f"{stats.missing_rows} were missing from {stats.payload_files} payload files."
    )
    print()
    print(
        "Positive `directional gap` means the signal is separating in the expected direction: "
        "boosts are higher on relevant/partial rows, while penalties are higher on wrong rows."
    )
    print()
    print("| Feature | Type | Nonzero | Relevant avg | Partial avg | Wrong avg | Nonwrong - wrong | Directional gap |")
    print("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    visible = 0
    for row in summaries:
        if not show_zero and row["nonzero"] == 0:
            continue
        visible += 1
        print(
            f"| {row['label']} | {row['kind']} | {row['nonzero']} | "
            f"{fmt(row['mean_relevant'])} | {fmt(row['mean_partial'])} | {fmt(row['mean_wrong'])} | "
            f"{fmt(row['raw_gap'])} | {fmt(row['directional_gap'])} |"
        )
    if visible == 0:
        print("| No nonzero features found | | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |")

    if examples <= 0 or not rows:
        return

    risky_boosts = [
        row
        for row in summaries
        if row["kind"] in {"boost", "boost/gap", "score", "diagnostic"}
        and row["nonzero"] > 0
        and row["directional_gap"] <= 0.02
    ]
    risky_penalties = [
        row
        for row in summaries
        if row["kind"] == "penalty" and row["nonzero"] > 0 and row["directional_gap"] <= 0.02
    ]
    risky = (risky_boosts + risky_penalties)[:max_example_features]
    if not risky:
        return

    print()
    print("## Tuning Checks")
    for summary in risky:
        grades = {"wrong"} if summary["polarity"] > 0 else {"relevant", "partial"}
        examples_rows = examples_for_feature(rows, summary["key"], grades=grades, limit=examples)
        if not examples_rows:
            continue
        print()
        print(f"### {summary['label']}")
        for row in examples_rows:
            print(f"- {example_text(row, summary['key'])}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Join saved search judgments to result score_breakdowns and summarize signal separation."
    )
    parser.add_argument(
        "--root",
        default="build/scaling_runs",
        help="Root used for default *judgments.csv discovery.",
    )
    parser.add_argument(
        "--runs",
        action="append",
        help="Run directory to analyze. May be repeated. Defaults to all runs under --root.",
    )
    parser.add_argument(
        "--judgments",
        action="append",
        help="Judgment CSV path to analyze. May be repeated.",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "tsv"),
        default="markdown",
        help="Output format.",
    )
    parser.add_argument(
        "--sort",
        choices=("useful", "risky", "component"),
        default="useful",
        help="Sort feature rows by useful directional gap, risky low/negative gap, or component order.",
    )
    parser.add_argument(
        "--show-zero",
        action="store_true",
        help="Show features that are zero or absent in all matched payloads.",
    )
    parser.add_argument(
        "--examples",
        type=int,
        default=3,
        help="Examples per risky feature in markdown output. Use 0 to disable.",
    )
    parser.add_argument(
        "--max-example-features",
        type=int,
        default=4,
        help="Maximum risky features to illustrate in markdown output.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    judgment_paths = parse_judgment_paths(args)
    if not judgment_paths:
        print(f"error: no judgment files found under {args.root}", file=sys.stderr)
        return 2

    rows, stats = join_judgments(judgment_paths)
    if not rows:
        print("error: no judged rows matched saved payload hits", file=sys.stderr)
        return 2

    summaries = sorted_summaries(summarize(rows), args.sort)
    if args.format == "tsv":
        print_tsv(summaries, stats, show_zero=args.show_zero)
    else:
        print_markdown(
            summaries,
            rows,
            stats,
            examples=max(args.examples, 0),
            max_example_features=max(args.max_example_features, 0),
            show_zero=args.show_zero,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
