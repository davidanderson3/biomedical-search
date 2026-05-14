#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qe_evidence_vectors.source_acquisition_progression import (
    build_progression_manifest,
    read_progression_stages,
    write_progression_json,
    write_progression_markdown,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write and optionally validate a reproducible source-acquisition progression manifest."
    )
    parser.add_argument(
        "--stages",
        type=Path,
        default=ROOT / "config" / "source_acquisition_progression.tsv",
        help="TSV describing progression stages, metrics, artifacts, hypotheses, and decisions.",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=ROOT / "build" / "source_acquisition" / "progression_manifest.json",
    )
    parser.add_argument(
        "--out-md",
        type=Path,
        default=ROOT / "build" / "source_acquisition" / "progression_report.md",
    )
    parser.add_argument(
        "--hash-limit-bytes",
        type=int,
        default=5_000_000,
        help="Hash artifact files up to this size; larger files are inventoried without hashing.",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit nonzero when any stage's decision rule fails or any listed artifact is missing.",
    )
    parser.add_argument(
        "--allow-missing-stage-metrics",
        action="store_true",
        help=(
            "Write a report even when historical stage metric files are absent. "
            "Useful for fresh GitHub clones before local build artifacts exist."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stages = read_progression_stages(args.stages)
    manifest = build_progression_manifest(
        stages,
        root=ROOT,
        stage_config_path=args.stages,
        hash_limit_bytes=args.hash_limit_bytes,
        allow_missing_metrics=args.allow_missing_stage_metrics,
    )
    write_progression_json(manifest, args.out_json)
    write_progression_markdown(manifest, args.out_md)
    print(json.dumps(manifest["summary"], indent=2, sort_keys=True))
    if args.fail_on_regression and (
        manifest["summary"]["rule_failures"] or manifest["summary"]["missing_artifacts"]
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
