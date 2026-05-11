from __future__ import annotations

import re

from qe_evidence_vectors.text import normalized_key
from qe_evidence_vectors.search_denial import (
    denied_context_mismatch_penalty_for_hit,
    denied_positive_finding_penalty_for_hit,
    denied_scope_specific_token_set,
    denial_scope_token_lists,
    has_denial_context,
    label_is_negated,
    label_is_low_quality_negated_fragment,
)
from qe_evidence_vectors.search_hit_features import (
    hit_matched_specific_tokens,
    is_contiguous_subsequence,
    is_ordered_subsequence,
    label_tokens_for_hit,
    numeric_query_anchor_tokens,
    rare_query_anchor_tokens,
    semantic_type_names,
    specific_query_token_set,
)
from qe_evidence_vectors.search_label_scoring import (
    exact_label_match,
    exact_primary_name_match,
    is_broad_primary_label,
    is_disambiguated_homonym_label,
    is_generic_label,
    label_relevance,
    semantic_query_boost,
    should_suppress_label_fallback_hit,
)
from qe_evidence_vectors.search_tokens import (
    RANK_STOPWORDS,
    SINGULAR_S_TOKENS,
    TOKEN_ALIASES,
    canonical_token,
    content_tokens,
)
from qe_evidence_vectors.search_mrrel import (
    MRREL_CATEGORY_ROLE_TOKENS,
    MRREL_RANK_COMPONENT_CAP,
    mrrel_component_for_relation_rows,
    mrrel_relation_group_from_relation,
    relation_category_matches_query_role,
)
from qe_evidence_vectors.search_role_tokens import (
    ACTION_OBSERVATION_LABEL_TOKENS,
    ACTION_OBSERVATION_QUERY_TOKENS,
    DRUG_ROLE_QUERY_TOKENS,
    OBSERVATION_STATE_QUERY_TOKENS,
    PHARMACOLOGIC_SEMANTIC_TYPES,
    PROCEDURE_ROLE_TOKENS,
    PROCEDURE_SEMANTIC_TYPES,
    THERAPEUTIC_ACTION_QUERY_TOKENS,
)
from qe_evidence_vectors.search_ranking_constants import (
    ALLOWED_DENIAL_ANCHOR_SPANS,
    COGNITIVE_MEMORY_CONTEXT_TOKENS,
    COGNITIVE_MEMORY_LABEL_TOKENS,
    COMPOSITE_CONTEXT_SEMANTIC_TYPES,
    FRAGMENT_SEMANTIC_TYPES,
    INFECTION_SITE_TOKENS,
    LOW_SPECIFICITY_QUERY_TOKENS,
    MODIFIER_FRAGMENT_LABEL_TOKENS,
    MODIFIER_FRAGMENT_PENALTY,
    MODIFIER_FRAGMENT_SEMANTIC_TYPES,
    NEGATION_QUERY_TOKENS,
    NORMAL_EXAM_ALLOWED_LABEL_TOKENS,
    NORMAL_EXAM_CONTEXT_TOKENS,
    NORMAL_EXAM_FRAGMENT_TOKENS,
    NUMERIC_CONTEXT_FRAGMENT_PENALTY,
    NUMERIC_SPECIFICITY_CONTEXT_TOKENS,
    PROCEDURE_LABEL_SUFFIXES,
    SEPSIS_ETIOLOGY_SUBTYPE_TOKENS,
    SEPSIS_SHOCK_ANCHOR_TOKENS,
    THERAPY_TRANSITION_ALLOWED_LABEL_TOKENS,
    THERAPY_TRANSITION_CONTEXT_TOKENS,
)
from qe_evidence_vectors.search_semantics import (
    DRUG_CHEMICAL_VIEW_SEMANTIC_TYPES,
    EXTERNAL_EMBEDDING_GROUP_CATEGORIES,
    GENE_PROTEIN_VIEW_SEMANTIC_TYPES,
    RELATION_CATEGORY_SEMANTIC_GROUPS,
    SEMANTIC_GROUP_LABELS,
    SEMANTIC_GROUP_RELATION_CATEGORIES,
    SEMANTIC_GROUP_VIEW_ORDER,
    SEMANTIC_GROUP_VIEW_PRESETS,
    SEMANTIC_VIEW_CATEGORY_LABELS,
    SEMANTIC_VIEW_CATEGORY_ORDER,
    semantic_group_from_types,
    semantic_group_metadata,
)
from qe_evidence_vectors.search_utils import dot, source_mix_from_evidence_items
from qe_evidence_vectors.search_types import ScoreBreakdown, SearchHit


def score_breakdown_for_hit(
    *,
    query: str,
    query_tokens: list[str],
    query_set: set[str],
    raw_query_tokens: set[str],
    raw_query_token_list: list[str],
    negative_adherence_context: bool,
    hit: SearchHit,
) -> ScoreBreakdown:
    labels = list(hit.get("labels") or [])
    if hit.get("name"):
        labels.insert(0, str(hit["name"]))
    lexical_score = max((label_relevance(query_tokens, label) for label in labels), default=0.0)
    all_label_tokens = set()
    for label in labels:
        all_label_tokens.update(content_tokens(label))
    if negative_adherence_context and (
        {"nonadherence", "noncompliance"} & all_label_tokens
        or ("poor" in all_label_tokens and {"compliance", "adherence"} & all_label_tokens)
    ):
        lexical_score = max(lexical_score, 1.08)
    if negative_adherence_context and all_label_tokens == {"medication", "adherence"}:
        lexical_score = max(0.0, lexical_score - 0.12)

    raw_score = float(hit.get("score") or 0.0)
    has_label_match = hit.get("match_type") == "umls_label"
    vector_score_preserved = bool(hit.get("vector_score_preserved"))
    is_pure_label_match = has_label_match and not vector_score_preserved
    vector_component = 0.0 if is_pure_label_match else 0.12 * min(max((raw_score - 0.72) / 0.18, 0.0), 1.0)
    label_component = 0.03 if has_label_match else 0.0
    query_norm = " ".join(raw_query_token_list)
    exact_label_component = 0.18 if exact_label_match(query_norm, labels) else 0.0
    exact_primary_name_component = 0.32 if exact_primary_name_match(query_norm, hit, labels) else 0.0
    exact_span_component = exact_matched_span_component(
        hit,
        labels=labels,
        query_set=query_set,
    )
    exact_pharmacologic_component = exact_pharmacologic_source_component(
        hit,
        exact_span_component=exact_span_component,
    )
    curated_exact_label_component = curated_exact_label_component_for_hit(
        hit,
        exact_span_component=exact_span_component,
    )
    numeric_specificity_penalty = numeric_specificity_mismatch_penalty(
        query_tokens=query_tokens,
        label_tokens=all_label_tokens,
        hit=hit,
    )
    numeric_context_fragment_penalty = numeric_context_fragment_penalty_for_hit(
        query_tokens=query_tokens,
        label_tokens=all_label_tokens,
    )
    evidence_count = int(hit.get("evidence_count") or 0)
    evidence_component = 0.04 if evidence_count > 0 else -0.10
    denial_context = has_denial_context(raw_query_tokens)
    negated_finding_component = 0.0
    if denial_context:
        for label in labels:
            if label_is_negated(label):
                label_tokens = set(content_tokens(label))
                if label_tokens and label_tokens & query_set:
                    negated_finding_component = 0.14
                    break
    denied_positive_finding_penalty = denied_positive_finding_penalty_for_hit(
        raw_query_tokens=raw_query_tokens,
        raw_query_token_list=raw_query_token_list,
        query_tokens=query_tokens,
        label_tokens=all_label_tokens,
        labels=labels,
        hit=hit,
    )
    denied_context_mismatch_penalty = (
        0.0
        if denied_positive_finding_penalty > 0.0
        else denied_context_mismatch_penalty_for_hit(
            raw_query_tokens=raw_query_tokens,
            raw_query_token_list=raw_query_token_list,
            label_tokens=all_label_tokens,
            labels=labels,
            hit=hit,
        )
    )
    primary_tokens = content_tokens(str(hit.get("name") or ""))
    primary_name_component = (
        0.04
        if primary_tokens
        and set(primary_tokens).issubset(query_set)
        and not is_generic_label([str(hit.get("name") or "")])
        and numeric_specificity_penalty <= 0.0
        and denied_positive_finding_penalty <= 0.0
        else 0.0
    )
    generic_penalty = 0.25 if is_generic_label(labels) else 0.0
    broad_label_penalty = broad_label_penalty_for_hit(
        query_tokens=query_tokens,
        label_tokens=all_label_tokens,
        hit=hit,
        is_exact_match=exact_label_component > 0.0 or exact_primary_name_component > 0.0,
    )
    lexical_fallback_used = False
    if lexical_score <= 0.0:
        lexical_score = 0.24
        lexical_fallback_used = True
    semantic_component = (
        0.0
        if denied_positive_finding_penalty > 0.0
        else semantic_query_boost(query_set, all_label_tokens, hit)
    )
    specificity_component = (
        0.0
        if (
            numeric_specificity_penalty > 0.0
            or numeric_context_fragment_penalty > 0.0
            or denied_positive_finding_penalty > 0.0
        )
        else query_specificity_component(query_tokens, all_label_tokens)
    )
    role_mismatch_penalty = query_role_mismatch_penalty(
        query_set=query_set,
        label_tokens=all_label_tokens,
        labels=labels,
        hit=hit,
    )
    action_observation_penalty = action_observation_mismatch_penalty(
        query_set=query_set,
        label_tokens=all_label_tokens,
        labels=labels,
        hit=hit,
    )
    semantic_fragment_penalty = semantic_fragment_mismatch_penalty(
        query_tokens=query_tokens,
        label_tokens=all_label_tokens,
        hit=hit,
    )
    evidence_context_component = (
        0.0
        if denied_positive_finding_penalty > 0.0
        else evidence_context_component_for_hit(
            query_tokens=query_tokens,
            label_tokens=all_label_tokens,
            hit=hit,
        )
    )
    definition_component, definition_matched_tokens = definition_component_for_hit(
        query_tokens=query_tokens,
        label_tokens=all_label_tokens,
        hit=hit,
    )
    mrrel_component = (
        0.0
        if denied_positive_finding_penalty > 0.0
        else min(max(float(hit.get("mrrel_component") or 0.0), 0.0), MRREL_RANK_COMPONENT_CAP)
    )
    mrrel_matched_tokens = sorted(
        {
            canonical_token(str(token))
            for token in hit.get("mrrel_matched_tokens") or []
            if canonical_token(str(token))
        }
    )
    mrrel_signal_reasons = list(hit.get("mrrel_signal_reasons") or [])
    composite_intent_component = composite_intent_component_for_hit(
        query_tokens=query_tokens,
        label_tokens=all_label_tokens,
        hit=hit,
    )
    lab_result_composite_component = lab_result_composite_component_for_hit(
        query_tokens=query_tokens,
        label_tokens=all_label_tokens,
        hit=hit,
    )
    composite_component_penalty = composite_component_penalty_for_hit(
        query_tokens=query_tokens,
        label_tokens=all_label_tokens,
        hit=hit,
    )
    first_statement_component = first_statement_component_for_hit(
        query=query,
        labels=labels,
        hit=hit,
    )
    organism_support_penalty = organism_support_penalty_for_hit(
        query=query,
        labels=labels,
        hit=hit,
    )
    local_extension_phrase_component = local_extension_phrase_component_for_hit(
        query=query,
        labels=labels,
        hit=hit,
    )
    comparator_arm_penalty = comparator_arm_penalty_for_hit(
        query=query,
        labels=labels,
        hit=hit,
    )
    sepsis_subtype_penalty = sepsis_subtype_penalty_for_hit(
        query_tokens=query_tokens,
        label_tokens=all_label_tokens,
    )
    generic_fragment_penalty = generic_query_fragment_penalty(
        query_tokens=query_tokens,
        label_tokens=all_label_tokens,
    )
    normal_exam_fragment_penalty = normal_exam_fragment_penalty_for_hit(
        query_tokens=query_tokens,
        label_tokens=all_label_tokens,
        hit=hit,
    )
    clinical_context_sense_penalty = clinical_context_sense_penalty_for_hit(
        query_tokens=query_tokens,
        raw_query_tokens=raw_query_tokens,
        label_tokens=all_label_tokens,
        labels=labels,
        hit=hit,
    )
    rank_score = (
        lexical_score
        + vector_component
        + label_component
        + exact_label_component
        + exact_primary_name_component
        + exact_span_component
        + exact_pharmacologic_component
        + curated_exact_label_component
        + evidence_component
        + primary_name_component
        + negated_finding_component
        + semantic_component
        + evidence_context_component
        + definition_component
        + mrrel_component
        + composite_intent_component
        + lab_result_composite_component
        + first_statement_component
        + local_extension_phrase_component
        + specificity_component
        - generic_penalty
        - broad_label_penalty
        - role_mismatch_penalty
        - numeric_specificity_penalty
        - numeric_context_fragment_penalty
        - action_observation_penalty
        - denied_positive_finding_penalty
        - denied_context_mismatch_penalty
        - composite_component_penalty
        - comparator_arm_penalty
        - organism_support_penalty
        - sepsis_subtype_penalty
        - semantic_fragment_penalty
        - generic_fragment_penalty
        - normal_exam_fragment_penalty
        - clinical_context_sense_penalty
    )
    return {
        "rank_score": round(rank_score, 6),
        "retrieval_score": round(raw_score, 6),
        "lexical_component": round(lexical_score, 6),
        "vector_component": round(vector_component, 6),
        "label_fallback_component": round(label_component, 6),
        "exact_label_component": round(exact_label_component, 6),
        "exact_primary_name_component": round(exact_primary_name_component, 6),
        "exact_span_component": round(exact_span_component, 6),
        "exact_pharmacologic_component": round(exact_pharmacologic_component, 6),
        "curated_exact_label_component": round(curated_exact_label_component, 6),
        "evidence_component": round(evidence_component, 6),
        "primary_name_component": round(primary_name_component, 6),
        "negated_finding_component": round(negated_finding_component, 6),
        "denied_positive_finding_penalty": round(denied_positive_finding_penalty, 6),
        "denied_context_mismatch_penalty": round(denied_context_mismatch_penalty, 6),
        "semantic_component": round(semantic_component, 6),
        "evidence_context_component": round(evidence_context_component, 6),
        "definition_component": round(definition_component, 6),
        "definition_matched_tokens": definition_matched_tokens,
        "mrrel_component": round(mrrel_component, 6),
        "mrrel_matched_tokens": mrrel_matched_tokens,
        "mrrel_signal_reasons": mrrel_signal_reasons,
        "composite_intent_component": round(composite_intent_component, 6),
        "lab_result_composite_component": round(lab_result_composite_component, 6),
        "first_statement_component": round(first_statement_component, 6),
        "local_extension_phrase_component": round(local_extension_phrase_component, 6),
        "specificity_component": round(specificity_component, 6),
        "generic_penalty": round(generic_penalty, 6),
        "broad_label_penalty": round(broad_label_penalty, 6),
        "relative_specificity_penalty": 0.0,
        "clinical_context_sense_penalty": round(clinical_context_sense_penalty, 6),
        "role_mismatch_penalty": round(role_mismatch_penalty, 6),
        "numeric_specificity_penalty": round(numeric_specificity_penalty, 6),
        "numeric_context_fragment_penalty": round(numeric_context_fragment_penalty, 6),
        "action_observation_penalty": round(action_observation_penalty, 6),
        "composite_component_penalty": round(composite_component_penalty, 6),
        "comparator_arm_penalty": round(comparator_arm_penalty, 6),
        "organism_support_penalty": round(organism_support_penalty, 6),
        "sepsis_subtype_penalty": round(sepsis_subtype_penalty, 6),
        "semantic_fragment_penalty": round(semantic_fragment_penalty, 6),
        "generic_fragment_penalty": round(generic_fragment_penalty, 6),
        "normal_exam_fragment_penalty": round(normal_exam_fragment_penalty, 6),
        "lexical_fallback_used": lexical_fallback_used,
        "retrieval_kind": (
            "label_enriched_semantic_vector"
            if vector_score_preserved
            else (
                "definition_enriched_semantic_vector"
                if hit.get("definition_score_preserved")
                else (
                    "umls_label"
                    if has_label_match
                    else ("umls_definition" if hit.get("match_type") == "umls_definition" else "semantic_vector")
                )
            )
        ),
    }


