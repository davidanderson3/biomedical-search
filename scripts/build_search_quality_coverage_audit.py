#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qe_evidence_vectors.search_semantics import (  # noqa: E402
    SEMANTIC_GROUP_LABELS,
    semantic_group_from_types,
)


DEFAULT_SOURCE_FILES = (
    "config/search_quality_real_query_regression.tsv",
    "config/search_quality_paragraph_queries.tsv",
    "config/search_quality_patient_portal_queries.tsv",
    "config/search_quality_clinical_text_variety_queries.tsv",
    "config/search_quality_consumer_lay_queries.tsv",
    "config/search_quality_source_specific_queries.tsv",
    "config/search_quality_judgments.tsv",
    "config/search_quality_wrong_first_noise_ledger.tsv",
    "config/search_quality_external_embedding_neighbor_probe.tsv",
    "build/pubmed_literature_benchmark_seed/pubmed_literature_approved_queries.tsv",
    "build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_queries.tsv",
)
DEFAULT_SEMANTIC_TYPE_INDEX = ROOT / "build" / "umls_semantic_types.sqlite"
DEFAULT_LABEL_INDEX = ROOT / "build" / "umls_biomedicine_search_label_index.sqlite"
DEFAULT_OUT_DIR = ROOT / "build" / "search_quality_coverage_audit" / "latest"
TARGET_ROLES = {
    "expected",
    "active_expected",
    "context_expected",
    "positive_neighbor",
    "source_anchor",
}
RISK_ROLES = {
    "disallowed",
    "true_false_positive",
    "observed_wrong_first",
    "disallowed_default",
}
SUPPORTING_ROLES = {
    "useful_extra",
}
CORE_GROUP_ORDER = (
    "DISO",
    "CHEM",
    "PROC",
    "OBS",
    "GENE",
    "LIVB",
    "DEVI",
    "ANAT",
    "PHEN",
    "PHYS",
)


