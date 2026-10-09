from __future__ import annotations

import json
import threading
import urllib.parse
from collections import OrderedDict
from typing import Iterable

from qe_evidence_vectors.code_index import (
    SAB_PRIORITY,
    TTY_PRIORITY,
    infer_umls_identifier_type,
    normalize_sab,
)
from qe_evidence_vectors.definition_index import _search_tokens
from qe_evidence_vectors.elastic_client import join_url, request_json
from qe_evidence_vectors.lexical_normalization import (
    lexical_normalized_key,
    lexical_normalized_tokens,
    lexical_variant_keys,
)
from qe_evidence_vectors.provenance_index import evidence_text_hash
from qe_evidence_vectors.research_relations import TARGET_LABELS
from qe_evidence_vectors.search_label_fallback import LabelFallback
from qe_evidence_vectors.text import normalized_key
from qe_evidence_vectors.universal_relationship import attach_universal_edge


def _quoted_index(index: str) -> str:
    return urllib.parse.quote(str(index or ""), safe=",*")


def _bool_to_yn(value: object, *, default: str = "N") -> str:
    if isinstance(value, bool):
        return "Y" if value else "N"
    text = str(value or default).strip().upper()
    return text if text in {"Y", "N", "O", "E"} else default


def _mapping_row(row: dict) -> dict:
    return {
        "cui": str(row.get("cui") or ""),
        "sab": str(row.get("sab") or ""),
        "code": str(row.get("code") or ""),
        "aui": str(row.get("aui") or ""),
        "scui": str(row.get("scui") or ""),
        "sdui": str(row.get("sdui") or ""),
        "tty": str(row.get("tty") or ""),
        "label": str(row.get("label") or ""),
        "ispref": _bool_to_yn(row.get("is_preferred", row.get("ispref"))),
        "suppress": _bool_to_yn(row.get("suppressed", row.get("suppress"))),
    }


class ElasticConceptCatalog:
    """Shared, cached access to the consolidated Elasticsearch concept catalog."""

    def __init__(
        self,
        *,
        base_url: str,
        index: str,
        cache_size: int = 20_000,
        request_func=request_json,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.index = index
        self.cache_size = max(100, int(cache_size or 100))
        self.request = request_func
        self._cache: OrderedDict[str, dict | None] = OrderedDict()
        self._lock = threading.Lock()
        self._count: int | None = None

    def _url(self, suffix: str) -> str:
        return join_url(self.base_url, f"{_quoted_index(self.index)}/{suffix.lstrip('/')}")

    def _store(self, cui: str, source: dict | None) -> None:
        with self._lock:
            self._cache[cui] = dict(source) if source is not None else None
            self._cache.move_to_end(cui)
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)

    def prefetch(self, cuis: Iterable[str]) -> None:
        wanted = []
        with self._lock:
            for raw_cui in cuis:
                cui = str(raw_cui or "").strip().upper()
                if cui and cui not in self._cache and cui not in wanted:
                    wanted.append(cui)
        if not wanted:
            return
        for start in range(0, len(wanted), 500):
            batch = wanted[start : start + 500]
            payload = self.request(
                method="POST",
                url=self._url("_mget"),
                payload={"ids": batch},
            )
            found = set()
            for item in payload.get("docs") or []:
                cui = str(item.get("_id") or "").strip().upper()
                if not cui:
                    continue
                found.add(cui)
                self._store(cui, item.get("_source") if item.get("found") else None)
            for cui in batch:
                if cui not in found:
                    self._store(cui, None)

    def get(self, cui: str) -> dict | None:
        cui = str(cui or "").strip().upper()
        if not cui:
            return None
        with self._lock:
            if cui in self._cache:
                source = self._cache[cui]
                self._cache.move_to_end(cui)
                return dict(source) if source is not None else None
        self.prefetch([cui])
        with self._lock:
            source = self._cache.get(cui)
            return dict(source) if source is not None else None

    def search(self, body: dict) -> dict:
        return self.request(method="POST", url=self._url("_search"), payload=body)

    def count(self) -> int:
        if self._count is None:
            payload = self.request(method="GET", url=self._url("_count"))
            self._count = int(payload.get("count") or 0)
        return self._count


