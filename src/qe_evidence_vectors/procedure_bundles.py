from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

from .extension_concepts import stable_extension_id
from .schema import write_jsonl
from .text import normalized_key


PUBLIC_ALLOWED_SOURCES = {
    "HCPCS",
    "HPO",
    "ICD10PCS",
    "LNC",
    "LOINC",
    "MSH",
    "MESH",
    "NCI",
    "NCIT",
}
SNOMED_SOURCES = {"SNOMED", "SNOMEDCT", "SNOMEDCT_US", "SNOMED_CT"}
CPT_SOURCES = {"CPT", "CPT4", "AMA_CPT"}
CPT_DESCRIPTOR_KEYS = {
    "cptdescriptor",
    "descriptor",
    "description",
    "label",
    "longdescriptor",
    "name",
    "shortdescriptor",
    "term",
}

ACTION_PATTERNS = (
    ("biopsy", ("biopsy", "biopsied")),
    ("placement", ("placement", "placed", "insertion", "inserted")),
    ("drainage", ("incision and drainage", "drainage", "drained")),
    ("imaging", ("ultrasound", "ct", "computed tomography", "mri", "magnetic resonance", "radiograph", "x-ray")),
    ("catheterization", ("catheterization", "catheterisation")),
    ("endoscopy", ("endoscopy", "endoscopic", "colonoscopy", "egd", "esophagogastroduodenoscopy")),
    ("repair", ("repair", "reconstruction")),
    ("replacement", ("replacement", "arthroplasty")),
    ("measurement", ("measurement", "monitoring")),
    ("injection", ("injection", "infusion")),
)
APPROACH_PATTERNS = (
    ("endoscopic", ("endoscopic", "endoscopy", "colonoscopy", "egd")),
    ("percutaneous", ("percutaneous",)),
    ("laparoscopic", ("laparoscopic",)),
    ("open", ("open",)),
    ("transcatheter", ("transcatheter",)),
)
MODALITY_PATTERNS = (
    ("ultrasound", ("ultrasound", "ultrasonography", "sonography", "ultrasound-guided", "ultrasound guided")),
    ("CT", ("ct", "computed tomography", "ct-guided", "ct guided")),
    ("MRI", ("mri", "magnetic resonance")),
    ("fluoroscopy", ("fluoroscopy", "fluoroscopic")),
    ("echocardiography", ("echocardiography", "echocardiogram", "echo")),
)
ANATOMY_PATTERNS = (
    ("central venous", ("central venous", "central vein")),
    ("stomach", ("gastric", "stomach")),
    ("coronary artery", ("coronary", "coronary artery")),
    ("heart", ("cardiac", "heart")),
    ("skin", ("skin", "cutaneous")),
    ("colon", ("colon", "colonic")),
    ("breast", ("breast",)),
    ("kidney", ("renal", "kidney")),
)
DEVICE_PATTERNS = (
    ("catheter", ("catheter", "line")),
    ("stent", ("stent",)),
    ("graft", ("graft",)),
    ("contrast", ("contrast",)),
)
SPECIMEN_PATTERNS = (
    ("tissue", ("biopsy", "tissue")),
    ("fluid", ("fluid", "aspiration")),
)


@dataclass(frozen=True)
class ProcedureAnchor:
    cui: str
    label: str = ""
    source: str = ""
    code: str = ""


@dataclass(frozen=True)
class ProcedureBundle:
    concept_id: str
    preferred_label: str
    aliases: list[str] = field(default_factory=list)
    semantic_type: str = "Therapeutic or Preventive Procedure"
    attributes: dict[str, Any] = field(default_factory=dict)
    open_anchors: list[ProcedureAnchor] = field(default_factory=list)
    broader_anchors: list[ProcedureAnchor] = field(default_factory=list)
    target_anatomy: list[ProcedureAnchor] = field(default_factory=list)
    modality_anchors: list[ProcedureAnchor] = field(default_factory=list)
    device_anchors: list[ProcedureAnchor] = field(default_factory=list)
    specimen_anchors: list[ProcedureAnchor] = field(default_factory=list)
    related_anchors: list[ProcedureAnchor] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    status: str = "candidate"
    metadata: dict[str, Any] = field(default_factory=dict)


