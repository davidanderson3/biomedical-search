from __future__ import annotations

import re
import time

from qe_evidence_vectors.code_index import (
    CODE_IDENTIFIER_SYSTEMS,
    UMLS_IDENTIFIER_SYSTEMS,
    infer_umls_identifier_type,
    is_cui,
    looks_like_code,
    normalize_sab,
    parse_system_code,
)
from qe_evidence_vectors.search_semantic_buckets import normalize_semantic_bucket_filter
from qe_evidence_vectors.search_semantics import semantic_group_metadata
from qe_evidence_vectors.search_tokens import content_tokens
from qe_evidence_vectors.search_utils import (
    concept_display_name,
    merge_definition_lists,
    merge_labels,
    sentence_bounded_evidence_text,
    source_mix_from_evidence_items,
)
from qe_evidence_vectors.text import normalized_key


DEFAULT_RETURN_CODE_SABS = ("SNOMEDCT_US", "RXNORM", "ICD10CM", "LNC")
ALL_RETURN_CODE_SABS = ("*",)
NO_RETURN_CODE_SABS: tuple[str, ...] = ()
RETURN_CODE_DEFAULT_TOKENS = {"", "default", "defaults", "standard", "source", "source_asserted"}
RETURN_CODE_NONE_TOKENS = {"0", "false", "none", "no", "off", "hide"}
RETURN_CODE_ALL_TOKENS = {"*", "all", "any"}
EMBEDDED_CODE_SYSTEMS = {
    "ICD10CM",
    "ICD10PCS",
    "ICD9CM",
    "LNC",
    "RXNORM",
    "SNOMEDCT_US",
}
EMBEDDED_SYSTEM_CODE_RE = re.compile(
    r"(?<!\S)([A-Za-z][A-Za-z0-9_]{1,31}):([A-Za-z0-9][A-Za-z0-9_.\-/]{0,31})(?!\S)"
)
EMBEDDED_CODE_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-/]*")
EMBEDDED_BARE_CODE_RE = re.compile(
    r"^(?:[A-Za-z]\d[A-Za-z0-9](?:\.[A-Za-z0-9]{1,5})?|\d{1,5}-\d)$",
    re.IGNORECASE,
)
EMBEDDED_CODE_CONTEXT_TOKENS = {"code", "codes", "sourcecode", "source_code"}
EMBEDDED_CODE_LOOKUP_CONTEXT_TOKENS = EMBEDDED_CODE_CONTEXT_TOKENS | {
    "billing",
    "cm",
    "concept",
    "diagnosis",
    "diagnostic",
    "dx",
    "icd",
    "icd9",
    "icd10",
    "lnc",
    "loinc",
    "medical",
    "pcs",
    "rxnorm",
    "snomed",
    "source",
    "system",
}
SOURCE_CODE_SYSTEM_NAMES = {
    "ICD10CM": "ICD-10-CM",
    "ICD10PCS": "ICD-10-PCS",
    "LNC": "LOINC",
    "RXNORM": "RxNorm",
    "SNOMEDCT_US": "SNOMED CT US",
}
EVIDENCE_QUERY_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "by",
    "for",
    "from",
    "had",
    "has",
    "have",
    "in",
    "is",
    "of",
    "on",
    "or",
    "patient",
    "patients",
    "reported",
    "showed",
    "the",
    "to",
    "was",
    "were",
    "with",
}


def evidence_query_terms(query: str) -> set[str]:
    return {
        token
        for token in content_tokens(query)
        if token not in EVIDENCE_QUERY_STOPWORDS and len(token) >= 3
    }


def evidence_item_query_score(item: dict, query_terms: set[str]) -> tuple[int, float, float]:
    if not query_terms:
        return (0, 0.0, float(item.get("weight") or 0.0))
    item_terms = set(content_tokens(str(item.get("text") or "")))
    overlap = query_terms & item_terms
    return (
        len(overlap),
        len(overlap) / max(len(query_terms), 1),
        float(item.get("weight") or 0.0),
    )


def rank_evidence_items_for_query(items: list[dict], query: str) -> list[dict]:
    query_terms = evidence_query_terms(query)
    if not query_terms:
        return list(items)
    return [
        item
        for _score, _index, item in sorted(
            (
                (evidence_item_query_score(item, query_terms), index, item)
                for index, item in enumerate(items)
            ),
            key=lambda row: (-row[0][0], -row[0][1], -row[0][2], row[1]),
        )
    ]