class ElasticLabelFallback(LabelFallback):
    def __init__(
        self,
        catalog: ElasticConceptCatalog,
        *,
        max_tokens: int = 8,
        rows_per_span: int = 50,
    ) -> None:
        self.catalog = catalog
        self.paths = [f"elasticsearch:{catalog.index}"]
        self.max_tokens = max_tokens
        self.rows_per_span = rows_per_span
        self._lookup_cache: dict[tuple[str, int], list[dict]] = {}

    def indexes(self) -> list["ElasticLabelFallback"]:
        return [self]

    def lookup(self, norm: str, *, limit: int = 50) -> list[dict]:
        norm = str(norm or "").strip()
        key = (norm, int(limit))
        cached = self._lookup_cache.get(key)
        if cached is not None:
            return [dict(item) for item in cached]
        response = self.catalog.search(
            {
                "size": max(1, int(limit)),
                "query": {"term": {"label_norms": norm}},
                "_source": ["cui", "labels"],
            }
        )
        rows: list[dict] = []
        for hit in response.get("hits", {}).get("hits", []):
            source = hit.get("_source") or {}
            cui = str(source.get("cui") or hit.get("_id") or "")
            for label in source.get("labels") or []:
                if str(label.get("norm") or "") != norm:
                    continue
                rows.append(
                    {
                        "norm": norm,
                        "cui": cui,
                        "label": str(label.get("label") or ""),
                        "sab": str(label.get("sab") or ""),
                        "tty": str(label.get("tty") or ""),
                        "ispref": _bool_to_yn(label.get("is_preferred")),
                        "suppress": _bool_to_yn(label.get("suppressed")),
                    }
                )
                if len(rows) >= limit:
                    break
            if len(rows) >= limit:
                break
        self._lookup_cache[key] = [dict(item) for item in rows]
        return rows


