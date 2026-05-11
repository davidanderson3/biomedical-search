#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


@dataclass(frozen=True)
class QuerySpec:
    query_id: str
    query: str
    expected_cuis: list[str]
    why: str = ""


def split_expected_cuis(value: str) -> list[str]:
    normalized = value.replace(",", "|").replace(";", "|")
    return [part.strip().upper() for part in normalized.split("|") if part.strip()]


def read_query_specs(path: Path) -> list[QuerySpec]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        if "\t" not in sample:
            return [
                QuerySpec(query_id=f"query_{index}", query=line.strip(), expected_cuis=[])
                for index, line in enumerate(handle, start=1)
                if line.strip() and not line.lstrip().startswith("#")
            ]
        reader = csv.DictReader(
            (line for line in handle if line.strip() and not line.lstrip().startswith("#")),
            delimiter="\t",
        )
        specs = []
        for index, row in enumerate(reader, start=1):
            query = (row.get("query") or "").strip()
            if not query:
                continue
            specs.append(
                QuerySpec(
                    query_id=(row.get("id") or f"query_{index}").strip(),
                    query=query,
                    expected_cuis=split_expected_cuis(row.get("expected_cuis") or ""),
                    why=(row.get("why") or "").strip(),
                )
            )
        return specs


def get_json(base_url: str, path: str, params: dict[str, str | int], *, timeout: float) -> dict:
    url = f"{base_url.rstrip('/')}{path}?{urlencode(params)}"
    with urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def source_mix_summary(hit: dict) -> str:
    items = (hit.get("source_mix") or {}).get("items") or []
    visible = [
        f"{item.get('source')}:{item.get('sample_refs')}"
        for item in items
        if int(item.get("sample_refs") or 0) > 0
    ]
    if visible:
        return ",".join(visible[:4])
    sources = [str(source) for source in hit.get("sources") or [] if source]
    return ",".join(sources[:4])


def semantic_type_summary(hit: dict) -> str:
    values = []
    for item in hit.get("semantic_types") or []:
        name = str(item.get("name") or "").strip()
        tui = str(item.get("tui") or "").strip()
        if name and tui:
            values.append(f"{name} {tui}")
        elif name:
            values.append(name)
        elif tui:
            values.append(tui)
    return "; ".join(values[:3])


def score_component_summary(hit: dict) -> str:
    breakdown = hit.get("score_breakdown") or {}
    penalty = sum(
        float(breakdown.get(name) or 0.0)
        for name in (
            "generic_penalty",
            "role_mismatch_penalty",
            "numeric_specificity_penalty",
            "numeric_context_fragment_penalty",
            "generic_fragment_penalty",
            "normal_exam_fragment_penalty",
            "action_observation_penalty",
            "denied_positive_finding_penalty",
            "denied_context_mismatch_penalty",
            "composite_component_penalty",
            "comparator_arm_penalty",
            "sepsis_subtype_penalty",
        )
    )
    fields = [
        ("lex", "lexical_component"),
        ("vec", "vector_component"),
        ("exact", "exact_label_component"),
        ("exact_primary", "exact_primary_name_component"),
        ("exact_span", "exact_span_component"),
        ("ev", "evidence_component"),
        ("sem", "semantic_component"),
        ("ctx", "evidence_context_component"),
        ("mrrel", "mrrel_component"),
        ("cmp", "composite_intent_component"),
        ("first", "first_statement_component"),
        ("new_phrase", "local_extension_phrase_component"),
        ("spec", "specificity_component"),
        ("pen", None),
    ]
    parts = []
    for label, key in fields:
        value = penalty if key is None else float(breakdown.get(key) or 0.0)
        if value:
            parts.append(f"{label}={value:.3f}")
    return ";".join(parts)


def expected_rank(hits: list[dict], expected_cuis: list[str]) -> int | None:
    expected = set(expected_cuis)
    for index, hit in enumerate(hits, start=1):
        if str(hit.get("cui") or "").upper() in expected:
            return index
    return None


