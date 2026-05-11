from __future__ import annotations

import math
from typing import Any


CURATED_PROVENANCE = {
    "ATC",
    "DRUGBANK",
    "FDB",
    "HPO",
    "LNC",
    "MED-RT",
    "MEDI",
    "MEDLINEPLUS",
    "MEDRT",
    "MSH",
    "MTH",
    "MTHSPL",
    "NCI",
    "OMIM",
    "RXNORM",
    "SNOMEDCT_US",
}


def _key(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _clamp01(value: float, *, default: float = 0.0) -> float:
    if not math.isfinite(value):
        value = default
    return round(max(0.0, min(1.0, value)), 3)


def relationship_type_for(
    *,
    relation: str = "",
    rela: str = "",
    relation_group: str = "",
) -> str:
    relation_key = _key(relation)
    rela_key = _key(rela)
    group_key = _key(relation_group)
    text = " ".join(item for item in (relation_key, rela_key, group_key) if item)
    if not text:
        return "associated_with"

    if "contraindicat" in text:
        return "contraindicated_with"
    if any(
        marker in text
        for marker in (
            "has_adverse_effect",
            "has_adverse_reaction",
            "adverse_effect",
            "adverse_reaction",
            "causative_agent",
            "may_cause",
            "cause_of",
        )
    ):
        return "causes"
    if any(
        marker in text
        for marker in (
            "indicated_for",
            "has_indicated_treatment",
            "has_therapy",
            "may_be_treated_by",
            "may_treat",
            "may_prevent",
            "may_be_prevented_by",
            "prevents_or_treats",
            "therapy",
            "treatment",
            "used_for",
        )
    ):
        return "treats"
    if any(marker in text for marker in ("temporal_precedes", "precedes", "prior_to")):
        return "precedes"
    if any(marker in text for marker in ("temporal_follows", "follows", "after")):
        return "follows"
    if any(marker in text for marker in ("part_of", "has_part")):
        return "part_of"
    if any(marker in text for marker in ("member_of", "has_member")):
        return "member_of"
    if any(marker in text for marker in ("isa", "is_a", "has_broader_concept", "broader_concept")):
        return "is_a"
    if any(marker in text for marker in ("has_narrower_concept", "narrower_concept")):
        return "has_subclass"
    if "associated" in text or group_key in {
        "embedding_similarity",
        "genetic_association",
        "phenotype",
        "procedure_or_test",
    }:
        return "associated_with"
    return rela_key or relation_key or "associated_with"


def evidence_method_for_source(source: str, *, relation_group: str = "", relation: str = "") -> str:
    source_key = _key(source)
    relation_text = " ".join((_key(relation_group), _key(relation)))
    if any(marker in source_key for marker in ("clinical_trial", "trial")):
        return "clinical_trial"
    if any(marker in source_key or marker in relation_text for marker in ("temporal", "longitudinal")):
        return "temporal_analysis"
    if any(
        marker in source_key or marker in relation_text
        for marker in (
            "bioconceptvec",
            "cui2vec",
            "evidence_vector",
            "embedding",
            "external_vector",
            "co_occurrence",
            "cooccurrence",
        )
    ):
        return "co_occurrence"
    if any(
        marker in source_key
        for marker in (
            "concept_document",
            "dailymed",
            "drug_enrichment",
            "literature",
            "openalex",
            "openfda",
            "pmc",
            "pubmed",
            "wikipedia",
        )
    ):
        return "literature_mined"
    if source.strip().upper() in CURATED_PROVENANCE:
        return "curated"
    return "curated"


def directionality_for(*, direction: str = "", relationship_type: str = "") -> str:
    direction_key = _key(direction)
    if relationship_type in {"associated_with", "contraindicated_with"}:
        return "bidirectional" if direction_key in {"", "incoming", "outgoing", "bidirectional"} else direction_key
    if relationship_type == "precedes":
        return "temporal_precedes"
    if relationship_type == "follows":
        return "temporal_follows"
    if direction_key == "incoming":
        return "object_to_subject"
    if direction_key == "bidirectional":
        return "bidirectional"
    return "subject_to_object"


def _numeric_support_count(row: dict[str, Any], support_count: Any = None) -> int:
    value = support_count if support_count is not None else row.get("support_count")
    explicit = _safe_float(value)
    if explicit is not None:
        return max(0, int(explicit))
    count = 0
    for field in ("supporting_pmids", "supporting_doc_ids", "supporting_titles"):
        values = row.get(field)
        if isinstance(values, list):
            count = max(count, len(values))
    return count


def _default_strength(
    *,
    row: dict[str, Any],
    method: str,
    relationship_type: str,
    support_count: int,
    rank: int,
) -> float:
    for field in ("strength", "weight", "score", "similarity"):
        explicit = _safe_float(row.get(field))
        if explicit is not None:
            return _clamp01(explicit)

    base = {
        "clinical_trial": 0.85,
        "curated": 0.76,
        "expert_opinion": 0.55,
        "literature_mined": 0.62,
        "temporal_analysis": 0.68,
        "co_occurrence": 0.46,
    }.get(method, 0.55)
    if relationship_type in {"causes", "contraindicated_with", "is_a", "part_of", "treats"}:
        base += 0.04
    if relationship_type == "associated_with":
        base -= 0.03
    if support_count:
        base += min(support_count, 10) * 0.015
    if rank > 1:
        base -= min((rank - 1) * 0.015, 0.18)
    return _clamp01(base)


def _default_confidence(
    *,
    method: str,
    provenance: str,
    support_count: int,
    rank: int,
) -> float:
    base = {
        "clinical_trial": 0.88,
        "curated": 0.82,
        "expert_opinion": 0.52,
        "literature_mined": 0.58,
        "temporal_analysis": 0.66,
        "co_occurrence": 0.42,
    }.get(method, 0.5)
    if provenance.strip().upper() in CURATED_PROVENANCE:
        base += 0.04
    if support_count:
        base += min(support_count, 10) * 0.02
    if rank > 1:
        base -= min((rank - 1) * 0.01, 0.12)
    return _clamp01(base)


def _structured_context(
    row: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = dict(context or {})
    for field in (
        "population",
        "clinical_setting",
        "disease_stage",
        "severity",
        "line_of_therapy",
        "geography",
        "time_period",
    ):
        value = row.get(field)
        if value not in (None, "", [], {}):
            result[field] = value
    if row.get("rollup"):
        result["rollup"] = {
            "via_cui": str(row.get("rollup_source_cui") or ""),
            "via_label": str(row.get("rollup_source_label") or ""),
            "role": str(row.get("rollup_role") or ""),
            "via_relation": str(row.get("rollup_via_rela") or row.get("rollup_via_relation") or ""),
            "via_source": str(row.get("rollup_via_source") or ""),
        }
    return result


def universal_relationship_edge(
    *,
    subject_cui: str,
    object_cui: str,
    relation: str = "",
    rela: str = "",
    relation_group: str = "",
    source: str = "",
    direction: str = "",
    row: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(row or {})
    relationship_type = relationship_type_for(
        relation=relation,
        rela=rela,
        relation_group=relation_group,
    )
    method = evidence_method_for_source(source, relation_group=relation_group, relation=relation)
    provenance = str(source or "unknown").strip() or "unknown"
    rank = max(0, int(_safe_float(payload.get("rank")) or 0))
    support_count = _numeric_support_count(payload)
    evidence: dict[str, Any] = {
        "method": method,
        "provenance": provenance,
    }
    if support_count:
        evidence["support_count"] = support_count
    for field in ("supporting_pmids", "supporting_doc_ids", "supporting_titles"):
        values = payload.get(field)
        if isinstance(values, list) and values:
            evidence[field] = list(values)
    return {
        "subject": str(subject_cui or "").strip().upper(),
        "object": str(object_cui or "").strip().upper(),
        "type": relationship_type,
        "strength": _default_strength(
            row=payload,
            method=method,
            relationship_type=relationship_type,
            support_count=support_count,
            rank=rank,
        ),
        "strength_metric": "normalized_score",
        "directionality": directionality_for(
            direction=direction,
            relationship_type=relationship_type,
        ),
        "evidence": evidence,
        "context": _structured_context(payload, context=context),
        "confidence": _default_confidence(
            method=method,
            provenance=provenance,
            support_count=support_count,
            rank=rank,
        ),
    }


def attach_universal_edge(
    row: dict[str, Any],
    *,
    subject_cui: str,
    object_cui: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = dict(row)
    target_cui = object_cui or str(item.get("cui") or item.get("target_cui") or "").strip().upper()
    item["edge"] = universal_relationship_edge(
        subject_cui=subject_cui,
        object_cui=target_cui,
        relation=str(item.get("relation") or ""),
        rela=str(item.get("rela") or ""),
        relation_group=str(item.get("relation_group") or ""),
        source=str(item.get("source") or item.get("sab") or ""),
        direction=str(item.get("direction") or ""),
        row=item,
        context=context,
    )
    return item