class ElasticCodeIndex:
    def __init__(self, catalog: ElasticConceptCatalog) -> None:
        self.catalog = catalog
        self.path = f"elasticsearch:{catalog.index}"
        self.cache: dict[tuple, list[dict]] = {}

    def close(self) -> None:
        return None

    def mapping_count(self) -> int:
        return self.catalog.count()

    def preferred_label(self, cui: str) -> str:
        source = self.catalog.get(cui) or {}
        return str(source.get("preferred_label") or "")

    def has_active_cui(self, cui: str) -> bool:
        source = self.catalog.get(cui)
        if not source:
            return False
        return any(_bool_to_yn(row.get("suppressed")) == "N" for row in source.get("codes") or [])

    def has_legacy_cui(self, cui: str) -> bool:
        source = self.catalog.get(cui) or {}
        return bool(source.get("legacy_identifiers"))

    def legacy_label(self, cui: str) -> str:
        source = self.catalog.get(cui) or {}
        for row in source.get("legacy_identifiers") or []:
            label = str(row.get("label") or "")
            if label:
                return label
        return ""

    def lookup_cui(
        self,
        cui: str,
        *,
        sabs: Iterable[str] | None = None,
        limit: int = 100,
    ) -> list[dict]:
        cui = str(cui or "").strip().upper()
        wanted_sabs = {normalize_sab(sab) for sab in (sabs or []) if sab}
        source = self.catalog.get(cui) or {}
        rows = []
        for raw in source.get("codes") or []:
            if wanted_sabs and normalize_sab(raw.get("sab") or "") not in wanted_sabs:
                continue
            row = _mapping_row({"cui": cui, **raw})
            rows.append(row)
            if len(rows) >= limit:
                break
        return rows

    def lookup_aui_for_cui(
        self,
        cui: str,
        *,
        sabs: Iterable[str] | None = None,
        include_obsolete: bool = False,
        include_suppressible: bool = False,
        limit: int = 100,
    ) -> list[dict]:
        rows = []
        for row in self.lookup_cui(cui, sabs=sabs, limit=max(limit * 4, limit)):
            if not row.get("aui"):
                continue
            if not include_obsolete and row.get("suppress") == "O":
                continue
            if not include_suppressible and row.get("suppress") not in {"", "N"}:
                continue
            item = dict(row)
            item["matched_identifier_type"] = "AUI"
            item["matched_identifier"] = row.get("aui") or ""
            rows.append(item)
            if len(rows) >= limit:
                break
        return rows

    @staticmethod
    def _identifier_keys(identifier: str, identifier_type: str, sab: str = "") -> list[str]:
        value = str(identifier or "").strip().casefold()
        kind = str(identifier_type or "CODE").strip().upper()
        keys = [f"{kind}|{value}"]
        if sab:
            keys.insert(0, f"SAB|{normalize_sab(sab)}|{kind}|{value}")
        return keys

    def _search_identifier_docs(self, keys: list[str], *, limit: int) -> list[dict]:
        response = self.catalog.search(
            {
                "size": max(1, int(limit)),
                "query": {"terms": {"identifier_keys": keys}},
                "_source": True,
            }
        )
        return [dict(hit.get("_source") or {}) for hit in response.get("hits", {}).get("hits", [])]

    def lookup_code(
        self,
        code: str,
        *,
        sab: str | None = None,
        limit: int = 100,
        include_legacy: bool = True,
    ) -> list[dict]:
        sab_value = normalize_sab(sab or "") if sab else ""
        keys = []
        for kind in ("CODE", "SCUI", "SDUI"):
            keys.extend(self._identifier_keys(code, kind, sab_value))
        docs = self._search_identifier_docs(keys, limit=max(limit * 2, 20))
        wanted = str(code or "").strip().casefold()
        rows = []
        for source in docs:
            cui = str(source.get("cui") or "")
            for raw in source.get("codes") or []:
                if sab_value and normalize_sab(raw.get("sab") or "") != sab_value:
                    continue
                values = {str(raw.get(field) or "").casefold() for field in ("code", "scui", "sdui")}
                if wanted not in values:
                    continue
                rows.append(_mapping_row({"cui": cui, **raw}))
                if len(rows) >= limit:
                    return rows
        if not rows and include_legacy:
            return self.lookup_legacy_identifier(code, identifier_type="CODE", sab=sab_value or None, limit=limit)
        return rows

    def lookup_legacy_identifier(
        self,
        identifier: str,
        *,
        identifier_type: str,
        sab: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        identifier_type = str(identifier_type or "").strip().upper()
        sab_value = normalize_sab(sab or "") if sab else ""
        docs = self._search_identifier_docs(
            self._identifier_keys(identifier, f"LEGACY_{identifier_type}", sab_value),
            limit=max(limit * 2, 20),
        )
        wanted = str(identifier or "").strip().casefold()
        rows = []
        for source in docs:
            cui = str(source.get("cui") or "")
            for raw in source.get("legacy_identifiers") or []:
                if str(raw.get("identifier_type") or "").upper() != identifier_type:
                    continue
                if str(raw.get("identifier") or "").casefold() != wanted:
                    continue
                if sab_value and normalize_sab(raw.get("sab") or "") != sab_value:
                    continue
                item = _mapping_row({"cui": cui, **raw})
                item.update(
                    {
                        "identifier_type": identifier_type,
                        "identifier": str(raw.get("identifier") or ""),
                        "last_release": str(raw.get("last_release") or ""),
                    }
                )
                rows.append(item)
                if len(rows) >= limit:
                    return rows
        return rows

    def lookup_identifier(
        self,
        identifier: str,
        *,
        identifier_type: str | None = None,
        sab: str | None = None,
        limit: int = 100,
        include_legacy: bool = True,
    ) -> list[dict]:
        kind = normalize_sab(identifier_type or infer_umls_identifier_type(identifier) or "CODE")
        if kind == "CUI":
            rows = self.lookup_cui(identifier, sabs=[sab] if sab else None, limit=limit)
        elif kind in {"CODE", "SCUI", "SDUI"}:
            docs = self._search_identifier_docs(
                self._identifier_keys(identifier, kind, sab or ""),
                limit=max(limit * 2, 20),
            )
            wanted = str(identifier or "").strip().casefold()
            rows = []
            for source in docs:
                cui = str(source.get("cui") or "")
                for raw in source.get("codes") or []:
                    if sab and normalize_sab(raw.get("sab") or "") != normalize_sab(sab):
                        continue
                    if str(raw.get(kind.lower()) or "").casefold() != wanted:
                        continue
                    rows.append(_mapping_row({"cui": cui, **raw}))
                    if len(rows) >= limit:
                        return rows
        elif kind == "AUI":
            docs = self._search_identifier_docs(
                self._identifier_keys(identifier, "AUI", sab or ""),
                limit=max(limit * 2, 20),
            )
            wanted = str(identifier or "").strip().casefold()
            rows = []
            for source in docs:
                cui = str(source.get("cui") or "")
                for raw in source.get("codes") or []:
                    if str(raw.get("aui") or "").casefold() == wanted:
                        rows.append(_mapping_row({"cui": cui, **raw}))
                        if len(rows) >= limit:
                            return rows
        else:
            rows = []
        if not rows and include_legacy:
            rows = self.lookup_legacy_identifier(
                identifier,
                identifier_type=kind,
                sab=sab,
                limit=limit,
            )
        return rows[:limit]

    def search_source_atoms(
        self,
        query: str,
        *,
        sabs: Iterable[str],
        include_obsolete: bool = False,
        include_suppressible: bool = False,
        limit: int = 50,
    ) -> list[dict]:
        sab_values = sorted({normalize_sab(sab) for sab in sabs if sab})
        if not sab_values:
            return []
        response = self.catalog.search(
            {
                "size": max(limit * 2, 50),
                "query": {
                    "nested": {
                        "path": "codes",
                        "query": {
                            "bool": {
                                "must": [{"match": {"codes.label": {"query": query, "operator": "and"}}}],
                                "filter": [{"terms": {"codes.sab": sab_values}}],
                            }
                        },
                    }
                },
                "_source": ["cui", "codes"],
            }
        )
        query_tokens = set(normalized_key(query).split())
        query_norm = normalized_key(query)
        ranked = []
        for hit in response.get("hits", {}).get("hits", []):
            source = hit.get("_source") or {}
            cui = str(source.get("cui") or "")
            for raw in source.get("codes") or []:
                if normalize_sab(raw.get("sab") or "") not in sab_values:
                    continue
                suppress = _bool_to_yn(raw.get("suppressed"))
                if not include_obsolete and suppress == "O":
                    continue
                if not include_suppressible and suppress not in {"", "N"}:
                    continue
                label_norm = normalized_key(raw.get("label") or "")
                label_tokens = set(label_norm.split())
                if query_tokens and not query_tokens.issubset(label_tokens):
                    continue
                item = _mapping_row({"cui": cui, **raw})
                coverage = len(query_tokens & label_tokens) / max(len(query_tokens), 1)
                item["source_atom_score"] = round(
                    coverage + (0.5 if label_norm == query_norm else 0.0) + (0.02 if item["ispref"] == "Y" else 0.0),
                    6,
                )
                item["matched_query_tokens"] = sorted(query_tokens)
                ranked.append(item)
        ranked.sort(
            key=lambda item: (
                -float(item.get("source_atom_score") or 0.0),
                SAB_PRIORITY.get(str(item.get("sab") or ""), 99),
                TTY_PRIORITY.get(str(item.get("tty") or ""), 99),
                str(item.get("label") or "").lower(),
            )
        )
        return ranked[:limit]

    def search_labels(
        self,
        query: str,
        *,
        search_type: str = "words",
        sabs: Iterable[str] | None = None,
        include_obsolete: bool = False,
        include_suppressible: bool = False,
        partial: bool = False,
        limit: int = 200,
    ) -> list[dict]:
        norm = normalized_key(query)
        if not norm:
            return []
        search_type = str(search_type or "words")
        exact_norms = lexical_variant_keys(query) if search_type == "normalizedString" else [norm]
        if search_type in {"exact", "normalizedString"} and not partial:
            query_body = {"terms": {"label_norms": exact_norms}}
        else:
            query_body = {
                "nested": {
                    "path": "labels",
                    "query": {"match": {"labels.label": {"query": query, "operator": "or" if partial else "and"}}},
                }
            }
        response = self.catalog.search(
            {"size": max(limit * 2, 100), "query": query_body, "_source": ["cui", "labels", "codes"]}
        )
        wanted_sabs = {normalize_sab(sab) for sab in (sabs or []) if sab}
        wanted_tokens = lexical_normalized_tokens(query) if search_type == "normalizedWords" else norm.split()
        rows = []
        seen = set()
        for hit in response.get("hits", {}).get("hits", []):
            source = hit.get("_source") or {}
            cui = str(source.get("cui") or "")
            code_by_label = {str(row.get("label") or ""): row for row in source.get("codes") or []}
            for label in source.get("labels") or []:
                label_norm = str(label.get("norm") or "")
                if search_type in {"exact", "normalizedString"} and not partial and label_norm not in exact_norms:
                    continue
                if wanted_tokens:
                    label_tokens = label_norm.split()
                    if partial:
                        if not any(any(token in candidate for candidate in label_tokens) for token in wanted_tokens):
                            continue
                    elif not all(token in label_tokens for token in wanted_tokens):
                        continue
                sab = normalize_sab(label.get("sab") or "")
                if wanted_sabs and sab not in wanted_sabs:
                    continue
                suppress = _bool_to_yn(label.get("suppressed"))
                if not include_obsolete and suppress == "O":
                    continue
                if not include_suppressible and suppress not in {"", "N"}:
                    continue
                code = code_by_label.get(str(label.get("label") or ""), {})
                item = _mapping_row({"cui": cui, **code, **label})
                item["norm"] = label_norm
                dedupe = (cui, sab, item.get("code"), item.get("label"))
                if dedupe in seen:
                    continue
                seen.add(dedupe)
                rows.append(item)
                if len(rows) >= limit:
                    return rows
        return rows


class ElasticSemanticTypeIndex:
    def __init__(self, catalog: ElasticConceptCatalog) -> None:
        self.catalog = catalog
        self.path = f"elasticsearch:{catalog.index}"

    def close(self) -> None:
        return None

    def semantic_type_count(self) -> int:
        return 0

    def source_count(self) -> int:
        return self.catalog.count()

    def lookup(self, cui: str) -> list[dict]:
        source = self.catalog.get(cui) or {}
        return [
            {
                "tui": str(row.get("tui") or ""),
                "stn": str(row.get("stn") or ""),
                "name": str(row.get("name") or ""),
                "atui": str(row.get("atui") or ""),
            }
            for row in source.get("semantic_types") or []
        ]

    def lookup_identifier(
        self,
        identifier: str,
        *,
        identifier_type: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        identifier = str(identifier or "").strip().upper()
        kind = str(identifier_type or ("TUI" if identifier.startswith("T") else "ATUI")).upper()
        field = "semantic_types.tui" if kind == "TUI" else "semantic_types.atui"
        response = self.catalog.search(
            {
                "size": limit,
                "query": {"nested": {"path": "semantic_types", "query": {"term": {field: identifier}}}},
                "_source": ["cui", "semantic_types"],
            }
        )
        rows = []
        for hit in response.get("hits", {}).get("hits", []):
            source = hit.get("_source") or {}
            for row in source.get("semantic_types") or []:
                if str(row.get(kind.lower()) or "").upper() != identifier:
                    continue
                rows.append(
                    {
                        "cui": str(source.get("cui") or ""),
                        "tui": str(row.get("tui") or ""),
                        "stn": str(row.get("stn") or ""),
                        "name": str(row.get("name") or ""),
                        "atui": str(row.get("atui") or ""),
                        "matched_identifier_type": kind,
                        "matched_identifier": identifier,
                    }
                )
                if len(rows) >= limit:
                    return rows
        return rows


class ElasticDefinitionIndex:
    def __init__(self, catalog: ElasticConceptCatalog) -> None:
        self.catalog = catalog
        self.path = f"elasticsearch:{catalog.index}"

    def close(self) -> None:
        return None

    def definition_count(self) -> int:
        return 0

    def cui_count(self) -> int:
        return self.catalog.count()

    def lookup(self, cui: str, *, limit: int = 3) -> list[dict]:
        source = self.catalog.get(cui) or {}
        rows = sorted(source.get("definitions") or [], key=lambda row: int(row.get("rank") or 0))
        return [
            {
                "cui": str(source.get("cui") or cui),
                "source": str(row.get("source") or ""),
                "definition": str(row.get("definition") or ""),
                "rank": int(row.get("rank") or 0),
            }
            for row in rows[:limit]
        ]

    def lookup_identifier(
        self,
        identifier: str,
        *,
        identifier_type: str = "ATUI",
        limit: int = 10,
    ) -> list[dict]:
        identifier = str(identifier or "").strip().upper()
        kind = str(identifier_type or "ATUI").strip().upper()
        if kind not in {"AUI", "ATUI"}:
            return []
        field = f"definitions.{kind.lower()}"
        response = self.catalog.search(
            {
                "size": limit,
                "query": {"nested": {"path": "definitions", "query": {"term": {field: identifier}}}},
                "_source": ["cui", "definitions"],
            }
        )
        rows = []
        for hit in response.get("hits", {}).get("hits", []):
            source = hit.get("_source") or {}
            for row in source.get("definitions") or []:
                if str(row.get(kind.lower()) or "").upper() != identifier:
                    continue
                rows.append(
                    {
                        "cui": str(source.get("cui") or ""),
                        "source": str(row.get("source") or ""),
                        "definition": str(row.get("definition") or ""),
                        "rank": int(row.get("rank") or 0),
                        "matched_identifier_type": kind,
                        "matched_identifier": identifier,
                    }
                )
                if len(rows) >= limit:
                    return rows
        return rows

    def search(self, query: str, *, limit: int = 50) -> list[dict]:
        tokens = _search_tokens(query)
        if len(tokens) < 2:
            return []
        response = self.catalog.search(
            {
                "size": max(limit, 1),
                "query": {
                    "nested": {
                        "path": "definitions",
                        "query": {"match": {"definitions.definition": {"query": " ".join(tokens), "operator": "and"}}},
                        "inner_hits": {"size": 1, "sort": [{"definitions.rank": "asc"}]},
                    }
                },
                "_source": ["cui"],
            }
        )
        rows = []
        for hit in response.get("hits", {}).get("hits", []):
            source = hit.get("_source") or {}
            inner = (hit.get("inner_hits") or {}).get("definitions", {}).get("hits", {}).get("hits", [])
            if not inner:
                continue
            definition = inner[0].get("_source") or {}
            rank = int(definition.get("rank") or 0)
            rows.append(
                {
                    "cui": str(source.get("cui") or hit.get("_id") or ""),
                    "source": str(definition.get("source") or ""),
                    "definition": str(definition.get("definition") or ""),
                    "rank": rank,
                    "score": round(max(0.72, 0.90 - (0.015 * max(rank - 1, 0))), 6),
                    "bm25": -float(hit.get("_score") or 0.0),
                    "match_query": " AND ".join(f"{token}*" for token in tokens),
                }
            )
        return rows[:limit]


class ElasticRelationStore:
    def __init__(self, *, base_url: str, index: str, request_func=request_json) -> None:
        self.base_url = base_url.rstrip("/")
        self.index = index
        self.request = request_func

    def _url(self, suffix: str) -> str:
        return join_url(self.base_url, f"{_quoted_index(self.index)}/{suffix.lstrip('/')}")

    def search(self, body: dict) -> dict:
        return self.request(method="POST", url=self._url("_search"), payload=body)

    def count(self, kind: str) -> int:
        response = self.request(
            method="POST",
            url=self._url("_count"),
            payload={"query": {"term": {"kind": kind}}},
        )
        return int(response.get("count") or 0)

    def cardinality(self, kind: str, field: str = "source_cui") -> int:
        response = self.search(
            {
                "size": 0,
                "query": {"term": {"kind": kind}},
                "aggs": {"value": {"cardinality": {"field": field, "precision_threshold": 40000}}},
            }
        )
        return int(response.get("aggregations", {}).get("value", {}).get("value") or 0)

    def rows(self, *, kind: str, field: str, value: str, limit: int, sort: list | None = None) -> list[dict]:
        response = self.search(
            {
                "size": max(1, int(limit)),
                "query": {"bool": {"filter": [{"term": {"kind": kind}}, {"term": {field: value}}]}},
                "sort": sort or [{"rank": "asc"}],
            }
        )
        return [dict(hit.get("_source") or {}) for hit in response.get("hits", {}).get("hits", [])]


class ElasticRelationIndex:
    def __init__(self, store: ElasticRelationStore) -> None:
        self.store = store
        self.path = f"elasticsearch:{store.index}"

    def close(self) -> None:
        return None

    def source_count(self) -> int:
        return self.store.cardinality("umls")

    def relation_count(self) -> int:
        return self.store.count("umls")

    @staticmethod
    def _row(row: dict, *, incoming: bool = False) -> dict:
        source_cui = str(row.get("source_cui") or "")
        target_cui = str(row.get("target_cui") or "")
        item = {
            "source_cui": source_cui,
            "target_cui": target_cui,
            "cui": source_cui if incoming else target_cui,
            "relation": str(row.get("relation") or ""),
            "rela": str(row.get("rela") or ""),
            "rui": str(row.get("rui") or ""),
            "source": str(row.get("sab") or ""),
            "direction": str(row.get("direction") or ""),
            "label": str(row.get("label") or "").replace("_", " "),
            "rank": int(row.get("rank") or 0),
        }
        return attach_universal_edge(item, subject_cui=source_cui, object_cui=target_cui)

    def lookup(self, cui: str, *, limit: int = 8) -> list[dict]:
        return [self._row(row) for row in self.store.rows(kind="umls", field="source_cui", value=cui, limit=limit)]

    def lookup_incoming(self, cui: str, *, limit: int = 16) -> list[dict]:
        return [self._row(row, incoming=True) for row in self.store.rows(kind="umls", field="target_cui", value=cui, limit=limit)]

    def lookup_children(self, cui: str, *, limit: int = 100) -> list[dict]:
        return self.lookup_children_many([cui], limit_per_parent=limit).get(cui, [])

    def lookup_children_many(
        self,
        cuis: Iterable[str],
        *,
        limit_per_parent: int = 100,
    ) -> dict[str, list[dict]]:
        parents = list(dict.fromkeys(str(cui or "").strip().upper() for cui in cuis if cui))
        if not parents:
            return {}
        per_parent = max(1, min(int(limit_per_parent or 1), 100))
        response = self.store.search(
            {
                "size": 0,
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"kind": "umls"}},
                            {"terms": {"source_cui": parents}},
                            {
                                "bool": {
                                    "minimum_should_match": 1,
                                    "should": [
                                        {
                                            "bool": {
                                                "filter": [
                                                    {"term": {"relation": "PAR"}},
                                                    {"term": {"direction": "incoming"}},
                                                ]
                                            }
                                        },
                                        {
                                            "bool": {
                                                "filter": [
                                                    {"term": {"relation": "CHD"}},
                                                    {"term": {"direction": "outgoing"}},
                                                ]
                                            }
                                        },
                                    ],
                                }
                            },
                        ]
                    }
                },
                "aggs": {
                    "parents": {
                        "terms": {
                            "field": "source_cui",
                            "size": len(parents),
                            "include": parents,
                        },
                        "aggs": {
                            "children": {
                                "top_hits": {
                                    "size": per_parent,
                                    "sort": [
                                        {"rank": "asc"},
                                        {"target_cui": "asc"},
                                    ],
                                }
                            }
                        },
                    }
                },
            }
        )
        results: dict[str, list[dict]] = {parent: [] for parent in parents}
        for bucket in response.get("aggregations", {}).get("parents", {}).get("buckets", []):
            parent = str(bucket.get("key") or "").strip().upper()
            seen: set[str] = set()
            for hit in bucket.get("children", {}).get("hits", {}).get("hits", []):
                row = dict(hit.get("_source") or {})
                child = str(row.get("target_cui") or "").strip().upper()
                if not child or child in seen:
                    continue
                seen.add(child)
                results.setdefault(parent, []).append(
                    {
                        "parent_cui": parent,
                        "child_cui": child,
                        "cui": child,
                        "relation": str(row.get("relation") or ""),
                        "rela": str(row.get("rela") or ""),
                        "rui": str(row.get("rui") or ""),
                        "source": str(row.get("sab") or ""),
                        "direction": str(row.get("direction") or ""),
                        "label": str(row.get("label") or ""),
                        "rank": int(row.get("rank") or 0),
                    }
                )
        return results

    def lookup_identifier(self, identifier: str, *, identifier_type: str = "RUI", limit: int = 16) -> list[dict]:
        if str(identifier_type or "").upper() != "RUI":
            return []
        rows = self.store.rows(kind="umls", field="rui", value=str(identifier).upper(), limit=limit)
        results = [self._row(row) for row in rows]
        for item in results:
            item["matched_identifier_type"] = "RUI"
            item["matched_identifier"] = str(identifier).upper()
        return results


