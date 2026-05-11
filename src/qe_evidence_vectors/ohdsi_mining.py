from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from qe_evidence_vectors.code_index import CodeIndex, normalize_sab
from qe_evidence_vectors.universal_relationship import universal_relationship_edge


PATIENT_LEVEL_FIELDS = {
    "person_id",
    "personid",
    "subject_id",
    "subjectid",
    "visit_occurrence_id",
    "visitoccurrenceid",
    "visit_detail_id",
    "visitdetailid",
    "observation_period_id",
    "observationperiodid",
    "provider_id",
    "providerid",
    "care_site_id",
    "caresiteid",
    "note_id",
    "noteid",
}
DRUG_CRITERIA = {"DrugExposure", "DrugEra"}
CLINICAL_CRITERIA = {
    "ConditionOccurrence",
    "ConditionEra",
    "Measurement",
    "Observation",
    "ProcedureOccurrence",
}
CONDITION_CRITERIA = {"ConditionOccurrence", "ConditionEra"}
VOCAB_TO_UMLS_SAB = {
    "ATC": "ATC",
    "HCPCS": "HCPCS",
    "ICD10CM": "ICD10CM",
    "ICD9CM": "ICD9CM",
    "LOINC": "LNC",
    "MedDRA": "MDR",
    "MeSH": "MSH",
    "NDC": "NDC",
    "RxNorm": "RXNORM",
    "RxNorm Extension": "RXNORM",
    "SNOMED": "SNOMEDCT_US",
    "SNOMED Clinical Terms": "SNOMEDCT_US",
}


@dataclass
class ResolvedConcept:
    cui: str
    label: str = ""
    concept_id: str = ""
    vocabulary_id: str = ""
    concept_code: str = ""
    domain_id: str = ""


@dataclass
class AtlasConceptSet:
    id: str
    name: str
    concepts: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AtlasCohortTarget:
    cohort_id: str
    cohort_name: str
    drug_concepts: list[ResolvedConcept] = field(default_factory=list)


@dataclass
class MiningResult:
    edges: list[dict[str, Any]] = field(default_factory=list)
    cohort_targets: dict[str, AtlasCohortTarget] = field(default_factory=dict)
    unresolved: list[dict[str, Any]] = field(default_factory=list)
    skipped_rows: list[dict[str, Any]] = field(default_factory=list)


class OmopConceptResolver:
    def __init__(
        self,
        *,
        omop_cui_map_path: Path | None = None,
        code_index_path: Path | None = None,
    ) -> None:
        self.by_concept_id: dict[str, str] = {}
        self.by_vocab_code: dict[tuple[str, str], str] = {}
        self.code_index = CodeIndex(code_index_path) if code_index_path else None
        if omop_cui_map_path:
            self.load_mapping(omop_cui_map_path)

    def close(self) -> None:
        if self.code_index:
            self.code_index.close()

    def load_mapping(self, path: Path) -> None:
        for row in iter_table_rows(path):
            cui = row_value(row, "cui", "umls_cui", "target_cui")
            if not is_cui(cui):
                continue
            concept_id = row_value(row, "concept_id", "omop_concept_id")
            if concept_id:
                self.by_concept_id[str(concept_id)] = cui.upper()
            vocabulary_id = row_value(row, "vocabulary_id", "vocab", "sab", "source")
            concept_code = row_value(row, "concept_code", "code", "source_code")
            if vocabulary_id and concept_code:
                for key in vocab_code_keys(vocabulary_id, concept_code):
                    self.by_vocab_code[key] = cui.upper()

    def resolve(self, concept: dict[str, Any] | None = None, **values: Any) -> ResolvedConcept | None:
        payload = dict(concept or {})
        payload.update({key: value for key, value in values.items() if value not in (None, "")})
        explicit_cui = concept_value(payload, "cui", "CUI", "umls_cui", "UMLS_CUI")
        label = concept_value(payload, "CONCEPT_NAME", "concept_name", "name", "label")
        concept_id = concept_value(payload, "CONCEPT_ID", "concept_id", "omop_concept_id")
        vocabulary_id = concept_value(payload, "VOCABULARY_ID", "vocabulary_id", "vocab", "sab")
        concept_code = concept_value(payload, "CONCEPT_CODE", "concept_code", "code")
        domain_id = concept_value(payload, "DOMAIN_ID", "domain_id", "domain")

        cui = explicit_cui.upper() if is_cui(explicit_cui) else ""
        if not cui and concept_id:
            cui = self.by_concept_id.get(str(concept_id), "")
        if not cui and vocabulary_id and concept_code:
            for key in vocab_code_keys(vocabulary_id, concept_code):
                cui = self.by_vocab_code.get(key, "")
                if cui:
                    break
        if not cui and self.code_index and vocabulary_id and concept_code:
            sab = omop_vocabulary_to_sab(vocabulary_id)
            rows = self.code_index.lookup_code(str(concept_code), sab=sab, limit=1) if sab else []
            if not rows:
                rows = self.code_index.lookup_code(str(concept_code), limit=1)
            if rows:
                cui = str(rows[0]["cui"]).upper()
                label = label or str(rows[0]["label"])
        if not cui:
            return None
        return ResolvedConcept(
            cui=cui,
            label=str(label or cui),
            concept_id=str(concept_id or ""),
            vocabulary_id=str(vocabulary_id or ""),
            concept_code=str(concept_code or ""),
            domain_id=str(domain_id or ""),
        )