def iter_rows(path: str | Path) -> Iterator[dict[str, Any]]:
    path = Path(path).expanduser()
    suffix = path.suffix.lower()
    if suffix in {".jsonl", ".ndjson"}:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError(f"{path}:{line_number}: expected JSON object")
                yield payload
        return
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload if isinstance(payload, list) else payload.get("rows") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ValueError(f"{path}: expected a JSON list or object with rows")
        for row in rows:
            if isinstance(row, dict):
                yield row
        return
    delimiter = "\t" if suffix in {".tsv", ".tab"} else ","
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter=delimiter):
            yield dict(row)


def source_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "", str(value or "")).upper()


def descriptor_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def list_value(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[|;]", value) if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def anchor_list(value: Any, *, field_name: str, allow_snomed: bool) -> list[ProcedureAnchor]:
    if value in (None, "", []):
        return []
    items = value if isinstance(value, list) else [value]
    anchors: list[ProcedureAnchor] = []
    for item in items:
        if isinstance(item, str):
            payload = {"cui": item}
        elif isinstance(item, dict):
            payload = item
        else:
            raise ValueError(f"{field_name} anchors must be strings or objects")
        validate_public_source(payload, field_name=field_name, allow_snomed=allow_snomed)
        cui = str(payload.get("cui") or payload.get("CUI") or "").strip().upper()
        if not cui:
            continue
        anchors.append(
            ProcedureAnchor(
                cui=cui,
                label=str(payload.get("label") or payload.get("name") or "").strip(),
                source=str(payload.get("source") or payload.get("sab") or payload.get("vocabulary") or "").strip(),
                code=str(payload.get("code") or payload.get("source_code") or "").strip(),
            )
        )
    return anchors


def validate_public_source(payload: dict[str, Any], *, field_name: str, allow_snomed: bool) -> None:
    system = source_key(
        str(payload.get("source") or payload.get("sab") or payload.get("vocabulary") or payload.get("code_system") or "")
    )
    if system in CPT_SOURCES:
        raise ValueError(f"{field_name} contains CPT content; public procedure bundles cannot ship CPT")
    if system in SNOMED_SOURCES and not allow_snomed:
        raise ValueError(f"{field_name} contains SNOMED CT content; pass allow_snomed for deployments that permit it")
    for key in payload:
        if descriptor_key(key) in CPT_DESCRIPTOR_KEYS and system in CPT_SOURCES:
            raise ValueError(f"{field_name} contains CPT descriptor field {key!r}")


def validate_no_public_cpt(payload: Any, *, path: str = "payload", allow_snomed: bool = True) -> None:
    if isinstance(payload, dict):
        validate_public_source(payload, field_name=path, allow_snomed=allow_snomed)
        for key, value in payload.items():
            if source_key(key) in {"CPT", "CPT4", "CPTCODE", "CPT_CODE"}:
                raise ValueError(f"{path}.{key} contains CPT content; use the private adapter instead")
            validate_no_public_cpt(value, path=f"{path}.{key}", allow_snomed=allow_snomed)
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            validate_no_public_cpt(item, path=f"{path}[{index}]", allow_snomed=allow_snomed)


def phrase_has(text: str, terms: Iterable[str]) -> bool:
    return any(term in text for term in terms)


def first_pattern(text: str, patterns: Iterable[tuple[str, Iterable[str]]]) -> str:
    for value, terms in patterns:
        if phrase_has(text, terms):
            return value
    return ""


def all_patterns(text: str, patterns: Iterable[tuple[str, Iterable[str]]]) -> list[str]:
    return [value for value, terms in patterns if phrase_has(text, terms)]


def infer_attributes(label: str, explicit: dict[str, Any] | None = None) -> dict[str, Any]:
    text = normalized_key(label).replace("-", " ")
    explicit = dict(explicit or {})
    attributes = {
        "action": explicit.get("action") or first_pattern(text, ACTION_PATTERNS),
        "anatomy_route": explicit.get("anatomy_route") or explicit.get("target_anatomy") or first_pattern(text, ANATOMY_PATTERNS),
        "approach": explicit.get("approach") or first_pattern(text, APPROACH_PATTERNS),
        "modality": explicit.get("modality") or first_pattern(text, MODALITY_PATTERNS),
        "intent": explicit.get("intent") or infer_intent(text),
        "device": explicit.get("device") or first_pattern(text, DEVICE_PATTERNS),
        "specimen": explicit.get("specimen") or first_pattern(text, SPECIMEN_PATTERNS),
        "qualifiers": explicit.get("qualifiers") or all_patterns(text, (("guided", ("guided",)), ("right", ("right",)), ("left", ("left",)))),
    }
    return {key: value for key, value in attributes.items() if value not in (None, "", [])}


def infer_intent(text: str) -> str:
    if phrase_has(text, ("screening", "surveillance")):
        return "screening/surveillance"
    if phrase_has(text, ("catheter", "line", "placement", "insertion")):
        return "therapeutic/supportive"
    if phrase_has(text, ("biopsy", "endoscopy", "imaging", "ct", "mri", "ultrasound")):
        return "diagnostic"
    return "therapeutic"


def infer_semantic_type(attributes: dict[str, Any]) -> str:
    action = str(attributes.get("action") or "").lower()
    intent = str(attributes.get("intent") or "").lower()
    if action in {"placement", "injection", "repair", "replacement", "drainage"}:
        return "Therapeutic or Preventive Procedure"
    if action in {"biopsy", "endoscopy", "imaging", "measurement"} or "diagnostic" in intent:
        return "Diagnostic Procedure"
    return "Therapeutic or Preventive Procedure"


def definition_for(label: str, attributes: dict[str, Any]) -> str:
    parts = [f"{key}: {value}" for key, value in attributes.items() if value]
    if not parts:
        return f"Procedure bundle for {label}."
    return f"Procedure bundle for {label} with " + ", ".join(parts) + "."


def generated_evidence(label: str, attributes: dict[str, Any]) -> dict[str, Any]:
    return {
        "text": definition_for(label, attributes),
        "source": "public_procedure_bundle",
        "evidence_type": "procedure_bundle",
        "weight": 1.0,
    }


def bundle_from_payload(payload: dict[str, Any], *, allow_snomed: bool = True) -> ProcedureBundle:
    validate_no_public_cpt(payload, allow_snomed=allow_snomed)
    label = str(payload.get("preferred_label") or payload.get("label") or payload.get("procedure") or "").strip()
    if not label:
        raise ValueError("procedure bundle is missing preferred_label")
    attributes = infer_attributes(label, payload.get("attributes") if isinstance(payload.get("attributes"), dict) else {})
    semantic_type = str(payload.get("semantic_type") or infer_semantic_type(attributes)).strip()
    concept_id = str(
        payload.get("concept_id")
        or payload.get("provisional_id")
        or stable_extension_id(label, semantic_type=semantic_type)
    ).strip()
    if re.fullmatch(r"C\d{7}", concept_id.upper()):
        raise ValueError("procedure bundle concept_id must be local NEW#######, not an official CUI")
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), list) else []
    if not evidence:
        evidence = [generated_evidence(label, attributes)]
    return ProcedureBundle(
        concept_id=concept_id,
        preferred_label=label,
        aliases=list_value(payload.get("aliases") or payload.get("synonyms")),
        semantic_type=semantic_type,
        attributes=attributes,
        open_anchors=anchor_list(payload.get("open_anchors") or payload.get("anchors"), field_name="open_anchors", allow_snomed=allow_snomed),
        broader_anchors=anchor_list(payload.get("broader") or payload.get("broader_anchors"), field_name="broader_anchors", allow_snomed=allow_snomed),
        target_anatomy=anchor_list(payload.get("target_anatomy"), field_name="target_anatomy", allow_snomed=allow_snomed),
        modality_anchors=anchor_list(payload.get("modality_anchors"), field_name="modality_anchors", allow_snomed=allow_snomed),
        device_anchors=anchor_list(payload.get("device_anchors"), field_name="device_anchors", allow_snomed=allow_snomed),
        specimen_anchors=anchor_list(payload.get("specimen_anchors"), field_name="specimen_anchors", allow_snomed=allow_snomed),
        related_anchors=anchor_list(payload.get("related") or payload.get("related_anchors"), field_name="related_anchors", allow_snomed=allow_snomed),
        evidence=evidence,
        status=str(payload.get("status") or "candidate").strip() or "candidate",
        metadata=dict(payload.get("metadata") or {}),
    )


