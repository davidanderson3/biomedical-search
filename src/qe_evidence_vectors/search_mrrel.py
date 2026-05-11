from __future__ import annotations

from qe_evidence_vectors.search_role_tokens import (
    ACTION_OBSERVATION_QUERY_TOKENS,
    DRUG_ROLE_QUERY_TOKENS,
    PROCEDURE_ROLE_TOKENS,
    THERAPEUTIC_ACTION_QUERY_TOKENS,
)
from qe_evidence_vectors.search_semantics import RELATION_CATEGORY_SEMANTIC_GROUPS
from qe_evidence_vectors.search_tokens import content_tokens


MRREL_RANK_COMPONENT_CAP = 0.22
MRREL_RESEARCH_COMPONENT_CAP = 0.18
MRREL_GENERIC_COMPONENT_CAP = 0.07
MRREL_RELATION_GROUP_WEIGHTS = {
    "treatment": 0.055,
    "procedure_or_test": 0.050,
    "genetic_association": 0.050,
    "safety_or_cause": 0.045,
    "phenotype": 0.040,
    "associated": 0.025,
}
MRREL_GENERIC_RELATION_GROUP_WEIGHT = 0.015
MRREL_CATEGORY_ROLE_TOKENS = {
    "condition": {
        "condition",
        "disease",
        "disorder",
        "finding",
        "sign",
        "symptom",
        "syndrome",
    },
    "phenotype": {
        "abnormality",
        "finding",
        "phenotype",
        "sign",
        "symptom",
        "trait",
    },
    "gene_protein": {
        "biomarker",
        "gene",
        "genetic",
        "genome",
        "mutation",
        "protein",
        "variant",
    },
    "drug_chemical": DRUG_ROLE_QUERY_TOKENS | THERAPEUTIC_ACTION_QUERY_TOKENS | {
        "antibiotic",
        "anticoagulant",
        "medicine",
        "pressor",
        "vasopressor",
    },
    "procedure_test": PROCEDURE_ROLE_TOKENS | ACTION_OBSERVATION_QUERY_TOKENS | {
        "assay",
        "diagnostic",
        "imaging",
        "lab",
        "laboratory",
        "panel",
        "screen",
        "screening",
        "test",
        "testing",
    },
    "device": {
        "catheter",
        "device",
        "implant",
        "pacemaker",
        "prosthesis",
        "stent",
    },
    "organism": {
        "bacterium",
        "fungus",
        "infection",
        "microbe",
        "organism",
        "pathogen",
        "virus",
    },
}


def relation_category_matches_query_role(category: str, query_set: set[str]) -> bool:
    if not category:
        return False
    return bool(query_set & MRREL_CATEGORY_ROLE_TOKENS.get(category, set()))


def mrrel_relation_group_from_relation(relation: dict) -> str:
    relation_text = " ".join(
        str(relation.get(key) or "").lower()
        for key in ("relation_group", "rela", "relation")
    )
    if any(token in relation_text for token in ("treat", "therapy", "therapeutic", "regimen")):
        return "treatment"
    if any(token in relation_text for token in ("procedure", "method", "interprets", "focus", "test")):
        return "procedure_or_test"
    if any(token in relation_text for token in ("gene", "genetic", "biomarker", "phenotype")):
        return "genetic_association"
    if any(token in relation_text for token in ("adverse", "contraindicated", "causative", "cause")):
        return "safety_or_cause"
    return "associated"


def mrrel_component_for_relation_rows(
    *,
    query_tokens: list[str],
    query_set: set[str],
    positive_specific_tokens: set[str],
    label_tokens: set[str],
    source_group: str,
    hit_category: str,
    relations: list[dict],
    is_research: bool,
) -> tuple[float, set[str], list[dict]]:
    if not relations or not positive_specific_tokens:
        return 0.0, set(), []
    total = 0.0
    matched_tokens: set[str] = set()
    reasons = []
    label_matched = positive_specific_tokens & label_tokens
    hit_role_match = relation_category_matches_query_role(hit_category, query_set)
    per_relation_cap = 0.14 if is_research else 0.055
    total_cap = MRREL_RESEARCH_COMPONENT_CAP if is_research else MRREL_GENERIC_COMPONENT_CAP
    for relation in relations:
        category = str(relation.get("category") or "").strip()
        relation_group = str(relation.get("relation_group") or "").strip() or mrrel_relation_group_from_relation(relation)
        target_group = str(relation.get("target_semantic_group") or "").strip()
        if not target_group and category:
            target_group = RELATION_CATEGORY_SEMANTIC_GROUPS.get(category, "")
        relation_role_match = relation_category_matches_query_role(category, query_set)
        cross_type = bool(category and hit_category and category != hit_category) or bool(
            target_group and source_group and target_group != source_group
        )
        relation_label = str(relation.get("label") or "")
        relation_tokens = set(content_tokens(relation_label))
        relation_matched = positive_specific_tokens & relation_tokens
        if not relation_matched and not (label_matched and relation_role_match):
            continue
        if not (cross_type or relation_matched):
            continue
        if not is_research and not cross_type:
            continue
        component = 0.0
        if relation_matched:
            component += 0.030 * min(len(relation_matched), 3)
            if relation_matched - label_tokens:
                component += 0.025
        if label_matched and relation_role_match:
            component += 0.035
        if hit_role_match and relation_matched:
            component += 0.035
        if cross_type:
            component += 0.030 if is_research else 0.015
        if relation_matched or relation_role_match or hit_role_match:
            if is_research:
                component += MRREL_RELATION_GROUP_WEIGHTS.get(relation_group, MRREL_RELATION_GROUP_WEIGHTS["associated"])
            else:
                component += MRREL_GENERIC_RELATION_GROUP_WEIGHT
        if not cross_type:
            component *= 0.45
        if not is_research:
            component *= 0.60
        component = min(component, per_relation_cap)
        if component <= 0.0:
            continue
        total += component
        matched_tokens.update(relation_matched)
        if label_matched and relation_role_match:
            matched_tokens.update(label_matched)
        reasons.append(
            {
                "cui": relation.get("cui") or "",
                "label": relation_label,
                "category": category,
                "relation_group": relation_group,
                "relation": relation.get("relation") or "",
                "rela": relation.get("rela") or "",
                "source": relation.get("source") or "",
                "rank_source": "research_mrrel" if is_research else "mrrel",
                "cross_semantic_type": cross_type,
                "matched_tokens": sorted(relation_matched),
                "component": round(component, 6),
            }
        )
        if total >= total_cap:
            break
    return min(total, total_cap), matched_tokens, reasons
