#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class QuerySpec:
    query_id: str
    query: str
    search_type: str = "words"
    sabs: str = ""
    expected_cuis: tuple[str, ...] = ()
    why: str = ""


def split_expected_cuis(value: str) -> tuple[str, ...]:
    normalized = value.replace(",", "|").replace(";", "|")
    return tuple(part.strip().upper() for part in normalized.split("|") if part.strip())


def read_query_specs(path: Path) -> list[QuerySpec]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        if "\t" not in sample:
            return [
                QuerySpec(query_id=f"query_{index}", query=line.strip())
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
                    search_type=(row.get("search_type") or "words").strip() or "words",
                    sabs=(row.get("sabs") or "").strip(),
                    expected_cuis=split_expected_cuis(row.get("expected_cuis") or ""),
                    why=(row.get("why") or "").strip(),
                )
            )
        return specs


def get_json(url: str, *, timeout: float) -> dict:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "query-expansion-umls-compare/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {err.code}: {body[:240]}") from err
    except URLError as err:
        raise RuntimeError(str(err.reason)) from err


def local_search(
    *,
    base_url: str,
    query: str,
    top_k: int,
    include_related: bool,
    timeout: float,
) -> dict:
    params = {
        "q": query,
        "k": top_k,
        "related": 1 if include_related else 0,
    }
    url = f"{base_url.rstrip('/')}/api/search?{urlencode(params)}"
    return get_json(url, timeout=timeout)


def umls_search(
    *,
    base_url: str,
    api_key: str,
    spec: QuerySpec,
    page_size: int,
    search_type: str | None,
    sabs: str | None,
    timeout: float,
) -> dict:
    params = {
        "apiKey": api_key,
        "string": spec.query,
        "searchType": search_type or spec.search_type or "words",
        "returnIdType": "concept",
        "includeObsolete": "false",
        "includeSuppressible": "false",
        "pageSize": max(1, min(page_size, 200)),
    }
    sabs_value = sabs if sabs is not None else spec.sabs
    if sabs_value:
        params["sabs"] = sabs_value
    url = f"{base_url.rstrip('/')}/search/current?{urlencode(params)}"
    return get_json(url, timeout=timeout)


def umls_hits(payload: dict) -> list[dict]:
    result = payload.get("result") or {}
    rows = result.get("results") if isinstance(result, dict) else []
    hits = []
    for row in rows or []:
        ui = str(row.get("ui") or "").strip().upper()
        if not ui or ui == "NONE":
            continue
        hits.append(
            {
                "cui": ui,
                "name": str(row.get("name") or ""),
                "root_source": str(row.get("rootSource") or ""),
                "uri": str(row.get("uri") or ""),
            }
        )
    return hits


def local_hits(payload: dict) -> list[dict]:
    hits = []
    for row in payload.get("hits") or []:
        cui = str(row.get("cui") or "").strip().upper()
        if not cui:
            continue
        hits.append(
            {
                "cui": cui,
                "name": str(row.get("name") or ""),
                "score": row.get("rank_score", row.get("score")),
                "semantic_group": str(row.get("semantic_group") or ""),
                "semantic_types": [
                    str(item.get("name") or "")
                    for item in row.get("semantic_types") or []
                    if item.get("name")
                ],
            }
        )
    return hits


def rank_map(hits: list[dict]) -> dict[str, int]:
    ranks: dict[str, int] = {}
    for index, hit in enumerate(hits, start=1):
        cui = str(hit.get("cui") or "").upper()
        if cui and cui not in ranks:
            ranks[cui] = index
    return ranks


def first_rank(cuis: list[str] | tuple[str, ...], ranks: dict[str, int]) -> int | None:
    found = [ranks[cui] for cui in cuis if cui in ranks]
    return min(found) if found else None


