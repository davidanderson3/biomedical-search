from __future__ import annotations

import time
from array import array
from copy import deepcopy
from urllib.error import URLError

from qe_evidence_vectors.generic_filters import is_blocked_generic_query
from qe_evidence_vectors.search_hit_features import semantic_type_names
from qe_evidence_vectors.search_hydration import normalize_return_code_sabs
from qe_evidence_vectors.search_long_documents import LongDocumentChunk, plan_long_document_chunks
from qe_evidence_vectors.search_semantics import semantic_group_metadata
from qe_evidence_vectors.search_semantic_buckets import (
    hit_relevance_score,
    hit_matches_any_semantic_bucket,
    normalize_semantic_bucket_filter,
    SELECTED_SEMANTIC_BUCKET_MIN_RELEVANCE,
)
from qe_evidence_vectors.search_utils import (
    dot,
    source_mix_from_evidence_items,
)
from qe_evidence_vectors.search_tokens import content_tokens

VALID_SEARCH_MODES = {"balanced", "exact", "comprehensive"}
SEARCH_SCOPE_UMLS = "umls"
SEARCH_SCOPE_UMLS_EVIDENCE = "umls_evidence"
VALID_SEARCH_SCOPES = {"umls", "umls_evidence"}
MIN_RESULT_RELEVANCE_BY_MODE = {
    "balanced": 0.60,
    "exact": 0.60,
    "comprehensive": 0.35,
}
SEMANTIC_FILTER_MIN_RESULT_RELEVANCE_BY_MODE = {
    "balanced": SELECTED_SEMANTIC_BUCKET_MIN_RELEVANCE,
    "exact": SELECTED_SEMANTIC_BUCKET_MIN_RELEVANCE,
    "comprehensive": SELECTED_SEMANTIC_BUCKET_MIN_RELEVANCE,
}
MIN_RESULT_RELEVANCE_PROTECTED_MATCH_TYPES = {
    "code",
    "code_label_broadened",
    "cui",
    "relation_identifier",
    "rui",
    "semantic_type_identifier",
    "system_code",
    "system_code_label_broadened",
    "tui",
    "atui",
    "umls_identifier",
}
MIN_RESULT_RELEVANCE_PROTECTED_SINGLE_TOKEN_LABEL_SPANS = {
    "homelessness",
}
TEMPORAL_WORD_CHEMICAL_SPANS = {
    "today",
    "tomorrow",
    "tonight",
    "yesterday",
}
TEMPORAL_WORD_CHEMICAL_SEMANTIC_TYPES = {
    "inorganic chemical",
    "organic chemical",
}


def temporal_word_chemical_false_positive(hit: dict, *, query: object = None) -> bool:
    if str(hit.get("matched_code_input") or "").strip():
        return False
    if str(hit.get("match_type") or "") in MIN_RESULT_RELEVANCE_PROTECTED_MATCH_TYPES:
        return False
    if str(hit.get("code_match_type") or "") in MIN_RESULT_RELEVANCE_PROTECTED_MATCH_TYPES:
        return False
    span_tokens = content_tokens(
        str(
            hit.get("matched_query_span")
            or hit.get("matched_input")
            or hit.get("matched_label")
            or hit.get("name")
            or ""
        )
    )
    if len(span_tokens) != 1 or span_tokens[0] not in TEMPORAL_WORD_CHEMICAL_SPANS:
        return False
    return bool(semantic_type_names(hit) & TEMPORAL_WORD_CHEMICAL_SEMANTIC_TYPES)


def exact_label_hit_protected_from_min_result_relevance(hit: dict) -> bool:
    if str(hit.get("match_type") or "") != "umls_label":
        return False
    assertion = hit.get("assertion") or {}
    if assertion.get("status") == "negated":
        return False
    span = str(hit.get("matched_query_span") or "").strip().lower()
    if not span:
        return False
    try:
        label_score = float(hit.get("label_fallback_score") or hit.get("score") or 0.0)
    except (TypeError, ValueError):
        label_score = 0.0
    if label_score < 1.05:
        return False
    sources = {str(source) for source in hit.get("sources") or []}
    if "active_label_supplement" not in sources and int(hit.get("evidence_count") or 0) <= 0:
        return False
    span_tokens = [token for token in span.replace("-", " ").split() if token]
    if len(span_tokens) == 1 and span_tokens[0] not in MIN_RESULT_RELEVANCE_PROTECTED_SINGLE_TOKEN_LABEL_SPANS:
        return False
    return True


class SearchBackendUnavailable(RuntimeError):
    pass


def normalize_search_mode(value: object = None) -> str:
    mode = str(value or "balanced").strip().lower().replace("_", "-")
    aliases = {
        "default": "balanced",
        "normal": "balanced",
        "standard": "balanced",
        "broad": "comprehensive",
        "wide": "comprehensive",
        "literal": "exact",
    }
    mode = aliases.get(mode, mode)
    if mode not in VALID_SEARCH_MODES:
        raise ValueError(
            "search mode must be one of: balanced, exact, comprehensive"
        )
    return mode


def normalize_search_scope(value: object = None) -> str:
    scope = str(value or "umls_evidence").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "default": "umls_evidence",
        "evidence": "umls_evidence",
        "expanded": "umls_evidence",
        "hybrid": "umls_evidence",
        "full": "umls_evidence",
        "umls+evidence": "umls_evidence",
        "umls_and_evidence": "umls_evidence",
        "umls_evidence": "umls_evidence",
        "umls_only": "umls",
        "umls": "umls",
        "labels": "umls",
        "label": "umls",
        "vocabulary": "umls",
    }
    scope = aliases.get(scope, scope)
    if scope not in VALID_SEARCH_SCOPES:
        raise ValueError("search scope must be one of: umls, umls_evidence")
    return scope


