#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import random
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qe_evidence_vectors.text import normalized_key  # noqa: E402


DEFAULT_INPUT_DIR = ROOT / "clinical-text"
DEFAULT_OUT_DIR = ROOT / "build" / "private_kaggle_clinical_text_probe"
DEFAULT_LABEL_INDEX = ROOT / "build" / "umls_clinical_label_index.sqlite"
DEFAULT_SEMANTIC_TYPES = ROOT / "build" / "umls_semantic_types.sqlite"

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "between",
    "by",
    "can",
    "for",
    "from",
    "had",
    "has",
    "have",
    "in",
    "into",
    "is",
    "it",
    "may",
    "not",
    "of",
    "on",
    "or",
    "our",
    "patients",
    "than",
    "that",
    "the",
    "their",
    "these",
    "this",
    "to",
    "was",
    "were",
    "with",
    "without",
}

EXCLUDED_STY = {
    "Classification",
    "Functional Concept",
    "Geographic Area",
    "Intellectual Product",
    "Language",
    "Occupation or Discipline",
    "Organization",
    "Qualitative Concept",
    "Quantitative Concept",
    "Regulation or Law",
    "Temporal Concept",
}

LOW_VALUE_NORMS = {
    "no effect",
    "pathological processes",
    "several days",
    "signs and symptoms",
    "tumor free",
}
TIME_TOKENS = {"day", "days", "month", "months", "week", "weeks", "year", "years"}


@dataclass(frozen=True)
class AbstractRecord:
    split: str
    row_number: int
    source_label: str
    text: str


def parse_records(input_dir: Path) -> list[AbstractRecord]:
    records: list[AbstractRecord] = []
    for split, filename in (("train", "train.dat"), ("test", "test.dat")):
        path = input_dir / filename
        if not path.exists():
            raise SystemExit(f"missing Kaggle clinical text file: {path}")
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            for row_number, line in enumerate(handle, 1):
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                source_label = ""
                text = line
                if split == "train" and "\t" in line:
                    maybe_label, maybe_text = line.split("\t", 1)
                    if maybe_label.isdigit():
                        source_label = maybe_label
                        text = maybe_text
                records.append(
                    AbstractRecord(
                        split=split,
                        row_number=row_number,
                        source_label=source_label,
                        text=" ".join(text.split()),
                    )
                )
    return records


def select_records(
    records: list[AbstractRecord],
    *,
    train_per_label: int,
    test_records: int,
    seed: int,
) -> list[AbstractRecord]:
    rng = random.Random(seed)
    selected: list[AbstractRecord] = []
    train_by_label: dict[str, list[AbstractRecord]] = defaultdict(list)
    test_rows: list[AbstractRecord] = []
    for record in records:
        if record.split == "train":
            train_by_label[record.source_label or "unlabeled"].append(record)
        elif record.split == "test":
            test_rows.append(record)

    for label in sorted(train_by_label):
        rows = train_by_label[label]
        if len(rows) <= train_per_label:
            selected.extend(rows)
        else:
            selected.extend(rows[index] for index in sorted(rng.sample(range(len(rows)), train_per_label)))

    if len(test_rows) <= test_records:
        selected.extend(test_rows)
    else:
        selected.extend(test_rows[index] for index in sorted(rng.sample(range(len(test_rows)), test_records)))
    return selected


def ngram_counts(text: str, *, max_ngram: int, include_unigrams: bool) -> Counter[str]:
    tokens = normalized_key(text).split()
    counts: Counter[str] = Counter()
    min_ngram = 1 if include_unigrams else 2
    for size in range(min_ngram, max_ngram + 1):
        if size > len(tokens):
            break
        for index in range(0, len(tokens) - size + 1):
            gram_tokens = tokens[index : index + size]
            if not gram_tokens:
                continue
            if size == 1 and (gram_tokens[0] in STOPWORDS or len(gram_tokens[0]) < 6):
                continue
            if size > 1 and (gram_tokens[0] in STOPWORDS or gram_tokens[-1] in STOPWORDS):
                continue
            if all(token in STOPWORDS for token in gram_tokens):
                continue
            counts[" ".join(gram_tokens)] += 1
    return counts


def chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-100000")
    return conn


def semantic_types_for(conn: sqlite3.Connection, cuis: list[str]) -> dict[str, list[str]]:
    if not cuis:
        return {}
    rows_by_cui: dict[str, list[str]] = defaultdict(list)
    unique_cuis = sorted(set(cuis))
    for batch in chunked(unique_cuis, 900):
        placeholders = ",".join("?" for _ in batch)
        query = f"SELECT cui, sty FROM semantic_types WHERE cui IN ({placeholders})"
        for row in conn.execute(query, batch):
            rows_by_cui[str(row["cui"])].append(str(row["sty"]))
    return dict(rows_by_cui)


