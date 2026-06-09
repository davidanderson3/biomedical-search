from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .code_index import CodeIndex
from .schema import ConceptDocument, iter_jsonl
from .text import normalized_key


DRUG_MAPPING_SABS = ("RXNORM", "ATC", "MTHSPL", "DRUGBANK")
DRUG_ENRICHMENT_VIEW = "drug_enrichment"
OPEN_DRUG_ENRICHMENT_SOURCE_POLICY = (
    "open_literature_and_drug_vocabularies_only_no_ehr"
)
EHR_SOURCE_MARKERS = (
    "ehr",
    "electronic health record",
    "electronic medical record",
    "clinical note",
    "clinical_note",
)


@dataclass(frozen=True)
class DrugMention:
    doc_id: str
    source: str
    title: str
    snippet: str
    matched_label: str
    weight: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DrugTargetSpec:
    cui: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class DrugLiteratureRelationRule:
    cui: str
    label: str
    category: str
    relation_group: str
    relation: str
    rela: str
    triggers: tuple[str, ...]
    min_support: int = 1
    rank: int = 50


def is_ehr_like_source(value: str | Path) -> bool:
    text = str(value or "").lower()
    if not text:
        return False
    normalized = re.sub(r"[^a-z0-9]+", " ", text).strip()
    tokens = set(normalized.split())
    for marker in EHR_SOURCE_MARKERS:
        marker_normalized = re.sub(r"[^a-z0-9]+", " ", marker.lower()).strip()
        if not marker_normalized:
            continue
        if " " in marker_normalized and marker_normalized in normalized:
            return True
        if " " not in marker_normalized and marker_normalized in tokens:
            return True
    return False


