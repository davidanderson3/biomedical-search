from __future__ import annotations

import time
from array import array
from copy import deepcopy
from urllib.error import URLError

from qe_evidence_vectors.search_semantics import semantic_group_metadata
from qe_evidence_vectors.search_semantic_buckets import (
    hit_matches_any_semantic_bucket,
    normalize_semantic_bucket_filter,
)
from qe_evidence_vectors.search_utils import (
    concept_display_name,
    dot,
    source_mix_from_evidence_items,
)


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

    def search_cache_key(
        self,
        query: str,
        *,
        top_k: int,
        include_related: bool,
        semantic_bucket_keys: object = None,
    ) -> tuple:
        return (
            "search",
            str(query or "").strip(),
            int(top_k),
            bool(include_related),
            tuple(normalize_semantic_bucket_filter(semantic_bucket_keys)),
            int(getattr(self, "related_limit", 0) or 0),
            int(getattr(self, "related_source_limit", 0) or 0),
            int(getattr(self, "expensive_related_source_limit", 0) or 0),
            int(getattr(self, "candidate_pool_multiplier", 0) or 0),
            int(getattr(self, "candidate_pool_min", 0) or 0),
            str(getattr(self, "elastic_url", "") or ""),
            str(getattr(self, "elastic_index", "") or ""),
        )

    def rerank_candidate_pool_size(self, top_k: int) -> int:
        top_k = max(1, int(top_k or 1))
        multiplier = max(1, int(getattr(self, "candidate_pool_multiplier", 1) or 1))
        minimum = max(1, int(getattr(self, "candidate_pool_min", 40) or 40))
        return max(top_k, minimum, top_k * multiplier)

    def semantic_filter_rank_limit(self, top_k: int, semantic_bucket_keys: object = None) -> int:
        keys = normalize_semantic_bucket_filter(semantic_bucket_keys)
        if not keys:
            return top_k
        return max(top_k, self.rerank_candidate_pool_size(top_k))

    def filter_hits_by_semantic_buckets(
        self,
        hits: list[dict],
        semantic_bucket_keys: object = None,
    ) -> list[dict]:
        keys = normalize_semantic_bucket_filter(semantic_bucket_keys)
        if not keys:
            return hits
        return [
            hit
            for hit in hits
            if hit_matches_any_semantic_bucket(hit, keys)
        ]

    def compact_search_hit(self, hit: dict) -> dict:
        compact = {
            key: value
            for key, value in hit.items()
            if key not in self.SEARCH_HIT_DETAIL_FIELDS
        }
        compact["details_lazy"] = True
        return compact

    def compact_search_response(self, result: dict) -> dict:
        output = dict(result)
        output["hits"] = [self.compact_search_hit(hit) for hit in result.get("hits") or []]
        output["details_lazy"] = True
        return output

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
                    )
                    for raw_hit in raw_hits:
                        source = raw_hit.get("_source", {}) or {}
                        doc_id = str(source.get("doc_id") or raw_hit.get("_id") or "")
                        record = self.records_by_doc_id.get(doc_id)
                        target_cui = str(source.get("cui") or (record.cui if record else ""))
                        if not target_cui or target_cui == cui:
                            continue
                        score = float(raw_hit.get("_score", 0.0))
                        hit = self.hit_from_record(record, score=score) if record else {
                            "doc_id": doc_id,
                            "cui": target_cui,
                            "name": self.preferred_label_for_cui(target_cui) or concept_display_name(
                                self.labels_for_cui(target_cui, list(source.get("labels") or [])),
                                fallback=target_cui,
                            ),
                            "view": str(source.get("view") or ""),
                            "score": score,
                            "labels": self.labels_for_cui(target_cui, list(source.get("labels") or [])),
                            "sources": list(source.get("sources") or []),
                            "evidence_count": int(source.get("evidence_count") or 0),
                            "semantic_types": self.semantic_types_for_cui(target_cui),
                            "images": self.images_for_cui(target_cui),
                            "text": str(source.get("text") or ""),
                            "evidence_items": [],
                            "related_concepts": [],
                        }
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
                        hit = self.hit_from_record(record, score=score)
                        hit["seed_doc_id"] = seed.doc_id
                        candidate_hits[record.cui] = hit
        hits = sorted(candidate_hits.values(), key=lambda item: item["score"], reverse=True)[:top_k]
        for hit in hits:
            hit["score"] = round(float(hit["score"]), 6)
            hit["mappings"] = self.mappings_for_cui(str(hit.get("cui") or ""), limit=10)
        return hits

    def search(
        self,
        query: str,
        *,
        top_k: int,
        include_related: bool = True,
        semantic_bucket_keys: object = None,
    ) -> dict:
        started = time.time()
        semantic_bucket_keys = normalize_semantic_bucket_filter(semantic_bucket_keys)
        cache_key = self.search_cache_key(
            query,
            top_k=top_k,
            include_related=include_related,
            semantic_bucket_keys=semantic_bucket_keys,
        )
        cached = self.cached_search_result(cache_key, started=started)
        if cached is not None:
            return cached
        resolution = self.resolve(query, limit=max(top_k * 2, 10))
        if resolution.get("input_type") in {"cui", "system_code", "code"} and resolution.get("candidates"):
            result = self.direct_search(
                resolution,
                top_k=top_k,
                started=started,
                include_related=include_related,
                semantic_bucket_keys=semantic_bucket_keys,
            )
            return self.store_search_result_cache(cache_key, result)
        query_vector = array("f", self.embedder.embed([query])[0])
        if self.records and len(query_vector) != self.dim:
            raise ValueError(
                f"query vector dimension {len(query_vector)} does not match index dimension {self.dim}"
            )
        if self.elastic_url and self.elastic_index:
            try:
                result = self.search_elastic(
                    query,
                    query_vector=list(query_vector),
                    top_k=top_k,
                    started=started,
                    include_related=include_related,
                    semantic_bucket_keys=semantic_bucket_keys,
                )
                return self.store_search_result_cache(cache_key, result)
            except (OSError, URLError) as exc:
                result = self.search_local(
                    query,
                    query_vector=query_vector,
                    top_k=top_k,
                    started=started,
                    include_related=include_related,
                    backend="local_fallback",
                    fallback_reason=f"elasticsearch unavailable: {exc}",
                    semantic_bucket_keys=semantic_bucket_keys,
                )
                return self.store_search_result_cache(cache_key, result)
        result = self.search_local(
            query,
            query_vector=query_vector,
            top_k=top_k,
            started=started,
            include_related=include_related,
            semantic_bucket_keys=semantic_bucket_keys,
        )
        return self.store_search_result_cache(cache_key, result)

    def search_local(
        self,
        query: str,
        *,
        query_vector: array,
        top_k: int,
        started: float,
        include_related: bool = True,
        backend: str = "local",
        fallback_reason: str = "",
        semantic_bucket_keys: object = None,
    ) -> dict:
        best_by_cui: dict[str, dict] = {}
        for record in self.records:
            score = dot(query_vector, record.vector)
            current = best_by_cui.get(record.cui)
            if current is None or score > current["score"]:
                best_by_cui[record.cui] = {
                    "score": score,
                    "record": record,
                }
        rank_top_k = self.semantic_filter_rank_limit(top_k, semantic_bucket_keys)
        candidate_pool_k = self.rerank_candidate_pool_size(rank_top_k)
        hits = [
            self.hit_from_record(item["record"], score=float(item["score"]))
            for item in sorted(best_by_cui.values(), key=lambda hit: hit["score"], reverse=True)[:candidate_pool_k]
        ]
        hits = self.merge_label_fallback(query, hits, top_k=rank_top_k)
        hits = self.filter_hits_by_semantic_buckets(hits, semantic_bucket_keys)[:top_k]
        if include_related:
            self.attach_related_concepts(hits)
        for hit in hits:
            hit["score"] = round(float(hit["score"]), 6)
        result = {
            "query": query,
            "top_k": top_k,
            "backend": backend,
            "scoring": self.scoring_summary("local"),
            "semantic_bucket_filter": list(normalize_semantic_bucket_filter(semantic_bucket_keys)),
            "hits": hits,
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
        return self.compact_search_response(result)

    def search_elastic(
        self,
        query: str,
        *,
        query_vector: list[float],
        top_k: int,
        started: float,
        include_related: bool = True,
        semantic_bucket_keys: object = None,
    ) -> dict:
        rank_top_k = self.semantic_filter_rank_limit(top_k, semantic_bucket_keys)
        candidate_pool_k = self.rerank_candidate_pool_size(rank_top_k)
        elastic_k = candidate_pool_k
        raw_hits = self.search_knn(
            base_url=self.elastic_url or "",
            index=self.elastic_index or "",
            vector=query_vector,
            k=elastic_k,
            num_candidates=max(self.elastic_num_candidates, elastic_k),
        )
        best_by_cui: dict[str, dict] = {}
        for hit in raw_hits:
            source = hit.get("_source", {}) or {}
            doc_id = str(source.get("doc_id") or hit.get("_id") or "")
            record = self.records_by_doc_id.get(doc_id)
            cui = str(source.get("cui") or (record.cui if record else ""))
            if not cui:
                continue
            semantic_types = self.semantic_types_for_cui(cui)
            result = {
                "doc_id": doc_id,
                "cui": cui,
                "name": self.preferred_label_for_cui(cui) or concept_display_name(
                    self.labels_for_cui(cui, list(source.get("labels") or (record.labels if record else []))),
                    fallback=cui,
                ),
                "view": str(source.get("view") or (record.view if record else "")),
                "score": float(hit.get("_score", 0.0)),
                "labels": self.labels_for_cui(
                    cui,
                    list(source.get("labels") or (record.labels if record else [])),
                ),
                "sources": list(source.get("sources") or (record.sources if record else [])),
                "evidence_count": int(
                    source.get("evidence_count") or (record.evidence_count if record else 0)
                ),
                "source_mix": source_mix_from_evidence_items(
                    self.evidence_items_for_record(record) if record else [],
                    declared_sources=list(source.get("sources") or (record.sources if record else [])),
                    evidence_count=int(source.get("evidence_count") or (record.evidence_count if record else 0)),
                ),
                "semantic_types": semantic_types,
                **semantic_group_metadata(semantic_types),
                "definitions": self.definitions_for_cui(cui),
                "images": self.images_for_cui(cui),
                "text": record.text if record else str(source.get("text") or ""),
                "evidence_items": self.evidence_items_for_record(record) if record else [],
            }
            current = best_by_cui.get(cui)
            if current is None or result["score"] > current["score"]:
                best_by_cui[cui] = result
        hits = sorted(best_by_cui.values(), key=lambda item: item["score"], reverse=True)[:candidate_pool_k]
        hits = self.merge_label_fallback(query, hits, top_k=rank_top_k)
        hits = self.filter_hits_by_semantic_buckets(hits, semantic_bucket_keys)[:top_k]
        if include_related:
            self.attach_related_concepts(hits)
        for hit in hits:
            hit["score"] = round(float(hit["score"]), 6)
        return self.compact_search_response({
            "query": query,
            "top_k": top_k,
            "backend": "elasticsearch",
            "scoring": self.scoring_summary("elasticsearch"),
            "semantic_bucket_filter": list(normalize_semantic_bucket_filter(semantic_bucket_keys)),
            "hits": hits,
            **self.semantic_response_metadata(
                hits,
                include_related=include_related,
                semantic_bucket_keys=semantic_bucket_keys,
            ),
            "elapsed_ms": round((time.time() - started) * 1000, 1),
        })