@dataclass(frozen=True)
class ConceptRecord:
    source_id: str
    source_path: str
    row_id: str
    role: str
    cui: str
    query: str = ""
    note: str = ""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def repo_path(path: str | Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except Exception:
        return str(path)


def hpath(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def source_id_for_path(path: Path) -> str:
    name = path.name
    if name.endswith(".tsv"):
        name = name[:-4]
    return name.replace(".", "_")


def split_cuis(value: object) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    cuis: list[str] = []
    for part in text.replace(",", "|").split("|"):
        cui = part.strip()
        if not cui:
            continue
        if cui.startswith("C") or cui.startswith("NEW"):
            cuis.append(cui)
    return cuis


def row_query(row: dict[str, str]) -> str:
    return str(row.get("query") or row.get("regression_query") or row.get("source_label") or "")


def records_from_row(
    row: dict[str, str],
    *,
    source_id: str,
    source_path: str,
    row_number: int,
) -> Iterable[ConceptRecord]:
    row_id = str(row.get("id") or row.get("ledger_id") or row.get("query_id") or f"row_{row_number}")
    query = row_query(row)
    note = str(row.get("why") or row.get("notes") or "")

    judgment = str(row.get("judgment") or "").strip()
    if row.get("cui") and judgment:
        role = judgment
        if judgment in {"expected", "active_expected", "context_expected", "disallowed", "true_false_positive", "useful_extra"}:
            yield ConceptRecord(source_id, source_path, row_id, role, row["cui"], query, note)

    for cui in split_cuis(row.get("expected_cuis")):
        yield ConceptRecord(source_id, source_path, row_id, "expected", cui, query, note)
    for cui in split_cuis(row.get("disallowed_cuis")):
        yield ConceptRecord(source_id, source_path, row_id, "disallowed", cui, query, note)
    for cui in split_cuis(row.get("expected_top_cui")):
        yield ConceptRecord(source_id, source_path, row_id, "expected", cui, query, note)
    for cui in split_cuis(row.get("actual_top_cui")):
        yield ConceptRecord(source_id, source_path, row_id, "observed_wrong_first", cui, query, note)
    for cui in split_cuis(row.get("source_cui")):
        yield ConceptRecord(source_id, source_path, row_id, "source_anchor", cui, query, note)
    for cui in split_cuis(row.get("positive_neighbor_cuis")):
        yield ConceptRecord(source_id, source_path, row_id, "positive_neighbor", cui, query, note)
    for cui in split_cuis(row.get("disallowed_default_cuis")):
        yield ConceptRecord(source_id, source_path, row_id, "disallowed_default", cui, query, note)


def records_from_source(path: Path) -> list[ConceptRecord]:
    source_id = source_id_for_path(path)
    source_path = repo_path(path)
    records: list[ConceptRecord] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row_number, row in enumerate(reader, start=1):
            records.extend(
                records_from_row(
                    row,
                    source_id=source_id,
                    source_path=source_path,
                    row_number=row_number,
                )
            )
    return records


def readonly_sqlite(path: Path) -> sqlite3.Connection | None:
    if not path.exists():
        return None
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def semantic_types_for_cui(conn: sqlite3.Connection | None, cui: str) -> list[dict[str, str]]:
    if cui.startswith("NEW"):
        return [{"name": "Local Extension Concept", "tui": "LOCAL"}]
    if conn is None:
        return []
    rows = conn.execute(
        """
        SELECT tui, stn, sty, atui
        FROM semantic_types
        WHERE cui = ?
        ORDER BY tui, sty
        """,
        (cui,),
    )
    return [
        {
            "tui": str(row["tui"]),
            "stn": str(row["stn"]),
            "name": str(row["sty"]),
            "atui": str(row["atui"]),
        }
        for row in rows
    ]


def semantic_group_for_types(types: list[dict[str, str]], cui: str) -> str:
    if cui.startswith("NEW"):
        return "LOCAL"
    return semantic_group_from_types(types)


def label_for_cui(conn: sqlite3.Connection | None, cui: str) -> str:
    if conn is None or cui.startswith("NEW"):
        return ""
    rows = conn.execute(
        """
        SELECT label, sab, tty, ispref, suppress
        FROM labels
        WHERE cui = ?
        ORDER BY
            CASE WHEN suppress = 'N' THEN 0 ELSE 1 END,
            CASE WHEN ispref = 'Y' THEN 0 ELSE 1 END,
            CASE tty
                WHEN 'PT' THEN 0
                WHEN 'PN' THEN 1
                WHEN 'MH' THEN 2
                WHEN 'SY' THEN 3
                ELSE 4
            END,
            LENGTH(label),
            label
        LIMIT 1
        """,
        (cui,),
    ).fetchone()
    return str(rows["label"]) if rows else ""


def summarize(records: list[ConceptRecord], *, semantic_conn: sqlite3.Connection | None, label_conn: sqlite3.Connection | None) -> dict:
    concept_roles: dict[tuple[str, str], dict] = {}
    unique_cuis = {record.cui for record in records}
    concept_metadata: dict[str, dict] = {}
    for cui in sorted(unique_cuis):
        types = semantic_types_for_cui(semantic_conn, cui)
        group = semantic_group_for_types(types, cui)
        concept_metadata[cui] = {
            "cui": cui,
            "label": label_for_cui(label_conn, cui),
            "semantic_group": group,
            "semantic_group_label": SEMANTIC_GROUP_LABELS.get(group, "Local Extension Concepts" if group == "LOCAL" else "Other"),
            "semantic_types": [str(item.get("name") or "") for item in types],
        }

    by_group: dict[str, dict] = defaultdict(lambda: {
        "semantic_group": "",
        "semantic_group_label": "",
        "target_mentions": 0,
        "unique_target_cuis": set(),
        "risk_mentions": 0,
        "unique_risk_cuis": set(),
        "supporting_mentions": 0,
        "unique_supporting_cuis": set(),
        "source_ids": set(),
    })
    by_source: dict[str, dict] = defaultdict(lambda: {
        "source_id": "",
        "source_path": "",
        "record_count": 0,
        "target_mentions": 0,
        "unique_target_cuis": set(),
        "risk_mentions": 0,
        "unique_risk_cuis": set(),
        "semantic_groups": Counter(),
    })

    for record in records:
        metadata = concept_metadata[record.cui]
        role_key = (record.role, record.cui)
        role_row = concept_roles.setdefault(
            role_key,
            {
                **metadata,
                "role": record.role,
                "mention_count": 0,
                "source_ids": set(),
                "row_ids": set(),
                "example_queries": [],
            },
        )
        role_row["mention_count"] += 1
        role_row["source_ids"].add(record.source_id)
        role_row["row_ids"].add(record.row_id)
        if record.query and len(role_row["example_queries"]) < 3:
            role_row["example_queries"].append(record.query[:240])

        group_row = by_group[metadata["semantic_group"]]
        group_row["semantic_group"] = metadata["semantic_group"]
        group_row["semantic_group_label"] = metadata["semantic_group_label"]
        group_row["source_ids"].add(record.source_id)

        source_row = by_source[record.source_id]
        source_row["source_id"] = record.source_id
        source_row["source_path"] = record.source_path
        source_row["record_count"] += 1
        source_row["semantic_groups"][metadata["semantic_group"]] += 1

        if record.role in TARGET_ROLES:
            group_row["target_mentions"] += 1
            group_row["unique_target_cuis"].add(record.cui)
            source_row["target_mentions"] += 1
            source_row["unique_target_cuis"].add(record.cui)
        elif record.role in RISK_ROLES:
            group_row["risk_mentions"] += 1
            group_row["unique_risk_cuis"].add(record.cui)
            source_row["risk_mentions"] += 1
            source_row["unique_risk_cuis"].add(record.cui)
        elif record.role in SUPPORTING_ROLES:
            group_row["supporting_mentions"] += 1
            group_row["unique_supporting_cuis"].add(record.cui)

    group_rows = []
    for row in by_group.values():
        group_rows.append(
            {
                "semantic_group": row["semantic_group"],
                "semantic_group_label": row["semantic_group_label"],
                "target_mentions": row["target_mentions"],
                "unique_target_cuis": len(row["unique_target_cuis"]),
                "risk_mentions": row["risk_mentions"],
                "unique_risk_cuis": len(row["unique_risk_cuis"]),
                "supporting_mentions": row["supporting_mentions"],
                "unique_supporting_cuis": len(row["unique_supporting_cuis"]),
                "source_count": len(row["source_ids"]),
                "source_ids": sorted(row["source_ids"]),
            }
        )
    existing_groups = {row["semantic_group"] for row in group_rows}
    for group in CORE_GROUP_ORDER:
        if group in existing_groups:
            continue
        group_rows.append(
            {
                "semantic_group": group,
                "semantic_group_label": SEMANTIC_GROUP_LABELS.get(group, "Other"),
                "target_mentions": 0,
                "unique_target_cuis": 0,
                "risk_mentions": 0,
                "unique_risk_cuis": 0,
                "supporting_mentions": 0,
                "unique_supporting_cuis": 0,
                "source_count": 0,
                "source_ids": [],
            }
        )
    group_rows.sort(key=lambda item: (-int(item["unique_target_cuis"]), str(item["semantic_group"])))

    source_rows = []
    for row in by_source.values():
        source_rows.append(
            {
                "source_id": row["source_id"],
                "source_path": row["source_path"],
                "record_count": row["record_count"],
                "target_mentions": row["target_mentions"],
                "unique_target_cuis": len(row["unique_target_cuis"]),
                "risk_mentions": row["risk_mentions"],
                "unique_risk_cuis": len(row["unique_risk_cuis"]),
                "semantic_groups": dict(sorted(row["semantic_groups"].items())),
            }
        )
    source_rows.sort(key=lambda item: (-int(item["unique_target_cuis"]), str(item["source_id"])))

    concept_rows = []
    for row in concept_roles.values():
        concept_rows.append(
            {
                **{key: value for key, value in row.items() if key not in {"source_ids", "row_ids"}},
                "source_ids": sorted(row["source_ids"]),
                "row_ids": sorted(row["row_ids"]),
            }
        )
    concept_rows.sort(key=lambda item: (str(item["role"]), str(item["semantic_group"]), -int(item["mention_count"]), str(item["cui"])))

    total_target_mentions = sum(row["target_mentions"] for row in group_rows)
    unique_target_cuis = {
        record.cui for record in records if record.role in TARGET_ROLES
    }
    thin_core_groups = [
        group
        for group in CORE_GROUP_ORDER
        if next((row["unique_target_cuis"] for row in group_rows if row["semantic_group"] == group), 0) < 5
    ]
    largest_group = max(group_rows, key=lambda row: int(row["target_mentions"]), default={})
    largest_share = (
        float(largest_group.get("target_mentions") or 0) / float(total_target_mentions)
        if total_target_mentions
        else 0.0
    )

    return {
        "created_at": utc_now(),
        "source_files": sorted({record.source_path for record in records}),
        "record_count": len(records),
        "target_mentions": total_target_mentions,
        "unique_target_cuis": len(unique_target_cuis),
        "risk_mentions": sum(row["risk_mentions"] for row in group_rows),
        "unique_risk_cuis": len({record.cui for record in records if record.role in RISK_ROLES}),
        "group_rows": group_rows,
        "source_rows": source_rows,
        "concept_rows": concept_rows,
        "thin_core_groups": thin_core_groups,
        "largest_group": largest_group.get("semantic_group", ""),
        "largest_group_share": round(largest_share, 4),
        "interpretation": (
            "This audit measures which concepts the search-quality tests target. "
            "It is not a prevalence-weighted clinical usage model and does not prove broad clinical coverage."
        ),
    }


def write_tsv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: json.dumps(row[field]) if isinstance(row.get(field), (list, dict)) else row.get(field, "") for field in fields})