def is_cui(value: Any) -> bool:
    return bool(re.fullmatch(r"C\d{7}|NEW\d{7}", str(value or "").strip().upper()))


def omop_vocabulary_to_sab(value: str) -> str:
    text = str(value or "").strip()
    return normalize_sab(VOCAB_TO_UMLS_SAB.get(text, text))


def vocab_code_keys(vocabulary_id: str, concept_code: str) -> list[tuple[str, str]]:
    vocab = str(vocabulary_id or "").strip()
    code = str(concept_code or "").strip().lower()
    keys = []
    if vocab and code:
        keys.append((vocab.lower(), code))
        keys.append((omop_vocabulary_to_sab(vocab).lower(), code))
    return list(dict.fromkeys(keys))


def concept_value(concept: dict[str, Any], *names: str) -> str:
    if not concept:
        return ""
    lookup = {str(key).lower(): value for key, value in concept.items()}
    for name in names:
        value = lookup.get(name.lower())
        if value not in (None, ""):
            return str(value).strip()
    return ""


def row_value(row: dict[str, Any], *names: str) -> str:
    lookup = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        value = lookup.get(name.lower())
        if value not in (None, ""):
            return str(value).strip()
    return ""


def row_float(row: dict[str, Any], *names: str) -> float | None:
    value = row_value(row, *names)
    if value == "":
        return None
    try:
        result = float(value)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def normalized_probability(value: float | None) -> float | None:
    if value is None:
        return None
    if value > 1.0 and value <= 100.0:
        value = value / 100.0
    return round(max(0.0, min(1.0, value)), 4)


def normalized_effect_strength(estimate: float | None) -> float:
    if estimate is None or estimate <= 0:
        return 0.0
    return round(max(0.0, min(abs(math.log(estimate)) / math.log(4.0), 1.0)), 4)


def confidence_from_ci(
    *,
    lower: float | None,
    upper: float | None,
    sample_size: float | None = None,
    base: float = 0.58,
) -> float:
    confidence = base
    if lower and upper and lower > 0 and upper > lower:
        width = abs(math.log(upper) - math.log(lower))
        confidence += max(0.0, 0.24 - min(width, 2.4) * 0.10)
    if sample_size:
        confidence += min(math.log10(max(sample_size, 1)) * 0.05, 0.20)
    return round(max(0.0, min(confidence, 0.96)), 4)


def ensure_aggregate_row(row: dict[str, Any], *, source: str) -> None:
    present = sorted(
        str(key)
        for key in row
        if re.sub(r"[^a-z0-9]+", "", str(key).lower()) in PATIENT_LEVEL_FIELDS
        or str(key).lower() in PATIENT_LEVEL_FIELDS
    )
    if present:
        raise ValueError(
            f"{source} appears to contain patient-level fields ({', '.join(present)}); "
            "only public/shareable aggregate OHDSI artifacts are supported"
        )


def iter_table_rows(path: Path) -> Iterable[dict[str, Any]]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in {".json", ".jsonl", ".ndjson"}:
        with path.open("r", encoding="utf-8") as handle:
            if suffix == ".json":
                payload = json.load(handle)
                if isinstance(payload, list):
                    for row in payload:
                        if isinstance(row, dict):
                            yield row
                elif isinstance(payload, dict):
                    rows = payload.get("rows") or payload.get("data") or payload.get("results")
                    if isinstance(rows, list):
                        for row in rows:
                            if isinstance(row, dict):
                                yield row
                    else:
                        yield payload
            else:
                for line in handle:
                    if line.strip():
                        payload = json.loads(line)
                        if isinstance(payload, dict):
                            yield payload
        return

    delimiter = "\t" if suffix in {".tsv", ".tab"} else ","
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        for row in reader:
            yield dict(row)


