#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from evaluate_search_api import QuerySpec, read_query_specs
from search_quality_server import (
    DEFAULT_ACTIVE_LABEL_SUPPLEMENT,
    DEFAULT_CODE_INDEX,
    DEFAULT_DEFINITION_INDEX,
    DEFAULT_DOC_PATHS,
    DEFAULT_EXTERNAL_CUI_VECTOR_INDEX,
    DEFAULT_LABEL_INDEXES,
    DEFAULT_RELATION_INDEX,
    DEFAULT_RELATIONSHIP_EDGE_INDEX,
    DEFAULT_RESEARCH_RELATION_INDEX,
    DEFAULT_SEMANTIC_TYPE_INDEX,
    DEFAULT_VECTOR_PATHS,
    SearchIndex,
)


DEFAULT_ACCEPTABLE_ALTERNATIVES = ROOT / "config" / "search_quality_acceptable_cui_alternatives.tsv"


def semantic_type_names(hit: dict) -> str:
    names = [
        str(item.get("name") or item.get("sty") or "").strip()
        for item in hit.get("semantic_types") or []
    ]
    return "; ".join(name for name in names if name)


def rank_by_cui(hits: list[dict]) -> dict[str, int]:
    ranks = {}
    for index, hit in enumerate(hits, start=1):
        cui = str(hit.get("cui") or "").upper()
        if cui and cui not in ranks:
            ranks[cui] = index
    return ranks


def split_cui_values(value: str) -> set[str]:
    normalized = value.replace(",", "|").replace(";", "|")
    return {part.strip().upper() for part in normalized.split("|") if part.strip()}