class SearchExecutionMixin:
    SEARCH_HIT_DETAIL_FIELDS = {
        "definitions",
        "evidence_items",
        "evidence_related_concepts",
        "external_embedding_neighbors",
        "images",
        "mappings",
        "mrrel_related_concepts",
        "related_concepts",
        "research_relations",
        "source_mix",
        "text",
    }
    SEARCH_HIT_DEBUG_FIELDS = {
        "retrieval",
        "source_bundle",
        "vector_lineage",
        "vector_path",
        "vector_row",
    }

    def search_cache_key(
        self,
        query: str,
        *,
        top_k: int,
        include_related: bool,
        include_linked_concepts: bool,
        include_evidence_items: bool,
        semantic_bucket_keys: object = None,
        search_mode: object = None,
        search_scope: object = None,
        return_code_sabs: object = None,
        debug: bool = False,
    ) -> tuple:
        mode = normalize_search_mode(search_mode)
        scope = normalize_search_scope(search_scope)
        code_sabs = normalize_return_code_sabs(return_code_sabs)
        return (
            "search",
            str(query or "").strip(),
            int(top_k),
            bool(include_related),
            bool(include_linked_concepts),
            bool(include_evidence_items),
            bool(debug),
            mode,
            scope,
            code_sabs,
            tuple(normalize_semantic_bucket_filter(semantic_bucket_keys)),
            int(getattr(self, "related_limit", 0) or 0),
            int(getattr(self, "related_source_limit", 0) or 0),
            int(getattr(self, "expensive_related_source_limit", 0) or 0),
            int(getattr(self, "candidate_pool_multiplier", 0) or 0),
            int(getattr(self, "candidate_pool_min", 0) or 0),
            int(getattr(self, "label_fallback_limit", 0) or 0),
            int(getattr(self, "definition_fallback_limit", 0) or 0),
            str(getattr(self, "elastic_url", "") or ""),
            str(getattr(self, "elastic_index", "") or ""),
            int(getattr(self, "elastic_num_candidates", 0) or 0),
        )

    def strip_evidence_from_umls_hit(self, hit: dict) -> dict:
        cui = str(hit.get("cui") or "").strip().upper()
        match_type = str(hit.get("match_type") or "")
        sources = [
            str(source).strip()
            for source in (hit.get("sources") or [])
            if str(source).strip().startswith("umls")
            or str(source).strip() in {
                "code",
                "cui",
                "resolver",
                "rui",
                "system_code",
                "semantic_type_identifier",
            }
        ]
        source_from_match = {
            "code": "umls_code",
            "cui": "umls_cui",
            "relation_identifier": "umls_relation_identifier",
            "rui": "umls_relation_identifier",
            "semantic_type_identifier": "umls_semantic_type_identifier",
            "system_code": "umls_code",
            "tui": "umls_semantic_type_identifier",
            "umls_identifier": "umls_identifier",
            "umls_label": "umls_label",
        }.get(match_type)
        if source_from_match and source_from_match not in sources:
            sources.insert(0, source_from_match)
        if not sources:
            sources = ["umls"]
        labels = self.labels_for_cui(cui, list(hit.get("labels") or [])) if cui else list(hit.get("labels") or [])
        definitions = list(hit.get("definitions") or (self.definitions_for_cui(cui) if cui else []))
        definition_lines = [
            f"- {item.get('source') or 'MRDEF'}: {item.get('definition') or ''}"
            for item in definitions[:3]
            if item.get("definition")
        ]
        text_lines = [
            f"CUI: {cui}" if cui else "",
            "Search scope: UMLS only",
            f"Matched input: {hit.get('matched_input') or hit.get('matched_query_span') or ''}",
        ]
        if labels:
            text_lines.append("Labels:")
            text_lines.extend(f"- {label}" for label in labels[:8])
        if definition_lines:
            text_lines.append("Definitions:")
            text_lines.extend(definition_lines)
        hit["labels"] = labels
        hit["sources"] = sources
        hit["source_bundle"] = "umls"
        hit["view"] = "umls_label" if match_type == "umls_label" else "resolver"
        hit["doc_id"] = hit.get("label_fallback_doc_id") or (f"{cui}:umls" if cui else hit.get("doc_id") or "")
        hit["evidence_count"] = 0
        hit["evidence_items"] = []
        hit["source_mix"] = source_mix_from_evidence_items([], declared_sources=sources, evidence_count=0)
        hit["text"] = "\n".join(line for line in text_lines if line)
        hit["vector_path"] = ""
        hit["vector_row"] = -1
        hit["vector_lineage"] = {}
        hit["images"] = []
        hit["evidence_related_concepts"] = []
        hit["external_embedding_neighbors"] = []
        hit["related_concepts"] = []
        hit["related_source"] = ""
        return hit

    def strip_evidence_from_umls_hits(self, hits: list[dict]) -> list[dict]:
        return [self.strip_evidence_from_umls_hit(hit) for hit in hits]

    def strip_evidence_from_umls_resolution(self, resolution: dict) -> dict:
        output = dict(resolution)
        candidates = []
        for candidate in output.get("candidates") or []:
            stripped = dict(candidate)
            stripped["has_evidence"] = False
            stripped["evidence_count"] = 0
            stripped["best_doc_id"] = ""
            stripped["best_view"] = ""
            stripped["images"] = []
            candidates.append(stripped)
        output["candidates"] = candidates
        return output

    def search_umls_scope(
        self,
        query: str,
        resolution: dict,
        *,
        top_k: int,
        started: float,
        semantic_bucket_keys: object = None,
        search_mode: object = None,
        return_code_sabs: object = None,
        debug: bool = False,
    ) -> dict:
        search_mode = normalize_search_mode(search_mode)
        semantic_bucket_keys = normalize_semantic_bucket_filter(semantic_bucket_keys)
        return_code_sabs = normalize_return_code_sabs(return_code_sabs)
        rank_top_k = self.semantic_filter_rank_limit(
            top_k,
            semantic_bucket_keys,
            search_mode=search_mode,
        )
        hits = []
        for candidate in list(resolution.get("candidates") or []):
            hit = self.hit_from_candidate(candidate)
            if hit.get("name"):
                hits.append(hit)
        hits = self.merge_label_fallback(
            query,
            hits,
            top_k=rank_top_k,
            include_extension_labels=False,
            include_active_label_supplement=False,
            include_related_anchor_candidates=False,
            strip_evidence_before_rank=True,
        )
        hits = self.filter_hits_by_search_mode(hits, search_mode=search_mode)
        hits = self.filter_hits_by_semantic_buckets(
            hits,
            semantic_bucket_keys,
            search_mode=search_mode,
        )
        score_filter_before_count = len(hits)
        hits = self.filter_hits_by_min_result_relevance(
            hits,
            query=query,
            search_mode=search_mode,
            semantic_bucket_keys=semantic_bucket_keys,
        )
        if search_scope == SEARCH_SCOPE_UMLS_EVIDENCE:
            hits = self.promote_rankable_linked_label_results(query, hits, top_k=rank_top_k)
        score_filter_metadata = self.result_score_filter_metadata(
            search_mode=search_mode,
            semantic_bucket_keys=semantic_bucket_keys,
            before_count=score_filter_before_count,
            after_count=len(hits),
        )
        hits = self.strip_evidence_from_umls_hits(hits[:top_k])
        hits = self.apply_source_code_selection(hits, sabs=return_code_sabs)
        for hit in hits:
            hit["score"] = round(float(hit.get("score") or 0.0), 6)
            if "rank_score" in hit:
                hit["rank_score"] = round(float(hit.get("rank_score") or 0.0), 6)
        return self.compact_search_response(
            {
                "query": query,
                "top_k": top_k,
                "search_mode": search_mode,
                "search_scope": "umls",
                "backend": "umls",
                "scoring": self.scoring_summary(
                    "umls",
                    search_mode=search_mode,
                    search_scope="umls",
                ),
                "semantic_bucket_filter": list(semantic_bucket_keys),
                "input_type": resolution.get("input_type") or "",
                "resolution": self.strip_evidence_from_umls_resolution(resolution),
                "hits": hits,
                "linked_concepts": [],
                "linked_concepts_enabled": False,
                **score_filter_metadata,
                **self.source_contribution_metadata(hits, include_debug=debug),
                **self.semantic_response_metadata(
                    hits,
                    include_related=False,
                    semantic_bucket_keys=semantic_bucket_keys,
                ),
                "elapsed_ms": round((time.time() - started) * 1000, 1),
            },
            include_debug=debug,
            include_evidence_items=False,
        )

    def rerank_candidate_pool_size(self, top_k: int, *, search_mode: object = None) -> int:
        top_k = max(1, int(top_k or 1))
        mode = normalize_search_mode(search_mode)
        multiplier = max(1, int(getattr(self, "candidate_pool_multiplier", 1) or 1))
        minimum = max(1, int(getattr(self, "candidate_pool_min", 40) or 40))
        if mode == "comprehensive":
            multiplier = max(multiplier, 3)
            minimum = max(minimum, 120)
        elif mode == "exact":
            minimum = max(minimum, 80)
        return max(top_k, minimum, top_k * multiplier)

    def semantic_filter_rank_limit(
        self,
        top_k: int,
        semantic_bucket_keys: object = None,
        *,
        search_mode: object = None,
    ) -> int:
        keys = normalize_semantic_bucket_filter(semantic_bucket_keys)
        mode = normalize_search_mode(search_mode)
        if mode == "comprehensive":
            return max(top_k, self.rerank_candidate_pool_size(top_k, search_mode=mode))
        if not keys:
            return top_k
        return max(top_k, self.rerank_candidate_pool_size(top_k, search_mode=mode))

    def filter_hits_by_semantic_buckets(
        self,
        hits: list[dict],
        semantic_bucket_keys: object = None,
        *,
        search_mode: object = None,
    ) -> list[dict]:
        keys = normalize_semantic_bucket_filter(semantic_bucket_keys)
        if not keys:
            return hits
        min_relevance = self.min_result_relevance(
            search_mode=search_mode,
            semantic_bucket_keys=keys,
        )
        return [
            hit
            for hit in hits
            if hit_matches_any_semantic_bucket(hit, keys, min_relevance=min_relevance)
        ]

    def min_result_relevance(
        self,
        *,
        search_mode: object = None,
        semantic_bucket_keys: object = None,
    ) -> float:
        mode = normalize_search_mode(search_mode)
        base = MIN_RESULT_RELEVANCE_BY_MODE.get(mode, MIN_RESULT_RELEVANCE_BY_MODE["balanced"])
        if normalize_semantic_bucket_filter(semantic_bucket_keys):
            return min(
                base,
                SEMANTIC_FILTER_MIN_RESULT_RELEVANCE_BY_MODE.get(
                    mode,
                    SELECTED_SEMANTIC_BUCKET_MIN_RELEVANCE,
                ),
            )
        return base

    def hit_clears_min_result_relevance(
        self,
        hit: dict,
        *,
        query: object = None,
        search_mode: object = None,
        semantic_bucket_keys: object = None,
    ) -> bool:
        if temporal_word_chemical_false_positive(hit, query=query):
            return False
        match_type = str(hit.get("match_type") or "")
        code_match_type = str(hit.get("code_match_type") or "")
        if (
            match_type in MIN_RESULT_RELEVANCE_PROTECTED_MATCH_TYPES
            or code_match_type in MIN_RESULT_RELEVANCE_PROTECTED_MATCH_TYPES
            or str(hit.get("matched_code_input") or "").strip()
            or exact_label_hit_protected_from_min_result_relevance(hit)
        ):
            return True
        return hit_relevance_score(hit) >= self.min_result_relevance(
            search_mode=search_mode,
            semantic_bucket_keys=semantic_bucket_keys,
        )

    def filter_hits_by_min_result_relevance(
        self,
        hits: list[dict],
        *,
        query: object = None,
        search_mode: object = None,
        semantic_bucket_keys: object = None,
    ) -> list[dict]:
        return [
            hit
            for hit in hits
            if self.hit_clears_min_result_relevance(
                hit,
                query=query,
                search_mode=search_mode,
                semantic_bucket_keys=semantic_bucket_keys,
            )
        ]

    def result_score_filter_metadata(
        self,
        *,
        search_mode: object = None,
        semantic_bucket_keys: object = None,
        before_count: int,
        after_count: int,
    ) -> dict:
        return {
            "result_score_filter": {
                "min_relevance": self.min_result_relevance(
                    search_mode=search_mode,
                    semantic_bucket_keys=semantic_bucket_keys,
                ),
                "removed": max(0, int(before_count) - int(after_count)),
            },
        }

    def compact_search_hit(
        self,
        hit: dict,
        *,
        include_debug: bool = False,
        include_evidence_items: bool = True,
    ) -> dict:
        compact = {
            key: value
            for key, value in hit.items()
            if key not in self.SEARCH_HIT_DETAIL_FIELDS
        }
        if compact.get("codes") and not compact.get("source_asserted_codes"):
            compact["source_asserted_codes"] = compact["codes"]
        if (
            hit.get("mappings")
            and str(hit.get("match_type") or "") in {"code", "cui", "system_code"}
        ):
            compact["mappings"] = hit["mappings"]
        if (
            include_evidence_items
            and hit.get("evidence_items")
            and str(hit.get("match_type") or "") == "umls_label"
            and int(hit.get("evidence_count") or 0) > 0
        ):
            compact["evidence_items"] = hit["evidence_items"]
        if not include_debug:
            for key in self.SEARCH_HIT_DEBUG_FIELDS:
                compact.pop(key, None)
        compact["details_lazy"] = True
        return compact

    def compact_search_response(
        self,
        result: dict,
        *,
        include_debug: bool = False,
        include_evidence_items: bool = True,
    ) -> dict:
        output = dict(result)
        output["hits"] = [
            self.compact_search_hit(
                hit,
                include_debug=include_debug,
                include_evidence_items=include_evidence_items,
            )
            for hit in result.get("hits") or []
        ]
        if "linked_concepts" in result:
            output["linked_concepts"] = [
                self.compact_search_hit(
                    hit,
                    include_debug=include_debug,
                    include_evidence_items=include_evidence_items,
                )
                for hit in result.get("linked_concepts") or []
            ]
        output["details_lazy"] = True
        return output

    def source_contribution_metadata(self, hits: list[dict], *, include_debug: bool = False) -> dict:
        def summarize(bucket: dict[str, dict]) -> list[dict]:
            rows = []
            for key, value in bucket.items():
                best = value["best_hit"]
                rows.append(
                    {
                        value["field"]: key,
                        "hits": value["hits"],
                        "unique_cuis": len(value["cuis"]),
                        "top_rank": value["top_rank"],
                        "max_score": round(value["max_score"], 6),
                        "best_hit": best,
                    }
                )
            return sorted(rows, key=lambda row: (row["top_rank"], -row["max_score"], row.get("source") or row.get("source_bundle") or row.get("vector_path") or ""))

        def add(bucket: dict[str, dict], *, field: str, key: str, rank: int, hit: dict) -> None:
            key = str(key or "unknown")
            score = float(hit.get("score") or 0.0)
            current = bucket.get(key)
            best_hit = {
                "rank": rank,
                "cui": str(hit.get("cui") or ""),
                "name": str(hit.get("name") or ""),
                "score": round(score, 6),
            }
            if current is None:
                bucket[key] = {
                    "field": field,
                    "hits": 1,
                    "cuis": {str(hit.get("cui") or "")},
                    "top_rank": rank,
                    "max_score": score,
                    "best_hit": best_hit,
                }
                return
            current["hits"] += 1
            current["cuis"].add(str(hit.get("cui") or ""))
            if rank < current["top_rank"]:
                current["top_rank"] = rank
            if score > current["max_score"]:
                current["max_score"] = score
                current["best_hit"] = best_hit

        source_bucket: dict[str, dict] = {}
        bundle_bucket: dict[str, dict] = {}
        vector_bucket: dict[str, dict] = {}
        for rank, hit in enumerate(hits, start=1):
            sources = [
                str(source).strip()
                for source in (hit.get("sources") or [])
                if str(source).strip()
            ] or ["unknown"]
            for source in sources:
                add(source_bucket, field="source", key=source, rank=rank, hit=hit)
            add(
                bundle_bucket,
                field="source_bundle",
                key=str(hit.get("source_bundle") or "unknown"),
                rank=rank,
                hit=hit,
            )
            if include_debug:
                add(
                    vector_bucket,
                    field="vector_path",
                    key=str(hit.get("vector_path") or "unknown"),
                    rank=rank,
                    hit=hit,
                )
        metadata = {
            "source_contributions": summarize(source_bucket),
            "source_bundle_contributions": summarize(bundle_bucket),
        }
        if include_debug:
            metadata["vector_file_contributions"] = summarize(vector_bucket)
        return metadata

    def filter_hits_by_search_mode(self, hits: list[dict], *, search_mode: object = None) -> list[dict]:
        mode = normalize_search_mode(search_mode)
        if mode != "exact":
            return hits
        return [hit for hit in hits if self.hit_has_exact_search_signal(hit)]

    def hit_has_exact_search_signal(self, hit: dict) -> bool:
        if str(hit.get("match_type") or "") in {
            "code",
            "system_code",
            "code_label_broadened",
            "system_code_label_broadened",
        }:
            return True
        if str(hit.get("code_match_type") or "") in {"code", "system_code"}:
            return True
        breakdown = hit.get("score_breakdown") or {}
        exact_keys = (
            "exact_label_component",
            "exact_primary_name_component",
            "exact_span_component",
            "exact_pharmacologic_component",
            "curated_exact_label_component",
            "local_extension_phrase_component",
        )
        if any(float(breakdown.get(key) or 0.0) > 0.0 for key in exact_keys):
            return True
        if hit.get("match_type") == "umls_label" and str(hit.get("matched_query_span") or "").strip():
            return True
        return False

    def cached_search_result(self, cache_key: tuple, *, started: float) -> dict | None:
        if int(getattr(self, "query_cache_size", 0) or 0) <= 0:
            return None
        cache = getattr(self, "query_result_cache", None)
        cache_lock = getattr(self, "query_cache_lock", None)
        if cache is None or cache_lock is None:
            return None
        with cache_lock:
            cached = cache.get(cache_key)
            if cached is None:
                self.query_cache_misses = int(getattr(self, "query_cache_misses", 0) or 0) + 1
                return None
            cache.move_to_end(cache_key)
            self.query_cache_hits = int(getattr(self, "query_cache_hits", 0) or 0) + 1
            result = deepcopy(cached)
        result["cached"] = True
        result["cache_hit"] = True
        result["uncached_elapsed_ms"] = result.get("elapsed_ms")
        result["elapsed_ms"] = round((time.time() - started) * 1000, 1)
        return result

    def store_search_result_cache(self, cache_key: tuple, result: dict) -> dict:
        max_size = int(getattr(self, "query_cache_size", 0) or 0)
        if max_size <= 0 or result.get("fallback_reason"):
            result["cached"] = False
            result["cache_hit"] = False
            return result
        cache = getattr(self, "query_result_cache", None)
        cache_lock = getattr(self, "query_cache_lock", None)
        if cache is None or cache_lock is None:
            result["cached"] = False
            result["cache_hit"] = False
            return result
        cached = deepcopy(result)
        cached.pop("cached", None)
        cached.pop("cache_hit", None)
        cached.pop("uncached_elapsed_ms", None)
        with cache_lock:
            cache[cache_key] = cached
            cache.move_to_end(cache_key)
            while len(cache) > max_size:
                cache.popitem(last=False)
        result["cached"] = False
        result["cache_hit"] = False
        return result

    def evidence_vector_neighbors_for_cui(self, cui: str, *, top_k: int = 10) -> list[dict]:
        seed_records = self.records_by_cui.get(cui, [])
        if not seed_records:
            return []
        candidate_hits: dict[str, dict] = {}
        seed_records = sorted(
            seed_records,
            key=lambda record: (record.evidence_count, len(record.evidence_items), record.view),
            reverse=True,
        )[:4]
        if self.elastic_url and self.elastic_index:
            try:
                elastic_k = max(top_k * 4, top_k + len(seed_records))
                for seed in seed_records:
                    raw_hits = self.search_knn(
                        base_url=self.elastic_url or "",
                        index=self.elastic_index or "",
                        vector=list(seed.vector),
                        k=elastic_k,
                        num_candidates=max(self.elastic_num_candidates, elastic_k),
                        exclude_source_prefixes=getattr(self, "elastic_exclude_source_prefixes", ()),
                    )
                    for raw_hit in raw_hits:
                        source = raw_hit.get("_source", {}) or {}
                        doc_id = str(source.get("doc_id") or raw_hit.get("_id") or "")
                        record = self.records_by_doc_id.get(doc_id)
                        target_cui = str(source.get("cui") or (record.cui if record else ""))
                        if not target_cui or target_cui == cui:
                            continue
                        score = float(raw_hit.get("_score", 0.0))
                        if record:
                            hit = self.hit_from_record(
                                record,
                                score=score,
                                hydrate_details=False,
                                include_codes=False,
                            )
                        else:
                            labels = self.labels_for_cui(target_cui, list(source.get("labels") or []))
                            name = self.display_label_for_cui(target_cui, labels)
                            if not name:
                                continue
                            hit = {
                                "doc_id": doc_id,
                                "cui": target_cui,
                                "name": name,
                                "view": str(source.get("view") or ""),
                                "score": score,
                                "labels": labels,
                                "sources": list(source.get("sources") or []),
                                "evidence_count": int(source.get("evidence_count") or 0),
                                "semantic_types": self.semantic_types_for_cui(target_cui),
                                "images": [],
                                "codes": [],
                                "source_asserted_codes": [],
                                "text": str(source.get("text") or ""),
                                "evidence_items": [],
                                "related_concepts": [],
                            }
                        if not hit.get("name"):
                            continue
                        hit["seed_doc_id"] = seed.doc_id
                        current = candidate_hits.get(target_cui)
                        if current is None or score > float(current.get("score") or 0):
                            candidate_hits[target_cui] = hit
            except (OSError, URLError):
                return []
        else:
            for seed in seed_records:
                for record in self.records:
                    if record.cui == cui:
                        continue
                    score = dot(seed.vector, record.vector)
                    current = candidate_hits.get(record.cui)
                    if current is None or score > float(current.get("score") or 0):
                        hit = self.hit_from_record(
                            record,
                            score=score,
                            hydrate_details=False,
                            include_codes=False,
                        )
                        hit["seed_doc_id"] = seed.doc_id
                        candidate_hits[record.cui] = hit
        hits = sorted(candidate_hits.values(), key=lambda item: item["score"], reverse=True)[:top_k]
        for hit in hits:
            hit["score"] = round(float(hit["score"]), 6)
            hit["mappings"] = self.mappings_for_cui(str(hit.get("cui") or ""), limit=10)
            if not hit.get("codes"):
                hit.update(self.source_code_fields_for_cui(str(hit.get("cui") or "")))
            else:
                hit["source_asserted_codes"] = hit.get("source_asserted_codes") or hit["codes"]
        return hits

    def mark_elasticsearch_unavailable(self, exc: BaseException, *, cooldown_seconds: float = 30.0) -> str:
        reason = f"elasticsearch unavailable: {exc}"
        self.elastic_failure_reason = reason
        self.elastic_disabled_until = time.time() + cooldown_seconds
        return reason

    def elastic_search_is_temporarily_disabled(self) -> bool:
        return bool(
            getattr(self, "elastic_disabled_until", 0.0)
            and time.time() < float(getattr(self, "elastic_disabled_until", 0.0))
        )

    def require_elasticsearch_or_raise(self, reason: str) -> None:
        if getattr(self, "require_elasticsearch", False):
            raise SearchBackendUnavailable(f"Elasticsearch is required: {reason}")

    def local_vector_candidates(self, query_vector: array, *, candidate_pool_k: int) -> list[dict]:
        matrix = getattr(self, "vector_matrix", None)
        if matrix is not None:
            candidates = self.numpy_local_vector_candidates(
                query_vector,
                candidate_pool_k=candidate_pool_k,
            )
            if candidates:
                return candidates
        best_by_cui: dict[str, dict] = {}
        for record in self.records:
            score = dot(query_vector, record.vector)
            current = best_by_cui.get(record.cui)
            if current is None or score > current["score"]:
                best_by_cui[record.cui] = {
                    "score": score,
                    "record": record,
                }
        return sorted(best_by_cui.values(), key=lambda hit: hit["score"], reverse=True)[:candidate_pool_k]

    def numpy_local_vector_candidates(self, query_vector: array, *, candidate_pool_k: int) -> list[dict]:
        try:
            import numpy as np
        except Exception:
            return []
        matrix = getattr(self, "vector_matrix", None)
        if matrix is None or not len(self.records):
            return []
        query = np.asarray(query_vector, dtype=np.float32)
        if query.ndim != 1 or query.shape[0] != matrix.shape[1]:
            return []
        if not np.isfinite(query).all():
            query = np.nan_to_num(query, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
        with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
            scores = matrix @ query
        if not np.isfinite(scores).all():
            scores = np.nan_to_num(scores, copy=False, nan=-np.inf, posinf=-np.inf, neginf=-np.inf)
        total = int(scores.shape[0])
        if total <= 0:
            return []
        raw_k = min(total, max(candidate_pool_k * 8, candidate_pool_k + 256))
        while True:
            if raw_k >= total:
                order = np.argsort(scores)[::-1]
            else:
                unordered = np.argpartition(scores, -raw_k)[-raw_k:]
                order = unordered[np.argsort(scores[unordered])[::-1]]
            candidates = []
            seen_cuis: set[str] = set()
            for index in order:
                record = self.records[int(index)]
                if record.cui in seen_cuis:
                    continue
                seen_cuis.add(record.cui)
                candidates.append(
                    {
                        "score": float(scores[int(index)]),
                        "record": record,
                    }
                )
                if len(candidates) >= candidate_pool_k:
                    return candidates
            if raw_k >= total:
                return candidates
            raw_k = min(total, raw_k * 2)

    def search(
        self,
        query: str,
        *,
        top_k: int,
        include_related: bool = True,
        include_linked_concepts: bool = True,
        include_evidence_items: bool = True,
        semantic_bucket_keys: object = None,
        search_mode: object = None,
        search_scope: object = None,
        return_code_sabs: object = None,
        debug: bool = False,
    ) -> dict:
        started = time.time()
        search_mode = normalize_search_mode(search_mode)
        search_scope = normalize_search_scope(search_scope)
        semantic_bucket_keys = normalize_semantic_bucket_filter(semantic_bucket_keys)
        return_code_sabs = normalize_return_code_sabs(return_code_sabs)
        if search_scope == "umls":
            include_related = False
        cache_key = self.search_cache_key(
            query,
            top_k=top_k,
            include_related=include_related,
            include_linked_concepts=include_linked_concepts,
            include_evidence_items=include_evidence_items,
            semantic_bucket_keys=semantic_bucket_keys,
            search_mode=search_mode,
            search_scope=search_scope,
            return_code_sabs=return_code_sabs,
            debug=debug,
        )
        cached = self.cached_search_result(cache_key, started=started)
        if cached is not None:
            return cached
        if is_blocked_generic_query(query):
            result = {
                "query": query,
                "top_k": top_k,
                "search_mode": search_mode,
                "search_scope": search_scope,
                "backend": "generic_query_filter",
                "scoring": self.scoring_summary(
                    "generic_query_filter",
                    search_mode=search_mode,
                    search_scope=search_scope,
                ),
                "semantic_bucket_filter": list(semantic_bucket_keys),
                "hits": [],
                **self.source_contribution_metadata([], include_debug=debug),
                **self.semantic_response_metadata(
                    [],
                    include_related=include_related,
                    semantic_bucket_keys=semantic_bucket_keys,
                ),
                "elapsed_ms": round((time.time() - started) * 1000, 1),
            }
            return self.store_search_result_cache(cache_key, result)
        resolution = self.resolve(query, limit=max(top_k * 2, 10))
        if search_scope == "umls":
            result = self.search_umls_scope(
                query,
                resolution,
                top_k=top_k,
                started=started,
                semantic_bucket_keys=semantic_bucket_keys,
                search_mode=search_mode,
                return_code_sabs=return_code_sabs,
                debug=debug,
            )
            return self.store_search_result_cache(cache_key, result)
        if resolution.get("input_type") in {
            "cui",
            "system_code",
            "code",
            "umls_identifier",
            "semantic_type_identifier",
            "relation_identifier",
        } and resolution.get("candidates"):
            result = self.direct_search(
                resolution,
                top_k=top_k,
                started=started,
                include_related=include_related,
                include_evidence_items=include_evidence_items,
                semantic_bucket_keys=semantic_bucket_keys,
                search_mode=search_mode,
                search_scope=search_scope,
                return_code_sabs=return_code_sabs,
                debug=debug,
            )
            return self.store_search_result_cache(cache_key, result)
        embedded_code_resolution = (
            self.resolve_embedded_code_lookup(query, limit=max(top_k * 2, 10))
            if search_mode == "exact"
            else None
        )
        if embedded_code_resolution and embedded_code_resolution.get("candidates"):
            result = self.direct_search(
                embedded_code_resolution,
                top_k=top_k,
                started=started,
                include_related=include_related,
                include_evidence_items=include_evidence_items,
                semantic_bucket_keys=semantic_bucket_keys,
                search_mode=search_mode,
                search_scope=search_scope,
                return_code_sabs=return_code_sabs,
                debug=debug,
            )
            return self.store_search_result_cache(cache_key, result)
        long_document_chunks = plan_long_document_chunks(query)
        embed_inputs = [query, *[chunk.text for chunk in long_document_chunks]]
        embedded_vectors = self.embedder.embed(embed_inputs)
        query_vector = array("f", embedded_vectors[0])
        long_document_chunk_vectors = [
            array("f", vector) for vector in embedded_vectors[1:]
        ]
        if self.records and len(query_vector) != self.dim:
            raise ValueError(
                f"query vector dimension {len(query_vector)} does not match index dimension {self.dim}"
            )
        if self.elastic_url and self.elastic_index:
            if self.elastic_search_is_temporarily_disabled():
                self.require_elasticsearch_or_raise(
                    self.elastic_failure_reason or "temporarily disabled after a previous failure"
                )
                result = self.search_local(
                    query,
                    query_vector=query_vector,
                    top_k=top_k,
                    started=started,
                    include_related=include_related,
                    include_linked_concepts=include_linked_concepts,
                    include_evidence_items=include_evidence_items,
                    backend="local_fallback",
                    fallback_reason=self.elastic_failure_reason or "elasticsearch temporarily disabled",
                    semantic_bucket_keys=semantic_bucket_keys,
                    search_mode=search_mode,
                    search_scope=search_scope,
                    return_code_sabs=return_code_sabs,
                    debug=debug,
                    long_document_chunks=long_document_chunks,
                    long_document_chunk_vectors=long_document_chunk_vectors,
                )
                return self.store_search_result_cache(cache_key, result)
            try:
                result = self.search_elastic(
                    query,
                    query_vector=list(query_vector),
                    top_k=top_k,
                    started=started,
                    include_related=include_related,
                    include_linked_concepts=include_linked_concepts,
                    include_evidence_items=include_evidence_items,
                    semantic_bucket_keys=semantic_bucket_keys,
                    search_mode=search_mode,
                    search_scope=search_scope,
                    return_code_sabs=return_code_sabs,
                    debug=debug,
                    long_document_chunks=long_document_chunks,
                    long_document_chunk_vectors=long_document_chunk_vectors,
                )
                self.elastic_disabled_until = 0.0
                self.elastic_failure_reason = ""
                return self.store_search_result_cache(cache_key, result)
            except (OSError, URLError) as exc:
                fallback_reason = self.mark_elasticsearch_unavailable(exc)
                self.require_elasticsearch_or_raise(fallback_reason)
                result = self.search_local(
                    query,
                    query_vector=query_vector,
                    top_k=top_k,
                    started=started,
                    include_related=include_related,
                    include_linked_concepts=include_linked_concepts,
                    include_evidence_items=include_evidence_items,
                    backend="local_fallback",
                    fallback_reason=fallback_reason,
                    semantic_bucket_keys=semantic_bucket_keys,
                    search_mode=search_mode,
                    search_scope=search_scope,
                    return_code_sabs=return_code_sabs,
                    debug=debug,
                    long_document_chunks=long_document_chunks,
                    long_document_chunk_vectors=long_document_chunk_vectors,
                )
                return self.store_search_result_cache(cache_key, result)
        self.require_elasticsearch_or_raise("missing --elastic-url or --elastic-index")
        result = self.search_local(
            query,
            query_vector=query_vector,
            top_k=top_k,
            started=started,
            include_related=include_related,
            include_linked_concepts=include_linked_concepts,
            include_evidence_items=include_evidence_items,
            semantic_bucket_keys=semantic_bucket_keys,
            search_mode=search_mode,
            search_scope=search_scope,
            return_code_sabs=return_code_sabs,
            debug=debug,
            long_document_chunks=long_document_chunks,
            long_document_chunk_vectors=long_document_chunk_vectors,
        )
        return self.store_search_result_cache(cache_key, result)

    def long_document_local_vector_hits(
        self,
        *,
        chunks: list[LongDocumentChunk],
        chunk_vectors: list[array],
        candidate_pool_k: int,
    ) -> list[dict]:
        if not chunks or not chunk_vectors:
            return []
        limit = max(8, min(candidate_pool_k, 24))
        hits: list[dict] = []
        for chunk, vector in zip(chunks, chunk_vectors):
            for candidate_rank, item in enumerate(
                self.local_vector_candidates(vector, candidate_pool_k=limit),
                start=1,
            ):
                hit = self.hit_from_record(
                    item["record"],
                    score=float(item["score"]),
                    hydrate_details=False,
                    include_codes=False,
                )
                if not hit.get("name"):
                    continue
                hit["retrieval"] = {
                    "kind": "long_document_local_chunk_vector",
                    "candidate_rank": candidate_rank,
                    "chunk_index": chunk.index,
                    "section": chunk.section,
                    "vector_backend": getattr(self, "vector_matrix_backend", "python"),
                }
                self.add_long_document_support(
                    hit,
                    source="chunk_vector",
                    section=chunk.section,
                    chunk_index=chunk.index,
                    score=float(item["score"]),
                    candidate_rank=candidate_rank,
                    section_weight=chunk.weight,
                    matched_text=chunk.text,
                )
                hits.append(hit)
        return hits

    def long_document_elastic_vector_hits(
        self,
        *,
        chunks: list[LongDocumentChunk],
        chunk_vectors: list[array],
        candidate_pool_k: int,
    ) -> list[dict]:
        if not chunks or not chunk_vectors or not self.elastic_url or not self.elastic_index:
            return []
        limit = max(8, min(candidate_pool_k, 24))
        hits: list[dict] = []
        for chunk, vector in zip(chunks, chunk_vectors):
            raw_hits = self.search_knn(
                base_url=self.elastic_url or "",
                index=self.elastic_index or "",
                vector=list(vector),
                k=limit,
                num_candidates=max(self.elastic_num_candidates, limit),
                exclude_source_prefixes=getattr(self, "elastic_exclude_source_prefixes", ()),
            )
            for candidate_rank, raw_hit in enumerate(raw_hits, start=1):
                source = raw_hit.get("_source", {}) or {}
                doc_id = str(source.get("doc_id") or raw_hit.get("_id") or "")
                record = self.records_by_doc_id.get(doc_id)
                if record is None:
                    continue
                cui = str(source.get("cui") or record.cui)
                if not cui:
                    continue
                semantic_types = self.semantic_types_for_cui(cui)
                labels = self.labels_for_cui(
                    cui,
                    list(source.get("labels") or record.labels),
                )
                name = self.display_label_for_cui(cui, labels)
                if not name:
                    continue
                hit = {
                    "doc_id": doc_id,
                    "cui": cui,
                    "name": name,
                    "view": str(source.get("view") or record.view),
                    "score": float(raw_hit.get("_score", 0.0)),
                    "labels": labels,
                    "sources": list(source.get("sources") or record.sources),
                    "evidence_count": int(source.get("evidence_count") or record.evidence_count),
                    "source_bundle": record.source_bundle,
                    "vector_path": record.vector_path,
                    "vector_row": record.vector_row,
                    "vector_lineage": {
                        "vector_path": record.vector_path,
                        "vector_row": record.vector_row,
                        "source_bundle": record.source_bundle,
                        "doc_id": record.doc_id,
                        "cui": record.cui,
                        "view": record.view,
                    },
                    "retrieval": {
                        "kind": "long_document_elasticsearch_chunk_vector",
                        "elastic_index": self.elastic_index or "",
                        "candidate_rank": candidate_rank,
                        "chunk_index": chunk.index,
                        "section": chunk.section,
                    },
                    "source_mix": source_mix_from_evidence_items(
                        list(record.evidence_items),
                        declared_sources=list(source.get("sources") or record.sources),
                        evidence_count=int(source.get("evidence_count") or record.evidence_count),
                    ),
                    "semantic_types": semantic_types,
                    **semantic_group_metadata(semantic_types),
                    "definitions": [],
                    "images": [],
                    "codes": [],
                    "source_asserted_codes": [],
                    "text": record.text,
                    "evidence_items": [dict(item) for item in record.evidence_items],
                    "related_concepts": [],
                }
                self.add_long_document_support(
                    hit,
                    source="chunk_vector",
                    section=chunk.section,
                    chunk_index=chunk.index,
                    score=float(raw_hit.get("_score", 0.0)),
                    candidate_rank=candidate_rank,
                    section_weight=chunk.weight,
                    matched_text=chunk.text,
                )
                hits.append(hit)
        return hits

    def search_local(
        self,
        query: str,
        *,
        query_vector: array,
        top_k: int,
        started: float,
        include_related: bool = True,
        include_linked_concepts: bool = True,
        include_evidence_items: bool = True,
        backend: str = "local",
        fallback_reason: str = "",
        semantic_bucket_keys: object = None,
        search_mode: object = None,
        search_scope: object = None,
        return_code_sabs: object = None,
        debug: bool = False,
        long_document_chunks: list[LongDocumentChunk] | None = None,
        long_document_chunk_vectors: list[array] | None = None,
    ) -> dict:
        search_mode = normalize_search_mode(search_mode)
        search_scope = normalize_search_scope(search_scope)
        rank_top_k = self.semantic_filter_rank_limit(top_k, semantic_bucket_keys, search_mode=search_mode)
        candidate_pool_k = self.rerank_candidate_pool_size(rank_top_k, search_mode=search_mode)
        candidates = self.local_vector_candidates(query_vector, candidate_pool_k=candidate_pool_k)
        hits = []
        for candidate_rank, item in enumerate(candidates, start=1):
            hit = self.hit_from_record(
                item["record"],
                score=float(item["score"]),
                hydrate_details=False,
                include_codes=False,
            )
            if not hit.get("name"):
                continue
            hit["retrieval"] = {
                "kind": "local_vector",
                "candidate_rank": candidate_rank,
                "vector_backend": getattr(self, "vector_matrix_backend", "python"),
            }
            hits.append(hit)
        hits = self.merge_label_fallback(query, hits, top_k=rank_top_k)
        hits = self.merge_long_document_candidates(
            query,
            hits,
            chunks=list(long_document_chunks or []),
            chunk_hits=self.long_document_local_vector_hits(
                chunks=list(long_document_chunks or []),
                chunk_vectors=list(long_document_chunk_vectors or []),
                candidate_pool_k=candidate_pool_k,
            ),
            top_k=rank_top_k,
        )
        hits = self.filter_hits_by_search_mode(hits, search_mode=search_mode)
        hits = self.filter_hits_by_semantic_buckets(
            hits,
            semantic_bucket_keys,
            search_mode=search_mode,
        )
        score_filter_before_count = len(hits)
        hits = self.filter_hits_by_min_result_relevance(
            hits,
            query=query,
            search_mode=search_mode,
            semantic_bucket_keys=semantic_bucket_keys,
        )
        if search_scope == SEARCH_SCOPE_UMLS_EVIDENCE:
            hits = self.promote_rankable_linked_label_results(query, hits, top_k=rank_top_k)
        score_filter_metadata = self.result_score_filter_metadata(
            search_mode=search_mode,
            semantic_bucket_keys=semantic_bucket_keys,
            before_count=score_filter_before_count,
            after_count=len(hits),
        )
        hits = hits[:top_k]
        if include_related:
            self.attach_related_concepts(hits)
        hits = self.apply_source_code_selection(hits, sabs=return_code_sabs)
        for hit in hits:
            hit["score"] = round(float(hit["score"]), 6)
        mentions = (
            self.query_entity_mentions(
                query,
                limit=max(top_k * 6, 120),
                return_code_sabs=return_code_sabs,
            )
            if include_linked_concepts
            else []
        )
        result = {
            "query": query,
            "top_k": top_k,
            "search_mode": search_mode,
            "search_scope": search_scope,
            "backend": backend,
            "scoring": self.scoring_summary(
                "local",
                search_mode=search_mode,
                search_scope=search_scope,
            ),
            "semantic_bucket_filter": list(normalize_semantic_bucket_filter(semantic_bucket_keys)),
            "hits": hits,
            "linked_concepts": (
                self.query_linked_concept_hits(query, limit=max(top_k * 3, 60))
                if include_linked_concepts
                else []
            ),
            "linked_concepts_enabled": bool(include_linked_concepts),
            "mentions": mentions,
            "mentions_enabled": bool(include_linked_concepts),
            "mention_count": len(mentions),
            **self.long_document_response_metadata(long_document_chunks or []),
            **(
                {
                    "rankable_linked_label_promotions": list(
                        getattr(self, "_rankable_linked_label_promotion_cuis", [])
                    )
                }
                if debug
                else {}
            ),
            **score_filter_metadata,
            **self.source_contribution_metadata(hits, include_debug=debug),
            **self.semantic_response_metadata(
                hits,
                include_related=include_related,
                semantic_bucket_keys=semantic_bucket_keys,
            ),
            "elapsed_ms": round((time.time() - started) * 1000, 1),
        }
        if fallback_reason:
            result["fallback_reason"] = fallback_reason
            result["requested_backend"] = "elasticsearch"
        return self.compact_search_response(
            result,
            include_debug=debug,
            include_evidence_items=include_evidence_items,
        )

    def search_elastic(
        self,
        query: str,
        *,
        query_vector: list[float],
        top_k: int,
        started: float,
        include_related: bool = True,
        include_linked_concepts: bool = True,
        include_evidence_items: bool = True,
        semantic_bucket_keys: object = None,
        search_mode: object = None,
        search_scope: object = None,
        return_code_sabs: object = None,
        debug: bool = False,
        long_document_chunks: list[LongDocumentChunk] | None = None,
        long_document_chunk_vectors: list[array] | None = None,
    ) -> dict:
        search_mode = normalize_search_mode(search_mode)
        search_scope = normalize_search_scope(search_scope)
        rank_top_k = self.semantic_filter_rank_limit(top_k, semantic_bucket_keys, search_mode=search_mode)
        candidate_pool_k = self.rerank_candidate_pool_size(rank_top_k, search_mode=search_mode)
        elastic_k = candidate_pool_k
        raw_hits = self.search_knn(
            base_url=self.elastic_url or "",
            index=self.elastic_index or "",
            vector=query_vector,
            k=elastic_k,
            num_candidates=max(self.elastic_num_candidates, elastic_k),
            exclude_source_prefixes=getattr(self, "elastic_exclude_source_prefixes", ()),
        )
        best_by_cui: dict[str, dict] = {}
        for hit in raw_hits:
            source = hit.get("_source", {}) or {}
            doc_id = str(source.get("doc_id") or hit.get("_id") or "")
            record = self.records_by_doc_id.get(doc_id)
            if record is None:
                continue
            cui = str(source.get("cui") or (record.cui if record else ""))
            if not cui:
                continue
            semantic_types = self.semantic_types_for_cui(cui)
            labels = self.labels_for_cui(
                cui,
                list(source.get("labels") or (record.labels if record else [])),
            )
            name = self.display_label_for_cui(cui, labels)
            if not name:
                continue
            result = {
                "doc_id": doc_id,
                "cui": cui,
                "name": name,
                "view": str(source.get("view") or (record.view if record else "")),
                "score": float(hit.get("_score", 0.0)),
                "labels": labels,
                "sources": list(source.get("sources") or (record.sources if record else [])),
                "evidence_count": int(
                    source.get("evidence_count") or (record.evidence_count if record else 0)
                ),
                "source_bundle": record.source_bundle if record else "",
                "vector_path": record.vector_path if record else "",
                "vector_row": record.vector_row if record else -1,
                "vector_lineage": (
                    {
                        "vector_path": record.vector_path,
                        "vector_row": record.vector_row,
                        "source_bundle": record.source_bundle,
                        "doc_id": record.doc_id,
                        "cui": record.cui,
                        "view": record.view,
                    }
                    if record
                    else {}
                ),
                "retrieval": {
                    "kind": "elasticsearch_knn",
                    "elastic_index": self.elastic_index or "",
                },
                "source_mix": source_mix_from_evidence_items(
                    list(record.evidence_items) if record else [],
                    declared_sources=list(source.get("sources") or (record.sources if record else [])),
                    evidence_count=int(source.get("evidence_count") or (record.evidence_count if record else 0)),
                ),
                "semantic_types": semantic_types,
                **semantic_group_metadata(semantic_types),
                "definitions": [],
                "images": [],
                "codes": [],
                "source_asserted_codes": [],
                "text": record.text if record else str(source.get("text") or ""),
                "evidence_items": [dict(item) for item in record.evidence_items] if record else [],
            }
            current = best_by_cui.get(cui)
            if current is None or result["score"] > current["score"]:
                best_by_cui[cui] = result
        hits = sorted(best_by_cui.values(), key=lambda item: item["score"], reverse=True)[:candidate_pool_k]
        hits = self.merge_label_fallback(query, hits, top_k=rank_top_k)
        hits = self.merge_long_document_candidates(
            query,
            hits,
            chunks=list(long_document_chunks or []),
            chunk_hits=self.long_document_elastic_vector_hits(
                chunks=list(long_document_chunks or []),
                chunk_vectors=list(long_document_chunk_vectors or []),
                candidate_pool_k=candidate_pool_k,
            ),
            top_k=rank_top_k,
        )
        hits = self.filter_hits_by_search_mode(hits, search_mode=search_mode)
        hits = self.filter_hits_by_semantic_buckets(
            hits,
            semantic_bucket_keys,
            search_mode=search_mode,
        )
        score_filter_before_count = len(hits)
        hits = self.filter_hits_by_min_result_relevance(
            hits,
            query=query,
            search_mode=search_mode,
            semantic_bucket_keys=semantic_bucket_keys,
        )
        if search_scope == SEARCH_SCOPE_UMLS_EVIDENCE:
            hits = self.promote_rankable_linked_label_results(query, hits, top_k=rank_top_k)
        score_filter_metadata = self.result_score_filter_metadata(
            search_mode=search_mode,
            semantic_bucket_keys=semantic_bucket_keys,
            before_count=score_filter_before_count,
            after_count=len(hits),
        )
        hits = hits[:top_k]
        if include_related:
            self.attach_related_concepts(hits)
        hits = self.apply_source_code_selection(hits, sabs=return_code_sabs)
        for hit in hits:
            hit["score"] = round(float(hit["score"]), 6)
        mentions = (
            self.query_entity_mentions(
                query,
                limit=max(top_k * 6, 120),
                return_code_sabs=return_code_sabs,
            )
            if include_linked_concepts
            else []
        )
        return self.compact_search_response({
            "query": query,
            "top_k": top_k,
            "search_mode": search_mode,
            "search_scope": search_scope,
            "backend": "elasticsearch",
            "scoring": self.scoring_summary(
                "elasticsearch",
                search_mode=search_mode,
                search_scope=search_scope,
            ),
            "semantic_bucket_filter": list(normalize_semantic_bucket_filter(semantic_bucket_keys)),
            "hits": hits,
            "linked_concepts": (
                self.query_linked_concept_hits(query, limit=max(top_k * 3, 60))
                if include_linked_concepts
                else []
            ),
            "linked_concepts_enabled": bool(include_linked_concepts),
            "mentions": mentions,
            "mentions_enabled": bool(include_linked_concepts),
            "mention_count": len(mentions),
            **self.long_document_response_metadata(long_document_chunks or []),
            **(
                {
                    "rankable_linked_label_promotions": list(
                        getattr(self, "_rankable_linked_label_promotion_cuis", [])
                    )
                }
                if debug
                else {}
            ),
            **score_filter_metadata,
            **self.source_contribution_metadata(hits, include_debug=debug),
            **self.semantic_response_metadata(
                hits,
                include_related=include_related,
                semantic_bucket_keys=semantic_bucket_keys,
            ),
            "elapsed_ms": round((time.time() - started) * 1000, 1),
        }, include_debug=debug, include_evidence_items=include_evidence_items)