def read_atlas_json(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("cohortDefinition"), dict):
        return dict(payload["cohortDefinition"])
    if isinstance(payload, dict):
        return payload
    raise ValueError(f"{path} is not an ATLAS cohort JSON object")


def concept_sets_from_atlas(payload: dict[str, Any]) -> dict[str, AtlasConceptSet]:
    result = {}
    for item in payload.get("ConceptSets") or payload.get("conceptSets") or []:
        set_id = first_present(item, "id", "Id", "conceptSetId")
        expression = item.get("expression") or item.get("Expression") or {}
        concepts = []
        for concept_item in expression.get("items") or expression.get("Items") or []:
            concept = concept_item.get("concept") or concept_item.get("Concept") or concept_item
            if isinstance(concept, dict):
                concepts.append(concept)
        if set_id:
            result[set_id] = AtlasConceptSet(
                id=set_id,
                name=str(item.get("name") or item.get("Name") or f"concept set {set_id}"),
                concepts=concepts,
            )
    return result


def first_present(payload: dict[str, Any], *names: str) -> str:
    for name in names:
        value = payload.get(name)
        if value not in (None, ""):
            return str(value)
    return ""


def iter_criteria_nodes(payload: Any) -> Iterable[tuple[str, dict[str, Any]]]:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in DRUG_CRITERIA | CLINICAL_CRITERIA and isinstance(value, dict):
                yield key, value
            yield from iter_criteria_nodes(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from iter_criteria_nodes(item)


def criteria_codeset_id(criteria: dict[str, Any]) -> str:
    value = criteria.get("CodesetId")
    if value in (None, ""):
        value = criteria.get("codesetId") or criteria.get("conceptSetId")
    return str(value) if value not in (None, "") else ""


def resolved_concepts_for_set(
    concept_set: AtlasConceptSet,
    resolver: OmopConceptResolver,
    *,
    result: MiningResult,
    source_path: Path,
) -> list[ResolvedConcept]:
    resolved = []
    for concept in concept_set.concepts:
        item = resolver.resolve(concept)
        if item:
            resolved.append(item)
        else:
            result.unresolved.append(
                {
                    "source": "atlas",
                    "path": str(source_path),
                    "concept_set_id": concept_set.id,
                    "concept_set_name": concept_set.name,
                    "concept": concept,
                }
            )
    return resolved


def mine_atlas_cohort(path: Path, resolver: OmopConceptResolver, result: MiningResult) -> None:
    payload = read_atlas_json(path)
    cohort_id = str(payload.get("id") or payload.get("cohortId") or payload.get("CohortId") or Path(path).stem)
    cohort_name = str(payload.get("name") or payload.get("cohortName") or payload.get("Name") or Path(path).stem)
    concept_sets = concept_sets_from_atlas(payload)
    drug_set_ids = {
        codeset_id
        for criterion, criteria in iter_criteria_nodes(payload.get("PrimaryCriteria") or payload)
        if criterion in DRUG_CRITERIA and (codeset_id := criteria_codeset_id(criteria))
    }
    drug_concepts: list[ResolvedConcept] = []
    for set_id in sorted(drug_set_ids):
        concept_set = concept_sets.get(set_id)
        if concept_set:
            drug_concepts.extend(
                resolved_concepts_for_set(concept_set, resolver, result=result, source_path=path)
            )
    if drug_concepts:
        result.cohort_targets[cohort_id] = AtlasCohortTarget(
            cohort_id=cohort_id,
            cohort_name=cohort_name,
            drug_concepts=dedupe_resolved(drug_concepts),
        )

    for rule_index, rule in enumerate(payload.get("InclusionRules") or [], start=1):
        expression = rule.get("expression") or rule.get("Expression") or rule
        for criterion, criteria in iter_criteria_nodes(expression):
            if criterion not in CONDITION_CRITERIA:
                continue
            set_id = criteria_codeset_id(criteria)
            concept_set = concept_sets.get(set_id)
            if not concept_set:
                continue
            objects = resolved_concepts_for_set(concept_set, resolver, result=result, source_path=path)
            for drug in dedupe_resolved(drug_concepts):
                for condition in dedupe_resolved(objects):
                    row = {
                        "strength": 0.72,
                        "rank": rule_index,
                        "support_count": 1,
                    }
                    edge = universal_relationship_edge(
                        subject_cui=drug.cui,
                        object_cui=condition.cui,
                        relation="likely_indication",
                        relation_group="indication",
                        source="atlas_cohort_definition",
                        direction="outgoing",
                        row=row,
                        context={
                            "cohort_id": cohort_id,
                            "cohort_name": cohort_name,
                            "concept_set_id": set_id,
                            "concept_set_name": concept_set.name,
                            "inclusion_rule_id": str(rule.get("id") or rule_index),
                            "inclusion_rule_name": str(rule.get("name") or rule.get("Name") or ""),
                            "source_path": str(path),
                            "subject_omop_concept_id": drug.concept_id,
                            "object_omop_concept_id": condition.concept_id,
                        },
                    )
                    edge["strength_metric"] = "cohort_rule_score"
                    edge["evidence"]["method"] = "curated"
                    add_edge(
                        result,
                        edge,
                        source_class="atlas_cohort_json",
                        subject=drug,
                        object_=condition,
                    )


def dedupe_resolved(items: Iterable[ResolvedConcept]) -> list[ResolvedConcept]:
    seen = set()
    result = []
    for item in items:
        if item.cui in seen:
            continue
        seen.add(item.cui)
        result.append(item)
    return result


def add_edge(
    result: MiningResult,
    edge: dict[str, Any],
    *,
    source_class: str,
    subject: ResolvedConcept | None = None,
    object_: ResolvedConcept | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    row = {
        "source_class": source_class,
        "subject_cui": edge["subject"],
        "subject_label": subject.label if subject else "",
        "object_cui": edge["object"],
        "object_label": object_.label if object_ else "",
        "relationship_type": edge["type"],
        "edge": edge,
    }
    if extra:
        row.update(extra)
    result.edges.append(row)


def subject_concepts_for_row(row: dict[str, Any], resolver: OmopConceptResolver, cohort_targets: dict[str, AtlasCohortTarget]) -> list[ResolvedConcept]:
    explicit = resolver.resolve(
        cui=row_value(row, "drug_cui", "exposure_cui", "target_cui", "subject_cui"),
        concept_id=row_value(row, "drug_concept_id", "exposure_concept_id", "target_concept_id", "subject_concept_id"),
        vocabulary_id=row_value(row, "drug_vocabulary_id", "exposure_vocabulary_id", "target_vocabulary_id", "subject_vocabulary_id"),
        concept_code=row_value(row, "drug_concept_code", "exposure_concept_code", "target_concept_code", "subject_concept_code"),
        concept_name=row_value(row, "drug_name", "exposure_name", "target_name", "subject_name"),
        domain_id="Drug",
    )
    if explicit:
        return [explicit]
    cohort_id = row_value(row, "cohort_id", "cohortid", "target_cohort_id", "targetcohortid")
    target = cohort_targets.get(cohort_id)
    return list(target.drug_concepts) if target else []


def object_concept_for_row(row: dict[str, Any], resolver: OmopConceptResolver, *, prefix: str = "") -> ResolvedConcept | None:
    names = [prefix] if prefix else [""]
    for item_prefix in names:
        concept = resolver.resolve(
            cui=row_value(row, f"{item_prefix}_cui" if item_prefix else "cui", "object_cui", "outcome_cui", "condition_cui", "covariate_cui", "feature_cui"),
            concept_id=row_value(row, f"{item_prefix}_concept_id" if item_prefix else "concept_id", "object_concept_id", "outcome_concept_id", "condition_concept_id", "covariate_concept_id", "feature_concept_id"),
            vocabulary_id=row_value(row, f"{item_prefix}_vocabulary_id" if item_prefix else "vocabulary_id", "object_vocabulary_id", "outcome_vocabulary_id", "condition_vocabulary_id", "covariate_vocabulary_id", "feature_vocabulary_id"),
            concept_code=row_value(row, f"{item_prefix}_concept_code" if item_prefix else "concept_code", "object_concept_code", "outcome_concept_code", "condition_concept_code", "covariate_concept_code", "feature_concept_code"),
            concept_name=row_value(row, f"{item_prefix}_name" if item_prefix else "concept_name", "object_name", "outcome_name", "condition_name", "covariate_name", "feature_name"),
            domain_id=row_value(row, f"{item_prefix}_domain_id" if item_prefix else "domain_id", "object_domain_id", "outcome_domain_id", "condition_domain_id", "covariate_domain_id", "feature_domain_id"),
        )
        if concept:
            return concept
    return None


def mine_cohort_diagnostics(path: Path, resolver: OmopConceptResolver, result: MiningResult) -> None:
    for row_index, row in enumerate(iter_table_rows(path), start=1):
        ensure_aggregate_row(row, source=str(path))
        subjects = subject_concepts_for_row(row, resolver, result.cohort_targets)
        object_ = object_concept_for_row(row, resolver)
        if not subjects or not object_:
            result.unresolved.append({"source": "cohort_diagnostics", "path": str(path), "row": row})
            continue
        prevalence = normalized_probability(
            row_float(row, "prevalence", "proportion", "covariate_value", "mean", "percent")
        )
        cohort_count = row_float(row, "cohort_count", "cohort_size", "subjects", "persons")
        count = row_float(row, "count", "num_persons", "person_count")
        if prevalence is None and cohort_count and count is not None and cohort_count > 0:
            prevalence = normalized_probability(count / cohort_count)
        if prevalence is None:
            result.skipped_rows.append({"source": "cohort_diagnostics", "path": str(path), "reason": "missing prevalence", "row": row})
            continue
        temporal = row_has_temporal_precedence(row)
        relation = "likely_indication" if temporal or row_bool(row, "is_inclusion_criterion", "inclusion_criterion") else "associated_with"
        for subject in subjects:
            edge = universal_relationship_edge(
                subject_cui=subject.cui,
                object_cui=object_.cui,
                relation=relation,
                relation_group="temporal_analysis" if temporal else "cohort_characterization",
                source="ohdsi_cohort_diagnostics",
                direction="outgoing",
                row={
                    "strength": prevalence,
                    "support_count": int(count or 0),
                    "rank": row_index,
                },
                context=cohort_context(row, path=path),
            )
            edge["strength_metric"] = "conditional_prevalence"
            edge["evidence"]["method"] = "temporal_analysis" if temporal else "co_occurrence"
            edge["evidence"]["conditional_prevalence"] = prevalence
            if cohort_count:
                edge["evidence"]["cohort_count"] = int(cohort_count)
            edge["confidence"] = cohort_diagnostics_confidence(
                prevalence=prevalence,
                count=count,
                cohort_count=cohort_count,
                temporal=temporal,
                inclusion=row_bool(row, "is_inclusion_criterion", "inclusion_criterion"),
            )
            add_edge(result, edge, source_class="cohort_diagnostics", subject=subject, object_=object_)
            if temporal:
                temporal_edge = universal_relationship_edge(
                    subject_cui=object_.cui,
                    object_cui=subject.cui,
                    relation="precedes",
                    relation_group="temporal_analysis",
                    source="ohdsi_cohort_diagnostics",
                    direction="outgoing",
                    row={"strength": max(0.4, prevalence), "support_count": int(count or 0), "rank": row_index},
                    context=cohort_context(row, path=path),
                )
                temporal_edge["strength_metric"] = "temporal_precedence_score"
                temporal_edge["evidence"]["method"] = "temporal_analysis"
                temporal_edge["confidence"] = cohort_diagnostics_confidence(
                    prevalence=prevalence,
                    count=count,
                    cohort_count=cohort_count,
                    temporal=True,
                    inclusion=row_bool(row, "is_inclusion_criterion", "inclusion_criterion"),
                )
                add_edge(result, temporal_edge, source_class="cohort_diagnostics_temporal", subject=object_, object_=subject)


def row_bool(row: dict[str, Any], *names: str) -> bool:
    value = row_value(row, *names).lower()
    return value in {"1", "true", "t", "yes", "y"}


def row_has_temporal_precedence(row: dict[str, Any]) -> bool:
    if row_bool(row, "temporal_precedence", "pre_index", "before_index", "prior_to_index"):
        return True
    text = " ".join(
        row_value(row, "time_window", "window", "temporal_window", "period", "covariate_name").lower().split()
    )
    return any(marker in text for marker in ("pre index", "pre-index", "prior", "before index", "baseline"))


def cohort_diagnostics_confidence(
    *,
    prevalence: float,
    count: float | None,
    cohort_count: float | None,
    temporal: bool,
    inclusion: bool,
) -> float:
    confidence = 0.48
    if temporal:
        confidence += 0.12
    if inclusion:
        confidence += 0.10
    confidence += min(max(prevalence, 0.0) * 0.16, 0.16)
    support = count or cohort_count
    if support:
        confidence += min(math.log10(max(support, 1.0)) * 0.045, 0.18)
    return round(max(0.0, min(confidence, 0.92)), 4)


def cohort_context(row: dict[str, Any], *, path: Path) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "cohort_id": row_value(row, "cohort_id", "cohortid", "target_cohort_id", "targetcohortid"),
            "cohort_name": row_value(row, "cohort_name", "cohortname", "target_cohort_name", "targetcohortname"),
            "database_id": row_value(row, "database_id", "database", "database_name"),
            "analysis_id": row_value(row, "analysis_id", "analysisid"),
            "time_period": row_value(row, "time_window", "window", "temporal_window", "period"),
            "source_path": str(path),
        }.items()
        if value
    }