def rank_hits(query: str, hits: list[SearchHit], *, top_k: int) -> list[SearchHit]:
    query_tokens = content_tokens(query)
    query_set = set(query_tokens)
    raw_query_token_list = normalized_key(query).split()
    raw_query_tokens = set(raw_query_token_list)
    negative_adherence_context = bool(
        {"inconsistent", "unable", "recall", "poor", "missed", "forget", "forgot", "nonadherence"}
        & query_set
    ) and bool({"adherence", "medication", "prescription"} & query_set)
    ranked = []
    for hit in hits:
        breakdown = score_breakdown_for_hit(
            query=query,
            query_tokens=query_tokens,
            query_set=query_set,
            raw_query_tokens=raw_query_tokens,
            raw_query_token_list=raw_query_token_list,
            negative_adherence_context=negative_adherence_context,
            hit=hit,
        )
        hit["rank_score"] = breakdown["rank_score"]
        hit["score_breakdown"] = breakdown
        ranked.append(hit)
    apply_relative_specificity_penalties(ranked, query_tokens=query_tokens)
    ranked = sorted(
        ranked,
        key=lambda item: (
            -float(item.get("rank_score") or 0.0),
            -int(item.get("evidence_count") or 0),
            -float(item.get("score") or 0.0),
            str(item.get("name") or ""),
        ),
    )
    return apply_evidence_aware_cutoff(ranked, query_tokens=query_tokens, top_k=top_k)


def apply_relative_specificity_penalties(ranked_hits: list[SearchHit], *, query_tokens: list[str]) -> None:
    for hit in ranked_hits:
        penalty = relative_specificity_penalty_for_hit(hit, ranked_hits, query_tokens=query_tokens)
        breakdown = hit.get("score_breakdown") or {}
        breakdown["relative_specificity_penalty"] = round(penalty, 6)
        if penalty <= 0.0:
            continue
        hit["rank_score"] = round(float(hit.get("rank_score") or 0.0) - penalty, 6)
        breakdown["rank_score"] = hit["rank_score"]


def relative_specificity_penalty_for_hit(
    hit: SearchHit,
    ranked_hits: list[SearchHit],
    *,
    query_tokens: list[str],
) -> float:
    specific_tokens = specific_query_token_set(query_tokens)
    if len(specific_tokens) < 2:
        return 0.0
    hit_sets = query_aligned_label_token_sets(hit, specific_tokens=specific_tokens)
    if not hit_sets:
        return 0.0
    if is_exact_query_hit(hit):
        return 0.0
    primary_broad = is_broad_primary_label(hit)
    strongest_penalty = 0.0
    for matched_tokens in hit_sets:
        if len(matched_tokens) > 1 and not primary_broad:
            continue
        for candidate in ranked_hits:
            if candidate is hit:
                continue
            candidate_sets = query_aligned_label_token_sets(candidate, specific_tokens=specific_tokens)
            if not candidate_sets:
                continue
            for candidate_tokens in candidate_sets:
                if not matched_tokens < candidate_tokens:
                    continue
                extra_tokens = candidate_tokens - matched_tokens
                if not extra_tokens:
                    continue
                penalty = 0.24
                if len(candidate_tokens) >= min(3, len(specific_tokens)):
                    penalty += 0.16
                if primary_broad:
                    penalty += 0.16
                if not semantic_groups_compatible_for_specificity(hit, candidate):
                    penalty += 0.06
                strongest_penalty = max(strongest_penalty, min(penalty, 0.62))
    return strongest_penalty


def semantic_groups_compatible_for_specificity(hit: SearchHit, candidate: SearchHit) -> bool:
    hit_group = str(hit.get("semantic_group") or semantic_group_from_types(list(hit.get("semantic_types") or [])))
    candidate_group = str(
        candidate.get("semantic_group") or semantic_group_from_types(list(candidate.get("semantic_types") or []))
    )
    if not hit_group or not candidate_group:
        return True
    if hit_group == candidate_group:
        return True
    compatible = {
        frozenset({"DISO", "PHEN"}),
        frozenset({"DISO", "PHYS"}),
        frozenset({"DISO", "OBS"}),
        frozenset({"PROC", "PHYS"}),
        frozenset({"PROC", "OBS"}),
        frozenset({"PROC", "DISO"}),
    }
    return frozenset({hit_group, candidate_group}) in compatible


def query_aligned_label_token_sets(hit: SearchHit, *, specific_tokens: set[str]) -> list[set[str]]:
    labels = list(hit.get("labels") or [])
    if hit.get("name"):
        labels.insert(0, str(hit["name"]))
    aligned = []
    seen = set()
    for label in labels:
        matched = frozenset(set(content_tokens(str(label))) & specific_tokens)
        if not matched or matched in seen:
            continue
        seen.add(matched)
        aligned.append(set(matched))
    aligned = [
        matched
        for matched in aligned
        if not any(matched < other for other in aligned)
    ]
    aligned.sort(key=lambda item: (-len(item), sorted(item)))
    return aligned


def is_exact_query_hit(hit: SearchHit) -> bool:
    breakdown = hit.get("score_breakdown") or {}
    return bool(
        float(breakdown.get("exact_primary_name_component") or 0.0) > 0.0
        or float(breakdown.get("exact_label_component") or 0.0) > 0.0
        or float(breakdown.get("exact_span_component") or 0.0) > 0.0
    )


USEFUL_EXACT_SPAN_GROUPS = {
    "ANAT",
    "CHEM",
    "DEVI",
    "DISO",
    "GENE",
    "LIVB",
    "PHEN",
    "PHYS",
    "PROC",
}
USEFUL_EXACT_SPAN_TYPES = {
    "clinical attribute",
    "laboratory procedure",
    "laboratory or test result",
}
PHARMACOLOGIC_EXACT_SOURCE_SABS = {
    "ATC",
    "DRUGBANK",
    "GS",
    "MEDCIN",
    "MSH",
    "MTH",
    "MTHSPL",
    "NCI",
    "NDDF",
    "RXNORM",
    "SNOMEDCT_US",
    "VANDF",
}
PHARMACOLOGIC_EXACT_INGREDIENT_TTYS = {
    "BN",
    "IN",
    "MH",
    "MIN",
    "PIN",
    "PN",
    "SU",
}
LOW_VALUE_EXACT_PHARMACOLOGIC_SPANS = {
    "adjuvant",
    "androgen",
    "androgens",
    "estrogen",
    "estrogens",
    "glucose",
    "opioid",
    "opioids",
    "oxygen",
}
EXACT_DRUG_SEMANTIC_TYPES = {
    "antibiotic",
    "clinical drug",
    "pharmacologic substance",
}
ADMINISTERED_PHARMACOLOGIC_QUERY_TOKENS = {
    "administer",
    "administered",
    "administration",
    "antibiotic",
    "antibiotics",
    "continued",
    "dose",
    "doses",
    "empiric",
    "given",
    "held",
    "missed",
    "prescribed",
    "require",
    "required",
    "requiring",
    "received",
    "started",
}
SEPSIS_COMPONENT_ACTION_TOKENS = {
    "dose",
    "doses",
    "given",
    "manage",
    "management",
    "monitor",
    "monitored",
    "monitoring",
    "require",
    "required",
    "requiring",
    "support",
    "therapy",
    "treat",
    "treatment",
}
SEPSIS_COMPONENT_LABEL_TOKENS = {
    "antibiotic",
    "antibiotics",
    "lactate",
    "norepinephrine",
    "pressor",
    "vasopressin",
    "vasopressor",
}
DIABETES_CONTROL_GENERIC_LABEL_TOKENS = {
    "adult",
    "condition",
    "diabetes",
    "diabetic",
    "disease",
    "disorder",
    "dm",
    "i",
    "ii",
    "mellitu",
    "mellitus",
    "nos",
    "t1dm",
    "t2dm",
    "type",
    "1",
    "2",
}
LATERALITY_FRAGMENT_TOKENS = {
    "bilateral",
    "bilaterally",
    "both",
    "left",
    "right",
    "side",
    "sided",
}
BRAND_LABEL_TOKENS = {"brand"}
VACCINE_LABEL_TOKENS = {"immunization", "immunisation", "vaccination", "vaccine", "vaccines"}
VACCINE_INTENT_QUERY_TOKENS = VACCINE_LABEL_TOKENS | {
    "boost",
    "booster",
    "dose",
    "doses",
    "immunize",
    "immunized",
    "immunizing",
    "prevent",
    "prevention",
    "preventive",
    "prophylaxis",
    "receive",
    "received",
    "recipient",
    "recipients",
}
ACTIVE_LABEL_SUPPLEMENT_SOURCE = "active_label_supplement"
CENTRAL_SINGLE_TOKEN_CONDITION_TYPES = {
    "acquired abnormality",
    "cell or molecular dysfunction",
    "congenital abnormality",
    "disease or syndrome",
    "injury or poisoning",
    "mental or behavioral dysfunction",
    "neoplastic process",
    "pathologic function",
}
LOW_VALUE_SINGLE_TOKEN_CONDITION_LABELS = {
    "edema",
    "fever",
    "hemorrhage",
    "infection",
    "pain",
    "shock",
}
FIRST_SENTENCE_INFECTION_FOCUS_TOKENS = {
    "abscess",
    "bacteremia",
    "cellulitis",
    "celluliti",
    "endocarditis",
    "endocarditi",
    "infection",
    "meningitis",
    "meningiti",
    "osteomyelitis",
    "osteomyeliti",
    "pneumonia",
    "sepsis",
    "septic",
}
SPECIFIC_INFECTION_CONTEXT_TOKENS = FIRST_SENTENCE_INFECTION_FOCUS_TOKENS | {
    "chlamydia",
    "gonorrhea",
    "pid",
    "pyelonephritis",
    "pyelonephriti",
    "urethritis",
    "urethriti",
}


def exact_matched_span_component(
    hit: SearchHit,
    *,
    labels: list[str],
    query_set: set[str],
) -> float:
    if hit.get("match_type") != "umls_label":
        return 0.0
    span_tokens = content_tokens(str(hit.get("matched_query_span") or ""))
    if not span_tokens:
        return 0.0
    span_set = set(span_tokens)
    if is_generic_label([str(hit.get("matched_label") or ""), *labels]):
        return 0.0
    label_token_sets = [
        set(content_tokens(label))
        for label in labels
        if content_tokens(label)
    ]
    if not any(span_set == label_tokens for label_tokens in label_token_sets):
        return 0.0
    semantic_types = semantic_type_names(hit)
    semantic_group = str(hit.get("semantic_group") or semantic_group_from_types(list(hit.get("semantic_types") or [])))
    useful_semantic = semantic_group in USEFUL_EXACT_SPAN_GROUPS or bool(
        semantic_types & USEFUL_EXACT_SPAN_TYPES
    )
    if len(span_set) == 1:
        if not useful_semantic:
            return 0.0
        if semantic_group in {"CHEM", "DISO", "LIVB", "PROC"}:
            return 0.22
        return 0.12
    if useful_semantic:
        return 0.20
    return 0.08