DRUG_LITERATURE_RELATION_RULES: dict[str, tuple[DrugLiteratureRelationRule, ...]] = {
    "C4508938": (
        DrugLiteratureRelationRule(
            cui="C0184567",
            label="Acute onset pain",
            category="condition",
            relation_group="treatment",
            relation="indicated_for",
            rela="local_literature_indicated_for",
            triggers=(r"\bacute pain\b", r"\bpostoperative pain\b", r"\bpost-?surgical pain\b"),
            rank=10,
        ),
    ),
    "C0025598": (
        DrugLiteratureRelationRule(
            cui="C0011860",
            label="Diabetes mellitus, Type 2",
            category="condition",
            relation_group="treatment",
            relation="indicated_for",
            rela="local_literature_indicated_for",
            triggers=(
                r"\btype\s*2 diabetes\b",
                r"\btype\s*2 diabetes mellitus\b",
                r"\bt2dm\b",
            ),
            rank=10,
        ),
        DrugLiteratureRelationRule(
            cui="C5392125",
            label="Glycemic Control",
            category="finding",
            relation_group="effect",
            relation="affects",
            rela="local_literature_affects",
            triggers=(
                r"\bglyc[ae]mic control\b",
                r"\bblood glucose control\b",
                r"\bhba1c\b",
            ),
            rank=20,
        ),
    ),
    "C0016860": (
        DrugLiteratureRelationRule(
            cui="C0354100",
            label="Loop Diuretics",
            category="drug_class",
            relation_group="classification",
            relation="has_drug_class",
            rela="local_literature_has_drug_class",
            triggers=(r"\bloop diuretic",),
            rank=10,
        ),
        DrugLiteratureRelationRule(
            cui="C0018801",
            label="Heart failure",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(
                r"\bheart failure\b",
                r"\bcongestive heart failure\b",
                r"\bdecompensated heart failure\b",
            ),
            rank=20,
        ),
        DrugLiteratureRelationRule(
            cui="C0013604",
            label="Edema",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\bedema\b", r"\boedema\b", r"\bpulmonary edema\b"),
            rank=30,
        ),
        DrugLiteratureRelationRule(
            cui="C0012797",
            label="Diuresis",
            category="finding",
            relation_group="effect",
            relation="causes_or_promotes",
            rela="local_literature_causes_or_promotes",
            triggers=(r"\bdiuresis\b", r"\bdiuretic\b", r"\bdecongestion\b"),
            rank=40,
        ),
    ),
    "C0042313": (
        DrugLiteratureRelationRule(
            cui="C1265292",
            label="Methicillin-Resistant Staphylococcus aureus",
            category="organism",
            relation_group="treatment",
            relation="active_against",
            rela="local_literature_active_against",
            triggers=(r"\bmrsa\b", r"\bmethicillin-resistant staphylococcus aureus\b"),
            rank=10,
        ),
        DrugLiteratureRelationRule(
            cui="C0014121",
            label="Bacterial Endocarditis",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\bendocarditis\b",),
            rank=20,
        ),
        DrugLiteratureRelationRule(
            cui="C0025295",
            label="Meningitis, Pneumococcal",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\bmeningitis\b", r"\bpneumococcal meningitis\b"),
            rank=30,
        ),
        DrugLiteratureRelationRule(
            cui="C0489941",
            label="Vancomycin measurement",
            category="laboratory_test",
            relation_group="monitoring",
            relation="monitored_by",
            rela="local_literature_monitored_by",
            triggers=(
                r"\btherapeutic drug monitoring\b",
                r"\bvancomycin (?:level|levels|trough)\b",
                r"\btrough (?:level|levels|concentration)",
            ),
            rank=40,
        ),
    ),
    "C0286651": (
        DrugLiteratureRelationRule(
            cui="C0360714",
            label="Hydroxymethylglutaryl-CoA Reductase Inhibitors",
            category="drug_class",
            relation_group="classification",
            relation="has_drug_class",
            rela="local_literature_has_drug_class",
            triggers=(
                r"\bhmg-?coa reductase inhibitor",
                r"\bhydroxymethylglutaryl-?coa reductase inhibitor",
                r"\bstatin\b",
            ),
            rank=10,
        ),
        DrugLiteratureRelationRule(
            cui="C0020473",
            label="Hyperlipidemia",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\bhyperlipid[ae]mia\b",),
            rank=20,
        ),
        DrugLiteratureRelationRule(
            cui="C0242339",
            label="Dyslipidemia",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\bdyslipid[ae]mia\b",),
            rank=30,
        ),
        DrugLiteratureRelationRule(
            cui="C1956346",
            label="Coronary Artery Disease",
            category="condition",
            relation_group="prevention",
            relation="used_for_risk_reduction",
            rela="local_literature_used_for_risk_reduction",
            triggers=(r"\bcoronary artery disease\b", r"\bcardiovascular disease\b"),
            rank=40,
        ),
        DrugLiteratureRelationRule(
            cui="C2975999",
            label="HMGCR protein, human",
            category="gene_protein",
            relation_group="target",
            relation="acts_on",
            rela="local_literature_acts_on",
            triggers=(r"\bhmgcr\b", r"\bhmg-?coa reductase\b"),
            rank=50,
        ),
    ),
    "C0043031": (
        DrugLiteratureRelationRule(
            cui="C3653316",
            label="Vitamin K antagonists",
            category="drug_class",
            relation_group="classification",
            relation="has_drug_class",
            rela="local_literature_has_drug_class",
            triggers=(r"\bvitamin k antagonist", r"\bvka\b"),
            rank=10,
        ),
        DrugLiteratureRelationRule(
            cui="C0003280",
            label="Anticoagulants",
            category="drug_class",
            relation_group="classification",
            relation="has_drug_class",
            rela="local_literature_has_drug_class",
            triggers=(r"\banticoagulant", r"\banticoagulation\b"),
            rank=20,
        ),
        DrugLiteratureRelationRule(
            cui="C0004238",
            label="Atrial Fibrillation",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\batrial fibrillation\b", r"\bnonvalvular atrial fibrillation\b"),
            rank=30,
        ),
        DrugLiteratureRelationRule(
            cui="C0040053",
            label="Thrombosis",
            category="condition",
            relation_group="prevention",
            relation="prevents_or_treats",
            rela="local_literature_prevents_or_treats",
            triggers=(r"\bthrombo", r"\bthrombosis\b", r"\bvenous thromboembolism\b"),
            rank=40,
        ),
        DrugLiteratureRelationRule(
            cui="C0525032",
            label="International Normalized Ratio",
            category="laboratory_test",
            relation_group="monitoring",
            relation="monitored_by",
            rela="local_literature_monitored_by",
            triggers=(r"\binr\b", r"\binternational normalized ratio\b"),
            rank=50,
        ),
        DrugLiteratureRelationRule(
            cui="C0019080",
            label="Bleeding",
            category="adverse_event",
            relation_group="safety",
            relation="may_cause",
            rela="local_literature_may_cause",
            triggers=(r"\bbleeding\b", r"\bhemorrhage\b", r"\bhaemorrhage\b"),
            rank=60,
        ),
    ),
    "C3885068": (
        DrugLiteratureRelationRule(
            cui="C1562104",
            label="GLP-1 Receptor Agonists",
            category="drug_class",
            relation_group="classification",
            relation="has_drug_class",
            rela="local_literature_has_drug_class",
            triggers=(
                r"\bglp-?1 receptor agonist",
                r"\bglucagon-like peptide-?1 receptor agonist",
            ),
            rank=10,
        ),
        DrugLiteratureRelationRule(
            cui="C0011860",
            label="Diabetes mellitus, Type 2",
            category="condition",
            relation_group="treatment",
            relation="indicated_for",
            rela="local_literature_indicated_for",
            triggers=(r"\btype\s*2 diabetes\b", r"\btype\s*2 diabetes mellitus\b", r"\bt2dm\b"),
            rank=20,
        ),
        DrugLiteratureRelationRule(
            cui="C0028754",
            label="Obesity",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\bobesity\b", r"\bweight loss\b", r"\bweight management\b"),
            rank=30,
        ),
        DrugLiteratureRelationRule(
            cui="C5392125",
            label="Glycemic Control",
            category="finding",
            relation_group="effect",
            relation="affects",
            rela="local_literature_affects",
            triggers=(r"\bglyc[ae]mic control\b", r"\bhba1c\b", r"\bblood glucose\b"),
            rank=40,
        ),
    ),
    "C0075632": (
        DrugLiteratureRelationRule(
            cui="C1567966",
            label="Triptans",
            category="drug_class",
            relation_group="classification",
            relation="has_drug_class",
            rela="local_literature_has_drug_class",
            triggers=(r"\btriptan",),
            rank=10,
        ),
        DrugLiteratureRelationRule(
            cui="C0162754",
            label="Serotonin 5-HT1 Receptor Agonists",
            category="drug_class",
            relation_group="classification",
            relation="has_drug_class",
            rela="local_literature_has_drug_class",
            triggers=(
                r"\b5-?ht1\b",
                r"\bserotonin 5-?ht1 receptor agonist",
                r"\b5-?hydroxytryptamine\s*1\b",
            ),
            rank=20,
        ),
        DrugLiteratureRelationRule(
            cui="C0149931",
            label="Migraine Disorders",
            category="condition",
            relation_group="treatment",
            relation="indicated_for",
            rela="local_literature_indicated_for",
            triggers=(r"\bmigraine", r"\bmigraine headache", r"\bacute migraine"),
            rank=30,
        ),
        DrugLiteratureRelationRule(
            cui="C0009088",
            label="Cluster Headache",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\bcluster headache",),
            rank=40,
        ),
    ),
    "C1831808": (
        DrugLiteratureRelationRule(
            cui="C0003280",
            label="Anticoagulants",
            category="drug_class",
            relation_group="classification",
            relation="has_drug_class",
            rela="local_literature_has_drug_class",
            triggers=(r"\banticoagulant", r"\banticoagulation\b", r"\bdirect oral anticoagulant"),
            rank=10,
        ),
        DrugLiteratureRelationRule(
            cui="C0004238",
            label="Atrial Fibrillation",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\batrial fibrillation\b", r"\bnonvalvular atrial fibrillation\b"),
            rank=20,
        ),
        DrugLiteratureRelationRule(
            cui="C0042487",
            label="Venous Thrombosis",
            category="condition",
            relation_group="treatment",
            relation="prevents_or_treats",
            rela="local_literature_prevents_or_treats",
            triggers=(r"\bvenous thrombo", r"\bvenous thrombosis\b", r"\bvenous thromboembolism\b"),
            rank=30,
        ),
        DrugLiteratureRelationRule(
            cui="C0034065",
            label="Pulmonary Embolism",
            category="condition",
            relation_group="treatment",
            relation="prevents_or_treats",
            rela="local_literature_prevents_or_treats",
            triggers=(r"\bpulmonary embol",),
            rank=40,
        ),
        DrugLiteratureRelationRule(
            cui="C0019080",
            label="Bleeding",
            category="adverse_event",
            relation_group="safety",
            relation="may_cause",
            rela="local_literature_may_cause",
            triggers=(r"\bbleeding\b", r"\bhemorrhage\b", r"\bhaemorrhage\b"),
            rank=50,
        ),
    ),
    "C0529793": (
        DrugLiteratureRelationRule(
            cui="C0020542",
            label="Pulmonary Hypertension",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\bpulmonary hypertension\b", r"\bpulmonary arterial hypertension\b"),
            rank=10,
        ),
    ),
    "C0065374": (
        DrugLiteratureRelationRule(
            cui="C0020538",
            label="Hypertensive disease",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\bhypertension\b", r"\bhigh blood pressure\b"),
            rank=10,
        ),
        DrugLiteratureRelationRule(
            cui="C0018801",
            label="Heart failure",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\bheart failure\b", r"\bcongestive heart failure\b"),
            rank=20,
        ),
    ),
    "C0023570": (
        DrugLiteratureRelationRule(
            cui="C0030567",
            label="Parkinson Disease",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\bparkinson", r"\bparkinson disease\b"),
            rank=10,
        ),
    ),
    "C0024002": (
        DrugLiteratureRelationRule(
            cui="C0236663",
            label="Alcohol Withdrawal Syndrome",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\balcohol withdrawal\b", r"\bwithdrawal syndrome\b"),
            rank=10,
        ),
        DrugLiteratureRelationRule(
            cui="C0036572",
            label="Seizures",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\bseizure", r"\bstatus epilepticus\b"),
            rank=20,
        ),
    ),
    "C0004057": (
        DrugLiteratureRelationRule(
            cui="C0027051",
            label="Myocardial Infarction",
            category="condition",
            relation_group="prevention",
            relation="used_for_risk_reduction",
            rela="local_literature_used_for_risk_reduction",
            triggers=(r"\bmyocardial infarction\b", r"\bheart attack\b"),
            rank=10,
        ),
        DrugLiteratureRelationRule(
            cui="C0040053",
            label="Thrombosis",
            category="condition",
            relation_group="prevention",
            relation="prevents_or_treats",
            rela="local_literature_prevents_or_treats",
            triggers=(r"\bthrombo", r"\bantiplatelet\b"),
            rank=20,
        ),
        DrugLiteratureRelationRule(
            cui="C0019080",
            label="Bleeding",
            category="adverse_event",
            relation_group="safety",
            relation="may_cause",
            rela="local_literature_may_cause",
            triggers=(r"\bbleeding\b", r"\bhemorrhage\b", r"\bhaemorrhage\b"),
            rank=30,
        ),
    ),
    "C0039286": (
        DrugLiteratureRelationRule(
            cui="C0678222",
            label="Breast Cancer",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\bbreast cancer\b", r"\bbreast carcinoma\b"),
            rank=10,
        ),
        DrugLiteratureRelationRule(
            cui="C0279754",
            label="Estrogen receptor positive",
            category="finding",
            relation_group="biomarker_context",
            relation="biomarker_context",
            rela="local_literature_biomarker_context",
            triggers=(r"\bestrogen receptor positive\b", r"\ber-positive\b", r"\ber positive\b"),
            rank=20,
        ),
    ),
    "C0377265": (
        DrugLiteratureRelationRule(
            cui="C0036572",
            label="Seizures",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\bseizure", r"\bepilepsy\b"),
            rank=10,
        ),
    ),
    "C0002645": (
        DrugLiteratureRelationRule(
            cui="C0003232",
            label="Antibiotics",
            category="drug_class",
            relation_group="classification",
            relation="has_drug_class",
            rela="local_literature_has_drug_class",
            triggers=(r"\bantibiotic", r"\bantibacterial"),
            rank=10,
        ),
        DrugLiteratureRelationRule(
            cui="C0029882",
            label="Otitis Media",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\botitis media\b", r"\bmiddle ear infection\b"),
            rank=20,
        ),
        DrugLiteratureRelationRule(
            cui="C0037199",
            label="Sinusitis",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\bsinusitis\b",),
            rank=30,
        ),
    ),
    "C0007716": (
        DrugLiteratureRelationRule(
            cui="C0003232",
            label="Antibiotics",
            category="drug_class",
            relation_group="classification",
            relation="has_drug_class",
            rela="local_literature_has_drug_class",
            triggers=(r"\bantibiotic", r"\bcephalosporin"),
            rank=10,
        ),
        DrugLiteratureRelationRule(
            cui="C0007642",
            label="Cellulitis",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\bcellulitis\b", r"\bskin and soft tissue infection", r"\bssti\b"),
            rank=20,
        ),
    ),
    "C0007561": (
        DrugLiteratureRelationRule(
            cui="C0003232",
            label="Antibiotics",
            category="drug_class",
            relation_group="classification",
            relation="has_drug_class",
            rela="local_literature_has_drug_class",
            triggers=(r"\bantibiotic", r"\bcephalosporin"),
            rank=10,
        ),
        DrugLiteratureRelationRule(
            cui="C0520575",
            label="Pyelonephritis",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\bpyelonephritis\b",),
            rank=20,
        ),
        DrugLiteratureRelationRule(
            cui="C0018081",
            label="Gonorrhea",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\bgonorrh",),
            rank=30,
        ),
    ),
    "C0013090": (
        DrugLiteratureRelationRule(
            cui="C0003232",
            label="Antibiotics",
            category="drug_class",
            relation_group="classification",
            relation="has_drug_class",
            rela="local_literature_has_drug_class",
            triggers=(r"\bantibiotic", r"\btetracycline"),
            rank=10,
        ),
        DrugLiteratureRelationRule(
            cui="C0024198",
            label="Lyme Disease",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\blyme disease\b", r"\bborrelia\b"),
            rank=20,
        ),
        DrugLiteratureRelationRule(
            cui="C0242172",
            label="Pelvic Inflammatory Disease",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\bpelvic inflammatory disease\b", r"\bpid\b"),
            rank=30,
        ),
    ),
    "C0001927": (
        DrugLiteratureRelationRule(
            cui="C0004096",
            label="Asthma",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\basthma\b",),
            rank=10,
        ),
        DrugLiteratureRelationRule(
            cui="C0043144",
            label="Wheezing",
            category="finding",
            relation_group="effect",
            relation="relieves",
            rela="local_literature_relieves",
            triggers=(r"\bwheez", r"\bbronchospasm\b"),
            rank=20,
        ),
    ),
    "C0025677": (
        DrugLiteratureRelationRule(
            cui="C0003873",
            label="Rheumatoid Arthritis",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\brheumatoid arthritis\b",),
            rank=10,
        ),
        DrugLiteratureRelationRule(
            cui="C0033860",
            label="Psoriasis",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\bpsoriasis\b",),
            rank=20,
        ),
    ),
    "C0081876": (
        DrugLiteratureRelationRule(
            cui="C0038358",
            label="Gastric Ulcer",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\bgastric ulcer\b", r"\bpeptic ulcer\b"),
            rank=10,
        ),
        DrugLiteratureRelationRule(
            cui="C0017168",
            label="Gastroesophageal reflux disease",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\bgastroesophageal reflux\b", r"\bgerd\b"),
            rank=20,
        ),
    ),
    "C0040233": (
        DrugLiteratureRelationRule(
            cui="C0017601",
            label="Glaucoma",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\bglaucoma\b",),
            rank=10,
        ),
        DrugLiteratureRelationRule(
            cui="C0234708",
            label="Intraocular Pressure",
            category="measurement",
            relation_group="effect",
            relation="affects",
            rela="local_literature_affects",
            triggers=(r"\bintraocular pressure\b", r"\biop\b"),
            rank=20,
        ),
    ),
    "C0874161": (
        DrugLiteratureRelationRule(
            cui="C0021400",
            label="Influenza",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\binfluenza\b", r"\bflu\b"),
            rank=10,
        ),
    ),
    "C0020268": (
        DrugLiteratureRelationRule(
            cui="C0001403",
            label="Addison Disease",
            category="condition",
            relation_group="treatment",
            relation="used_for",
            rela="local_literature_used_for",
            triggers=(r"\baddison", r"\badrenal insufficiency\b"),
            rank=10,
        ),
    ),
}