def mine_estimation_results(path: Path, resolver: OmopConceptResolver, result: MiningResult) -> None:
    for row_index, row in enumerate(iter_table_rows(path), start=1):
        ensure_aggregate_row(row, source=str(path))
        subject = resolver.resolve(
            cui=row_value(row, "exposure_cui", "target_cui", "subject_cui", "drug_cui"),
            concept_id=row_value(row, "exposure_concept_id", "target_concept_id", "subject_concept_id", "drug_concept_id"),
            vocabulary_id=row_value(row, "exposure_vocabulary_id", "target_vocabulary_id", "subject_vocabulary_id", "drug_vocabulary_id"),
            concept_code=row_value(row, "exposure_concept_code", "target_concept_code", "subject_concept_code", "drug_concept_code"),
            concept_name=row_value(row, "exposure_name", "target_name", "subject_name", "drug_name"),
            domain_id="Drug",
        )
        object_ = object_concept_for_row(row, resolver, prefix="outcome")
        if not subject or not object_:
            result.unresolved.append({"source": "estimation_results", "path": str(path), "row": row})
            continue
        estimate, metric = effect_estimate(row)
        if estimate is None:
            result.skipped_rows.append({"source": "estimation_results", "path": str(path), "reason": "missing effect estimate", "row": row})
            continue
        lower = row_float(row, "lower_95", "lower95", "ci_lower", "lower_ci", "lower")
        upper = row_float(row, "upper_95", "upper95", "ci_upper", "upper_ci", "upper")
        relation = "increases_risk_of" if estimate > 1.05 else "decreases_risk_of" if estimate < 0.95 else "affects_risk_of"
        strength = normalized_effect_strength(estimate)
        edge = universal_relationship_edge(
            subject_cui=subject.cui,
            object_cui=object_.cui,
            relation=relation,
            relation_group="effect_estimate",
            source="ohdsi_population_level_estimation",
            direction="outgoing",
            row={"strength": strength, "rank": row_index},
            context=estimation_context(row, path=path),
        )
        edge["strength_metric"] = f"{metric}_normalized"
        edge["evidence"]["method"] = "temporal_analysis"
        edge["evidence"]["effect_estimate"] = {
            "measure": metric,
            "estimate": estimate,
            "lower_95": lower,
            "upper_95": upper,
        }
        edge["evidence"]["quantitative"] = dict(edge["evidence"]["effect_estimate"])
        edge["confidence"] = confidence_from_ci(
            lower=lower,
            upper=upper,
            sample_size=row_float(row, "target_count", "treated_count", "sample_size", "n"),
            base=0.64,
        )
        add_edge(result, edge, source_class="estimation_results", subject=subject, object_=object_)


