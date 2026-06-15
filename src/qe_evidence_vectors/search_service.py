from __future__ import annotations

import time
import csv
from array import array
from collections import Counter, OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from qe_evidence_vectors.code_index import CodeIndex
from qe_evidence_vectors.definition_index import DefinitionIndex
from qe_evidence_vectors.display_names import load_display_name_overrides
from qe_evidence_vectors.elastic_client import search_knn
from qe_evidence_vectors.embeddings import make_embedder
from qe_evidence_vectors.external_cui_vectors import ExternalCuiVectorIndex
from qe_evidence_vectors.provenance_index import ProvenanceIndex
from qe_evidence_vectors.public_output import (
    DEFAULT_PUBLIC_OUTPUT_SOURCES,
    load_public_output_sources,
    normalize_public_output_sources,
    PublicOutputMixin,
)
from qe_evidence_vectors.relation_index import RelationIndex
from qe_evidence_vectors.relationship_edge_index import RelationshipEdgeIndex
from qe_evidence_vectors.research_relations import ResearchRelationIndex
from qe_evidence_vectors.schema import iter_jsonl
from qe_evidence_vectors.search import iter_vectors, l2_normalize
from qe_evidence_vectors.search_execution import SearchExecutionMixin
from qe_evidence_vectors.search_hydration import SearchHydrationMixin, rank_evidence_items_for_query
from qe_evidence_vectors.search_label_fallback import LabelFallback
from qe_evidence_vectors.search_semantics import local_extension_semantic_type_rows
from qe_evidence_vectors.semantic_type_index import SemanticTypeIndex
from qe_evidence_vectors.lexical_normalization import lexical_variant_keys
from qe_evidence_vectors.text import normalized_key
from qe_evidence_vectors.search_related import SearchRelatedMixin
from qe_evidence_vectors.search_rerank import SearchRerankMixin
from qe_evidence_vectors.search_utils import (
    concept_display_name,
    load_evidence_provenance,
    parse_document_evidence,
    sentence_bounded_evidence_text,
)



@dataclass(frozen=True)
class SearchRecord:
    doc_id: str
    cui: str
    view: str
    vector: array
    labels: list[str]
    sources: list[str]
    evidence_count: int
    text: str
    evidence_items: list[dict]
    metadata: dict
    vector_path: str
    vector_row: int
    source_bundle: str