def load_drug_target_specs(path: str | Path) -> list[DrugTargetSpec]:
    specs: list[DrugTargetSpec] = []
    seen: set[str] = set()
    for raw_line in Path(path).expanduser().read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split(None, 1)
        cui = parts[0].strip().upper()
        if not cui or cui in seen:
            continue
        alias_text = parts[1].strip() if len(parts) > 1 else ""
        aliases = tuple(
            alias.strip()
            for alias in re.split(r"\s*[|,]\s*", alias_text)
            if alias.strip()
        )
        seen.add(cui)
        specs.append(DrugTargetSpec(cui=cui, aliases=aliases))
    return specs


def load_target_cuis(path: str | Path) -> list[str]:
    return [spec.cui for spec in load_drug_target_specs(path)]


def build_drug_enrichment_documents(
    *,
    target_cuis: Iterable[str],
    code_index_path: str | Path,
    corpus_paths: Iterable[str | Path],
    target_aliases_by_cui: dict[str, Iterable[str]] | None = None,
    mapping_sabs: Iterable[str] = DRUG_MAPPING_SABS,
    max_mentions_per_cui: int = 80,
    max_labels: int = 24,
) -> list[ConceptDocument]:
    code_index = CodeIndex(code_index_path)
    try:
        prepared: list[tuple[str, list[str], list[dict]]] = []
        target_cui_rows = [cui.strip().upper() for cui in target_cuis if cui.strip()]
        aliases_by_cui = target_aliases_by_cui or {}
        requested_sabs = tuple(sab.strip().upper() for sab in mapping_sabs if sab)
        for cui in target_cui_rows:
            mappings = code_index.lookup_cui(cui, sabs=requested_sabs, limit=500)
            preferred = code_index.preferred_label(cui)
            labels = drug_labels(
                preferred,
                mappings,
                aliases=aliases_by_cui.get(cui, ()),
                max_labels=max_labels,
            )
            if labels:
                prepared.append((cui, labels, mappings))
        mentions_by_cui = find_local_drug_mentions_by_cui(
            corpus_paths,
            {cui: labels for cui, labels, _mappings in prepared},
            max_mentions_per_cui=max_mentions_per_cui,
        )
        documents = []
        for cui, labels, mappings in prepared:
            mentions = mentions_by_cui.get(cui, [])
            if not mentions and not mappings:
                continue
            relations = extract_literature_relations(cui, mentions)
            document = drug_enrichment_document(
                cui,
                labels,
                mappings,
                mentions,
                relations=relations,
            )
            if document:
                documents.append(document)
        return documents
    finally:
        code_index.close()


