from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterable


def join_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def request_json(
    *,
    method: str,
    url: str,
    payload: dict | None = None,
    data: bytes | None = None,
    content_type: str = "application/json",
) -> dict:
    if payload is not None and data is not None:
        raise ValueError("pass payload or data, not both")
    body = data
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method=method)
    if body is not None:
        request.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            detail = json.loads(raw.decode("utf-8"))
        except Exception:
            detail = raw.decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed with HTTP {exc.code}: {detail}") from exc
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def create_index(
    *,
    base_url: str,
    index: str,
    mapping_path: str | Path,
    delete_existing: bool = False,
) -> dict:
    url = join_url(base_url, urllib.parse.quote(index))
    if delete_existing:
        try:
            request_json(method="DELETE", url=url)
        except RuntimeError as exc:
            if "HTTP 404" not in str(exc):
                raise
    mapping = json.loads(Path(mapping_path).expanduser().read_text(encoding="utf-8"))
    return request_json(method="PUT", url=url, payload=mapping)


def add_alias(*, base_url: str, index: str, alias: str) -> dict:
    return request_json(
        method="POST",
        url=join_url(base_url, "_aliases"),
        payload={"actions": [{"add": {"index": index, "alias": alias}}]},
    )


def delete_docs_by_cui(*, base_url: str, index: str, cuis: Iterable[str]) -> dict:
    cui_values = sorted({cui for cui in cuis if cui})
    if not cui_values:
        raise ValueError("at least one CUI is required")
    return request_json(
        method="POST",
        url=join_url(
            base_url,
            f"{urllib.parse.quote(index)}/_delete_by_query?conflicts=proceed&refresh=true",
        ),
        payload={"query": {"terms": {"cui": cui_values}}},
    )


def _part_glob(path: Path) -> list[Path]:
    suffix = path.suffix or ".ndjson"
    stem = path.name[: -len(suffix)] if path.name.endswith(suffix) else path.name
    return sorted(path.parent.glob(f"{stem}.part-*{suffix}"))


def resolve_bulk_paths(paths: Iterable[str | Path]) -> list[Path]:
    resolved: list[Path] = []
    for raw_path in paths:
        path = Path(raw_path).expanduser()
        if path.exists():
            resolved.append(path)
            continue
        part_paths = _part_glob(path)
        if part_paths:
            resolved.extend(part_paths)
            continue
        raise FileNotFoundError(path)
    return resolved


def load_bulk_file(*, base_url: str, path: str | Path) -> dict:
    raw = Path(path).expanduser().read_bytes()
    if not raw.endswith(b"\n"):
        raw += b"\n"
    return request_json(
        method="POST",
        url=join_url(base_url, "_bulk"),
        data=raw,
        content_type="application/x-ndjson",
    )


def _item_has_error(item: dict) -> bool:
    for payload in item.values():
        if isinstance(payload, dict) and "error" in payload:
            return True
    return False


def load_bulk_files(*, base_url: str, paths: Iterable[str | Path]) -> tuple[int, int]:
    total_items = 0
    total_errors = 0
    for path in resolve_bulk_paths(paths):
        response = load_bulk_file(base_url=base_url, path=path)
        items = response.get("items", [])
        total_items += len(items)
        if response.get("errors"):
            total_errors += sum(1 for item in items if _item_has_error(item))
    return total_items, total_errors


def build_knn_search_body(
    *,
    vector: list[float],
    vector_field: str = "vector",
    k: int = 10,
    num_candidates: int = 100,
    source_fields: list[str] | None = None,
    exclude_source_prefixes: Iterable[str] | None = None,
) -> dict:
    if source_fields is None:
        source_fields = [
            "doc_id",
            "cui",
            "view",
            "sources",
            "labels",
            "text",
            "evidence_count",
            "total_weight",
            "embedding_provider",
            "embedding_model",
        ]
    knn = {
        "field": vector_field,
        "query_vector": vector,
        "k": k,
        "num_candidates": num_candidates,
    }
    source_prefixes = sorted({prefix.strip() for prefix in (exclude_source_prefixes or []) if prefix.strip()})
    if source_prefixes:
        knn["filter"] = {
            "bool": {
                "must_not": [
                    {"prefix": {"sources": prefix}}
                    for prefix in source_prefixes
                ]
            }
        }
    return {
        "size": k,
        "knn": knn,
        "_source": source_fields,
    }


def search_knn(
    *,
    base_url: str,
    index: str,
    vector: list[float],
    vector_field: str = "vector",
    k: int = 10,
    num_candidates: int = 100,
    exclude_source_prefixes: Iterable[str] | None = None,
) -> list[dict]:
    body = build_knn_search_body(
        vector=vector,
        vector_field=vector_field,
        k=k,
        num_candidates=num_candidates,
        exclude_source_prefixes=exclude_source_prefixes,
    )
    response = request_json(
        method="POST",
        url=join_url(base_url, f"{urllib.parse.quote(index)}/_search"),
        payload=body,
    )
    return list(response.get("hits", {}).get("hits", []))
