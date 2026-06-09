from __future__ import annotations

import csv
from pathlib import Path

from qe_evidence_vectors.code_index import is_cui


def load_display_name_overrides(path: str | Path | None) -> dict[str, str]:
    if not path:
        return {}
    source = Path(path).expanduser()
    if not source.exists():
        return {}
    overrides: dict[str, str] = {}
    with source.open("r", encoding="utf-8", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        delimiter = "\t" if sample.count("\t") >= sample.count(",") else ","
        reader = csv.reader(
            (line for line in handle if line.strip() and not line.lstrip().startswith("#"))
        )
        for row in reader:
            if not row:
                continue
            if len(row) == 1 and delimiter != ",":
                row = row[0].split(delimiter)
            cui = str(row[0] if row else "").strip().upper()
            label = str(row[1] if len(row) > 1 else "").strip()
            if cui == "CUI" or label.lower() in {"label", "display_name", "name"}:
                continue
            if is_cui(cui) and label:
                overrides[cui] = label
    return overrides
