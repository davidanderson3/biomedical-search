from __future__ import annotations

from qe_evidence_vectors.search_mrrel import (
    MRREL_CATEGORY_ROLE_TOKENS,
    MRREL_RANK_COMPONENT_CAP,
    mrrel_component_for_relation_rows,
    mrrel_relation_group_from_relation,
    relation_category_matches_query_role,
)
from qe_evidence_vectors.search_denial import (
    denied_scope_specific_token_set,
    has_denial_context,
)
from qe_evidence_vectors.search_ranking import (
    label_fallback_anchor_queries,
    mrrel_candidate_priority,
    rank_hits,
    related_anchor_candidate_matches_query,
)
from qe_evidence_vectors.search_hit_features import (
    hit_matched_specific_tokens,
    label_tokens_for_hit,
    specific_query_token_set,
)
from qe_evidence_vectors.search_label_scoring import should_suppress_label_fallback_hit
from qe_evidence_vectors.search_role_tokens import PROCEDURE_ROLE_TOKENS
from qe_evidence_vectors.search_semantics import (
    SEMANTIC_GROUP_RELATION_CATEGORIES,
    semantic_group_from_types,
    semantic_group_metadata,
)
from qe_evidence_vectors.search_tokens import content_tokens
from qe_evidence_vectors.search_utils import (
    merge_definition_lists,
    merge_labels,
    source_mix_from_evidence_items,
)
from qe_evidence_vectors.generic_filters import is_blocked_generic_query
from qe_evidence_vectors.text import normalized_key


def active_label_context_values(value: str) -> list[str]:
    return [
        normalized
        for raw in str(value or "").split("|")
        if (normalized := normalized_key(raw))
    ]


def active_label_phrase_in_query(query_norm: str, phrase_norm: str) -> bool:
    return f" {phrase_norm} " in f" {query_norm} "


def active_label_row_matches_query_context(row: dict, query_norm: str) -> bool:
    required = active_label_context_values(str(row.get("context_any") or ""))
    blocked = active_label_context_values(str(row.get("block_any") or ""))
    if blocked and any(active_label_phrase_in_query(query_norm, phrase) for phrase in blocked):
        return False
    if required and not any(active_label_phrase_in_query(query_norm, phrase) for phrase in required):
        return False
    return True


def definition_fallback_query_is_too_generic(query: str) -> bool:
    return is_blocked_generic_query(query)


