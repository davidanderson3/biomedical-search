#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_real_query_inventory import (  # noqa: E402
    CODE_LIKE_RE,
    DEFAULT_INPUT_DIR,
    PUNCTUATION_RE,
    QueryRow,
    format_score,
    iter_query_rows,
)
from compare_umls_api import QuerySpec, local_hits, umls_hits, umls_search  # noqa: E402


DEFAULT_OUTPUT_ROOT = ROOT / "build" / "private_real_query_diagnostics"
DEFAULT_REGRESSION_BENCHMARK = ROOT / "config" / "search_quality_real_query_regression.tsv"
DEFAULT_UMLS_BASE_URL = "https://uts-ws.nlm.nih.gov/rest"
DEFAULT_RUN_QUERY_LIMIT = 50
DEFAULT_SEEN_STATE = DEFAULT_OUTPUT_ROOT / "seen_query_ids.json"
USER_AGENT = "query-expansion-private-real-query-diagnostic/1.0"

ROW_FIELDS = [
    "id",
    "source_file",
    "source_row",
    "token_bucket",
    "search_term",
    "unique_users",
    "normalized_term",
    "normalized_token_count",
    "privacy_flags",
    "local_hit_count",
    "local_no_hit",
    "local_low_score",
    "local_top_cui",
    "local_top_name",
    "local_top_score",
    "local_top_in_umls_rank",
    "umls_hit_count",
    "umls_no_hit",
    "umls_top_cui",
    "umls_top_name",
    "umls_top_source",
    "umls_top_in_local_rank",
    "top_cui_match",
    "overlap_at_n",
    "overlap_cuis",
    "local_error",
    "umls_error",
    "review_priority",
    "review_reasons",
    "recommended_action",
    "local_hits",
    "umls_hits",
]

REVIEW_FIELDS = [
    "review_status",
    "reviewed_safe_query",
    "reviewed_expected_cuis",
    "review_note",
    "promotion_ready",
    *ROW_FIELDS,
]

PROMOTION_FIELDS = [
    "id",
    "query",
    "expected_cuis",
    "why",
    "source",
    "review_status",
    "review_note",
    "diagnostic_query_id",
    "umls_top_cui",
    "umls_top_name",
    "local_top_cui",
    "local_top_name",
]

REVIEW_QUEUE_REASONS = {
    "local_error",
    "umls_error",
    "local_no_hit",
    "local_low_score",
    "umls_no_hit",
    "umls_top_missing_locally",
    "top_disagreement",
}


def hms_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def slugify(value: str, *, limit: int = 72) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:limit].strip("-") or "run"


def query_id(row: QueryRow) -> str:
    stem = row.source_file.removesuffix(".csv").replace("-real-queries", "")
    return f"{slugify(stem, limit=40)}_row_{row.source_row}"


def bool_text(value: bool | None) -> str:
    if value is None:
        return ""
    return "1" if value else "0"


def rank_map(hits: list[dict]) -> dict[str, int]:
    ranks: dict[str, int] = {}
    for index, hit in enumerate(hits, start=1):
        cui = str(hit.get("cui") or "").upper()
        if cui and cui not in ranks:
            ranks[cui] = index
    return ranks


def first_rank(cui: str, ranks: dict[str, int]) -> int | None:
    if not cui:
        return None
    return ranks.get(cui.upper())


def compact_hits(hits: list[dict], *, limit: int, include_score: bool) -> str:
    chunks = []
    for index, hit in enumerate(hits[:limit], start=1):
        cui = str(hit.get("cui") or "")
        name = str(hit.get("name") or "")
        score = hit.get("score")
        score_text = ""
        if include_score and score is not None:
            try:
                score_text = f" [{float(score):.3f}]"
            except (TypeError, ValueError):
                score_text = f" [{score}]"
        source = f" {hit.get('root_source')}" if hit.get("root_source") else ""
        chunks.append(f"{index}:{cui} {name}{source}{score_text}")
    return " | ".join(chunks)


