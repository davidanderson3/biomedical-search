from __future__ import annotations

import csv
import re
from pathlib import Path

from qe_evidence_vectors.text import normalized_key


REQUIRED_COLUMNS = {
    "cui",
    "label",
    "ispref",
    "sab",
    "tty",
    "semantic_type",
    "field",
    "why",
    "specialty",
    "context_any",
    "block_any",
}

ALLOWED_FIELDS = {
    "assessment",
    "condition",
    "drug",
    "drug_alias",
    "finding",
    "lab",
    "organism",
    "procedure",
}

CUI_PATTERN = re.compile(r"^(?:C\d{7}|NEW\d{7})$")
SHORT_OR_ABBREVIATION_TTYS = {"AB"}


def read_active_label_supplement_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(
            (line for line in handle if line.strip() and not line.lstrip().startswith("#")),
            delimiter="\t",
        )
        columns = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - columns)
        rows = [
            {str(key): str(value or "").strip() for key, value in row.items()}
            for row in reader
        ]
    return rows, missing


def split_pipe_values(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split("|") if part.strip()]


def row_needs_context(row: dict[str, str]) -> bool:
    if row.get("field") == "drug_alias":
        return False
    if str(row.get("ispref") or "").upper() == "Y":
        return False
    tty = str(row.get("tty") or "").upper()
    label_norm = normalized_key(str(row.get("label") or ""))
    label_tokens = label_norm.split()
    return tty in SHORT_OR_ABBREVIATION_TTYS or len(label_norm) <= 5 or len(label_tokens) <= 1


def validate_active_label_supplement_rows(
    rows: list[dict[str, str]],
    *,
    missing_columns: list[str] | None = None,
) -> list[str]:
    issues: list[str] = []
    if missing_columns:
        issues.append(f"Missing required columns: {', '.join(missing_columns)}")

    seen_label_to_cuis: dict[str, set[str]] = {}
    seen_pairs: set[tuple[str, str]] = set()

    for line_number, row in enumerate(rows, start=2):
        prefix = f"row {line_number}"
        cui = str(row.get("cui") or "").strip().upper()
        label = str(row.get("label") or "").strip()
        label_norm = normalized_key(label)
        field = str(row.get("field") or "").strip()
        ispref = str(row.get("ispref") or "").strip().upper()
        why = str(row.get("why") or "").strip()

        if not CUI_PATTERN.fullmatch(cui):
            issues.append(f"{prefix}: invalid CUI {cui!r}")
        if not label:
            issues.append(f"{prefix}: missing label")
        if not label_norm:
            issues.append(f"{prefix}: label does not normalize to searchable text")
        if ispref not in {"Y", "N"}:
            issues.append(f"{prefix}: ispref must be Y or N")
        if not str(row.get("sab") or "").strip():
            issues.append(f"{prefix}: missing sab")
        if not str(row.get("tty") or "").strip():
            issues.append(f"{prefix}: missing tty")
        if not str(row.get("semantic_type") or "").strip():
            issues.append(f"{prefix}: missing semantic_type")
        if field not in ALLOWED_FIELDS:
            issues.append(f"{prefix}: unsupported field {field!r}")
        if len(why) < 24:
            issues.append(f"{prefix}: why must explain the clinical/retrieval reason")

        context_values = split_pipe_values(str(row.get("context_any") or ""))
        block_values = split_pipe_values(str(row.get("block_any") or ""))
        if row_needs_context(row) and not context_values:
            issues.append(
                f"{prefix}: non-preferred short/abbreviation label {label!r} requires context_any"
            )
        if len({normalized_key(value) for value in context_values}) != len(context_values):
            issues.append(f"{prefix}: duplicate context_any value")
        if len({normalized_key(value) for value in block_values}) != len(block_values):
            issues.append(f"{prefix}: duplicate block_any value")

        pair = (cui, label_norm)
        if pair in seen_pairs:
            issues.append(f"{prefix}: duplicate CUI/label pair {cui} {label!r}")
        seen_pairs.add(pair)
        if label_norm:
            seen_label_to_cuis.setdefault(label_norm, set()).add(cui)

    for label_norm, cuis in sorted(seen_label_to_cuis.items()):
        if len(cuis) > 1:
            issues.append(
                f"label {label_norm!r} maps to multiple CUIs: {', '.join(sorted(cuis))}"
            )
    return issues


def validate_active_label_supplement_file(path: Path) -> list[str]:
    rows, missing = read_active_label_supplement_rows(path)
    return validate_active_label_supplement_rows(rows, missing_columns=missing)