class SearchRerankMixin:
    def capped_fallback_limit(self, requested: int, attr: str) -> int:
        requested = max(1, int(requested or 1))
        cap = int(getattr(self, attr, 0) or 0)
        if cap <= 0:
            return requested
        return min(requested, cap)

    def hydrate_label_hit(self, label_hit: dict) -> dict:
        cui = str(label_hit.get("cui") or "")
        label_source = str(label_hit.get("source") or "umls_label")
        record = self.best_record_for_cui(cui)
        if not record:
            hydrated = dict(label_hit)
            hydrated.setdefault("mappings", self.mappings_for_cui(cui, limit=25))
            hydrated.setdefault("semantic_types", self.semantic_types_for_cui(cui))
            hydrated.setdefault("definitions", self.definitions_for_cui(cui))
            hydrated["labels"] = self.labels_for_cui(cui, list(hydrated.get("labels") or []))
            name = self.display_label_for_cui(cui, list(hydrated.get("labels") or []))
            if not name:
                return {}
            hydrated["name"] = name
            hydrated.update(semantic_group_metadata(list(hydrated.get("semantic_types") or [])))
            return hydrated
        hydrated = self.hit_from_record(record, score=float(label_hit.get("score") or 0))
        hydrated["match_type"] = "umls_label"
        hydrated["matched_label"] = label_hit.get("matched_label") or (label_hit.get("labels") or [""])[0]
        hydrated["matched_query_span"] = label_hit.get("matched_query_span") or ""
        hydrated["matched_sab"] = label_hit.get("matched_sab") or ""
        hydrated["matched_tty"] = label_hit.get("matched_tty") or ""
        hydrated["matched_ispref"] = label_hit.get("matched_ispref") or ""
        hydrated["label_fallback_doc_id"] = label_hit.get("doc_id") or ""
        hydrated["labels"] = self.labels_for_cui(
            cui,
            merge_labels(list(label_hit.get("labels") or []), list(hydrated.get("labels") or [])),
        )
        name = self.display_label_for_cui(cui, list(hydrated.get("labels") or []))
        if not name:
            return {}
        hydrated["name"] = name
        hydrated["sources"] = merge_labels([label_source], list(hydrated.get("sources") or []))
        hydrated["mappings"] = self.mappings_for_cui(cui, limit=25)
        return hydrated

    def extension_label_fallback_hits(self, query: str, *, limit: int) -> list[dict]:
        rows_by_norm = getattr(self, "extension_label_rows_by_norm", {})
        if not rows_by_norm:
            return []
        tokens = normalized_key(query).split()
        if not tokens:
            return []
        query_norm = " ".join(tokens)
        query_content_tokens = max(self.label_fallback.content_token_count(tokens), 1)
        best: dict[str, dict] = {}
        for span_norm, token_count, span_content_tokens in self.label_fallback.query_spans(tokens):
            rows = rows_by_norm.get(span_norm, [])
            if not rows:
                continue
            context_rows = [
                row for row in rows if active_label_row_matches_query_context(row, query_norm)
            ]
            if not context_rows:
                continue
            unique_cuis = {row["cui"] for row in context_rows}
            for row in context_rows:
                score = self.label_fallback.label_score(
                    token_count=token_count,
                    query_content_tokens=query_content_tokens,
                    span_content_tokens=span_content_tokens,
                    unique_cui_count=len(unique_cuis),
                    is_preferred=str(row.get("ispref") or "") == "Y",
                )
                candidate = {
                    "doc_id": row.get("doc_id") or f"{row['cui']}:extension_label",
                    "cui": row["cui"],
                    "view": "extension_label",
                    "score": score,
                    "labels": [row["label"]],
                    "sources": ["extension_label"],
                    "source": "extension_label",
                    "evidence_count": 0,
                    "match_type": "umls_label",
                    "matched_label": row["label"],
                    "matched_query_span": span_norm,
                    "text": (
                        f"CUI: {row['cui']}\n"
                        "Evidence view: extension_label\n"
                        "Local extension label fallback:\n"
                        f"- {row['label']}\n"
                        f"Matched query span: {span_norm}"
                    ),
                    "evidence_items": [],
                    "images": self.images_for_cui(row["cui"]),
                }
                current = best.get(row["cui"])
                if current is None or candidate["score"] > current["score"]:
                    best[row["cui"]] = candidate
        return sorted(best.values(), key=lambda item: item["score"], reverse=True)[:limit]

    def active_label_supplement_hits(self, query: str, *, limit: int) -> list[dict]:
        rows_by_norm = getattr(self, "active_label_rows_by_norm", {})
        if not rows_by_norm:
            return []
        tokens = normalized_key(query).split()
        if not tokens:
            return []
        query_norm = " ".join(tokens)
        query_content_tokens = max(self.label_fallback.content_token_count(tokens), 1)
        best: dict[str, dict] = {}
        for span_norm, token_count, span_content_tokens in self.active_label_query_spans(
            tokens,
            rows_by_norm=rows_by_norm,
        ):
            rows = rows_by_norm.get(span_norm, [])
            if not rows:
                continue
            context_rows = [
                row for row in rows if active_label_row_matches_query_context(row, query_norm)
            ]
            if not context_rows:
                continue
            unique_cuis = {row["cui"] for row in context_rows}
            for row in context_rows:
                score = self.label_fallback.label_score(
                    token_count=token_count,
                    query_content_tokens=query_content_tokens,
                    span_content_tokens=span_content_tokens,
                    unique_cui_count=len(unique_cuis),
                    is_preferred=str(row.get("ispref") or "") == "Y",
                )
                candidate = {
                    "doc_id": row.get("doc_id") or f"{row['cui']}:active_label_supplement",
                    "cui": row["cui"],
                    "view": "active_label_supplement",
                    "score": score,
                    "labels": [row["label"]],
                    "sources": ["active_label_supplement"],
                    "source": "active_label_supplement",
                    "evidence_count": 0,
                    "match_type": "umls_label",
                    "matched_label": row["label"],
                    "matched_query_span": span_norm,
                    "matched_sab": row.get("sab") or "",
                    "matched_tty": row.get("tty") or "",
                    "matched_ispref": row.get("ispref") or "",
                    "text": (
                        f"CUI: {row['cui']}\n"
                        "Evidence view: active_label_supplement\n"
                        "Curated active label supplement:\n"
                        f"- {row['label']}\n"
                        f"Matched query span: {span_norm}"
                    ),
                    "evidence_items": [],
                }
                current = best.get(row["cui"])
                if current is None or candidate["score"] > current["score"]:
                    best[row["cui"]] = candidate
        return sorted(best.values(), key=lambda item: item["score"], reverse=True)[:limit]

    def active_label_query_spans(
        self,
        tokens: list[str],
        *,
        rows_by_norm: dict[str, list[dict]],
    ):
        max_len = min(self.label_fallback.max_tokens, len(tokens))
        seen = set()
        for length in range(max_len, 0, -1):
            for start in range(0, len(tokens) - length + 1):
                span_tokens = tokens[start : start + length]
                span_norm = " ".join(span_tokens)
                if span_norm in seen:
                    continue
                seen.add(span_norm)
                if span_norm not in rows_by_norm:
                    continue
                content_count = max(self.label_fallback.content_token_count(span_tokens), 1)
                yield span_norm, length, content_count

    def definition_fallback_hits(self, query: str, *, limit: int) -> list[dict]:
        if not self.definition_index:
            return []
        if definition_fallback_query_is_too_generic(query):
            return []
        if len(specific_query_token_set(content_tokens(query))) < 2:
            return []
        hydrated_hits = []
        for definition_hit in self.definition_index.search(query, limit=limit):
            cui = str(definition_hit.get("cui") or "")
            if not cui:
                continue
            candidate = self.candidate_from_cui(
                cui,
                score=float(definition_hit.get("score") or 0.0),
                source="umls_definition",
                matched=str(definition_hit.get("match_query") or ""),
            )
            hit = self.hit_from_candidate(candidate)
            matched_definition = {
                "cui": cui,
                "source": definition_hit.get("source") or "",
                "definition": definition_hit.get("definition") or "",
                "rank": int(definition_hit.get("rank") or 0),
            }
            hit["match_type"] = "umls_definition"
            hit["matched_definition"] = matched_definition
            hit["matched_query_span"] = str(definition_hit.get("match_query") or "")
            hit["definitions"] = merge_definition_lists(
                [matched_definition],
                list(hit.get("definitions") or []),
            )
            hit["sources"] = merge_labels(["umls_definition"], list(hit.get("sources") or []))
            hit["source_mix"] = source_mix_from_evidence_items(
                list(hit.get("evidence_items") or []),
                declared_sources=list(hit.get("sources") or []),
                evidence_count=int(hit.get("evidence_count") or 0),
            )
            hydrated_hits.append(hit)
        return hydrated_hits

    def attach_mrrel_rank_signals(
        self,
        query: str,
        hits: list[dict],
        *,
        candidate_limit: int | None = None,
    ) -> None:
        for hit in hits:
            hit["mrrel_component"] = 0.0
            hit["mrrel_matched_tokens"] = []
            hit["mrrel_signal_reasons"] = []
        use_relationship_edges_for_ranking = bool(getattr(self, "relationship_edges_rank", False))
        if not hits or not (
            self.research_relation_index
            or self.relation_index
            or (use_relationship_edges_for_ranking and getattr(self, "relationship_edge_index", None))
        ):
            return
        query_tokens = content_tokens(query)
        query_set = set(query_tokens)
        if not query_tokens:
            return
        raw_query_token_list = normalized_key(query).split()
        specific_tokens = specific_query_token_set(query_tokens)
        denied_tokens = (
            denied_scope_specific_token_set(raw_query_token_list)
            if has_denial_context(set(raw_query_token_list))
            else set()
        )
        positive_specific_tokens = specific_tokens - denied_tokens
        if not positive_specific_tokens:
            positive_specific_tokens = specific_tokens
        if not positive_specific_tokens:
            return
        has_role_intent = any(query_set & tokens for tokens in MRREL_CATEGORY_ROLE_TOKENS.values())
        rankable_hits = hits
        if candidate_limit is not None and candidate_limit > 0 and len(hits) > candidate_limit:
            rankable_hits = sorted(
                hits,
                key=lambda hit: mrrel_candidate_priority(query_tokens, hit),
                reverse=True,
            )[:candidate_limit]
        for hit in rankable_hits:
            cui = str(hit.get("cui") or "")
            if not cui:
                continue
            label_tokens = label_tokens_for_hit(hit)
            label_matched = positive_specific_tokens & label_tokens
            source_group = semantic_group_from_types(list(hit.get("semantic_types") or []))
            hit_category = SEMANTIC_GROUP_RELATION_CATEGORIES.get(source_group, "")
            hit_role_match = relation_category_matches_query_role(hit_category, query_set)
            if not (label_matched or hit_role_match or has_role_intent or len(positive_specific_tokens) >= 2):
                continue
            research_relations = self.research_relations_for_cui(
                cui,
                include_relationship_edges=use_relationship_edges_for_ranking,
            )
            research_component, research_tokens, research_reasons = mrrel_component_for_relation_rows(
                query_tokens=query_tokens,
                query_set=query_set,
                positive_specific_tokens=positive_specific_tokens,
                label_tokens=label_tokens,
                source_group=source_group,
                hit_category=hit_category,
                relations=research_relations,
                is_research=True,
            )
            research_targets = {str(reason.get("cui") or "") for reason in research_reasons}
            generic_relations = []
            if self.relation_index and not self.research_relation_index:
                for relation in self.related_concepts_for_cui(cui):
                    target_cui = str(relation.get("cui") or "")
                    if target_cui in research_targets:
                        continue
                    target_group = semantic_group_from_types(self.semantic_types_for_cui(target_cui))
                    enriched = dict(relation)
                    enriched["category"] = SEMANTIC_GROUP_RELATION_CATEGORIES.get(target_group, "")
                    enriched["target_semantic_group"] = target_group
                    enriched["relation_group"] = mrrel_relation_group_from_relation(enriched)
                    generic_relations.append(enriched)
            generic_component, generic_tokens, generic_reasons = mrrel_component_for_relation_rows(
                query_tokens=query_tokens,
                query_set=query_set,
                positive_specific_tokens=positive_specific_tokens,
                label_tokens=label_tokens,
                source_group=source_group,
                hit_category=hit_category,
                relations=generic_relations,
                is_research=False,
            )
            component = min(
                research_component + generic_component,
                MRREL_RANK_COMPONENT_CAP,
            )
            if component <= 0.0:
                continue
            matched_tokens = sorted((research_tokens | generic_tokens) & positive_specific_tokens)
            reasons = sorted(
                [*research_reasons, *generic_reasons],
                key=lambda reason: (
                    -float(reason.get("component") or 0.0),
                    str(reason.get("label") or ""),
                    str(reason.get("cui") or ""),
                ),
            )[:5]
            hit["mrrel_component"] = round(component, 6)
            hit["mrrel_matched_tokens"] = matched_tokens
            hit["mrrel_signal_reasons"] = reasons

    def merge_label_fallback(self, query: str, hits: list[dict], *, top_k: int) -> list[dict]:
        has_extension_labels = bool(getattr(self, "extension_label_rows_by_norm", {}))
        has_active_label_supplement = bool(getattr(self, "active_label_rows_by_norm", {}))
        if (
            not self.label_fallback.paths
            and not self.definition_index
            and not has_extension_labels
            and not has_active_label_supplement
        ):
            self.attach_mrrel_rank_signals(query, hits, candidate_limit=min(max(top_k * 4, 20), 80))
            return rank_hits(query, hits, top_k=top_k)
        best_by_cui = {hit.get("cui", ""): hit for hit in hits if hit.get("cui")}
        label_hits = []
        if self.label_fallback.paths:
            label_hits = self.label_fallback.search(
                query,
                limit=self.capped_fallback_limit(
                    max(top_k * 12, 100),
                    "label_fallback_limit",
                ),
            )
            for anchor_query in label_fallback_anchor_queries(query):
                label_hits.extend(self.label_fallback.search(anchor_query, limit=8))
        label_hits.extend(
            self.extension_label_fallback_hits(
                query,
                limit=self.capped_fallback_limit(max(top_k * 8, 60), "label_fallback_limit"),
            )
        )
        label_hits.extend(
            self.active_label_supplement_hits(
                query,
                limit=self.capped_fallback_limit(max(top_k * 4, 40), "label_fallback_limit"),
            )
        )
        for label_hit in label_hits:
            hydrated = self.hydrate_label_hit(label_hit)
            if not hydrated:
                continue
            if should_suppress_label_fallback_hit(hydrated):
                continue
            current = best_by_cui.get(label_hit["cui"])
            hydrated_sources = [str(source) for source in hydrated.get("sources") or []]
            if current is not None and "active_label_supplement" in hydrated_sources:
                current_span_tokens = len(content_tokens(str(current.get("matched_query_span") or "")))
                hydrated_span_tokens = len(content_tokens(str(hydrated.get("matched_query_span") or "")))
                current["labels"] = self.labels_for_cui(
                    str(current.get("cui") or ""),
                    merge_labels(
                        list(hydrated.get("labels") or []),
                        list(current.get("labels") or []),
                    ),
                )
                current["sources"] = merge_labels(
                    list(hydrated.get("sources") or []),
                    list(current.get("sources") or []),
                )
                if current.get("match_type") != "umls_label" or hydrated_span_tokens >= current_span_tokens:
                    current["match_type"] = "umls_label"
                    current["matched_label"] = hydrated.get("matched_label") or current.get("matched_label") or ""
                    current["matched_query_span"] = hydrated.get("matched_query_span") or current.get("matched_query_span") or ""
                    current["matched_sab"] = hydrated.get("matched_sab") or current.get("matched_sab") or ""
                    current["matched_tty"] = hydrated.get("matched_tty") or current.get("matched_tty") or ""
                    current["matched_ispref"] = hydrated.get("matched_ispref") or current.get("matched_ispref") or ""
                    current["label_fallback_doc_id"] = hydrated.get("label_fallback_doc_id") or current.get("label_fallback_doc_id") or ""
                    if int(current.get("evidence_count") or 0) > 0:
                        current["vector_score_preserved"] = True
                if float(current.get("score") or 0.0) >= float(hydrated.get("score") or 0.0):
                    continue
            if current is not None and current.get("match_type") == "umls_label":
                current_span_tokens = len(content_tokens(str(current.get("matched_query_span") or "")))
                hydrated_span_tokens = len(content_tokens(str(hydrated.get("matched_query_span") or "")))
                if current_span_tokens > hydrated_span_tokens:
                    current["labels"] = self.labels_for_cui(
                        str(current.get("cui") or ""),
                        merge_labels(
                            list(current.get("labels") or []),
                            list(hydrated.get("labels") or []),
                        ),
                    )
                    current["sources"] = merge_labels(
                        list(current.get("sources") or []),
                        list(hydrated.get("sources") or []),
                    )
                    continue
            if (
                current is not None
                and hydrated.get("match_type") == "umls_label"
                and current.get("match_type") != "umls_label"
                and int(current.get("evidence_count") or 0) > 0
            ):
                current["labels"] = self.labels_for_cui(
                    str(current.get("cui") or ""),
                    merge_labels(
                        list(hydrated.get("labels") or []),
                        list(current.get("labels") or []),
                    ),
                )
                current["sources"] = merge_labels(
                    list(hydrated.get("sources") or []),
                    list(current.get("sources") or []),
                )
                current.setdefault("matched_label", hydrated.get("matched_label") or "")
                current.setdefault("matched_query_span", hydrated.get("matched_query_span") or "")
                current.setdefault("label_fallback_doc_id", hydrated.get("label_fallback_doc_id") or "")
                current["match_type"] = "umls_label"
                current["vector_score_preserved"] = True
                continue
            if current is None or hydrated["score"] > float(current.get("score", 0)):
                best_by_cui[label_hit["cui"]] = hydrated
        for definition_hit in self.definition_fallback_hits(
            query,
            limit=self.capped_fallback_limit(
                max(top_k * 8, 60),
                "definition_fallback_limit",
            ),
        ):
            cui = str(definition_hit.get("cui") or "")
            current = best_by_cui.get(cui)
            if current is None:
                best_by_cui[cui] = definition_hit
                continue
            current["definitions"] = merge_definition_lists(
                list(definition_hit.get("definitions") or []),
                list(current.get("definitions") or []),
            )
            current.setdefault("matched_definition", definition_hit.get("matched_definition") or {})
            current.setdefault("matched_query_span", definition_hit.get("matched_query_span") or "")
            current["sources"] = merge_labels(
                ["umls_definition"],
                list(current.get("sources") or []),
            )
            current["source_mix"] = source_mix_from_evidence_items(
                list(current.get("evidence_items") or []),
                declared_sources=list(current.get("sources") or []),
                evidence_count=int(current.get("evidence_count") or 0),
            )
            if current.get("match_type") not in {"umls_label", "umls_definition"}:
                current["definition_score_preserved"] = True
        hits = self.merge_related_anchor_candidates(query, list(best_by_cui.values()), top_k=top_k)
        self.attach_mrrel_rank_signals(query, hits, candidate_limit=min(max(top_k * 4, 20), 80))
        return rank_hits(query, hits, top_k=top_k)

    def merge_related_anchor_candidates(self, query: str, hits: list[dict], *, top_k: int) -> list[dict]:
        query_tokens = content_tokens(query)
        query_set = set(query_tokens)
        if not (query_set & PROCEDURE_ROLE_TOKENS):
            return hits
        best_by_cui = {str(hit.get("cui") or ""): hit for hit in hits if hit.get("cui")}
        seeds = [
            hit
            for hit in hits
            if hit.get("match_type") == "umls_label"
            and hit_matched_specific_tokens(hit, query_tokens=query_tokens)
        ]
        seeds = sorted(seeds, key=lambda hit: float(hit.get("score") or 0.0), reverse=True)[:3]
        added = 0
        for seed in seeds:
            for candidate in self.evidence_vector_neighbors_for_cui(
                str(seed.get("cui") or ""),
                top_k=max(top_k * 4, 12),
            ):
                cui = str(candidate.get("cui") or "")
                if not cui or cui in best_by_cui:
                    continue
                if not related_anchor_candidate_matches_query(
                    query_tokens=query_tokens,
                    seed_hit=seed,
                    candidate_hit=candidate,
                ):
                    continue
                candidate["match_type"] = "related_anchor_vector"
                candidate["related_seed_cui"] = str(seed.get("cui") or "")
                candidate["related_seed_label"] = str(seed.get("name") or "")
                candidate["matched_query_span"] = str(seed.get("matched_query_span") or "")
                candidate["sources"] = merge_labels(
                    ["related_anchor_vector"],
                    list(candidate.get("sources") or []),
                )
                best_by_cui[cui] = candidate
                added += 1
                if added >= max(top_k * 2, 10):
                    return list(best_by_cui.values())
        return list(best_by_cui.values())