class SearchIndex(
    SearchExecutionMixin,
    SearchRerankMixin,
    SearchHydrationMixin,
    SearchRelatedMixin,
    PublicOutputMixin,
):
    def __init__(
        self,
        *,
        vector_paths: list[Path],
        doc_paths: list[Path],
        evidence_paths: list[Path],
        provenance_index_path: Path | None,
        provider: str,
        model: str | None,
        dim: int,
        local_files_only: bool,
        max_seq_length: int | None,
        device: str,
        idf_path: Path | None = None,
        elastic_url: str | None = None,
        elastic_index: str | None = None,
        elastic_num_candidates: int = 100,
        require_elasticsearch: bool = False,
        elastic_exclude_source_prefixes: list[str] | tuple[str, ...] | None = (),
        search_knn_func: Callable[..., list[dict]] | None = None,
        label_index_paths: list[Path] | None = None,
        label_max_tokens: int = 8,
        label_fallback_limit: int = 120,
        definition_fallback_limit: int = 80,
        code_index_path: Path | None = None,
        semantic_type_index_path: Path | None = None,
        relation_index_path: Path | None = None,
        relationship_edge_index_path: Path | None = None,
        research_relation_index_path: Path | None = None,
        external_cui_vector_index_path: Path | None = None,
        definition_index_path: Path | None = None,
        active_label_supplement_path: Path | None = None,
        related_limit: int = 8,
        related_source_limit: int = 8,
        expensive_related_source_limit: int = 0,
        query_cache_size: int = 0,
        candidate_pool_multiplier: int = 1,
        candidate_pool_min: int = 40,
        relationship_edges_rank: bool = False,
        display_name_overrides_path: Path | None = None,
        public_output_only: bool = False,
        public_output_sources: list[str] | tuple[str, ...] | None = None,
        public_output_source_allowlist_path: Path | None = None,
    ) -> None:
        self.vector_paths = vector_paths
        self.doc_paths = doc_paths
        self.evidence_paths = evidence_paths
        self.provenance_index_path = provenance_index_path
        self.provenance_index = ProvenanceIndex(provenance_index_path) if provenance_index_path else None
        self.provenance_by_doc_text: dict[tuple[str, str], list[dict]] = {}
        self.dim = dim
        self.embedder = make_embedder(
            provider,
            model=model,
            dim=dim,
            idf_path=idf_path,
            local_files_only=local_files_only,
            max_seq_length=max_seq_length,
            device=device,
        )
        self.idf_path = idf_path
        self.elastic_url = elastic_url
        self.elastic_index = elastic_index
        self.elastic_num_candidates = elastic_num_candidates
        self.require_elasticsearch = require_elasticsearch
        self.elastic_exclude_source_prefixes = tuple(
            prefix.strip()
            for prefix in (elastic_exclude_source_prefixes or [])
            if prefix.strip()
        )
        self.search_knn = search_knn_func or search_knn
        self.elastic_disabled_until = 0.0
        self.elastic_failure_reason = ""
        self.label_fallback = LabelFallback(
            label_index_paths or [],
            max_tokens=label_max_tokens,
        )
        self.label_fallback_limit = max(0, int(label_fallback_limit or 0))
        self.definition_fallback_limit = max(0, int(definition_fallback_limit or 0))
        self.code_index_path = code_index_path
        self.code_index = CodeIndex(code_index_path) if code_index_path else None
        self.semantic_type_index_path = semantic_type_index_path
        self.semantic_type_index = SemanticTypeIndex(semantic_type_index_path) if semantic_type_index_path else None
        self.relation_index_path = relation_index_path
        self.relation_index = RelationIndex(relation_index_path) if relation_index_path else None
        self.relationship_edge_index_path = relationship_edge_index_path
        self.relationship_edge_index = (
            RelationshipEdgeIndex(relationship_edge_index_path) if relationship_edge_index_path else None
        )
        self.research_relation_index_path = research_relation_index_path
        self.research_relation_index = (
            ResearchRelationIndex(research_relation_index_path) if research_relation_index_path else None
        )
        self.external_cui_vector_index_path = external_cui_vector_index_path
        self.external_cui_vector_index = (
            ExternalCuiVectorIndex(external_cui_vector_index_path)
            if external_cui_vector_index_path
            else None
        )
        self.definition_index_path = definition_index_path
        self.definition_index = DefinitionIndex(definition_index_path) if definition_index_path else None
        self.active_label_supplement_path = active_label_supplement_path
        self.related_limit = related_limit
        self.related_source_limit = related_source_limit
        self.expensive_related_source_limit = expensive_related_source_limit
        self.query_cache_size = max(0, int(query_cache_size or 0))
        self.query_result_cache = OrderedDict()
        self.query_cache_lock = Lock()
        self.query_cache_hits = 0
        self.query_cache_misses = 0
        self.candidate_pool_multiplier = max(1, int(candidate_pool_multiplier or 1))
        self.candidate_pool_min = max(1, int(candidate_pool_min or 1))
        self.relationship_edges_rank = bool(relationship_edges_rank)
        self.display_name_overrides_path = display_name_overrides_path
        self.display_name_overrides = load_display_name_overrides(display_name_overrides_path)
        self.public_output_only = bool(public_output_only)
        if public_output_source_allowlist_path:
            self.public_output_sources = load_public_output_sources(public_output_source_allowlist_path)
        elif public_output_sources is not None:
            self.public_output_sources = normalize_public_output_sources(public_output_sources)
        else:
            self.public_output_sources = DEFAULT_PUBLIC_OUTPUT_SOURCES
        self.public_output_source_allowlist_path = public_output_source_allowlist_path
        self.public_label_cache: dict[tuple[str, int], list[str]] = {}
        self.evidence_related_cache: dict[tuple[str, int], list[dict]] = {}
        self.external_related_cache: dict[tuple[str, int], list[dict]] = {}
        self.mrrel_related_cache: dict[tuple[str, int], list[dict]] = {}
        self.research_relation_cache: dict[tuple[str, int, bool], list[dict]] = {}
        self.relationship_edge_cache: dict[tuple[str, int], list[dict]] = {}
        self.drug_rollup_cache: dict[tuple[str, int], list[dict]] = {}
        self.loinc_lc_label_cache: dict[str, str] = {}
        self.records: list[SearchRecord] = []
        self.vector_matrix = None
        self.vector_matrix_backend = "python"
        self.source_bundle_counts: dict[str, int] = {}
        self.vector_file_counts: dict[str, int] = {}
        self.records_by_doc_id: dict[str, SearchRecord] = {}
        self.records_by_cui: dict[str, list[SearchRecord]] = {}
        self.best_record_by_cui: dict[str, SearchRecord] = {}
        self.preferred_label_cache: dict[str, str] = {}
        self.return_code_mappings_cache: dict[tuple, list[dict]] = {}
        self.semantic_types_cache: dict[str, list[dict]] = {}
        self.definitions_cache: dict[tuple[str, int], list[dict]] = {}
        self.extension_label_rows_by_norm: dict[str, list[dict]] = {}
        self.extension_semantic_types_by_cui: dict[str, list[dict]] = {}
        self.active_label_rows_by_norm: dict[str, list[dict]] = {}
        self.active_label_semantic_types_by_cui: dict[str, list[dict]] = {}
        self.metadata_reverse_relations_by_cui: dict[str, list[dict]] = {}
        self.images_by_cui: dict[str, list[dict]] = {}
        self.docs_count = 0
        self.provenance_count = 0
        self.loaded_at = time.time()
        self.load_seconds = 0.0
        self._load()

    def _load(self) -> None:
        started = time.time()
        if self.provenance_index:
            self.provenance_count = self.provenance_index.source_count()
        else:
            self.provenance_by_doc_text = load_evidence_provenance(self.evidence_paths)
            self.provenance_count = sum(len(value) for value in self.provenance_by_doc_text.values())
        docs_by_id: dict[str, dict] = {}
        for docs_path in self.doc_paths:
            if not docs_path.exists():
                continue
            for payload in iter_jsonl(docs_path):
                doc_id = payload.get("doc_id")
                if doc_id:
                    docs_by_id[doc_id] = payload
        self.docs_count = len(docs_by_id)

        records: list[SearchRecord] = []
        actual_dim: int | None = None
        for vectors_path in self.vector_paths:
            for vector_row, vector_record in enumerate(iter_vectors(vectors_path)):
                if actual_dim is None:
                    actual_dim = len(vector_record.vector)
                elif len(vector_record.vector) != actual_dim:
                    raise ValueError(
                        f"inconsistent vector dimensions in {vectors_path}: "
                        f"expected {actual_dim}, got {len(vector_record.vector)}"
                )
                doc = docs_by_id.get(vector_record.doc_id, {})
                metadata = {}
                if isinstance(doc.get("metadata"), dict):
                    metadata.update(doc["metadata"])
                if isinstance(vector_record.metadata, dict):
                    metadata.update(vector_record.metadata)
                labels = list(metadata.get("labels") or doc.get("labels") or [])
                sources = list(metadata.get("sources") or doc.get("sources") or [])
                evidence_count = int(
                    metadata.get("evidence_count") or doc.get("evidence_count") or 0
                )
                source_bundle = self.source_bundle_for_record(
                    vector_path=vectors_path,
                    doc=doc,
                    metadata=metadata,
                    sources=sources,
                )
                records.append(
                    SearchRecord(
                        doc_id=vector_record.doc_id,
                        cui=vector_record.cui,
                        view=vector_record.view,
                        vector=array("f", l2_normalize(vector_record.vector)),
                        labels=labels,
                        sources=sources,
                        evidence_count=evidence_count,
                        text=str(doc.get("text") or vector_record.text or ""),
                        evidence_items=parse_document_evidence(
                            str(doc.get("text") or vector_record.text or "")
                        ),
                        metadata=metadata,
                        vector_path=str(vectors_path),
                        vector_row=vector_row,
                        source_bundle=source_bundle,
                    )
                )
        self.records = records
        self.vector_matrix = self._build_vector_matrix(records)
        self.source_bundle_counts = dict(Counter(record.source_bundle for record in records))
        self.vector_file_counts = dict(Counter(record.vector_path for record in records))
        self.records_by_doc_id = {record.doc_id: record for record in records}
        records_by_cui: dict[str, list[SearchRecord]] = {}
        for record in records:
            records_by_cui.setdefault(record.cui, []).append(record)
        self.records_by_cui = records_by_cui
        self.best_record_by_cui = {
            cui: max(
                cui_records,
                key=lambda record: (
                    record.evidence_count,
                    len(record.evidence_items),
                    1 if record.labels else 0,
                    record.view,
                ),
            )
            for cui, cui_records in records_by_cui.items()
        }
        self.extension_label_rows_by_norm = self._extension_label_rows_by_norm(records_by_cui)
        self.extension_semantic_types_by_cui = self._extension_semantic_types_by_cui(records_by_cui)
        self.images_by_cui = self.images_by_cui_for_records(records)
        self.metadata_reverse_relations_by_cui = self.metadata_reverse_relations_by_cui_for_records(records)
        (
            self.active_label_rows_by_norm,
            self.active_label_semantic_types_by_cui,
        ) = self._active_label_supplement()
        if actual_dim is not None:
            self.dim = actual_dim
        self.load_seconds = time.time() - started

    def _build_vector_matrix(self, records: list[SearchRecord]):
        if not records:
            return None
        try:
            import numpy as np
        except Exception:
            self.vector_matrix_backend = "python"
            return None
        matrix = np.asarray([record.vector for record in records], dtype=np.float32)
        if matrix.ndim != 2:
            self.vector_matrix_backend = "python"
            return None
        if not np.isfinite(matrix).all():
            matrix = np.nan_to_num(matrix, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
        self.vector_matrix_backend = "numpy"
        return np.ascontiguousarray(matrix, dtype=np.float32)

    def source_bundle_for_record(
        self,
        *,
        vector_path: Path,
        doc: dict,
        metadata: dict,
        sources: list[str],
    ) -> str:
        explicit = str(
            metadata.get("source_bundle")
            or doc.get("source_bundle")
            or ""
        ).strip()
        if explicit:
            return explicit
        if len(sources) == 1 and sources[0]:
            return str(sources[0])
        name = vector_path.name
        for suffix in (
            ".hashing.jsonl",
            ".sentence_transformers.jsonl",
            ".transformers_cls.jsonl",
            ".bert_cls.jsonl",
            ".sapbert.jsonl",
            ".jsonl",
        ):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break
        for marker in (
            "_concept_vectors",
            "_vectors",
            ".cumulative",
        ):
            name = name.replace(marker, "")
        return name or "unknown"

    def images_by_cui_for_records(self, records: list[SearchRecord]) -> dict[str, list[dict]]:
        by_cui: dict[str, list[dict]] = {}
        seen_by_cui: dict[str, set[str]] = {}
        for record in records:
            raw_images = record.metadata.get("images") or []
            if not isinstance(raw_images, list):
                continue
            for raw_image in raw_images:
                if not isinstance(raw_image, dict):
                    continue
                thumbnail_url = str(raw_image.get("thumbnail_url") or raw_image.get("image_url") or "").strip()
                source_url = str(raw_image.get("source_url") or raw_image.get("file_page_url") or "").strip()
                if not thumbnail_url and not source_url:
                    continue
                key = source_url or thumbnail_url
                seen = seen_by_cui.setdefault(record.cui, set())
                if key in seen:
                    continue
                seen.add(key)
                image = {
                    "source": str(raw_image.get("source") or "wikimedia_commons"),
                    "title": str(raw_image.get("title") or ""),
                    "source_url": source_url,
                    "file_page_url": str(raw_image.get("file_page_url") or source_url),
                    "image_url": str(raw_image.get("image_url") or ""),
                    "thumbnail_url": thumbnail_url,
                    "mime": str(raw_image.get("mime") or ""),
                    "width": int(raw_image.get("width") or 0),
                    "height": int(raw_image.get("height") or 0),
                    "license": str(raw_image.get("license") or ""),
                    "license_url": str(raw_image.get("license_url") or ""),
                    "attribution": str(raw_image.get("attribution") or ""),
                    "description": str(raw_image.get("description") or ""),
                    "source_kind": str(raw_image.get("source_kind") or ""),
                }
                by_cui.setdefault(record.cui, []).append(image)
        return by_cui

    def _active_label_supplement(self) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
        path = self.active_label_supplement_path
        if not path or not path.exists():
            return {}, {}
        rows_by_norm: dict[str, list[dict]] = {}
        semantic_types_by_cui: dict[str, list[dict]] = {}
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(
                (line for line in handle if line.strip() and not line.lstrip().startswith("#")),
                delimiter="\t",
            )
            for row in reader:
                cui = str(row.get("cui") or "").strip().upper()
                label = str(row.get("label") or "").strip()
                normalized_keys = lexical_variant_keys(label)
                if not cui or not normalized_keys:
                    continue
                for normalized in normalized_keys:
                    rows_by_norm.setdefault(normalized, []).append(
                        {
                            "cui": cui,
                            "label": label,
                            "ispref": str(row.get("ispref") or "N").strip() or "N",
                            "sab": str(row.get("sab") or "MTH").strip() or "MTH",
                            "tty": str(row.get("tty") or "PT").strip() or "PT",
                            "specialty": str(row.get("specialty") or "").strip(),
                            "context_any": str(row.get("context_any") or "").strip(),
                            "block_any": str(row.get("block_any") or "").strip(),
                            "source": "active_label_supplement",
                            "doc_id": f"{cui}:active_label_supplement",
                        }
                    )
                semantic_type = str(row.get("semantic_type") or "").strip()
                if semantic_type and cui not in semantic_types_by_cui:
                    field = str(row.get("field") or "").strip()
                    semantic_rows = local_extension_semantic_type_rows(
                        semantic_type,
                        field=field,
                    )
                    if not semantic_rows:
                        semantic_rows = [
                            {
                                "name": semantic_type,
                                "sty": semantic_type,
                            }
                        ]
                        if field:
                            semantic_rows[0]["local_field"] = field
                    for semantic_row in semantic_rows:
                        semantic_row["source"] = "active_label_supplement"
                        semantic_row["atui"] = f"ACTIVE_LABEL_SUPPLEMENT:{cui}"
                    if semantic_rows:
                        semantic_types_by_cui[cui] = semantic_rows
        return rows_by_norm, semantic_types_by_cui

    def _extension_label_rows_by_norm(
        self,
        records_by_cui: dict[str, list[SearchRecord]],
    ) -> dict[str, list[dict]]:
        rows_by_norm: dict[str, list[dict]] = {}
        for cui, records in records_by_cui.items():
            if not str(cui).startswith("NEW"):
                continue
            seen_labels = set()
            for record in records:
                for index, label in enumerate(record.labels):
                    for normalized in lexical_variant_keys(str(label)):
                        if not normalized or normalized in seen_labels:
                            continue
                        seen_labels.add(normalized)
                        rows_by_norm.setdefault(normalized, []).append(
                            {
                                "cui": cui,
                                "label": str(label),
                                "ispref": "Y" if index == 0 else "N",
                                "doc_id": record.doc_id,
                            }
                        )
        return rows_by_norm

    def _extension_semantic_types_by_cui(
        self,
        records_by_cui: dict[str, list[SearchRecord]],
    ) -> dict[str, list[dict]]:
        rows_by_cui: dict[str, list[dict]] = {}
        for cui, records in records_by_cui.items():
            if not str(cui).startswith("NEW"):
                continue
            for record in records:
                rows = local_extension_semantic_type_rows(
                    str(record.metadata.get("semantic_type") or ""),
                    field=str(record.metadata.get("field") or ""),
                )
                if rows:
                    rows_by_cui[str(cui).upper()] = rows
                    break
        return rows_by_cui

    def related_concepts_mode_name(self) -> str:
        parts: list[str] = []
        if self.expensive_related_source_limit > 0:
            parts.append("evidence_vectors")
        if self.external_cui_vector_index:
            parts.append("external_embeddings")
        if self.relation_index:
            parts.append("mrrel")
        if self.research_relation_index:
            parts.append("research")
        return "_".join(parts) if parts else "disabled"

    def status(self) -> dict:
        return {
            "vectors_path": str(self.vector_paths[0]) if self.vector_paths else "",
            "docs_path": str(self.doc_paths[0]) if self.doc_paths else "",
            "vector_paths": [str(path) for path in self.vector_paths],
            "doc_paths": [str(path) for path in self.doc_paths],
            "records": len(self.records),
            "source_bundles": [
                {"source_bundle": source_bundle, "records": count}
                for source_bundle, count in sorted(
                    self.source_bundle_counts.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ],
            "vector_file_records": [
                {"vector_path": vector_path, "records": count}
                for vector_path, count in sorted(
                    self.vector_file_counts.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ],
            "docs": self.docs_count,
            "evidence_sources": self.provenance_count,
            "evidence_files": len(self.evidence_paths),
            "provenance_mode": "sqlite" if self.provenance_index else "memory",
            "provenance_index": str(self.provenance_index_path or ""),
            "dim": self.dim,
            "embedding_provider": self.embedder.provider_name,
            "embedding_model": self.embedder.model_name,
            "idf_path": str(self.idf_path or ""),
            "search_backend": "elasticsearch" if self.elastic_url and self.elastic_index else "local",
            "local_vector_backend": self.vector_matrix_backend,
            "elastic_url": self.elastic_url or "",
            "elastic_index": self.elastic_index or "",
            "elastic_num_candidates": self.elastic_num_candidates,
            "require_elasticsearch": self.require_elasticsearch,
            "elastic_exclude_source_prefixes": list(self.elastic_exclude_source_prefixes),
            "elastic_disabled_until": round(self.elastic_disabled_until, 3),
            "label_indexes": [str(path) for path in self.label_fallback.paths],
            "label_fallback_limit": self.label_fallback_limit,
            "definition_fallback_limit": self.definition_fallback_limit,
            "code_index": str(self.code_index_path or ""),
            "code_mappings": self.code_index.mapping_count() if self.code_index else 0,
            "semantic_type_index": str(self.semantic_type_index_path or ""),
            "semantic_type_cuis": self.semantic_type_index.source_count() if self.semantic_type_index else 0,
            "semantic_type_rows": self.semantic_type_index.semantic_type_count() if self.semantic_type_index else 0,
            "relation_index": str(self.relation_index_path or ""),
            "related_concepts_mode": self.related_concepts_mode_name(),
            "related_source_limit": self.related_source_limit,
            "expensive_related_source_limit": self.expensive_related_source_limit,
            "query_cache_size": self.query_cache_size,
            "query_cache_entries": len(self.query_result_cache),
            "query_cache_hits": self.query_cache_hits,
            "query_cache_misses": self.query_cache_misses,
            "candidate_pool_multiplier": self.candidate_pool_multiplier,
            "candidate_pool_min": self.candidate_pool_min,
            "relationship_edges_rank": self.relationship_edges_rank,
            "display_name_overrides": str(self.display_name_overrides_path or ""),
            "display_name_override_count": len(self.display_name_overrides),
            "public_output_only": self.public_output_only,
            "public_output_sources": list(self.public_output_sources)
            if self.public_output_only
            else [],
            "public_output_source_allowlist": str(self.public_output_source_allowlist_path or ""),
            "related_concept_sources": self.relation_index.source_count() if self.relation_index else 0,
            "related_concept_links": self.relation_index.relation_count() if self.relation_index else 0,
            "research_relation_index": str(self.research_relation_index_path or ""),
            "research_relation_sources": self.research_relation_index.source_count() if self.research_relation_index else 0,
            "research_relation_links": self.research_relation_index.relation_count() if self.research_relation_index else 0,
            "relationship_edge_index": str(self.relationship_edge_index_path or ""),
            "relationship_edge_sources": (
                self.relationship_edge_index.source_count() if self.relationship_edge_index else 0
            ),
            "relationship_edge_links": (
                self.relationship_edge_index.edge_count() if self.relationship_edge_index else 0
            ),
            "external_cui_vector_index": str(self.external_cui_vector_index_path or ""),
            "external_embedding_sources": self.external_cui_vector_index.sources() if self.external_cui_vector_index else [],
            "external_embedding_source_cuis": (
                self.external_cui_vector_index.source_count() if self.external_cui_vector_index else 0
            ),
            "external_embedding_links": (
                self.external_cui_vector_index.neighbor_count() if self.external_cui_vector_index else 0
            ),
            "definition_index": str(self.definition_index_path or ""),
            "definition_cuis": self.definition_index.cui_count() if self.definition_index else 0,
            "definition_rows": self.definition_index.definition_count() if self.definition_index else 0,
            "active_label_supplement": str(self.active_label_supplement_path or ""),
            "active_label_supplement_labels": sum(
                len(rows) for rows in self.active_label_rows_by_norm.values()
            ),
            "active_label_supplement_cuis": len(self.active_label_semantic_types_by_cui),
            "load_seconds": round(self.load_seconds, 3),
            "loaded_at": self.loaded_at,
        }

    def sources_for_evidence_text(self, doc_id: str, text: str) -> list[dict]:
        if self.provenance_index:
            return self.provenance_index.lookup_sources(doc_id, text, limit=5)
        return self.provenance_by_doc_text.get((doc_id, normalized_key(text)), [])

    def document_source_citation_for_record(self, record: SearchRecord) -> dict:
        metadata = record.metadata or {}
        source = str(metadata.get("source") or (record.sources[0] if record.sources else "")).strip()
        url = str(metadata.get("source_url") or "").strip()
        title = str(metadata.get("source_title") or source).strip()
        if not source and not url:
            return {}
        citation = {
            "label": title or source or url,
            "source": source or title or "document",
        }
        if url:
            citation["url"] = url
        if metadata.get("source_accessed"):
            citation["accessed"] = str(metadata.get("source_accessed") or "")
        if metadata.get("source_license"):
                citation["license"] = str(metadata.get("source_license") or "")
        return citation

    def mention_source_citations_for_record(self, record: SearchRecord, text: str) -> list[dict]:
        metadata = record.metadata or {}
        mention_sources = metadata.get("mention_sources") or []
        if not isinstance(mention_sources, list):
            return []
        haystack = text.lower()
        citations: list[dict] = []
        for mention_source in mention_sources:
            if not isinstance(mention_source, dict):
                continue
            doc_id = str(mention_source.get("doc_id") or "").strip()
            pmid = str(mention_source.get("pmid") or "").strip()
            doi = str(mention_source.get("doi") or "").strip()
            identifiers = [value for value in (doc_id, f"PMID:{pmid}" if pmid else "", doi) if value]
            if identifiers and not any(identifier.lower() in haystack for identifier in identifiers):
                continue
            source = str(mention_source.get("source") or "local_corpus").strip()
            title = str(mention_source.get("title") or doc_id or source).strip()
            citation = {
                "label": f"PubMed PMID:{pmid}" if pmid else title,
                "source": source,
            }
            if pmid:
                citation["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                citation["pmid"] = pmid
            elif doi:
                citation["url"] = f"https://doi.org/{doi}"
            if doc_id:
                citation["corpus_doc_id"] = doc_id
            if doi:
                citation["doi"] = doi
            if title:
                citation["title"] = title
            citations.append(citation)
            break
        return citations

    def evidence_items_for_record(self, record: SearchRecord, *, query: str = "") -> list[dict]:
        items: list[dict] = []
        for item in rank_evidence_items_for_query(list(record.evidence_items), query):
            hydrated = dict(item)
            text = str(item.get("text") or "")
            hydrated["sources"] = self.sources_for_evidence_text(record.doc_id, text)
            if not hydrated["sources"]:
                hydrated["sources"] = self.mention_source_citations_for_record(record, text)
            if not hydrated["sources"]:
                citation = self.document_source_citation_for_record(record)
                if citation:
                    hydrated["sources"] = [citation]
            hydrated["text"] = sentence_bounded_evidence_text(text)
            items.append(hydrated)
        return items
