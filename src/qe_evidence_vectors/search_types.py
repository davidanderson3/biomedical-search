from __future__ import annotations

from typing import TypedDict


class SemanticType(TypedDict, total=False):
    tui: str
    stn: str
    name: str
    atui: str


class RelatedConcept(TypedDict, total=False):
    cui: str
    label: str
    category: str
    category_label: str
    relation_group: str
    relation: str
    rela: str
    source: str
    direction: str
    semantic_type: str
    semantic_group: str
    semantic_group_label: str
    rank: int
    source_rank: int
    source_cui: str
    source_name: str


class ScoreBreakdown(TypedDict, total=False):
    rank_score: float
    retrieval_score: float
    lexical_component: float
    vector_component: float
    label_fallback_component: float
    exact_label_component: float
    exact_primary_name_component: float
    exact_span_component: float
    exact_pharmacologic_component: float
    treatment_pharmacologic_component: float
    mention_frequency_component: float
    mention_count: int
    evidence_component: float
    primary_name_component: float
    negated_finding_component: float
    semantic_component: float
    evidence_context_component: float
    definition_component: float
    mrrel_component: float
    long_document_support_component: float
    composite_intent_component: float
    lab_result_abnormal_component: float
    specificity_component: float
    generic_penalty: float
    broad_label_penalty: float
    relative_specificity_penalty: float
    clinical_context_sense_penalty: float
    role_mismatch_penalty: float
    numeric_specificity_penalty: float
    numeric_context_fragment_penalty: float
    action_observation_penalty: float
    denied_positive_finding_penalty: float
    denied_context_mismatch_penalty: float
    denied_assertion_penalty: float
    composite_component_penalty: float
    sepsis_subtype_penalty: float
    semantic_fragment_penalty: float
    generic_fragment_penalty: float
    normal_exam_fragment_penalty: float
    assertion_context_penalty: float
    assertion: dict
    lexical_fallback_used: bool
    retrieval_kind: str


class SearchHit(TypedDict, total=False):
    doc_id: str
    cui: str
    name: str
    view: str
    score: float
    rank_score: float
    labels: list[str]
    sources: list[str]
    evidence_count: int
    match_type: str
    text: str
    semantic_types: list[SemanticType]
    semantic_group: str
    semantic_group_label: str
    related_concepts: list[RelatedConcept]
    score_breakdown: ScoreBreakdown
    assertion: dict