def compact_hits(hits: list[dict], *, limit: int, include_score: bool) -> str:
    parts = []
    for index, hit in enumerate(hits[:limit], start=1):
        score = hit.get("score")
        score_text = ""
        if include_score and score is not None:
            try:
                score_text = f" [{float(score):.3f}]"
            except (TypeError, ValueError):
                score_text = f" [{score}]"
        source = f" {hit.get('root_source')}" if hit.get("root_source") else ""
        parts.append(f"{index}:{hit.get('cui')} {hit.get('name')}{source}{score_text}")
    return " | ".join(parts)


def compare_payloads(
    spec: QuerySpec,
    local_payload: dict | None,
    umls_payload: dict | None,
    *,
    compare_top_n: int,
    show_hits: int,
    local_error: str = "",
    umls_error: str = "",
) -> dict:
    local = local_hits(local_payload or {})
    umls = umls_hits(umls_payload or {})
    local_ranks = rank_map(local)
    umls_ranks = rank_map(umls)
    local_top = local[0] if local else {}
    umls_top = umls[0] if umls else {}
    local_top_cui = str(local_top.get("cui") or "")
    umls_top_cui = str(umls_top.get("cui") or "")
    local_top_in_umls = first_rank([local_top_cui], umls_ranks) if local_top_cui else None
    umls_top_in_local = first_rank([umls_top_cui], local_ranks) if umls_top_cui else None
    local_top_set = {hit["cui"] for hit in local[:compare_top_n]}
    umls_top_set = {hit["cui"] for hit in umls[:compare_top_n]}
    overlap = sorted(local_top_set & umls_top_set)
    expected_local_rank = first_rank(spec.expected_cuis, local_ranks) if spec.expected_cuis else None
    expected_umls_rank = first_rank(spec.expected_cuis, umls_ranks) if spec.expected_cuis else None
    return {
        "id": spec.query_id,
        "query": spec.query,
        "search_type": spec.search_type,
        "sabs": spec.sabs,
        "expected_cuis": "|".join(spec.expected_cuis),
        "local_top_cui": local_top_cui,
        "local_top_name": str(local_top.get("name") or ""),
        "umls_top_cui": umls_top_cui,
        "umls_top_name": str(umls_top.get("name") or ""),
        "umls_top_source": str(umls_top.get("root_source") or ""),
        "local_top_in_umls_rank": "" if local_top_in_umls is None else str(local_top_in_umls),
        "umls_top_in_local_rank": "" if umls_top_in_local is None else str(umls_top_in_local),
        "expected_local_rank": "" if expected_local_rank is None else str(expected_local_rank),
        "expected_umls_rank": "" if expected_umls_rank is None else str(expected_umls_rank),
        "overlap_at_n": f"{len(overlap)}/{compare_top_n}",
        "overlap_cuis": "|".join(overlap),
        "local_error": local_error,
        "umls_error": umls_error,
        "local_hits": compact_hits(local, limit=show_hits, include_score=True),
        "umls_hits": compact_hits(umls, limit=show_hits, include_score=False),
    }