def build_drug_enrichment_document(
    cui: str,
    *,
    code_index: CodeIndex,
    corpus_paths: Iterable[str | Path],
    aliases: Iterable[str] = (),
    mapping_sabs: Iterable[str] = DRUG_MAPPING_SABS,
    max_mentions: int = 80,
    max_labels: int = 24,
) -> ConceptDocument | None:
    cui = cui.strip().upper()
    if not cui:
        return None
    requested_sabs = tuple(sab.strip().upper() for sab in mapping_sabs if sab)
    mappings = code_index.lookup_cui(cui, sabs=requested_sabs, limit=500)
    preferred = code_index.preferred_label(cui)
    labels = drug_labels(preferred, mappings, aliases=aliases, max_labels=max_labels)
    if not labels:
        return None
    mentions = find_local_drug_mentions(corpus_paths, labels, max_mentions=max_mentions)
    if not mentions and not mappings:
        return None
    relations = extract_literature_relations(cui, mentions)
    return drug_enrichment_document(cui, labels, mappings, mentions, relations=relations)


def drug_labels(
    preferred: str,
    mappings: list[dict],
    *,
    aliases: Iterable[str] = (),
    max_labels: int = 24,
) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        text = re.sub(r"\s+", " ", value or "").strip()
        key = normalized_key(text)
        if not text or not key or key in seen:
            return
        seen.add(key)
        labels.append(text)

    add(preferred)
    for alias in aliases:
        add(alias)
    for row in sorted(
        mappings,
        key=lambda item: (
            0 if str(item.get("ispref") or "") == "Y" else 1,
            str(item.get("sab") or ""),
            str(item.get("tty") or ""),
            str(item.get("label") or "").lower(),
        ),
    ):
        add(str(row.get("label") or ""))
        if len(labels) >= max_labels:
            break
    return labels[:max_labels]