def anchor_payload(anchor: ProcedureAnchor) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "cui": anchor.cui,
            "label": anchor.label,
            "source": anchor.source,
            "code": anchor.code,
        }.items()
        if value
    }


def concept_payload(bundle: ProcedureBundle) -> dict[str, Any]:
    related = [
        anchor.cui
        for anchor in [
            *bundle.target_anatomy,
            *bundle.modality_anchors,
            *bundle.device_anchors,
            *bundle.specimen_anchors,
            *bundle.related_anchors,
        ]
    ]
    metadata = {
        "concept_origin": "procedure_bundle",
        "procedure_bundle": True,
        "procedure_attributes": bundle.attributes,
        "open_anchors": [anchor_payload(anchor) for anchor in bundle.open_anchors],
        "broader_anchors": [anchor_payload(anchor) for anchor in bundle.broader_anchors],
        "target_anatomy": [anchor_payload(anchor) for anchor in bundle.target_anatomy],
        "modality_anchors": [anchor_payload(anchor) for anchor in bundle.modality_anchors],
        "device_anchors": [anchor_payload(anchor) for anchor in bundle.device_anchors],
        "specimen_anchors": [anchor_payload(anchor) for anchor in bundle.specimen_anchors],
        "source_policy": "public_open_or_permitted_sources_no_cpt",
        **bundle.metadata,
    }
    return {
        "concept_id": bundle.concept_id,
        "preferred_label": bundle.preferred_label,
        "aliases": bundle.aliases,
        "semantic_type": bundle.semantic_type,
        "definition": definition_for(bundle.preferred_label, bundle.attributes),
        "status": bundle.status,
        "broader_cuis": [anchor.cui for anchor in bundle.broader_anchors],
        "related_cuis": list(dict.fromkeys(related)),
        "close_match_cuis": [anchor.cui for anchor in bundle.open_anchors],
        "evidence": bundle.evidence,
        "metadata": metadata,
    }