def effect_estimate(row: dict[str, Any]) -> tuple[float | None, str]:
    for metric, names in (
        ("hazard_ratio", ("hazard_ratio", "hazardratio", "hr")),
        ("risk_ratio", ("risk_ratio", "riskratio", "rr")),
        ("odds_ratio", ("odds_ratio", "oddsratio", "or")),
    ):
        value = row_float(row, *names)
        if value is not None:
            return value, metric
    return None, "effect_estimate"


def estimation_context(row: dict[str, Any], *, path: Path) -> dict[str, Any]:
    context = cohort_context(row, path=path)
    for key, names in {
        "target_cohort_id": ("target_cohort_id", "targetcohortid"),
        "comparator_cohort_id": ("comparator_cohort_id", "comparatorcohortid"),
        "outcome_cohort_id": ("outcome_cohort_id", "outcomecohortid"),
        "time_at_risk": ("time_at_risk", "timeatrisk"),
        "adjustment_method": ("adjustment_method", "method", "analysis_method"),
        "study_id": ("study_id", "package_id", "publication_id"),
    }.items():
        value = row_value(row, *names)
        if value:
            context[key] = value
    return context


def mine_plp_outputs(path: Path, resolver: OmopConceptResolver, result: MiningResult) -> None:
    for row_index, row in enumerate(iter_table_rows(path), start=1):
        ensure_aggregate_row(row, source=str(path))
        feature = object_concept_for_row(row, resolver, prefix="feature")
        target = resolver.resolve(
            cui=row_value(row, "target_cui", "outcome_cui", "drug_cui", "object_cui"),
            concept_id=row_value(row, "target_concept_id", "outcome_concept_id", "drug_concept_id", "object_concept_id"),
            vocabulary_id=row_value(row, "target_vocabulary_id", "outcome_vocabulary_id", "drug_vocabulary_id", "object_vocabulary_id"),
            concept_code=row_value(row, "target_concept_code", "outcome_concept_code", "drug_concept_code", "object_concept_code"),
            concept_name=row_value(row, "target_name", "outcome_name", "drug_name", "object_name"),
        )
        if not feature or not target:
            result.unresolved.append({"source": "plp_outputs", "path": str(path), "row": row})
            continue
        importance = row_float(row, "importance", "feature_importance", "standardized_coefficient", "coefficient", "auc_delta")
        if importance is None:
            result.skipped_rows.append({"source": "plp_outputs", "path": str(path), "reason": "missing feature importance", "row": row})
            continue
        strength = normalized_probability(abs(importance)) or min(abs(importance), 1.0)
        edge = universal_relationship_edge(
            subject_cui=feature.cui,
            object_cui=target.cui,
            relation="predicts",
            relation_group="prediction_model",
            source="ohdsi_patient_level_prediction",
            direction="outgoing",
            row={"strength": strength, "rank": row_index},
            context={**estimation_context(row, path=path), "noncausal": True},
        )
        edge["strength_metric"] = row_value(row, "importance_metric", "metric") or "feature_importance"
        edge["evidence"]["method"] = "prediction_model"
        edge["evidence"]["feature_importance"] = importance
        edge["evidence"]["quantitative"] = {
            key: value
            for key, value in {
                "feature_importance": importance,
                "auc": row_float(row, "auc", "validation_auc", "test_auc"),
                "calibration": row_float(row, "calibration", "calibration_error"),
            }.items()
            if value is not None
        }
        edge["confidence"] = plp_confidence(row)
        add_edge(result, edge, source_class="plp_outputs", subject=feature, object_=target)