def write_markdown(path: Path, summary: dict) -> None:
    group_lines = []
    for row in summary["group_rows"][:12]:
        group_lines.append(
            f"| {row['semantic_group']} | {row['semantic_group_label']} | {row['unique_target_cuis']} | {row['target_mentions']} | {row['unique_risk_cuis']} |"
        )
    source_lines = []
    for row in summary["source_rows"][:12]:
        source_lines.append(
            f"| `{row['source_id']}` | {row['unique_target_cuis']} | {row['target_mentions']} | {row['unique_risk_cuis']} |"
        )
    thin = ", ".join(f"`{group}`" for group in summary["thin_core_groups"]) or "none"
    path.write_text(
        "\n".join(
            [
                "# Search Quality Coverage Audit",
                "",
                f"Created: {summary['created_at']}",
                "",
                "This audit measures the concepts our current search-quality tests ask the system to retrieve. It does not measure clinical prevalence, production query frequency, or full UMLS coverage.",
                "",
                "## Headline",
                "",
                f"- Unique target CUIs: {summary['unique_target_cuis']}",
                f"- Target mentions across test rows: {summary['target_mentions']}",
                f"- Unique risk/disallowed CUIs: {summary['unique_risk_cuis']}",
                f"- Largest target group: `{summary['largest_group']}` ({summary['largest_group_share']:.1%} of target mentions)",
                f"- Thin core groups with fewer than 5 unique target CUIs: {thin}",
                "",
                "## Semantic Group Coverage",
                "",
                "| Group | Label | Unique target CUIs | Target mentions | Unique risk CUIs |",
                "| --- | --- | ---: | ---: | ---: |",
                *group_lines,
                "",
                "## Source File Coverage",
                "",
                "| Source | Unique target CUIs | Target mentions | Unique risk CUIs |",
                "| --- | ---: | ---: | ---: |",
                *source_lines,
                "",
                "## Interpretation",
                "",
                "The search index itself can retrieve far more concepts than this audit lists. The audit is about evaluation coverage: which concepts we have chosen to assert in tests. A green result on the current suite should therefore be treated as evidence for these sampled slices, not as proof that common clinical concept coverage is complete.",
                "",
                "Next useful step: add a prevalence- or workflow-weighted target list for common diagnoses, drugs, labs, procedures, organisms, devices, anatomy, and patient wording, then keep that list separate from one-off regression rows.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def build_audit(
    *,
    source_files: list[Path],
    semantic_type_index: Path,
    label_index: Path,
    out_dir: Path,
) -> dict:
    records: list[ConceptRecord] = []
    skipped: list[str] = []
    for path in source_files:
        path = hpath(path)
        if not path.exists():
            skipped.append(repo_path(path))
            continue
        records.extend(records_from_source(path))
    semantic_conn = readonly_sqlite(hpath(semantic_type_index))
    label_conn = readonly_sqlite(hpath(label_index))
    try:
        summary = summarize(records, semantic_conn=semantic_conn, label_conn=label_conn)
    finally:
        if semantic_conn is not None:
            semantic_conn.close()
        if label_conn is not None:
            label_conn.close()
    summary["skipped_source_files"] = skipped
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "coverage_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_tsv(
        out_dir / "coverage_by_group.tsv",
        summary["group_rows"],
        [
            "semantic_group",
            "semantic_group_label",
            "unique_target_cuis",
            "target_mentions",
            "unique_risk_cuis",
            "risk_mentions",
            "source_count",
            "source_ids",
        ],
    )
    write_tsv(
        out_dir / "coverage_by_source.tsv",
        summary["source_rows"],
        [
            "source_id",
            "source_path",
            "unique_target_cuis",
            "target_mentions",
            "unique_risk_cuis",
            "risk_mentions",
            "semantic_groups",
        ],
    )
    write_tsv(
        out_dir / "coverage_concepts.tsv",
        summary["concept_rows"],
        [
            "role",
            "cui",
            "label",
            "semantic_group",
            "semantic_group_label",
            "semantic_types",
            "mention_count",
            "source_ids",
            "row_ids",
            "example_queries",
        ],
    )
    write_markdown(out_dir / "coverage_summary.md", summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize semantic coverage of search-quality target CUIs.")
    parser.add_argument(
        "--source-file",
        action="append",
        type=Path,
        default=[],
        help="TSV source to include. Defaults to the standard search-quality target files.",
    )
    parser.add_argument(
        "--semantic-type-index",
        type=Path,
        default=DEFAULT_SEMANTIC_TYPE_INDEX,
        help="SQLite semantic type index with semantic_types(cui,tui,stn,sty,atui).",
    )
    parser.add_argument(
        "--label-index",
        type=Path,
        default=DEFAULT_LABEL_INDEX,
        help="SQLite label index used to add display labels to audited CUIs.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Directory for coverage_summary.json, coverage_summary.md, and TSV detail files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_files = args.source_file or [Path(path) for path in DEFAULT_SOURCE_FILES]
    summary = build_audit(
        source_files=source_files,
        semantic_type_index=args.semantic_type_index,
        label_index=args.label_index,
        out_dir=hpath(args.out_dir),
    )
    print(json.dumps({
        "out_dir": repo_path(hpath(args.out_dir)),
        "unique_target_cuis": summary["unique_target_cuis"],
        "target_mentions": summary["target_mentions"],
        "unique_risk_cuis": summary["unique_risk_cuis"],
        "thin_core_groups": summary["thin_core_groups"],
        "largest_group": summary["largest_group"],
        "largest_group_share": summary["largest_group_share"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
