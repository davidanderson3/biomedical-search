from __future__ import annotations

from qe_evidence_vectors.search_mrrel import (
    MRREL_CATEGORY_ROLE_TOKENS,
    MRREL_RANK_COMPONENT_CAP,
    mrrel_component_for_relation_rows,
    mrrel_relation_group_from_relation,
    relation_category_matches_query_role,
)
from qe_evidence_vectors.search_assertions import assertion_context_for_hit
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
from qe_evidence_vectors.clinical_query_expansion import clinical_query_variants
from qe_evidence_vectors.entity_mentions import (
    context_window,
    detect_parenthetical_abbreviations,
    section_for_offset,
    sentence_index_for_offset,
    token_spans,
)
from qe_evidence_vectors.generic_filters import is_blocked_generic_query
from qe_evidence_vectors.text import normalized_key


MRREL_BROAD_QUERY_SCAN_LIMIT = 12
LINKED_CONCEPT_GROUPS = {
    "ANAT",
    "CHEM",
    "DEVI",
    "DISO",
    "FIND",
    "GENE",
    "LIVB",
    "OBS",
    "PHEN",
    "PHYS",
    "PROC",
}
LINKED_CONCEPT_EXCLUDED_TYPES = {
    "health care activity",
}
LINKED_CONCEPT_BLOCKED_MATCHES = {
    "absent",
    "report",
    "reported",
    "reports",
    "today",
    "tomorrow",
    "tonight",
    "yesterday",
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
MIN_RANKED_LINKED_LABEL_TOKEN_COUNT = 3
MAX_ENTITY_CANDIDATES_PER_SURFACE = 3


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


def linked_concept_hit_is_highlightable(hit: dict) -> bool:
    group = str(hit.get("semantic_group") or semantic_group_from_types(list(hit.get("semantic_types") or [])))
    if group not in LINKED_CONCEPT_GROUPS:
        return False
    type_names = {
        str(item.get("name") or "").strip().lower()
        for item in hit.get("semantic_types") or []
        if str(item.get("name") or "").strip()
    }
    if type_names & LINKED_CONCEPT_EXCLUDED_TYPES:
        return False
    return True


def temporal_word_chemical_mention_false_positive(hit: dict) -> bool:
    span_tokens = content_tokens(
        str(
            hit.get("matched_query_span")
            or hit.get("matched_label")
            or hit.get("name")
            or ""
        )
    )
    if len(span_tokens) != 1 or span_tokens[0] not in TEMPORAL_WORD_CHEMICAL_SPANS:
        return False
    type_names = {
        str(item.get("name") or "").strip().lower()
        for item in hit.get("semantic_types") or []
        if str(item.get("name") or "").strip()
    }
    return bool(type_names & TEMPORAL_WORD_CHEMICAL_SEMANTIC_TYPES)


def linked_label_candidate_is_rankable(hit: dict, *, query_tokens: set[str]) -> bool:
    if str(hit.get("match_type") or "") != "umls_label":
        return False
    assertion = hit.get("assertion") or {}
    if assertion.get("status") == "negated":
        return False
    span_tokens = content_tokens(str(hit.get("matched_query_span") or ""))
    span_norm_tokens = normalized_key(str(hit.get("matched_query_span") or "")).split()
    if len(span_norm_tokens) < MIN_RANKED_LINKED_LABEL_TOKEN_COUNT:
        return False
    span_set = set(span_tokens)
    if query_tokens and not span_set <= query_tokens:
        return False
    span_norm_set = set(span_norm_tokens)
    labels = [
        str(hit.get("name") or ""),
        str(hit.get("matched_label") or ""),
        *[str(label or "") for label in hit.get("labels") or []],
    ]
    label_token_sets = [
        set(normalized_key(label).split())
        for label in labels
        if len(normalized_key(label).split()) >= MIN_RANKED_LINKED_LABEL_TOKEN_COUNT
    ]
    if not any(label_tokens <= span_norm_set for label_tokens in label_token_sets):
        return False
    sources = {str(source) for source in hit.get("sources") or []}
    if "active_label_supplement" not in sources and int(hit.get("evidence_count") or 0) <= 0:
        return False
    return linked_concept_hit_is_highlightable(hit)


def entity_mention_priority(mention: dict) -> tuple[int, float, int, int, str]:
    source_rank = {
        "active_label_supplement": 3,
        "extension_label": 2,
        "umls_label": 1,
    }.get(str(mention.get("match_source") or ""), 0)
    length = int(mention.get("end") or 0) - int(mention.get("start") or 0)
    is_preferred = 1 if str(mention.get("matched_ispref") or "") == "Y" else 0
    return (
        source_rank,
        float(mention.get("score") or 0.0),
        length,
        is_preferred,
        str(mention.get("name") or ""),
    )


def spans_overlap(left: dict, right: dict) -> bool:
    return int(left["start"]) < int(right["end"]) and int(right["start"]) < int(left["end"])


def span_contains(outer: dict, inner: dict) -> bool:
    return int(outer["start"]) <= int(inner["start"]) and int(inner["end"]) <= int(outer["end"])


def suppress_nested_entity_mentions(mentions: list[dict], *, limit: int) -> list[dict]:
    by_surface: dict[tuple[int, int], list[dict]] = {}
    for mention in mentions:
        key = (int(mention.get("start") or 0), int(mention.get("end") or 0))
        by_surface.setdefault(key, []).append(mention)

    surface_candidates: list[dict] = []
    for rows in by_surface.values():
        sorted_rows = sorted(rows, key=entity_mention_priority, reverse=True)
        for ambiguity_rank, mention in enumerate(
            sorted_rows[:MAX_ENTITY_CANDIDATES_PER_SURFACE],
            start=1,
        ):
            mention["ambiguity_rank"] = ambiguity_rank
            surface_candidates.append(mention)

    accepted: list[dict] = []
    for mention in sorted(
        surface_candidates,
        key=lambda item: (
            -(int(item.get("end") or 0) - int(item.get("start") or 0)),
            -float(item.get("score") or 0.0),
            int(item.get("start") or 0),
            int(item.get("ambiguity_rank") or 0),
        ),
    ):
        nested = False
        for existing in accepted:
            if not spans_overlap(existing, mention):
                continue
            if int(existing["start"]) == int(mention["start"]) and int(existing["end"]) == int(mention["end"]):
                continue
            if span_contains(existing, mention) or span_contains(mention, existing):
                nested = True
                break
        if not nested:
            accepted.append(mention)
    accepted.sort(key=lambda item: (int(item.get("start") or 0), int(item.get("end") or 0)))
    for index, mention in enumerate(accepted[: max(0, int(limit or 0))], start=1):
        mention["mention_id"] = f"m{index:04d}"
    return accepted[: max(0, int(limit or 0))]


class SearchRerankMixin:
    def capped_fallback_limit(self, requested: int, attr: str) -> int:
        requested = max(1, int(requested or 1))
        cap = int(getattr(self, attr, 0) or 0)
        if cap <= 0:
            return requested
        return min(requested, cap)

    def mrrel_rank_candidate_limit(self, top_k: int) -> int:
        return min(max(int(top_k or 0), 20), 40)

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
        hydrated = self.hit_from_record(
            record,
            score=float(label_hit.get("score") or 0),
            hydrate_details=False,
            include_codes=False,
        )
        hydrated["match_type"] = "umls_label"
        hydrated["matched_label"] = label_hit.get("matched_label") or (label_hit.get("labels") or [""])[0]
        hydrated["matched_query_span"] = label_hit.get("matched_query_span") or ""
        hydrated["matched_sab"] = label_hit.get("matched_sab") or ""
        hydrated["matched_tty"] = label_hit.get("matched_tty") or ""
        hydrated["matched_ispref"] = label_hit.get("matched_ispref") or ""
        hydrated["label_fallback_doc_id"] = label_hit.get("doc_id") or ""
        hydrated["label_fallback_score"] = float(label_hit.get("score") or 0.0)
        hydrated["labels"] = self.labels_for_cui(
            cui,
            merge_labels(list(label_hit.get("labels") or []), list(hydrated.get("labels") or [])),
        )
        name = self.display_label_for_cui(cui, list(hydrated.get("labels") or []))
        if not name:
            return {}
        hydrated["name"] = name
        hydrated["sources"] = merge_labels([label_source], list(hydrated.get("sources") or []))
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
            for lookup_norm in self.label_fallback.lookup_norms_for_span(span_norm):
                rows = rows_by_norm.get(lookup_norm, [])
                if not rows:
                    continue
                context_rows = [
                    row for row in rows if active_label_row_matches_query_context(row, query_norm)
                ]
                if not context_rows:
                    continue
                unique_cuis = {row["cui"] for row in context_rows}
                lexical_variant = lookup_norm != span_norm
                for row in context_rows:
                    score = self.label_fallback.label_score(
                        token_count=token_count,
                        query_content_tokens=query_content_tokens,
                        span_content_tokens=span_content_tokens,
                        unique_cui_count=len(unique_cuis),
                        is_preferred=str(row.get("ispref") or "") == "Y",
                        lexical_variant=lexical_variant,
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
                        "matched_lookup_norm": lookup_norm,
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
        for span_norm, lookup_norm, token_count, span_content_tokens in self.active_label_query_spans(
            tokens,
            rows_by_norm=rows_by_norm,
        ):
            rows = rows_by_norm.get(lookup_norm, [])
            if not rows:
                continue
            context_rows = [
                row for row in rows if active_label_row_matches_query_context(row, query_norm)
            ]
            if not context_rows:
                continue
            unique_cuis = {row["cui"] for row in context_rows}
            lexical_variant = lookup_norm != span_norm
            for row in context_rows:
                score = self.label_fallback.label_score(
                    token_count=token_count,
                    query_content_tokens=query_content_tokens,
                    span_content_tokens=span_content_tokens,
                    unique_cui_count=len(unique_cuis),
                    is_preferred=str(row.get("ispref") or "") == "Y",
                    lexical_variant=lexical_variant,
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
                    "matched_lookup_norm": lookup_norm,
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

    def query_linked_concept_hits(self, query: str, *, limit: int) -> list[dict]:
        """Exact mention matches for UI highlighting, separate from ranked results."""
        query = str(query or "").strip()
        if not query:
            return []
        has_extension_labels = bool(getattr(self, "extension_label_rows_by_norm", {}))
        has_active_label_supplement = bool(getattr(self, "active_label_rows_by_norm", {}))
        if not self.label_fallback.paths and not has_extension_labels and not has_active_label_supplement:
            return []
        query_tokens = set(content_tokens(query))
        if not query_tokens:
            return []
        raw_label_hits: list[dict] = []
        fallback_queries = [query, *label_fallback_anchor_queries(query)]
        seen_queries = set()
        label_limit = self.capped_fallback_limit(max(limit * 4, 80), "label_fallback_limit")
        extension_limit = self.capped_fallback_limit(max(limit * 3, 60), "label_fallback_limit")
        active_limit = self.capped_fallback_limit(max(limit * 3, 60), "label_fallback_limit")
        for index, fallback_query in enumerate(fallback_queries):
            fallback_query = str(fallback_query or "").strip()
            normalized_query = normalized_key(fallback_query)
            if not normalized_query or normalized_query in seen_queries:
                continue
            seen_queries.add(normalized_query)
            if self.label_fallback.paths:
                raw_label_hits.extend(
                    self.label_fallback.search(
                        fallback_query,
                        limit=label_limit if index == 0 else min(label_limit, 12),
                    )
                )
            raw_label_hits.extend(
                self.extension_label_fallback_hits(
                    fallback_query,
                    limit=extension_limit if index == 0 else min(extension_limit, 12),
                )
            )
            raw_label_hits.extend(
                self.active_label_supplement_hits(
                    fallback_query,
                    limit=active_limit if index == 0 else min(active_limit, 12),
                )
            )

        best_by_key: dict[tuple[str, str], dict] = {}
        for label_hit in raw_label_hits:
            hydrated = self.hydrate_label_hit(label_hit)
            if not hydrated:
                continue
            if not linked_concept_hit_is_highlightable(hydrated):
                continue
            if should_suppress_label_fallback_hit(hydrated):
                continue
            if temporal_word_chemical_mention_false_positive(hydrated):
                continue
            label_tokens = label_tokens_for_hit(hydrated)
            if label_tokens and not (label_tokens & query_tokens):
                continue
            span_key = normalized_key(
                hydrated.get("matched_query_span")
                or hydrated.get("matched_label")
                or hydrated.get("name")
                or ""
            )
            label_key = normalized_key(hydrated.get("matched_label") or "")
            if span_key in LINKED_CONCEPT_BLOCKED_MATCHES or label_key in LINKED_CONCEPT_BLOCKED_MATCHES:
                continue
            cui = str(hydrated.get("cui") or "")
            if not cui or not span_key:
                continue
            hydrated["linked_only"] = True
            hydrated["rank_score"] = float(hydrated.get("rank_score") or hydrated.get("score") or 0.0)
            hydrated["assertion"] = assertion_context_for_hit(
                query=query,
                labels=[str(label or "") for label in hydrated.get("labels") or []],
                hit=hydrated,
            )
            key = (cui, span_key)
            current = best_by_key.get(key)
            if current is None or self.linked_concept_priority(hydrated) > self.linked_concept_priority(current):
                best_by_key[key] = hydrated
        return sorted(
            best_by_key.values(),
            key=self.linked_concept_priority,
            reverse=True,
        )[:limit]

    def linked_concept_priority(self, hit: dict) -> tuple[float, int, int, str]:
        assertion = hit.get("assertion") or {}
        span_token_count = len(content_tokens(str(hit.get("matched_query_span") or "")))
        return (
            float(hit.get("score") or 0.0),
            1 if assertion.get("status") == "negated" else 0,
            span_token_count,
            str(hit.get("name") or ""),
        )

    def merge_rankable_linked_label_candidates(
        self,
        query: str,
        best_by_cui: dict[str, dict],
        *,
        top_k: int,
    ) -> None:
        query_tokens = set(content_tokens(query))
        promoted_cuis = getattr(self, "_rankable_linked_label_promotion_cuis", [])
        if not query_tokens:
            self._rankable_linked_label_promotion_cuis = promoted_cuis
            return
        limit = self.capped_fallback_limit(max(top_k * 2, 80), "label_fallback_limit")
        for linked_hit in self.query_linked_concept_hits(query, limit=limit):
            if not linked_label_candidate_is_rankable(linked_hit, query_tokens=query_tokens):
                continue
            cui = str(linked_hit.get("cui") or "")
            if not cui:
                continue
            candidate = dict(linked_hit)
            candidate.pop("linked_only", None)
            candidate.pop("details_lazy", None)
            candidate.pop("rank_score", None)
            current = best_by_cui.get(cui)
            if current is None:
                best_by_cui[cui] = candidate
                promoted_cuis.append(cui)
                continue
            current_span_tokens = len(content_tokens(str(current.get("matched_query_span") or "")))
            candidate_span_tokens = len(content_tokens(str(candidate.get("matched_query_span") or "")))
            current["label_fallback_score"] = max(
                float(current.get("label_fallback_score") or 0.0),
                float(candidate.get("label_fallback_score") or candidate.get("score") or 0.0),
            )
            current["labels"] = merge_labels(
                list(candidate.get("labels") or []),
                list(current.get("labels") or []),
            )
            current["sources"] = merge_labels(
                list(candidate.get("sources") or []),
                list(current.get("sources") or []),
            )
            if current.get("match_type") != "umls_label" or candidate_span_tokens >= current_span_tokens:
                current["match_type"] = "umls_label"
                current["matched_label"] = candidate.get("matched_label") or current.get("matched_label") or ""
                current["matched_query_span"] = (
                    candidate.get("matched_query_span") or current.get("matched_query_span") or ""
                )
                current["matched_sab"] = candidate.get("matched_sab") or current.get("matched_sab") or ""
                current["matched_tty"] = candidate.get("matched_tty") or current.get("matched_tty") or ""
                current["matched_ispref"] = (
                    candidate.get("matched_ispref") or current.get("matched_ispref") or ""
                )
                current["label_fallback_doc_id"] = (
                    candidate.get("label_fallback_doc_id")
                    or current.get("label_fallback_doc_id")
                    or ""
                )
                if int(current.get("evidence_count") or 0) > 0:
                    current["vector_score_preserved"] = True
                promoted_cuis.append(cui)
        self._rankable_linked_label_promotion_cuis = promoted_cuis

    def promote_rankable_linked_label_results(
        self,
        query: str,
        hits: list[dict],
        *,
        top_k: int,
    ) -> list[dict]:
        self._rankable_linked_label_promotion_cuis = []
        best_by_cui = {str(hit.get("cui") or ""): hit for hit in hits if hit.get("cui")}
        before_signature = {
            cui: (
                str(hit.get("matched_query_span") or ""),
                tuple(str(source) for source in hit.get("sources") or []),
                float(hit.get("label_fallback_score") or 0.0),
            )
            for cui, hit in best_by_cui.items()
        }
        self.merge_rankable_linked_label_candidates(query, best_by_cui, top_k=top_k)
        after_signature = {
            cui: (
                str(hit.get("matched_query_span") or ""),
                tuple(str(source) for source in hit.get("sources") or []),
                float(hit.get("label_fallback_score") or 0.0),
            )
            for cui, hit in best_by_cui.items()
        }
        if before_signature == after_signature:
            return hits
        promoted_hits = list(best_by_cui.values())
        self.attach_mrrel_rank_signals(
            query,
            promoted_hits,
            candidate_limit=self.mrrel_rank_candidate_limit(top_k),
        )
        return rank_hits(query, promoted_hits, top_k=top_k)

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
                for lookup_norm in self.label_fallback.lookup_norms_for_span(span_norm):
                    if lookup_norm not in rows_by_norm:
                        continue
                    content_count = max(self.label_fallback.content_token_count(span_tokens), 1)
                    yield span_norm, lookup_norm, length, content_count

    def query_entity_mentions(
        self,
        query: str,
        *,
        limit: int = 200,
        return_code_sabs: object = None,
    ) -> list[dict]:
        """Dictionary mention extraction with offsets, assertion cues, and code summaries."""
        text = str(query or "")
        tokens = token_spans(text)
        if not tokens:
            return []
        has_extension_labels = bool(getattr(self, "extension_label_rows_by_norm", {}))
        has_active_label_supplement = bool(getattr(self, "active_label_rows_by_norm", {}))
        if not self.label_fallback.paths and not has_extension_labels and not has_active_label_supplement:
            return []
        query_norm = " ".join(token.norm for token in tokens)
        query_content_tokens = max(
            self.label_fallback.content_token_count([token.norm for token in tokens]),
            1,
        )
        abbreviations = detect_parenthetical_abbreviations(text)
        candidates: dict[tuple[str, int, int], dict] = {}
        max_len = min(self.label_fallback.max_tokens, len(tokens))
        for token_length in range(max_len, 0, -1):
            for start_index in range(0, len(tokens) - token_length + 1):
                span_tokens = tokens[start_index : start_index + token_length]
                span_norm_tokens = [token.norm for token in span_tokens]
                if token_length == 1:
                    token = span_norm_tokens[0]
                    if (
                        token in self.label_fallback.SKIP_SINGLE_TOKENS
                        or (
                            len(token) < 5
                            and token not in self.label_fallback.ALLOW_SHORT_SINGLE_TOKENS
                            and token not in abbreviations
                        )
                    ):
                        continue
                span_norm = " ".join(span_norm_tokens)
                if span_norm in self.label_fallback.SKIP_SPANS:
                    continue
                span_content_tokens = self.label_fallback.content_token_count(span_norm_tokens)
                if span_content_tokens <= 0:
                    continue
                lookup_norms = list(self.label_fallback.lookup_norms_for_span(span_norm))
                abbreviation_expansion = abbreviations.get(span_norm, "")
                if abbreviation_expansion:
                    lookup_norms.extend(self.label_fallback.lookup_norms_for_span(abbreviation_expansion))
                lookup_norms = list(dict.fromkeys(norm for norm in lookup_norms if norm))
                span_start = span_tokens[0].start
                span_end = span_tokens[-1].end
                surface = text[span_start:span_end]
                for lookup_norm in lookup_norms:
                    rows = self.entity_mention_rows_for_lookup(
                        lookup_norm,
                        query_norm=query_norm,
                    )
                    if not rows:
                        continue
                    unique_cuis = {row["cui"] for row in rows if row.get("cui")}
                    lexical_variant = lookup_norm != span_norm
                    for row in rows:
                        candidate = self.entity_mention_from_row(
                            row,
                            text=text,
                            surface=surface,
                            span_norm=span_norm,
                            lookup_norm=lookup_norm,
                            start=span_start,
                            end=span_end,
                            token_count=token_length,
                            query_content_tokens=query_content_tokens,
                            span_content_tokens=span_content_tokens,
                            unique_cui_count=len(unique_cuis),
                            lexical_variant=lexical_variant,
                            abbreviation_expansion=abbreviation_expansion,
                            return_code_sabs=return_code_sabs,
                        )
                        if not candidate:
                            continue
                        key = (candidate["cui"], span_start, span_end)
                        current = candidates.get(key)
                        if current is None or entity_mention_priority(candidate) > entity_mention_priority(current):
                            candidates[key] = candidate
        return suppress_nested_entity_mentions(list(candidates.values()), limit=limit)

    def entity_mention_rows_for_lookup(self, lookup_norm: str, *, query_norm: str) -> list[dict]:
        rows: list[dict] = []
        if self.label_fallback.paths:
            for index in self.label_fallback.indexes():
                for row in index.lookup(lookup_norm, limit=self.label_fallback.rows_per_span):
                    rows.append(
                        {
                            "cui": row["cui"],
                            "label": row["label"],
                            "sab": row["sab"],
                            "tty": row["tty"],
                            "ispref": row["ispref"],
                            "source": "umls_label",
                            "doc_id": f"{row['cui']}:umls_label",
                        }
                    )
        for row in getattr(self, "extension_label_rows_by_norm", {}).get(lookup_norm, []):
            rows.append(
                {
                    "cui": row["cui"],
                    "label": row["label"],
                    "sab": row.get("sab") or "",
                    "tty": row.get("tty") or "",
                    "ispref": row.get("ispref") or "N",
                    "source": "extension_label",
                    "doc_id": row.get("doc_id") or f"{row['cui']}:extension_label",
                }
            )
        for row in getattr(self, "active_label_rows_by_norm", {}).get(lookup_norm, []):
            if active_label_row_matches_query_context(row, query_norm):
                rows.append(dict(row))
        return rows

    def entity_mention_from_row(
        self,
        row: dict,
        *,
        text: str,
        surface: str,
        span_norm: str,
        lookup_norm: str,
        start: int,
        end: int,
        token_count: int,
        query_content_tokens: int,
        span_content_tokens: int,
        unique_cui_count: int,
        lexical_variant: bool,
        abbreviation_expansion: str,
        return_code_sabs: object = None,
    ) -> dict:
        cui = str(row.get("cui") or "").strip().upper()
        label = str(row.get("label") or "").strip()
        if not cui or not label:
            return {}
        score = self.label_fallback.label_score(
            token_count=token_count,
            query_content_tokens=query_content_tokens,
            span_content_tokens=span_content_tokens,
            unique_cui_count=unique_cui_count,
            is_preferred=str(row.get("ispref") or "") == "Y",
            lexical_variant=lexical_variant,
        )
        label_hit = {
            "doc_id": row.get("doc_id") or f"{cui}:umls_label",
            "cui": cui,
            "view": row.get("source") or "umls_label",
            "score": score,
            "labels": [label],
            "sources": [row.get("source") or "umls_label"],
            "source": row.get("source") or "umls_label",
            "evidence_count": 0,
            "match_type": "umls_label",
            "matched_label": label,
            "matched_query_span": surface,
            "matched_lookup_norm": lookup_norm,
            "matched_sab": row.get("sab") or "",
            "matched_tty": row.get("tty") or "",
            "matched_ispref": row.get("ispref") or "",
            "text": "",
            "evidence_items": [],
        }
        hydrated = self.hydrate_label_hit(label_hit)
        if not hydrated:
            return {}
        if should_suppress_label_fallback_hit(hydrated):
            return {}
        if temporal_word_chemical_mention_false_positive(hydrated):
            return {}
        labels = [str(label or "") for label in hydrated.get("labels") or []]
        assertion = assertion_context_for_hit(query=text, labels=labels, hit=hydrated)
        mention = {
            "mention_id": "",
            "start": int(start),
            "end": int(end),
            "text": surface,
            "normalized_text": span_norm,
            "cui": cui,
            "name": hydrated.get("name") or label,
            "matched_label": hydrated.get("matched_label") or label,
            "matched_lookup_norm": lookup_norm,
            "matched_sab": row.get("sab") or "",
            "matched_tty": row.get("tty") or "",
            "matched_ispref": row.get("ispref") or "",
            "match_source": row.get("source") or "umls_label",
            "match_type": "dictionary_mention",
            "score": round(float(score), 6),
            "assertion": assertion,
            "semantic_types": list(hydrated.get("semantic_types") or []),
            "semantic_group": hydrated.get("semantic_group") or "",
            "semantic_group_label": hydrated.get("semantic_group_label") or "",
            "sentence_index": sentence_index_for_offset(text, start),
            "section": section_for_offset(text, start),
            "context": context_window(text, start, end),
        }
        if abbreviation_expansion:
            mention["abbreviation_expansion"] = abbreviation_expansion
        mention.update(self.source_code_fields_for_cui(cui, sabs=return_code_sabs))
        return mention

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
        for rank_index, hit in enumerate(rankable_hits):
            cui = str(hit.get("cui") or "")
            if not cui:
                continue
            label_tokens = label_tokens_for_hit(hit)
            label_matched = positive_specific_tokens & label_tokens
            source_group = semantic_group_from_types(list(hit.get("semantic_types") or []))
            hit_category = SEMANTIC_GROUP_RELATION_CATEGORIES.get(source_group, "")
            hit_role_match = relation_category_matches_query_role(hit_category, query_set)
            has_direct_relation_reason = label_matched or hit_role_match or has_role_intent
            allow_broad_relation_scan = (
                len(positive_specific_tokens) >= 2
                and rank_index < MRREL_BROAD_QUERY_SCAN_LIMIT
            )
            if not (has_direct_relation_reason or allow_broad_relation_scan):
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

    def merge_label_fallback(
        self,
        query: str,
        hits: list[dict],
        *,
        top_k: int,
        include_extension_labels: bool = True,
        include_active_label_supplement: bool = True,
        include_related_anchor_candidates: bool = True,
        strip_evidence_before_rank: bool = False,
    ) -> list[dict]:
        has_extension_labels = bool(
            include_extension_labels and getattr(self, "extension_label_rows_by_norm", {})
        )
        has_active_label_supplement = bool(
            include_active_label_supplement and getattr(self, "active_label_rows_by_norm", {})
        )
        if (
            not self.label_fallback.paths
            and not self.definition_index
            and not has_extension_labels
            and not has_active_label_supplement
        ):
            hits = self.merge_code_fallback(query, hits, top_k=top_k)
            if strip_evidence_before_rank:
                hits = self.strip_evidence_from_umls_hits(hits)
            self.attach_mrrel_rank_signals(query, hits, candidate_limit=self.mrrel_rank_candidate_limit(top_k))
            return rank_hits(query, hits, top_k=top_k)
        best_by_cui = {hit.get("cui", ""): hit for hit in hits if hit.get("cui")}
        fallback_queries = clinical_query_variants(query)
        label_hits = []
        if self.label_fallback.paths:
            label_limit = self.capped_fallback_limit(
                max(top_k * 12, 100),
                "label_fallback_limit",
            )
            for index, fallback_query in enumerate(fallback_queries):
                limit = label_limit if index == 0 else min(label_limit, 80)
                label_hits.extend(self.label_fallback.search(fallback_query, limit=limit))
                for anchor_query in label_fallback_anchor_queries(fallback_query):
                    label_hits.extend(self.label_fallback.search(anchor_query, limit=8))
        extension_limit = self.capped_fallback_limit(max(top_k * 8, 60), "label_fallback_limit")
        active_limit = self.capped_fallback_limit(max(top_k * 4, 40), "label_fallback_limit")
        for index, fallback_query in enumerate(fallback_queries):
            label_hits.extend(
                self.extension_label_fallback_hits(
                    fallback_query,
                    limit=extension_limit if index == 0 else min(extension_limit, 60),
                )
            )
            label_hits.extend(
                self.active_label_supplement_hits(
                    fallback_query,
                    limit=active_limit if index == 0 else min(active_limit, 40),
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
            hydrated_score = float(hydrated.get("score") or 0.0)
            if current is not None and "active_label_supplement" in hydrated_sources:
                current["label_fallback_score"] = max(
                    float(current.get("label_fallback_score") or 0.0),
                    hydrated_score,
                )
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
                current["label_fallback_score"] = max(
                    float(current.get("label_fallback_score") or 0.0),
                    hydrated_score,
                )
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
                current["label_fallback_score"] = max(
                    float(current.get("label_fallback_score") or 0.0),
                    hydrated_score,
                )
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
        ranking_query = fallback_queries[-1] if fallback_queries else query
        hits = self.merge_code_fallback(query, list(best_by_cui.values()), top_k=top_k)
        best_by_cui = {str(hit.get("cui") or ""): hit for hit in hits if hit.get("cui")}
        self.merge_rankable_linked_label_candidates(ranking_query, best_by_cui, top_k=top_k)
        hits = list(best_by_cui.values())
        if include_related_anchor_candidates:
            hits = self.merge_related_anchor_candidates(ranking_query, hits, top_k=top_k)
        if strip_evidence_before_rank:
            hits = self.strip_evidence_from_umls_hits(hits)
        self.attach_mrrel_rank_signals(ranking_query, hits, candidate_limit=self.mrrel_rank_candidate_limit(top_k))
        return rank_hits(ranking_query, hits, top_k=top_k)

    def merge_code_fallback(self, query: str, hits: list[dict], *, top_k: int) -> list[dict]:
        code_fallback = getattr(self, "code_fallback_hits_for_query", None)
        if not callable(code_fallback):
            return hits
        code_hits = code_fallback(query, limit=max(top_k * 2, 10))
        if not code_hits:
            return hits
        passthrough = [hit for hit in hits if not hit.get("cui")]
        best_by_cui = {str(hit.get("cui") or ""): hit for hit in hits if hit.get("cui")}
        for code_hit in code_hits:
            cui = str(code_hit.get("cui") or "")
            if not cui:
                continue
            current = best_by_cui.get(cui)
            if current is None:
                best_by_cui[cui] = code_hit
                continue
            current["sources"] = merge_labels(
                list(code_hit.get("sources") or []),
                list(current.get("sources") or []),
            )
            current["mappings"] = list(code_hit.get("mappings") or current.get("mappings") or [])
            current["codes"] = list(code_hit.get("codes") or current.get("codes") or [])
            current["source_asserted_codes"] = list(
                code_hit.get("source_asserted_codes")
                or current.get("source_asserted_codes")
                or current.get("codes")
                or []
            )
            current["matched_code_input"] = code_hit.get("matched_code_input") or code_hit.get("matched_input") or ""
            current["code_match_type"] = code_hit.get("code_match_type") or code_hit.get("match_type") or "code"
            if current.get("match_type") not in {"umls_label", "umls_definition"}:
                current["match_type"] = code_hit.get("match_type") or current.get("match_type") or "code"
                current["matched_input"] = code_hit.get("matched_input") or current.get("matched_input") or ""
                current["score"] = max(float(current.get("score") or 0.0), float(code_hit.get("score") or 0.0))
        return [*best_by_cui.values(), *passthrough]

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