def normalize_return_code_sabs(value: object = None) -> tuple[str, ...]:
    if value is None:
        return DEFAULT_RETURN_CODE_SABS
    if value == NO_RETURN_CODE_SABS:
        return NO_RETURN_CODE_SABS
    if isinstance(value, str):
        raw_values = re.split(r"[,|]", value)
    else:
        try:
            raw_values = list(value)
        except TypeError:
            raw_values = [value]
    tokens = [str(item or "").strip() for item in raw_values]
    if not tokens:
        return DEFAULT_RETURN_CODE_SABS
    normalized: list[str] = []
    for token in tokens:
        token_key = token.strip().lower()
        if token_key in RETURN_CODE_DEFAULT_TOKENS:
            return DEFAULT_RETURN_CODE_SABS
        if token_key in RETURN_CODE_NONE_TOKENS:
            return NO_RETURN_CODE_SABS
        if token_key in RETURN_CODE_ALL_TOKENS:
            return ALL_RETURN_CODE_SABS
        sab = normalize_sab(token)
        if sab and sab not in normalized:
            normalized.append(sab)
    return tuple(normalized) if normalized else DEFAULT_RETURN_CODE_SABS


class SearchHydrationMixin:
    def concept_has_active_atoms(self, cui: str) -> bool:
        cui = str(cui or "").strip().upper()
        if not cui:
            return False
        if not is_cui(cui):
            return True
        if cui in getattr(self, "extension_semantic_types_by_cui", {}):
            return True
        if cui in getattr(self, "active_label_semantic_types_by_cui", {}):
            return True
        if not self.code_index:
            return True
        return self.code_index.has_active_cui(cui)

    def display_label_for_cui(self, cui: str, labels: list[str]) -> str:
        cui = str(cui or "").strip().upper()
        if not self.concept_has_active_atoms(cui):
            return ""
        override = str(getattr(self, "display_name_overrides", {}).get(cui, "") or "").strip()
        if override:
            return override
        preferred = self.preferred_label_for_cui(cui)
        if preferred:
            return preferred
        cui_norm = normalized_key(cui)
        filtered_labels = [
            str(label).strip()
            for label in labels
            if str(label).strip()
            and not is_cui(str(label).strip())
            and normalized_key(str(label)) != cui_norm
        ]
        return concept_display_name(filtered_labels, fallback="")

    def concept_is_displayable(self, cui: str, labels: list[str] | None = None) -> bool:
        return bool(self.display_label_for_cui(cui, list(labels or [])))

    def hit_from_record(
        self,
        record: SearchRecord,
        *,
        score: float,
        hydrate_details: bool = True,
        include_codes: bool = True,
        evidence_query: str = "",
    ) -> dict:
        labels = self.labels_for_cui(record.cui, record.labels)
        name = self.display_label_for_cui(record.cui, labels)
        evidence_items = (
            self.evidence_items_for_record(record, query=evidence_query)
            if hydrate_details
            else [
                {
                    **dict(item),
                    "text": sentence_bounded_evidence_text(str(item.get("text") or "")),
                }
                for item in record.evidence_items
            ]
        )
        semantic_types = self.semantic_types_for_cui(record.cui)
        definitions = self.definitions_for_cui(record.cui) if hydrate_details else []
        images = self.images_for_cui(record.cui) if hydrate_details else []
        code_fields = self.source_code_fields_for_cui(record.cui) if include_codes else {}
        return {
            "doc_id": record.doc_id,
            "cui": record.cui,
            "name": name,
            "view": record.view,
            "score": score,
            "labels": labels,
            "sources": record.sources,
            "evidence_count": record.evidence_count,
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
            "source_mix": source_mix_from_evidence_items(
                evidence_items,
                declared_sources=record.sources,
                evidence_count=record.evidence_count,
            ),
            "semantic_types": semantic_types,
            **semantic_group_metadata(semantic_types),
            "definitions": definitions,
            "images": images,
            **code_fields,
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

    def return_code_mappings_for_cui(
        self,
        cui: str,
        *,
        sabs: object = None,
        limit_per_sab: int = 2,
    ) -> list[dict]:
        cui = str(cui or "").strip().upper()
        if not cui or not self.code_index:
            return []
        normalized_sabs = normalize_return_code_sabs(sabs)
        if not normalized_sabs:
            return []
        key = (cui, normalized_sabs, int(limit_per_sab))
        if not hasattr(self, "return_code_mappings_cache"):
            self.return_code_mappings_cache = {}
        cached = self.return_code_mappings_cache.get(key)
        if cached is not None:
            return [dict(row) for row in cached]
        rows = []
        seen = set()
        if normalized_sabs == ALL_RETURN_CODE_SABS:
            source_rows = self.mappings_for_cui(cui, sabs=None, limit=max(limit_per_sab * 12, 50))
            for row in source_rows:
                system = str(row.get("sab") or "").strip()
                code = str(row.get("code") or "").strip()
                if not system or not code or code.upper() == "NOCODE":
                    continue
                row_key = (system, code.upper())
                if row_key in seen:
                    continue
                seen.add(row_key)
                rows.append(dict(row))
        else:
            for sab in normalized_sabs:
                for row in self.mappings_for_cui(cui, sabs=[sab], limit=limit_per_sab):
                    system = str(row.get("sab") or "").strip()
                    code = str(row.get("code") or "").strip()
                    if not system or not code or code.upper() == "NOCODE":
                        continue
                    row_key = (system, code.upper())
                    if row_key in seen:
                        continue
                    seen.add(row_key)
                    rows.append(dict(row))
        self.return_code_mappings_cache[key] = [dict(row) for row in rows]
        return [dict(row) for row in rows]

    def source_code_fields_for_cui(self, cui: str, *, sabs: object = None) -> dict:
        codes = self.return_codes_for_cui(cui, sabs=sabs)
        return {
            "codes": codes,
            "source_asserted_codes": [dict(row) for row in codes],
        }

    def return_codes_for_cui(self, cui: str, *, sabs: object = None) -> list[dict]:
        rows = []
        for row in self.return_code_mappings_for_cui(cui, sabs=sabs):
            system = row.get("sab") or ""
            code = row.get("code") or ""
            rows.append(
                {
                    "system": system,
                    "system_name": SOURCE_CODE_SYSTEM_NAMES.get(system, system),
                    "sab": system,
                    "code": code,
                    "source_asserted_code": code,
                    "source_cui": row.get("scui") or "",
                    "source_dui": row.get("sdui") or "",
                    "scui": row.get("scui") or "",
                    "sdui": row.get("sdui") or "",
                    "tty": row.get("tty") or "",
                    "label": row.get("label") or "",
                    "ispref": row.get("ispref") or "",
                }
            )
        return rows

    def apply_source_code_selection(self, hits: list[dict], *, sabs: object = None) -> list[dict]:
        selected_sabs = normalize_return_code_sabs(sabs)
        for hit in hits:
            cui = str(hit.get("cui") or "")
            if not cui:
                continue
            hit.update(self.source_code_fields_for_cui(cui, sabs=selected_sabs))
        return hits

    def preferred_label_for_cui(self, cui: str) -> str:
        if not self.code_index or not cui:
            return ""
        cui = cui.strip().upper()
        cached = self.preferred_label_cache.get(cui)
        if cached is not None:
            return cached
        if self.is_clinical_attribute_cui(cui):
            loinc_lc_label = self.loinc_lc_label_for_cui(cui)
            if loinc_lc_label:
                self.preferred_label_cache[cui] = loinc_lc_label
                return loinc_lc_label
        label = self.code_index.preferred_label(cui)
        self.preferred_label_cache[cui] = label
        return label

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
        cui = cui.strip().upper()
        cached = self.semantic_types_cache.get(cui)
        if cached is not None:
            return [dict(row) for row in cached]
        supplement_rows = list(
            getattr(self, "active_label_semantic_types_by_cui", {}).get(cui, [])
        )
        if self.semantic_type_index:
            rows = self.semantic_type_index.lookup(cui)
            if rows:
                if not supplement_rows:
                    self.semantic_types_cache[cui] = [dict(row) for row in rows]
                    return [dict(row) for row in rows]
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
                self.semantic_types_cache[cui] = [dict(row) for row in merged]
                return [dict(row) for row in merged]
        if supplement_rows:
            self.semantic_types_cache[cui] = [dict(row) for row in supplement_rows]
            return [dict(row) for row in supplement_rows]
        rows = list(getattr(self, "extension_semantic_types_by_cui", {}).get(cui, []))
        self.semantic_types_cache[cui] = [dict(row) for row in rows]
        return [dict(row) for row in rows]

    def definitions_for_cui(self, cui: str, *, limit: int = 3) -> list[dict]:
        if not self.definition_index or not cui:
            return []
        key = (cui.strip().upper(), int(limit))
        cached = self.definitions_cache.get(key)
        if cached is not None:
            return [dict(row) for row in cached]
        rows = self.definition_index.lookup(key[0], limit=limit)
        self.definitions_cache[key] = [dict(row) for row in rows]
        return [dict(row) for row in rows]

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
        query: str = "",
        return_code_sabs: object = None,
        search_scope: str = "umls_evidence",
    ) -> dict:
        doc_id = str(doc_id or "").strip()
        cui = str(cui or "").strip().upper()
        search_scope = str(search_scope or "umls_evidence").strip().lower()
        if search_scope == "umls":
            include_related = False
        record = self.records_by_doc_id.get(doc_id) if doc_id else None
        if not record and cui:
            record = self.best_record_for_cui(cui)
        if record:
            hit = self.hit_from_record(record, score=0.0, evidence_query=query)
        elif cui:
            labels = self.labels_for_cui(cui, [])
            name = self.display_label_for_cui(cui, labels)
            if not name:
                return {"error": "concept has no active display label", "doc_id": doc_id, "cui": cui}
            semantic_types = self.semantic_types_for_cui(cui)
            hit = {
                "doc_id": doc_id or f"{cui}:detail",
                "cui": cui,
                "name": name,
                "view": "detail",
                "score": 0.0,
                "labels": labels,
                "sources": [],
                "evidence_count": 0,
                "source_mix": source_mix_from_evidence_items([], declared_sources=[], evidence_count=0),
                "semantic_types": semantic_types,
                **semantic_group_metadata(semantic_types),
                "definitions": self.definitions_for_cui(cui),
                "images": self.images_for_cui(cui),
                **self.source_code_fields_for_cui(cui, sabs=return_code_sabs),
                "text": "",
                "evidence_items": [],
                "related_concepts": [],
            }
        else:
            return {"error": "missing doc_id or cui"}
        hit["mappings"] = self.mappings_for_cui(str(hit.get("cui") or ""), limit=50)
        self.apply_source_code_selection([hit], sabs=return_code_sabs)
        if include_related:
            self.attach_related_concepts([hit])
        if search_scope == "umls":
            self.strip_evidence_from_umls_hits([hit])
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
        definitions: list[dict] | None = None,
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
        name = self.display_label_for_cui(cui, deduped_labels)
        if not name:
            return {}
        return {
            "cui": cui,
            "name": name,
            "score": score,
            "source": source,
            "matched": matched,
            "label": name,
            "labels": deduped_labels[:8],
            "has_evidence": bool(record),
            "evidence_count": record.evidence_count if record else 0,
            "best_doc_id": record.doc_id if record else "",
            "best_view": record.view if record else "",
            "semantic_types": self.semantic_types_for_cui(cui),
            "definitions": merge_definition_lists(
                list(definitions or []),
                self.definitions_for_cui(cui),
            ),
            "images": self.images_for_cui(cui),
            "mappings": resolved_mappings[:25],
            **self.source_code_fields_for_cui(cui),
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
            candidate = self.candidate_from_cui(
                cui,
                score=1.3 if source == "system_code" else 1.2,
                source=source,
                matched=matched,
                mappings=mappings,
                label=str(best.get("label") or ""),
            )
            if candidate:
                candidates.append(candidate)
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

    def candidates_from_semantic_identifier_rows(
        self,
        rows: list[dict],
        *,
        source: str,
        matched: str,
        limit: int,
    ) -> list[dict]:
        candidates = []
        seen_cuis = set()
        for row in rows:
            cui = str(row.get("cui") or "").strip().upper()
            if not cui or cui in seen_cuis:
                continue
            seen_cuis.add(cui)
            label = str(row.get("name") or "").strip()
            candidate = self.candidate_from_cui(
                cui,
                score=1.15,
                source=source,
                matched=matched,
                label=label,
            )
            if not candidate:
                continue
            candidate["matched_identifier_type"] = str(row.get("matched_identifier_type") or source).upper()
            candidate["matched_identifier"] = str(row.get("matched_identifier") or matched).strip()
            candidates.append(candidate)
            if len(candidates) >= limit:
                break
        return sorted(
            candidates,
            key=lambda item: (
                0 if item.get("has_evidence") else 1,
                -int(item.get("evidence_count") or 0),
                item.get("label") or "",
            ),
        )[:limit]

    def candidates_from_relation_identifier_rows(
        self,
        rows: list[dict],
        *,
        matched: str,
        limit: int,
    ) -> list[dict]:
        candidates = []
        seen_cuis = set()
        for row in rows:
            for role, cui_key in (("relation_source", "source_cui"), ("relation_target", "target_cui")):
                cui = str(row.get(cui_key) or "").strip().upper()
                if not cui or cui in seen_cuis:
                    continue
                seen_cuis.add(cui)
                candidate = self.candidate_from_cui(
                    cui,
                    score=1.1,
                    source="rui",
                    matched=matched,
                    label=str(row.get("label") or ""),
                )
                if not candidate:
                    continue
                candidate["matched_identifier_type"] = "RUI"
                candidate["matched_identifier"] = matched
                candidate["relation_identifier_role"] = role
                candidates.append(candidate)
                if len(candidates) >= limit:
                    return candidates
        return candidates

    def candidates_from_definition_identifier_rows(
        self,
        rows: list[dict],
        *,
        source: str,
        matched: str,
        limit: int,
    ) -> list[dict]:
        candidates = []
        seen_cuis = set()
        for row in rows:
            cui = str(row.get("cui") or "").strip().upper()
            if not cui or cui in seen_cuis:
                continue
            seen_cuis.add(cui)
            candidate = self.candidate_from_cui(
                cui,
                score=1.1,
                source=source,
                matched=matched,
                definitions=[row],
            )
            if not candidate:
                continue
            candidate["matched_identifier_type"] = str(row.get("matched_identifier_type") or source).upper()
            candidate["matched_identifier"] = str(row.get("matched_identifier") or matched).strip()
            candidates.append(candidate)
            if len(candidates) >= limit:
                break
        return candidates

    def embedded_code_queries(self, query: str) -> list[tuple[str, str | None, str]]:
        text = str(query or "").strip()
        if not text:
            return []
        seen: set[tuple[str, str | None, str]] = set()
        matches: list[tuple[str, str | None, str]] = []

        def add(code: str, *, sab: str | None = None, matched: str = "") -> None:
            normalized_code = str(code or "").strip().strip(".,;()[]{}")
            if not normalized_code or not looks_like_code(normalized_code):
                return
            normalized_sab = normalize_sab(sab or "") if sab else None
            if normalized_sab and normalized_sab not in EMBEDDED_CODE_SYSTEMS:
                return
            key = (normalized_code.lower(), normalized_sab, matched or normalized_code)
            if key in seen:
                return
            seen.add(key)
            matches.append((normalized_code, normalized_sab, matched or normalized_code))

        for match in EMBEDDED_SYSTEM_CODE_RE.finditer(text):
            sab = normalize_sab(match.group(1))
            if sab in EMBEDDED_CODE_SYSTEMS:
                add(match.group(2), sab=sab, matched=f"{sab}:{match.group(2).strip()}")

        tokens = [match.group(0) for match in EMBEDDED_CODE_TOKEN_RE.finditer(text)]
        for index, token in enumerate(tokens):
            matched_system = False
            max_width = min(4, len(tokens) - index - 1)
            for width in range(max_width, 0, -1):
                system_text = " ".join(tokens[index : index + width])
                sab = normalize_sab(system_text)
                next_token = tokens[index + width] if index + width < len(tokens) else ""
                if sab in EMBEDDED_CODE_SYSTEMS and next_token:
                    add(next_token, sab=sab, matched=f"{sab}:{next_token}")
                    matched_system = True
                    break
            if matched_system:
                continue
            previous = normalize_sab(tokens[index - 1]) if index > 0 else ""
            previous_raw = tokens[index - 1].lower() if index > 0 else ""
            if EMBEDDED_BARE_CODE_RE.match(token):
                add(token, matched=token)
                continue
            if previous in EMBEDDED_CODE_SYSTEMS or previous_raw in EMBEDDED_CODE_CONTEXT_TOKENS:
                add(token, matched=token)
        return matches

    def code_fallback_hits_for_query(self, query: str, *, limit: int = 10) -> list[dict]:
        if not self.code_index:
            return []
        hits: list[dict] = []
        seen_cuis: set[str] = set()
        for code, sab, matched in self.embedded_code_queries(query):
            rows = self.code_index.lookup_code(
                code,
                sab=sab,
                limit=max(limit * 5, 25),
            )
            if not rows:
                continue
            source = "system_code" if sab else "code"
            candidates = self.candidates_from_mappings(
                rows,
                source=source,
                matched=matched,
                limit=limit,
            )
            for candidate in candidates:
                cui = str(candidate.get("cui") or "")
                if not cui or cui in seen_cuis:
                    continue
                hit = self.hit_from_candidate(candidate)
                if not hit:
                    continue
                hit["matched_code_input"] = matched
                hit["code_match_type"] = source
                seen_cuis.add(cui)
                hits.append(hit)
                if len(hits) >= limit:
                    return hits
        return hits

    def resolve_embedded_code_lookup(self, query: str, *, limit: int = 10) -> dict | None:
        if not self.code_index:
            return None
        embedded_queries = self.embedded_code_queries(query)
        if not embedded_queries or not self.query_is_embedded_code_lookup_context(query):
            return None
        candidates: list[dict] = []
        seen_cuis: set[str] = set()
        input_type = "system_code" if any(sab for _, sab, _ in embedded_queries) else "code"
        for code, sab, matched in embedded_queries:
            rows = self.code_index.lookup_code(
                code,
                sab=sab,
                limit=max(limit * 5, 25),
            )
            if not rows:
                continue
            source = "system_code" if sab else "code"
            for candidate in self.candidates_from_mappings(
                rows,
                source=source,
                matched=matched,
                limit=limit,
            ):
                cui = str(candidate.get("cui") or "")
                if not cui or cui in seen_cuis:
                    continue
                seen_cuis.add(cui)
                candidates.append(candidate)
                if len(candidates) >= limit:
                    return {
                        "query": query,
                        "input_type": f"embedded_{input_type}",
                        "candidates": candidates,
                    }
        if not candidates:
            return None
        return {
            "query": query,
            "input_type": f"embedded_{input_type}",
            "candidates": candidates,
        }

    def query_is_embedded_code_lookup_context(self, query: str) -> bool:
        tokens = [match.group(0) for match in EMBEDDED_CODE_TOKEN_RE.finditer(str(query or ""))]
        if not tokens:
            return False
        saw_code = False
        for token in tokens:
            token_text = str(token or "").strip()
            token_lower = token_text.lower()
            if looks_like_code(token_text):
                saw_code = True
                continue
            if normalize_sab(token_text) in EMBEDDED_CODE_SYSTEMS:
                continue
            if token_lower in EMBEDDED_CODE_LOOKUP_CONTEXT_TOKENS:
                continue
            return False
        return saw_code

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
                    if not broadened_candidate:
                        continue
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
            candidate = self.candidate_from_cui(cui, score=1.4, source="cui", matched=cui)
            return {
                "query": query,
                "input_type": "cui",
                "candidates": [candidate] if candidate else [],
            }
        parsed_code = parse_system_code(raw_query)
        if parsed_code:
            sab, code = parsed_code
            if sab == "CUI" and is_cui(code):
                cui = code.upper()
                candidate = self.candidate_from_cui(cui, score=1.4, source="cui", matched=cui)
                return {
                    "query": query,
                    "input_type": "cui",
                    "candidates": [candidate] if candidate else [],
                }
            if sab in CODE_IDENTIFIER_SYSTEMS:
                rows = (
                    self.code_index.lookup_identifier(
                        code,
                        identifier_type=sab,
                        limit=max(limit * 5, 25),
                    )
                    if self.code_index
                    else []
                )
                return {
                    "query": query,
                    "input_type": "umls_identifier",
                    "identifier_type": sab,
                    "identifier": code,
                    "candidates": self.candidates_from_mappings(
                        rows,
                        source="umls_identifier",
                        matched=f"{sab}:{code}",
                        limit=limit,
                    ),
                }
            if sab in {"TUI", "ATUI"}:
                rows = (
                    self.semantic_type_index.lookup_identifier(
                        code,
                        identifier_type=sab,
                        limit=max(limit * 5, 25),
                    )
                    if self.semantic_type_index
                    else []
                )
                definition_rows = []
                if not rows and sab == "ATUI" and self.definition_index:
                    definition_rows = self.definition_index.lookup_identifier(
                        code,
                        identifier_type=sab,
                        limit=max(limit * 5, 25),
                    )
                return {
                    "query": query,
                    "input_type": "semantic_type_identifier",
                    "identifier_type": sab,
                    "identifier": code,
                    "candidates": (
                        self.candidates_from_semantic_identifier_rows(
                            rows,
                            source=sab.lower(),
                            matched=f"{sab}:{code}",
                            limit=limit,
                        )
                        if rows
                        else self.candidates_from_definition_identifier_rows(
                            definition_rows,
                            source=sab.lower(),
                            matched=f"{sab}:{code}",
                            limit=limit,
                        )
                    ),
                }
            if sab == "RUI":
                rows = (
                    self.relation_index.lookup_identifier(
                        code,
                        identifier_type=sab,
                        limit=max(limit * 2, 10),
                    )
                    if self.relation_index
                    else []
                )
                return {
                    "query": query,
                    "input_type": "relation_identifier",
                    "identifier_type": sab,
                    "identifier": code,
                    "candidates": self.candidates_from_relation_identifier_rows(
                        rows,
                        matched=f"{sab}:{code}",
                        limit=limit,
                    ),
                }
            if sab in UMLS_IDENTIFIER_SYSTEMS:
                return {
                    "query": query,
                    "input_type": "unsupported_identifier",
                    "identifier_type": sab,
                    "identifier": code,
                    "candidates": [],
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
        identifier_type = infer_umls_identifier_type(raw_query)
        if identifier_type in CODE_IDENTIFIER_SYSTEMS:
            rows = (
                self.code_index.lookup_identifier(
                    raw_query,
                    identifier_type=identifier_type,
                    limit=max(limit * 5, 25),
                )
                if self.code_index
                else []
            )
            return {
                "query": query,
                "input_type": "umls_identifier",
                "identifier_type": identifier_type,
                "identifier": raw_query,
                "candidates": self.candidates_from_mappings(
                    rows,
                    source="umls_identifier",
                    matched=raw_query,
                    limit=limit,
                ),
            }
        if identifier_type in {"TUI", "ATUI"}:
            rows = (
                self.semantic_type_index.lookup_identifier(
                    raw_query,
                    identifier_type=identifier_type,
                    limit=max(limit * 5, 25),
                )
                if self.semantic_type_index
                else []
            )
            definition_rows = []
            if not rows and identifier_type == "ATUI" and self.definition_index:
                definition_rows = self.definition_index.lookup_identifier(
                    raw_query,
                    identifier_type=identifier_type,
                    limit=max(limit * 5, 25),
                )
            return {
                "query": query,
                "input_type": "semantic_type_identifier",
                "identifier_type": identifier_type,
                "identifier": raw_query,
                "candidates": (
                    self.candidates_from_semantic_identifier_rows(
                        rows,
                        source=identifier_type.lower(),
                        matched=raw_query,
                        limit=limit,
                    )
                    if rows
                    else self.candidates_from_definition_identifier_rows(
                        definition_rows,
                        source=identifier_type.lower(),
                        matched=raw_query,
                        limit=limit,
                    )
                ),
            }
        if identifier_type == "RUI":
            rows = (
                self.relation_index.lookup_identifier(
                    raw_query,
                    identifier_type=identifier_type,
                    limit=max(limit * 2, 10),
                )
                if self.relation_index
                else []
            )
            return {
                "query": query,
                "input_type": "relation_identifier",
                "identifier_type": identifier_type,
                "identifier": raw_query,
                "candidates": self.candidates_from_relation_identifier_rows(
                    rows,
                    matched=raw_query,
                    limit=limit,
                ),
            }
        if identifier_type in UMLS_IDENTIFIER_SYSTEMS:
            return {
                "query": query,
                "input_type": "unsupported_identifier",
                "identifier_type": identifier_type,
                "identifier": raw_query,
                "candidates": [],
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
            candidate = self.candidate_from_cui(
                cui,
                score=float(hit.get("score") or 0),
                source="umls_label",
                matched=str(hit.get("matched_query_span") or raw_query),
                label=(hit.get("labels") or [""])[0],
            )
            if candidate:
                label_candidates.append(candidate)
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
            name = self.display_label_for_cui(cui, labels)
            if not name:
                return {}
            definitions = self.definitions_for_cui(cui)
            definition_lines = "\n".join(
                f"- {item.get('source') or 'MRDEF'}: {item.get('definition') or ''}"
                for item in definitions[:3]
            )
            hit = {
                "doc_id": f"{cui}:resolver",
                "cui": cui,
                "name": name,
                "view": "resolver",
                "score": float(candidate.get("score") or 0),
                "labels": labels,
                "sources": [str(candidate.get("source") or "resolver")],
                "evidence_count": 0,
                "source_bundle": str(candidate.get("source") or "resolver"),
                "vector_path": "",
                "vector_row": -1,
                "vector_lineage": {},
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
                **self.source_code_fields_for_cui(cui),
                "related_concepts": [],
            }
        hit["match_type"] = candidate.get("source") or "resolver"
        hit["matched_input"] = candidate.get("matched") or ""
        if candidate.get("matched_identifier_type"):
            hit["matched_identifier_type"] = candidate.get("matched_identifier_type") or ""
            hit["matched_identifier"] = candidate.get("matched_identifier") or hit["matched_input"]
        if hit["match_type"] in {"code", "system_code", "umls_identifier"}:
            hit["matched_code_input"] = hit["matched_input"]
            hit["code_match_type"] = hit["match_type"]
        hit["mappings"] = candidate.get("mappings") or []
        hit["codes"] = candidate.get("codes") or hit.get("codes") or self.return_codes_for_cui(cui)
        hit["source_asserted_codes"] = (
            candidate.get("source_asserted_codes")
            or hit.get("source_asserted_codes")
            or hit["codes"]
        )
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
            name = self.display_label_for_cui(cui, list(hit.get("labels") or []))
            if not name:
                return {}
            hit["name"] = name
        if candidate.get("source") and candidate["source"] not in hit.get("sources", []):
            hit["sources"] = [candidate["source"]] + list(hit.get("sources") or [])
            hit["source_mix"] = source_mix_from_evidence_items(
                list(hit.get("evidence_items") or []),
                declared_sources=list(hit.get("sources") or []),
                evidence_count=int(hit.get("evidence_count") or 0),
            )
        return hit

    def scoring_summary(
        self,
        backend: str,
        *,
        search_mode: str = "balanced",
        search_scope: str = "umls_evidence",
    ) -> dict:
        if backend == "resolver":
            retrieval = "direct CUI/code resolver"
        elif backend == "umls":
            retrieval = "UMLS CUI/code/label lookup with evidence vector retrieval disabled"
        elif backend == "elasticsearch":
            retrieval = "Elasticsearch kNN over concept-document embeddings"
        elif backend == "generic_query_filter":
            retrieval = "audited generic query suppression"
        else:
            retrieval = "local vector scan over concept-document embeddings"
        mode_descriptions = {
            "balanced": "balanced hybrid search",
            "exact": "exact literal label/span search; semantic-only vector hits are filtered out",
            "comprehensive": "comprehensive search with a larger reranking candidate pool",
        }
        scope = str(search_scope or "umls_evidence").strip().lower()
        scope_descriptions = {
            "umls": "UMLS only: CUI/code/label lookup without evidence vectors or evidence snippets",
            "umls_evidence": "UMLS plus evidence: UMLS identifiers with evidence-backed semantic retrieval",
        }
        ranker = (
            "UMLS span rerank: CUI/code/label lookup plus official UMLS label fallback, MRDEF definitions, MRSTY semantic types, and source code mappings"
            if scope == "umls"
            else "hybrid rerank: lexical label match + bounded MRDEF definition match + MRREL cross-type relation support + query-anchor recall/specificity + vector similarity + evidence presence + semantic, composite-intent, and fragment controls"
        )
        source_role = (
            "UMLS label, identifier, source-code, semantic-type, and definition indexes provide "
            "lookup fields; evidence vectors and evidence snippets are not used."
            if scope == "umls"
            else (
                "PubMed, PMC OA, and other permitted corpora contribute evidence text to CUI/view "
                "documents. Source names do not receive independent score weights in the current ranker."
            )
        )
        return {
            "retrieval": retrieval,
            "search_mode": search_mode,
            "search_mode_description": mode_descriptions.get(search_mode, mode_descriptions["balanced"]),
            "search_scope": scope,
            "search_scope_description": scope_descriptions.get(scope, scope_descriptions["umls_evidence"]),
            "embedding_provider": self.embedder.provider_name,
            "embedding_model": self.embedder.model_name,
            "ranker": ranker,
            "source_role": source_role,
        }

    def direct_search(
        self,
        resolution: dict,
        *,
        top_k: int,
        started: float,
        include_related: bool = True,
        include_evidence_items: bool = True,
        semantic_bucket_keys: object = None,
        search_mode: str = "balanced",
        search_scope: str = "umls_evidence",
        return_code_sabs: object = None,
        debug: bool = False,
    ) -> dict:
        semantic_bucket_keys = normalize_semantic_bucket_filter(semantic_bucket_keys)
        search_scope = str(search_scope or "umls_evidence").strip().lower()
        if search_scope == "umls":
            include_related = False
        response_resolution = (
            self.strip_evidence_from_umls_resolution(resolution)
            if search_scope == "umls"
            else resolution
        )
        candidates = list(resolution.get("candidates") or [])
        candidate_limit = len(candidates) if semantic_bucket_keys else top_k
        hits = [self.hit_from_candidate(candidate) for candidate in candidates[:candidate_limit]]
        hits = self.filter_hits_by_semantic_buckets(
            hits,
            semantic_bucket_keys,
            search_mode=search_mode,
        )[:top_k]
        if include_related:
            self.attach_related_concepts(hits)
        if search_scope == "umls":
            hits = self.strip_evidence_from_umls_hits(hits)
        hits = self.apply_source_code_selection(hits, sabs=return_code_sabs)
        for hit in hits:
            hit["score"] = round(float(hit["score"]), 6)
            hit["rank_score"] = hit["score"]
            exact_code_component = (
                hit["score"]
                if str(hit.get("match_type") or "") in {"code", "system_code", "umls_identifier"}
                else 0.0
            )
            hit["score_breakdown"] = {
                "rank_score": hit["score"],
                "retrieval_score": hit["score"],
                "lexical_component": 0.0,
                "vector_component": 0.0,
                "label_fallback_component": 0.0,
                "exact_label_component": 0.0,
                "exact_primary_name_component": 0.0,
                "exact_code_component": exact_code_component,
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
                "long_document_support_component": 0.0,
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
                "assertion_context_penalty": 0.0,
                "assertion": {"status": "current"},
                "normal_exam_fragment_penalty": 0.0,
                "lexical_fallback_used": False,
                "retrieval_kind": str(hit.get("match_type") or "resolver"),
            }
            hit["assertion"] = {"status": "current"}
        return self.compact_search_response({
            "query": resolution.get("query") or "",
            "top_k": top_k,
            "search_mode": search_mode,
            "search_scope": search_scope,
            "backend": "resolver",
            "scoring": self.scoring_summary(
                "resolver",
                search_mode=search_mode,
                search_scope=search_scope,
            ),
            "semantic_bucket_filter": list(semantic_bucket_keys),
            "input_type": resolution.get("input_type") or "",
            "resolution": response_resolution,
            "hits": hits,
            **self.result_score_filter_metadata(
                search_mode=search_mode,
                semantic_bucket_keys=semantic_bucket_keys,
                before_count=len(hits),
                after_count=len(hits),
            ),
            **self.source_contribution_metadata(hits, include_debug=debug),
            **self.semantic_response_metadata(
                hits,
                include_related=include_related,
                semantic_bucket_keys=semantic_bucket_keys,
            ),
            "elapsed_ms": round((time.time() - started) * 1000, 1),
        }, include_debug=debug, include_evidence_items=include_evidence_items)