def write_tsv(rows: list[dict], output) -> None:
    fields = [
        "id",
        "query",
        "search_type",
        "sabs",
        "expected_cuis",
        "local_top_cui",
        "local_top_name",
        "umls_top_cui",
        "umls_top_name",
        "umls_top_source",
        "local_top_in_umls_rank",
        "umls_top_in_local_rank",
        "expected_local_rank",
        "expected_umls_rank",
        "overlap_at_n",
        "overlap_cuis",
        "local_error",
        "umls_error",
        "local_hits",
        "umls_hits",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare local semantic-evidence search results with UMLS UTS /search/current results."
    )
    parser.add_argument("--queries", type=Path, default=Path("config/umls_api_comparison_queries.tsv"))
    parser.add_argument("--local-base-url", default="http://127.0.0.1:8766")
    parser.add_argument("--umls-base-url", default="https://uts-ws.nlm.nih.gov/rest")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("UMLS_API_KEY") or os.environ.get("APIKEY") or "",
        help="UMLS API key. Defaults to UMLS_API_KEY or APIKEY from the environment.",
    )
    parser.add_argument("--local-top-k", type=int, default=25)
    parser.add_argument("--umls-page-size", type=int, default=25)
    parser.add_argument("--compare-top-n", type=int, default=10)
    parser.add_argument("--show-hits", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--sleep", type=float, default=0.15, help="Seconds to wait between UMLS requests.")
    parser.add_argument("--include-related", action="store_true")
    parser.add_argument("--search-type", help="Override the query file search_type for every UMLS request.")
    parser.add_argument("--sabs", help="Override the query file sabs filter for every UMLS request.")
    parser.add_argument("--payload-dir", type=Path, help="Save <id>.local.json and <id>.umls.json payloads.")
    parser.add_argument("--from-payload-dir", type=Path, help="Read saved payloads instead of calling either API.")
    parser.add_argument("--fail-on-error", action="store_true")
    return parser.parse_args()


def read_payload_pair(payload_dir: Path, query_id: str) -> tuple[dict, dict]:
    local_path = payload_dir / f"{query_id}.local.json"
    umls_path = payload_dir / f"{query_id}.umls.json"
    return (
        json.loads(local_path.read_text(encoding="utf-8")),
        json.loads(umls_path.read_text(encoding="utf-8")),
    )


def save_payload_pair(payload_dir: Path, query_id: str, local_payload: dict | None, umls_payload: dict | None) -> None:
    payload_dir.mkdir(parents=True, exist_ok=True)
    if local_payload is not None:
        (payload_dir / f"{query_id}.local.json").write_text(
            json.dumps(local_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if umls_payload is not None:
        (payload_dir / f"{query_id}.umls.json").write_text(
            json.dumps(umls_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def main() -> int:
    args = parse_args()
    specs = read_query_specs(args.queries)
    if not specs:
        print(f"no queries found in {args.queries}", file=sys.stderr)
        return 2
    if args.from_payload_dir and args.payload_dir:
        print("--from-payload-dir and --payload-dir are mutually exclusive", file=sys.stderr)
        return 2
    if not args.from_payload_dir and not args.api_key:
        print("UMLS API key missing. Export APIKEY or UMLS_API_KEY, or pass --api-key.", file=sys.stderr)
        return 2

    rows = []
    had_error = False
    for index, spec in enumerate(specs, start=1):
        local_payload = None
        umls_payload = None
        local_error = ""
        umls_error = ""
        if args.from_payload_dir:
            try:
                local_payload, umls_payload = read_payload_pair(args.from_payload_dir, spec.query_id)
            except Exception as err:  # noqa: BLE001 - preserve batch output with error column
                local_error = str(err)
                umls_error = str(err)
                had_error = True
        else:
            try:
                local_payload = local_search(
                    base_url=args.local_base_url,
                    query=spec.query,
                    top_k=args.local_top_k,
                    include_related=args.include_related,
                    timeout=args.timeout,
                )
            except Exception as err:  # noqa: BLE001
                local_error = str(err)
                had_error = True
            try:
                umls_payload = umls_search(
                    base_url=args.umls_base_url,
                    api_key=args.api_key,
                    spec=spec,
                    page_size=args.umls_page_size,
                    search_type=args.search_type,
                    sabs=args.sabs,
                    timeout=args.timeout,
                )
            except Exception as err:  # noqa: BLE001
                umls_error = str(err)
                had_error = True
            if args.payload_dir:
                save_payload_pair(args.payload_dir, spec.query_id, local_payload, umls_payload)
            if index < len(specs) and args.sleep > 0:
                time.sleep(args.sleep)

        rows.append(
            compare_payloads(
                spec,
                local_payload,
                umls_payload,
                compare_top_n=args.compare_top_n,
                show_hits=args.show_hits,
                local_error=local_error,
                umls_error=umls_error,
            )
        )

    write_tsv(rows, sys.stdout)
    return 1 if had_error and args.fail_on_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
