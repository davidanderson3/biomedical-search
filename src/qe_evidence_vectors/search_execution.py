from __future__ import annotations

import time
from array import array
from copy import deepcopy
from urllib.error import URLError

from qe_evidence_vectors.generic_filters import is_blocked_generic_query
from qe_evidence_vectors.search_semantics import semantic_group_metadata
from qe_evidence_vectors.search_semantic_buckets import (
    hit_matches_any_semantic_bucket,
    normalize_semantic_bucket_filter,
)
from qe_evidence_vectors.search_utils import (
    dot,
    source_mix_from_evidence_items,
)

VALID_SEARCH_MODES = {"balanced", "exact", "comprehensive"}


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
        semantic_bucket_keys: object = None,
        search_mode: object = None,
        debug: bool = False,
    ) -> tuple:
        mode = normalize_search_mode(search_mode)
        return (
            "search",
            str(query or "").strip(),
            int(top_k),
            bool(include_related),
            bool(debug),
            mode,
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
    ) -> list[dict]:
        keys = normalize_semantic_bucket_filter(semantic_bucket_keys)
        if not keys:
            return hits
        return [
            hit
            for hit in hits
            if hit_matches_any_semantic_bucket(hit, keys)
        ]

    def compact_search_hit(self, hit: dict, *, include_debug: bool = False) -> dict:
        compact = {
            key: value
            for key, value in hit.items()
            if key not in self.SEARCH_HIT_DETAIL_FIELDS
        }
        if (
            hit.get("mappings")
            and str(hit.get("match_type") or "") in {"code", "cui", "system_code"}
        ):
            compact["mappings"] = hit["mappings"]
        if (
            hit.get("evidence_items")
            and str(hit.get("match_type") or "") == "umls_label"
            and int(hit.get("evidence_count") or 0) > 0
        ):
            compact["evidence_items"] = hit["evidence_items"]
        if not include_debug:
            for key in self.SEARCH_HIT_DEBUG_FIELDS:
                compact.pop(key, None)
        compact["details_lazy"] = True
        return compact

    def compact_search_response(self, result: dict, *, include_debug: bool = False) -> dict:
        output = dict(result)
        output["hits"] = [
            self.compact_search_hit(hit, include_debug=include_debug)
            for hit in result.get("hits") or []
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
                            hit = self.hit_from_record(record, score=score)
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
                                "images": self.images_for_cui(target_cui),
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
                        hit = self.hit_from_record(record, score=score)
                        hit["seed_doc_id"] = seed.doc_id
                        candidate_hits[record.cui] = hit
        hits = sorted(candidate_hits.values(), key=lambda item: item["score"], reverse=True)[:top_k]
        for hit in hits:
            hit["score"] = round(float(hit["score"]), 6)
            hit["mappings"] = self.mappings_for_cui(str(hit.get("cui") or ""), limit=10)
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
        semantic_bucket_keys: object = None,
        search_mode: object = None,
        debug: bool = False,
    ) -> dict:
        started = time.time()
        search_mode = normalize_search_mode(search_mode)
        semantic_bucket_keys = normalize_semantic_bucket_filter(semantic_bucket_keys)
        cache_key = self.search_cache_key(
            query,
            top_k=top_k,
            include_related=include_related,
            semantic_bucket_keys=semantic_bucket_keys,
            search_mode=search_mode,
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
                "backend": "generic_query_filter",
                "scoring": self.scoring_summary("generic_query_filter", search_mode=search_mode),
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
        if resolution.get("input_type") in {"cui", "system_code", "code"} and resolution.get("candidates"):
            result = self.direct_search(
                resolution,
                top_k=top_k,
                started=started,
                include_related=include_related,
                semantic_bucket_keys=semantic_bucket_keys,
                search_mode=search_mode,
                debug=debug,
            )
            return self.store_search_result_cache(cache_key, result)
        query_vector = array("f", self.embedder.embed([query])[0])
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
                    backend="local_fallback",
                    fallback_reason=self.elastic_failure_reason or "elasticsearch temporarily disabled",
                    semantic_bucket_keys=semantic_bucket_keys,
                    search_mode=search_mode,
                    debug=debug,
                )
                return self.store_search_result_cache(cache_key, result)
            try:
                result = self.search_elastic(
                    query,
                    query_vector=list(query_vector),
                    top_k=top_k,
                    started=started,
                    include_related=include_related,
                    semantic_bucket_keys=semantic_bucket_keys,
                    search_mode=search_mode,
                    debug=debug,
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
                    backend="local_fallback",
                    fallback_reason=fallback_reason,
                    semantic_bucket_keys=semantic_bucket_keys,
                    search_mode=search_mode,
                    debug=debug,
                )
                return self.store_search_result_cache(cache_key, result)
        self.require_elasticsearch_or_raise("missing --elastic-url or --elastic-index")
        result = self.search_local(
            query,
            query_vector=query_vector,
            top_k=top_k,
            started=started,
            include_related=include_related,
            semantic_bucket_keys=semantic_bucket_keys,
            search_mode=search_mode,
            debug=debug,
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
        search_mode: object = None,
        debug: bool = False,
    ) -> dict:
        search_mode = normalize_search_mode(search_mode)
        rank_top_k = self.semantic_filter_rank_limit(top_k, semantic_bucket_keys, search_mode=search_mode)
        candidate_pool_k = self.rerank_candidate_pool_size(rank_top_k, search_mode=search_mode)
        candidates = self.local_vector_candidates(query_vector, candidate_pool_k=candidate_pool_k)
        hits = []
        for candidate_rank, item in enumerate(candidates, start=1):
            hit = self.hit_from_record(
                item["record"],
                score=float(item["score"]),
                hydrate_details=False,
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
        hits = self.filter_hits_by_search_mode(hits, search_mode=search_mode)
        hits = self.filter_hits_by_semantic_buckets(hits, semantic_bucket_keys)[:top_k]
        if include_related:
            self.attach_related_concepts(hits)
        for hit in hits:
            hit["score"] = round(float(hit["score"]), 6)
        result = {
            "query": query,
            "top_k": top_k,
            "search_mode": search_mode,
            "backend": backend,
            "scoring": self.scoring_summary("local", search_mode=search_mode),
            "semantic_bucket_filter": list(normalize_semantic_bucket_filter(semantic_bucket_keys)),
            "hits": hits,
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
        return self.compact_search_response(result, include_debug=debug)

    def search_elastic(
        self,
        query: str,
        *,
        query_vector: list[float],
        top_k: int,
        started: float,
        include_related: bool = True,
        semantic_bucket_keys: object = None,
        search_mode: object = None,
        debug: bool = False,
    ) -> dict:
        search_mode = normalize_search_mode(search_mode)
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
                "text": record.text if record else str(source.get("text") or ""),
                "evidence_items": [dict(item) for item in record.evidence_items] if record else [],
            }
            current = best_by_cui.get(cui)
            if current is None or result["score"] > current["score"]:
                best_by_cui[cui] = result
        hits = sorted(best_by_cui.values(), key=lambda item: item["score"], reverse=True)[:candidate_pool_k]
        hits = self.merge_label_fallback(query, hits, top_k=rank_top_k)
        hits = self.filter_hits_by_search_mode(hits, search_mode=search_mode)
        hits = self.filter_hits_by_semantic_buckets(hits, semantic_bucket_keys)[:top_k]
        if include_related:
            self.attach_related_concepts(hits)
        for hit in hits:
            hit["score"] = round(float(hit["score"]), 6)
        return self.compact_search_response({
            "query": query,
            "top_k": top_k,
            "search_mode": search_mode,
            "backend": "elasticsearch",
            "scoring": self.scoring_summary("elasticsearch", search_mode=search_mode),
            "semantic_bucket_filter": list(normalize_semantic_bucket_filter(semantic_bucket_keys)),
            "hits": hits,
            **self.source_contribution_metadata(hits, include_debug=debug),
            **self.semantic_response_metadata(
                hits,
                include_related=include_related,
                semantic_bucket_keys=semantic_bucket_keys,
            ),
            "elapsed_ms": round((time.time() - started) * 1000, 1),
        }, include_debug=debug)