def find_local_drug_mentions(
    corpus_paths: Iterable[str | Path],
    labels: Iterable[str],
    *,
    max_mentions: int = 80,
) -> list[DrugMention]:
    patterns = label_patterns(labels)
    if not patterns:
        return []
    mentions: list[DrugMention] = []
    seen_snippets: set[str] = set()
    for corpus_path in corpus_paths:
        path = Path(corpus_path).expanduser()
        if not path.exists() or is_ehr_like_source(path):
            continue
        for payload in iter_jsonl(path):
            metadata = payload.get("metadata") or {}
            source = str(payload.get("source") or metadata.get("source") or "")
            if is_ehr_like_source(source):
                continue
            text = str(payload.get("text") or "")
            title = str(payload.get("title") or "")
            searchable = " ".join(part for part in (title, text) if part)
            matched_label = first_matching_label(searchable, patterns)
            if not matched_label:
                continue
            snippet = mention_snippet(searchable, matched_label)
            snippet_key = normalized_key(snippet)
            if not snippet or snippet_key in seen_snippets:
                continue
            seen_snippets.add(snippet_key)
            doc_id = str(payload.get("doc_id") or metadata.get("pmid") or "")
            mentions.append(
                DrugMention(
                    doc_id=doc_id,
                    source=source or path.stem,
                    title=title,
                    snippet=snippet,
                    matched_label=matched_label,
                    weight=mention_weight(payload, matched_label),
                    metadata=dict(metadata),
                )
            )
            if len(mentions) >= max_mentions:
                return sort_mentions(mentions)[:max_mentions]
    return sort_mentions(mentions)[:max_mentions]