def exact_pharmacologic_source_component(
    hit: SearchHit,
    *,
    exact_span_component: float | None = None,
) -> float:
    if hit.get("match_type") != "umls_label":
        return 0.0
    if exact_span_component is None:
        exact_span_component = float((hit.get("score_breakdown") or {}).get("exact_span_component") or 0.0)
    if exact_span_component <= 0.0:
        return 0.0
    span_tokens = content_tokens(str(hit.get("matched_query_span") or ""))
    if not span_tokens or len(span_tokens) > 2:
        return 0.0
    span_norm = " ".join(span_tokens)
    if span_norm in LOW_VALUE_EXACT_PHARMACOLOGIC_SPANS:
        return 0.0
    semantic_types = semantic_type_names(hit)
    if not (semantic_types & EXACT_DRUG_SEMANTIC_TYPES):
        return 0.0
    sab = str(hit.get("matched_sab") or "").upper()
    tty = str(hit.get("matched_tty") or "").upper()
    if sab == "CPT":
        return 0.0
    component = 0.0
    if sab in PHARMACOLOGIC_EXACT_SOURCE_SABS:
        component += 0.14
    if tty in PHARMACOLOGIC_EXACT_INGREDIENT_TTYS:
        component += 0.04
    return min(component, 0.18)


def curated_exact_label_component_for_hit(
    hit: SearchHit,
    *,
    exact_span_component: float,
) -> float:
    if exact_span_component <= 0.0:
        return 0.0
    if ACTIVE_LABEL_SUPPLEMENT_SOURCE not in {str(source) for source in hit.get("sources") or []}:
        return 0.0
    span_tokens = content_tokens(str(hit.get("matched_query_span") or ""))
    if not span_tokens:
        return 0.0
    return 0.30 if len(span_tokens) == 1 else 0.22


def apply_evidence_aware_cutoff(
    ranked_hits: list[SearchHit],
    *,
    query_tokens: list[str],
    top_k: int,
) -> list[SearchHit]:
    signal_hits = [
        hit
        for hit in ranked_hits
        if not is_unanchored_low_signal_hit(hit, query_tokens=query_tokens)
    ]
    if signal_hits:
        ranked_hits = signal_hits
    evidence_hits = sum(1 for hit in ranked_hits if int(hit.get("evidence_count") or 0) > 0)
    if evidence_hits < min(top_k, 3):
        return ranked_hits[:top_k]
    filtered = []
    for hit in ranked_hits:
        if is_weak_zero_evidence_label_fallback(hit, query_tokens=query_tokens):
            continue
        if is_generic_status_noise_result(hit, query_tokens=query_tokens):
            continue
        filtered.append(hit)
    return select_anchor_diverse_hits(filtered, query_tokens=query_tokens, top_k=top_k)


LOW_VALUE_ADMIN_STATUS_RESULT_LABELS = {
    "after delivery",
    "active",
    "baseline",
    "biospecimen collection",
    "body substance discharge",
    "cohort studies",
    "compatible",
    "complete",
    "critical",
    "developed countries",
    "discharge summary",
    "dosage",
    "education",
    "empiric",
    "ever told you have or had atrial fibrillation",
    "every qualifier",
    "forty four",
    "granular",
    "general mechanism of the forces which caused the injury",
    "had no pain",
    "high",
    "high dose",
    "hormonal",
    "immune-mediated",
    "living alone",
    "low dose",
    "mg dl",
    "milliliter per second",
    "neoplasms",
    "patient symptoms",
    "patient discharge",
    "pending day type",
    "per 4 0 milliliters",
    "second ordinal",
    "second unit of plane angle",
    "scheduled procedure status",
    "sixty four",
    "singular",
    "symptom score",
    "symptom severe",
    "suspected diagnosis",
    "suspicious",
    "teaching",
    "thyroid hormones",
    "update",
    "vitamins",
    "volume",
    "wound status",
    "disease susceptibility",
    "benefit",
}
LOW_VALUE_ADMIN_STATUS_RESULT_TOKEN_SETS = {
    frozenset(content_tokens(label)) for label in LOW_VALUE_ADMIN_STATUS_RESULT_LABELS
}
LOW_VALUE_CONTEXT_STATUS_RESULT_LABELS = {
    "absence of pain",
    "attack",
    "attack finding",
    "benefit",
    "expression negative",
    "had no pain",
    "negative",
    "negative predictive value",
    "no pain",
    "pain absent",
    "positive finding",
    "positive and negative",
    "incidence proportion",
    "incidence proportions",
    "recurrent condition",
    "relieved",
    "relieved qualifier value",
    "risks and benefits",
}
LOW_VALUE_CONTEXT_STATUS_RESULT_TOKEN_SETS = {
    frozenset(content_tokens(label)) for label in LOW_VALUE_CONTEXT_STATUS_RESULT_LABELS
}
BROAD_SYMPTOM_AGGREGATE_LABEL_TOKENS = {
    "absence",
    "absent",
    "clinical",
    "distressing",
    "general",
    "multiple",
    "negative",
    "no",
    "patient",
    "respiratory",
    "sign",
    "signs",
    "systemic",
    "symptom",
    "symptoms",
    "without",
}
LOW_VALUE_CONTEXT_ANCHOR_TOKENS = {
    "absence",
    "absent",
    "active",
    "administered",
    "associated",
    "association",
    "attack",
    "baseline",
    "chronic",
    "compatible",
    "complete",
    "confirm",
    "confirmed",
    "critical",
    "empiric",
    "granular",
    "incidence",
    "pending",
    "negative",
    "pain",
    "positive",
    "predictive",
    "rapid",
    "recurrent",
    "relieved",
    "score",
    "second",
    "singular",
    "suspected",
    "suspicious",
    "teaching",
    "treat",
    "treatment",
    "update",
    "updated",
    "value",
    "volume",
}
LOW_VALUE_PROCEDURE_FRAGMENT_TOKENS = {
    "computed",
    "diagnostic",
    "disease",
    "imaging",
    "infection",
    "pharmacotherapy",
    "prescribed",
    "preventive",
    "procedure",
    "service",
    "services",
    "test",
    "testing",
    "tomographic",
    "tomography",
    "treat",
    "treatment",
}


def is_generic_status_noise_result(hit: SearchHit, *, query_tokens: list[str]) -> bool:
    query_set = set(query_tokens)
    breakdown = hit.get("score_breakdown") or {}
    clinical_context_sense_penalty = float(
        breakdown.get("clinical_context_sense_penalty") or 0.0
    )
    labels = list(hit.get("labels") or [])
    if hit.get("name"):
        labels.insert(0, str(hit["name"]))
    label_tokens = set()
    for label in labels:
        label_tokens.update(content_tokens(label))
    primary_token_sets = hit_primary_label_token_sets(hit=hit, labels=labels)
    if query_has_context_beyond_primary_label(query_set, primary_token_sets, label_tokens):
        if any(token_set in LOW_VALUE_CONTEXT_STATUS_RESULT_TOKEN_SETS for token_set in primary_token_sets):
            return True
        if hit_is_context_only_anchor_noise_result(
            hit=hit,
            query_tokens=query_set,
            label_tokens=label_tokens,
        ):
            return True
        if hit_has_contextual_false_positive_anchor_context(
            hit=hit,
            labels=labels,
            label_tokens=label_tokens,
            query_tokens=query_set,
            semantic_types=semantic_type_names(hit),
        ):
            return True
        if hit_has_broad_symptom_aggregate_context(
            hit=hit,
            labels=labels,
            semantic_types=semantic_type_names(hit),
        ):
            return True
        if (
            any(label_is_mortality_outcome_context(label_tokens=token_set) for token_set in primary_token_sets)
            and not query_asks_for_mortality_outcome(query_set)
        ):
            return True
        if hit_is_low_value_procedure_fragment(
            hit=hit,
            query_tokens=query_set,
            label_tokens=label_tokens,
        ):
            return True
    if clinical_context_sense_penalty >= 0.60 and (
        hit_has_generic_prose_status_context(
            hit=hit,
            labels=labels,
            label_tokens=label_tokens,
        )
        or hit_has_confirmation_status_context(
            hit=hit,
            labels=labels,
            label_tokens=label_tokens,
        )
        or hit_has_broad_organism_context(
            hit=hit,
            labels=labels,
            semantic_types=semantic_type_names(hit),
        )
        or hit_has_broad_infection_disease_context(
            hit=hit,
            labels=labels,
            semantic_types=semantic_type_names(hit),
        )
        or hit_has_yes_no_answer_status_context(hit=hit, labels=labels)
    ):
        return True
    return is_low_value_admin_status_result(
        hit=hit,
        labels=labels,
        query_tokens=query_tokens,
    )


def query_has_context_beyond_primary_label(
    query_tokens: set[str],
    primary_token_sets: list[set[str]],
    label_tokens: set[str],
) -> bool:
    useful_query = query_tokens - LOW_SPECIFICITY_QUERY_TOKENS
    if not useful_query:
        return False
    if useful_query <= label_tokens:
        return False
    return not any(useful_query <= token_set for token_set in primary_token_sets)


def hit_is_context_only_anchor_noise_result(
    *,
    hit: SearchHit,
    query_tokens: set[str],
    label_tokens: set[str],
) -> bool:
    breakdown = hit.get("score_breakdown") or {}
    if float(breakdown.get("negated_finding_component") or 0.0) > 0.0:
        return False
    matched_label_tokens = (query_tokens - LOW_SPECIFICITY_QUERY_TOKENS) & label_tokens
    if not matched_label_tokens:
        if query_tokens & PROCEDURE_ROLE_TOKENS:
            return False
        lexical_component = float((hit.get("score_breakdown") or {}).get("lexical_component") or 0.0)
        exact_span_component = float((hit.get("score_breakdown") or {}).get("exact_span_component") or 0.0)
        return lexical_component <= 0.50 and exact_span_component <= 0.0
    return matched_label_tokens <= LOW_VALUE_CONTEXT_ANCHOR_TOKENS


def hit_is_low_value_procedure_fragment(
    *,
    hit: SearchHit,
    query_tokens: set[str],
    label_tokens: set[str],
) -> bool:
    semantic_types = semantic_type_names(hit)
    if not (
        semantic_types & PROCEDURE_SEMANTIC_TYPES
        or str(hit.get("semantic_group") or "") == "PROC"
    ):
        return False
    matched_label_tokens = (query_tokens - LOW_SPECIFICITY_QUERY_TOKENS) & label_tokens
    if not matched_label_tokens:
        return False
    if not matched_label_tokens <= LOW_VALUE_PROCEDURE_FRAGMENT_TOKENS:
        return False
    if len(matched_label_tokens) >= 2 and {"computed", "tomography"} <= matched_label_tokens:
        return False
    return True


def is_low_value_admin_status_result(
    *,
    hit: SearchHit,
    labels: list[str],
    query_tokens: list[str],
) -> bool:
    query_set = set(query_tokens)
    if not query_has_biomedical_context_beyond_prose_status(query_set):
        return False
    token_sets = hit_primary_label_token_sets(hit=hit, labels=labels)
    label_tokens = set()
    for label in labels:
        label_tokens.update(content_tokens(label))
    if not query_has_context_beyond_primary_label(query_set, token_sets, label_tokens):
        return False
    if any(token_set in LOW_VALUE_ADMIN_STATUS_RESULT_TOKEN_SETS for token_set in token_sets):
        return True
    primary_name = normalized_key(str(hit.get("name") or ""))
    if primary_name == "positive":
        return "positive" in query_set and bool(query_set & LAB_RESULT_TEST_TOKENS)
    return False


def select_anchor_diverse_hits(
    ranked_hits: list[SearchHit],
    *,
    query_tokens: list[str],
    top_k: int,
) -> list[SearchHit]:
    specific_tokens = specific_query_token_set(query_tokens)
    if len(specific_tokens) < 2:
        return ranked_hits[:top_k]
    selected: list[dict] = []
    deferred: list[dict] = []
    covered: set[str] = set()
    for hit in ranked_hits:
        matched = hit_direct_label_specific_tokens(hit, query_tokens=query_tokens)
        uncovered = specific_tokens - covered
        is_fragment = (
            float((hit.get("score_breakdown") or {}).get("semantic_fragment_penalty") or 0.0) > 0.0
            or float((hit.get("score_breakdown") or {}).get("normal_exam_fragment_penalty") or 0.0) > 0.0
        )
        if selected and uncovered and is_fragment:
            deferred.append(hit)
            continue
        if selected and uncovered and (not matched or matched <= covered):
            if not (
                is_exact_administered_pharmacologic_hit(hit, query_tokens=query_tokens)
                or is_explicit_sepsis_component_anchor_hit(hit, query_tokens=query_tokens)
                or is_curated_exact_label_hit(hit)
            ):
                deferred.append(hit)
                continue
        if (
            selected
            and not uncovered
            and is_zero_evidence_single_anchor_label(hit, query_tokens=query_tokens)
            and matched
            and matched <= covered
            and not is_exact_administered_pharmacologic_hit(hit, query_tokens=query_tokens)
            and not is_explicit_sepsis_component_anchor_hit(hit, query_tokens=query_tokens)
            and not is_curated_exact_label_hit(hit)
        ):
            deferred.append(hit)
            continue
        if (
            selected
            and not uncovered
            and not matched
            and bool((hit.get("score_breakdown") or {}).get("lexical_fallback_used"))
            and not hit_has_composite_intent_signal(hit)
        ):
            deferred.append(hit)
            continue
        selected.append(hit)
        if hit_satisfies_composite_intent(hit):
            covered.update(specific_tokens)
        else:
            covered.update(matched)
        if len(selected) >= top_k and not (specific_tokens - covered):
            break
    if len(selected) < top_k:
        selected_ids = {id(hit) for hit in selected}
        fill_candidates = [*deferred, *ranked_hits]
        order = {id(hit): index for index, hit in enumerate(fill_candidates)}
        for hit in sorted(
            fill_candidates,
            key=lambda item: anchor_fill_priority(item, query_tokens=query_tokens, order=order),
        ):
            if id(hit) in selected_ids:
                continue
            selected.append(hit)
            selected_ids.add(id(hit))
            if len(selected) >= top_k:
                break
    return selected[:top_k]


