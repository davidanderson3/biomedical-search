from __future__ import annotations

from qe_evidence_vectors.search_semantics import (
    EXTERNAL_EMBEDDING_GROUP_CATEGORIES,
    RELATION_CATEGORY_SEMANTIC_GROUPS,
    SEMANTIC_GROUP_RELATION_CATEGORIES,
    SEMANTIC_GROUP_LABELS,
    SEMANTIC_GROUP_VIEW_ORDER,
    SEMANTIC_GROUP_VIEW_PRESETS,
    SEMANTIC_VIEW_CATEGORY_LABELS,
    SEMANTIC_VIEW_CATEGORY_ORDER,
    semantic_type_name_set,
    semantic_group_from_types,
)
from qe_evidence_vectors.search_semantic_buckets import (
    related_result_buckets_for_response,
    semantic_result_buckets_for_response,
)
from qe_evidence_vectors.text import normalized_key
from qe_evidence_vectors.universal_relationship import attach_universal_edge


INVERSE_RELATION_LABELS = {
    "acts_on": ("target_of", "target of"),
    "administration_route": ("route_for", "route for"),
    "brand_of": ("has_brand", "has brand"),
    "clinical_comparator": ("clinical_comparator", "compared with"),
    "contraindicated_with": ("contraindication_for", "contraindication for"),
    "contraindicated_with_disease": ("contraindicated_condition_for", "contraindicated condition for"),
    "has_adverse_effect": ("adverse_effect_of", "adverse effect of"),
    "has_drug_class": ("drug_class_of", "drug class of"),
    "has_indicated_treatment": ("indicated_for", "indicated for"),
    "has_member": ("member_of", "member of"),
    "has_warning": ("warning_for", "warning for"),
    "indicated_for": ("has_indicated_treatment", "has indicated treatment"),
    "may_be_prevented_by": ("may_prevent", "may prevent"),
    "may_treat": ("may_be_treated_by", "may be treated by"),
    "member_of": ("has_member", "has member"),
    "pharmacology_context": ("pharmacology_context_for", "pharmacology context for"),
    "route_of_administration": ("administration_route_for", "administration route for"),
    "used_for": ("has_therapy", "has therapy"),
}
DRUG_ROLLUP_PRECISE_TTYS = {"PIN", "MIN"}
DRUG_ROLLUP_CLINICAL_TTYS = {
    "SCD",
    "SBD",
    "GPCK",
    "BPCK",
    "SCDG",
    "SBDG",
    "SCDF",
    "SBDF",
    "SBDC",
    "SCDC",
}
DRUG_ROLLUP_BRAND_TTYS = {"BN", "BD"}
DRUG_ROLLUP_MEASUREMENT_TERMS = {
    "assay",
    "concentration",
    "level",
    "mass",
    "measurement",
    "monitoring",
    "serum",
    "urine",
}
DRUG_ROLLUP_THERAPY_TERMS = {
    "administration",
    "infusion",
    "injection",
    "prophylaxis",
    "therapy",
    "treatment",
}
DRUG_ROLLUP_ROLE_PRIORITY = {
    "salt_or_precise_ingredient": 0,
    "clinical_drug": 1,
    "brand": 2,
    "therapy": 3,
    "measurement": 4,
    "drug_related": 5,
}
DRUG_ROLLUP_BIO_LABEL_TERMS = {
    "cytochrome",
    "dehydrogenase",
    "enzyme",
    "gene",
    "kinase",
    "protein",
    "receptor",
    "transporter",
}


def inverse_relation_labels(relation: str, rela: str) -> tuple[str, str]:
    relation_key = str(relation or "").strip()
    rela_key = str(rela or "").strip()
    for key in (rela_key, relation_key):
        normalized = key.lower().replace(" ", "_")
        if normalized in INVERSE_RELATION_LABELS:
            return INVERSE_RELATION_LABELS[normalized]
    if rela_key:
        return f"inverse_{rela_key}", f"inverse {rela_key.replace('_', ' ')}"
    if relation_key:
        return f"inverse_{relation_key}", f"inverse {relation_key.replace('_', ' ')}"
    return "inverse_related_to", "inverse related to"


