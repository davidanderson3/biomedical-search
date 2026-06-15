from __future__ import annotations

import json
import re
from pathlib import Path

from qe_evidence_vectors.search_semantics import semantic_group_from_types, semantic_type_name_set
from qe_evidence_vectors.text import normalized_key


DEFAULT_BUCKET_CONFIG = (
    Path(__file__).resolve().parents[2] / "config" / "search_quality_semantic_buckets.json"
)
CONTRAINDICATION_RELATION_MARKERS = ("contraindicat",)
GENE_BUCKET_DRUG_LIKE_RELAS = {
    "chemotherapy_regimen_has_component",
    "contraindicated_class_of",
    "has_gdc_value",
    "may_be_treated_by",
}
GENE_PROTEIN_SEMANTIC_TYPES = {
    "amino acid sequence",
    "amino acid, peptide, or protein",
    "gene or genome",
    "nucleic acid, nucleoside, or nucleotide",
    "nucleotide sequence",
}
GENE_PROTEIN_ALWAYS_SEMANTIC_TYPES = {
    "amino acid sequence",
    "gene or genome",
    "nucleotide sequence",
}
GENE_PROTEIN_AMBIGUOUS_SEMANTIC_TYPES = {
    "amino acid, peptide, or protein",
    "nucleic acid, nucleoside, or nucleotide",
}
GENE_PROTEIN_LABEL_MARKERS = {
    "allele",
    "antibody",
    "antigen",
    "codon",
    "codons",
    "cytokine",
    "enzyme",
    "exon",
    "exons",
    "factor",
    "factors",
    "gene",
    "genes",
    "globin",
    "hemoglobin",
    "immunoglobulin",
    "intron",
    "introns",
    "interleukin",
    "kinase",
    "protein",
    "proteins",
    "promoter",
    "promoters",
    "receptor",
    "receptors",
}
OBSERVATION_LAB_SEMANTIC_TYPES = {"laboratory procedure"}
MEASUREMENT_OBSERVATION_SEMANTIC_TYPES = {
    "diagnostic procedure",
    "laboratory procedure",
}
MEASUREMENT_OBSERVATION_LABEL_MARKERS = {
    "assay",
    "assays",
    "level",
    "levels",
    "measurement",
    "measurements",
    "panel",
    "panels",
    "ratio",
    "ratios",
    "test",
    "tests",
}
DOSAGE_FORM_SEMANTIC_TYPES = {"biomedical or dental material"}
DOSAGE_FORM_LABEL_MARKERS = ("dosage form",)
CLINICAL_DRUG_FORMULATION_SEMANTIC_TYPES = {"clinical drug"}
CLINICAL_DRUG_FORMULATION_UNITS = {
    "mg",
    "mcg",
    "meq",
    "ml",
    "unt",
    "unit",
    "units",
}
CLINICAL_DRUG_FORMULATION_TERMS = {
    "capsule",
    "injection",
    "solution",
    "tablet",
    "tablets",
}
BROAD_CHEMICAL_FRAGMENT_CLASSES = {
    "chlorides",
    "nitrates",
    "oxides",
    "phosphates",
    "salts",
    "sulfates",
}
BROAD_CHEMICAL_FRAGMENT_MODIFIERS = {"inorganic", "organic"}
NOISY_BROAD_RELATION_SOURCES = {"ccpss"}
NOISY_BROAD_RELATION_RELAS = {
    "clinically_associated_with",
    "clinically associated with",
    "inverse clinically associated with",
    "inverse_clinically_associated_with",
}
NOISY_BROAD_RELATION_BUCKET_KEYS = {"CHEM", "CLIN_ATTR", "GENE", "PROC"}
NOISY_ORGANISM_SOURCE_SEMANTIC_TYPES = {"finding", "sign or symptom"}
ORGANISM_RELATION_SEMANTIC_TYPES = {
    "alga",
    "archaeon",
    "bacterium",
    "fungus",
    "rickettsia or chlamydia",
    "virus",
}
RELATION_OVERLAP_STOPWORDS = {
    "and",
    "for",
    "has",
    "nos",
    "of",
    "the",
    "to",
    "with",
    "procedure",
    "procedures",
    "screen",
    "screening",
    "therapy",
    "treatment",
}
GENERIC_MORTALITY_RELATION_TOKENS = {
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
YES_NO_RELATED_LABELS = {"no", "yes"}
GENERIC_MORTALITY_RELATION_FILLER_TOKENS = {
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


def optional_float(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:
        return None
    return result


def normalize_semantic_result_buckets(payload: object) -> list[dict]:
    if not isinstance(payload, list):
        return []
    buckets = []
    seen_keys = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        label = str(item.get("label") or "").strip()
        code = str(item.get("code") or "").strip()
        if not key or not label or key in seen_keys:
            continue
        semantic_types = [
            str(value).strip().lower()
            for value in item.get("semanticTypes") or item.get("semantic_types") or []
            if str(value).strip()
        ]
        codes = [str(value).strip() for value in item.get("codes") or [] if str(value).strip()]
        min_relevance = optional_float(item.get("minRelevance", item.get("min_relevance", None)))
        buckets.append(
            {
                "key": key,
                "label": label,
                "code": code,
                "codes": codes,
                "semanticTypes": semantic_types,
                **({"minRelevance": min_relevance} if min_relevance is not None else {}),
            }
        )
        seen_keys.add(key)
    return buckets


def load_semantic_result_buckets(path: Path = DEFAULT_BUCKET_CONFIG) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    buckets = normalize_semantic_result_buckets(payload)
    if not buckets:
        raise ValueError(f"No semantic result buckets found in {path}")
    return buckets


SEMANTIC_RESULT_BUCKETS = load_semantic_result_buckets()
FALLBACK_SEMANTIC_RESULT_BUCKET = {
    "key": "OTHER",
    "label": "Other Concepts",
    "code": "OTHER",
    "codes": ["OTHER"],
    "semanticTypes": [],
}
DEFAULT_SEMANTIC_BUCKET_MIN_RELEVANCE = 0.25
SELECTED_SEMANTIC_BUCKET_MIN_RELEVANCE = 0.20
DEFAULT_RELATED_BUCKET_MIN_STRENGTH = 0.58
DEFAULT_RELATED_BUCKET_MIN_CONFIDENCE = 0.50


def normalize_semantic_bucket_filter(values: object) -> tuple[str, ...]:
    if not values:
        return ()
    if isinstance(values, str):
        raw_values = [values]
    else:
        try:
            raw_values = list(values)  # type: ignore[arg-type]
        except TypeError:
            raw_values = [values]

    bucket_lookup: dict[str, list[str]] = {}
    for bucket in SEMANTIC_RESULT_BUCKETS:
        key = str(bucket.get("key") or "").strip()
        label = str(bucket.get("label") or "").strip()
        code = str(bucket.get("code") or "").strip()
        aliases = [key, label, code, *(bucket.get("codes") or [])]
        for alias in aliases:
            normalized = str(alias or "").strip().lower()
            if normalized:
                bucket_lookup.setdefault(normalized, []).append(key)

    selected = []
    selected_set = set()
    unknown = []
    for raw_value in raw_values:
        for part in str(raw_value or "").split(","):
            token = part.strip()
            if not token or token.lower() in {"*", "all", "any"}:
                continue
            keys = bucket_lookup.get(token.lower())
            if not keys:
                unknown.append(token)
                continue
            for key in keys:
                if key not in selected_set:
                    selected.append(key)
                    selected_set.add(key)
    if unknown:
        valid = ", ".join(str(bucket["key"]) for bucket in SEMANTIC_RESULT_BUCKETS)
        raise ValueError(
            f"unknown semantic bucket filter {', '.join(unknown)}; valid values: {valid}"
        )
    return tuple(selected)


def selected_semantic_result_buckets(semantic_bucket_keys: object = None) -> list[dict]:
    keys = set(normalize_semantic_bucket_filter(semantic_bucket_keys))
    if not keys:
        return list(SEMANTIC_RESULT_BUCKETS)
    return [bucket for bucket in SEMANTIC_RESULT_BUCKETS if bucket.get("key") in keys]


def hit_semantic_group(hit: dict) -> str:
    group = str(hit.get("semantic_group") or "").strip()
    if group:
        return group
    return semantic_group_from_types(list(hit.get("semantic_types") or [])) or "OTHER"


def hit_is_gene_protein_bucket_item(hit: dict) -> bool:
    type_names = semantic_type_name_set(list(hit.get("semantic_types") or []))
    if type_names & GENE_PROTEIN_ALWAYS_SEMANTIC_TYPES:
        return True
    if not type_names & GENE_PROTEIN_AMBIGUOUS_SEMANTIC_TYPES:
        return False
    return has_gene_protein_label_marker(
        " ".join(
            [
                str(hit.get("name") or hit.get("label") or ""),
                " ".join(str(label or "") for label in hit.get("labels") or []),
            ]
        )
    )


def has_gene_protein_label_marker(value: object) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", str(value or "").lower()))
    if tokens & GENE_PROTEIN_LABEL_MARKERS:
        return True
    text = str(value or "").lower()
    return any(phrase in text for phrase in ("growth factor", "tumor necrosis factor"))


def hit_is_observation_lab_bucket_item(hit: dict) -> bool:
    return bool(semantic_type_name_set(list(hit.get("semantic_types") or [])) & OBSERVATION_LAB_SEMANTIC_TYPES)


def hit_matches_semantic_bucket(hit: dict, bucket: dict) -> bool:
    if bucket.get("key") == "CHEM" and hit_is_gene_protein_bucket_item(hit):
        return False
    if bucket.get("key") == "CHEM" and hit_is_dosage_form_bucket_noise(hit):
        return False
    if bucket.get("key") == "CHEM" and hit_is_broad_chemical_fragment_bucket_noise(hit):
        return False
    if bucket.get("key") == "CLIN_ATTR" and hit_is_measurement_observation_bucket_item(hit):
        return True
    if bucket.get("key") == "GENE" and hit_has_ambiguous_gene_protein_type(hit) and not hit_is_gene_protein_bucket_item(hit):
        return False
    if bucket.get("key") == "PROC" and hit_is_observation_lab_bucket_item(hit):
        return False
    if bucket.get("key") == "PROC" and hit_is_measurement_observation_bucket_item(hit):
        return False
    expected_types = {str(item).strip().lower() for item in bucket.get("semanticTypes") or [] if item}
    type_match = bool(semantic_type_name_set(list(hit.get("semantic_types") or [])) & expected_types)
    code_match = hit_semantic_group(hit) in {str(item).strip() for item in bucket.get("codes") or []}
    return type_match or code_match


def hit_matches_any_semantic_bucket(
    hit: dict,
    semantic_bucket_keys: object = None,
    *,
    min_relevance: float | None = None,
) -> bool:
    if min_relevance is not None:
        return any(
            hit_matches_semantic_bucket(hit, bucket)
            and hit_clears_semantic_bucket_relevance(hit, min_relevance=min_relevance)
            for bucket in selected_semantic_result_buckets(semantic_bucket_keys)
        )
    return any(
        hit_visible_in_semantic_bucket(hit, bucket)
        for bucket in selected_semantic_result_buckets(semantic_bucket_keys)
    )


def bucket_preferred_order(bucket: dict) -> int:
    key = str(bucket.get("key") or "")
    for index, item in enumerate(SEMANTIC_RESULT_BUCKETS):
        if str(item.get("key") or "") == key:
            return index
    return len(SEMANTIC_RESULT_BUCKETS)


def numeric_value(value: object, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if result != result:
        return default
    return result


def bucket_min_relevance(bucket: dict) -> float:
    return numeric_value(bucket.get("minRelevance"), DEFAULT_SEMANTIC_BUCKET_MIN_RELEVANCE)


def selected_bucket_min_relevance(bucket: dict) -> float:
    return min(bucket_min_relevance(bucket), SELECTED_SEMANTIC_BUCKET_MIN_RELEVANCE)


def hit_relevance_score(hit: dict) -> float:
    breakdown = hit.get("score_breakdown") if isinstance(hit.get("score_breakdown"), dict) else {}
    for value in (
        breakdown.get("rank_score"),
        hit.get("rank_score"),
        hit.get("score"),
    ):
        if value not in (None, ""):
            return numeric_value(value)
    return 0.0


def hit_clears_semantic_bucket_relevance(
    hit: dict,
    *,
    bucket: dict | None = None,
    min_relevance: float | None = None,
) -> bool:
    if min_relevance is None:
        min_relevance = bucket_min_relevance(bucket or {})
    return hit_relevance_score(hit) >= min_relevance


def hit_visible_in_semantic_bucket(hit: dict, bucket: dict) -> bool:
    return hit_matches_semantic_bucket(hit, bucket) and hit_clears_semantic_bucket_relevance(
        hit,
        bucket=bucket,
    )


def relation_strength_confidence(relation: dict) -> tuple[float, float]:
    edge = relation.get("edge") if isinstance(relation.get("edge"), dict) else {}
    strength = numeric_value(
        edge.get("strength")
        if edge
        else relation.get("strength", relation.get("score", relation.get("similarity", 0.0)))
    )
    confidence = numeric_value(edge.get("confidence") if edge else relation.get("confidence", 0.0))
    if confidence <= 0.0 and strength >= 0.75:
        confidence = 0.50
    return strength, confidence


def relation_clears_related_bucket_evidence(
    relation: dict,
    *,
    min_strength: float = DEFAULT_RELATED_BUCKET_MIN_STRENGTH,
    min_confidence: float = DEFAULT_RELATED_BUCKET_MIN_CONFIDENCE,
) -> bool:
    strength, confidence = relation_strength_confidence(relation)
    return strength >= min_strength and confidence >= min_confidence


def relation_matches_semantic_bucket(relation: dict, bucket: dict, group_code: str) -> bool:
    if bucket.get("key") == "CHEM" and relation_is_gene_protein_bucket_item(relation):
        return False
    if bucket.get("key") == "CHEM" and relation_is_dosage_form_bucket_noise(relation):
        return False
    if bucket.get("key") == "CHEM" and relation_is_clinical_drug_formulation_noise(relation):
        return False
    if bucket.get("key") == "CHEM" and relation_is_broad_chemical_fragment_bucket_noise(relation):
        return False
    if bucket.get("key") == "CLIN_ATTR" and relation_is_measurement_observation_bucket_item(relation):
        return True
    if (
        bucket.get("key") == "GENE"
        and relation_has_ambiguous_gene_protein_type(relation)
        and not relation_is_gene_protein_bucket_item(relation)
    ):
        return False
    if bucket.get("key") == "PROC" and relation_is_observation_lab_bucket_item(relation):
        return False
    if bucket.get("key") == "PROC" and relation_is_measurement_observation_bucket_item(relation):
        return False
    expected_types = [str(item).strip().lower() for item in bucket.get("semanticTypes") or [] if item]
    relation_type = str(relation.get("semantic_type") or "").strip().lower()
    type_match = relation_type in expected_types
    code_match = str(group_code or "").strip() in {str(item).strip() for item in bucket.get("codes") or []}
    return type_match or code_match


def relation_is_gene_protein_bucket_item(relation: dict) -> bool:
    category = str(relation.get("category") or "").strip().lower()
    relation_type = str(relation.get("semantic_type") or "").strip().lower()
    if category == "gene_protein" or relation_type in GENE_PROTEIN_ALWAYS_SEMANTIC_TYPES:
        return True
    if relation_type not in GENE_PROTEIN_AMBIGUOUS_SEMANTIC_TYPES:
        return False
    return has_gene_protein_label_marker(relation.get("label") or relation.get("target_label"))


def hit_has_ambiguous_gene_protein_type(hit: dict) -> bool:
    return bool(
        semantic_type_name_set(list(hit.get("semantic_types") or []))
        & GENE_PROTEIN_AMBIGUOUS_SEMANTIC_TYPES
    )


def relation_has_ambiguous_gene_protein_type(relation: dict) -> bool:
    relation_type = str(relation.get("semantic_type") or "").strip().lower()
    return relation_type in GENE_PROTEIN_AMBIGUOUS_SEMANTIC_TYPES


def relation_is_observation_lab_bucket_item(relation: dict) -> bool:
    relation_type = str(relation.get("semantic_type") or "").strip().lower()
    return relation_type in OBSERVATION_LAB_SEMANTIC_TYPES


def has_measurement_observation_label_marker(value: object) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", str(value or "").lower()))
    return bool(tokens & MEASUREMENT_OBSERVATION_LABEL_MARKERS)


def hit_is_measurement_observation_bucket_item(hit: dict) -> bool:
    type_names = semantic_type_name_set(list(hit.get("semantic_types") or []))
    if not type_names & MEASUREMENT_OBSERVATION_SEMANTIC_TYPES:
        return False
    label = " ".join(
        [
            str(hit.get("name") or hit.get("label") or ""),
            " ".join(str(label or "") for label in hit.get("labels") or []),
        ]
    )
    return has_measurement_observation_label_marker(label)


def relation_is_measurement_observation_bucket_item(relation: dict) -> bool:
    relation_type = str(relation.get("semantic_type") or "").strip().lower()
    if relation_type not in MEASUREMENT_OBSERVATION_SEMANTIC_TYPES:
        return False
    label = relation.get("label") or relation.get("target_label") or ""
    return has_measurement_observation_label_marker(label)


def hit_is_dosage_form_bucket_noise(hit: dict) -> bool:
    type_names = semantic_type_name_set(list(hit.get("semantic_types") or []))
    label = " ".join(
        [
            str(hit.get("name") or hit.get("label") or ""),
            " ".join(str(label or "") for label in hit.get("labels") or []),
        ]
    ).lower()
    return bool(type_names & DOSAGE_FORM_SEMANTIC_TYPES) and any(
        marker in label for marker in DOSAGE_FORM_LABEL_MARKERS
    )


def relation_is_dosage_form_bucket_noise(relation: dict) -> bool:
    relation_type = str(relation.get("semantic_type") or "").strip().lower()
    label = str(relation.get("label") or relation.get("target_label") or "").lower()
    return relation_type in DOSAGE_FORM_SEMANTIC_TYPES and any(
        marker in label for marker in DOSAGE_FORM_LABEL_MARKERS
    )


def relation_is_clinical_drug_formulation_noise(relation: dict) -> bool:
    relation_type = str(relation.get("semantic_type") or "").strip().lower()
    if relation_type not in CLINICAL_DRUG_FORMULATION_SEMANTIC_TYPES:
        return False
    label = str(relation.get("label") or relation.get("target_label") or "").lower()
    tokens = set(re.findall(r"[a-z]+", label))
    has_strength = bool(re.search(r"\b\d+(?:\.\d+)?\b", label)) and bool(
        tokens & CLINICAL_DRUG_FORMULATION_UNITS
    )
    has_form = bool(tokens & CLINICAL_DRUG_FORMULATION_TERMS)
    return has_strength or has_form


def is_broad_chemical_fragment_label(value: object) -> bool:
    text = str(value or "").strip().lower()
    if "," not in text:
        return False
    left, right = [part.strip() for part in text.split(",", 1)]
    left_tokens = set(re.findall(r"[a-z]+", left))
    right_tokens = set(re.findall(r"[a-z]+", right))
    return bool(left_tokens & BROAD_CHEMICAL_FRAGMENT_CLASSES) and bool(
        right_tokens & BROAD_CHEMICAL_FRAGMENT_MODIFIERS
    )


def hit_is_broad_chemical_fragment_bucket_noise(hit: dict) -> bool:
    label = hit.get("name") or hit.get("label") or ""
    return is_broad_chemical_fragment_label(label)


def relation_is_broad_chemical_fragment_bucket_noise(relation: dict) -> bool:
    label = relation.get("label") or relation.get("target_label") or ""
    return is_broad_chemical_fragment_label(label)


def relation_text_value(relation: dict) -> str:
    return " ".join(
        str(relation.get(key) or "").lower()
        for key in (
            "rela",
            "relation",
            "relation_group",
            "category",
            "category_label",
            "source",
            "label",
        )
    )


def is_contraindication_relation(relation: dict) -> bool:
    value = relation_text_value(relation)
    return any(marker in value for marker in CONTRAINDICATION_RELATION_MARKERS)


def is_drug_like_gene_bucket_relation(relation: dict) -> bool:
    rela = str(relation.get("rela") or relation.get("relation") or "").strip().lower()
    relation_group = str(relation.get("relation_group") or "").strip().lower()
    if rela in GENE_BUCKET_DRUG_LIKE_RELAS:
        return True
    return relation_group == "treatment" and rela != "has_target"


def relation_overlap_tokens(value: object) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", str(value or "").lower())
        if len(token) > 2 and token not in RELATION_OVERLAP_STOPWORDS
    }


def relation_has_source_label_overlap(relation: dict) -> bool:
    source_tokens = relation_overlap_tokens(relation.get("source_name") or relation.get("source_label"))
    label_tokens = relation_overlap_tokens(relation.get("label") or relation.get("target_label"))
    return bool(source_tokens & label_tokens)


def is_noisy_broad_relation(relation: dict, bucket: dict) -> bool:
    if bucket.get("key") not in NOISY_BROAD_RELATION_BUCKET_KEYS:
        return False
    source = str(relation.get("source") or "").strip().lower()
    if source not in NOISY_BROAD_RELATION_SOURCES:
        return False
    relation_values = {
        str(relation.get("rela") or "").strip().lower(),
        str(relation.get("relation") or "").strip().lower(),
    }
    if not relation_values & NOISY_BROAD_RELATION_RELAS:
        return False
    return not relation_has_source_label_overlap(relation)


def is_noisy_symptom_to_organism_relation(relation: dict, bucket: dict) -> bool:
    if bucket.get("key") != "ORGANISM":
        return False
    category = str(relation.get("category") or "").strip().lower()
    semantic_type = str(relation.get("semantic_type") or "").strip().lower()
    if category != "organism" and semantic_type not in ORGANISM_RELATION_SEMANTIC_TYPES:
        return False
    source = str(relation.get("source") or "").strip().lower()
    if source not in NOISY_BROAD_RELATION_SOURCES:
        return False
    relation_values = {
        str(relation.get("rela") or "").strip().lower(),
        str(relation.get("relation") or "").strip().lower(),
    }
    if not relation_values & NOISY_BROAD_RELATION_RELAS:
        return False
    source_type = str(relation.get("source_semantic_type") or "").strip().lower()
    if source_type not in NOISY_ORGANISM_SOURCE_SEMANTIC_TYPES:
        return False
    return not relation_has_source_label_overlap(relation)


def is_yes_no_related_value(relation: dict) -> bool:
    label = relation.get("label") or relation.get("target_label") or relation.get("name") or ""
    return normalized_key(str(label)) in YES_NO_RELATED_LABELS


def relation_visible_in_semantic_bucket(relation: dict, bucket: dict, group_code: str) -> bool:
    if is_yes_no_related_value(relation):
        return False
    if not relation_matches_semantic_bucket(relation, bucket, group_code):
        return False
    if is_contraindication_relation(relation):
        return False
    if bucket.get("key") == "GENE" and is_drug_like_gene_bucket_relation(relation):
        return False
    if is_noisy_broad_relation(relation, bucket):
        return False
    if is_noisy_symptom_to_organism_relation(relation, bucket):
        return False
    if relation_is_generic_mortality_outcome_noise(relation):
        return False
    return True


def semantic_result_buckets_for_response(
    hits: list[dict],
    semantic_group_views: list[dict],
    *,
    semantic_bucket_keys: object = None,
) -> list[dict]:
    assigned_cuis: set[str] = set()
    threshold_excluded_cuis: set[str] = set()
    buckets: list[dict] = []
    selected_keys = normalize_semantic_bucket_filter(semantic_bucket_keys)
    for bucket in selected_semantic_result_buckets(semantic_bucket_keys):
        matches = []
        min_relevance = (
            selected_bucket_min_relevance(bucket)
            if selected_keys
            else bucket_min_relevance(bucket)
        )
        for rank, hit in enumerate(hits, start=1):
            hit_key = str(hit.get("cui") or hit.get("doc_id") or rank)
            if hit_key in assigned_cuis or hit_key in threshold_excluded_cuis:
                continue
            if not hit_matches_semantic_bucket(hit, bucket):
                continue
            if not hit_clears_semantic_bucket_relevance(hit, min_relevance=min_relevance):
                threshold_excluded_cuis.add(hit_key)
                continue
            matches.append(
                {
                    "kind": "hit",
                    "cui": hit.get("cui") or "",
                    "doc_id": hit.get("doc_id") or "",
                    "rank": rank,
                }
            )
            assigned_cuis.add(hit_key)

        if not matches:
            continue
        best_relevance = max(
            hit_relevance_score(hits[item["rank"] - 1])
            for item in matches
            if 0 < item["rank"] <= len(hits)
        )
        buckets.append(
            {
                **bucket,
                "total": len(matches),
                "relatedTotal": 0,
                "bestRelevance": round(best_relevance, 6),
                "minRelevance": round(min_relevance, 6),
                "items": matches,
            }
        )
    sorted_buckets = sorted(
        buckets,
        key=lambda bucket: (
            -numeric_value(bucket.get("bestRelevance")),
            bucket_preferred_order(bucket),
            str(bucket.get("label") or ""),
        ),
    )
    if selected_keys:
        return sorted_buckets

    unmatched = []
    for rank, hit in enumerate(hits, start=1):
        hit_key = str(hit.get("cui") or hit.get("doc_id") or rank)
        if hit_key in assigned_cuis or hit_key in threshold_excluded_cuis:
            continue
        if not hit_clears_semantic_bucket_relevance(
            hit,
            min_relevance=DEFAULT_SEMANTIC_BUCKET_MIN_RELEVANCE,
        ):
            continue
        assigned_cuis.add(hit_key)
        unmatched.append(
            {
                "kind": "hit",
                "cui": hit.get("cui") or "",
                "doc_id": hit.get("doc_id") or "",
                "rank": rank,
            }
        )
    if unmatched:
        best_relevance = max(
            hit_relevance_score(hits[item["rank"] - 1])
            for item in unmatched
            if 0 < item["rank"] <= len(hits)
        )
        sorted_buckets.append(
            {
                **FALLBACK_SEMANTIC_RESULT_BUCKET,
                "total": len(unmatched),
                "relatedTotal": 0,
                "bestRelevance": round(best_relevance, 6),
                "minRelevance": DEFAULT_SEMANTIC_BUCKET_MIN_RELEVANCE,
                "items": unmatched,
            }
        )
    return sorted_buckets


def related_result_buckets_for_response(
    semantic_group_views: list[dict],
    *,
    semantic_bucket_keys: object = None,
) -> list[dict]:
    assigned_cuis: set[str] = set()
    buckets: list[dict] = []
    for bucket in selected_semantic_result_buckets(semantic_bucket_keys):
        related_items = []
        total = 0
        best_relevance = 0.0
        for view in semantic_group_views or []:
            group_code = str(view.get("semantic_group") or "").strip()
            for relation in view.get("items") or []:
                if not isinstance(relation, dict):
                    continue
                if not relation_visible_in_semantic_bucket(relation, bucket, group_code):
                    continue
                if not relation_clears_related_bucket_evidence(relation):
                    continue
                key = str(relation.get("cui") or relation.get("label") or "")
                if not key or key in assigned_cuis:
                    continue
                assigned_cuis.add(key)
                total += 1
                strength, confidence = relation_strength_confidence(relation)
                best_relevance = max(best_relevance, strength, confidence)
                related_items.append({"kind": "relation", "relation": dict(relation)})
        if not related_items:
            continue
        buckets.append(
            {
                **bucket,
                "total": 0,
                "relatedTotal": total,
                "bestRelevance": round(best_relevance, 6),
                "minStrength": DEFAULT_RELATED_BUCKET_MIN_STRENGTH,
                "minConfidence": DEFAULT_RELATED_BUCKET_MIN_CONFIDENCE,
                "items": related_items,
            }
        )
    return sorted(
        buckets,
        key=lambda bucket: (
            -numeric_value(bucket.get("bestRelevance")),
            bucket_preferred_order(bucket),
            str(bucket.get("label") or ""),
        ),
    )


def relation_is_generic_mortality_outcome_noise(relation: dict) -> bool:
    label = relation.get("label") or relation.get("target_label") or ""
    tokens = set(re.findall(r"[a-z0-9]+", str(label).lower()))
    meaningful_tokens = tokens - GENERIC_MORTALITY_RELATION_FILLER_TOKENS
    return bool(meaningful_tokens & GENERIC_MORTALITY_RELATION_TOKENS) and meaningful_tokens <= (
        GENERIC_MORTALITY_RELATION_TOKENS
    )