def hit_direct_label_specific_tokens(hit: SearchHit, *, query_tokens: list[str]) -> set[str]:
    return specific_query_token_set(query_tokens) & label_tokens_for_hit(hit)


def is_weak_zero_evidence_label_fallback(hit: SearchHit, *, query_tokens: list[str]) -> bool:
    if hit.get("match_type") != "umls_label":
        return False
    if "active_label_supplement" in {str(source) for source in hit.get("sources") or []}:
        return False
    if int(hit.get("evidence_count") or 0) > 0:
        return False
    if float(hit.get("score") or 0.0) >= 1.0:
        return False
    query_unique = set(query_tokens)
    if len(query_unique) < 3:
        return False
    span = str(hit.get("matched_query_span") or "").strip()
    if not span:
        return False
    span_tokens = set(content_tokens(span))
    return 0 < len(span_tokens) <= 1 and bool(span_tokens & query_unique)


def is_zero_evidence_single_anchor_label(hit: SearchHit, *, query_tokens: list[str]) -> bool:
    if hit.get("match_type") != "umls_label":
        return False
    if int(hit.get("evidence_count") or 0) > 0:
        return False
    matched = hit_matched_specific_tokens(hit, query_tokens=query_tokens)
    return 0 < len(matched) <= 1


def is_exact_administered_pharmacologic_hit(hit: SearchHit, *, query_tokens: list[str]) -> bool:
    breakdown = hit.get("score_breakdown") or {}
    if float(breakdown.get("exact_pharmacologic_component") or 0.0) <= 0.0:
        return False
    if not (set(query_tokens) & ADMINISTERED_PHARMACOLOGIC_QUERY_TOKENS):
        return False
    span_tokens = content_tokens(str(hit.get("matched_query_span") or ""))
    if not span_tokens:
        return False
    return " ".join(span_tokens) not in LOW_VALUE_EXACT_PHARMACOLOGIC_SPANS


def is_explicit_sepsis_component_anchor_hit(hit: SearchHit, *, query_tokens: list[str]) -> bool:
    query_set = set(query_tokens)
    if not is_sepsis_shock_intent(query_set):
        return False
    if not (query_set & SEPSIS_COMPONENT_ACTION_TOKENS):
        return False
    breakdown = hit.get("score_breakdown") or {}
    if float(breakdown.get("exact_span_component") or 0.0) <= 0.0:
        return False
    label_tokens = label_tokens_for_hit(hit)
    if not (label_tokens & SEPSIS_COMPONENT_LABEL_TOKENS):
        return False
    semantic_types = semantic_type_names(hit)
    if semantic_types & (
        PHARMACOLOGIC_SEMANTIC_TYPES
        | PROCEDURE_SEMANTIC_TYPES
        | {"laboratory procedure", "laboratory or test result"}
    ):
        return True
    group = str(hit.get("semantic_group") or semantic_group_from_types(list(hit.get("semantic_types") or [])))
    return group in {"CHEM", "OBS", "PHYS", "PROC"}


def is_unanchored_low_signal_hit(hit: SearchHit, *, query_tokens: list[str]) -> bool:
    breakdown = hit.get("score_breakdown") or {}
    if not breakdown.get("lexical_fallback_used"):
        return False
    if hit_matched_specific_tokens(hit, query_tokens=query_tokens):
        return False
    signal_keys = (
        "vector_component",
        "label_fallback_component",
        "exact_label_component",
        "exact_primary_name_component",
        "exact_span_component",
        "primary_name_component",
        "negated_finding_component",
        "semantic_component",
        "evidence_context_component",
        "definition_component",
        "mrrel_component",
        "composite_intent_component",
        "specificity_component",
    )
    return not any(float(breakdown.get(key) or 0.0) > 0.0 for key in signal_keys)


def anchor_fill_priority(hit: SearchHit, *, query_tokens: list[str], order: dict[int, int]) -> tuple[int, int]:
    matched = hit_direct_label_specific_tokens(hit, query_tokens=query_tokens)
    sense_penalty = float((hit.get("score_breakdown") or {}).get("clinical_context_sense_penalty") or 0.0)
    lexical_fallback = bool((hit.get("score_breakdown") or {}).get("lexical_fallback_used"))
    is_fragment = (
        float((hit.get("score_breakdown") or {}).get("semantic_fragment_penalty") or 0.0) > 0.0
        or float((hit.get("score_breakdown") or {}).get("normal_exam_fragment_penalty") or 0.0) > 0.0
    )
    if sense_penalty >= 0.40:
        bucket = 4
    elif hit_has_composite_intent_signal(hit) or is_curated_exact_label_hit(hit):
        bucket = 0
    elif matched and int(hit.get("evidence_count") or 0) > 0 and not is_fragment:
        bucket = 0
    elif matched:
        bucket = 1
    elif lexical_fallback:
        bucket = 3
    else:
        bucket = 2
    return bucket, order.get(id(hit), 0)


def hit_satisfies_composite_intent(hit: SearchHit) -> bool:
    return float((hit.get("score_breakdown") or {}).get("composite_intent_component") or 0.0) >= 0.30


def hit_has_composite_intent_signal(hit: SearchHit) -> bool:
    return float((hit.get("score_breakdown") or {}).get("composite_intent_component") or 0.0) > 0.0


def is_curated_exact_label_hit(hit: SearchHit) -> bool:
    return float((hit.get("score_breakdown") or {}).get("curated_exact_label_component") or 0.0) > 0.0


def label_fallback_anchor_queries(query: str) -> list[str]:
    anchors = []
    seen = set()
    for token in normalized_key(query).split():
        canonical = canonical_token(token)
        if (
            not canonical
            or canonical in NEGATION_QUERY_TOKENS
            or canonical in RANK_STOPWORDS
            or canonical in LOW_SPECIFICITY_QUERY_TOKENS
            or (len(canonical) < 4 and not any(char.isdigit() for char in canonical))
        ):
            continue
        if token in seen:
            continue
        seen.add(token)
        anchors.append(token)
    for anchor in negated_label_fallback_queries(query):
        if anchor in seen:
            continue
        seen.add(anchor)
        anchors.append(anchor)
    return anchors


def negated_label_fallback_queries(query: str) -> list[str]:
    raw_tokens = normalized_key(query).split()
    if not has_denial_context(set(raw_tokens)):
        return []
    anchors = []
    seen = set()
    for scope_tokens in denial_scope_token_lists(raw_tokens):
        max_len = min(4, len(scope_tokens))
        for length in range(max_len, 0, -1):
            for start in range(0, len(scope_tokens) - length + 1):
                span_tokens = scope_tokens[start : start + length]
                if any(canonical_token(token) in NEGATION_QUERY_TOKENS for token in span_tokens):
                    continue
                if not is_denial_anchor_span(span_tokens):
                    continue
                span = " ".join(span_tokens)
                for anchor in (f"no {span}", f"{span} absent"):
                    if anchor in seen:
                        continue
                    seen.add(anchor)
                    anchors.append(anchor)
                    if len(anchors) >= 24:
                        return anchors
    return anchors


def is_denial_anchor_span(tokens: list[str]) -> bool:
    if not tokens:
        return False
    canonical_tokens = tuple(canonical_token(token) for token in tokens)
    if canonical_tokens in ALLOWED_DENIAL_ANCHOR_SPANS:
        return True
    if tokens[0] in RANK_STOPWORDS or tokens[-1] in RANK_STOPWORDS:
        return False
    content = []
    for token in tokens:
        canonical = canonical_token(token)
        if not canonical or canonical in NEGATION_QUERY_TOKENS:
            return False
        if canonical in RANK_STOPWORDS:
            continue
        if canonical in LOW_SPECIFICITY_QUERY_TOKENS:
            continue
        if len(canonical) < 4 and not any(char.isdigit() for char in canonical):
            continue
        content.append(canonical)
    if not content:
        return False
    if len(tokens) > 1 and len(content) <= 1:
        return False
    return True


def mrrel_candidate_priority(query_tokens: list[str], hit: dict) -> tuple[int, float, int, float]:
    labels = list(hit.get("labels") or [])
    if hit.get("name"):
        labels.insert(0, str(hit["name"]))
    lexical_score = max((label_relevance(query_tokens, label) for label in labels), default=0.0)
    matched = specific_query_token_set(query_tokens) & label_tokens_for_hit(hit)
    return (
        len(matched),
        lexical_score,
        1 if int(hit.get("evidence_count") or 0) > 0 else 0,
        float(hit.get("score") or 0.0),
    )


def label_has_procedure_role(*, label_tokens: set[str], labels: list[str], hit: dict) -> bool:
    if label_tokens & PROCEDURE_ROLE_TOKENS:
        return True
    if semantic_type_names(hit) & PROCEDURE_SEMANTIC_TYPES:
        return True
    view = str(hit.get("view") or "").lower()
    if "procedure" in view or "procedures" in view:
        return True
    for token in label_tokens:
        if token.endswith(PROCEDURE_LABEL_SUFFIXES):
            return True
    for label in labels:
        norm = normalized_key(label)
        if " procedure" in f" {norm}" or " operation" in f" {norm}" or " surgical" in f" {norm}":
            return True
    return False


def hit_has_pharmacologic_role(*, label_tokens: set[str], hit: dict) -> bool:
    semantic_types = semantic_type_names(hit)
    if semantic_types & PHARMACOLOGIC_SEMANTIC_TYPES:
        return True
    if label_tokens & {"antibiotic", "anticoagulant", "antithrombotic", "drug", "medication"}:
        return True
    return False


def related_anchor_candidate_matches_query(
    *,
    query_tokens: list[str],
    seed_hit: dict,
    candidate_hit: dict,
) -> bool:
    seed_anchor_tokens = hit_matched_specific_tokens(seed_hit, query_tokens=query_tokens)
    if not seed_anchor_tokens:
        return False
    candidate_label_tokens = label_tokens_for_hit(candidate_hit)
    if not (candidate_label_tokens & seed_anchor_tokens):
        return False
    query_set = set(query_tokens)
    if query_set & PROCEDURE_ROLE_TOKENS:
        labels = [str(candidate_hit.get("name") or ""), *[str(label) for label in candidate_hit.get("labels") or []]]
        if not label_has_procedure_role(
            label_tokens=candidate_label_tokens,
            labels=labels,
            hit=candidate_hit,
        ):
            return False
    return True


def evidence_context_component_for_hit(
    *,
    query_tokens: list[str],
    label_tokens: set[str],
    hit: dict,
) -> float:
    specific_tokens = specific_query_token_set(query_tokens)
    if len(specific_tokens) < 3:
        return 0.0
    if int(hit.get("evidence_count") or 0) <= 0:
        return 0.0
    if not (semantic_type_names(hit) & COMPOSITE_CONTEXT_SEMANTIC_TYPES):
        return 0.0
    label_matched = specific_tokens & label_tokens
    if not label_matched:
        return 0.0
    evidence_matched = specific_tokens & evidence_context_tokens(hit)
    new_evidence_anchors = evidence_matched - label_matched
    if not new_evidence_anchors:
        return 0.0
    combined = label_matched | evidence_matched
    component = 0.05 * min(len(new_evidence_anchors), 2)
    if len(combined) >= min(len(specific_tokens), 3):
        component += 0.04
    if "sepsis" in combined and {"lactate", "vasopressor"} <= combined:
        component += 0.04
    return min(component, 0.18)


def composite_intent_component_for_hit(
    *,
    query_tokens: list[str],
    label_tokens: set[str],
    hit: dict,
) -> float:
    query_set = set(query_tokens)
    if int(hit.get("evidence_count") or 0) <= 0:
        return 0.0
    if not (semantic_type_names(hit) & COMPOSITE_CONTEXT_SEMANTIC_TYPES):
        return 0.0
    if not is_sepsis_shock_intent(query_set):
        return 0.0
    evidence_tokens = evidence_context_tokens(hit)
    if {"sepsis", "shock"} <= label_tokens:
        component = 0.34
        if evidence_tokens & (SEPSIS_SHOCK_ANCHOR_TOKENS | {"lactate"}):
            component += 0.04
        if {"sepsis", "shock"} <= evidence_tokens:
            component += 0.04
        return min(component, 0.42)
    if "shock" in label_tokens:
        component = 0.16
        if "sepsis" in evidence_tokens:
            component += 0.04
        if evidence_tokens & (SEPSIS_SHOCK_ANCHOR_TOKENS | {"lactate"}):
            component += 0.03
        if "sepsis" in evidence_tokens and evidence_tokens & SEPSIS_SHOCK_ANCHOR_TOKENS:
            component += 0.03
        return min(component, 0.26)
    return 0.0