def find_local_drug_mentions_by_cui(
    corpus_paths: Iterable[str | Path],
    labels_by_cui: dict[str, Iterable[str]],
    *,
    max_mentions_per_cui: int = 80,
) -> dict[str, list[DrugMention]]:
    rows_by_label_key: dict[str, list[tuple[str, str]]] = {}
    label_text_by_key: dict[str, str] = {}
    for cui, labels in labels_by_cui.items():
        for label, _pattern in label_patterns(labels):
            key = normalized_key(label)
            if not key:
                continue
            rows_by_label_key.setdefault(key, []).append((cui, label))
            label_text_by_key.setdefault(key, label)
    if not rows_by_label_key:
        return {cui: [] for cui in labels_by_cui}
    labels_for_regex = sorted(
        label_text_by_key.values(),
        key=lambda item: (-len(item), item.lower()),
    )
    combined_pattern = re.compile(
        r"(?<![A-Za-z0-9])("
        + "|".join(re.escape(label) for label in labels_for_regex)
        + r")(?![A-Za-z0-9])",
        re.IGNORECASE,
    )
    mentions_by_cui: dict[str, list[DrugMention]] = {cui: [] for cui in labels_by_cui}
    seen_by_cui: dict[str, set[str]] = {cui: set() for cui in labels_by_cui}
    complete: set[str] = set()
    for corpus_path in corpus_paths:
        path = Path(corpus_path).expanduser()
        if not path.exists() or is_ehr_like_source(path):
            continue
        for payload in iter_jsonl(path):
            if len(complete) >= len(mentions_by_cui):
                return {
                    cui: sort_mentions(mentions)[:max_mentions_per_cui]
                    for cui, mentions in mentions_by_cui.items()
                }
            metadata = payload.get("metadata") or {}
            source = str(payload.get("source") or metadata.get("source") or "")
            if is_ehr_like_source(source):
                continue
            text = str(payload.get("text") or "")
            title = str(payload.get("title") or "")
            searchable = " ".join(part for part in (title, text) if part)
            if not searchable:
                continue
            matched_this_payload: set[str] = set()
            for match in combined_pattern.finditer(searchable):
                label_key = normalized_key(match.group(1))
                for cui, label in rows_by_label_key.get(label_key, ()):
                    if cui in complete or cui in matched_this_payload:
                        continue
                    snippet = mention_snippet(searchable, label)
                    snippet_key = normalized_key(snippet)
                    if not snippet or snippet_key in seen_by_cui[cui]:
                        matched_this_payload.add(cui)
                        continue
                    seen_by_cui[cui].add(snippet_key)
                    doc_id = str(payload.get("doc_id") or metadata.get("pmid") or "")
                    mentions_by_cui[cui].append(
                        DrugMention(
                            doc_id=doc_id,
                            source=source or path.stem,
                            title=title,
                            snippet=snippet,
                            matched_label=label,
                            weight=mention_weight(payload, label),
                            metadata=dict(metadata),
                        )
                    )
                    matched_this_payload.add(cui)
                    if len(mentions_by_cui[cui]) >= max_mentions_per_cui:
                        complete.add(cui)
                if len(complete) >= len(mentions_by_cui):
                    break
            if len(complete) >= len(mentions_by_cui):
                return {
                    cui: sort_mentions(mentions)[:max_mentions_per_cui]
                    for cui, mentions in mentions_by_cui.items()
                }
    return {
        cui: sort_mentions(mentions)[:max_mentions_per_cui]
        for cui, mentions in mentions_by_cui.items()
    }