class ElasticResearchRelationIndex:
    def __init__(self, store: ElasticRelationStore) -> None:
        self.store = store
        self.path = f"elasticsearch:{store.index}"

    def close(self) -> None:
        return None

    def source_count(self) -> int:
        return self.store.cardinality("research")

    def relation_count(self) -> int:
        return self.store.count("research")

    @staticmethod
    def _row(row: dict, *, incoming: bool = False) -> dict:
        source_cui = str(row.get("source_cui") or "")
        target_cui = str(row.get("target_cui") or "")
        category = str(row.get("category") or "")
        item = {
            "source_cui": source_cui,
            "target_cui": target_cui,
            "cui": source_cui if incoming else target_cui,
            "category": category,
            "category_label": TARGET_LABELS.get(category, category),
            "relation_group": str(row.get("relation_group") or ""),
            "relation": str(row.get("relation") or ""),
            "rela": str(row.get("rela") or ""),
            "source": str(row.get("sab") or ""),
            "direction": str(row.get("direction") or ""),
            "label": str(row.get("label") or ""),
            "source_semantic_type": str(row.get("source_semantic_type") or ""),
            "target_semantic_type": str(row.get("target_semantic_type") or ""),
            "semantic_type": str(row.get("target_semantic_type") or ""),
            "rank": int(row.get("rank") or 0),
        }
        return attach_universal_edge(item, subject_cui=source_cui, object_cui=target_cui)

    def lookup(self, cui: str, *, limit_per_category: int = 6) -> list[dict]:
        rows = self.store.rows(kind="research", field="source_cui", value=cui, limit=max(limit_per_category * 12, 72))
        counts: dict[str, int] = {}
        results = []
        seen = set()
        for row in rows:
            category = str(row.get("category") or "")
            key = (category, str(row.get("target_cui") or ""))
            if key in seen or counts.get(category, 0) >= limit_per_category:
                continue
            seen.add(key)
            counts[category] = counts.get(category, 0) + 1
            results.append(self._row(row))
        return results

    def lookup_incoming(self, cui: str, *, limit: int = 48) -> list[dict]:
        return [self._row(row, incoming=True) for row in self.store.rows(kind="research", field="target_cui", value=cui, limit=limit)]