def plp_confidence(row: dict[str, Any]) -> float:
    confidence = 0.44
    auc = row_float(row, "auc", "validation_auc", "test_auc")
    if auc is not None:
        confidence += max(0.0, min((auc - 0.5) * 0.8, 0.24))
    if row_bool(row, "external_validation", "has_external_validation"):
        confidence += 0.12
    sample_size = row_float(row, "sample_size", "n", "population_size")
    if sample_size:
        confidence += min(math.log10(max(sample_size, 1)) * 0.04, 0.14)
    return round(max(0.0, min(confidence, 0.9)), 4)


def mine_literature_studies(path: Path, resolver: OmopConceptResolver, result: MiningResult) -> None:
    for row_index, row in enumerate(iter_table_rows(path), start=1):
        ensure_aggregate_row(row, source=str(path))
        relationship = row_value(row, "type", "relationship_type", "relation") or "associated_with"
        subject = resolver.resolve(
            cui=row_value(row, "subject_cui", "exposure_cui", "drug_cui", "target_cui"),
            concept_id=row_value(row, "subject_concept_id", "exposure_concept_id", "drug_concept_id", "target_concept_id"),
            vocabulary_id=row_value(row, "subject_vocabulary_id", "exposure_vocabulary_id", "drug_vocabulary_id", "target_vocabulary_id"),
            concept_code=row_value(row, "subject_concept_code", "exposure_concept_code", "drug_concept_code", "target_concept_code"),
            concept_name=row_value(row, "subject_name", "exposure_name", "drug_name", "target_name"),
        )
        object_ = resolver.resolve(
            cui=row_value(row, "object_cui", "outcome_cui", "condition_cui"),
            concept_id=row_value(row, "object_concept_id", "outcome_concept_id", "condition_concept_id"),
            vocabulary_id=row_value(row, "object_vocabulary_id", "outcome_vocabulary_id", "condition_vocabulary_id"),
            concept_code=row_value(row, "object_concept_code", "outcome_concept_code", "condition_concept_code"),
            concept_name=row_value(row, "object_name", "outcome_name", "condition_name"),
        )
        if not subject or not object_:
            result.unresolved.append({"source": "literature_ohdsi", "path": str(path), "row": row})
            continue
        estimate, metric = effect_estimate(row)
        strength = normalized_effect_strength(estimate) if estimate is not None else (normalized_probability(row_float(row, "strength", "score")) or 0.62)
        edge = universal_relationship_edge(
            subject_cui=subject.cui,
            object_cui=object_.cui,
            relation=relationship,
            relation_group=row_value(row, "relation_group") or "literature_backed_ohdsi",
            source=row_value(row, "source", "study_id", "publication_id") or "literature_backed_ohdsi_study",
            direction="outgoing",
            row={"strength": strength, "rank": row_index},
            context=estimation_context(row, path=path),
        )
        edge["strength_metric"] = f"{metric}_normalized" if estimate is not None else "literature_ohdsi_score"
        edge["evidence"]["method"] = "literature_mined"
        if estimate is not None:
            lower = row_float(row, "lower_95", "lower95", "ci_lower", "lower_ci", "lower")
            upper = row_float(row, "upper_95", "upper95", "ci_upper", "upper_ci", "upper")
            edge["evidence"]["effect_estimate"] = {
                "measure": metric,
                "estimate": estimate,
                "lower_95": lower,
                "upper_95": upper,
            }
            edge["evidence"]["quantitative"] = dict(edge["evidence"]["effect_estimate"])
            edge["confidence"] = confidence_from_ci(
                lower=lower,
                upper=upper,
                sample_size=row_float(row, "target_count", "treated_count", "sample_size", "n"),
                base=0.62,
            )
        add_edge(result, edge, source_class="literature_backed_ohdsi", subject=subject, object_=object_)