def relation_row(
    *,
    source_cui: str,
    source_label: str,
    target: ProcedureAnchor,
    relation: str,
    rela: str,
    direction: str = "outgoing",
    rank: int = 1,
    assertion: str,
    rationale: str,
) -> dict[str, Any]:
    return {
        "source_cui": source_cui,
        "source_label": source_label,
        "target_cui": target.cui,
        "target_label": target.label or target.cui,
        "relation": relation,
        "rela": rela,
        "sab": "MTH",
        "direction": direction,
        "rank": rank,
        "assertion": assertion,
        "rationale": rationale,
    }


def relation_rows(bundle: ProcedureBundle) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rank, anchor in enumerate(bundle.broader_anchors, start=1):
        rows.append(
            relation_row(
                source_cui=bundle.concept_id,
                source_label=bundle.preferred_label,
                target=anchor,
                relation="RB",
                rela="",
                rank=rank,
                assertion="procedure_bundle_has_broader_target",
                rationale=f"Procedure bundle is narrower than {anchor.label or anchor.cui}.",
            )
        )
        rows.append(
            {
                **relation_row(
                    source_cui=anchor.cui,
                    source_label=anchor.label or anchor.cui,
                    target=ProcedureAnchor(bundle.concept_id, bundle.preferred_label),
                    relation="RN",
                    rela="",
                    direction="inverse",
                    rank=rank,
                    assertion="target_has_narrower_procedure_bundle",
                    rationale=f"{anchor.label or anchor.cui} has local procedure bundle {bundle.concept_id} as a narrower concept.",
                )
            }
        )
    relation_groups = [
        ("target_anatomy", bundle.target_anatomy, "target_anatomy"),
        ("uses_modality", bundle.modality_anchors, "modality"),
        ("uses_device", bundle.device_anchors, "device"),
        ("uses_specimen", bundle.specimen_anchors, "specimen"),
        ("related_open_anchor", bundle.related_anchors, "related"),
        ("close_match", bundle.open_anchors, "open_anchor"),
    ]
    offset = len(bundle.broader_anchors) + 1
    for rela, anchors, assertion_suffix in relation_groups:
        for index, anchor in enumerate(anchors, start=offset):
            rows.append(
                relation_row(
                    source_cui=bundle.concept_id,
                    source_label=bundle.preferred_label,
                    target=anchor,
                    relation="RO" if rela != "close_match" else "RQ",
                    rela=rela,
                    rank=index,
                    assertion=f"procedure_bundle_{assertion_suffix}",
                    rationale=f"Procedure bundle attribute {rela} resolves to {anchor.label or anchor.cui}.",
                )
            )
    return rows


