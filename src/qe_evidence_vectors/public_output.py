from __future__ import annotations

import sqlite3
import re
from pathlib import Path

from qe_evidence_vectors.code_index import normalize_sab
from qe_evidence_vectors.search_semantic_buckets import semantic_result_buckets_for_response
from qe_evidence_vectors.search_semantics import SEMANTIC_GROUP_LABELS, semantic_group_from_types
from qe_evidence_vectors.search_utils import concept_display_name, merge_labels
from qe_evidence_vectors.text import normalized_key


DEFAULT_PUBLIC_OUTPUT_SOURCES = (
    "AOD",
    "AOT",
    "ATC",
    "CCS",
    "CCSR_ICD10CM",
    "CCSR_ICD10PCS",
    "CDCREC",
    "CHV",
    "CSP",
    "CST",
    "CVX",
    "FMA",
    "GO",
    "HGNC",
    "HL7V2.5",
    "HL7V3.0",
    "HPO",
    "LNC",
    "MED-RT",
    "MEDLINEPLUS",
    "MSH",
    "MTH",
    "MTHICD9",
    "MTHMST",
    "MTHSPL",
    "NCBI",
    "NCI",
    "NCISEER",
    "OMIM",
    "PDQ",
    "RXNORM",
    "SRC",
    "VANDF",
)
DEFAULT_PUBLIC_EVIDENCE_SOURCE_PREFIXES = (
    "active_label_supplement",
    "atc",
    "cdc",
    "clinicaltrials",
    "clinicaltrials_gov",
    "dailymed",
    "drugbank",
    "europepmc",
    "fda",
    "hpo",
    "local_extension",
    "medlineplus",
    "medlineplus_genetics",
    "mondo",
    "ncbi_bookshelf_oa",
    "nci",
    "niddk",
    "openalex",
    "openalex_top_cited",
    "pmc",
    "pmc_oa",
    "pubmed",
    "pubmed_bulk",
    "rxnorm",
    "umls_label",
    "wikipedia",
    "wikimedia",
)

PUBLIC_OUTPUT_DROP_FIELDS = {
    "codes",
    "source_asserted_codes",
    "mappings",
    "matched_label",
    "matched_sab",
    "matched_tty",
    "matched_ispref",
    "matched_lexical_span",
    "matched_lookup_norm",
    "mrrel_component",
    "mrrel_matched_tokens",
    "mrrel_signal_reasons",
    "score_breakdown",
    "source_bundle",
    "vector_lineage",
    "vector_path",
    "vector_row",
    "retrieval",
    "text",
}
PUBLIC_OUTPUT_DROP_CONTAINER_FIELDS = {
    "evidence_items",
    "evidence_vector_neighbors",
    "external_embedding_neighbors",
    "research_relations",
    "source_mix",
    "source_bundle_contributions",
    "source_contributions",
    "semantic_views",
    "semantic_view_sources",
    "semantic_group_views",
    "related_result_buckets",
    "semantic_result_buckets",
}
PUBLIC_OUTPUT_DEFINITION_FIELDS = {"definitions"}
PUBLIC_OUTPUT_RELATION_FIELDS = {
    "related_concepts",
    "mrrel_neighbors",
    "mrrel_related_concepts",
}
PUBLIC_OUTPUT_HIT_LIST_FIELDS = {
    "hits",
    "linked_concepts",
    "candidates",
    "evidence_related_concepts",
}
PUBLIC_OUTPUT_HIT_LIKE_FIELDS = {
    "details_lazy",
    "doc_id",
    "evidence_count",
    "match_type",
    "rank_score",
    "score",
    "score_breakdown",
    "view",
}
PUBLIC_OUTPUT_TTY_PRIORITY = {
    "PT": 0,
    "MH": 1,
    "PN": 2,
    "IN": 3,
    "ET": 4,
    "FN": 5,
    "SY": 6,
    "LLT": 7,
}


def normalize_public_output_source(value: object) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    collapsed = re.sub(r"[^A-Z0-9_]+", "", text)
    alias = normalize_sab(text)
    if alias != collapsed:
        return alias
    return text


