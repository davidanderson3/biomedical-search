#!/usr/bin/env python3
"""Estimate specific UMLS concepts missed by lexical search using 2026AA MRREL."""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict, deque
from pathlib import Path


def read_tsv(path: Path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def cuis(value: str) -> set[str]:
    return {x.strip().upper() for x in value.split("|") if x.strip()}


def load_children(path: Path) -> dict[str, set[str]]:
    children: dict[str, set[str]] = defaultdict(set)
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            cols = line.rstrip("\n").split("|")
            if len(cols) < 8:
                continue
            c1, rel, c2, rela = cols[0].upper(), cols[3], cols[4].upper(), cols[7].lower()
            # Use only explicit ISA hierarchy edges.  Other CHD/PAR and
            # associative relations are intentionally excluded because they
            # create broad, non-specific candidate explosions.
            if rela == "isa":
                children[c1].add(c2)
            elif rela == "inverse_isa":
                children[c2].add(c1)
    return children


def descendants(seed: str, children: dict[str, set[str]], max_depth: int) -> dict[str, int]:
    found: dict[str, int] = {seed: 0}
    queue = deque([(seed, 0)])
    while queue:
        cui, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for child in children.get(cui, ()):
            if child not in found or depth + 1 < found[child]:
                found[child] = depth + 1
                queue.append((child, depth + 1))
    return found


def load_labels(path: Path, wanted: set[str]) -> dict[str, str]:
    labels: dict[str, str] = {}
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            cols = line.rstrip("\n").split("|")
            if len(cols) < 15 or cols[1] != "ENG":
                continue
            cui = cols[0].upper()
            if cui not in wanted or cui in labels:
                continue
            # Prefer a preferred term, then accept the first English term.
            if cols[12] in {"PT", "PN"} or cui not in labels:
                labels[cui] = cols[14]
    return labels


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--baseline-run", type=Path, required=True)
    p.add_argument("--umls-root", type=Path, required=True)
    p.add_argument("--max-depth", type=int, default=2)
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    rows = read_tsv(args.baseline_run / "rows.tsv")
    children = load_children(args.umls_root / "META" / "MRREL.RRF")
    records = []
    wanted: set[str] = set()
    for row in rows:
        baseline = cuis(row.get("umls_hit_cuis", ""))
        semantic = cuis(row.get("vector_cuis", ""))
        # If paired comparison exists, use its semantic CUI list.
        comparison = args.baseline_run / "vector_comparison_top10" / "query_comparisons.tsv"
        if comparison.exists():
            pass
        for seed in baseline:
            for child, depth in descendants(seed, children, args.max_depth).items():
                if child == seed:
                    continue
                wanted.add(child)
                records.append((row, seed, child, depth, child in baseline, child in semantic))
    labels = load_labels(args.umls_root / "META" / "MRCONSO.RRF", wanted)
    out = args.out or args.baseline_run / "specificity_misses.tsv"
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["id", "search_term", "seed_cui", "specific_cui", "specific_label", "depth", "found_by_umls", "found_by_semantic"]
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        w.writeheader()
        for row, seed, child, depth, in_umls, in_semantic in records:
            w.writerow({"id": row["id"], "search_term": row["search_term"], "seed_cui": seed, "specific_cui": child, "specific_label": labels.get(child, ""), "depth": depth, "found_by_umls": int(in_umls), "found_by_semantic": int(in_semantic)})
    total = len(records)
    missed = sum(not r[4] for r in records)
    print(json.dumps({"rows": len(rows), "hierarchical_edges": sum(map(len, children.values())), "specific_candidate_rows": total, "missed_by_umls": missed, "candidate_missed_percentage": round(100 * missed / total, 2) if total else 0, "output": str(out)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