LAB_RESULT_COMPOSITE_SEMANTIC_TYPES = {
    "laboratory or test result",
}
LAB_RESULT_TEST_TOKENS = {
    "antibody",
    "antibodies",
    "antigen",
    "biopsy",
    "culture",
    "cultures",
    "pcr",
    "polymerase",
    "reaction",
    "test",
    "testing",
    "urine",
}
LAB_RESULT_CONTEXT_TOKENS = LAB_RESULT_TEST_TOKENS | {
    "detected",
    "grew",
    "growth",
    "positive",
    "result",
    "results",
    "showed",
}


def lab_result_composite_component_for_hit(
    *,
    query_tokens: list[str],
    label_tokens: set[str],
    hit: dict,
) -> float:
    if int(hit.get("evidence_count") or 0) <= 0:
        return 0.0
    if not (semantic_type_names(hit) & LAB_RESULT_COMPOSITE_SEMANTIC_TYPES):
        return 0.0
    query_set = set(query_tokens)
    if not (query_set & LAB_RESULT_CONTEXT_TOKENS):
        return 0.0
    if not (label_tokens & LAB_RESULT_TEST_TOKENS):
        return 0.0
    matched_specific = specific_query_token_set(query_tokens) & label_tokens
    if len(matched_specific) < 3:
        return 0.0
    non_test_anchors = matched_specific - LAB_RESULT_TEST_TOKENS
    if not non_test_anchors:
        return 0.0
    component = 0.22
    if len(non_test_anchors) >= 2:
        component += 0.04
    if query_set & {"detected", "grew", "growth", "positive"}:
        component += 0.04
    return min(component, 0.30)


def composite_component_penalty_for_hit(
    *,
    query_tokens: list[str],
    label_tokens: set[str],
    hit: dict,
) -> float:
    query_set = set(query_tokens)
    if not is_sepsis_shock_intent(query_set):
        return 0.0
    if semantic_type_names(hit) & COMPOSITE_CONTEXT_SEMANTIC_TYPES:
        return 0.0
    matched_specific = specific_query_token_set(query_tokens) & label_tokens
    if not matched_specific:
        return 0.0
    if matched_specific <= (SEPSIS_SHOCK_ANCHOR_TOKENS | {"lactate"}):
        if is_explicit_sepsis_component_context(
            query_set=query_set,
            label_tokens=label_tokens,
            hit=hit,
        ):
            return 0.0
        return 0.36 if int(hit.get("evidence_count") or 0) > 0 else 0.46
    return 0.0


def is_explicit_sepsis_component_context(
    *,
    query_set: set[str],
    label_tokens: set[str],
    hit: dict,
) -> bool:
    if not (query_set & SEPSIS_COMPONENT_ACTION_TOKENS):
        return False
    if not (label_tokens & SEPSIS_COMPONENT_LABEL_TOKENS):
        return False
    semantic_types = semantic_type_names(hit)
    if semantic_types & (
        PHARMACOLOGIC_SEMANTIC_TYPES
        | PROCEDURE_SEMANTIC_TYPES
        | {"laboratory procedure", "laboratory or test result"}
    ):
        return True
    group = str(hit.get("semantic_group") or semantic_group_from_types(list(hit.get("semantic_types") or [])))
    return group in {"CHEM", "OBS", "PHYS", "PROC"}


def sepsis_subtype_penalty_for_hit(
    *,
    query_tokens: list[str],
    label_tokens: set[str],
) -> float:
    query_set = set(query_tokens)
    if not is_sepsis_shock_intent(query_set):
        return 0.0
    if not ({"sepsis", "septicemia"} & label_tokens):
        return 0.0
    if "shock" in label_tokens:
        return 0.0
    unmatched_etiologies = (label_tokens & SEPSIS_ETIOLOGY_SUBTYPE_TOKENS) - query_set
    return 0.14 if unmatched_etiologies else 0.0


def is_sepsis_shock_intent(query_tokens: set[str]) -> bool:
    if "sepsis" not in query_tokens:
        return False
    if "shock" in query_tokens:
        return True
    if query_tokens & SEPSIS_SHOCK_ANCHOR_TOKENS:
        return True
    return "lactate" in query_tokens and bool(query_tokens & {"hypoperfusion", "perfusion"})


def evidence_context_tokens(hit: dict, *, max_items: int = 32) -> set[str]:
    tokens: set[str] = set()
    for item in list(hit.get("evidence_items") or [])[:max_items]:
        tokens.update(content_tokens(str(item.get("text") or "")))
    if not tokens:
        tokens.update(content_tokens(str(hit.get("text") or "")[:20000]))
    return tokens


def definition_context_token_lists(hit: dict, *, max_definitions: int = 5) -> list[list[str]]:
    definitions = []
    matched_definition = hit.get("matched_definition")
    if isinstance(matched_definition, dict):
        definitions.append(matched_definition)
    definitions.extend(list(hit.get("definitions") or []))
    token_lists = []
    seen = set()
    for item in definitions[:max_definitions]:
        if not isinstance(item, dict):
            continue
        definition = str(item.get("definition") or "")
        key = normalized_key(definition)
        if not key or key in seen:
            continue
        seen.add(key)
        tokens = content_tokens(definition)
        if tokens:
            token_lists.append(tokens)
    return token_lists


def definition_component_for_hit(
    *,
    query_tokens: list[str],
    label_tokens: set[str],
    hit: dict,
) -> tuple[float, list[str]]:
    specific_tokens = specific_query_token_set(query_tokens)
    if not specific_tokens:
        return 0.0, []
    token_lists = definition_context_token_lists(hit)
    if not token_lists:
        return 0.0, []
    definition_tokens = set()
    for tokens in token_lists:
        definition_tokens.update(tokens)
    matched = specific_tokens & definition_tokens
    if not matched:
        return 0.0, []
    new_definition_anchors = matched - label_tokens
    has_definition_retrieval = hit.get("match_type") == "umls_definition" or bool(
        hit.get("definition_score_preserved")
    )
    if not new_definition_anchors and not has_definition_retrieval:
        return 0.0, sorted(matched)
    component = 0.025 * min(len(matched), 4)
    if len(matched) >= min(len(specific_tokens), 3):
        component += 0.05
    specific_sequence = [token for token in query_tokens if token in specific_tokens]
    if len(specific_sequence) >= 2:
        for tokens in token_lists:
            if is_ordered_subsequence(specific_sequence, tokens):
                component += 0.03
                if is_contiguous_subsequence(specific_sequence, tokens):
                    component += 0.04
                break
    if has_definition_retrieval:
        component += 0.035
    return min(component, 0.18), sorted(matched)


def first_statement_component_for_hit(
    *,
    query: str,
    labels: list[str],
    hit: dict,
) -> float:
    first_sentence_end = first_sentence_boundary(query)
    if first_sentence_end <= 0 or first_sentence_end >= len(query.strip()):
        return 0.0
    span = query_span_for_hit(query, labels, hit, min_tokens=2)
    if not span:
        span = query_span_for_hit(query, labels, hit, min_tokens=1)
        if not span:
            return 0.0
    start, end, text = span
    if start >= first_sentence_end:
        return 0.0
    if is_comparator_arm_span(query, start, end):
        return 0.0
    token_count = len(content_tokens(text))
    if token_count >= 2:
        if is_central_multi_token_condition_hit(hit, labels=labels, span_text=text):
            return 0.24 if token_count >= 3 else 0.22
        return 0.18 if token_count >= 3 else 0.14
    if token_count == 1:
        return 0.20 if is_central_single_token_condition_hit(hit, labels=labels, span_text=text) else 0.0
    return 0.0


def is_central_multi_token_condition_hit(
    hit: dict,
    *,
    labels: list[str],
    span_text: str,
) -> bool:
    span_tokens = content_tokens(span_text)
    if len(span_tokens) < 2:
        return False
    if any(token in LOW_SPECIFICITY_QUERY_TOKENS for token in span_tokens):
        return False
    label_values = [str(hit.get("name") or ""), *[str(label) for label in labels]]
    if is_generic_label(label_values):
        return False
    return bool(semantic_type_names(hit) & CENTRAL_SINGLE_TOKEN_CONDITION_TYPES)


def is_central_single_token_condition_hit(
    hit: dict,
    *,
    labels: list[str],
    span_text: str,
) -> bool:
    span_tokens = content_tokens(span_text)
    if len(span_tokens) != 1:
        return False
    token = span_tokens[0]
    if token in LOW_SPECIFICITY_QUERY_TOKENS or token in LOW_VALUE_SINGLE_TOKEN_CONDITION_LABELS:
        return False
    label_values = [str(hit.get("name") or ""), *[str(label) for label in labels]]
    if is_generic_label(label_values):
        return False
    return bool(semantic_type_names(hit) & CENTRAL_SINGLE_TOKEN_CONDITION_TYPES)


def local_extension_phrase_component_for_hit(
    *,
    query: str,
    labels: list[str],
    hit: dict,
) -> float:
    if not str(hit.get("cui") or "").startswith("NEW"):
        return 0.0
    span = query_span_for_hit(query, labels, hit, min_tokens=2)
    if not span:
        return 0.0
    start, end, text = span
    if is_comparator_arm_span(query, start, end):
        return 0.0
    token_count = len(content_tokens(text))
    return 0.18 if token_count >= 3 else 0.04


def comparator_arm_penalty_for_hit(
    *,
    query: str,
    labels: list[str],
    hit: dict,
) -> float:
    span = query_span_for_hit(query, labels, hit, min_tokens=2)
    if not span:
        return 0.0
    start, end, _ = span
    return 0.55 if is_comparator_arm_span(query, start, end) else 0.0


def organism_support_penalty_for_hit(
    *,
    query: str,
    labels: list[str],
    hit: dict,
) -> float:
    semantic_group = str(hit.get("semantic_group") or semantic_group_from_types(list(hit.get("semantic_types") or [])))
    if semantic_group != "LIVB":
        return 0.0
    first_sentence_end = first_sentence_boundary(query)
    if first_sentence_end <= 0:
        return 0.0
    first_sentence_tokens = set(content_tokens(query[:first_sentence_end]))
    if not (first_sentence_tokens & FIRST_SENTENCE_INFECTION_FOCUS_TOKENS):
        return 0.0
    span = query_span_for_hit(query, labels, hit, min_tokens=1)
    if not span:
        return 0.0
    start, _end, _text = span
    if start <= first_sentence_end:
        return 0.0
    before = query[max(first_sentence_end, start - 90) : start].lower()
    if not re.search(r"\b(culture|cultures|grew|isolated|detected|positive)\b", before):
        return 0.0
    return 0.22


def first_sentence_boundary(query: str) -> int:
    match = re.search(r"[.!?]\s+\S", query)
    return match.start() + 1 if match else -1


def query_span_for_hit(
    query: str,
    labels: list[str],
    hit: dict,
    *,
    min_tokens: int,
) -> tuple[int, int, str] | None:
    values = [
        hit.get("matched_query_span"),
        hit.get("matched_label"),
        hit.get("name"),
        *labels,
    ]
    seen = set()
    candidates = []
    for value in values:
        text = str(value or "").strip()
        key = normalized_key(text)
        if not key or key in seen:
            continue
        seen.add(key)
        if len(content_tokens(text)) < min_tokens:
            continue
        candidates.append(text)
    candidates.sort(key=lambda item: (-len(content_tokens(item)), -len(item), normalized_key(item)))
    for label in candidates:
        span = direct_query_span(query, label)
        if span:
            return span
    return None


def direct_query_span(query: str, label: str) -> tuple[int, int, str] | None:
    label = label.strip()
    if not label:
        return None
    lower = query.lower()
    index = lower.find(label.lower())
    if index >= 0:
        end = index + len(label)
        return index, end, query[index:end]
    flexible = re.escape(label).replace(r"\ ", r"\s+")
    try:
        match = re.search(rf"(?<![A-Za-z0-9])({flexible})(?![A-Za-z0-9])", query, flags=re.I)
    except re.error:
        return None
    if not match:
        return None
    return match.start(1), match.end(1), query[match.start(1):match.end(1)]


def is_comparator_arm_span(query: str, start: int, end: int) -> bool:
    lower = query.lower()
    before = lower[:start]
    after = lower[end : min(len(lower), end + 140)]
    compared_pos = before.rfind("compared")
    if compared_pos < 0:
        return False
    with_pos = before.rfind(" with ")
    if with_pos <= compared_pos:
        return False
    comparator_intro = before[with_pos:]
    if not re.search(r"\b(patient|patients|group|arm|treated|receiving)\b", comparator_intro):
        return False
    return bool(re.search(r"\b(alone|control|comparator)\b", after))


def query_specificity_component(query_tokens: list[str], label_tokens: set[str]) -> float:
    specific_tokens = specific_query_token_set(query_tokens)
    if not specific_tokens:
        return 0.0
    matched_specific = specific_tokens & label_tokens
    if not matched_specific:
        return 0.0
    component = 0.04 if len(specific_tokens) == 1 else 0.0
    if len(specific_tokens) >= 2 and len(matched_specific) >= 2:
        component += 0.09
        if len(matched_specific) >= min(len(specific_tokens), 3):
            component += 0.03
    if matched_specific & rare_query_anchor_tokens(specific_tokens):
        component += 0.12 if len(specific_tokens) >= 2 else 0.04
    return min(component, 0.18)