def read_acceptable_alternatives(path: Path | None) -> dict[str, set[str]]:
    if not path or not path.exists():
        return {}
    alternatives: dict[str, set[str]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(
            (line for line in handle if line.strip() and not line.lstrip().startswith("#")),
            delimiter="\t",
        )
        for row in reader:
            expected_values = split_cui_values(
                row.get("expected_cui")
                or row.get("canonical_cui")
                or row.get("cui")
                or ""
            )
            acceptable_values = split_cui_values(
                row.get("acceptable_cui")
                or row.get("alternative_cui")
                or row.get("alternatives")
                or ""
            )
            for expected_cui in expected_values:
                alternatives.setdefault(expected_cui, set()).update(acceptable_values)
    return alternatives


def acceptable_options(expected_cui: str, alternatives: dict[str, set[str]]) -> set[str]:
    expected_cui = expected_cui.upper()
    return {expected_cui, *alternatives.get(expected_cui, set())}


def accepted_ranks_by_expected(
    hits: list[dict],
    expected: set[str],
    alternatives: dict[str, set[str]],
) -> tuple[dict[str, int], dict[str, str]]:
    ranks = rank_by_cui(hits)
    accepted_ranks: dict[str, int] = {}
    accepted_cuis: dict[str, str] = {}
    for expected_cui in sorted(expected):
        candidates = [
            (ranks[cui], cui)
            for cui in acceptable_options(expected_cui, alternatives)
            if cui in ranks
        ]
        if not candidates:
            continue
        rank, accepted_cui = min(candidates)
        accepted_ranks[expected_cui] = rank
        accepted_cuis[expected_cui] = accepted_cui
    return accepted_ranks, accepted_cuis


def expected_groups_at_limit(
    hits: list[dict],
    expected: set[str],
    *,
    limit: int,
    alternatives: dict[str, set[str]] | None = None,
) -> set[str]:
    alternatives = alternatives or {}
    accepted_ranks, accepted_cuis = accepted_ranks_by_expected(hits, expected, alternatives)
    hits_by_cui = {str(hit.get("cui") or "").upper(): hit for hit in hits}
    groups = set()
    for expected_cui, rank in accepted_ranks.items():
        if rank > limit:
            continue
        hit = hits_by_cui.get(accepted_cuis.get(expected_cui, ""))
        if hit:
            groups.add(str(hit.get("semantic_group") or "OTHER"))
    return groups


def compact_hits(hits: list[dict], *, limit: int) -> str:
    chunks = []
    for index, hit in enumerate(hits[:limit], start=1):
        score = hit.get("rank_score", hit.get("score"))
        score_text = f"{float(score):.3f}" if score is not None else ""
        chunks.append(
            f"{index}:{hit.get('cui')} {hit.get('name') or hit.get('label')} "
            f"[{hit.get('semantic_group') or 'OTHER'} {score_text}]"
        )
    return " | ".join(chunks)


def judge_quality(
    spec: QuerySpec,
    hits: list[dict],
    *,
    acceptable_alternatives: dict[str, set[str]] | None = None,
) -> dict:
    acceptable_alternatives = acceptable_alternatives or {}
    expected = {cui.upper() for cui in spec.expected_cuis}
    ranks, accepted_cuis = accepted_ranks_by_expected(hits, expected, acceptable_alternatives)
    found_5 = sorted(cui for cui in expected if ranks.get(cui, 10**9) <= 5)
    found_10 = sorted(cui for cui in expected if ranks.get(cui, 10**9) <= 10)
    found_20 = sorted(cui for cui in expected if ranks.get(cui, 10**9) <= 20)
    found_60 = sorted(cui for cui in expected if ranks.get(cui, 10**9) <= 60)
    missing_10 = sorted(expected - set(found_10))
    missing_20 = sorted(expected - set(found_20))
    missing_60 = sorted(expected - set(found_60))
    first_expected_rank = min((ranks[cui] for cui in expected if cui in ranks), default=0)
    top = hits[0] if hits else {}
    top_cui = str(top.get("cui") or "").upper()
    acceptable_universe = set()
    for expected_cui in expected:
        acceptable_universe.update(acceptable_options(expected_cui, acceptable_alternatives))
    top_on_target = top_cui in acceptable_universe
    expected_groups = expected_groups_at_limit(
        hits,
        expected,
        limit=60,
        alternatives=acceptable_alternatives,
    )
    groups_10 = expected_groups_at_limit(
        hits,
        expected,
        limit=10,
        alternatives=acceptable_alternatives,
    )
    coverage_10 = len(found_10) / len(expected) if expected else 0.0
    coverage_20 = len(found_20) / len(expected) if expected else 0.0
    group_coverage_10 = len(groups_10) / len(expected_groups) if expected_groups else 0.0

    if expected and top_on_target and coverage_10 >= 0.8 and not missing_20 and group_coverage_10 >= 0.8:
        verdict = "good"
        rationale = "Central concept is top-ranked and most expected concepts/groups are visible in the first page."
    elif expected and (coverage_20 >= 0.6 or coverage_10 >= 0.5):
        verdict = "mixed"
        rationale = "Useful concepts are recoverable, but omissions or ranking would slow a reviewer."
    else:
        verdict = "poor"
        rationale = "Central expected concepts are missing from the useful result window or the focus is wrong."

    return {
        "id": spec.query_id,
        "verdict": verdict,
        "rationale": rationale,
        "expected_count": len(expected),
        "found_at_5": len(found_5),
        "found_at_10": len(found_10),
        "found_at_20": len(found_20),
        "found_at_60": len(found_60),
        "coverage_at_10": f"{coverage_10:.3f}",
        "coverage_at_20": f"{coverage_20:.3f}",
        "expected_group_count": len(expected_groups),
        "expected_groups_at_10": len(groups_10),
        "group_coverage_at_10": f"{group_coverage_10:.3f}",
        "first_expected_rank": first_expected_rank or "",
        "top_cui": top.get("cui") or "",
        "top_name": top.get("name") or top.get("label") or "",
        "top_semantic_group": top.get("semantic_group") or "",
        "top_semantic_types": semantic_type_names(top),
        "missing_at_10": "|".join(missing_10),
        "missing_at_20": "|".join(missing_20),
        "missing_at_60": "|".join(missing_60),
        "accepted_alternatives_at_10": "|".join(
            f"{expected_cui}={accepted_cuis[expected_cui]}"
            for expected_cui in sorted(found_10)
            if accepted_cuis.get(expected_cui) and accepted_cuis[expected_cui] != expected_cui
        ),
        "hits_top_10": compact_hits(hits, limit=10),
        "query": spec.query,
    }


def write_tsv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "id",
        "verdict",
        "rationale",
        "expected_count",
        "found_at_5",
        "found_at_10",
        "found_at_20",
        "found_at_60",
        "coverage_at_10",
        "coverage_at_20",
        "expected_group_count",
        "expected_groups_at_10",
        "group_coverage_at_10",
        "first_expected_rank",
        "top_cui",
        "top_name",
        "top_semantic_group",
        "top_semantic_types",
        "missing_at_10",
        "missing_at_20",
        "missing_at_60",
        "accepted_alternatives_at_10",
        "hits_top_10",
        "query",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")


def summarize(rows: list[dict]) -> dict:
    expected_total = sum(int(row["expected_count"]) for row in rows)
    verdict_counts = Counter(str(row["verdict"]) for row in rows)
    summary = {
        "paragraphs": len(rows),
        "expected_concepts": expected_total,
        "verdict_counts": dict(sorted(verdict_counts.items())),
    }
    for limit in (5, 10, 20, 60):
        found = sum(int(row[f"found_at_{limit}"]) for row in rows)
        summary[f"recall_at_{limit}"] = found / expected_total if expected_total else 0.0
        summary[f"found_at_{limit}"] = found
    group_total = sum(int(row["expected_group_count"]) for row in rows)
    group_found_10 = sum(int(row["expected_groups_at_10"]) for row in rows)
    summary["expected_semantic_groups"] = group_total
    summary["expected_group_recall_at_10"] = group_found_10 / group_total if group_total else 0.0
    summary["queries_all_expected_at_10"] = sum(
        1 for row in rows if int(row["found_at_10"]) == int(row["expected_count"])
    )
    summary["queries_all_expected_at_20"] = sum(
        1 for row in rows if int(row["found_at_20"]) == int(row["expected_count"])
    )
    return summary


def write_report(path: Path, summary: dict, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    misses = [row for row in rows if row["missing_at_10"]]
    accepted = [row for row in rows if row.get("accepted_alternatives_at_10")]
    poor_or_mixed = [row for row in rows if row["verdict"] != "good"]
    lines = [
        "# Paragraph Search Quality Evaluation",
        "",
        "This run evaluates whether paragraph search output is good, not merely whether a concept appears somewhere. The verdict rubric is:",
        "",
        "- `good`: top result is clinically on target and most expected concepts plus semantic groups are visible in the first page.",
        "- `mixed`: useful concepts are recoverable, but ranking, omissions, or semantic typing would slow review.",
        "- `poor`: central expected concepts are missing from the useful result window or the result set has the wrong focus.",
        "",
        "## Metrics",
        "",
        f"- Paragraphs: {summary['paragraphs']}",
        f"- Expected concepts: {summary['expected_concepts']}",
        f"- Verdicts: {summary['verdict_counts']}",
    ]
    for limit in (5, 10, 20, 60):
        found = summary[f"found_at_{limit}"]
        recall = summary[f"recall_at_{limit}"] * 100
        lines.append(f"- Recall@{limit}: {found}/{summary['expected_concepts']} ({recall:.1f}%)")
    group_recall = summary["expected_group_recall_at_10"] * 100
    lines.extend(
        [
            f"- Expected semantic group recall@10: {group_recall:.1f}%",
            f"- Queries with all expected concepts@10: {summary['queries_all_expected_at_10']}/{summary['paragraphs']}",
            f"- Queries with all expected concepts@20: {summary['queries_all_expected_at_20']}/{summary['paragraphs']}",
            "",
            "## Mixed Or Poor Paragraphs",
            "",
        ]
    )
    if not poor_or_mixed:
        lines.append("- None.")
    else:
        for row in poor_or_mixed:
            lines.append(
                f"- {row['id']}: {row['verdict']}; missing@10={row['missing_at_10'] or 'none'}; "
                f"top={row['top_cui']} {row['top_name']}"
            )
    lines.extend(["", "## Missing Expected Concepts At 10", ""])
    if not misses:
        lines.append("- None.")
    else:
        for row in misses:
            lines.append(f"- {row['id']}: {row['missing_at_10']}")
    lines.extend(["", "## Accepted Alternatives At 10", ""])
    if not accepted:
        lines.append("- None.")
    else:
        for row in accepted:
            lines.append(f"- {row['id']}: {row['accepted_alternatives_at_10']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate paragraph-level clinical search usefulness.")
    parser.add_argument("--queries", type=Path, default=ROOT / "config" / "search_quality_paragraph_queries.tsv")
    parser.add_argument("--alternatives", type=Path, default=DEFAULT_ACCEPTABLE_ALTERNATIVES)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--vectors",
        type=Path,
        nargs="+",
        default=DEFAULT_VECTOR_PATHS,
        help="Vector JSONL files to evaluate. Defaults to the local server defaults that exist.",
    )
    parser.add_argument(
        "--docs",
        type=Path,
        nargs="+",
        default=DEFAULT_DOC_PATHS,
        help="Concept document JSONL files paired with --vectors. Defaults to the local server defaults that exist.",
    )
    parser.add_argument(
        "--label-index",
        type=Path,
        action="append",
        default=None,
        help="SQLite label fallback index. Repeat for multiple indexes. Defaults to local server defaults.",
    )
    parser.add_argument("--code-index", type=Path, help="SQLite CUI/code lookup index.")
    parser.add_argument("--semantic-type-index", type=Path, help="SQLite semantic type index.")
    parser.add_argument("--relation-index", type=Path, help="SQLite related concept index.")
    parser.add_argument("--research-relation-index", type=Path, help="SQLite cross-semantic research relation index.")
    parser.add_argument("--relationship-edge-index", type=Path, help="SQLite mined relationship edge index.")
    parser.add_argument("--external-cui-vector-index", type=Path, help="SQLite external CUI vector neighbor index.")
    parser.add_argument("--definition-index", type=Path, help="SQLite definition fallback index.")
    parser.add_argument("--active-label-supplement", type=Path, help="Curated active-label supplement TSV.")
    parser.add_argument("--top-k", type=int, default=60)
    parser.add_argument(
        "--candidate-pool-multiplier",
        type=int,
        default=1,
        help="Number of vector candidates per requested result to hydrate before reranking.",
    )
    parser.add_argument(
        "--candidate-pool-min",
        type=int,
        default=40,
        help="Minimum vector candidate pool size before reranking.",
    )
    parser.add_argument("--no-code-index", action="store_true", help="Disable source-code lookup index for ablation.")
    parser.add_argument(
        "--no-semantic-type-index",
        action="store_true",
        help="Disable MRSTY semantic type index for ablation.",
    )
    parser.add_argument("--no-relation-index", action="store_true", help="Disable MRREL related concept index.")
    parser.add_argument(
        "--no-research-relation-index",
        action="store_true",
        help="Disable cross-semantic research relation index.",
    )
    parser.add_argument(
        "--no-relationship-edge-index",
        action="store_true",
        help="Disable mined universal relationship edge index.",
    )
    parser.add_argument(
        "--rank-relationship-edges",
        action="store_true",
        help="Use mined relationship edges as rank signals. By default they remain available for relationship views only.",
    )
    parser.add_argument(
        "--no-external-cui-vector-index",
        action="store_true",
        help="Disable external CUI vector index.",
    )
    parser.add_argument("--no-definition-index", action="store_true", help="Disable MRDEF definition fallback index.")
    parser.add_argument(
        "--no-active-label-supplement",
        action="store_true",
        help="Disable curated active-label supplement.",
    )
    return parser.parse_args()


def optional_path(
    override: Path | None,
    default: Path,
    *,
    disabled: bool,
    label: str,
) -> Path | None:
    if disabled:
        return None
    path = override if override is not None else (default if default.exists() else None)
    if path and not path.exists():
        raise SystemExit(f"missing {label}: {path}")
    return path


def main() -> int:
    args = parse_args()
    if not args.vectors:
        raise SystemExit("no vector files configured; pass --vectors")
    if not args.docs:
        raise SystemExit("no concept document files configured; pass --docs")
    for path in args.vectors:
        if not path.exists():
            raise SystemExit(f"missing vector file: {path}")
    for path in args.docs:
        if not path.exists():
            raise SystemExit(f"missing concept document file: {path}")
    label_index_paths = args.label_index if args.label_index is not None else DEFAULT_LABEL_INDEXES
    for path in label_index_paths:
        if not path.exists():
            raise SystemExit(f"missing label index file: {path}")
    code_index_path = optional_path(
        args.code_index,
        DEFAULT_CODE_INDEX,
        disabled=args.no_code_index,
        label="code index",
    )
    semantic_type_index_path = optional_path(
        args.semantic_type_index,
        DEFAULT_SEMANTIC_TYPE_INDEX,
        disabled=args.no_semantic_type_index,
        label="semantic type index",
    )
    relation_index_path = optional_path(
        args.relation_index,
        DEFAULT_RELATION_INDEX,
        disabled=args.no_relation_index,
        label="relation index",
    )
    research_relation_index_path = optional_path(
        args.research_relation_index,
        DEFAULT_RESEARCH_RELATION_INDEX,
        disabled=args.no_research_relation_index,
        label="research relation index",
    )
    relationship_edge_index_path = optional_path(
        args.relationship_edge_index,
        DEFAULT_RELATIONSHIP_EDGE_INDEX,
        disabled=args.no_relationship_edge_index,
        label="relationship edge index",
    )
    external_cui_vector_index_path = optional_path(
        args.external_cui_vector_index,
        DEFAULT_EXTERNAL_CUI_VECTOR_INDEX,
        disabled=args.no_external_cui_vector_index,
        label="external CUI vector index",
    )
    definition_index_path = optional_path(
        args.definition_index,
        DEFAULT_DEFINITION_INDEX,
        disabled=args.no_definition_index,
        label="definition index",
    )
    active_label_supplement_path = optional_path(
        args.active_label_supplement,
        DEFAULT_ACTIVE_LABEL_SUPPLEMENT,
        disabled=args.no_active_label_supplement,
        label="active label supplement",
    )
    specs = read_query_specs(args.queries)
    index = SearchIndex(
        vector_paths=args.vectors,
        doc_paths=args.docs,
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=384,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        label_index_paths=label_index_paths,
        code_index_path=code_index_path,
        semantic_type_index_path=semantic_type_index_path,
        relation_index_path=relation_index_path,
        research_relation_index_path=research_relation_index_path,
        relationship_edge_index_path=relationship_edge_index_path,
        external_cui_vector_index_path=external_cui_vector_index_path,
        definition_index_path=definition_index_path,
        active_label_supplement_path=active_label_supplement_path,
        candidate_pool_multiplier=args.candidate_pool_multiplier,
        candidate_pool_min=args.candidate_pool_min,
        relationship_edges_rank=args.rank_relationship_edges,
    )
    acceptable_alternatives = read_acceptable_alternatives(args.alternatives)
    payloads = []
    rows = []
    for spec in specs:
        response = index.search(spec.query, top_k=args.top_k, include_related=False)
        hits = list(response.get("hits") or [])
        rows.append(
            judge_quality(
                spec,
                hits,
                acceptable_alternatives=acceptable_alternatives,
            )
        )
        payloads.append({"id": spec.query_id, "query": spec.query, "response": response})

    summary = summarize(rows)
    summary["records"] = len(index.records)
    summary["extension_semantic_type_cuis"] = len(index.extension_semantic_types_by_cui)
    summary["active_label_supplement_labels"] = sum(
        len(rows) for rows in index.active_label_rows_by_norm.values()
    )
    summary["acceptable_alternative_rows"] = sum(len(values) for values in acceptable_alternatives.values())
    summary["candidate_pool_multiplier"] = args.candidate_pool_multiplier
    summary["candidate_pool_min"] = args.candidate_pool_min
    summary["candidate_pool_for_top_k"] = index.rerank_candidate_pool_size(args.top_k)
    summary["relationship_edges_rank"] = args.rank_relationship_edges
    summary["vector_paths"] = [str(path) for path in args.vectors]
    summary["doc_paths"] = [str(path) for path in args.docs]
    summary["index_paths"] = {
        "active_label_supplement": str(active_label_supplement_path) if active_label_supplement_path else "",
        "code_index": str(code_index_path) if code_index_path else "",
        "definition_index": str(definition_index_path) if definition_index_path else "",
        "external_cui_vector_index": str(external_cui_vector_index_path) if external_cui_vector_index_path else "",
        "label_indexes": [str(path) for path in label_index_paths],
        "relation_index": str(relation_index_path) if relation_index_path else "",
        "relationship_edge_index": str(relationship_edge_index_path) if relationship_edge_index_path else "",
        "research_relation_index": str(research_relation_index_path) if research_relation_index_path else "",
        "semantic_type_index": str(semantic_type_index_path) if semantic_type_index_path else "",
    }
    summary["disabled_indexes"] = sorted(
        name
        for name, disabled in {
            "active_label_supplement": args.no_active_label_supplement,
            "code_index": args.no_code_index,
            "definition_index": args.no_definition_index,
            "external_cui_vector_index": args.no_external_cui_vector_index,
            "relation_index": args.no_relation_index,
            "relationship_edge_index": args.no_relationship_edge_index,
            "research_relation_index": args.no_research_relation_index,
            "semantic_type_index": args.no_semantic_type_index,
        }.items()
        if disabled
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_tsv(args.output_dir / "paragraph_quality_summary.tsv", rows)
    write_jsonl(args.output_dir / "paragraph_search_payloads.jsonl", payloads)
    (args.output_dir / "paragraph_quality_metrics.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_report(args.output_dir / "paragraph_quality_report.md", summary, rows)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
