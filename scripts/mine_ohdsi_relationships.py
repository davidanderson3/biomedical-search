#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qe_evidence_vectors.ohdsi_mining import (  # noqa: E402
    mine_public_ohdsi_artifacts,
    mining_summary,
    write_jsonl,
)


def path_args(values: list[str] | None) -> list[Path]:
    return [Path(value).expanduser() for value in values or []]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Mine public/shareable aggregate OHDSI artifacts into universal "
            "relationship-edge JSONL. Patient-level EHR rows are rejected."
        )
    )
    parser.add_argument("--atlas", action="append", default=[], help="ATLAS cohort JSON export.")
    parser.add_argument(
        "--cohort-diagnostics",
        action="append",
        default=[],
        help="CohortDiagnostics aggregate CSV/TSV/JSON/JSONL output.",
    )
    parser.add_argument(
        "--estimation-results",
        action="append",
        default=[],
        help="CohortMethod/PLE aggregate effect-estimate CSV/TSV/JSON/JSONL output.",
    )
    parser.add_argument(
        "--plp-output",
        action="append",
        default=[],
        help="PatientLevelPrediction aggregate feature-importance CSV/TSV/JSON/JSONL output.",
    )
    parser.add_argument(
        "--literature-study",
        action="append",
        default=[],
        help="Published/shared OHDSI study relationship or result table.",
    )
    parser.add_argument("--omop-cui-map", help="CSV/TSV mapping OMOP concept_id or vocabulary/code to CUI.")
    parser.add_argument("--code-index", help="Existing source-code index SQLite for vocabulary/code to CUI lookup.")
    parser.add_argument("--out", required=True, help="Output relationship edge JSONL path.")
    parser.add_argument("--unresolved-out", help="Optional unresolved concept/row JSONL path.")
    parser.add_argument("--skipped-out", help="Optional skipped aggregate-row JSONL path.")
    parser.add_argument("--summary-out", help="Optional summary JSON path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = mine_public_ohdsi_artifacts(
        atlas_paths=path_args(args.atlas),
        cohort_diagnostics_paths=path_args(args.cohort_diagnostics),
        estimation_result_paths=path_args(args.estimation_results),
        plp_output_paths=path_args(args.plp_output),
        literature_study_paths=path_args(args.literature_study),
        omop_cui_map_path=Path(args.omop_cui_map).expanduser() if args.omop_cui_map else None,
        code_index_path=Path(args.code_index).expanduser() if args.code_index else None,
    )

    write_jsonl(Path(args.out).expanduser(), result.edges)
    if args.unresolved_out:
        write_jsonl(Path(args.unresolved_out).expanduser(), result.unresolved)
    if args.skipped_out:
        write_jsonl(Path(args.skipped_out).expanduser(), result.skipped_rows)

    summary = mining_summary(result)
    if args.summary_out:
        summary_path = Path(args.summary_out).expanduser()
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