def normalize_public_output_sources(values: object = None) -> tuple[str, ...]:
    if values is None:
        return DEFAULT_PUBLIC_OUTPUT_SOURCES
    if isinstance(values, str):
        raw_values = values.replace("|", ",").split(",")
    else:
        try:
            raw_values = list(values)
        except TypeError:
            raw_values = [values]
    normalized = []
    for raw_value in raw_values:
        source = normalize_public_output_source(raw_value)
        if source and source not in normalized:
            normalized.append(source)
    return tuple(normalized)


def load_public_output_sources(path: Path | None) -> tuple[str, ...]:
    if not path:
        return DEFAULT_PUBLIC_OUTPUT_SOURCES
    values = []
    with path.expanduser().open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.split("#", 1)[0].strip()
            if not text:
                continue
            values.extend(part.strip() for part in text.replace("\t", ",").split(",") if part.strip())
    return normalize_public_output_sources(values)


def normalize_public_evidence_source(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return re.sub(r"[^a-z0-9_]+", "_", text).strip("_")


class PublicOutputMixin:
    def public_output_enabled(self) -> bool:
        return bool(getattr(self, "public_output_only", False))

    def public_source_allowed(self, source: object) -> bool:
        return normalize_public_output_source(source) in set(
            getattr(self, "public_output_sources", DEFAULT_PUBLIC_OUTPUT_SOURCES)
        )

    def public_evidence_source_allowed(self, source: object) -> bool:
        normalized = normalize_public_evidence_source(source)
        if not normalized:
            return False
        if self.public_source_allowed(source):
            return True
        prefixes = tuple(DEFAULT_PUBLIC_EVIDENCE_SOURCE_PREFIXES)
        return normalized in prefixes or any(
            normalized.startswith(f"{prefix}_") for prefix in prefixes
        )

    def public_evidence_sources_for_hit(self, hit: dict) -> list[str] | None:
        raw_sources = hit.get("sources")
        if raw_sources is None:
            return []
        try:
            sources = [str(source).strip() for source in raw_sources if str(source).strip()]
        except TypeError:
            source = str(raw_sources).strip()
            sources = [source] if source else []
        if not sources:
            return []
        public_sources = [
            source for source in sources if self.public_evidence_source_allowed(source)
        ]
        if len(public_sources) != len(sources):
            return None
        return public_sources

    def public_labels_for_cui(self, cui: str, *, limit: int = 8) -> list[str]:
        cui = str(cui or "").strip().upper()
        if not cui:
            return []
        cache = getattr(self, "public_label_cache", None)
        if cache is None:
            self.public_label_cache = {}
            cache = self.public_label_cache
        key = (cui, int(limit))
        cached = cache.get(key)
        if cached is not None:
            return list(cached)
        labels = self._public_labels_from_code_index(cui, limit=limit)
        if not labels and cui.startswith("NEW"):
            record = self.best_record_for_cui(cui)
            if record:
                labels = merge_labels(list(record.labels or []), [])[:limit]
        cache[key] = list(labels)
        return list(labels)

    def _public_labels_from_code_index(self, cui: str, *, limit: int) -> list[str]:
        code_index = getattr(self, "code_index", None)
        if not code_index:
            return []
        sources = tuple(getattr(self, "public_output_sources", DEFAULT_PUBLIC_OUTPUT_SOURCES))
        if not sources:
            return []
        placeholders = ",".join("?" for _ in sources)
        try:
            rows = list(
                code_index.connection().execute(
                    f"""
                    SELECT label, sab, tty, 'Y' AS ispref, suppress, 0 AS source_table
                    FROM preferred_terms
                    WHERE cui = ? AND suppress = 'N' AND sab IN ({placeholders})
                    UNION ALL
                    SELECT label, sab, tty, ispref, suppress, 1 AS source_table
                    FROM code_mappings
                    WHERE cui = ? AND suppress = 'N' AND sab IN ({placeholders})
                    LIMIT ?
                    """,
                    (cui, *sources, cui, *sources, max(limit * 25, 100)),
                )
            )
        except sqlite3.OperationalError:
            rows = []
        source_priority = {source: index for index, source in enumerate(sources)}
        labels = []
        seen = set()
        for row in sorted(
            rows,
            key=lambda row: (
                int(row["source_table"] or 0),
                0 if str(row["ispref"] or "") == "Y" else 1,
                source_priority.get(str(row["sab"] or ""), 999),
                PUBLIC_OUTPUT_TTY_PRIORITY.get(str(row["tty"] or ""), 99),
                str(row["label"] or "").lower(),
            ),
        ):
            label = str(row["label"] or "").strip()
            normalized = normalized_key(label)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            labels.append(label)
            if len(labels) >= limit:
                break
        return labels

    def public_display_label_for_cui(self, cui: str) -> str:
        return concept_display_name(self.public_labels_for_cui(cui), fallback="")

    def public_active_label_supplement_labels_for_hit(
        self,
        cui: str,
        hit: dict,
        *,
        public_sources: list[str],
        limit: int = 8,
    ) -> list[str]:
        if not str(cui or "").strip().upper():
            return []
        normalized_sources = {normalize_public_evidence_source(source) for source in public_sources}
        if "active_label_supplement" not in normalized_sources:
            return []
        values = [
            hit.get("name"),
            hit.get("matched_label"),
            *list(hit.get("labels") or []),
        ]
        labels = []
        seen = set()
        for value in values:
            label = str(value or "").strip()
            key = normalized_key(label)
            if not key or key in seen:
                continue
            seen.add(key)
            labels.append(label)
            if len(labels) >= limit:
                break
        return labels

    def public_output_payload(self, payload):
        if not self.public_output_enabled():
            return payload
        return self._public_output_value(payload, parent_key="") or {}

    def _public_output_value(self, value, *, parent_key: str):
        if isinstance(value, list):
            items = []
            for item in value:
                cleaned = self._public_output_value(item, parent_key=parent_key)
                if cleaned is not None:
                    items.append(cleaned)
            return items
        if not isinstance(value, dict):
            return value
        if parent_key in PUBLIC_OUTPUT_DEFINITION_FIELDS:
            return self._public_output_definition(value)
        if parent_key in PUBLIC_OUTPUT_RELATION_FIELDS:
            return self._public_output_relation(value)
        if parent_key in PUBLIC_OUTPUT_HIT_LIST_FIELDS or self._public_output_hit_like(value):
            return self._public_output_hit(value)

        cleaned = {}
        for key, item in value.items():
            if key in PUBLIC_OUTPUT_DROP_FIELDS or key in PUBLIC_OUTPUT_DROP_CONTAINER_FIELDS:
                continue
            if key in PUBLIC_OUTPUT_DEFINITION_FIELDS:
                cleaned[key] = [
                    definition
                    for definition in (
                        self._public_output_definition(definition)
                        for definition in (item or [])
                        if isinstance(definition, dict)
                    )
                    if definition is not None
                ]
                continue
            if key in PUBLIC_OUTPUT_RELATION_FIELDS:
                cleaned[key] = [
                    relation
                    for relation in (
                        self._public_output_relation(relation)
                        for relation in (item or [])
                        if isinstance(relation, dict)
                    )
                    if relation is not None
                ]
                continue
            if key == "score_breakdown" and isinstance(item, dict):
                cleaned_score_breakdown = {
                    score_key: score_value
                    for score_key, score_value in item.items()
                    if score_key not in PUBLIC_OUTPUT_DROP_FIELDS
                }
                if cleaned_score_breakdown:
                    cleaned[key] = cleaned_score_breakdown
                continue
            cleaned_value = self._public_output_value(item, parent_key=str(key))
            if cleaned_value is not None:
                cleaned[key] = cleaned_value
        if isinstance(cleaned.get("hits"), list):
            hits = list(cleaned.get("hits") or [])
            top_group = semantic_group_from_types(list(hits[0].get("semantic_types") or [])) if hits else ""
            cleaned["top_semantic_group"] = top_group
            cleaned["top_semantic_group_label"] = (
                SEMANTIC_GROUP_LABELS.get(top_group, "Other") if top_group else ""
            )
            semantic_result_buckets = semantic_result_buckets_for_response(
                hits,
                [],
                semantic_bucket_keys=cleaned.get("semantic_bucket_filter") or (),
            )
            for bucket in semantic_result_buckets:
                bucket.pop("codes", None)
            cleaned["semantic_result_buckets"] = semantic_result_buckets
            cleaned["related_result_buckets"] = []
        return cleaned

    def _public_output_hit_like(self, value: dict) -> bool:
        if not value.get("cui"):
            return False
        return bool({"name", "label", "labels"} & set(value)) or bool(
            PUBLIC_OUTPUT_HIT_LIKE_FIELDS & set(value)
        )

    def _public_output_hit(self, hit: dict) -> dict | None:
        cui = str(hit.get("cui") or "").strip().upper()
        public_sources = self.public_evidence_sources_for_hit(hit)
        if public_sources is None:
            return None
        if cui:
            labels = self.public_labels_for_cui(cui)
            if not labels:
                labels = self.public_active_label_supplement_labels_for_hit(
                    cui,
                    hit,
                    public_sources=public_sources,
                )
            name = concept_display_name(labels, fallback="")
            if not name:
                return None
        else:
            labels = []
            name = ""

        cleaned = {}
        for key, value in hit.items():
            if key in PUBLIC_OUTPUT_DROP_FIELDS or key in PUBLIC_OUTPUT_DROP_CONTAINER_FIELDS:
                continue
            if key == "sources":
                if public_sources:
                    cleaned[key] = public_sources
                continue
            if key in {"name", "label"}:
                if name:
                    cleaned[key] = name
                continue
            if key == "labels":
                cleaned[key] = list(labels)
                continue
            if key in PUBLIC_OUTPUT_DEFINITION_FIELDS:
                cleaned[key] = [
                    definition
                    for definition in (
                        self._public_output_definition(definition)
                        for definition in (value or [])
                        if isinstance(definition, dict)
                    )
                    if definition is not None
                ]
                continue
            if key in PUBLIC_OUTPUT_RELATION_FIELDS:
                cleaned[key] = [
                    relation
                    for relation in (
                        self._public_output_relation(relation)
                        for relation in (value or [])
                        if isinstance(relation, dict)
                    )
                    if relation is not None
                ]
                continue
            cleaned_value = self._public_output_value(value, parent_key=str(key))
            if cleaned_value is not None:
                cleaned[key] = cleaned_value
        if cui:
            cleaned["cui"] = cui
            cleaned["name"] = name
            cleaned["label"] = name if "label" in hit else cleaned.get("label", name)
            cleaned["labels"] = list(labels)
        return cleaned

    def _public_output_definition(self, item: dict) -> dict | None:
        source = str(item.get("source") or "").strip()
        if not source or not self.public_source_allowed(source):
            return None
        definition = str(item.get("definition") or "").strip()
        if not definition:
            return None
        return {
            "cui": str(item.get("cui") or "").strip(),
            "source": source,
            "definition": definition,
            "rank": int(item.get("rank") or 0),
        }

    def _public_output_relation(self, item: dict) -> dict | None:
        source = str(item.get("source") or item.get("sab") or "").strip()
        if source and not self.public_source_allowed(source):
            return None
        target_cui = str(item.get("cui") or item.get("target_cui") or "").strip().upper()
        if not target_cui:
            return None
        label = self.public_display_label_for_cui(target_cui)
        if not label:
            return None
        cleaned = {}
        for key, value in item.items():
            if key in PUBLIC_OUTPUT_DROP_FIELDS or key in PUBLIC_OUTPUT_DROP_CONTAINER_FIELDS:
                continue
            if key in {"label", "target_label", "name"}:
                cleaned[key] = label
                continue
            cleaned_value = self._public_output_value(value, parent_key=str(key))
            if cleaned_value is not None:
                cleaned[key] = cleaned_value
        cleaned["cui"] = target_cui
        cleaned["label"] = label
        if "target_cui" in item:
            cleaned["target_cui"] = target_cui
        return cleaned
