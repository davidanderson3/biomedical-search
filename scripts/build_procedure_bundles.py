#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qe_evidence_vectors.procedure_bundles import (  # noqa: E402
    build_procedure_bundle_artifacts,
    validate_private_cpt_adapter,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build public procedure-bundle extension concepts and relations from "
            "open/permitted procedure sources. CPT content is rejected from public outputs."
        )
    )
    parser.add_argument("--input", required=True, help="Input procedure bundle JSONL/JSON/CSV/TSV.")
    parser.add_argument("--out-concepts", required=True, help="Output extension-concept JSONL.")
    parser.add_argument("--out-relations", required=True, help="Output procedure relation JSONL.")
    parser.add_argument("--out-registry", help="Optional registry JSONL.")
    snomed_group = parser.add_mutually_exclusive_group()
    snomed_group.add_argument(
        "--allow-snomed",
        dest="allow_snomed",
        action="store_true",
        default=True,
        help="Allow SNOMED CT anchors. This is the default.",
    )
    snomed_group.add_argument(
        "--no-snomed",
        dest="allow_snomed",
        action="store_false",
        help="Reject SNOMED CT anchors for deployments that cannot include them.",
    )
    parser.add_argument(
        "--private-cpt-adapter",
        help=(
            "Optional private CPT adapter file to validate. It is never copied "
            "into public outputs and must be code-only with no descriptors."
        ),
    )
    parser.add_argument("--summary-out", help="Optional summary JSON path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = build_procedure_bundle_artifacts(
        input_path=args.input,
        out_concepts=args.out_concepts,
        out_relations=args.out_relations,
        out_registry=args.out_registry,
        allow_snomed=args.allow_snomed,
    )
    if args.private_cpt_adapter:
        summary.update(validate_private_cpt_adapter(args.private_cpt_adapter))
        summary["private_cpt_adapter_policy"] = "validated_only_not_written_to_public_outputs"
    if args.summary_out:
        path = Path(args.summary_out).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