def get_json(base_url: str, path: str, params: dict[str, str | int], *, timeout: float) -> dict:
    url = f"{base_url.rstrip('/')}{path}?{urlencode(params)}"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def local_search(
    *,
    base_url: str,
    query: str,
    top_k: int,
    scope: str,
    mode: str,
    include_related: bool,
    timeout: float,
) -> dict:
    return get_json(
        base_url,
        "/api/search",
        {
            "q": query,
            "k": top_k,
            "limit": top_k,
            "scope": scope,
            "mode": mode,
            "related": 1 if include_related else 0,
            "linked": 0,
            "evidence_items": 0,
        },
        timeout=timeout,
    )


def call_local(args: argparse.Namespace, row: QueryRow) -> tuple[dict | None, str]:
    try:
        return (
            local_search(
                base_url=args.base_url,
                query=row.search_term,
                top_k=args.top_k,
                scope=args.scope,
                mode=args.mode,
                include_related=args.include_related,
                timeout=args.timeout,
            ),
            "",
        )
    except HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace").strip()
        return None, f"http_{exc.code}: {message[:240]}"
    except (TimeoutError, URLError, OSError) as exc:
        return None, str(exc)[:240]
    except json.JSONDecodeError as exc:
        return None, f"invalid_json: {exc}"


def call_umls(args: argparse.Namespace, row: QueryRow) -> tuple[dict | None, str]:
    spec = QuerySpec(
        query_id=query_id(row),
        query=row.search_term,
        search_type=args.search_type,
        sabs=args.sabs,
    )
    try:
        return (
            umls_search(
                base_url=args.umls_base_url,
                api_key=args.api_key,
                spec=spec,
                page_size=args.umls_page_size,
                search_type=args.search_type,
                sabs=args.sabs,
                timeout=args.timeout,
            ),
            "",
        )
    except Exception as exc:  # noqa: BLE001 - keep batch output with error column
        return None, str(exc)[:240]