def mine_public_ohdsi_artifacts(
    *,
    atlas_paths: list[Path] | None = None,
    cohort_diagnostics_paths: list[Path] | None = None,
    estimation_result_paths: list[Path] | None = None,
    plp_output_paths: list[Path] | None = None,
    literature_study_paths: list[Path] | None = None,
    omop_cui_map_path: Path | None = None,
    code_index_path: Path | None = None,
) -> MiningResult:
    resolver = OmopConceptResolver(
        omop_cui_map_path=omop_cui_map_path,
        code_index_path=code_index_path,
    )
    result = MiningResult()
    try:
        for path in atlas_paths or []:
            mine_atlas_cohort(Path(path), resolver, result)
        for path in cohort_diagnostics_paths or []:
            mine_cohort_diagnostics(Path(path), resolver, result)
        for path in estimation_result_paths or []:
            mine_estimation_results(Path(path), resolver, result)
        for path in plp_output_paths or []:
            mine_plp_outputs(Path(path), resolver, result)
        for path in literature_study_paths or []:
            mine_literature_studies(Path(path), resolver, result)
    finally:
        resolver.close()
    result.edges = dedupe_edges(result.edges)
    return result


def dedupe_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best = {}
    for row in edges:
        edge = row.get("edge") or {}
        key = (
            edge.get("subject"),
            edge.get("object"),
            edge.get("type"),
            row.get("source_class"),
            json.dumps(edge.get("context") or {}, sort_keys=True),
        )
        current = best.get(key)
        if current is None or float(edge.get("confidence") or 0) > float((current.get("edge") or {}).get("confidence") or 0):
            best[key] = row
    return list(best.values())