class ElasticRelationshipEdgeIndex:
    def __init__(self, store: ElasticRelationStore) -> None:
        self.store = store
        self.path = f"elasticsearch:{store.index}"

    def close(self) -> None:
        return None

    def source_count(self) -> int:
        return self.store.cardinality("derived")

    def edge_count(self) -> int:
        return self.store.count("derived")

    @staticmethod
    def _row(row: dict, *, incoming: bool = False) -> dict:
        item = {
            "source_cui": str(row.get("source_cui") or ""),
            "target_cui": str(row.get("target_cui") or ""),
            "cui": str((row.get("source_cui") if incoming else row.get("target_cui")) or ""),
            "relationship_type": str(row.get("relationship_type") or row.get("relation") or ""),
            "relation": str(row.get("relation") or ""),
            "rela": str(row.get("rela") or ""),
            "relation_group": str(row.get("relation_group") or ""),
            "source": str(row.get("sab") or ""),
            "source_class": str(row.get("source_class") or ""),
            "direction": "incoming" if incoming else str(row.get("direction") or "outgoing"),
            "label": str(row.get("label") or ""),
            "source_label": str(row.get("source_label") or ""),
            "strength": float(row.get("strength") or 0.0),
            "confidence": float(row.get("confidence") or 0.0),
            "rank": int(row.get("rank") or 0),
        }
        if isinstance(row.get("context"), dict):
            item["context"] = dict(row["context"])
        return item

    def lookup(self, cui: str, *, limit: int = 24) -> list[dict]:
        rows = self.store.rows(
            kind="derived",
            field="source_cui",
            value=cui,
            limit=limit,
            sort=[{"confidence": "desc"}, {"strength": "desc"}, {"rank": "asc"}],
        )
        return [self._row(row) for row in rows]

    def lookup_incoming(self, cui: str, *, limit: int = 24) -> list[dict]:
        rows = self.store.rows(
            kind="derived",
            field="target_cui",
            value=cui,
            limit=limit,
            sort=[{"confidence": "desc"}, {"strength": "desc"}, {"rank": "asc"}],
        )
        return [self._row(row, incoming=True) for row in rows]