def query_role_mismatch_penalty(
    *,
    query_set: set[str],
    label_tokens: set[str],
    labels: list[str],
    hit: dict,
) -> float:
    specific_tokens = query_set - LOW_SPECIFICITY_QUERY_TOKENS
    if not specific_tokens:
        return 0.0
    if (query_set & DRUG_ROLE_QUERY_TOKENS) and (query_set & THERAPEUTIC_ACTION_QUERY_TOKENS):
        if hit_has_pharmacologic_role(label_tokens=label_tokens, hit=hit):
            return 0.0
        non_role_specific = specific_tokens - DRUG_ROLE_QUERY_TOKENS - THERAPEUTIC_ACTION_QUERY_TOKENS
        return 0.65 if label_tokens & non_role_specific else 0.45
    if label_tokens & specific_tokens:
        return 0.0
    if query_set & PROCEDURE_ROLE_TOKENS:
        if label_has_procedure_role(
            label_tokens=label_tokens,
            labels=labels,
            hit=hit,
        ):
            return 0.18
        return 0.24
    return 0.0


def numeric_specificity_mismatch_penalty(
    *,
    query_tokens: list[str],
    label_tokens: set[str],
    hit: dict,
) -> float:
    query_set = set(query_tokens)
    numeric_anchors = numeric_query_anchor_tokens(specific_query_token_set(query_tokens))
    if not numeric_anchors:
        return 0.0
    if numeric_anchors <= label_tokens:
        return 0.0
    if not (query_set & NUMERIC_SPECIFICITY_CONTEXT_TOKENS):
        return 0.0
    matched_without_number = (specific_query_token_set(query_tokens) - numeric_anchors) & label_tokens
    if not matched_without_number:
        return 0.0
    if label_tokens & NUMERIC_SPECIFICITY_CONTEXT_TOKENS:
        return 0.22 if len(matched_without_number) >= 2 else 0.16
    if semantic_type_names(hit) & COMPOSITE_CONTEXT_SEMANTIC_TYPES:
        return 0.20
    return 0.12


def numeric_context_fragment_penalty_for_hit(
    *,
    query_tokens: list[str],
    label_tokens: set[str],
) -> float:
    query_set = set(query_tokens)
    numeric_anchors = numeric_query_anchor_tokens(specific_query_token_set(query_tokens))
    if not numeric_anchors:
        return 0.0
    if not (numeric_anchors & label_tokens):
        return 0.0
    if not (query_set & NUMERIC_SPECIFICITY_CONTEXT_TOKENS):
        return 0.0
    if not (label_tokens & NUMERIC_SPECIFICITY_CONTEXT_TOKENS):
        return 0.0
    substantive_query_tokens = (
        specific_query_token_set(query_tokens)
        - numeric_anchors
        - NUMERIC_SPECIFICITY_CONTEXT_TOKENS
    )
    if not substantive_query_tokens:
        return 0.0
    if substantive_query_tokens & label_tokens:
        return 0.0
    return NUMERIC_CONTEXT_FRAGMENT_PENALTY


def action_observation_mismatch_penalty(
    *,
    query_set: set[str],
    label_tokens: set[str],
    labels: list[str],
    hit: dict,
) -> float:
    if query_set & ACTION_OBSERVATION_QUERY_TOKENS:
        return 0.0
    if not (query_set & OBSERVATION_STATE_QUERY_TOKENS):
        return 0.0
    if not (label_tokens & query_set):
        return 0.0
    if label_tokens & ACTION_OBSERVATION_LABEL_TOKENS:
        return 0.10
    if label_has_procedure_role(label_tokens=label_tokens, labels=labels, hit=hit):
        return 0.08
    return 0.0


def broad_label_penalty_for_hit(
    *,
    query_tokens: list[str],
    label_tokens: set[str],
    hit: dict,
    is_exact_match: bool = False,
) -> float:
    specific_tokens = specific_query_token_set(query_tokens)
    if len(specific_tokens) < 2:
        return 0.0
    if not (specific_tokens & label_tokens):
        return 0.0
    if is_exact_match:
        return 0.0
    if not is_broad_primary_label(hit):
        return 0.0
    matched_specific = specific_tokens & label_tokens
    missing_specific = specific_tokens - label_tokens
    if not missing_specific:
        return 0.0
    if len(matched_specific) <= 1:
        return 0.24
    return 0.14


def clinical_context_sense_penalty_for_hit(
    *,
    query_tokens: list[str],
    raw_query_tokens: set[str] | None = None,
    label_tokens: set[str],
    labels: list[str],
    hit: dict,
) -> float:
    query_set = set(query_tokens)
    raw_query_set = set(raw_query_tokens or ()) | query_set
    semantic_types = semantic_type_names(hit)
    matched_specific = specific_query_token_set(query_tokens) & label_tokens
    penalty = 0.0
    if label_is_history_context(labels=labels, label_tokens=label_tokens) and not query_asks_for_history(query_set):
        penalty = max(penalty, 0.34)
    if label_is_susceptibility_context(label_tokens=label_tokens) and not query_asks_for_susceptibility(query_set):
        penalty = max(penalty, 0.34)
    if label_is_staging_context(label_tokens=label_tokens) and not query_asks_for_staging(query_set):
        penalty = max(penalty, 0.24)
    if label_is_generic_mutation_context(label_tokens=label_tokens) and query_has_specific_mutation_context(query_set):
        penalty = max(penalty, 0.24)
    if label_is_broad_thromboembolism_fragment(
        label_tokens=label_tokens
    ) and query_has_specific_thromboembolism_context(query_set):
        penalty = max(penalty, 0.34)
    if hit_has_generic_prose_status_context(
        hit=hit,
        labels=labels,
        label_tokens=label_tokens,
    ) and query_has_biomedical_context_beyond_prose_status(query_set):
        penalty = max(penalty, 0.60)
    if hit_has_confirmation_status_context(
        hit=hit,
        labels=labels,
        label_tokens=label_tokens,
    ) and query_has_biomedical_context_beyond_prose_status(query_set):
        penalty = max(penalty, 0.95)
    if label_is_mortality_outcome_context(label_tokens=label_tokens) and not query_asks_for_mortality_outcome(
        raw_query_set
    ):
        penalty = max(penalty, 0.50)
    if label_is_device_alert_metadata_context(label_tokens=label_tokens) and not query_asks_for_device_alert_metadata(
        query_set
    ):
        penalty = max(penalty, 0.50)
    if label_is_sleep_metric_context(label_tokens=label_tokens) and not query_asks_for_sleep_metric(
        query_set
    ):
        penalty = max(penalty, 0.34)
    if label_is_prior_condition_context(
        semantic_types=semantic_types,
        label_tokens=label_tokens,
    ) and not query_asks_for_prior_condition(query_set):
        penalty = max(penalty, 0.34)
    if label_is_recent_condition_context(
        semantic_types=semantic_types,
        label_tokens=label_tokens,
        labels=labels,
    ) and not query_asks_for_recent_condition(raw_query_set):
        penalty = max(penalty, 0.24)
    if label_is_periprocedural_context(
        semantic_types=semantic_types,
        label_tokens=label_tokens,
    ) and not query_asks_for_periprocedural_context(query_set):
        penalty = max(penalty, 0.24)
    if label_is_resistant_organism_context(
        semantic_types=semantic_types,
        label_tokens=label_tokens,
    ) and not query_asks_for_resistant_organism(query_set):
        penalty = max(penalty, 0.34)
    if hit_has_broad_organism_context(
        hit=hit,
        labels=labels,
        semantic_types=semantic_types,
    ) and not query_asks_for_broad_organism(query_set):
        penalty = max(penalty, 0.70)
    if hit_has_broad_infection_disease_context(
        hit=hit,
        labels=labels,
        semantic_types=semantic_types,
    ) and not query_asks_for_broad_infection_disease(query_set):
        penalty = max(penalty, 0.70)
    if hit_has_yes_no_answer_status_context(hit=hit, labels=labels) and not query_asks_for_yes_no_answer(
        raw_query_set
    ):
        penalty = max(penalty, 0.95)
    if query_set & NORMAL_EXAM_CONTEXT_TOKENS:
        if semantic_types & DRUG_CHEMICAL_VIEW_SEMANTIC_TYPES and label_tokens & NORMAL_EXAM_CONTEXT_TOKENS:
            penalty = max(penalty, 0.42)
    if is_cognitive_memory_context(query_set):
        if "memory" in label_tokens and not (label_tokens & (COGNITIVE_MEMORY_LABEL_TOKENS | {"loss"})):
            if semantic_types & (FRAGMENT_SEMANTIC_TYPES | GENE_PROTEIN_VIEW_SEMANTIC_TYPES | DRUG_CHEMICAL_VIEW_SEMANTIC_TYPES):
                penalty = max(penalty, 0.42)
    if is_therapy_transition_context(query_set):
        if semantic_types & PROCEDURE_SEMANTIC_TYPES:
            if not label_tokens & THERAPY_TRANSITION_ALLOWED_LABEL_TOKENS:
                penalty = max(penalty, 0.36)
            elif matched_specific <= {"therapy"} and not label_tokens & {"physical", "rehabilitation"}:
                penalty = max(penalty, 0.24)
    if "cervical" in query_set:
        query_gyne = query_has_cervical_gynecology_context(query_set)
        query_spine = query_has_cervical_spine_context(query_set)
        if query_gyne and not query_spine and label_is_cervical_spine_or_neck_context(
            label_tokens=label_tokens
        ):
            penalty = max(penalty, 0.42)
        if query_spine and not query_gyne and label_is_cervical_gynecology_context(
            label_tokens=label_tokens
        ):
            penalty = max(penalty, 0.42)
    if {"non", "st"} <= query_set and "st" in label_tokens:
        if (label_tokens & {"elevation", "elevated"}) and "non" not in label_tokens:
            penalty = max(penalty, 0.18)
    if {"poorly", "controlled"} <= query_set:
        if (
            has_generic_diabetes_label(labels=labels, hit=hit)
            and not {"poorly", "controlled"} <= label_tokens
        ):
            penalty = max(penalty, 0.50)
    if {"gestational", "diabetes"} <= query_set:
        if has_generic_diabetes_label(labels=labels, hit=hit) and "gestational" not in label_tokens:
            penalty = max(penalty, 0.95)
    if hit_has_broad_therapy_component_context(
        hit=hit,
        labels=labels,
        semantic_types=semantic_types,
    ):
        if query_uses_component_as_part_of_more_specific_phrase(query_set):
            penalty = max(penalty, 0.85)
    if (
        label_tokens & BRAND_LABEL_TOKENS
        and semantic_types & DRUG_CHEMICAL_VIEW_SEMANTIC_TYPES
        and not (query_set & DRUG_ROLE_QUERY_TOKENS)
    ):
        penalty = max(penalty, 0.42)
    if (
        label_tokens & VACCINE_LABEL_TOKENS
        and semantic_types & DRUG_CHEMICAL_VIEW_SEMANTIC_TYPES
        and not (query_set & VACCINE_INTENT_QUERY_TOKENS)
    ):
        penalty = max(penalty, 0.42)
    if label_is_emergency_setting_noise(label_tokens=label_tokens) and query_uses_emergency_as_setting(
        query_set
    ):
        penalty = max(penalty, 0.42)
    if hit_has_contextual_false_positive_anchor_context(
        hit=hit,
        labels=labels,
        label_tokens=label_tokens,
        query_tokens=query_set,
        semantic_types=semantic_types,
    ):
        penalty = max(penalty, 0.70)
    if "infection" in query_set and "infection" in label_tokens:
        query_sites = query_set & INFECTION_SITE_TOKENS
        label_sites = label_tokens & INFECTION_SITE_TOKENS
        if content_tokens(str(hit.get("name") or "")) == ["infection"] and (
            (query_set & SPECIFIC_INFECTION_CONTEXT_TOKENS) - {"infection"}
        ):
            penalty = max(penalty, 0.24)
        if query_sites and label_sites and not (query_sites & label_sites):
            penalty = max(penalty, 0.34)
        elif {"urinary", "tract"} <= query_set and not (label_tokens & {"urinary", "tract"}):
            penalty = max(penalty, 0.24)
    return penalty


def label_is_history_context(*, labels: list[str], label_tokens: set[str]) -> bool:
    if label_tokens & {"history", "historical"}:
        return True
    normalized_labels = [" ".join(content_tokens(label)) for label in labels]
    return any(
        label.startswith(("h o ", "history of ", "past history of ", "personal history of "))
        for label in normalized_labels
    )


def query_asks_for_history(query_tokens: set[str]) -> bool:
    return bool(query_tokens & {"history", "historical", "past", "prior", "previous", "family"})


def label_is_susceptibility_context(*, label_tokens: set[str]) -> bool:
    return bool(label_tokens & {"predisposition", "risk", "susceptibility", "susceptible"})


def query_asks_for_susceptibility(query_tokens: set[str]) -> bool:
    return bool(
        query_tokens
        & {
            "family",
            "familial",
            "gene",
            "genes",
            "genetic",
            "genetics",
            "predisposition",
            "risk",
            "susceptibility",
            "susceptible",
            "variant",
            "variants",
        }
    )


def label_is_staging_context(*, label_tokens: set[str]) -> bool:
    return bool(label_tokens & {"stage", "staging"})


def query_asks_for_staging(query_tokens: set[str]) -> bool:
    return bool(query_tokens & {"stage", "staging", "tnm"})


GENERIC_MUTATION_LABEL_TOKENS = {"abnormality", "abnormalities", "mutation", "mutations"}
GENERIC_MUTATION_QUERY_TOKENS = {"abnormality", "abnormalities", "mutation", "mutations", "mutated"}