def mining_summary(result: MiningResult) -> dict[str, Any]:
    by_source_class: dict[str, int] = {}
    by_relationship_type: dict[str, int] = {}
    for row in result.edges:
        by_source_class[str(row.get("source_class") or "")] = by_source_class.get(str(row.get("source_class") or ""), 0) + 1
        by_relationship_type[str(row.get("relationship_type") or "")] = by_relationship_type.get(str(row.get("relationship_type") or ""), 0) + 1
    return {
        "edges": len(result.edges),
        "cohort_targets": len(result.cohort_targets),
        "unresolved": len(result.unresolved),
        "skipped_rows": len(result.skipped_rows),
        "by_source_class": dict(sorted(by_source_class.items())),
        "by_relationship_type": dict(sorted(by_relationship_type.items())),
    }


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            count += 1
    return count


def write_edges_jsonl(path: Path, edges: list[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in edges:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")


def mining_summary(result: MiningResult) -> dict[str, Any]:
    counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    for row in result.edges:
        counts[str(row.get("source_class") or "unknown")] = counts.get(str(row.get("source_class") or "unknown"), 0) + 1
        edge_type = str((row.get("edge") or {}).get("type") or "unknown")
        type_counts[edge_type] = type_counts.get(edge_type, 0) + 1
    return {
        "edges": len(result.edges),
        "source_class_counts": dict(sorted(counts.items())),
        "relationship_type_counts": dict(sorted(type_counts.items())),
        "cohort_targets": len(result.cohort_targets),
        "unresolved": len(result.unresolved),
        "skipped_rows": len(result.skipped_rows),
    }