def build_procedure_bundle_artifacts(
    *,
    input_path: str | Path,
    out_concepts: str | Path,
    out_relations: str | Path,
    out_registry: str | Path | None = None,
    allow_snomed: bool = True,
) -> dict[str, int]:
    bundles = [bundle_from_payload(row, allow_snomed=allow_snomed) for row in iter_rows(input_path)]
    concept_rows = [concept_payload(bundle) for bundle in bundles]
    relation_items = [row for bundle in bundles for row in relation_rows(bundle)]
    registry_rows = [
        {
            "concept_id": bundle.concept_id,
            "preferred_label": bundle.preferred_label,
            "semantic_type": bundle.semantic_type,
            "attributes": bundle.attributes,
            "open_anchor_count": len(bundle.open_anchors),
            "broader_anchor_count": len(bundle.broader_anchors),
            "relation_count": len(relation_rows(bundle)),
        }
        for bundle in bundles
    ]
    concept_count = write_jsonl(out_concepts, concept_rows)
    relation_count = write_jsonl(out_relations, relation_items)
    if out_registry:
        write_jsonl(out_registry, registry_rows)
    return {
        "bundles": len(bundles),
        "concepts": concept_count,
        "relations": relation_count,
        "registry_rows": len(registry_rows),
    }


def validate_private_cpt_adapter(path: str | Path) -> dict[str, int]:
    rows = list(iter_rows(path))
    for index, row in enumerate(rows, start=1):
        system = source_key(str(row.get("private_code_system") or row.get("code_system") or ""))
        if system not in CPT_SOURCES:
            raise ValueError(f"private CPT adapter row {index} must use private_code_system CPT/CPT4")
        if not str(row.get("procedure_bundle_id") or "").strip():
            raise ValueError(f"private CPT adapter row {index} is missing procedure_bundle_id")
        if not str(row.get("private_code") or row.get("code") or "").strip():
            raise ValueError(f"private CPT adapter row {index} is missing private_code")
        forbidden = sorted(key for key in row if descriptor_key(key) in CPT_DESCRIPTOR_KEYS)
        if forbidden:
            raise ValueError(
                f"private CPT adapter row {index} contains descriptor-like fields "
                f"{', '.join(forbidden)}; keep private adapters code-only"
            )
    return {"private_cpt_adapter_rows": len(rows)}
