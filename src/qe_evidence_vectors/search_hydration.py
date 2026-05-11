from __future__ import annotations

import time

from qe_evidence_vectors.code_index import is_cui, looks_like_code, parse_system_code
from qe_evidence_vectors.search_semantic_buckets import normalize_semantic_bucket_filter
from qe_evidence_vectors.search_semantics import semantic_group_metadata
from qe_evidence_vectors.search_tokens import content_tokens
from qe_evidence_vectors.search_utils import (
    concept_display_name,
    merge_definition_lists,
    merge_labels,
    source_mix_from_evidence_items,
)


class SearchHydrationMixin:
    def hit_from_record(self, record: SearchRecord, *, score: float) -> dict:
        labels = self.labels_for_cui(record.cui, record.labels)
        name = self.preferred_label_for_cui(record.cui) or concept_display_name(labels, fallback=record.cui)
        evidence_items = self.evidence_items_for_record(record)
        semantic_types = self.semantic_types_for_cui(record.cui)
        return {
            "doc_id": record.doc_id,
            "cui": record.cui,
            "name": name,
            "view": record.view,
            "score": score,
            "labels": labels,
            "sources": record.sources,
            "evidence_count": record.evidence_count,
            "source_mix": source_mix_from_evidence_items(
                evidence_items,
                declared_sources=record.sources,
                evidence_count=record.evidence_count,
            ),
            "semantic_types": semantic_types,
            **semantic_group_metadata(semantic_types),
            "definitions": self.definitions_for_cui(record.cui),
            "images": self.images_for_cui(record.cui),
            "text": record.text,
            "evidence_items": evidence_items,
            "related_concepts": [],
        }

    def best_record_for_cui(self, cui: str) -> SearchRecord | None:
        return self.best_record_by_cui.get(cui)

    def mappings_for_cui(
        self,
        cui: str,
        *,
        sabs: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict]:
        if not self.code_index or not cui:
            return []
        return self.code_index.lookup_cui(cui, sabs=sabs, limit=limit)

    def preferred_label_for_cui(self, cui: str) -> str:
        if not self.code_index or not cui:
            return ""
        if self.is_clinical_attribute_cui(cui):
            loinc_lc_label = self.loinc_lc_label_for_cui(cui)
            if loinc_lc_label:
                return loinc_lc_label
        return self.code_index.preferred_label(cui)

    def is_clinical_attribute_cui(self, cui: str) -> bool:
        return any(
            str(item.get("name") or "").strip().lower() == "clinical attribute"
            for item in self.semantic_types_for_cui(cui)
        )

    def loinc_lc_label_for_cui(self, cui: str) -> str:
        cui = cui.strip().upper()
        if not cui or not self.code_index:
            return ""
        cached = self.loinc_lc_label_cache.get(cui)
        if cached is not None:
            return cached
        try:
            candidates = [
                dict(row)
                for row in self.code_index.connection().execute(
                    """
                    SELECT label, ispref, suppress
                    FROM code_mappings
                    WHERE cui = ? AND sab = 'LNC' AND tty = 'LC'
                    """,
                    (cui,),
                )
            ]
        except Exception:
            candidates = []
        candidates = [
            row
            for row in candidates
            if str(row.get("label") or "").strip()
            and str(row.get("suppress") or "N") == "N"
        ]
        candidates.sort(
            key=lambda row: (
                0 if str(row.get("ispref") or "") == "Y" else 1,
                str(row.get("label") or "").lower(),
            )
        )
        label = str(candidates[0].get("label") or "") if candidates else ""
        self.loinc_lc_label_cache[cui] = label
        return label

    def labels_for_cui(self, cui: str, labels: list[str]) -> list[str]:
        preferred = self.preferred_label_for_cui(cui)
        if preferred:
            return merge_labels([preferred], labels)
        return list(labels)

    def semantic_types_for_cui(self, cui: str) -> list[dict]:
        if not cui:
            return []
        supplement_rows = list(
            getattr(self, "active_label_semantic_types_by_cui", {}).get(cui.strip().upper(), [])
        )
        if self.semantic_type_index:
            rows = self.semantic_type_index.lookup(cui)
            if rows:
                if not supplement_rows:
                    return rows
                seen = {
                    (
                        str(row.get("tui") or ""),
                        str(row.get("name") or row.get("sty") or ""),
                        str(row.get("atui") or ""),
                    )
                    for row in supplement_rows
                }
                merged = list(supplement_rows)
                for row in rows:
                    key = (
                        str(row.get("tui") or ""),
                        str(row.get("name") or row.get("sty") or ""),
                        str(row.get("atui") or ""),
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    merged.append(row)
                return merged
        if supplement_rows:
            return supplement_rows
        return list(getattr(self, "extension_semantic_types_by_cui", {}).get(cui.strip().upper(), []))

    def definitions_for_cui(self, cui: str, *, limit: int = 3) -> list[dict]:
        if not self.definition_index or not cui:
            return []
        return self.definition_index.lookup(cui, limit=limit)

    def images_for_cui(self, cui: str, *, limit: int = 4) -> list[dict]:
        if not cui:
            return []
        return [
            dict(item)
            for item in getattr(self, "images_by_cui", {}).get(cui.strip().upper(), [])[:limit]
        ]

    def detail_bundle(
        self,
        *,
        doc_id: str = "",
        cui: str = "",
        include_related: bool = True,
    ) -> dict:
        doc_id = str(doc_id or "").strip()
        cui = str(cui or "").strip().upper()
        record = self.records_by_doc_id.get(doc_id) if doc_id else None
        if not record and cui:
            record = self.best_record_for_cui(cui)
        if record:
            hit = self.hit_from_record(record, score=0.0)
        elif cui:
            labels = self.labels_for_cui(cui, [])
            semantic_types = self.semantic_types_for_cui(cui)
            hit = {
                "doc_id": doc_id or f"{cui}:detail",
                "cui": cui,
                "name": self.preferred_label_for_cui(cui) or concept_display_name(labels, fallback=cui),
                "view": "detail",
                "score": 0.0,
                "labels": labels or [cui],
                "sources": [],
                "evidence_count": 0,
                "source_mix": source_mix_from_evidence_items([], declared_sources=[], evidence_count=0),
                "semantic_types": semantic_types,
                **semantic_group_metadata(semantic_types),
                "definitions": self.definitions_for_cui(cui),
                "images": self.images_for_cui(cui),
                "text": "",
                "evidence_items": [],
                "related_concepts": [],
            }
        else:
            return {"error": "missing doc_id or cui"}
        hit["mappings"] = self.mappings_for_cui(str(hit.get("cui") or ""), limit=50)
        if include_related:
            self.attach_related_concepts([hit])
        return {"doc_id": doc_id, "cui": hit.get("cui") or cui, "hit": hit}

    def candidate_from_cui(
        self,
        cui: str,
        *,
        score: float,
        source: str,
        matched: str = "",
        mappings: list[dict] | None = None,
        label: str = "",
    ) -> dict:
        record = self.best_record_for_cui(cui)
        resolved_mappings = mappings if mappings is not None else self.mappings_for_cui(cui, limit=25)
        labels = []
        if label:
            labels.append(label)
        if record:
            labels.extend(record.labels)
        labels.extend(mapping["label"] for mapping in resolved_mappings if mapping.get("label"))
        labels = self.labels_for_cui(cui, labels)
        deduped_labels = []
        seen_labels = set()
        for item in labels:
            key = str(item).strip().lower()
            if not key or key in seen_labels:
                continue
            seen_labels.add(key)
            deduped_labels.append(str(item))
        return {
            "cui": cui,
            "name": self.preferred_label_for_cui(cui) or concept_display_name(deduped_labels, fallback=cui),
            "score": score,
            "source": source,
            "matched": matched,
            "label": self.preferred_label_for_cui(cui) or concept_display_name(deduped_labels, fallback=cui),
            "labels": deduped_labels[:8],
            "has_evidence": bool(record),
            "evidence_count": record.evidence_count if record else 0,
            "best_doc_id": record.doc_id if record else "",
            "best_view": record.view if record else "",
            "semantic_types": self.semantic_types_for_cui(cui),
            "definitions": self.definitions_for_cui(cui),
            "images": self.images_for_cui(cui),
            "mappings": resolved_mappings[:25],
        }

    def candidates_from_mappings(
        self,
        rows: list[dict],
        *,
        source: str,
        matched: str,
        limit: int,
    ) -> list[dict]:
        by_cui: dict[str, list[dict]] = {}
        for row in rows:
            by_cui.setdefault(str(row.get("cui") or ""), []).append(row)
        candidates = []
        for cui, mappings in by_cui.items():
            if not cui:
                continue
            best = mappings[0]
            candidates.append(
                self.candidate_from_cui(
                    cui,
                    score=1.3 if source == "system_code" else 1.2,
                    source=source,
                    matched=matched,
                    mappings=mappings,
                    label=str(best.get("label") or ""),
                )
            )
        sorted_candidates = sorted(
            candidates,
            key=lambda item: (
                -float(item.get("score") or 0),
                0 if item.get("has_evidence") else 1,
                -int(item.get("evidence_count") or 0),
                item.get("label") or "",
            ),
        )
        broadened = self.broaden_code_candidates_from_labels(
            sorted_candidates,
            source=source,
            limit=limit,
        )
        if broadened:
            sorted_candidates = sorted(
                [*sorted_candidates, *broadened],
                key=lambda item: (
                    -float(item.get("score") or 0),
                    0 if item.get("has_evidence") else 1,
                    -int(item.get("evidence_count") or 0),
                    item.get("label") or "",
                ),
            )
        return sorted_candidates[:limit]

    def broaden_code_candidates_from_labels(
        self,
        candidates: list[dict],
        *,
        source: str,
        limit: int,
    ) -> list[dict]:
        if not self.label_fallback.paths:
            return []
        seen_cuis = {str(candidate.get("cui") or "") for candidate in candidates}
        broadened: list[dict] = []
        for candidate in candidates:
            if candidate.get("has_evidence"):
                continue
            seed_cui = str(candidate.get("cui") or "")
            seed_labels = merge_labels(
                [str(candidate.get("label") or "")],
                list(candidate.get("labels") or []),
            )
            for seed_label in seed_labels[:4]:
                for label_hit in self.label_fallback.search(seed_label, limit=max(limit * 4, 20)):
                    cui = str(label_hit.get("cui") or "")
                    matched_span = str(label_hit.get("matched_query_span") or seed_label)
                    if len(content_tokens(matched_span)) < 2:
                        continue
                    if not cui or cui in seen_cuis or not self.best_record_for_cui(cui):
                        continue
                    labels = list(label_hit.get("labels") or [])
                    broadened_candidate = self.candidate_from_cui(
                        cui,
                        score=1.05 if source == "system_code" else 0.95,
                        source=f"{source}_label_broadened",
                        matched=matched_span,
                        label=str(labels[0] if labels else ""),
                    )
                    broadened_candidate["broadened_from_cui"] = seed_cui
                    broadened_candidate["broadened_from_label"] = seed_label
                    seen_cuis.add(cui)
                    broadened.append(broadened_candidate)
                    if len(broadened) >= limit:
                        return broadened
        return broadened

    def resolve(self, query: str, *, limit: int = 10) -> dict:
        raw_query = query.strip()
        if not raw_query:
            return {"query": query, "input_type": "empty", "candidates": []}
        if is_cui(raw_query):
            cui = raw_query.upper()
            return {
                "query": query,
                "input_type": "cui",
                "candidates": [
                    self.candidate_from_cui(cui, score=1.4, source="cui", matched=cui)
                ],
            }
        parsed_code = parse_system_code(raw_query)
        if parsed_code:
            sab, code = parsed_code
            if sab == "CUI" and is_cui(code):
                cui = code.upper()
                return {
                    "query": query,
                    "input_type": "cui",
                    "candidates": [
                        self.candidate_from_cui(cui, score=1.4, source="cui", matched=cui)
                    ],
                }
            rows = self.code_index.lookup_code(code, sab=sab, limit=max(limit * 5, 25)) if self.code_index else []
            return {
                "query": query,
                "input_type": "system_code",
                "system": sab,
                "code": code,
                "candidates": self.candidates_from_mappings(
                    rows,
                    source="system_code",
                    matched=f"{sab}:{code}",
                    limit=limit,
                ),
            }
        if self.code_index and looks_like_code(raw_query):
            rows = self.code_index.lookup_code(raw_query, limit=max(limit * 5, 25))
            if rows:
                return {
                    "query": query,
                    "input_type": "code",
                    "code": raw_query,
                    "candidates": self.candidates_from_mappings(
                        rows,
                        source="code",
                        matched=raw_query,
                        limit=limit,
                    ),
                }
        label_candidates = []
        for hit in self.label_fallback.search(raw_query, limit=limit):
            cui = str(hit.get("cui") or "")
            if not cui:
                continue
            label_candidates.append(
                self.candidate_from_cui(
                    cui,
                    score=float(hit.get("score") or 0),
                    source="umls_label",
                    matched=str(hit.get("matched_query_span") or raw_query),
                    label=(hit.get("labels") or [""])[0],
                )
            )
        return {
            "query": query,
            "input_type": "text",
            "candidates": label_candidates[:limit],
        }

    def hit_from_candidate(self, candidate: dict) -> dict:
        cui = str(candidate.get("cui") or "")
        record = self.best_record_for_cui(cui)
        if record:
            hit = self.hit_from_record(record, score=float(candidate.get("score") or 0))
        else:
            labels = self.labels_for_cui(cui, list(candidate.get("labels") or []))
            definitions = self.definitions_for_cui(cui)
            definition_lines = "\n".join(
                f"- {item.get('source') or 'MRDEF'}: {item.get('definition') or ''}"
                for item in definitions[:3]
            )
            hit = {
                "doc_id": f"{cui}:resolver",
                "cui": cui,
                "name": self.preferred_label_for_cui(cui) or concept_display_name(labels, fallback=cui),
                "view": "resolver",
                "score": float(candidate.get("score") or 0),
                "labels": labels or [cui],
                "sources": [str(candidate.get("source") or "resolver")],
                "evidence_count": 0,
                "source_mix": source_mix_from_evidence_items(
                    [],
                    declared_sources=[str(candidate.get("source") or "resolver")],
                    evidence_count=0,
                ),
                "semantic_types": self.semantic_types_for_cui(cui),
                "text": (
                    f"CUI: {cui}\n"
                    "Evidence view: resolver\n"
                    f"Matched input: {candidate.get('matched') or ''}"
                    + (f"\nDefinitions:\n{definition_lines}" if definition_lines else "")
                ),
                "evidence_items": [],
                "definitions": definitions,
                "related_concepts": [],
            }
        hit["match_type"] = candidate.get("source") or "resolver"
        hit["matched_input"] = candidate.get("matched") or ""
        hit["mappings"] = candidate.get("mappings") or []
        if candidate.get("broadened_from_cui"):
            hit["broadened_from_cui"] = candidate.get("broadened_from_cui") or ""
            hit["broadened_from_label"] = candidate.get("broadened_from_label") or ""
        if candidate.get("semantic_types"):
            hit["semantic_types"] = candidate.get("semantic_types") or []
        hit.update(semantic_group_metadata(list(hit.get("semantic_types") or [])))
        if candidate.get("definitions"):
            hit["definitions"] = merge_definition_lists(
                list(candidate.get("definitions") or []),
                list(hit.get("definitions") or []),
            )
        if candidate.get("labels"):
            hit["labels"] = self.labels_for_cui(
                cui,
                merge_labels(list(candidate.get("labels") or []), list(hit.get("labels") or [])),
            )
            hit["name"] = self.preferred_label_for_cui(cui) or concept_display_name(list(hit.get("labels") or []), fallback=cui)
        if candidate.get("source") and candidate["source"] not in hit.get("sources", []):
            hit["sources"] = [candidate["source"]] + list(hit.get("sources") or [])
            hit["source_mix"] = source_mix_from_evidence_items(
                list(hit.get("evidence_items") or []),
                declared_sources=list(hit.get("sources") or []),
                evidence_count=int(hit.get("evidence_count") or 0),
            )
        return hit

    def scoring_summary(self, backend: str) -> dict:
        if backend == "resolver":
            retrieval = "direct CUI/code resolver"
        elif backend == "elasticsearch":
            retrieval = "Elasticsearch kNN over concept-document embeddings"
        else:
            retrieval = "local vector scan over concept-document embeddings"
        return {
            "retrieval": retrieval,
            "embedding_provider": self.embedder.provider_name,
            "embedding_model": self.embedder.model_name,
            "ranker": "hybrid rerank: lexical label match + bounded MRDEF definition match + MRREL cross-type relation support + query-anchor recall/specificity + vector similarity + evidence presence + semantic, composite-intent, and fragment controls",
            "source_role": (
                "PubMed, PMC OA, MIMIC, and other corpora contribute evidence text to CUI/view "
                "documents. Source names do not receive independent score weights in the current ranker."
            ),
        }

    def direct_search(
        self,
        resolution: dict,
        *,
        top_k: int,
        started: float,
        include_related: bool = True,
        semantic_bucket_keys: object = None,
    ) -> dict:
        semantic_bucket_keys = normalize_semantic_bucket_filter(semantic_bucket_keys)
        candidates = list(resolution.get("candidates") or [])
        candidate_limit = len(candidates) if semantic_bucket_keys else top_k
        hits = [self.hit_from_candidate(candidate) for candidate in candidates[:candidate_limit]]
        hits = self.filter_hits_by_semantic_buckets(hits, semantic_bucket_keys)[:top_k]
        if include_related:
            self.attach_related_concepts(hits)
        for hit in hits:
            hit["score"] = round(float(hit["score"]), 6)
            hit["rank_score"] = hit["score"]
            hit["score_breakdown"] = {
                "rank_score": hit["score"],
                "retrieval_score": hit["score"],
                "lexical_component": 0.0,
                "vector_component": 0.0,
                "label_fallback_component": 0.0,
                "exact_label_component": 0.0,
                "exact_primary_name_component": 0.0,
                "evidence_component": 0.04 if int(hit.get("evidence_count") or 0) > 0 else -0.10,
                "primary_name_component": 0.0,
                "negated_finding_component": 0.0,
                "denied_positive_finding_penalty": 0.0,
                "denied_context_mismatch_penalty": 0.0,
                "semantic_component": 0.0,
                "evidence_context_component": 0.0,
                "definition_component": 0.0,
                "definition_matched_tokens": [],
                "mrrel_component": 0.0,
                "mrrel_matched_tokens": [],
                "mrrel_signal_reasons": [],
                "composite_intent_component": 0.0,
                "specificity_component": 0.0,
                "generic_penalty": 0.0,
                "broad_label_penalty": 0.0,
                "relative_specificity_penalty": 0.0,
                "clinical_context_sense_penalty": 0.0,
                "role_mismatch_penalty": 0.0,
                "numeric_specificity_penalty": 0.0,
                "numeric_context_fragment_penalty": 0.0,
                "action_observation_penalty": 0.0,
                "composite_component_penalty": 0.0,
                "sepsis_subtype_penalty": 0.0,
                "semantic_fragment_penalty": 0.0,
                "generic_fragment_penalty": 0.0,
                "normal_exam_fragment_penalty": 0.0,
                "lexical_fallback_used": False,
                "retrieval_kind": str(hit.get("match_type") or "resolver"),
            }
        return self.compact_search_response({
            "query": resolution.get("query") or "",
            "top_k": top_k,
            "backend": "resolver",
            "scoring": self.scoring_summary("resolver"),
            "semantic_bucket_filter": list(semantic_bucket_keys),
            "input_type": resolution.get("input_type") or "",
            "resolution": resolution,
            "hits": hits,
            **self.semantic_response_metadata(
                hits,
                include_related=include_related,
                semantic_bucket_keys=semantic_bucket_keys,
            ),
            "elapsed_ms": round((time.time() - started) * 1000, 1),
        })
