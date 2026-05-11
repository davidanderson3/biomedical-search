from __future__ import annotations

from collections import defaultdict
from pathlib import Path


TTY_PRIORITY = {
    "PT": 0,
    "MH": 1,
    "PN": 2,
    "FN": 3,
    "SY": 4,
}


def _score(fields: list[str]) -> tuple[int, int, int, int, str]:
    ts = fields[2]
    stt = fields[4]
    ispref = fields[6]
    tty = fields[12]
    string = fields[14]
    return (
        0 if ts == "P" else 1,
        0 if stt == "PF" else 1,
        0 if ispref == "Y" else 1,
        TTY_PRIORITY.get(tty, 99),
        string.lower(),
    )


def collect_labels(
    mrconso_path: str | Path,
    cuis: set[str],
    *,
    max_labels: int = 8,
    language: str = "ENG",
    include_suppressed: bool = False,
) -> dict[str, list[str]]:
    candidates: dict[str, list[tuple[tuple[int, int, int, str], str]]] = defaultdict(list)
    with Path(mrconso_path).expanduser().open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("|")
            if len(fields) < 18:
                continue
            cui = fields[0]
            if cui not in cuis or fields[1] != language:
                continue
            if not include_suppressed and fields[16] != "N":
                continue
            string = fields[14].strip()
            if string:
                candidates[cui].append((_score(fields), string))

    labels: dict[str, list[str]] = {}
    for cui, rows in candidates.items():
        seen = set()
        labels[cui] = []
        for _, label in sorted(rows):
            key = label.lower()
            if key in seen:
                continue
            labels[cui].append(label)
            seen.add(key)
            if len(labels[cui]) >= max_labels:
                break
    return labels