def label_is_generic_mutation_context(*, label_tokens: set[str]) -> bool:
    return bool(label_tokens & {"mutation", "mutations"}) and not (
        label_tokens - GENERIC_MUTATION_LABEL_TOKENS
    )


def query_has_specific_mutation_context(query_tokens: set[str]) -> bool:
    return bool(query_tokens & GENERIC_MUTATION_QUERY_TOKENS) and bool(
        query_tokens - GENERIC_MUTATION_QUERY_TOKENS
    )


BROAD_THROMBOEMBOLISM_LABEL_TOKENS = {
    "emboli",
    "embolism",
    "embolu",
    "embolus",
    "thrombi",
    "thromboemboli",
    "thromboembolu",
    "thromboembolism",
    "thrombosis",
    "thrombu",
    "thrombus",
}
THROMBOEMBOLISM_SITE_TOKENS = {
    "arterial",
    "artery",
    "brain",
    "cerebral",
    "coronary",
    "deep",
    "lung",
    "pulmonary",
    "vein",
    "venous",
}


def label_is_broad_thromboembolism_fragment(*, label_tokens: set[str]) -> bool:
    return bool(label_tokens & BROAD_THROMBOEMBOLISM_LABEL_TOKENS) and label_tokens <= (
        BROAD_THROMBOEMBOLISM_LABEL_TOKENS
    )


def query_has_specific_thromboembolism_context(query_tokens: set[str]) -> bool:
    return bool(query_tokens & BROAD_THROMBOEMBOLISM_LABEL_TOKENS) and bool(
        query_tokens & THROMBOEMBOLISM_SITE_TOKENS
    )


GENERIC_PROSE_STATUS_LABEL_TOKENS = {
    "administration",
    "declined",
    "confirmed",
    "confirmation",
    "developed",
    "diagnosed",
    "demonstrated",
    "documented",
    "during",
    "evaluated",
    "evaluation",
    "follow",
    "new",
    "newly",
    "not",
    "onset",
    "ordered",
    "performed",
    "prescribed",
    "received",
    "recommended",
    "record",
    "response",
    "reviewed",
    "started",
    "statu",
    "testing",
    "treat",
    "up",
    "visit",
}
GENERIC_PROSE_STATUS_FILLER_TOKENS = {
    "contextual",
    "drug",
    "medication",
    "procedure",
    "qualifier",
    "therapy",
}
GENERIC_PROSE_STATUS_QUERY_TOKENS = (
    GENERIC_PROSE_STATUS_LABEL_TOKENS | GENERIC_PROSE_STATUS_FILLER_TOKENS
)


def label_is_generic_prose_status_context(*, label_tokens: set[str]) -> bool:
    meaningful_tokens = label_tokens - GENERIC_PROSE_STATUS_FILLER_TOKENS
    return bool(meaningful_tokens) and meaningful_tokens <= GENERIC_PROSE_STATUS_LABEL_TOKENS