def low_value_candidate_norm(norm: str) -> bool:
    tokens = norm.split()
    if norm in LOW_VALUE_NORMS:
        return True
    if len(tokens) <= 3 and tokens and tokens[0] == "no":
        return True
    if len(tokens) <= 3 and "free" in tokens:
        return True
    if len(tokens) <= 4 and any(token in TIME_TOKENS for token in tokens):
        if any(any(char.isdigit() for char in token) for token in tokens):
            return True
        if tokens[0] in {"few", "several"}:
            return True
    return False


def label_rows_for(conn: sqlite3.Connection, norms: list[str]) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = []
    for batch in chunked(sorted(set(norms)), 900):
        placeholders = ",".join("?" for _ in batch)
        query = (
            "SELECT norm, cui, label, sab, tty, ispref, suppress "
            f"FROM labels WHERE norm IN ({placeholders})"
        )
        rows.extend(conn.execute(query, batch))
    return rows


def candidate_rows(
    record: AbstractRecord,
    *,
    label_conn: sqlite3.Connection,
    semantic_conn: sqlite3.Connection,
    max_ngram: int,
    include_unigrams: bool,
    max_candidates: int,
) -> tuple[list[dict[str, str]], int]:
    counts = ngram_counts(record.text, max_ngram=max_ngram, include_unigrams=include_unigrams)
    label_rows = label_rows_for(label_conn, list(counts))
    semantic_types = semantic_types_for(semantic_conn, [str(row["cui"]) for row in label_rows])
    best_by_cui: dict[str, dict[str, object]] = {}
    for row in label_rows:
        if str(row["suppress"]).upper() != "N":
            continue
        cui = str(row["cui"])
        stys = semantic_types.get(cui, [])
        if stys and all(sty in EXCLUDED_STY for sty in stys):
            continue
        norm = str(row["norm"])
        if low_value_candidate_norm(norm):
            continue
        token_count = len(norm.split())
        occurrence_count = counts[norm]
        preferred = 1 if str(row["ispref"]).upper() == "Y" else 0
        score = (
            token_count,
            len(norm),
            preferred,
            occurrence_count,
            1 if stys else 0,
        )
        existing = best_by_cui.get(cui)
        if existing and score <= existing["score"]:
            continue
        best_by_cui[cui] = {
            "score": score,
            "cui": cui,
            "label": str(row["label"]),
            "matched_text": norm,
            "semantic_types": "|".join(sorted(set(stys))),
            "source": f"{row['sab']}:{row['tty']}",
        }

    ranked = sorted(best_by_cui.values(), key=lambda item: item["score"], reverse=True)
    rows: list[dict[str, str]] = []
    for item in ranked[:max_candidates]:
        rows.append(
            {
                "cui": str(item["cui"]),
                "label": str(item["label"]),
                "matched_text": str(item["matched_text"]),
                "semantic_types": str(item["semantic_types"]),
                "source": str(item["source"]),
            }
        )
    return rows, len(best_by_cui)


def title_preview(text: str) -> str:
    first_sentence = text.split(". ", 1)[0].strip()
    if len(first_sentence) > 180:
        return first_sentence[:177].rstrip() + "..."
    return first_sentence


