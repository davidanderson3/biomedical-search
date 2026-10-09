from __future__ import annotations

from collections import deque
from collections.abc import Iterable


DEFAULT_DESCENDANT_MAX_DEPTH = 1
DEFAULT_DESCENDANT_LIMIT = 40
DEFAULT_DESCENDANT_BRANCH_LIMIT = 100
MAX_DESCENDANT_DEPTH = 3
MAX_DESCENDANT_LIMIT = 100
MAX_DESCENDANT_SEEDS = 3


def bounded_descendant_depth(value: object = None) -> int:
    try:
        depth = int(value or DEFAULT_DESCENDANT_MAX_DEPTH)
    except (TypeError, ValueError) as exc:
        raise ValueError("descendant depth must be an integer") from exc
    if not 1 <= depth <= MAX_DESCENDANT_DEPTH:
        raise ValueError(f"descendant depth must be between 1 and {MAX_DESCENDANT_DEPTH}")
    return depth


def bounded_descendant_limit(value: object = None) -> int:
    try:
        limit = int(value or DEFAULT_DESCENDANT_LIMIT)
    except (TypeError, ValueError) as exc:
        raise ValueError("descendant limit must be an integer") from exc
    if not 1 <= limit <= MAX_DESCENDANT_LIMIT:
        raise ValueError(f"descendant limit must be between 1 and {MAX_DESCENDANT_LIMIT}")
    return limit


def normalize_descendant_seeds(cuis: Iterable[object]) -> list[str]:
    seeds: list[str] = []
    seen: set[str] = set()
    for value in cuis:
        cui = str(value or "").strip().upper()
        if not cui or cui in seen:
            continue
        seen.add(cui)
        seeds.append(cui)
        if len(seeds) >= MAX_DESCENDANT_SEEDS:
            break
    return seeds


def _children_by_parent(
    relation_index: object,
    parents: list[str],
    *,
    limit_per_parent: int,
) -> dict[str, list[dict]]:
    batch_lookup = getattr(relation_index, "lookup_children_many", None)
    if callable(batch_lookup):
        rows = batch_lookup(parents, limit_per_parent=limit_per_parent)
        return {
            str(parent or "").strip().upper(): [dict(row) for row in values]
            for parent, values in (rows or {}).items()
        }
    lookup = getattr(relation_index, "lookup_children", None)
    if not callable(lookup):
        return {}
    return {
        parent: [dict(row) for row in lookup(parent, limit=limit_per_parent)]
        for parent in parents
    }


def traverse_descendants(
    relation_index: object | None,
    seeds: Iterable[object],
    *,
    max_depth: int = DEFAULT_DESCENDANT_MAX_DEPTH,
    limit: int = DEFAULT_DESCENDANT_LIMIT,
    branch_limit: int = DEFAULT_DESCENDANT_BRANCH_LIMIT,
) -> dict:
    """Breadth-first UMLS descendant traversal with hard cycle and fan-out bounds.

    The relation adapter is responsible for interpreting MRREL direction and
    returning rows with ``parent_cui`` and ``child_cui``.  A concept is visited
    at most once across the traversal, so self loops and longer UMLS cycles
    cannot cause repeated work or repeated candidates.
    """

    normalized_seeds = normalize_descendant_seeds(seeds)
    depth_limit = bounded_descendant_depth(max_depth)
    result_limit = bounded_descendant_limit(limit)
    per_parent_limit = max(1, min(int(branch_limit or 1), MAX_DESCENDANT_LIMIT))
    metadata = {
        "enabled": bool(relation_index and normalized_seeds),
        "seeds": normalized_seeds,
        "max_depth": depth_limit,
        "limit": result_limit,
        "branch_limit": per_parent_limit,
        "visited_count": len(normalized_seeds),
        "candidate_count": 0,
        "cycle_skips": 0,
        "duplicate_edge_skips": 0,
        "truncated": False,
        "candidates": [],
    }
    if not relation_index or not normalized_seeds:
        return metadata

    visited = set(normalized_seeds)
    frontier = list(normalized_seeds)
    parent_paths: dict[str, list[str]] = {seed: [seed] for seed in normalized_seeds}
    parent_seeds: dict[str, str] = {seed: seed for seed in normalized_seeds}
    candidates: list[dict] = []

    for depth in range(1, depth_limit + 1):
        if not frontier or len(candidates) >= result_limit:
            break
        rows_by_parent = _children_by_parent(
            relation_index,
            frontier,
            limit_per_parent=per_parent_limit,
        )
        next_frontier: list[str] = []
        seen_edges: set[tuple[str, str, str, str]] = set()
        for parent in frontier:
            rows = rows_by_parent.get(parent, [])
            for row in rows:
                child = str(row.get("child_cui") or row.get("cui") or "").strip().upper()
                if not child:
                    continue
                edge_key = (
                    parent,
                    child,
                    str(row.get("relation") or "").upper(),
                    str(row.get("source") or row.get("sab") or "").upper(),
                )
                if edge_key in seen_edges:
                    metadata["duplicate_edge_skips"] += 1
                    continue
                seen_edges.add(edge_key)
                if child in visited:
                    metadata["cycle_skips"] += 1
                    continue
                visited.add(child)
                path = [*parent_paths.get(parent, [parent]), child]
                seed = parent_seeds.get(parent, parent)
                candidate = {
                    **row,
                    "cui": child,
                    "parent_cui": parent,
                    "child_cui": child,
                    "seed_cui": seed,
                    "depth": depth,
                    "path": path,
                }
                candidates.append(candidate)
                next_frontier.append(child)
                parent_paths[child] = path
                parent_seeds[child] = seed
                if len(candidates) >= result_limit:
                    metadata["truncated"] = True
                    break
            if len(candidates) >= result_limit:
                break
        frontier = next_frontier

    metadata["visited_count"] = len(visited)
    metadata["candidate_count"] = len(candidates)
    metadata["candidates"] = candidates
    return metadata