def save_payload_pair(
    payload_dir: Path,
    row: QueryRow,
    local_payload: dict | None,
    umls_payload: dict | None,
) -> None:
    payload_dir.mkdir(parents=True, exist_ok=True)
    qid = query_id(row)
    if local_payload is not None:
        (payload_dir / f"{qid}.local.json").write_text(
            json.dumps(local_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if umls_payload is not None:
        (payload_dir / f"{qid}.umls.json").write_text(
            json.dumps(umls_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def review_reasons(
    row: QueryRow,
    *,
    local_error: str,
    umls_error: str,
    local_no_hit: bool,
    local_low_score: bool,
    umls_no_hit: bool | None,
    top_cui_match: bool | None,
    umls_top_in_local_rank: int | None,
    high_demand_min: int,
) -> list[str]:
    reasons: list[str] = []
    reasons.extend(f"privacy:{flag}" for flag in row.privacy_flags)
    if local_error:
        reasons.append("local_error")
    elif local_no_hit:
        reasons.append("local_no_hit")
    elif local_low_score:
        reasons.append("local_low_score")
    if umls_error:
        reasons.append("umls_error")
    elif umls_no_hit:
        reasons.append("umls_no_hit")
    elif umls_top_in_local_rank is None:
        reasons.append("umls_top_missing_locally")
    if top_cui_match is False:
        reasons.append("top_disagreement")
    if row.unique_users >= high_demand_min:
        reasons.append("high_demand")
    if CODE_LIKE_RE.search(row.search_term):
        reasons.append("code_like")
    if len(PUNCTUATION_RE.findall(row.search_term)) >= 2 and not row.privacy_flags:
        reasons.append("punctuation_variant")
    if row.normalized_token_count >= 8:
        reasons.append("long_query")
    return reasons


def review_priority(row: QueryRow, reasons: list[str]) -> int:
    priority = row.unique_users
    if any(reason.startswith("privacy:") for reason in reasons):
        priority += 100_000
    if "local_error" in reasons:
        priority += 75_000
    if "umls_error" in reasons:
        priority += 70_000
    if "local_no_hit" in reasons:
        priority += 60_000
    if "umls_top_missing_locally" in reasons:
        priority += 50_000
    if "local_low_score" in reasons:
        priority += 35_000
    if "top_disagreement" in reasons:
        priority += 10_000
    if "code_like" in reasons:
        priority += 5_000
    if "punctuation_variant" in reasons:
        priority += 2_000
    if "long_query" in reasons:
        priority += 1_000
    return priority


def recommended_action(row: QueryRow, reasons: list[str], umls_top_cui: str) -> str:
    if any(reason.startswith("privacy:") for reason in reasons):
        return "privacy_review_do_not_promote"
    if "umls_error" in reasons:
        return "rerun_umls_api"
    if "local_error" in reasons:
        return "rerun_local_es"
    if not umls_top_cui:
        return "manual_review_no_umls_top"
    if (
        "local_no_hit" in reasons
        or "local_low_score" in reasons
        or "umls_top_missing_locally" in reasons
        or "top_disagreement" in reasons
    ):
        return "review_for_possible_promotion"
    if row.unique_users:
        return "sample_for_safe_regression_promotion"
    return "monitor"


def evaluate_payloads(
    row: QueryRow,
    *,
    local_payload: dict | None,
    umls_payload: dict | None,
    local_error: str,
    umls_error: str,
    low_score_threshold: float,
    compare_top_n: int,
    show_hits: int,
    high_demand_min: int,
) -> dict[str, str | int]:
    local = local_hits(local_payload or {})
    umls = umls_hits(umls_payload or {})
    local_top = local[0] if local else {}
    umls_top = umls[0] if umls else {}
    local_top_cui = str(local_top.get("cui") or "")
    umls_top_cui = str(umls_top.get("cui") or "")
    local_top_score = float_or_none(local_top.get("score"))
    local_no_hit = not local and not local_error
    umls_no_hit = (not umls and not umls_error) if umls_payload is not None or not umls_error else None
    local_low_score = bool(
        local
        and local_top_score is not None
        and local_top_score < low_score_threshold
        and not local_error
    )
    local_ranks = rank_map(local)
    umls_ranks = rank_map(umls)
    local_top_in_umls_rank = first_rank(local_top_cui, umls_ranks)
    umls_top_in_local_rank = first_rank(umls_top_cui, local_ranks)
    top_cui_match = None
    if local_top_cui or umls_top_cui:
        top_cui_match = bool(local_top_cui and umls_top_cui and local_top_cui == umls_top_cui)
    local_top_set = {str(hit.get("cui") or "").upper() for hit in local[:compare_top_n] if hit.get("cui")}
    umls_top_set = {str(hit.get("cui") or "").upper() for hit in umls[:compare_top_n] if hit.get("cui")}
    overlap = sorted(local_top_set & umls_top_set)
    reasons = review_reasons(
        row,
        local_error=local_error,
        umls_error=umls_error,
        local_no_hit=local_no_hit,
        local_low_score=local_low_score,
        umls_no_hit=umls_no_hit,
        top_cui_match=top_cui_match,
        umls_top_in_local_rank=umls_top_in_local_rank,
        high_demand_min=high_demand_min,
    )
    return {
        "id": query_id(row),
        "source_file": row.source_file,
        "source_row": row.source_row,
        "token_bucket": row.token_bucket,
        "search_term": row.search_term,
        "unique_users": row.unique_users,
        "normalized_term": row.normalized_term,
        "normalized_token_count": row.normalized_token_count,
        "privacy_flags": "|".join(row.privacy_flags),
        "local_hit_count": len(local),
        "local_no_hit": bool_text(local_no_hit),
        "local_low_score": bool_text(local_low_score),
        "local_top_cui": local_top_cui,
        "local_top_name": str(local_top.get("name") or ""),
        "local_top_score": format_score(local_top_score),
        "local_top_in_umls_rank": "" if local_top_in_umls_rank is None else local_top_in_umls_rank,
        "umls_hit_count": len(umls),
        "umls_no_hit": bool_text(umls_no_hit),
        "umls_top_cui": umls_top_cui,
        "umls_top_name": str(umls_top.get("name") or ""),
        "umls_top_source": str(umls_top.get("root_source") or ""),
        "umls_top_in_local_rank": "" if umls_top_in_local_rank is None else umls_top_in_local_rank,
        "top_cui_match": bool_text(top_cui_match),
        "overlap_at_n": f"{len(overlap)}/{compare_top_n}",
        "overlap_cuis": "|".join(overlap),
        "local_error": local_error,
        "umls_error": umls_error,
        "review_priority": review_priority(row, reasons),
        "review_reasons": "|".join(reasons),
        "recommended_action": recommended_action(row, reasons, umls_top_cui),
        "local_hits": compact_hits(local, limit=show_hits, include_score=True),
        "umls_hits": compact_hits(umls, limit=show_hits, include_score=False),
    }


def sort_rows(rows: list[QueryRow], mode: str) -> list[QueryRow]:
    if mode == "demand":
        return sorted(rows, key=lambda row: (-row.unique_users, row.normalized_term, row.source_file, row.source_row))
    return sorted(rows, key=lambda row: (row.source_file, row.source_row))


def read_seen_state(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"version": 1, "seen_query_ids": [], "runs": []}
    with path.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    if not isinstance(state, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    seen = state.get("seen_query_ids")
    runs = state.get("runs")
    if not isinstance(seen, list) or not all(isinstance(item, str) for item in seen):
        raise ValueError(f"{path} has invalid seen_query_ids")
    if runs is not None and not isinstance(runs, list):
        raise ValueError(f"{path} has invalid runs")
    state.setdefault("version", 1)
    state.setdefault("runs", [])
    return state


def select_rows_for_run(
    rows: list[QueryRow],
    *,
    limit: int | None,
    sort_mode: str,
    selection: str,
    seen_state_path: Path,
    reset_seen_state: bool,
) -> tuple[list[QueryRow], dict[str, object]]:
    ordered = sort_rows(rows, sort_mode)
    if selection == "all":
        selected = ordered
        selected_ids = [query_id(row) for row in selected]
        return selected, {
            "selection_mode": selection,
            "query_limit": None,
            "seen_state": str(seen_state_path),
            "seen_before": 0,
            "seen_after": len(set(selected_ids)),
            "total_available_queries": len(ordered),
            "selected_new_queries": len(set(selected_ids)),
            "selected_recycled_queries": 0,
            "selected_query_ids": selected_ids,
            "selected_new_query_ids": selected_ids,
            "selected_recycled_query_ids": [],
            "reset_seen_state": reset_seen_state,
        }

    if limit is None:
        raise ValueError("limit is required unless selection is all")
    if limit < 1:
        raise ValueError("limit must be at least 1")

    if selection == "first":
        selected = ordered[:limit]
        selected_ids = [query_id(row) for row in selected]
        return selected, {
            "selection_mode": selection,
            "query_limit": limit,
            "seen_state": str(seen_state_path),
            "seen_before": 0,
            "seen_after": len(set(selected_ids)),
            "total_available_queries": len(ordered),
            "selected_new_queries": len(selected),
            "selected_recycled_queries": 0,
            "selected_query_ids": selected_ids,
            "selected_new_query_ids": selected_ids,
            "selected_recycled_query_ids": [],
            "reset_seen_state": reset_seen_state,
        }

    state = {"seen_query_ids": []} if reset_seen_state else read_seen_state(seen_state_path)
    seen_ids = set(str(item) for item in state.get("seen_query_ids") or [])
    unseen = [row for row in ordered if query_id(row) not in seen_ids]
    recycled = [row for row in ordered if query_id(row) in seen_ids]
    selected_new = unseen[:limit]
    selected_recycled = recycled[: max(0, limit - len(selected_new))]
    selected = selected_new + selected_recycled
    selected_ids = [query_id(row) for row in selected]
    selected_new_ids = [query_id(row) for row in selected_new]
    selected_recycled_ids = [query_id(row) for row in selected_recycled]
    return selected, {
        "selection_mode": selection,
        "query_limit": limit,
        "seen_state": str(seen_state_path),
        "seen_before": len(seen_ids),
        "seen_after": len(seen_ids | set(selected_ids)),
        "total_available_queries": len(ordered),
        "selected_new_queries": len(selected_new),
        "selected_recycled_queries": len(selected_recycled),
        "selected_query_ids": selected_ids,
        "selected_new_query_ids": selected_new_ids,
        "selected_recycled_query_ids": selected_recycled_ids,
        "reset_seen_state": reset_seen_state,
    }


def write_seen_state(path: Path, state: dict[str, object], *, run_id: str) -> None:
    if state.get("selection_mode") != "unseen":
        return
    seen_ids = set(read_seen_state(path).get("seen_query_ids") or [])
    if state.get("reset_seen_state"):
        seen_ids = set()
    selected_ids = [str(item) for item in state.get("selected_query_ids") or []]
    seen_ids.update(selected_ids)
    existing = {"version": 1, "seen_query_ids": [], "runs": []}
    if path.exists() and not state.get("reset_seen_state"):
        existing = read_seen_state(path)
    runs = list(existing.get("runs") or [])
    runs.append(
        {
            "run_id": run_id,
            "updated_utc": datetime.now(timezone.utc).isoformat(),
            "selected_query_ids": selected_ids,
            "selected_new_query_ids": list(state.get("selected_new_query_ids") or []),
            "selected_recycled_query_ids": list(state.get("selected_recycled_query_ids") or []),
        }
    )
    payload = {
        "version": 1,
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "seen_query_ids": sorted(seen_ids),
        "runs": runs[-200:],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_tsv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def int_field(row: dict, key: str) -> int:
    try:
        return int(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def summarize(rows: list[dict], *, args: argparse.Namespace, run_id: str) -> dict[str, object]:
    total = len(rows)
    local_scored = [row for row in rows if not row.get("local_error")]
    umls_scored = [row for row in rows if not row.get("umls_error")]
    both_top = [row for row in rows if row.get("local_top_cui") and row.get("umls_top_cui")]
    local_no_hit = sum(1 for row in local_scored if row.get("local_no_hit") == "1")
    local_low_score = sum(1 for row in local_scored if row.get("local_low_score") == "1")
    umls_no_hit = sum(1 for row in umls_scored if row.get("umls_no_hit") == "1")
    umls_top_in_local = sum(1 for row in rows if str(row.get("umls_top_in_local_rank") or "").isdigit())
    top_match = sum(1 for row in both_top if row.get("top_cui_match") == "1")
    reason_counts = Counter(
        reason
        for row in rows
        for reason in str(row.get("review_reasons") or "").split("|")
        if reason
    )
    return {
        "run_id": run_id,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "private_raw_query_diagnostic": True,
        "public_smoke_test": False,
        "input_dir": str(args.input_dir),
        "local_base_url": args.base_url,
        "local_scope": args.scope,
        "local_mode": args.mode,
        "umls_base_url": args.umls_base_url,
        "umls_api_required": True,
        "queries": total,
        "sum_unique_users": sum(int_field(row, "unique_users") for row in rows),
        "privacy_flagged_queries": sum(1 for row in rows if row.get("privacy_flags")),
        "local_scored_queries": len(local_scored),
        "local_error_queries": total - len(local_scored),
        "local_no_hit_queries": local_no_hit,
        "local_no_hit_rate": rate(local_no_hit, len(local_scored)),
        "local_low_score_threshold": args.low_score_threshold,
        "local_low_score_queries": local_low_score,
        "local_low_score_rate": rate(local_low_score, len(local_scored)),
        "umls_scored_queries": len(umls_scored),
        "umls_error_queries": total - len(umls_scored),
        "umls_no_hit_queries": umls_no_hit,
        "umls_no_hit_rate": rate(umls_no_hit, len(umls_scored)),
        "top_cui_match_queries": top_match,
        "top_cui_match_rate": rate(top_match, len(both_top)),
        f"umls_top_in_local_at_{args.top_k}_queries": umls_top_in_local,
        f"umls_top_in_local_at_{args.top_k}_rate": rate(umls_top_in_local, len(umls_scored)),
        "review_reason_counts": dict(sorted(reason_counts.items())),
    }


def review_queue_rows(rows: list[dict], *, limit: int) -> list[dict]:
    def needs_review(row: dict) -> bool:
        reasons = [part for part in str(row.get("review_reasons") or "").split("|") if part]
        return any(reason in REVIEW_QUEUE_REASONS or reason.startswith("privacy:") for reason in reasons)

    queued = [dict(row) for row in rows if needs_review(row)]
    queued.sort(
        key=lambda row: (
            -int_field(row, "review_priority"),
            -int_field(row, "unique_users"),
            str(row.get("normalized_term") or ""),
            str(row.get("id") or ""),
        )
    )
    review_rows = []
    for row in queued[:limit]:
        review_rows.append(
            {
                "review_status": "",
                "reviewed_safe_query": "",
                "reviewed_expected_cuis": "",
                "review_note": "",
                "promotion_ready": "",
                **row,
            }
        )
    return review_rows


def promotion_candidate_rows(rows: list[dict], *, limit: int) -> list[dict]:
    candidates = []
    for row in rows:
        reasons = set(str(row.get("review_reasons") or "").split("|"))
        if row.get("privacy_flags"):
            continue
        if not row.get("umls_top_cui"):
            continue
        if row.get("recommended_action") not in {
            "review_for_possible_promotion",
            "sample_for_safe_regression_promotion",
        }:
            continue
        why_bits = [
            "Private real-query diagnostic candidate; human review required before promotion.",
            f"UMLS API top result was {row.get('umls_top_cui')} {row.get('umls_top_name')}.",
        ]
        if "local_no_hit" in reasons:
            why_bits.append("Local Elasticsearch had no hit.")
        if "local_low_score" in reasons:
            why_bits.append("Local Elasticsearch top score was below threshold.")
        if "umls_top_missing_locally" in reasons:
            why_bits.append("UMLS API top CUI was not in local top results.")
        if "top_disagreement" in reasons:
            why_bits.append("Local top CUI and UMLS API top CUI disagreed.")
        candidates.append(
            {
                "id": f"real_{slugify(str(row.get('id') or ''), limit=48)}",
                "query": row.get("search_term", ""),
                "expected_cuis": row.get("umls_top_cui", ""),
                "why": " ".join(why_bits),
                "source": "private_real_query_diagnostic",
                "review_status": "",
                "review_note": "",
                "diagnostic_query_id": row.get("id", ""),
                "umls_top_cui": row.get("umls_top_cui", ""),
                "umls_top_name": row.get("umls_top_name", ""),
                "local_top_cui": row.get("local_top_cui", ""),
                "local_top_name": row.get("local_top_name", ""),
            }
        )
    candidates.sort(key=lambda row: str(row.get("diagnostic_query_id") or ""))
    return candidates[:limit]


def write_summary(path: Path, summary: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown_report(
    path: Path,
    *,
    summary: dict[str, object],
    rows_path: Path,
    review_queue_path: Path,
    promotion_path: Path,
    benchmark_path: Path,
) -> None:
    report = f"""# Private Real-Query Diagnostic

Generated: {summary['generated_utc']}

This run is private diagnostic output, not a public smoke test. It uses raw real-query exports from `data/local_search_logs/umls_query_exports`, writes raw query text only under `build/private_real_query_diagnostics`, and keeps those exports out of `docs/search_quality_experiments.html`.

## Query Selection

- Selection mode: `{summary['selection_mode']}`
- Query limit: {summary['query_limit']}
- New queries selected: {summary['selected_new_queries']}
- Recycled queries selected: {summary['selected_recycled_queries']}
- Seen-state file: `{summary['seen_state']}`

## What Was Measured

- Queries: {summary['queries']}
- Local Elasticsearch scope: `{summary['local_scope']}`
- Local no-hit rate: {summary['local_no_hit_rate']} ({summary['local_no_hit_queries']} queries)
- Local low-score rate: {summary['local_low_score_rate']} ({summary['local_low_score_queries']} queries below {summary['local_low_score_threshold']})
- UMLS API no-hit rate: {summary['umls_no_hit_rate']} ({summary['umls_no_hit_queries']} queries)
- Local top CUI matched UMLS API top CUI: {summary['top_cui_match_rate']} ({summary['top_cui_match_queries']} queries)

## Outputs

- All rows: `{rows_path}`
- Top-result review queue: `{review_queue_path}`
- Manual promotion candidates: `{promotion_path}`
- Reviewed regression benchmark target: `{benchmark_path}`

## Promotion Rule

Do not auto-promote rows. Open the review queue, remove unsafe or ambiguous rows, and only promote a query after a human reviewer confirms that the query text is safe to keep and the expected CUI is clinically correct. Copy reviewed rows into `{benchmark_path}` with `id`, `query`, `expected_cuis`, `why`, and `source`.

Run the reviewed real-query regression against the local Elasticsearch-backed API with UMLS scope:

```sh
python3 scripts/run_search_regression_benchmark.py \\
  {benchmark_path} \\
  --base-url http://127.0.0.1:8766 \\
  --scope umls \\
  --top-k 10 \\
  --rows-out build/search_regression_real_queries_rows.csv \\
  --json-out build/search_regression_real_queries_summary.json
```

The actual UMLS API result is a comparison signal, not automatic ground truth. Human review is still required before any query/CUI pair becomes part of the regression benchmark.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")


def ensure_regression_template(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["id", "query", "expected_cuis", "why", "source"],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a private real-query diagnostic against the local Elasticsearch-backed UMLS scope "
            "and compare top results with the actual UMLS UTS API."
        )
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", help="Output run id. Defaults to timestamp plus label slug.")
    parser.add_argument("--label", default="real-query-umls-api-diagnostic")
    parser.add_argument("--sort", choices=("demand", "file"), default="demand")
    parser.add_argument(
        "--max-rows",
        type=int,
        default=DEFAULT_RUN_QUERY_LIMIT,
        help=f"Queries per run. Defaults to {DEFAULT_RUN_QUERY_LIMIT}.",
    )
    parser.add_argument(
        "--selection",
        choices=("unseen", "first", "all"),
        default="unseen",
        help="Use next unseen real queries by default; first keeps old fixed-prefix behavior; all runs every row.",
    )
    parser.add_argument("--seen-state", type=Path, default=DEFAULT_SEEN_STATE)
    parser.add_argument(
        "--reset-seen-state",
        action="store_true",
        help="Forget prior private diagnostic query rotation state before selecting this run.",
    )
    parser.add_argument(
        "--score-all",
        action="store_true",
        help="Alias for --selection all. This can issue many UMLS API requests.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8766")
    parser.add_argument("--scope", choices=("umls", "umls_evidence"), default="umls")
    parser.add_argument("--mode", choices=("balanced", "exact", "comprehensive"), default="balanced")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--compare-top-n", type=int, default=10)
    parser.add_argument("--show-hits", type=int, default=5)
    parser.add_argument("--include-related", action="store_true")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--low-score-threshold", type=float, default=0.35)
    parser.add_argument("--high-demand-min", type=int, default=5)
    parser.add_argument("--review-queue-limit", type=int, default=500)
    parser.add_argument("--promotion-candidate-limit", type=int, default=500)
    parser.add_argument("--umls-base-url", default=DEFAULT_UMLS_BASE_URL)
    parser.add_argument(
        "--api-key",
        default=os.environ.get("UMLS_API_KEY") or "",
        help="UMLS UTS API key. Defaults only to UMLS_API_KEY.",
    )
    parser.add_argument("--search-type", default="words")
    parser.add_argument("--sabs", default="")
    parser.add_argument("--umls-page-size", type=int, default=10)
    parser.add_argument("--sleep", type=float, default=0.15, help="Delay between UMLS API calls.")
    parser.add_argument(
        "--payload-dir",
        type=Path,
        help="Save <query id>.local.json and <query id>.umls.json payloads for audit. API calls still run.",
    )
    parser.add_argument("--fail-on-error", action="store_true")
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument(
        "--regression-benchmark",
        type=Path,
        default=DEFAULT_REGRESSION_BENCHMARK,
        help="Reviewed safe query/CUI benchmark file to create if missing.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.api_key:
        print("UMLS API key missing. Export UMLS_API_KEY or pass --api-key.", file=sys.stderr)
        return 2

    if args.score_all:
        args.selection = "all"
        args.max_rows = None
    rows, selection_summary = select_rows_for_run(
        list(iter_query_rows(args.input_dir)),
        limit=args.max_rows,
        sort_mode=args.sort,
        selection=args.selection,
        seen_state_path=args.seen_state,
        reset_seen_state=args.reset_seen_state,
    )
    run_id = args.run_id or f"{hms_timestamp()}_{slugify(args.label)}"
    run_dir = args.output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    result_rows: list[dict] = []
    had_error = False
    total = len(rows)
    for index, row in enumerate(rows, start=1):
        if args.progress_every > 0 and (index == 1 or index % args.progress_every == 0 or index == total):
            print(f"diagnosing {index}/{total}: {row.source_file}:{row.source_row}", file=sys.stderr)
        local_payload, local_error = call_local(args, row)
        umls_payload, umls_error = call_umls(args, row)
        if index < total and args.sleep > 0:
            time.sleep(args.sleep)
        if args.payload_dir:
            save_payload_pair(args.payload_dir, row, local_payload, umls_payload)
        had_error = had_error or bool(local_error or umls_error)
        result_rows.append(
            evaluate_payloads(
                row,
                local_payload=local_payload,
                umls_payload=umls_payload,
                local_error=local_error,
                umls_error=umls_error,
                low_score_threshold=args.low_score_threshold,
                compare_top_n=args.compare_top_n,
                show_hits=args.show_hits,
                high_demand_min=args.high_demand_min,
            )
        )

    rows_path = run_dir / "rows.tsv"
    review_queue_path = run_dir / "top_result_review_queue.tsv"
    promotion_path = run_dir / "manual_promotion_candidates.tsv"
    summary_path = run_dir / "summary.json"
    report_path = run_dir / "README.md"

    write_tsv(rows_path, result_rows, ROW_FIELDS)
    review_rows = review_queue_rows(result_rows, limit=args.review_queue_limit)
    write_tsv(review_queue_path, review_rows, REVIEW_FIELDS)
    promotion_rows = promotion_candidate_rows(result_rows, limit=args.promotion_candidate_limit)
    write_tsv(promotion_path, promotion_rows, PROMOTION_FIELDS)
    ensure_regression_template(args.regression_benchmark)
    summary = summarize(result_rows, args=args, run_id=run_id)
    summary.update(
        {
            **selection_summary,
            "rows_tsv": str(rows_path),
            "top_result_review_queue_tsv": str(review_queue_path),
            "manual_promotion_candidates_tsv": str(promotion_path),
            "reviewed_regression_benchmark": str(args.regression_benchmark),
            "review_queue_rows": len(review_rows),
            "promotion_candidate_rows": len(promotion_rows),
        }
    )
    write_summary(summary_path, summary)
    write_seen_state(args.seen_state, selection_summary, run_id=run_id)
    write_markdown_report(
        report_path,
        summary=summary,
        rows_path=rows_path,
        review_queue_path=review_queue_path,
        promotion_path=promotion_path,
        benchmark_path=args.regression_benchmark,
    )

    print(f"wrote {len(result_rows)} diagnostic rows to {rows_path}")
    print(f"wrote {len(review_rows)} review rows to {review_queue_path}")
    print(f"wrote {len(promotion_rows)} promotion candidate rows to {promotion_path}")
    print(f"wrote summary to {summary_path}")
    return 1 if had_error and args.fail_on_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