def hit_primary_label_token_sets(
    *,
    hit: dict,
    labels: list[str],
    include_matched: bool = True,
    label_limit: int = 3,
) -> list[set[str]]:
    primary_values = []
    if include_matched:
        primary_values.append(str(hit.get("matched_label") or ""))
    primary_values.append(str(hit.get("name") or ""))
    primary_values.extend(str(label) for label in labels[:label_limit])
    token_sets = []
    seen = set()
    for value in primary_values:
        normalized = normalized_key(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        tokens = set(content_tokens(value))
        if tokens:
            token_sets.append(tokens)
    return token_sets


def hit_has_generic_prose_status_context(
    *,
    hit: dict,
    labels: list[str],
    label_tokens: set[str],
) -> bool:
    if label_is_generic_prose_status_context(label_tokens=label_tokens):
        return True
    return any(
        label_is_generic_prose_status_context(label_tokens=token_set)
        for token_set in hit_primary_label_token_sets(hit=hit, labels=labels)
    )


def query_has_biomedical_context_beyond_prose_status(query_tokens: set[str]) -> bool:
    return bool(
        query_tokens - GENERIC_PROSE_STATUS_QUERY_TOKENS - LOW_SPECIFICITY_QUERY_TOKENS
    )


CONFIRMATION_STATUS_LABEL_TOKENS = {
    "confirm",
    "confirmed",
    "confirmation",
    "unconfirmed",
}
CONFIRMATION_STATUS_FILLER_TOKENS = {"by", "not", "statu", "status"}


def label_is_confirmation_status_context(*, label_tokens: set[str]) -> bool:
    meaningful_tokens = label_tokens - CONFIRMATION_STATUS_FILLER_TOKENS
    return bool(meaningful_tokens) and meaningful_tokens <= CONFIRMATION_STATUS_LABEL_TOKENS


def hit_has_confirmation_status_context(
    *,
    hit: dict,
    labels: list[str],
    label_tokens: set[str],
) -> bool:
    if label_is_confirmation_status_context(label_tokens=label_tokens):
        return True
    return any(
        label_is_confirmation_status_context(label_tokens=token_set)
        for token_set in hit_primary_label_token_sets(hit=hit, labels=labels)
    )


MORTALITY_OUTCOME_LABEL_TOKENS = {
    "dead",
    "death",
    "deaths",
    "deceased",
    "died",
    "fatal",
    "fatality",
    "fatalities",
    "mortality",
}
MORTALITY_OUTCOME_FILLER_TOKENS = {
    "event",
    "events",
    "finding",
    "outcome",
    "outcomes",
    "rate",
    "rates",
    "risk",
    "statu",
    "status",
}
MORTALITY_OUTCOME_QUERY_TOKENS = MORTALITY_OUTCOME_LABEL_TOKENS | {"survival", "survive"}


def label_is_mortality_outcome_context(*, label_tokens: set[str]) -> bool:
    meaningful_tokens = label_tokens - MORTALITY_OUTCOME_FILLER_TOKENS
    return bool(meaningful_tokens & MORTALITY_OUTCOME_LABEL_TOKENS) and meaningful_tokens <= (
        MORTALITY_OUTCOME_LABEL_TOKENS
    )


def query_asks_for_mortality_outcome(query_tokens: set[str]) -> bool:
    return bool(query_tokens & MORTALITY_OUTCOME_QUERY_TOKENS)


CERVICAL_GYNECOLOGY_CONTEXT_TOKENS = {
    "adnexal",
    "cancer",
    "cervix",
    "chlamydia",
    "colposcopy",
    "doxycycline",
    "dysplasia",
    "gonorrhea",
    "gynecologic",
    "hpv",
    "intraepithelial",
    "laceration",
    "motion",
    "neoplasm",
    "pap",
    "papanicolaou",
    "pelvic",
    "pid",
    "polyp",
    "pregnancy",
    "smear",
    "tenderness",
    "uterine",
    "uterus",
    "vaginal",
    "vagina",
}
CERVICAL_SPINE_CONTEXT_TOKENS = {
    "atlas",
    "axis",
    "cord",
    "disc",
    "disk",
    "fracture",
    "fusion",
    "laminectomy",
    "mri",
    "myelopathy",
    "neck",
    "nerve",
    "plexus",
    "radiculopathy",
    "spinal",
    "spine",
    "spondylosis",
    "stenosis",
    "trauma",
    "vertebra",
    "vertebrae",
    "vertebral",
}


def query_has_cervical_gynecology_context(query_tokens: set[str]) -> bool:
    return bool(query_tokens & CERVICAL_GYNECOLOGY_CONTEXT_TOKENS)


def query_has_cervical_spine_context(query_tokens: set[str]) -> bool:
    return bool(query_tokens & CERVICAL_SPINE_CONTEXT_TOKENS)


def label_is_cervical_gynecology_context(*, label_tokens: set[str]) -> bool:
    return "cervical" in label_tokens and bool(label_tokens & CERVICAL_GYNECOLOGY_CONTEXT_TOKENS)


def label_is_cervical_spine_or_neck_context(*, label_tokens: set[str]) -> bool:
    return "cervical" in label_tokens and bool(label_tokens & CERVICAL_SPINE_CONTEXT_TOKENS)


EMERGENCY_SETTING_QUERY_TOKENS = {
    "department",
    "ed",
    "responder",
    "responders",
    "room",
}
EMERGENCY_LABEL_FILLER_TOKENS = {
    "disease",
    "finding",
    "findings",
}


def label_is_emergency_setting_noise(*, label_tokens: set[str]) -> bool:
    meaningful_tokens = label_tokens - EMERGENCY_LABEL_FILLER_TOKENS
    return bool(meaningful_tokens) and meaningful_tokens <= {"emergency"}


def query_uses_emergency_as_setting(query_tokens: set[str]) -> bool:
    return "emergency" in query_tokens and bool(query_tokens & EMERGENCY_SETTING_QUERY_TOKENS)


DEVICE_ALERT_METADATA_LABEL_TOKENS = {"devicealertlevel"}
DEVICE_ALERT_METADATA_QUERY_TOKENS = {"alert", "device", "devicealertlevel"}
DEVICE_INTENT_QUERY_TOKENS = {
    "device",
    "devices",
    "equipment",
    "machine",
    "probe",
    "scanner",
    "transducer",
}
ULTRASOUND_DEVICE_LABEL_TOKENS = {"device", "equipment", "ultrasound"}
CLINICAL_BASELINE_CONTEXT_TOKENS = {
    "albumin",
    "bilirubin",
    "creatinine",
    "glucose",
    "hemoglobin",
    "lactate",
    "platelet",
    "potassium",
    "sodium",
    "troponin",
}
DENTAL_MATERIAL_LABEL_TOKENS = {"cement", "dental"}
URINARY_CAST_CONTEXT_TOKENS = {
    "aki",
    "creatinine",
    "granular",
    "kidney",
    "nephrology",
    "renal",
    "sediment",
    "urinalysis",
    "urinary",
    "urine",
}
ORTHOPEDIC_CAST_LABEL_TOKENS = {"cast", "orthopedic", "plaster"}
ORTHOPEDIC_ASPIRATION_CONTEXT_TOKENS = {
    "arthroplasty",
    "joint",
    "knee",
    "orthopedic",
    "prosthetic",
    "synovial",
}
RESPIRATORY_ASPIRATION_CONTEXT_TOKENS = {
    "airway",
    "body",
    "foreign",
    "pneumonia",
    "pulmonary",
    "respiratory",
}
RESPIRATORY_ASPIRATION_LABEL_TOKENS = {"aspiration", "aspirated", "respiratory"}
ANATOMY_EXTRACT_LABEL_TOKENS = {
    "brain",
    "heart",
    "kidney",
    "liver",
    "lung",
    "pancreas",
    "spleen",
    "thyroid",
}
EXTRACT_INTENT_QUERY_TOKENS = {"extract", "supplement", "supplements"}
COUGH_DRUG_INGREDIENT_TOKENS = {"dextromethorphan", "guaifenesin"}


def label_is_device_alert_metadata_context(*, label_tokens: set[str]) -> bool:
    return bool(label_tokens & DEVICE_ALERT_METADATA_LABEL_TOKENS)


def query_asks_for_device_alert_metadata(query_tokens: set[str]) -> bool:
    return bool(query_tokens & DEVICE_ALERT_METADATA_QUERY_TOKENS)


def query_asks_for_device_or_equipment(query_tokens: set[str]) -> bool:
    return bool(query_tokens & DEVICE_INTENT_QUERY_TOKENS)


def query_asks_for_extract_or_supplement(query_tokens: set[str]) -> bool:
    return bool(query_tokens & EXTRACT_INTENT_QUERY_TOKENS)


def query_uses_urinary_cast_context(query_tokens: set[str]) -> bool:
    return "cast" in query_tokens and bool(query_tokens & URINARY_CAST_CONTEXT_TOKENS)


def query_uses_orthopedic_aspiration_context(query_tokens: set[str]) -> bool:
    if not (query_tokens & {"aspirate", "aspirated", "aspiration"}):
        return False
    if not (query_tokens & ORTHOPEDIC_ASPIRATION_CONTEXT_TOKENS):
        return False
    return not bool(query_tokens & RESPIRATORY_ASPIRATION_CONTEXT_TOKENS)


def hit_has_contextual_false_positive_anchor_context(
    *,
    hit: dict,
    labels: list[str],
    label_tokens: set[str],
    query_tokens: set[str],
    semantic_types: set[str],
) -> bool:
    primary_token_sets = hit_primary_label_token_sets(hit=hit, labels=labels)
    if not query_has_context_beyond_primary_label(query_tokens, primary_token_sets, label_tokens):
        return False
    semantic_group = str(hit.get("semantic_group") or "")
    if (
        "baseline" in query_tokens
        and label_tokens >= DENTAL_MATERIAL_LABEL_TOKENS
        and (query_tokens & CLINICAL_BASELINE_CONTEXT_TOKENS)
    ):
        return True
    if (
        query_uses_urinary_cast_context(query_tokens)
        and "cast" in label_tokens
        and bool(label_tokens & ORTHOPEDIC_CAST_LABEL_TOKENS)
        and (semantic_group == "DEVI" or semantic_types & {"medical device"})
    ):
        return True
    if (
        query_uses_orthopedic_aspiration_context(query_tokens)
        and "respiratory" in label_tokens
        and bool(label_tokens & RESPIRATORY_ASPIRATION_LABEL_TOKENS)
    ):
        return True
    if (
        "ultrasound" in label_tokens
        and label_tokens & ULTRASOUND_DEVICE_LABEL_TOKENS
        and (semantic_group == "DEVI" or semantic_types & {"medical device"})
        and not query_asks_for_device_or_equipment(query_tokens)
    ):
        return True
    if (
        semantic_types & DRUG_CHEMICAL_VIEW_SEMANTIC_TYPES
        and "extract" in label_tokens
        and label_tokens & ANATOMY_EXTRACT_LABEL_TOKENS
        and not query_asks_for_extract_or_supplement(query_tokens)
    ):
        return True
    if (
        semantic_types & DRUG_CHEMICAL_VIEW_SEMANTIC_TYPES
        and "cough" in label_tokens
        and bool(label_tokens & COUGH_DRUG_INGREDIENT_TOKENS)
        and "cough" in query_tokens
        and not (query_tokens & DRUG_ROLE_QUERY_TOKENS)
    ):
        return True
    return False


SLEEP_METRIC_LABEL_TOKENS = {"after", "onset", "sleep", "wake"}
SLEEP_METRIC_QUERY_TOKENS = {
    "apnea",
    "apnoea",
    "insomnia",
    "narcolepsy",
    "sleep",
    "sleepiness",
    "somnolence",
    "wake",
}


def label_is_sleep_metric_context(*, label_tokens: set[str]) -> bool:
    return bool(label_tokens & {"sleep", "wake"}) and bool(
        label_tokens & SLEEP_METRIC_LABEL_TOKENS
    )


def query_asks_for_sleep_metric(query_tokens: set[str]) -> bool:
    return bool(query_tokens & SLEEP_METRIC_QUERY_TOKENS)


TEMPORAL_CONDITION_CONTEXT_SEMANTIC_TYPES = {
    "disease or syndrome",
    "finding",
    "mental or behavioral dysfunction",
    "neoplastic process",
    "pathologic function",
}
PRIOR_CONDITION_LABEL_TOKENS = {"old"}
PRIOR_CONDITION_QUERY_TOKENS = {"history", "historical", "old", "past", "prior", "previous"}
RECENT_CONDITION_LABEL_TOKENS = {"recent"}
RECENT_CONDITION_QUERY_TOKENS = {"recent", "recently"}
PERIPROCEDURAL_LABEL_TOKENS = {"periprocedural"}
PERIPROCEDURAL_QUERY_TOKENS = {"periprocedural", "perioperative", "procedure", "procedural"}


def label_is_prior_condition_context(*, semantic_types: set[str], label_tokens: set[str]) -> bool:
    return bool(semantic_types & TEMPORAL_CONDITION_CONTEXT_SEMANTIC_TYPES) and bool(
        label_tokens & PRIOR_CONDITION_LABEL_TOKENS
    )


def query_asks_for_prior_condition(query_tokens: set[str]) -> bool:
    return bool(query_tokens & PRIOR_CONDITION_QUERY_TOKENS)


def label_is_recent_condition_context(
    *,
    semantic_types: set[str],
    label_tokens: set[str],
    labels: list[str],
) -> bool:
    if not (semantic_types & TEMPORAL_CONDITION_CONTEXT_SEMANTIC_TYPES):
        return False
    if label_tokens & RECENT_CONDITION_LABEL_TOKENS:
        return True
    return any(str(label or "").strip().lower().startswith("recent ") for label in labels)


def query_asks_for_recent_condition(query_tokens: set[str]) -> bool:
    return bool(query_tokens & RECENT_CONDITION_QUERY_TOKENS)


def label_is_periprocedural_context(*, semantic_types: set[str], label_tokens: set[str]) -> bool:
    return bool(semantic_types & TEMPORAL_CONDITION_CONTEXT_SEMANTIC_TYPES) and bool(
        label_tokens & PERIPROCEDURAL_LABEL_TOKENS
    )


def query_asks_for_periprocedural_context(query_tokens: set[str]) -> bool:
    return bool(query_tokens & PERIPROCEDURAL_QUERY_TOKENS)


ORGANISM_CONTEXT_SEMANTIC_TYPES = {
    "archaeon",
    "bacterium",
    "fungus",
    "rickettsia or chlamydia",
    "virus",
}
BROAD_INFECTION_DISEASE_CONTEXT_SEMANTIC_TYPES = {
    "disease or syndrome",
    "pathologic function",
}
BROAD_INFECTION_DISEASE_LABEL_TOKEN_SETS = {
    frozenset({"communicable", "disease"}),
    frozenset({"viral", "illness"}),
    frozenset({"viru", "disease"}),
}
BROAD_INFECTION_DISEASE_QUERY_TOKENS = {
    "communicable",
    "disease",
    "illness",
    "infection",
    "viral",
    "viru",
}
BROAD_ORGANISM_LABEL_TOKEN_SETS = {
    frozenset({"bacteria"}),
    frozenset({"bacterium"}),
    frozenset({"bacterial", "organism"}),
}
BROAD_ORGANISM_QUERY_TOKENS = {
    "bacteria",
    "bacterium",
    "bacterial",
    "organism",
    "organisms",
}
YES_NO_ANSWER_LABELS = {"no", "yes"}
RESISTANT_ORGANISM_LABEL_TOKENS = {"resistance", "resistant"}
RESISTANT_ORGANISM_QUERY_TOKENS = {
    "culture",
    "cultures",
    "grew",
    "growth",
    "mrsa",
    "resistance",
    "resistant",
    "vre",
}


def label_is_resistant_organism_context(*, semantic_types: set[str], label_tokens: set[str]) -> bool:
    return bool(semantic_types & ORGANISM_CONTEXT_SEMANTIC_TYPES) and bool(
        label_tokens & RESISTANT_ORGANISM_LABEL_TOKENS
    )


def query_asks_for_resistant_organism(query_tokens: set[str]) -> bool:
    return bool(query_tokens & RESISTANT_ORGANISM_QUERY_TOKENS)


def hit_has_broad_organism_context(
    *,
    hit: dict,
    labels: list[str],
    semantic_types: set[str],
) -> bool:
    if not (semantic_types & ORGANISM_CONTEXT_SEMANTIC_TYPES):
        return False
    for token_set in hit_primary_label_token_sets(
        hit=hit,
        labels=labels,
        include_matched=False,
        label_limit=1,
    ):
        if frozenset(token_set) in BROAD_ORGANISM_LABEL_TOKEN_SETS:
            return True
    return False


def query_asks_for_broad_organism(query_tokens: set[str]) -> bool:
    useful_tokens = query_tokens - LOW_SPECIFICITY_QUERY_TOKENS
    return bool(useful_tokens) and useful_tokens <= BROAD_ORGANISM_QUERY_TOKENS


def hit_has_broad_infection_disease_context(
    *,
    hit: dict,
    labels: list[str],
    semantic_types: set[str],
) -> bool:
    if not (semantic_types & BROAD_INFECTION_DISEASE_CONTEXT_SEMANTIC_TYPES):
        return False
    for token_set in hit_primary_label_token_sets(hit=hit, labels=labels, label_limit=2):
        if frozenset(token_set) in BROAD_INFECTION_DISEASE_LABEL_TOKEN_SETS:
            return True
    return False


def query_asks_for_broad_infection_disease(query_tokens: set[str]) -> bool:
    useful_tokens = query_tokens - LOW_SPECIFICITY_QUERY_TOKENS
    return bool(useful_tokens) and useful_tokens <= BROAD_INFECTION_DISEASE_QUERY_TOKENS


def hit_has_yes_no_answer_status_context(*, hit: dict, labels: list[str]) -> bool:
    return any(
        frozenset(token_set) in {frozenset({"yes"}), frozenset({"no"})}
        for token_set in hit_primary_label_token_sets(hit=hit, labels=labels, label_limit=2)
    )


def query_asks_for_yes_no_answer(query_tokens: set[str]) -> bool:
    return bool(query_tokens) and query_tokens <= YES_NO_ANSWER_LABELS


def hit_has_broad_symptom_aggregate_context(
    *,
    hit: dict,
    labels: list[str],
    semantic_types: set[str],
) -> bool:
    if not (semantic_types & {"finding", "sign or symptom"}):
        return False
    for tokens in hit_primary_label_token_sets(hit=hit, labels=labels, label_limit=2):
        if not tokens or not (tokens & {"symptom", "symptoms"}):
            continue
        if tokens <= BROAD_SYMPTOM_AGGREGATE_LABEL_TOKENS:
            return True
    return False


def is_cognitive_memory_context(query_tokens: set[str]) -> bool:
    if "memory" not in query_tokens:
        return False
    return bool(query_tokens & (COGNITIVE_MEMORY_CONTEXT_TOKENS | {"difficulty", "manage", "management"}))


def has_generic_diabetes_label(*, labels: list[str], hit: dict) -> bool:
    values = [str(hit.get("name") or ""), *[str(label) for label in labels]]
    for value in values:
        tokens = set(content_tokens(value))
        if not tokens:
            continue
        if not (tokens & {"diabetes", "mellitu", "mellitus"}):
            continue
        if tokens <= DIABETES_CONTROL_GENERIC_LABEL_TOKENS:
            return True
    return False


def hit_has_broad_therapy_component_context(
    *,
    hit: dict,
    labels: list[str],
    semantic_types: set[str],
) -> bool:
    if not (semantic_types & PHARMACOLOGIC_SEMANTIC_TYPES):
        return False
    for tokens in hit_primary_label_token_sets(hit=hit, labels=labels, label_limit=2):
        if tokens and tokens <= {"androgen", "androgens", "opioid", "opioids"}:
            return True
    return False


def query_uses_component_as_part_of_more_specific_phrase(query_tokens: set[str]) -> bool:
    return (
        {"opioid", "use", "disorder"} <= query_tokens
        or {"opioid", "withdrawal"} <= query_tokens
        or {"androgen", "deprivation", "therapy"} <= query_tokens
    )


def is_therapy_transition_context(query_tokens: set[str]) -> bool:
    if "therapy" not in query_tokens:
        return False
    return len(query_tokens & THERAPY_TRANSITION_CONTEXT_TOKENS) >= 3


def semantic_fragment_mismatch_penalty(
    *,
    query_tokens: list[str],
    label_tokens: set[str],
    hit: dict,
) -> float:
    specific_tokens = specific_query_token_set(query_tokens)
    if len(specific_tokens) < 2:
        return 0.0
    matched_specific = specific_tokens & label_tokens
    if (
        label_tokens
        and label_tokens <= LATERALITY_FRAGMENT_TOKENS
        and matched_specific
        and bool(specific_tokens - LATERALITY_FRAGMENT_TOKENS)
    ):
        return 0.24
    if is_standalone_modifier_fragment(hit, specific_tokens=specific_tokens):
        return MODIFIER_FRAGMENT_PENALTY
    if (
        label_tokens & BRAND_LABEL_TOKENS
        and semantic_type_names(hit) & DRUG_CHEMICAL_VIEW_SEMANTIC_TYPES
        and not (set(query_tokens) & DRUG_ROLE_QUERY_TOKENS)
    ):
        return 0.24
    if (
        label_tokens & VACCINE_LABEL_TOKENS
        and semantic_type_names(hit) & DRUG_CHEMICAL_VIEW_SEMANTIC_TYPES
        and not (set(query_tokens) & VACCINE_INTENT_QUERY_TOKENS)
    ):
        return 0.24
    if not matched_specific or len(matched_specific) > 1:
        return 0.0
    if semantic_type_names(hit) & FRAGMENT_SEMANTIC_TYPES:
        return 0.18
    return 0.0


def is_standalone_modifier_fragment(hit: dict, *, specific_tokens: set[str]) -> bool:
    if not (semantic_type_names(hit) & MODIFIER_FRAGMENT_SEMANTIC_TYPES):
        return False
    if not (specific_tokens & MODIFIER_FRAGMENT_LABEL_TOKENS):
        return False
    if not (specific_tokens - MODIFIER_FRAGMENT_LABEL_TOKENS):
        return False
    candidate_labels = [str(hit.get("name") or ""), *[str(label) for label in hit.get("labels") or []]]
    for label in candidate_labels:
        tokens = set(content_tokens(label)) - {"qualifier", "value"}
        if tokens and tokens <= MODIFIER_FRAGMENT_LABEL_TOKENS and tokens & specific_tokens:
            return True
    return False


def generic_query_fragment_penalty(query_tokens: list[str], label_tokens: set[str]) -> float:
    specific_tokens = specific_query_token_set(query_tokens)
    if len(specific_tokens) < 2:
        return 0.0
    matched_specific = specific_tokens & label_tokens
    matched_low_specificity = (set(query_tokens) & LOW_SPECIFICITY_QUERY_TOKENS) & label_tokens
    if not matched_low_specificity or len(matched_specific) > 1:
        return 0.0
    penalty = 0.08
    unmatched_rare = rare_query_anchor_tokens(specific_tokens) - label_tokens
    if unmatched_rare:
        penalty += 0.04
    return min(penalty, 0.12)


def normal_exam_fragment_penalty_for_hit(
    *,
    query_tokens: list[str],
    label_tokens: set[str],
    hit: dict,
) -> float:
    query_set = set(query_tokens)
    if not (query_set & NORMAL_EXAM_CONTEXT_TOKENS):
        return 0.0
    matched_specific = specific_query_token_set(query_tokens) & label_tokens
    if not matched_specific:
        return 0.0
    if not matched_specific <= NORMAL_EXAM_FRAGMENT_TOKENS:
        return 0.0
    if label_tokens & NORMAL_EXAM_ALLOWED_LABEL_TOKENS:
        return 0.0
    semantic_types = semantic_type_names(hit)
    if semantic_types & COMPOSITE_CONTEXT_SEMANTIC_TYPES:
        return 0.30
    if semantic_types & PROCEDURE_SEMANTIC_TYPES:
        return 0.18
    return 0.12