class SearchRelatedMixin:
    def related_concepts_for_cui(self, cui: str) -> list[dict]:
        cui = cui.strip().upper()
        if not self.relation_index or not cui:
            return []
        cache_key = (cui, self.related_limit)
        cached = getattr(self, "mrrel_related_cache", {}).get(cache_key)
        if cached is not None:
            return [dict(item) for item in cached]
        outgoing = self.normalize_direction_rows(
            self.relation_index.lookup(cui, limit=self.related_limit)
        )
        incoming = self.incoming_related_concepts_for_cui(cui, limit=self.related_limit)
        related = self.merge_related_concept_rows(outgoing, incoming, limit=self.related_limit)
        if hasattr(self, "mrrel_related_cache"):
            self.mrrel_related_cache[cache_key] = [dict(item) for item in related]
        return related

    def merge_related_concept_rows(
        self,
        primary: list[dict],
        secondary: list[dict],
        *,
        limit: int,
    ) -> list[dict]:
        merged = []
        seen = set()
        for item in [*primary, *secondary]:
            target_cui = str(item.get("cui") or "").strip()
            if not target_cui or target_cui in seen:
                continue
            seen.add(target_cui)
            merged.append(dict(item))
            if len(merged) >= limit:
                break
        return merged

    def incoming_related_concepts_for_cui(self, cui: str, *, limit: int) -> list[dict]:
        if not self.relation_index or not cui:
            return []
        rows = self.relation_index.lookup_incoming(cui, limit=max(limit * 3, 16))
        related = []
        for row in rows:
            target_cui = str(row.get("source_cui") or "").strip()
            if not target_cui or target_cui == cui:
                continue
            relation, rela = inverse_relation_labels(
                str(row.get("relation") or ""),
                str(row.get("rela") or ""),
            )
            label = self.display_label_for_cui(target_cui, [self.record_label_for_cui(target_cui)])
            if not label:
                continue
            item = {
                "cui": target_cui,
                "relation": relation,
                "rela": rela,
                "source": row.get("source") or "",
                "direction": "bidirectional",
                "raw_direction": row.get("direction") or "",
                "label": label,
            }
            related.append(
                attach_universal_edge(
                    item,
                    subject_cui=cui,
                    object_cui=target_cui,
                )
            )
            if len(related) >= limit:
                break
        return related

    def record_label_for_cui(self, cui: str) -> str:
        record = self.best_record_for_cui(cui)
        if not record:
            return ""
        return self.display_label_for_cui(cui, list(record.labels or []))

    def research_relations_for_cui(
        self,
        cui: str,
        *,
        include_relationship_edges: bool = True,
    ) -> list[dict]:
        cui = cui.strip().upper()
        if not cui:
            return []
        cache_key = (cui, 6, bool(include_relationship_edges))
        cached = getattr(self, "research_relation_cache", {}).get(cache_key)
        if cached is not None:
            return [dict(item) for item in cached]
        metadata_relations = self.metadata_relations_for_cui(cui, limit_per_category=6)
        edge_relations = (
            self.relationship_edge_relations_for_cui(cui, limit_per_category=6)
            if include_relationship_edges
            else []
        )
        indexed_relations = (
            self.normalize_direction_rows(
                self.research_relation_index.lookup(cui, limit_per_category=6)
            )
            if self.research_relation_index
            else []
        )
        indexed_incoming = self.incoming_research_relations_for_cui(cui, limit_per_category=6)
        direct_relations = self.merge_research_relation_rows(
            metadata_relations,
            [*edge_relations, *indexed_relations, *indexed_incoming],
            limit_per_category=6,
        )
        rollup_relations = self.drug_rollup_research_relations_for_cui(
            cui,
            seed_relations=direct_relations,
            limit_per_category=6,
        )
        relations = self.merge_research_relation_rows(
            direct_relations,
            rollup_relations,
            limit_per_category=6,
        )
        if hasattr(self, "research_relation_cache"):
            self.research_relation_cache[cache_key] = [dict(item) for item in relations]
        return relations

    def merge_research_relation_rows(
        self,
        primary: list[dict],
        secondary: list[dict],
        *,
        limit_per_category: int,
    ) -> list[dict]:
        merged: list[dict] = []
        seen: set[tuple[str, str]] = set()
        category_counts: dict[str, int] = {}
        for relation in [*primary, *secondary]:
            category = str(relation.get("category") or "").strip()
            target_cui = str(relation.get("cui") or "").strip()
            if not category or not target_cui:
                continue
            key = (category, target_cui)
            if key in seen:
                continue
            if category_counts.get(category, 0) >= limit_per_category:
                continue
            seen.add(key)
            category_counts[category] = category_counts.get(category, 0) + 1
            merged.append(dict(relation))
        return merged

    def normalize_direction_rows(self, rows: list[dict]) -> list[dict]:
        normalized = []
        for row in rows:
            item = dict(row)
            if str(item.get("direction") or "") == "incoming":
                item["raw_direction"] = "incoming"
                item["direction"] = "bidirectional"
                source_cui = str(item.get("source_cui") or "").strip().upper()
                target_cui = str(item.get("cui") or item.get("target_cui") or "").strip().upper()
                if source_cui and target_cui:
                    item = attach_universal_edge(
                        item,
                        subject_cui=source_cui,
                        object_cui=target_cui,
                    )
            normalized.append(item)
        return normalized

    def metadata_relations_for_cui(self, cui: str, *, limit_per_category: int = 6) -> list[dict]:
        source_cui = cui.strip().upper()
        record = self.best_record_for_cui(cui)
        records = list(getattr(self, "records_by_cui", {}).get(source_cui, []))
        if record and record not in records:
            records.append(record)
        raw_relations = []
        for relation_record in records:
            source = str(
                relation_record.metadata.get("source")
                or (relation_record.sources[0] if relation_record.sources else "")
                or "concept_document"
            )
            for raw_relation in list(relation_record.metadata.get("relations") or []):
                if not isinstance(raw_relation, dict):
                    raw_relations.append(raw_relation)
                    continue
                item = dict(raw_relation)
                item.setdefault("source", source)
                raw_relations.append(item)
            raw_relations.extend(
                self.legacy_metadata_relations(
                    relation_record.metadata,
                    source=source,
                )
            )
        raw_relations.extend(
            list(getattr(self, "metadata_reverse_relations_by_cui", {}).get(source_cui, []))
        )
        if not raw_relations:
            return []
        relations = []
        seen_targets: set[tuple[str, str]] = set()
        for rank, raw_relation in enumerate(raw_relations, start=1):
            if not isinstance(raw_relation, dict):
                continue
            target_cui = str(raw_relation.get("cui") or "").strip().upper()
            if not target_cui:
                continue
            target_semantic_types = self.semantic_types_for_cui(target_cui)
            target_group = semantic_group_from_types(target_semantic_types)
            category = str(raw_relation.get("category") or "").strip()
            if not category:
                category = SEMANTIC_GROUP_RELATION_CATEGORIES.get(target_group, "phenotype")
            key = (category, target_cui)
            if key in seen_targets:
                continue
            seen_targets.add(key)
            label = self.display_label_for_cui(target_cui, [str(raw_relation.get("label") or "").strip()])
            if not label:
                continue
            semantic_type = (
                target_semantic_types[0].get("name")
                or target_semantic_types[0].get("sty")
                if target_semantic_types
                else ""
            )
            relation = {
                "cui": target_cui,
                "category": category,
                "category_label": SEMANTIC_VIEW_CATEGORY_LABELS.get(
                    category,
                    category.replace("_", " ").title(),
                ),
                "relation_group": str(raw_relation.get("relation_group") or "associated"),
                "relation": str(raw_relation.get("relation") or "related_to"),
                "rela": str(
                    raw_relation.get("rela")
                    or raw_relation.get("relation")
                    or "related_to"
                ),
                "source": str(
                    raw_relation.get("source")
                    or (record.sources[0] if record and record.sources else "concept_document")
                ),
                "direction": str(raw_relation.get("direction") or "outgoing"),
                "label": label,
                "semantic_type": semantic_type,
                "target_semantic_group": target_group,
                "rank": int(raw_relation.get("rank") or rank),
            }
            if raw_relation.get("support_count"):
                relation["support_count"] = int(raw_relation.get("support_count") or 0)
            for field in ("supporting_pmids", "supporting_doc_ids", "supporting_titles"):
                if raw_relation.get(field):
                    relation[field] = list(raw_relation.get(field) or [])
            relations.append(
                attach_universal_edge(
                    relation,
                    subject_cui=source_cui,
                    object_cui=target_cui,
                )
            )
        relations.sort(
            key=lambda item: (
                int(item.get("rank") or 0),
                str(item.get("category") or ""),
                str(item.get("label") or ""),
            )
        )
        return self.merge_research_relation_rows(relations, [], limit_per_category=limit_per_category)

    def metadata_reverse_relations_by_cui_for_records(self, records: list) -> dict[str, list[dict]]:
        reverse: dict[str, list[dict]] = {}
        for record in records:
            raw_relations = list(record.metadata.get("relations") or [])
            raw_relations.extend(
                self.legacy_metadata_relations(
                    record.metadata,
                    source=str(record.sources[0] if record.sources else "concept_document"),
                )
            )
            for raw_relation in raw_relations:
                if not isinstance(raw_relation, dict):
                    continue
                target_cui = str(raw_relation.get("cui") or "").strip().upper()
                if not target_cui or target_cui == record.cui:
                    continue
                relation, rela = inverse_relation_labels(
                    str(raw_relation.get("relation") or ""),
                    str(raw_relation.get("rela") or ""),
                )
                reverse_relation = dict(raw_relation)
                label = self.display_label_for_cui(record.cui, list(record.labels or []))
                if not label:
                    continue
                reverse_relation.update(
                    {
                        "cui": record.cui,
                        "label": label,
                        "category": "",
                        "relation": relation,
                        "rela": rela,
                        "source": str(
                            raw_relation.get("source")
                            or (record.sources[0] if record.sources else "concept_document")
                        ),
                        "direction": "bidirectional",
                        "raw_direction": raw_relation.get("direction") or "outgoing",
                    }
                )
                reverse.setdefault(target_cui, []).append(reverse_relation)
        return reverse

    def incoming_research_relations_for_cui(
        self,
        cui: str,
        *,
        limit_per_category: int,
    ) -> list[dict]:
        if not self.research_relation_index or not cui:
            return []
        rows = self.research_relation_index.lookup_incoming(
            cui,
            limit=max(limit_per_category * 8, 48),
        )
        relations = []
        for row in rows:
            target_cui = str(row.get("source_cui") or "").strip()
            if not target_cui or target_cui == cui:
                continue
            target_semantic_types = self.semantic_types_for_cui(target_cui)
            target_group = semantic_group_from_types(target_semantic_types)
            category = SEMANTIC_GROUP_RELATION_CATEGORIES.get(target_group, "phenotype")
            relation, rela = inverse_relation_labels(
                str(row.get("relation") or ""),
                str(row.get("rela") or ""),
            )
            label = self.display_label_for_cui(
                target_cui,
                [self.record_label_for_cui(target_cui)],
            )
            if not label:
                continue
            semantic_type = (
                target_semantic_types[0].get("name")
                or target_semantic_types[0].get("sty")
                if target_semantic_types
                else str(row.get("source_semantic_type") or "")
            )
            item = {
                "cui": target_cui,
                "category": category,
                "category_label": SEMANTIC_VIEW_CATEGORY_LABELS.get(
                    category,
                    category.replace("_", " ").title(),
                ),
                "relation_group": str(row.get("relation_group") or "associated"),
                "relation": relation,
                "rela": rela,
                "source": row.get("source") or "",
                "direction": "bidirectional",
                "raw_direction": row.get("direction") or "",
                "label": label,
                "semantic_type": semantic_type,
                "target_semantic_group": target_group,
                "rank": int(row.get("rank") or 0),
            }
            relations.append(
                attach_universal_edge(
                    item,
                    subject_cui=cui,
                    object_cui=target_cui,
                )
            )
        return self.merge_research_relation_rows(
            relations,
            [],
            limit_per_category=limit_per_category,
        )

    def relationship_edge_relations_for_cui(
        self,
        cui: str,
        *,
        limit_per_category: int,
    ) -> list[dict]:
        if not self.relationship_edge_index or not cui:
            return []
        source_cui = cui.strip().upper()
        cache_key = (source_cui, limit_per_category)
        cached = getattr(self, "relationship_edge_cache", {}).get(cache_key)
        if cached is not None:
            return [dict(item) for item in cached]
        raw_rows = [
            *self.relationship_edge_index.lookup(source_cui, limit=max(limit_per_category * 8, 48)),
            *self.relationship_edge_index.lookup_incoming(source_cui, limit=max(limit_per_category * 8, 48)),
        ]
        relations = []
        for rank, raw_relation in enumerate(raw_rows, start=1):
            target_cui = str(raw_relation.get("cui") or "").strip().upper()
            if not target_cui or target_cui == source_cui:
                continue
            target_semantic_types = self.semantic_types_for_cui(target_cui)
            target_group = semantic_group_from_types(target_semantic_types)
            category = SEMANTIC_GROUP_RELATION_CATEGORIES.get(target_group, "phenotype")
            relation = str(raw_relation.get("relation") or raw_relation.get("relationship_type") or "associated_with")
            rela = str(raw_relation.get("rela") or relation)
            if str(raw_relation.get("direction") or "") == "incoming":
                relation, rela = inverse_relation_labels(relation, rela)
            label = self.display_label_for_cui(target_cui, [str(raw_relation.get("label") or "").strip()])
            if not label:
                continue
            semantic_type = (
                target_semantic_types[0].get("name")
                or target_semantic_types[0].get("sty")
                if target_semantic_types
                else ""
            )
            item = {
                "cui": target_cui,
                "category": category,
                "category_label": SEMANTIC_VIEW_CATEGORY_LABELS.get(
                    category,
                    category.replace("_", " ").title(),
                ),
                "relation_group": str(raw_relation.get("relation_group") or "associated"),
                "relation": relation,
                "rela": rela,
                "source": str(raw_relation.get("source") or "relationship_edge_jsonl"),
                "source_class": str(raw_relation.get("source_class") or ""),
                "direction": "bidirectional"
                if str(raw_relation.get("direction") or "") == "incoming"
                else str(raw_relation.get("direction") or "outgoing"),
                "label": label,
                "semantic_type": semantic_type,
                "target_semantic_group": target_group,
                "rank": int(raw_relation.get("rank") or rank),
                "strength": raw_relation.get("strength"),
                "confidence": raw_relation.get("confidence"),
            }
            if isinstance(raw_relation.get("edge"), dict):
                item["edge"] = dict(raw_relation["edge"])
            else:
                item = attach_universal_edge(
                    item,
                    subject_cui=source_cui,
                    object_cui=target_cui,
                )
            relations.append(item)
        merged = self.merge_research_relation_rows(
            relations,
            [],
            limit_per_category=limit_per_category,
        )
        if hasattr(self, "relationship_edge_cache"):
            self.relationship_edge_cache[cache_key] = [dict(item) for item in merged]
        return merged

    def legacy_metadata_relations(self, metadata: dict, *, source: str) -> list[dict]:
        relation_specs = (
            ("broader_cuis", "has_broader_concept", "broader concept", "associated"),
            ("narrower_cuis", "has_narrower_concept", "narrower concept", "associated"),
            ("related_cuis", "related_to", "related local support concept", "associated"),
        )
        relations = []
        for field, relation, rela, relation_group in relation_specs:
            values = metadata.get(field) or []
            if isinstance(values, str):
                values = [values]
            if not isinstance(values, list):
                continue
            for value in values:
                target_cui = str(value or "").strip().upper()
                if not target_cui:
                    continue
                relations.append(
                    {
                        "cui": target_cui,
                        "relation": relation,
                        "rela": rela,
                        "relation_group": relation_group,
                        "source": source,
                    }
                )
        return relations

    def drug_rollup_research_relations_for_cui(
        self,
        cui: str,
        *,
        seed_relations: list[dict],
        limit_per_category: int,
    ) -> list[dict]:
        cui = cui.strip().upper()
        if not cui or not self.is_drug_ingredient_cui(cui):
            return []
        cache_key = (cui, limit_per_category)
        cached = getattr(self, "drug_rollup_cache", {}).get(cache_key)
        if cached is not None:
            return [dict(item) for item in cached]
        sources = self.drug_rollup_sources_for_cui(cui, seed_relations=seed_relations)
        rollups: list[dict] = []
        for source in sources:
            rollups.extend(
                self.drug_rollup_rows_from_source(
                    cui,
                    source,
                    limit_per_category=max(2, min(4, limit_per_category)),
                )
            )
        rollups = self.merge_research_relation_rows(
            sorted(
                rollups,
                key=lambda item: (
                    DRUG_ROLLUP_ROLE_PRIORITY.get(str(item.get("rollup_role") or ""), 99),
                    int(item.get("rank") or 0),
                    str(item.get("category") or ""),
                    str(item.get("label") or ""),
                ),
            ),
            [],
            limit_per_category=limit_per_category,
        )
        if hasattr(self, "drug_rollup_cache"):
            self.drug_rollup_cache[cache_key] = [dict(item) for item in rollups]
        return rollups

    def is_drug_ingredient_cui(self, cui: str) -> bool:
        semantic_types = self.semantic_types_for_cui(cui)
        if semantic_group_from_types(semantic_types) != "CHEM":
            return False
        rxnorm_rows = self.mappings_for_cui(cui, sabs=["RXNORM"], limit=25)
        if any(str(row.get("tty") or "").strip().upper() == "IN" for row in rxnorm_rows):
            return True
        names = semantic_type_name_set(semantic_types)
        return "pharmacologic substance" in names and "clinical drug" not in names

    def drug_rollup_sources_for_cui(self, cui: str, *, seed_relations: list[dict]) -> list[dict]:
        base_label = self.display_label_for_cui(cui, [self.record_label_for_cui(cui)])
        if not base_label:
            return []
        candidate_rows: list[dict] = []
        if self.relation_index:
            candidate_rows.extend(
                self.normalize_direction_rows(
                    self.relation_index.lookup(cui, limit=max(self.related_limit * 8, 64))
                )
            )
            candidate_rows.extend(
                self.incoming_related_concepts_for_cui(
                    cui,
                    limit=max(self.related_limit * 8, 64),
                )
            )
        candidate_rows.extend(seed_relations)
        sources: list[dict] = []
        seen: set[str] = set()
        for row in candidate_rows:
            source_cui = str(row.get("cui") or "").strip().upper()
            if not source_cui or source_cui == cui or source_cui in seen:
                continue
            role = self.drug_rollup_role(cui, source_cui, row, base_label=base_label)
            if not role:
                continue
            label = self.display_label_for_cui(
                source_cui,
                [str(row.get("label") or "").strip(), self.record_label_for_cui(source_cui)],
            )
            if not label:
                continue
            seen.add(source_cui)
            sources.append(
                {
                    "cui": source_cui,
                    "label": label,
                    "rollup_role": role,
                    "rollup_relation": str(row.get("relation") or ""),
                    "rollup_rela": str(row.get("rela") or ""),
                    "rollup_source": str(row.get("source") or ""),
                }
            )
            if len(sources) >= 16:
                break
        return sources

    def drug_rollup_role(
        self,
        ingredient_cui: str,
        source_cui: str,
        row: dict,
        *,
        base_label: str,
    ) -> str:
        label = self.display_label_for_cui(
            source_cui,
            [str(row.get("label") or "").strip(), self.record_label_for_cui(source_cui)],
        )
        if not label:
            return "related drug concept"
        label_key = normalized_key(label)
        base_key = normalized_key(base_label)
        label_mentions_drug = bool(base_key and base_key in label_key)
        relation_key = normalized_key(
            " ".join(str(row.get(field) or "") for field in ("relation", "rela", "source"))
        )
        semantic_types = self.semantic_types_for_cui(source_cui)
        semantic_group = semantic_group_from_types(semantic_types)
        semantic_names = semantic_type_name_set(semantic_types)
        rxnorm_ttys = {
            str(mapping.get("tty") or "").strip().upper()
            for mapping in self.mappings_for_cui(source_cui, sabs=["RXNORM"], limit=25)
        }
        if rxnorm_ttys & DRUG_ROLLUP_BRAND_TTYS or "brand" in relation_key:
            return "brand"
        if semantic_group in {"OBS", "PROC"} and label_mentions_drug:
            if any(term in label_key for term in DRUG_ROLLUP_MEASUREMENT_TERMS):
                return "measurement"
        if semantic_group == "PROC" and label_mentions_drug:
            if any(term in label_key for term in DRUG_ROLLUP_THERAPY_TERMS):
                return "therapy"
        if rxnorm_ttys & DRUG_ROLLUP_PRECISE_TTYS and (
            label_mentions_drug or "ingredient" in relation_key or "isa" in relation_key
        ):
            return "salt_or_precise_ingredient"
        if (rxnorm_ttys & DRUG_ROLLUP_CLINICAL_TTYS or "clinical drug" in semantic_names) and (
            label_mentions_drug or "ingredient" in relation_key
        ):
            return "clinical_drug"
        if semantic_group == "CHEM" and label_mentions_drug and (
            "ingredient" in relation_key or "isa" in relation_key
        ):
            return "salt_or_precise_ingredient"
        if semantic_group == "PROC" and label_mentions_drug:
            return "therapy"
        if semantic_group == "CHEM" and label_mentions_drug:
            return "drug_related"
        return ""

    def drug_rollup_rows_from_source(
        self,
        ingredient_cui: str,
        source: dict,
        *,
        limit_per_category: int,
    ) -> list[dict]:
        source_cui = str(source.get("cui") or "").strip().upper()
        if not source_cui or source_cui == ingredient_cui:
            return []
        metadata_relations = self.metadata_relations_for_cui(
            source_cui,
            limit_per_category=limit_per_category,
        )
        indexed_relations = (
            self.normalize_direction_rows(
                self.research_relation_index.lookup(
                    source_cui,
                    limit_per_category=limit_per_category,
                )
            )
            if self.research_relation_index
            else []
        )
        indexed_incoming = self.incoming_research_relations_for_cui(
            source_cui,
            limit_per_category=limit_per_category,
        )
        rows = self.merge_research_relation_rows(
            metadata_relations,
            [*indexed_relations, *indexed_incoming],
            limit_per_category=limit_per_category,
        )
        rolled = []
        for row in rows:
            target_cui = str(row.get("cui") or "").strip().upper()
            if not target_cui or target_cui in {ingredient_cui, source_cui}:
                continue
            if self.should_skip_drug_rollup_target(ingredient_cui, row):
                continue
            item = dict(row)
            item.update(
                {
                    "rollup": True,
                    "rollup_source_cui": source_cui,
                    "rollup_source_label": str(source.get("label") or ""),
                    "rollup_role": str(source.get("rollup_role") or ""),
                    "rollup_via_relation": str(source.get("rollup_relation") or ""),
                    "rollup_via_rela": str(source.get("rollup_rela") or ""),
                    "rollup_via_source": str(source.get("rollup_source") or ""),
                }
            )
            item = attach_universal_edge(
                item,
                subject_cui=ingredient_cui,
                object_cui=target_cui,
            )
            rolled.append(item)
        return rolled

    def should_skip_drug_rollup_target(self, ingredient_cui: str, row: dict) -> bool:
        category = str(row.get("category") or "").strip()
        label_key = normalized_key(str(row.get("label") or ""))
        ingredient_label = self.display_label_for_cui(
            ingredient_cui,
            [self.record_label_for_cui(ingredient_cui)],
        )
        ingredient_key = normalized_key(ingredient_label)
        if category == "drug_chemical":
            return True
        if category == "gene_protein" and ingredient_key and ingredient_key in label_key:
            return not any(term in label_key for term in DRUG_ROLLUP_BIO_LABEL_TERMS)
        return False

    def external_embedding_neighbors_for_cui(self, cui: str, *, limit_per_source: int | None = None) -> list[dict]:
        if not self.external_cui_vector_index or not cui:
            return []
        limit = limit_per_source or self.related_limit
        cache_key = (cui, limit)
        cached = self.external_related_cache.get(cache_key)
        if cached is not None:
            return [dict(item) for item in cached]
        neighbors = []
        for row in self.external_cui_vector_index.lookup(cui, limit_per_source=limit):
            target_cui = str(row.get("cui") or "")
            semantic_types = self.semantic_types_for_cui(target_cui)
            semantic_group = semantic_group_from_types(semantic_types)
            category = EXTERNAL_EMBEDDING_GROUP_CATEGORIES.get(semantic_group, "embedding_neighbor")
            label = self.display_label_for_cui(target_cui, [str(row.get("label") or "")])
            if not label:
                continue
            enriched = dict(row)
            enriched.update(
                {
                    "label": label,
                    "category": category,
                    "category_label": SEMANTIC_VIEW_CATEGORY_LABELS.get(category, "Embedding Neighbors"),
                    "relation_group": "embedding_similarity",
                    "semantic_type": semantic_types[0]["name"] if semantic_types else "",
                    "semantic_group": semantic_group,
                }
            )
            neighbors.append(enriched)
        self.external_related_cache[cache_key] = [dict(item) for item in neighbors]
        return neighbors

    def semantic_views_for_hit(
        self,
        source_hit: dict,
        *,
        limit_per_view: int = 6,
        include_external: bool = True,
    ) -> list[dict]:
        source_cui = str(source_hit.get("cui") or "")
        source_group = semantic_group_from_types(list(source_hit.get("semantic_types") or []))
        relations = list(source_hit.get("research_relations") or [])
        if "research_relations" not in source_hit and source_cui:
            relations = self.research_relations_for_cui(source_cui)
        if include_external:
            external_neighbors = list(source_hit.get("external_embedding_neighbors") or [])
            if "external_embedding_neighbors" not in source_hit and source_cui:
                external_neighbors = self.external_embedding_neighbors_for_cui(source_cui)
            relations.extend(external_neighbors)
        grouped: dict[str, list[dict]] = {}
        for relation in relations:
            category = str(relation.get("category") or "").strip()
            target_cui = str(relation.get("cui") or "").strip()
            if not category or not target_cui:
                continue
            grouped.setdefault(category, []).append(relation)
        if not grouped:
            return []

        preferred_categories = list(
            SEMANTIC_GROUP_VIEW_PRESETS.get(source_group) or SEMANTIC_GROUP_VIEW_PRESETS["OTHER"]
        )
        overflow_categories = sorted(
            (category for category in grouped if category not in preferred_categories),
            key=lambda category: (SEMANTIC_VIEW_CATEGORY_ORDER.get(category, 99), category),
        )
        views = []
        for category in preferred_categories + overflow_categories:
            items = grouped.get(category, [])[:limit_per_view]
            if not items:
                continue
            views.append(
                {
                    "source_cui": source_cui,
                    "source_name": source_hit.get("name") or source_hit.get("label") or "",
                    "source_semantic_group": source_group,
                    "source_semantic_group_label": SEMANTIC_GROUP_LABELS.get(source_group, "Other"),
                    "category": category,
                    "semantic_group": RELATION_CATEGORY_SEMANTIC_GROUPS.get(category, "OTHER"),
                    "semantic_group_label": SEMANTIC_GROUP_LABELS.get(
                        RELATION_CATEGORY_SEMANTIC_GROUPS.get(category, "OTHER"),
                        "Other",
                    ),
                    "title": SEMANTIC_VIEW_CATEGORY_LABELS.get(category, category.replace("_", " ").title()),
                    "items": [dict(item) for item in items],
                }
            )
        return views

    def semantic_views_for_hits(
        self,
        hits: list[dict],
        *,
        limit_per_view: int = 6,
        include_external: bool = True,
    ) -> list[dict]:
        if not hits:
            return []
        return self.semantic_views_for_hit(
            hits[0],
            limit_per_view=limit_per_view,
            include_external=include_external,
        )

    def semantic_view_sources_for_hits(
        self,
        hits: list[dict],
        *,
        source_limit: int | None = None,
        limit_per_view: int = 6,
        include_external: bool = True,
    ) -> list[dict]:
        sources = []
        source_hits = hits if source_limit is None else hits[:source_limit]
        for rank, hit in enumerate(source_hits, start=1):
            views = self.semantic_views_for_hit(
                hit,
                limit_per_view=limit_per_view,
                include_external=include_external,
            )
            if not views:
                continue
            source_group = semantic_group_from_types(list(hit.get("semantic_types") or []))
            sources.append(
                {
                    "rank": rank,
                    "source_cui": hit.get("cui") or "",
                    "source_name": hit.get("name") or hit.get("label") or "",
                    "source_semantic_group": source_group,
                    "source_semantic_group_label": SEMANTIC_GROUP_LABELS.get(source_group, "Other"),
                    "views": views,
                }
            )
        return sources

    def semantic_group_views_from_sources(
        self,
        sources: list[dict],
        *,
        limit_per_group: int = 12,
    ) -> list[dict]:
        grouped: dict[str, dict] = {}
        seen_targets: dict[str, set[str]] = {}
        for source in sources:
            source_rank = int(source.get("rank") or 0)
            source_cui = str(source.get("source_cui") or "")
            source_name = str(source.get("source_name") or "")
            source_group_label = str(source.get("source_semantic_group_label") or "")
            for view in source.get("views") or []:
                semantic_group = str(view.get("semantic_group") or "OTHER")
                bucket = grouped.setdefault(
                    semantic_group,
                    {
                        "semantic_group": semantic_group,
                        "semantic_group_label": view.get("semantic_group_label") or SEMANTIC_GROUP_LABELS.get(
                            semantic_group,
                            "Other",
                        ),
                        "items": [],
                        "source_ranks": [],
                    },
                )
                seen = seen_targets.setdefault(semantic_group, set())
                for item in view.get("items") or []:
                    if len(bucket["items"]) >= limit_per_group:
                        break
                    target_cui = str(item.get("cui") or "")
                    if not target_cui or target_cui in seen:
                        continue
                    seen.add(target_cui)
                    enriched = dict(item)
                    enriched["source_rank"] = source_rank
                    enriched["source_cui"] = source_cui
                    enriched["source_name"] = source_name
                    enriched["source_semantic_group_label"] = source_group_label
                    bucket["items"].append(enriched)
                    if source_rank and source_rank not in bucket["source_ranks"]:
                        bucket["source_ranks"].append(source_rank)

        return [
            {
                "semantic_group": group["semantic_group"],
                "semantic_group_label": group["semantic_group_label"],
                "source_ranks": group["source_ranks"],
                "source_count": len(group["source_ranks"]),
                "items": group["items"],
            }
            for group in sorted(
                grouped.values(),
                key=lambda item: (
                    SEMANTIC_GROUP_VIEW_ORDER.get(str(item.get("semantic_group") or ""), 99),
                    str(item.get("semantic_group_label") or ""),
                ),
            )
            if group["items"]
        ]

    def semantic_response_metadata(
        self,
        hits: list[dict],
        *,
        include_related: bool = True,
        semantic_bucket_keys: object = None,
    ) -> dict:
        top_group = semantic_group_from_types(list(hits[0].get("semantic_types") or [])) if hits else ""
        semantic_view_sources = []
        semantic_group_views = []
        semantic_views = []
        if include_related:
            semantic_view_sources = self.semantic_view_sources_for_hits(
                hits,
                source_limit=getattr(self, "related_source_limit", 16),
                include_external=True,
            )
            semantic_group_views = self.semantic_group_views_from_sources(semantic_view_sources)
            semantic_views = self.semantic_views_for_hits(hits, include_external=True)
        return {
            "top_semantic_group": top_group,
            "top_semantic_group_label": SEMANTIC_GROUP_LABELS.get(top_group, "Other") if top_group else "",
            "semantic_views": semantic_views,
            "semantic_view_sources": semantic_view_sources,
            "semantic_group_views": semantic_group_views,
            "semantic_result_buckets": semantic_result_buckets_for_response(
                hits,
                semantic_group_views,
                semantic_bucket_keys=semantic_bucket_keys,
            ),
            "related_result_buckets": related_result_buckets_for_response(
                semantic_group_views if include_related else [],
                semantic_bucket_keys=semantic_bucket_keys,
            ),
        }

    def compact_evidence_related_hits(self, hits: list[dict], *, source_cui: str = "") -> list[dict]:
        related = []
        for hit in hits:
            labels = list(hit.get("labels") or [])
            label = self.display_label_for_cui(str(hit.get("cui") or ""), labels)
            if not label:
                continue
            item = {
                "cui": hit.get("cui") or "",
                "label": label,
                "relation": "evidence_vector",
                "rela": "evidence similarity",
                "source": "real-world evidence",
                "score": hit.get("score"),
                "doc_id": hit.get("doc_id") or "",
                "view": hit.get("view") or "",
                "evidence_count": int(hit.get("evidence_count") or 0),
                "seed_doc_id": hit.get("seed_doc_id") or "",
            }
            if source_cui:
                item = attach_universal_edge(
                    item,
                    subject_cui=source_cui,
                    object_cui=str(hit.get("cui") or ""),
                )
            related.append(item)
        return related

    def evidence_related_concepts_for_cui(self, cui: str, *, top_k: int | None = None) -> list[dict]:
        limit = top_k or self.related_limit
        if limit <= 0:
            return []
        cache_key = (cui, limit)
        cached = self.evidence_related_cache.get(cache_key)
        if cached is not None:
            return [dict(item) for item in cached]
        related = self.compact_evidence_related_hits(
            self.evidence_vector_neighbors_for_cui(cui, top_k=limit),
            source_cui=cui,
        )
        self.evidence_related_cache[cache_key] = related
        return [dict(item) for item in related]

    def attach_related_concepts(self, hits: list[dict]) -> None:
        related_source_limit = max(0, int(getattr(self, "related_source_limit", 16) or 0))
        expensive_source_limit = max(0, int(getattr(self, "expensive_related_source_limit", 0) or 0))
        for index, hit in enumerate(hits):
            cui = str(hit.get("cui") or "")
            in_related_scope = index < related_source_limit
            in_expensive_scope = index < expensive_source_limit
            evidence_related = self.evidence_related_concepts_for_cui(cui) if in_expensive_scope else []
            external_related = self.external_embedding_neighbors_for_cui(cui) if in_related_scope else []
            mrrel_related = self.related_concepts_for_cui(cui) if in_related_scope else []
            research_relations = self.research_relations_for_cui(cui) if in_related_scope else []
            hit["evidence_related_concepts"] = evidence_related
            hit["external_embedding_neighbors"] = external_related
            hit["mrrel_related_concepts"] = mrrel_related
            hit["research_relations"] = research_relations
            hit["related_concepts"] = evidence_related or external_related or mrrel_related
            hit["related_source"] = (
                "evidence_vectors"
                if evidence_related
                else ("external_embeddings" if external_related else ("mrrel" if mrrel_related else ""))
            )

    def related_bundle(
        self,
        cui: str,
        *,
        top_k: int = 10,
        mapping_sabs: list[str] | None = None,
    ) -> dict:
        cui = cui.strip().upper()
        mrrel_neighbors = self.related_concepts_for_cui(cui)
        vector_neighbors = self.evidence_vector_neighbors_for_cui(cui, top_k=top_k)
        evidence_related = self.compact_evidence_related_hits(vector_neighbors, source_cui=cui)
        self.evidence_related_cache[(cui, top_k)] = evidence_related
        external_neighbors = self.external_embedding_neighbors_for_cui(cui, limit_per_source=top_k)
        mappings = self.mappings_for_cui(cui, sabs=mapping_sabs, limit=100)
        research_relations = self.research_relations_for_cui(cui)
        return {
            "cui": cui,
            "related_concepts": evidence_related or external_neighbors or mrrel_neighbors,
            "related_source": (
                "evidence_vectors"
                if evidence_related
                else ("external_embeddings" if external_neighbors else ("mrrel" if mrrel_neighbors else ""))
            ),
            "mrrel_neighbors": mrrel_neighbors,
            "research_relations": research_relations,
            "external_embedding_neighbors": external_neighbors,
            "evidence_related_concepts": evidence_related,
            "evidence_vector_neighbors": vector_neighbors,
            "mappings": mappings,
        }
