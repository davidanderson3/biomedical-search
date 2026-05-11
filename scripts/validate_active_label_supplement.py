#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qe_evidence_vectors.active_label_supplement import validate_active_label_supplement_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate curated active-label supplement rows.")
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=ROOT / "config" / "active_label_supplement.tsv",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    issues = validate_active_label_supplement_file(args.path)
    if issues:
        for issue in issues:
            print(issue, file=sys.stderr)
        return 1
    print(f"active label supplement ok: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