def compact_hits(hits: list[dict], *, limit: int) -> str:
    chunks = []
    for index, hit in enumerate(hits[:limit], start=1):
        cui = str(hit.get("cui") or "")
        name = str(hit.get("name") or hit.get("label") or cui)
        rank_score = hit.get("rank_score")
        score = hit.get("score")
        shown_score = rank_score if rank_score is not None else score
        score_text = f"{float(shown_score):.3f}" if shown_score is not None else ""
        chunks.append(f"{index}:{cui} {name} [{score_text}]")
    return " | ".join(chunks)


def summarize_search_response(spec: QuerySpec, response: dict, *, show_hits: int) -> dict:
    hits = list(response.get("hits") or [])
    top = hits[0] if hits else {}
    rank = expected_rank(hits, spec.expected_cuis) if spec.expected_cuis else None
    return {
        "id": spec.query_id,
        "expected_cuis": "|".join(spec.expected_cuis),
        "expected_rank": "" if rank is None else str(rank),
        "top_cui": str(top.get("cui") or ""),
        "top_name": str(top.get("name") or top.get("label") or ""),
        "top_semantic_types": semantic_type_summary(top),
        "top_rank_score": str(top.get("rank_score") or ""),
        "top_retrieval_score": str(top.get("score") or ""),
        "top_sources": source_mix_summary(top),
        "top_score_parts": score_component_summary(top),
        "hits": compact_hits(hits, limit=show_hits),
        "query": spec.query,
    }


def write_tsv(rows: list[dict], output) -> None:
    fields = [
        "id",
        "expected_cuis",
        "expected_rank",
        "top_cui",
        "top_name",
        "top_semantic_types",
        "top_rank_score",
        "top_retrieval_score",
        "top_sources",
        "top_score_parts",
        "hits",
        "query",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run clinical search quality queries against the local search API."
    )
    parser.add_argument(
        "--queries",
        type=Path,
        default=Path("config/search_quality_clinical_queries.tsv"),
        help="TSV with id, query, expected_cuis, and optional why columns; a plain text file also works.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8766")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--show-hits", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--jsonl-out", type=Path)
    parser.add_argument("--payload-dir", type=Path)
    parser.add_argument(
        "--include-related",
        action="store_true",
        help="Request related-concept enrichment payloads. Disabled by default for faster ranking checks.",
    )
    parser.add_argument(
        "--from-payload-dir",
        type=Path,
        help="Read previously saved <query id>.json payloads instead of calling the API.",
    )
    parser.add_argument("--fail-on-missing-expected", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    specs = read_query_specs(args.queries)
    if not specs:
        print(f"no queries found in {args.queries}", file=sys.stderr)
        return 2
    if args.from_payload_dir and args.payload_dir:
        print("--from-payload-dir and --payload-dir are mutually exclusive", file=sys.stderr)
        return 2
    if args.payload_dir:
        args.payload_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    missing_expected = []
    jsonl_handle = args.jsonl_out.open("w", encoding="utf-8") if args.jsonl_out else None
    try:
        for spec in specs:
            if args.from_payload_dir:
                payload_path = args.from_payload_dir / f"{spec.query_id}.json"
                response = json.loads(payload_path.read_text(encoding="utf-8"))
            else:
                response = get_json(
                    args.base_url,
                    "/api/search",
                    {
                        "q": spec.query,
                        "limit": args.top_k,
                        "related": 1 if args.include_related else 0,
                    },
                    timeout=args.timeout,
                )
            if jsonl_handle:
                jsonl_handle.write(json.dumps(response, sort_keys=True) + "\n")
            if args.payload_dir and not args.from_payload_dir:
                out_path = args.payload_dir / f"{spec.query_id}.json"
                out_path.write_text(json.dumps(response, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            row = summarize_search_response(spec, response, show_hits=args.show_hits)
            rows.append(row)
            if spec.expected_cuis and not row["expected_rank"]:
                missing_expected.append(spec.query_id)
    finally:
        if jsonl_handle:
            jsonl_handle.close()

    write_tsv(rows, sys.stdout)
    if missing_expected:
        print(
            "Expected CUI not returned in top "
            f"{args.top_k}: {', '.join(missing_expected)}",
            file=sys.stderr,
        )
        if args.fail_on_missing_expected:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