def label_patterns(labels: Iterable[str]) -> list[tuple[str, re.Pattern[str]]]:
    patterns: list[tuple[str, re.Pattern[str]]] = []
    seen: set[str] = set()
    for label in labels:
        text = re.sub(r"\s+", " ", label or "").strip()
        key = normalized_key(text)
        if len(key) < 4 or key in seen:
            continue
        seen.add(key)
        left = r"(?<![A-Za-z0-9])"
        right = r"(?![A-Za-z0-9])"
        patterns.append((text, re.compile(left + re.escape(text) + right, re.IGNORECASE)))
    patterns.sort(key=lambda item: (-len(item[0]), item[0].lower()))
    return patterns


def first_matching_label(text: str, patterns: list[tuple[str, re.Pattern[str]]]) -> str:
    for label, pattern in patterns:
        if pattern.search(text):
            return label
    return ""


def mention_snippet(text: str, label: str, *, max_chars: int = 700) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if not clean:
        return ""
    pattern = re.compile(re.escape(label), re.IGNORECASE)
    match = pattern.search(clean)
    if not match:
        return clean[:max_chars].rstrip()
    sentence = containing_sentence(clean, match.start(), match.end())
    if len(sentence) <= max_chars:
        return sentence
    midpoint = (match.start() + match.end()) // 2
    start = max(0, midpoint - max_chars // 2)
    end = min(len(clean), start + max_chars)
    if end - start < max_chars:
        start = max(0, end - max_chars)
    return clean[start:end].strip(" ;,.")


def containing_sentence(text: str, start: int, end: int) -> str:
    left = text.rfind(". ", 0, start)
    right_candidates = [
        position for position in (text.find(". ", end),) if position != -1
    ]
    right = min(right_candidates) if right_candidates else len(text)
    sentence = text[(left + 2 if left >= 0 else 0) : right + (1 if right < len(text) else 0)]
    return sentence.strip()


def mention_weight(payload: dict[str, Any], matched_label: str) -> float:
    title = str(payload.get("title") or "")
    text = str(payload.get("text") or "")
    weight = 1.0
    if re.search(re.escape(matched_label), title, re.IGNORECASE):
        weight += 0.4
    if str(payload.get("doc_id") or "").upper().startswith("PMID:"):
        weight += 0.2
    metadata = payload.get("metadata") or {}
    if metadata.get("doi"):
        weight += 0.1
    if "clinical trial" in " ".join(map(str, metadata.get("publication_types") or [])).lower():
        weight += 0.2
    return round(weight, 2)


def sort_mentions(mentions: list[DrugMention]) -> list[DrugMention]:
    return sorted(
        mentions,
        key=lambda item: (
            -item.weight,
            -int(bool(item.metadata.get("publication_year"))),
            str(item.doc_id),
            item.snippet.lower(),
        ),
    )


def extract_literature_relations(cui: str, mentions: list[DrugMention]) -> list[dict]:
    rules = DRUG_LITERATURE_RELATION_RULES.get(cui.strip().upper(), ())
    if not rules or not mentions:
        return []
    relations = []
    for rule in rules:
        supporting = matching_relation_mentions(rule, mentions)
        if len(supporting) < rule.min_support:
            continue
        pmids = sorted(
            {
                str(mention.metadata.get("pmid") or "").strip()
                for mention in supporting
                if str(mention.metadata.get("pmid") or "").strip()
            }
        )
        doc_ids = sorted({mention.doc_id for mention in supporting if mention.doc_id})
        titles = []
        seen_titles: set[str] = set()
        for mention in supporting:
            title = re.sub(r"\s+", " ", mention.title or "").strip()
            key = normalized_key(title)
            if not title or key in seen_titles:
                continue
            seen_titles.add(key)
            titles.append(title)
            if len(titles) >= 5:
                break
        relations.append(
            {
                "cui": rule.cui,
                "label": rule.label,
                "category": rule.category,
                "relation_group": rule.relation_group,
                "relation": rule.relation,
                "rela": rule.rela,
                "source": "local_literature",
                "direction": "outgoing",
                "rank": rule.rank,
                "support_count": len(supporting),
                "supporting_pmids": pmids[:10],
                "supporting_doc_ids": doc_ids[:10],
                "supporting_titles": titles,
            }
        )
    return sorted(relations, key=lambda item: (int(item["rank"]), item["label"]))


def matching_relation_mentions(
    rule: DrugLiteratureRelationRule,
    mentions: list[DrugMention],
) -> list[DrugMention]:
    supporting = []
    seen: set[str] = set()
    patterns = [re.compile(pattern, re.IGNORECASE) for pattern in rule.triggers]
    for mention in mentions:
        text = " ".join(part for part in (mention.title, mention.snippet) if part)
        if not any(pattern.search(text) for pattern in patterns):
            continue
        key = mention.doc_id or normalized_key(text)
        if key in seen:
            continue
        seen.add(key)
        supporting.append(mention)
    return sort_mentions(supporting)


def drug_enrichment_document(
    cui: str,
    labels: list[str],
    mappings: list[dict],
    mentions: list[DrugMention],
    *,
    relations: list[dict] | None = None,
) -> ConceptDocument:
    relation_rows = relations or []
    sources = sorted({mention.source for mention in mentions if mention.source})
    mapping_rows = compact_mappings(mappings)
    mapping_sources = sorted({row["sab"] for row in mapping_rows if row.get("sab")})
    sources.extend(source for source in mapping_sources if source not in sources)
    lines = [
        f"CUI: {cui}",
        f"Evidence view: {DRUG_ENRICHMENT_VIEW}",
        "UMLS labels:",
    ]
    lines.extend(f"- {label}" for label in labels)
    if mapping_rows:
        lines.append("Drug vocabulary mappings:")
        for row in mapping_rows:
            code = row.get("code") or row.get("scui") or row.get("sdui") or ""
            code_text = f" {code}" if code else ""
            lines.append(
                f"- {row['sab']} {row['tty']}{code_text}: {row['label']}"
            )
    if relation_rows:
        lines.append("Literature-derived CUI relationships:")
        for row in relation_rows:
            support_text = f"{int(row.get('support_count') or 0)} local mention"
            if int(row.get("support_count") or 0) != 1:
                support_text += "s"
            lines.append(
                f"- {row['label']} ({row['cui']}): {row['relation']} "
                f"[{row['relation_group']}]; {support_text}"
            )
    if mentions:
        lines.append("Open literature evidence:")
        for mention in mentions:
            citation = mention_citation(mention)
            lines.append(f"- {citation}: {mention.snippet} (weight {mention.weight:g})")
    return ConceptDocument(
        doc_id=f"{cui}:{DRUG_ENRICHMENT_VIEW}",
        cui=cui,
        view=DRUG_ENRICHMENT_VIEW,
        text="\n".join(lines),
        evidence_count=len(mentions),
        sources=sources,
        labels=labels,
        metadata={
            "document_builder": "drug_enrichment",
            "source_policy": OPEN_DRUG_ENRICHMENT_SOURCE_POLICY,
            "mapping_sabs": list(DRUG_MAPPING_SABS),
            "mappings": mapping_rows,
            "mention_count": len(mentions),
            "relations": relation_rows,
            "mention_sources": [
                {
                    "doc_id": mention.doc_id,
                    "source": mention.source,
                    "title": mention.title,
                    "matched_label": mention.matched_label,
                    "pmid": str(mention.metadata.get("pmid") or ""),
                    "doi": str(mention.metadata.get("doi") or ""),
                    "publication_year": str(mention.metadata.get("publication_year") or ""),
                }
                for mention in mentions
            ],
        },
    )


def compact_mappings(mappings: list[dict]) -> list[dict]:
    compact = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in mappings:
        item = {
            "sab": str(row.get("sab") or ""),
            "code": str(row.get("code") or ""),
            "scui": str(row.get("scui") or ""),
            "sdui": str(row.get("sdui") or ""),
            "tty": str(row.get("tty") or ""),
            "label": str(row.get("label") or ""),
            "ispref": str(row.get("ispref") or ""),
            "suppress": str(row.get("suppress") or ""),
        }
        key = (item["sab"], item["code"], item["tty"], normalized_key(item["label"]))
        if not item["label"] or key in seen:
            continue
        seen.add(key)
        compact.append(item)
    return compact


def mention_citation(mention: DrugMention) -> str:
    pmid = str(mention.metadata.get("pmid") or "")
    doi = str(mention.metadata.get("doi") or "")
    if pmid:
        return f"PMID:{pmid}"
    if mention.doc_id:
        return mention.doc_id
    if doi:
        return f"DOI:{doi}"
    return mention.source or "local_corpus"