def write_outputs(
    *,
    out_dir: Path,
    records: list[AbstractRecord],
    all_records: list[AbstractRecord],
    reviewed_rows: list[dict[str, str]],
    semantic_counter: Counter[str],
    args: argparse.Namespace,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    queue_path = out_dir / "review_queue.tsv"
    summary_path = out_dir / "summary.md"
    with queue_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "id",
            "split",
            "source_label",
            "row_number",
            "candidate_count",
            "candidate_cuis",
            "candidate_labels",
            "candidate_semantic_types",
            "matched_text",
            "title_preview",
            "query",
            "why",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(reviewed_rows)

    split_counts = Counter(record.split for record in all_records)
    sampled_counts = Counter(record.split for record in records)
    train_label_counts = Counter(record.source_label for record in records if record.split == "train")
    with summary_path.open("w", encoding="utf-8") as handle:
        handle.write("# Kaggle Clinical Text Local Probe\n\n")
        handle.write("This is a private/local diagnostic artifact generated from the root `clinical-text/` drop. ")
        handle.write("Do not commit the raw Kaggle text or copy full abstract text into public docs unless the dataset license and redistribution terms are explicitly cleared.\n\n")
        handle.write("## What It Is\n\n")
        handle.write("- The files look like biomedical abstracts, not realistic chart notes.\n")
        handle.write("- `train.dat` has a numeric class label plus abstract text.\n")
        handle.write("- `test.dat` has abstract text without the class label.\n")
        handle.write("- Useful lane: `SQB-002` long-document PubMed/abstract recall shadow review.\n")
        handle.write("- Not useful as direct evidence for `SQB-015` realistic note-format recall.\n\n")
        handle.write("## Counts\n\n")
        handle.write(f"- Parsed train rows: {split_counts.get('train', 0):,}\n")
        handle.write(f"- Parsed test rows: {split_counts.get('test', 0):,}\n")
        handle.write(f"- Sampled train rows: {sampled_counts.get('train', 0):,}\n")
        handle.write(f"- Sampled test rows: {sampled_counts.get('test', 0):,}\n")
        handle.write(f"- Review rows with at least {args.min_candidates} candidate CUIs: {len(reviewed_rows):,}\n")
        handle.write(f"- Train rows sampled per source label: {dict(sorted(train_label_counts.items()))}\n\n")
        handle.write("## Generated Files\n\n")
        handle.write(f"- `{queue_path.relative_to(ROOT)}`: local review queue with candidate CUIs.\n")
        handle.write(f"- `{summary_path.relative_to(ROOT)}`: this summary.\n\n")
        handle.write("## Top Candidate Semantic Types\n\n")
        for sty, count in semantic_counter.most_common(15):
            handle.write(f"- {sty}: {count}\n")
        handle.write("\n## Recommended Use\n\n")
        handle.write("Use `review_queue.tsv` to pick abstracts whose candidate CUIs can be reviewed by a person. ")
        handle.write("Promote only reviewed rows into a checked-in benchmark, and only if the text can be redistributed. ")
        handle.write("Otherwise keep this as a local-only shadow stress set under `build/`.\n")

    print(f"wrote {queue_path}")
    print(f"wrote {summary_path}")


def build_probe(args: argparse.Namespace) -> int:
    input_dir = Path(args.input_dir)
    out_dir = Path(args.out_dir)
    label_index = Path(args.label_index)
    semantic_types = Path(args.semantic_types)
    for path in (input_dir, label_index, semantic_types):
        if not path.exists():
            raise SystemExit(f"missing required path: {path}")

    all_records = parse_records(input_dir)
    sampled = select_records(
        all_records,
        train_per_label=args.train_per_label,
        test_records=args.test_records,
        seed=args.seed,
    )
    label_conn = connect(label_index)
    semantic_conn = connect(semantic_types)
    review_rows: list[dict[str, str]] = []
    semantic_counter: Counter[str] = Counter()
    for record in sampled:
        candidates, candidate_count = candidate_rows(
            record,
            label_conn=label_conn,
            semantic_conn=semantic_conn,
            max_ngram=args.max_ngram,
            include_unigrams=args.include_unigrams,
            max_candidates=args.max_candidates,
        )
        if len(candidates) < args.min_candidates:
            continue
        for candidate in candidates:
            for sty in candidate["semantic_types"].split("|"):
                if sty:
                    semantic_counter[sty] += 1
        record_id = f"kaggle_{record.split}_{record.source_label or 'unlabeled'}_{record.row_number:05d}"
        review_rows.append(
            {
                "id": record_id,
                "split": record.split,
                "source_label": record.source_label,
                "row_number": str(record.row_number),
                "candidate_count": str(candidate_count),
                "candidate_cuis": "|".join(candidate["cui"] for candidate in candidates),
                "candidate_labels": "|".join(candidate["label"] for candidate in candidates),
                "candidate_semantic_types": "|".join(candidate["semantic_types"] for candidate in candidates),
                "matched_text": "|".join(candidate["matched_text"] for candidate in candidates),
                "title_preview": title_preview(record.text),
                "query": record.text,
                "why": "Local Kaggle abstract candidate; review candidate CUIs before promotion.",
            }
        )

    write_outputs(
        out_dir=out_dir,
        records=sampled,
        all_records=all_records,
        reviewed_rows=review_rows,
        semantic_counter=semantic_counter,
        args=args,
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a private review queue from the local Kaggle clinical-text abstract drop."
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--label-index", type=Path, default=DEFAULT_LABEL_INDEX)
    parser.add_argument("--semantic-types", type=Path, default=DEFAULT_SEMANTIC_TYPES)
    parser.add_argument("--train-per-label", type=int, default=8)
    parser.add_argument("--test-records", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260616)
    parser.add_argument("--max-ngram", type=int, default=5)
    parser.add_argument("--max-candidates", type=int, default=8)
    parser.add_argument("--min-candidates", type=int, default=4)
    parser.add_argument("--include-unigrams", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(build_probe(parse_args()))