class ElasticProvenanceIndex:
    def __init__(self, *, base_url: str, index: str, request_func=request_json) -> None:
        self.base_url = base_url.rstrip("/")
        self.index = index
        self.path = f"elasticsearch:{index}"
        self.request = request_func
        self._count: int | None = None
        self.cache: dict[tuple[str, str, int], list[dict]] = {}

    def _url(self, suffix: str) -> str:
        return join_url(self.base_url, f"{_quoted_index(self.index)}/{suffix.lstrip('/')}")

    def source_count(self) -> int:
        if self._count is None:
            payload = self.request(method="GET", url=self._url("_count"))
            self._count = int(payload.get("count") or 0)
        return self._count

    def lookup_sources(self, doc_id: str, text: str, *, limit: int = 5) -> list[dict]:
        text_hash = evidence_text_hash(text)
        key = (doc_id, text_hash, int(limit))
        cached = self.cache.get(key)
        if cached is not None:
            return [dict(item) for item in cached]
        payload = self.request(
            method="POST",
            url=self._url("_search"),
            payload={
                "size": max(1, int(limit)),
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"doc_id": doc_id}},
                            {"term": {"text_hash": text_hash}},
                        ]
                    }
                },
                "sort": [{"rank": "asc"}, {"citation_hash": "asc"}],
                "_source": ["citation"],
            },
        )
        results = []
        for hit in payload.get("hits", {}).get("hits", []):
            citation = (hit.get("_source") or {}).get("citation")
            if isinstance(citation, dict):
                results.append(dict(citation))
            elif isinstance(citation, str):
                try:
                    decoded = json.loads(citation)
                except json.JSONDecodeError:
                    continue
                if isinstance(decoded, dict):
                    results.append(decoded)
        self.cache[key] = [dict(item) for item in results]
        return results
