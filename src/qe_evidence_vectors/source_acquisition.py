from __future__ import annotations

import csv
import itertools
import json
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .schema import iter_jsonl
from .search_semantics import semantic_group_from_types
from .text import normalized_key
from .universal_relationship import universal_relationship_edge


@dataclass(frozen=True)
class SourceAcquisitionProfile:
    source: str
    label: str
    action: str
    rationale: str
    trust: float
    effort: float
    default_applicability: float = 0.0
    keywords: tuple[str, ...] = ()
    semantic_groups: tuple[str, ...] = ()
    public_default: bool = True


@dataclass
class AcquisitionRecommendation:
    source: str
    label: str
    action: str
    seed: str
    priority_score: float = 0.0
    query_count: int = 0
    missing_cuis: set[str] = field(default_factory=set)
    disallowed_cuis: set[str] = field(default_factory=set)
    candidate_disallowed_cuis: set[str] = field(default_factory=set)
    association_pairs: set[str] = field(default_factory=set)
    prevalence_score: float = 0.0
    raw_failure_weight: float = 0.0
    weighted_failure_weight: float = 0.0
    max_prevalence_multiplier: float = 1.0
    sample_query_ids: list[str] = field(default_factory=list)
    sample_queries: list[str] = field(default_factory=list)
    rationale: str = ""
    suggested_command: str = ""

    def add_row(
        self,
        row: dict[str, str],
        *,
        score: float,
        prevalence_score: float = 0.0,
        raw_failure_weight: float = 0.0,
        weighted_failure_weight: float = 0.0,
    ) -> None:
        self.priority_score += score
        self.query_count += 1
        self.prevalence_score = max(self.prevalence_score, prevalence_score)
        self.raw_failure_weight += raw_failure_weight
        self.weighted_failure_weight += weighted_failure_weight
        self.max_prevalence_multiplier = max(
            self.max_prevalence_multiplier,
            prevalence_multiplier(prevalence_score),
        )
        self.missing_cuis.update(missing_cuis(row))
        self.disallowed_cuis.update(split_values(row.get("disallowed_at_10", "")))
        self.disallowed_cuis.update(split_values(row.get("disallowed_at_20", "")))
        self.candidate_disallowed_cuis.update(split_values(row.get("candidate_disallowed_cuis", "")))
        self.association_pairs.update(split_pair_values(row.get("unavailable_association_pairs", "")))
        query_id = str(row.get("id") or "").strip()
        if query_id and query_id not in self.sample_query_ids and len(self.sample_query_ids) < 5:
            self.sample_query_ids.append(query_id)
        query = str(row.get("query") or "").strip()
        if query and query not in self.sample_queries and len(self.sample_queries) < 3:
            self.sample_queries.append(query)

    def to_payload(self) -> dict:
        payload = asdict(self)
        payload["priority_score"] = round(self.priority_score, 4)
        payload["missing_cuis"] = sorted(self.missing_cuis)
        payload["disallowed_cuis"] = sorted(self.disallowed_cuis)
        payload["candidate_disallowed_cuis"] = sorted(self.candidate_disallowed_cuis)
        payload["association_pairs"] = sorted(self.association_pairs)
        payload["association_count"] = len(self.association_pairs)
        payload["prevalence_score"] = round(self.prevalence_score, 3)
        payload["raw_failure_weight"] = round(self.raw_failure_weight, 4)
        payload["weighted_failure_weight"] = round(self.weighted_failure_weight, 4)
        payload["prevalence_multiplier"] = round(self.max_prevalence_multiplier, 3)
        return payload


@dataclass(frozen=True)
class AssociationInference:
    source_cui: str
    target_cui: str
    relationship_type: str
    relation_group: str
    direction: str
    confidence: float
    rationale: str


@dataclass
class AssociationCandidate:
    pair: str
    source_cui: str
    target_cui: str
    source_label: str
    target_label: str
    source_semantic_group: str
    target_semantic_group: str
    relationship_type: str
    relation_group: str
    direction: str
    relation_confidence: float
    rationale: str
    prevalence_score: float = 0.0
    utility_score: float = 0.0
    query_count: int = 0
    missing_query_count: int = 0
    evidence_sources: set[str] = field(default_factory=set)
    sample_query_ids: list[str] = field(default_factory=list)
    sample_queries: list[str] = field(default_factory=list)

    def add_row(
        self,
        row: dict[str, str],
        *,
        score: float,
        inference: AssociationInference,
        source_label: str,
        target_label: str,
        source_semantic_group: str,
        target_semantic_group: str,
        evidence_sources: Iterable[str],
        prevalence_score: float,
    ) -> None:
        self.utility_score += score
        self.prevalence_score = max(self.prevalence_score, prevalence_score)
        self.query_count += 1
        pair_cuis = set(pair_parts(self.pair))
        if pair_cuis & missing_cuis(row):
            self.missing_query_count += 1
        self.evidence_sources.update(source for source in evidence_sources if source)
        if inference.confidence > self.relation_confidence:
            self.source_cui = inference.source_cui
            self.target_cui = inference.target_cui
            self.source_label = source_label
            self.target_label = target_label
            self.source_semantic_group = source_semantic_group
            self.target_semantic_group = target_semantic_group
            self.relationship_type = inference.relationship_type
            self.relation_group = inference.relation_group
            self.direction = inference.direction
            self.relation_confidence = inference.confidence
            self.rationale = inference.rationale
        query_id = str(row.get("id") or "").strip()
        if query_id and query_id not in self.sample_query_ids and len(self.sample_query_ids) < 8:
            self.sample_query_ids.append(query_id)
        query = str(row.get("query") or "").strip()
        if query and query not in self.sample_queries and len(self.sample_queries) < 4:
            self.sample_queries.append(query)

    def to_payload(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "source_cui": self.source_cui,
            "target_cui": self.target_cui,
            "source_label": self.source_label,
            "target_label": self.target_label,
            "source_semantic_group": self.source_semantic_group,
            "target_semantic_group": self.target_semantic_group,
            "relationship_type": self.relationship_type,
            "relation_group": self.relation_group,
            "direction": self.direction,
            "relation_confidence": round(self.relation_confidence, 3),
            "prevalence_score": round(self.prevalence_score, 3),
            "prevalence_multiplier": round(prevalence_multiplier(self.prevalence_score), 3),
            "utility_score": round(self.utility_score, 4),
            "query_count": self.query_count,
            "missing_query_count": self.missing_query_count,
            "evidence_sources": sorted(self.evidence_sources),
            "sample_query_ids": list(self.sample_query_ids),
            "sample_queries": list(self.sample_queries),
            "rationale": self.rationale,
            "review_status": "needs_source_evidence",
            "index_destination": "relationship_edges",
        }


DRUG_HINTS = {
    "abacavir",
    "acetaminophen",
    "adalimumab",
    "albuterol",
    "amoxicillin",
    "apixaban",
    "aspirin",
    "azithromycin",
    "buprenorphine",
    "cefepime",
    "cephalexin",
    "ceftriaxone",
    "clindamycin",
    "clopidogrel",
    "corticosteroids",
    "daptomycin",
    "dexamethasone",
    "dextrose",
    "dihydroergotamine",
    "empagliflozin",
    "epinephrine",
    "ertapenem",
    "esomeprazole",
    "fentanyl",
    "furosemide",
    "heparin",
    "hydrocortisone",
    "hydroxychloroquine",
    "infliximab",
    "insulin",
    "labetalol",
    "levetiracetam",
    "leflunomide",
    "levothyroxine",
    "linezolid",
    "lisinopril",
    "lorazepam",
    "magnesium",
    "metformin",
    "methimazole",
    "methotrexate",
    "methylprednisolone",
    "metoprolol",
    "morphine",
    "mycophenolate",
    "naloxone",
    "nicardipine",
    "nitrofurantoin",
    "norepinephrine",
    "nivolumab",
    "omeprazole",
    "osimertinib",
    "oxytocin",
    "pantoprazole",
    "pembrolizumab",
    "pirfenidone",
    "platinum",
    "prednisone",
    "remdesivir",
    "rifampin",
    "risperidone",
    "semaglutide",
    "sertraline",
    "spironolactone",
    "sumatriptan",
    "tacrolimus",
    "tamoxifen",
    "tamsulosin",
    "tenecteplase",
    "thiamine",
    "ticagrelor",
    "vancomycin",
    "vitamin",
    "warfarin",
}

DRUG_SUFFIX_RE = re.compile(
    r"\b[a-z][a-z0-9-]*(?:cillin|cycline|floxacin|mab|nib|mycin|olol|pril|sartan|statin|vir|zepam|zumab)\b"
)
GENE_RE = re.compile(r"\b(?:[A-Z]{2,}[A-Z0-9-]*\*?[A-Z0-9-]*|CYP\d[A-Z]\d+|HLA-[A-Z0-9*:-]+)\b")

STOPWORDS = {
    "a",
    "after",
    "and",
    "as",
    "at",
    "because",
    "before",
    "by",
    "for",
    "from",
    "had",
    "has",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "patient",
    "patients",
    "search",
    "showed",
    "the",
    "to",
    "was",
    "were",
    "with",
}

GENERIC_FALSE_POSITIVE_PATTERNS = (
    "administrative",
    "artifact",
    "assessment",
    "chart review",
    "classification",
    "clinical trial",
    "cohort",
    "confirmed",
    "control",
    "disease",
    "finding",
    "follow up",
    "health evaluation",
    "history",
    "monitoring",
    "outcome",
    "patient",
    "placebo",
    "procedure",
    "review",
    "screening finding",
    "status",
    "study",
)

LABEL_SAB_PRIORITY = {
    "MTH": 0,
    "MSH": 1,
    "SNOMEDCT_US": 2,
    "NCI": 3,
    "RXNORM": 4,
    "LNC": 5,
    "MEDLINEPLUS": 6,
}

LABEL_TTY_PRIORITY = {
    "PT": 0,
    "PN": 1,
    "MH": 2,
    "HT": 3,
    "SY": 5,
}

TREATMENT_MARKERS = (
    "administered",
    "continued",
    "given for",
    "ordered",
    "prescribed",
    "recommended",
    "started",
    "therapy",
    "treated",
    "treatment",
    "used",
)

OUTCOME_MARKERS = (
    "improved",
    "relieved",
    "reduced",
    "response",
)

PHARMACOGENOMIC_MARKERS = (
    "activation",
    "allele",
    "cyp",
    "drug response",
    "genotype",
    "hla",
    "loss of function",
    "metabolizer",
    "pharmacogenomic",
)

COMMON_CONDITION_HINTS = {
    "acute kidney injury",
    "anemia",
    "asthma",
    "atrial fibrillation",
    "chronic kidney disease",
    "chronic obstructive pulmonary disease",
    "copd",
    "depression",
    "diabetes",
    "diabetes mellitus",
    "heart failure",
    "hypertension",
    "hypoglycemia",
    "infection",
    "migraine",
    "myocardial infarction",
    "pneumonia",
    "pulmonary embolism",
    "sepsis",
    "stroke",
    "urinary tract infection",
}

COMMON_LAB_TEST_HINTS = {
    "albumin",
    "blood culture",
    "blood glucose",
    "creatinine",
    "d dimer",
    "ferritin",
    "free thyroxine",
    "hemoglobin",
    "hemoglobin a1c",
    "inr",
    "lactate",
    "lipid panel",
    "potassium",
    "sodium",
    "thyroid stimulating hormone",
    "troponin",
    "urinalysis",
    "urine culture",
}

COMMON_PROCEDURE_HINTS = {
    "biopsy",
    "colonoscopy",
    "computed tomography",
    "ct angiography",
    "echocardiography",
    "electrocardiogram",
    "endoscopy",
    "mri",
    "radiograph",
    "ultrasound",
    "ultrasonography",
}

SAFETY_MARKERS = (
    "adverse",
    "allergy",
    "avoid",
    "contraindicat",
    "hypersensitivity",
    "reaction",
    "risk",
    "safety",
    "toxicity",
)

DIAGNOSTIC_MARKERS = (
    "biopsy",
    "confirmed",
    "demonstrated",
    "diagnosed",
    "evaluation",
    "found",
    "measurement",
    "monitor",
    "showed",
    "test",
    "workup",
)

TEMPORAL_MARKERS = (
    "after",
    "before",
    "followed",
    "later",
    "preceded",
    "prior",
    "then",
)


SOURCE_PROFILES: tuple[SourceAcquisitionProfile, ...] = (
    SourceAcquisitionProfile(
        source="active_label_supplement",
        label="Active label supplement",
        action="review_existing_cui_labels",
        rationale="Low-effort fix when expected existing CUIs are known but ranking misses common query phrasing.",
        trust=1.35,
        effort=0.8,
        default_applicability=0.35,
        keywords=("abbreviation", "search", "phrase", "term", "wording", "reviewed", "reported"),
    ),
    SourceAcquisitionProfile(
        source="extension_concepts",
        label="Reviewed local extension concepts",
        action="review_or_add_extension_concept",
        rationale="High-leverage lane for clinically important ideas that are missing or poorly represented by UMLS.",
        trust=1.2,
        effort=1.2,
        keywords=("new", "local", "specific", "poorly controlled", "right heart strain", "recurrent", "associated"),
    ),
    SourceAcquisitionProfile(
        source="relationship_edges",
        label="Relationship edge evidence",
        action="mine_or_curate_missing_associations",
        rationale="Adds explicit CUI-CUI association evidence when expected benchmark concept pairs are not available from existing relation indexes.",
        trust=1.2,
        effort=1.4,
        keywords=("associated", "caused", "complicated", "monitoring", "treated", "with"),
    ),
    SourceAcquisitionProfile(
        source="pubmed",
        label="PubMed literature",
        action="add_literature_topic",
        rationale="Primary open literature source for broad biomedical phrasing and co-mention evidence.",
        trust=1.0,
        effort=2.0,
        default_applicability=0.45,
        keywords=("review", "cohort", "study", "trial", "abstract", "manuscript", "research", "associated", "outcome"),
    ),
    SourceAcquisitionProfile(
        source="europepmc",
        label="Europe PMC literature",
        action="add_literature_topic",
        rationale="Complements PubMed and can provide high-rank literature hits for topic-specific gaps.",
        trust=0.95,
        effort=2.2,
        default_applicability=0.3,
        keywords=("review", "cohort", "study", "trial", "abstract", "manuscript", "research", "associated", "outcome"),
    ),
    SourceAcquisitionProfile(
        source="pmc_oa",
        label="PMC Open Access full text",
        action="add_oa_full_text_topic",
        rationale="Useful when short abstracts do not provide enough clinical or procedural context.",
        trust=1.0,
        effort=3.5,
        default_applicability=0.08,
        keywords=("guideline", "review", "management", "procedure", "workup", "diagnosis", "classification", "methods"),
    ),
    SourceAcquisitionProfile(
        source="dailymed",
        label="DailyMed",
        action="add_drug_label_subset",
        rationale="Best public source for drug labels, indications, contraindications, warnings, interactions, and adverse reactions.",
        trust=1.35,
        effort=1.5,
        keywords=(
            "adverse",
            "allergy",
            "contraindication",
            "dose",
            "drug",
            "interaction",
            "medication",
            "pharmacogenomic",
            "toxicity",
            "treatment",
        ),
        semantic_groups=("CHEM",),
    ),
    SourceAcquisitionProfile(
        source="fda",
        label="FDA public pages",
        action="add_drug_safety_reference_pages",
        rationale="Adds public drug-safety and product-safety vocabulary beyond individual SPL labels.",
        trust=1.15,
        effort=2.0,
        keywords=("adverse", "availability", "consumer", "drug safety", "device", "recall", "risk", "safety", "warning"),
        semantic_groups=("CHEM", "DEVI"),
    ),
    SourceAcquisitionProfile(
        source="clinicaltrials",
        label="ClinicalTrials.gov",
        action="add_trial_query_subset",
        rationale="Adds structured trial language for interventions, eligibility, outcomes, phases, and populations.",
        trust=0.9,
        effort=1.8,
        keywords=(
            "clinical trial",
            "controlled",
            "eligibility",
            "enrolled",
            "intervention",
            "outcome",
            "phase",
            "placebo",
            "progression free survival",
            "randomized",
            "trial",
        ),
    ),
    SourceAcquisitionProfile(
        source="ncbi_bookshelf_oa",
        label="NCBI Bookshelf / NLM LitArch OA",
        action="add_guideline_or_report_package",
        rationale="Closest current public source for long-form guideline/report-style clinical reasoning.",
        trust=1.25,
        effort=2.5,
        default_applicability=0.12,
        keywords=(
            "diagnosis",
            "differential",
            "evaluation",
            "guideline",
            "management",
            "monitoring",
            "recommended",
            "treatment",
            "workup",
        ),
    ),
    SourceAcquisitionProfile(
        source="medlineplus",
        label="MedlinePlus",
        action="expand_patient_language_topics",
        rationale="Useful for patient-facing symptoms, aliases, common tests, and general condition language.",
        trust=1.1,
        effort=1.2,
        default_applicability=0.1,
        keywords=("also called", "child", "denied", "exam", "fever", "headache", "pain", "patient", "symptom", "wheezing"),
        semantic_groups=("DISO", "PROC", "OBS"),
    ),
    SourceAcquisitionProfile(
        source="medlineplus_genetics",
        label="MedlinePlus Genetics",
        action="expand_genetics_topics",
        rationale="Adds genetics, rare-disease, inheritance, chromosome, gene, and phenotype descriptions.",
        trust=1.15,
        effort=1.6,
        keywords=("allele", "brca", "chromosome", "cyp", "egfr", "gene", "genetic", "genomic", "hla", "mutation", "variant"),
        semantic_groups=("GENE",),
    ),
    SourceAcquisitionProfile(
        source="nci",
        label="NCI public pages",
        action="add_oncology_reference_pages",
        rationale="Public oncology source for diagnosis, staging, risk, treatment, biopsy, imaging, and workup language.",
        trust=1.2,
        effort=1.8,
        keywords=(
            "brain metastases",
            "cancer",
            "carcinoma",
            "chemotherapy",
            "egfr",
            "leukemia",
            "lymphoma",
            "metastatic",
            "neoplasm",
            "oncology",
            "radiation",
            "staging",
            "tumor",
        ),
    ),
    SourceAcquisitionProfile(
        source="cdc",
        label="CDC public pages",
        action="add_public_health_reference_pages",
        rationale="Public source for infection, prevention, outbreak, vaccine, testing, sepsis, and public-health vocabulary.",
        trust=1.1,
        effort=1.8,
        keywords=(
            "bacteria",
            "covid",
            "cdc",
            "infection",
            "influenza",
            "mrsa",
            "outbreak",
            "pneumonia",
            "prevention",
            "sepsis",
            "septic",
            "vaccine",
            "virus",
        ),
    ),
    SourceAcquisitionProfile(
        source="niddk",
        label="NIDDK public pages",
        action="add_endocrine_kidney_gi_reference_pages",
        rationale="Public source for diabetes, kidney, digestive, endocrine, obesity, and nutrition language.",
        trust=1.15,
        effort=1.8,
        keywords=(
            "albuminuria",
            "creatinine",
            "diabetes",
            "digestive",
            "egfr",
            "glucose",
            "kidney",
            "nutrition",
            "obesity",
            "pancreatitis",
            "renal",
        ),
    ),
    SourceAcquisitionProfile(
        source="hpo",
        label="HPO annotation/xref relation pack",
        action="review_phenotype_relation_pack",
        rationale="Adds phenotype and disease/gene phenotype relations when reuse terms permit.",
        trust=1.1,
        effort=3.0,
        keywords=("congenital", "gene", "genetic", "inheritance", "phenotype", "rare", "syndrome"),
        semantic_groups=("DISO", "GENE"),
    ),
    SourceAcquisitionProfile(
        source="mondo",
        label="MONDO xref/hierarchy relation pack",
        action="review_disease_xref_hierarchy_pack",
        rationale="Adds disease hierarchy and xref semantics as first-class relation/code-crosswalk edges.",
        trust=1.05,
        effort=2.8,
        keywords=("disease", "disorder", "neoplasm", "rare", "syndrome"),
        semantic_groups=("DISO",),
    ),
)


def split_values(value: str | None) -> set[str]:
    text = str(value or "").strip()
    if not text:
        return set()
    normalized = text.replace(",", "|").replace(";", "|")
    values = set()
    for raw in normalized.split("|"):
        item = raw.strip()
        if not item:
            continue
        if "=" in item:
            item = item.split("=", 1)[0].strip()
        if item:
            values.add(item.upper())
    return values


def pair_key(left: str, right: str) -> tuple[str, str]:
    left = left.strip().upper()
    right = right.strip().upper()
    return tuple(sorted((left, right)))  # type: ignore[return-value]


def pair_text(left: str, right: str) -> str:
    first, second = pair_key(left, right)
    return f"{first}-{second}"


def pair_parts(pair: str) -> tuple[str, str]:
    left, right = str(pair or "").split("-", 1)
    return pair_key(left, right)


def split_pair_values(value: str | None) -> set[str]:
    pairs = set()
    for raw in str(value or "").replace(",", "|").replace(";", "|").split("|"):
        item = raw.strip()
        if not item or "-" not in item:
            continue
        left, right = item.split("-", 1)
        left = left.strip().upper()
        right = right.strip().upper()
        if left and right and left != right:
            pairs.add(pair_text(left, right))
    return pairs


def _sqlite_table_names(path: Path) -> set[str]:
    conn = sqlite3.connect(str(path))
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        return {str(row[0]) for row in rows}
    finally:
        conn.close()


def load_relation_pairs(paths: Iterable[str | Path]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for raw_path in paths:
        path = Path(raw_path).expanduser()
        if not path.exists():
            continue
        tables = _sqlite_table_names(path)
        conn = sqlite3.connect(str(path))
        try:
            for table in ("related_concepts", "research_relations", "relationship_edges"):
                if table not in tables:
                    continue
                for source_cui, target_cui in conn.execute(
                    f"SELECT source_cui, target_cui FROM {table}"
                ):
                    source = str(source_cui or "").strip().upper()
                    target = str(target_cui or "").strip().upper()
                    if source and target and source != target:
                        pairs.add(pair_key(source, target))
        finally:
            conn.close()
    return pairs


def _sqlite_column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})")
    except sqlite3.OperationalError:
        return set()
    return {str(row[1]) for row in rows}


def _chunked(values: Iterable[str], size: int = 400) -> Iterable[list[str]]:
    batch = []
    for value in sorted({str(item).strip().upper() for item in values if str(item).strip()}):
        batch.append(value)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _label_priority(
    label: str,
    *,
    sab: str = "",
    tty: str = "",
    ispref: str = "",
    suppress: str = "",
    path_rank: int = 0,
) -> tuple[int, int, int, int, int, int, str]:
    key = normalized_key(label)
    token_count = len(key.split()) if key else 999
    return (
        0 if suppress.upper() in {"", "N"} else 1,
        0 if ispref.upper() == "Y" else 1,
        LABEL_SAB_PRIORITY.get(sab.upper(), 50),
        LABEL_TTY_PRIORITY.get(tty.upper(), 50),
        path_rank,
        token_count,
        key,
    )


def load_cui_labels(
    paths: Iterable[str | Path],
    cuis: Iterable[str],
) -> dict[str, str]:
    wanted = {str(cui).strip().upper() for cui in cuis if str(cui).strip()}
    if not wanted:
        return {}
    best: dict[str, tuple[tuple[int, int, int, int, int, int, str], str]] = {}
    for path_rank, raw_path in enumerate(paths):
        path = Path(raw_path).expanduser()
        if not path.exists():
            continue
        conn = sqlite3.connect(str(path))
        try:
            tables = _sqlite_table_names(path)
            for table in ("preferred_terms", "labels", "code_mappings"):
                if table not in tables:
                    continue
                columns = _sqlite_column_names(conn, table)
                if "cui" not in columns or "label" not in columns:
                    continue
                optional = [
                    column
                    for column in ("sab", "tty", "ispref", "suppress")
                    if column in columns
                ]
                select_columns = ["cui", "label", *optional]
                for chunk in _chunked(wanted):
                    placeholders = ",".join("?" for _ in chunk)
                    rows = conn.execute(
                        f"SELECT {', '.join(select_columns)} FROM {table} WHERE cui IN ({placeholders})",
                        chunk,
                    )
                    for row in rows:
                        cui = str(row[0] or "").strip().upper()
                        label = str(row[1] or "").strip()
                        if not cui or not label or normalized_key(label) == normalized_key(cui):
                            continue
                        values = {
                            column: str(row[index + 2] or "")
                            for index, column in enumerate(optional)
                        }
                        priority = _label_priority(
                            label,
                            sab=values.get("sab", ""),
                            tty=values.get("tty", ""),
                            ispref=values.get("ispref", "Y" if table == "preferred_terms" else ""),
                            suppress=values.get("suppress", ""),
                            path_rank=path_rank,
                        )
                        current = best.get(cui)
                        if current is None or priority < current[0]:
                            best[cui] = (priority, label)
        finally:
            conn.close()
    return {cui: label for cui, (_priority, label) in best.items()}


def load_cui_semantic_groups(
    paths: Iterable[str | Path],
    cuis: Iterable[str],
) -> dict[str, str]:
    wanted = {str(cui).strip().upper() for cui in cuis if str(cui).strip()}
    if not wanted:
        return {}
    grouped_types: dict[str, list[dict[str, str]]] = {}
    for raw_path in paths:
        path = Path(raw_path).expanduser()
        if not path.exists():
            continue
        conn = sqlite3.connect(str(path))
        try:
            if "semantic_types" not in _sqlite_table_names(path):
                continue
            for chunk in _chunked(wanted):
                placeholders = ",".join("?" for _ in chunk)
                rows = conn.execute(
                    f"""
                    SELECT cui, tui, stn, sty, atui
                    FROM semantic_types
                    WHERE cui IN ({placeholders})
                    """,
                    chunk,
                )
                for row in rows:
                    cui = str(row[0] or "").strip().upper()
                    grouped_types.setdefault(cui, []).append(
                        {
                            "tui": str(row[1] or ""),
                            "stn": str(row[2] or ""),
                            "name": str(row[3] or ""),
                            "sty": str(row[3] or ""),
                            "atui": str(row[4] or ""),
                        }
                    )
        finally:
            conn.close()
    return {
        cui: semantic_group_from_types(types) or "OTHER"
        for cui, types in grouped_types.items()
    }


def missing_cuis(row: dict[str, str]) -> set[str]:
    values = split_values(row.get("missing_at_10", ""))
    if values:
        return values
    values = split_values(row.get("missing_at_20", ""))
    if values:
        return values
    return split_values(row.get("missing_at_60", ""))


def expected_cuis(row: dict[str, str]) -> set[str]:
    return split_values(row.get("expected_cuis", ""))


def unavailable_association_pairs(
    row: dict[str, str],
    *,
    available_relation_pairs: set[tuple[str, str]] | None = None,
    max_pairs: int = 12,
) -> set[str]:
    expected = sorted(expected_cuis(row))
    if len(expected) < 2:
        return set()
    missing = missing_cuis(row)
    scored: list[tuple[int, str]] = []
    for left, right in itertools.combinations(expected, 2):
        key = pair_key(left, right)
        if available_relation_pairs is not None and key in available_relation_pairs:
            continue
        priority = 0 if (left in missing or right in missing) else 1
        scored.append((priority, pair_text(left, right)))
    return {
        pair
        for _priority, pair in sorted(scored, key=lambda item: (item[0], item[1]))[:max_pairs]
    }


def _int(value: str | None) -> int:
    try:
        return int(str(value or "").strip())
    except ValueError:
        return 0


def _float(value: str | None) -> float:
    try:
        return float(str(value or "").strip())
    except ValueError:
        return 0.0


def read_quality_summary_tsv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).expanduser().open("r", encoding="utf-8", newline="") as handle:
        return [
            dict(row)
            for row in csv.DictReader(
                (line for line in handle if line.strip() and not line.lstrip().startswith("#")),
                delimiter="\t",
            )
        ]


def read_query_spec_tsv(path: str | Path) -> dict[str, dict[str, set[str]]]:
    with Path(path).expanduser().open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(
            (line for line in handle if line.strip() and not line.lstrip().startswith("#")),
            delimiter="\t",
        )
        specs: dict[str, dict[str, set[str]]] = {}
        for row in reader:
            query_id = str(row.get("id") or "").strip()
            if not query_id:
                continue
            specs[query_id] = {
                "expected_cuis": split_values(row.get("expected_cuis")),
                "disallowed_cuis": split_values(
                    row.get("disallowed_cuis")
                    or row.get("forbidden_cuis")
                    or row.get("negative_cuis")
                ),
            }
        return specs


def read_prevalence_prior_tsv(path: str | Path) -> dict[str, float]:
    priors: dict[str, float] = {}
    with Path(path).expanduser().open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(
            (line for line in handle if line.strip() and not line.lstrip().startswith("#")),
            delimiter="\t",
        )
        for row in reader:
            cui = str(row.get("cui") or row.get("CUI") or "").strip().upper()
            if not cui:
                continue
            value = (
                row.get("prevalence_weight")
                or row.get("utility_weight")
                or row.get("commonness")
                or row.get("priority")
                or row.get("weight")
                or ""
            )
            try:
                score = float(str(value).strip())
            except ValueError:
                score = 0.0
            if score <= 0:
                continue
            priors[cui] = max(priors.get(cui, 0.0), min(score, 3.0))
    return priors


def attach_query_specs(
    rows: Iterable[dict[str, str]],
    specs: dict[str, dict[str, set[str]]],
) -> list[dict[str, str]]:
    annotated = []
    for row in rows:
        item = dict(row)
        query_id = str(item.get("id") or "").strip()
        spec = specs.get(query_id)
        if spec:
            if spec.get("expected_cuis") and not item.get("expected_cuis"):
                item["expected_cuis"] = "|".join(sorted(spec["expected_cuis"]))
            if spec.get("disallowed_cuis"):
                existing = split_values(item.get("configured_disallowed_cuis", ""))
                existing.update(spec["disallowed_cuis"])
                item["configured_disallowed_cuis"] = "|".join(sorted(existing))
        annotated.append(item)
    return annotated


def parse_accepted_alternative_hits(value: str | None) -> set[str]:
    accepted = set()
    normalized = str(value or "").replace(",", "|").replace(";", "|")
    for raw in normalized.split("|"):
        item = raw.strip()
        if not item or "=" not in item:
            continue
        accepted.add(item.split("=", 1)[1].strip().upper())
    return {value for value in accepted if value}


@dataclass(frozen=True)
class CompactHit:
    rank: int
    cui: str
    name: str
    semantic_group: str
    score: float


COMPACT_HIT_RE = re.compile(
    r"(?P<rank>\d+):(?P<cui>[A-Z0-9]+)\s+"
    r"(?P<name>.*?)\s+\[(?P<group>[A-Z]+|OTHER)\s+(?P<score>-?\d+(?:\.\d+)?)\]"
)


def parse_compact_hits(value: str | None) -> list[CompactHit]:
    hits = []
    for match in COMPACT_HIT_RE.finditer(str(value or "")):
        hits.append(
            CompactHit(
                rank=int(match.group("rank")),
                cui=match.group("cui").upper(),
                name=match.group("name").strip(),
                semantic_group=match.group("group").upper(),
                score=float(match.group("score")),
            )
        )
    return hits


def collect_cuis_from_rows(rows: Iterable[dict[str, str]]) -> set[str]:
    cuis: set[str] = set()
    for row in rows:
        for field in (
            "expected_cuis",
            "missing_at_10",
            "missing_at_20",
            "missing_at_60",
            "disallowed_at_10",
            "disallowed_at_20",
            "candidate_disallowed_cuis",
            "configured_disallowed_cuis",
        ):
            cuis.update(split_values(row.get(field, "")))
        for pair in split_pair_values(row.get("unavailable_association_pairs", "")):
            cuis.update(pair_parts(pair))
        top_cui = str(row.get("top_cui") or "").strip().upper()
        if top_cui:
            cuis.add(top_cui)
        for hit in parse_compact_hits(row.get("hits_top_10", "")):
            cuis.add(hit.cui)
    return cuis


def row_hit_label_map(row: dict[str, str]) -> dict[str, str]:
    labels = {}
    top_cui = str(row.get("top_cui") or "").strip().upper()
    top_name = str(row.get("top_name") or "").strip()
    if top_cui and top_name:
        labels[top_cui] = top_name
    for hit in parse_compact_hits(row.get("hits_top_10", "")):
        if hit.cui and hit.name and hit.cui not in labels:
            labels[hit.cui] = hit.name
    return labels


def labels_from_rows(rows: Iterable[dict[str, str]]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for row in rows:
        for cui, label in row_hit_label_map(row).items():
            labels.setdefault(cui, label)
    return labels


def row_hit_group_map(row: dict[str, str]) -> dict[str, str]:
    groups = {}
    top_cui = str(row.get("top_cui") or "").strip().upper()
    top_group = str(row.get("top_semantic_group") or "").strip().upper()
    if top_cui and top_group:
        groups[top_cui] = top_group
    for hit in parse_compact_hits(row.get("hits_top_10", "")):
        if hit.cui and hit.semantic_group and hit.cui not in groups:
            groups[hit.cui] = hit.semantic_group
    return groups


def labels_for_row(
    row: dict[str, str],
    *,
    cui_label_map: dict[str, str],
) -> dict[str, str]:
    labels = row_hit_label_map(row)
    labels.update({cui: label for cui, label in cui_label_map.items() if label})
    return labels


def name_has_generic_false_positive_shape(name: str, query: str) -> bool:
    name_key = normalized_key(name)
    query_key = normalized_key(query)
    for pattern in GENERIC_FALSE_POSITIVE_PATTERNS:
        pattern_key = normalized_key(pattern)
        if pattern_key and pattern_key in name_key and pattern_key not in query_key:
            return True
    if name_key in {"disease", "procedure", "patient", "finding", "status"}:
        return True
    return False


def infer_candidate_disallowed_cuis(
    row: dict[str, str],
    *,
    rank_limit: int = 10,
) -> set[str]:
    expected = split_values(row.get("expected_cuis", ""))
    accepted = parse_accepted_alternative_hits(row.get("accepted_alternatives_at_10", ""))
    known_disallowed = split_values(row.get("configured_disallowed_cuis", ""))
    known_disallowed.update(split_values(row.get("disallowed_at_10", "")))
    known_disallowed.update(split_values(row.get("disallowed_at_20", "")))
    protected = expected | accepted | missing_cuis(row)
    query = str(row.get("query") or "")
    verdict = str(row.get("verdict") or "").strip().lower()
    coverage_10 = _float(row.get("coverage_at_10"))
    has_measured_problem = verdict in {"mixed", "poor"} or coverage_10 < 1.0 or bool(missing_cuis(row))
    inferred = set()
    for hit in parse_compact_hits(row.get("hits_top_10", "")):
        if hit.rank > rank_limit:
            continue
        if hit.cui in protected or hit.cui in known_disallowed:
            continue
        if name_has_generic_false_positive_shape(hit.name, query):
            inferred.add(hit.cui)
            continue
        if has_measured_problem and hit.rank <= 3 and expected:
            inferred.add(hit.cui)
    return inferred


def failure_weight(row: dict[str, str]) -> float:
    expected = _int(row.get("expected_count"))
    found_10 = _int(row.get("found_at_10"))
    found_20 = _int(row.get("found_at_20"))
    missing_10 = split_values(row.get("missing_at_10", ""))
    missing_20 = split_values(row.get("missing_at_20", ""))
    missing_60 = split_values(row.get("missing_at_60", ""))
    disallowed_10 = split_values(row.get("disallowed_at_10", ""))
    disallowed_20 = split_values(row.get("disallowed_at_20", ""))
    candidate_disallowed = split_values(row.get("candidate_disallowed_cuis", ""))
    association_pairs = split_pair_values(row.get("unavailable_association_pairs", ""))
    verdict = str(row.get("verdict") or "").strip().lower()

    weight = 0.0
    weight += 3.0 * len(missing_10)
    weight += 1.5 * len(missing_20)
    weight += 0.5 * len(missing_60)
    weight += 2.0 * len(disallowed_10)
    weight += 0.8 * len(disallowed_20 - disallowed_10)
    weight += 0.4 * len(candidate_disallowed)
    weight += 0.75 * len(association_pairs)
    if expected:
        weight += max(0, expected - found_10) * 1.2
        weight += max(0, expected - found_20) * 0.4
        weight += max(0.0, 1.0 - _float(row.get("coverage_at_10"))) * expected
    if verdict == "poor":
        weight += 4.0
    elif verdict == "mixed":
        weight += 1.2
    rank = _int(row.get("first_expected_rank"))
    if rank > 1:
        weight += min(2.0, (rank - 1) * 0.15)
    return weight


def _tokens(text: str) -> set[str]:
    return set(normalized_key(text).split())


def _keyword_matches(keywords: Iterable[str], text: str, tokens: set[str]) -> list[str]:
    normalized = normalized_key(text)
    matches = []
    for keyword in keywords:
        key = normalized_key(keyword)
        if not key:
            continue
        if " " in key:
            if key in normalized:
                matches.append(keyword)
        elif key in tokens:
            matches.append(keyword)
    return matches


def profile_applicability(profile: SourceAcquisitionProfile, row: dict[str, str]) -> float:
    if profile.source == "active_label_supplement" and not missing_cuis(row):
        return 0.0
    if profile.source == "extension_concepts" and not any(cui.startswith("NEW") for cui in missing_cuis(row)):
        return 0.0
    text = " ".join(
        str(row.get(field) or "")
        for field in ("query", "rationale", "top_name", "top_semantic_types", "hits_top_10")
    )
    tokens = _tokens(text)
    matches = _keyword_matches(profile.keywords, text, tokens)
    score = profile.default_applicability + len(matches) * 0.35
    semantic_group = str(row.get("top_semantic_group") or "").strip().upper()
    if semantic_group and semantic_group in profile.semantic_groups:
        score += 0.45
    if profile.source == "dailymed" and extract_drug_terms(str(row.get("query") or "")):
        score += 0.9
    if profile.source == "medlineplus_genetics" and extract_gene_terms(str(row.get("query") or "")):
        score += 0.8
    if profile.source == "extension_concepts" and any(cui.startswith("NEW") for cui in missing_cuis(row)):
        score += 1.2
    if profile.source == "active_label_supplement" and missing_cuis(row):
        score += 0.45
    association_count = len(split_pair_values(row.get("unavailable_association_pairs", "")))
    if association_count:
        if profile.source == "relationship_edges":
            score += 1.25
        elif profile.source in {
            "pubmed",
            "europepmc",
            "pmc_oa",
            "clinicaltrials",
            "ncbi_bookshelf_oa",
        }:
            score += min(0.8, 0.2 + association_count * 0.08)
        elif matches or score > profile.default_applicability + 0.1:
            score += min(0.6, 0.12 + association_count * 0.05)
    return min(score, 2.75)


def extract_drug_terms(text: str) -> list[str]:
    normalized = normalized_key(text)
    tokens = normalized.split()
    found = [token for token in tokens if token in DRUG_HINTS]
    found.extend(match.group(0) for match in DRUG_SUFFIX_RE.finditer(normalized))
    unique = []
    seen = set()
    for value in found:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(value)
    return unique[:8]


def extract_gene_terms(text: str) -> list[str]:
    found = [match.group(0) for match in GENE_RE.finditer(text)]
    unique = []
    seen = set()
    for value in found:
        key = value.upper()
        if key in seen or key in {"CT", "MRI", "ICU", "ED", "EHR"}:
            continue
        seen.add(key)
        unique.append(value)
    return unique[:8]


def _has_any(text: str, markers: Iterable[str]) -> bool:
    normalized = normalized_key(text)
    return any(normalized_key(marker) in normalized for marker in markers)


def _label_query_positions(label: str, query: str) -> list[int]:
    query_tokens = normalized_key(query).split()
    label_tokens = [
        token
        for token in normalized_key(label).split()
        if len(token) > 2 and token not in STOPWORDS
    ]
    if not query_tokens or not label_tokens:
        return []
    positions = []
    if len(label_tokens) > 1:
        width = len(label_tokens)
        for index in range(0, len(query_tokens) - width + 1):
            window = query_tokens[index : index + width]
            matched = sum(1 for token in label_tokens if token in window)
            if matched >= max(1, min(width, 3)):
                positions.append(index)
    if len(label_tokens) == 1:
        first_token = label_tokens[0]
        positions.extend(index for index, token in enumerate(query_tokens) if token == first_token)
    return sorted(set(positions))


def pair_text_proximity_score(left_label: str, right_label: str, query: str) -> float:
    left_positions = _label_query_positions(left_label, query)
    right_positions = _label_query_positions(right_label, query)
    if not left_positions or not right_positions:
        return 0.0
    distance = min(abs(left - right) for left in left_positions for right in right_positions)
    if distance <= 8:
        return 1.0
    if distance <= 18:
        return 0.75
    if distance <= 35:
        return 0.45
    return 0.25


def label_near_marker(label: str, query: str, markers: Iterable[str], *, window: int = 10) -> bool:
    label_positions = _label_query_positions(label, query)
    if not label_positions:
        return False
    query_tokens = normalized_key(query).split()
    marker_positions = []
    for marker in markers:
        marker_tokens = normalized_key(marker).split()
        if not marker_tokens:
            continue
        width = len(marker_tokens)
        for index in range(0, len(query_tokens) - width + 1):
            if query_tokens[index : index + width] == marker_tokens:
                marker_positions.append(index)
    if not marker_positions:
        return False
    return min(abs(left - right) for left in label_positions for right in marker_positions) <= window


def commonness_score(
    cui: str,
    *,
    label: str,
    group: str,
    query: str,
    prevalence_prior_map: dict[str, float] | None = None,
) -> float:
    cui = cui.strip().upper()
    if prevalence_prior_map and cui in prevalence_prior_map:
        return min(max(float(prevalence_prior_map[cui]), 0.0), 3.0)
    text = label if label and normalized_key(label) != normalized_key(cui) else query
    normalized = normalized_key(text)
    score = 0.0
    if group == "CHEM" and (extract_drug_terms(label) or extract_drug_terms(query)):
        score = max(score, 0.8)
    if group == "DISO" and _keyword_matches(COMMON_CONDITION_HINTS, normalized, set(normalized.split())):
        score = max(score, 0.9)
    if group in {"OBS", "PROC"} and _keyword_matches(COMMON_LAB_TEST_HINTS, normalized, set(normalized.split())):
        score = max(score, 0.85)
    if group == "PROC" and _keyword_matches(COMMON_PROCEDURE_HINTS, normalized, set(normalized.split())):
        score = max(score, 0.75)
    if group in {"DISO", "CHEM", "OBS", "PROC"}:
        score = max(score, 0.35)
    if any(marker in normalized for marker in ("rare", "exon", "allele", "hla", "brca", "cyp")):
        score *= 0.75
    return min(score, 1.0)


def prevalence_multiplier(prevalence_score: float) -> float:
    return 1.0 + min(max(prevalence_score, 0.0), 3.0) * 0.22


def row_prevalence_score(
    row: dict[str, str],
    *,
    cui_label_map: dict[str, str] | None = None,
    semantic_group_map: dict[str, str] | None = None,
    prevalence_prior_map: dict[str, float] | None = None,
) -> float:
    labels = labels_for_row(row, cui_label_map=cui_label_map or {})
    groups = semantic_group_map or {}
    cuis = expected_cuis(row) | missing_cuis(row)
    for pair in split_pair_values(row.get("unavailable_association_pairs", "")):
        cuis.update(pair_parts(pair))
    if not cuis:
        return 0.0
    missing = missing_cuis(row)
    scores = []
    for cui in sorted(cuis):
        label = labels.get(cui, cui)
        group = group_for_cui(cui, row, label=label, semantic_group_map=groups)
        score = commonness_score(
            cui,
            label=label,
            group=group,
            query=str(row.get("query") or ""),
            prevalence_prior_map=prevalence_prior_map,
        )
        if cui in missing:
            score *= 1.15
        scores.append(score)
    if not scores:
        return 0.0
    return min(max(scores) + (sum(scores) / len(scores)) * 0.35, 3.0)


def infer_semantic_group_from_label(cui: str, label: str, query: str = "") -> str:
    text = " ".join(part for part in (label, query) if part)
    key = normalized_key(text)
    label_key = normalized_key(label)
    if cui.startswith("NEW"):
        return "PHEN"
    if extract_gene_terms(label or query) or any(
        marker in key for marker in ("allele", "brca", "chromosome", "cyp", "egfr", "gene", "genomic", "hla", "mutation", "variant")
    ):
        return "GENE"
    if extract_drug_terms(label) or any(
        marker in label_key
        for marker in (
            "antibiotic",
            "antibody",
            "chemotherapy",
            "corticosteroid",
            "drug",
            "insulin",
            "medication",
            "pharmaceutical",
            "therapy agent",
            "vitamin",
        )
    ):
        return "CHEM"
    if any(
        marker in label_key
        for marker in (
            "catheter",
            "device",
            "lead",
            "pacemaker",
            "shunt",
            "stent",
            "walker",
        )
    ):
        return "DEVI"
    if any(
        marker in label_key
        for marker in (
            "angiography",
            "appendectomy",
            "arthroplasty",
            "biopsy",
            "catheterization",
            "colonoscopy",
            "computed tomography",
            "culture",
            "echocardiography",
            "endoscopy",
            "imaging",
            "mri",
            "puncture",
            "radiograph",
            "scan",
            "surgery",
            "test",
            "therapy",
            "thrombectomy",
            "transfusion",
            "ultrasound",
            "ultrasonography",
        )
    ):
        return "PROC"
    if any(
        marker in label_key
        for marker in (
            "albumin",
            "bilirubin",
            "blood glucose",
            "creatinine",
            "d dimer",
            "ferritin",
            "hemoglobin",
            "inr",
            "measurement",
            "potassium",
            "proteinuria",
            "ratio",
            "sodium",
            "troponin",
        )
    ):
        return "OBS"
    if any(
        marker in label_key
        for marker in (
            "drug response",
            "metabolizer",
            "response",
            "status",
        )
    ):
        return "PHEN"
    if any(
        marker in label_key
        for marker in (
            "bacteria",
            "clostridioides",
            "enterococcus",
            "escherichia",
            "influenza",
            "rhinovirus",
            "staphylococcus",
            "virus",
        )
    ):
        return "LIVB"
    if any(
        marker in label_key
        for marker in (
            "artery",
            "bone",
            "brain",
            "kidney",
            "liver",
            "lung",
            "nerve",
            "vein",
        )
    ):
        return "ANAT"
    if any(
        marker in label_key
        for marker in (
            "drug response",
            "metabolizer",
            "response",
            "status",
            "arthritis",
            "cancer",
            "carcinoma",
            "deficit",
            "diabetes",
            "disease",
            "embolism",
            "failure",
            "finding",
            "infection",
            "infarct",
            "metastases",
            "neoplasm",
            "pneumonia",
            "sepsis",
            "shock",
            "syndrome",
            "thrombosis",
            "ulcer",
        )
    ):
        return "DISO"
    return "OTHER"


def group_for_cui(
    cui: str,
    row: dict[str, str],
    *,
    label: str,
    semantic_group_map: dict[str, str],
) -> str:
    cui = cui.strip().upper()
    if semantic_group_map.get(cui):
        return semantic_group_map[cui]
    row_groups = row_hit_group_map(row)
    if row_groups.get(cui):
        return row_groups[cui]
    return infer_semantic_group_from_label(cui, label, str(row.get("query") or ""))


def directed_pair_for_groups(
    left: str,
    right: str,
    groups: dict[str, str],
    *,
    subject_groups: set[str],
    object_groups: set[str],
) -> tuple[str, str] | None:
    left_group = groups.get(left, "")
    right_group = groups.get(right, "")
    if left_group in subject_groups and right_group in object_groups:
        return left, right
    if right_group in subject_groups and left_group in object_groups:
        return right, left
    return None


def infer_association_relationship(
    left: str,
    right: str,
    row: dict[str, str],
    *,
    cui_label_map: dict[str, str],
    semantic_group_map: dict[str, str],
) -> AssociationInference:
    query = str(row.get("query") or "")
    labels = labels_for_row(row, cui_label_map=cui_label_map)
    label_by_cui = {
        left: labels.get(left, left),
        right: labels.get(right, right),
    }
    groups = {
        left: group_for_cui(left, row, label=label_by_cui[left], semantic_group_map=semantic_group_map),
        right: group_for_cui(right, row, label=label_by_cui[right], semantic_group_map=semantic_group_map),
    }
    treatment = _has_any(query, TREATMENT_MARKERS)
    outcome = _has_any(query, OUTCOME_MARKERS)
    safety = _has_any(query, SAFETY_MARKERS)
    diagnostic = _has_any(query, DIAGNOSTIC_MARKERS)
    temporal = _has_any(query, TEMPORAL_MARKERS)
    pharmacogenomic = _has_any(query, PHARMACOGENOMIC_MARKERS)

    directed = directed_pair_for_groups(
        left,
        right,
        groups,
        subject_groups={"CHEM"},
        object_groups={"DISO", "PHEN", "LIVB"},
    )
    if directed:
        source, target = directed
        source_label = label_by_cui.get(source, source)
        source_treatment = label_near_marker(source_label, query, TREATMENT_MARKERS, window=10)
        source_safety = label_near_marker(source_label, query, SAFETY_MARKERS, window=10)
        if pharmacogenomic:
            return AssociationInference(
                source,
                target,
                "associated_with",
                "drug_response",
                "bidirectional",
                0.76,
                "Pharmacogenomic or drug-response wording; prioritize response/activation evidence, not a treatment edge.",
            )
        if (source_safety or safety) and not source_treatment:
            return AssociationInference(
                source,
                target,
                "causes",
                "adverse_effect",
                "subject_to_object",
                0.72,
                "Drug/chemical plus safety wording; review as adverse-effect or contraindication evidence.",
            )
        if treatment and (source_treatment or not safety):
            return AssociationInference(
                source,
                target,
                "treats",
                "treatment",
                "subject_to_object",
                0.82,
                "Drug/chemical paired with treatment wording; prioritize indication or therapy evidence.",
            )
        if outcome:
            return AssociationInference(
                source,
                target,
                "associated_with",
                "outcome_association",
                "bidirectional",
                0.64,
                "Drug/chemical paired with outcome wording; review before treating it as an indication edge.",
            )
        return AssociationInference(
            source,
            target,
            "associated_with",
            "therapeutic_association",
            "bidirectional",
            0.58,
            "Drug/chemical paired with disorder or phenotype but relation wording is indirect.",
        )

    directed = directed_pair_for_groups(
        left,
        right,
        groups,
        subject_groups={"GENE"},
        object_groups={"DISO", "PHEN", "CHEM"},
    )
    if directed:
        source, target = directed
        if pharmacogenomic and "CHEM" in {groups.get(source, ""), groups.get(target, "")}:
            return AssociationInference(
                source,
                target,
                "associated_with",
                "drug_response",
                "bidirectional",
                0.78,
                "Gene/variant and drug-response wording; prioritize pharmacogenomic response evidence.",
            )
        return AssociationInference(
            source,
            target,
            "associated_with",
            "genetic_association",
            "bidirectional",
            0.74,
            "Gene or variant paired with disease/drug-response context; prioritize genetics association evidence.",
        )

    directed = directed_pair_for_groups(
        left,
        right,
        groups,
        subject_groups={"PROC", "OBS"},
        object_groups={"DISO", "PHEN", "LIVB", "ANAT"},
    )
    if directed:
        source, target = directed
        relation_group = "procedure_or_test"
        relationship_type = "diagnostic_evidence" if diagnostic else "associated_with"
        return AssociationInference(
            source,
            target,
            relationship_type,
            relation_group,
            "subject_to_object",
            0.69 if diagnostic else 0.58,
            "Procedure, test, or observation paired with clinical condition; prioritize diagnostic/workup evidence.",
        )

    if temporal:
        return AssociationInference(
            left,
            right,
            "precedes",
            "temporal_analysis",
            "temporal_precedes",
            0.56,
            "Temporal wording is present, but direction requires evidence review.",
        )

    if {"DISO", "PHEN"} & set(groups.values()) and len(set(groups.values())) > 1:
        return AssociationInference(
            left,
            right,
            "associated_with",
            "clinical_association",
            "bidirectional",
            0.54,
            "Clinically complementary concepts co-occur in an expected benchmark paragraph.",
        )

    return AssociationInference(
        left,
        right,
        "associated_with",
        "benchmark_expected_pair",
        "bidirectional",
        0.45,
        "Expected benchmark concepts co-occur, but relation type needs manual evidence review.",
    )


def association_evidence_sources(
    row: dict[str, str],
    *,
    groups: tuple[str, str],
    relationship_type: str,
    labels: tuple[str, str],
) -> list[str]:
    query = str(row.get("query") or "")
    text = " ".join([query, *labels])
    normalized = normalized_key(text)
    source_scores: dict[str, float] = {}

    def add(source: str, score: float) -> None:
        source_scores[source] = max(source_scores.get(source, 0.0), score)

    group_set = set(groups)
    if _has_any(text, PHARMACOGENOMIC_MARKERS):
        add("medlineplus_genetics", 0.92)
        add("pubmed", 0.78)
        if "CHEM" in group_set:
            add("dailymed", 0.82)
    if "CHEM" in group_set:
        add("dailymed", 1.0 if relationship_type in {"treats", "causes", "contraindicated_with"} else 0.75)
        if _has_any(text, SAFETY_MARKERS):
            add("fda", 0.78)
        if "trial" in normalized or "randomized" in normalized or "progression free survival" in normalized:
            add("clinicaltrials", 0.76)
        add("pubmed", 0.62)
    if "GENE" in group_set:
        add("medlineplus_genetics", 0.92)
        add("pubmed", 0.7)
        if any(marker in normalized for marker in ("cancer", "carcinoma", "oncology", "tumor", "neoplasm", "egfr", "brca")):
            add("nci", 0.82)
        if any(marker in normalized for marker in ("phenotype", "rare", "syndrome")):
            add("hpo", 0.65)
    if any(marker in normalized for marker in ("cancer", "carcinoma", "oncology", "tumor", "metast", "neoplasm")):
        add("nci", 0.9)
        add("pubmed", 0.68)
    if any(marker in normalized for marker in ("bacteria", "cdc", "covid", "infection", "mrsa", "pneumonia", "sepsis", "virus")):
        add("cdc", 0.82)
        add("pubmed", 0.65)
    if any(marker in normalized for marker in ("diabetes", "kidney", "renal", "creatinine", "albuminuria", "digestive", "obesity")):
        add("niddk", 0.78)
        add("pubmed", 0.62)
    if group_set & {"PROC", "OBS"}:
        add("ncbi_bookshelf_oa", 0.7)
        add("pubmed", 0.62)
    if group_set & {"DISO", "PHEN"}:
        add("medlineplus", 0.55)
        add("pubmed", 0.58)
    if not source_scores:
        add("pubmed", 0.5)

    return [
        source
        for source, _score in sorted(
            source_scores.items(),
            key=lambda item: (-item[1], item[0]),
        )[:5]
    ]


def association_candidate_score(
    row: dict[str, str],
    *,
    pair: str,
    inference: AssociationInference,
    groups: tuple[str, str],
    labels: tuple[str, str],
    evidence_sources: Iterable[str],
    prevalence_score: float = 0.0,
) -> float:
    weight = max(failure_weight(row), 0.1)
    pair_cuis = set(pair_parts(pair))
    missing_bonus = 1.45 if pair_cuis & split_values(row.get("missing_at_10", "")) else 1.0
    missing_bonus += 0.25 if pair_cuis & split_values(row.get("missing_at_20", "")) else 0.0
    complementary_groups = {
        frozenset(("CHEM", "DISO")),
        frozenset(("CHEM", "PHEN")),
        frozenset(("GENE", "DISO")),
        frozenset(("GENE", "CHEM")),
        frozenset(("PROC", "DISO")),
        frozenset(("OBS", "DISO")),
        frozenset(("LIVB", "DISO")),
    }
    group_bonus = 1.25 if frozenset(groups) in complementary_groups else 1.0
    source_quality = 0.0
    profile_by_source = {profile.source: profile for profile in SOURCE_PROFILES}
    for source in evidence_sources:
        profile = profile_by_source.get(source)
        if profile:
            source_quality = max(source_quality, profile.trust / max(profile.effort, 0.1))
    source_bonus = 1.0 + min(source_quality * 0.25, 0.55)
    relation_bonus = 0.75 + inference.confidence
    proximity = pair_text_proximity_score(labels[0], labels[1], str(row.get("query") or ""))
    proximity_bonus = 0.75 + proximity * 0.5
    prevalence_bonus = prevalence_multiplier(prevalence_score)
    return weight * missing_bonus * group_bonus * source_bonus * relation_bonus * proximity_bonus * prevalence_bonus


def association_sort_key(item: AssociationCandidate) -> tuple[float, int, int, str]:
    return (-item.utility_score, -item.missing_query_count, -item.query_count, item.pair)


def rank_association_candidates(
    rows: Iterable[dict[str, str]],
    *,
    cui_label_map: dict[str, str] | None = None,
    semantic_group_map: dict[str, str] | None = None,
    prevalence_prior_map: dict[str, float] | None = None,
    max_candidates: int = 50,
) -> list[dict[str, Any]]:
    labels = dict(cui_label_map or {})
    groups = dict(semantic_group_map or {})
    buckets: dict[str, AssociationCandidate] = {}
    for row in rows:
        row_labels = labels_for_row(row, cui_label_map=labels)
        for pair in split_pair_values(row.get("unavailable_association_pairs", "")):
            left, right = pair_parts(pair)
            inference = infer_association_relationship(
                left,
                right,
                row,
                cui_label_map=row_labels,
                semantic_group_map=groups,
            )
            source_label = row_labels.get(inference.source_cui, inference.source_cui)
            target_label = row_labels.get(inference.target_cui, inference.target_cui)
            source_group = group_for_cui(
                inference.source_cui,
                row,
                label=source_label,
                semantic_group_map=groups,
            )
            target_group = group_for_cui(
                inference.target_cui,
                row,
                label=target_label,
                semantic_group_map=groups,
            )
            evidence_sources = association_evidence_sources(
                row,
                groups=(source_group, target_group),
                relationship_type=inference.relationship_type,
                labels=(source_label, target_label),
            )
            source_commonness = commonness_score(
                inference.source_cui,
                label=source_label,
                group=source_group,
                query=str(row.get("query") or ""),
                prevalence_prior_map=prevalence_prior_map,
            )
            target_commonness = commonness_score(
                inference.target_cui,
                label=target_label,
                group=target_group,
                query=str(row.get("query") or ""),
                prevalence_prior_map=prevalence_prior_map,
            )
            prevalence_score = max(source_commonness, target_commonness) + (
                min(source_commonness, target_commonness) * 0.35
            )
            score = association_candidate_score(
                row,
                pair=pair,
                inference=inference,
                groups=(source_group, target_group),
                labels=(source_label, target_label),
                evidence_sources=evidence_sources,
                prevalence_score=prevalence_score,
            )
            current = buckets.get(pair)
            if current is None:
                current = AssociationCandidate(
                    pair=pair,
                    source_cui=inference.source_cui,
                    target_cui=inference.target_cui,
                    source_label=source_label,
                    target_label=target_label,
                    source_semantic_group=source_group,
                    target_semantic_group=target_group,
                    relationship_type=inference.relationship_type,
                    relation_group=inference.relation_group,
                    direction=inference.direction,
                    relation_confidence=inference.confidence,
                    rationale=inference.rationale,
                    prevalence_score=prevalence_score,
                )
                buckets[pair] = current
            current.add_row(
                row,
                score=score,
                inference=inference,
                source_label=source_label,
                target_label=target_label,
                source_semantic_group=source_group,
                target_semantic_group=target_group,
                evidence_sources=evidence_sources,
                prevalence_score=prevalence_score,
            )
    candidates = sorted(buckets.values(), key=association_sort_key)
    if max_candidates > 0:
        candidates = candidates[:max_candidates]
    return [candidate.to_payload() for candidate in candidates]


def concise_topic_seed(text: str, *, max_terms: int = 8) -> str:
    cleaned = re.sub(r"^\s*Search:\s*", "", text.strip(), flags=re.I)
    tokens = [
        token
        for token in normalized_key(cleaned).split()
        if len(token) > 2 and token not in STOPWORDS and not token.isdigit()
    ]
    if not tokens:
        return "general clinical gap"
    unique = []
    seen = set()
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        unique.append(token)
        if len(unique) >= max_terms:
            break
    return " ".join(unique)


def source_seed(profile: SourceAcquisitionProfile, row: dict[str, str]) -> str:
    query = str(row.get("query") or "")
    if profile.source == "dailymed":
        drugs = extract_drug_terms(query)
        return drugs[0] if drugs else "drug safety and therapeutics"
    if profile.source == "medlineplus_genetics":
        genes = extract_gene_terms(query)
        return genes[0] if genes else "genetics and rare disease language"
    if profile.source in {"active_label_supplement", "extension_concepts"}:
        missing = sorted(missing_cuis(row))
        return missing[0] if missing else concise_topic_seed(query, max_terms=5)
    if profile.source == "relationship_edges":
        pairs = sorted(split_pair_values(row.get("unavailable_association_pairs", "")))
        return pairs[0] if pairs else concise_topic_seed(query, max_terms=5)
    if profile.source == "clinicaltrials":
        return concise_topic_seed(query, max_terms=8)
    if profile.source in {"pubmed", "europepmc", "pmc_oa"}:
        return concise_topic_seed(query, max_terms=8)
    matches = _keyword_matches(profile.keywords, query, _tokens(query))
    if matches:
        return normalized_key(matches[0])
    return concise_topic_seed(query, max_terms=5)


def suggested_command(profile: SourceAcquisitionProfile, seed: str) -> str:
    quoted = seed.replace('"', '\\"')
    seed_slug = _slug(seed)
    label_index = "build/umls_biomedicine_search_label_index.sqlite"
    if profile.source == "dailymed":
        return (
            "python3 scripts/evidence_vectors.py build-source-subset --source dailymed "
            f'--drug-name "{quoted}" --label-index {label_index} '
            f"--out-dir build/public/source_subsets/dailymed_{seed_slug}"
        )
    if profile.source == "clinicaltrials":
        return (
            "python3 scripts/evidence_vectors.py build-source-subset --source clinicaltrials "
            f'--query "{quoted}" --label-index {label_index} '
            f"--out-dir build/public/source_subsets/clinicaltrials_{seed_slug}"
        )
    if profile.source in {"pubmed", "europepmc", "pmc_oa"}:
        command = {
            "pubmed": "fetch-pubmed-topics",
            "europepmc": "fetch-europepmc-topics",
            "pmc_oa": "fetch-pmc-oa-topics",
        }[profile.source]
        return (
            f"add a TSV topic row for \"{quoted}\", then run "
            f"python3 scripts/evidence_vectors.py {command} --topics <topics.tsv> --out <corpus.jsonl>"
        )
    if profile.source == "ncbi_bookshelf_oa":
        return (
            "python3 scripts/evidence_vectors.py build-source-subset --source ncbi_bookshelf_oa "
            f'--term "{quoted}" --label-index {label_index} '
            f"--out-dir build/public/source_subsets/bookshelf_oa_{seed_slug}"
        )
    if profile.source in {"nci", "cdc", "fda", "niddk", "medlineplus", "medlineplus_genetics"}:
        return (
            f"python3 scripts/evidence_vectors.py build-source-subset --source {profile.source} "
            f"--max-records 0 --label-index {label_index} "
            f"--out-dir build/public/source_subsets/{profile.source}_expanded"
        )
    if profile.source == "active_label_supplement":
        return f"review config/active_label_supplement.tsv for missing CUI/phrase seed {quoted}"
    if profile.source == "extension_concepts":
        return f"review extension concept evidence for seed {quoted}, then run build-extension-concepts"
    if profile.source == "relationship_edges":
        return (
            f"add or mine universal relationship-edge evidence for pair {quoted}, then run "
            "python3 scripts/evidence_vectors.py build-relationship-edge-index --edges <edges.jsonl> --out build/relationship_edges.sqlite --replace"
        )
    if profile.source in {"hpo", "mondo"}:
        return f"stage and review {profile.label} before adding it to the relation/index build"
    return f"review source acquisition for {profile.source}: {quoted}"


def recommendation_sort_key(item: AcquisitionRecommendation) -> tuple[float, int, str, str]:
    return (-item.priority_score, -item.query_count, item.source, item.seed)


def plan_source_acquisition(
    rows: Iterable[dict[str, str]],
    *,
    max_recommendations: int = 25,
    max_association_candidates: int = 50,
    include_public_default_only: bool = True,
    minimum_score: float = 0.01,
    infer_disallowed: bool = True,
    candidate_disallowed_rank_limit: int = 10,
    available_relation_pairs: set[tuple[str, str]] | None = None,
    infer_associations: bool = True,
    max_association_pairs_per_query: int = 12,
    cui_label_map: dict[str, str] | None = None,
    semantic_group_map: dict[str, str] | None = None,
    prevalence_prior_map: dict[str, float] | None = None,
) -> dict:
    buckets: dict[tuple[str, str, str], AcquisitionRecommendation] = {}
    augmented_rows: list[dict[str, str]] = []
    evaluated_rows = 0
    contributing_rows = 0
    total_failure_weight = 0.0
    total_raw_failure_weight = 0.0
    total_prevalence_score = 0.0
    profiles = [
        profile
        for profile in SOURCE_PROFILES
        if profile.public_default or not include_public_default_only
    ]
    inferred_disallowed_total = 0
    unavailable_association_total = 0
    for raw_row in rows:
        row = dict(raw_row)
        if infer_disallowed and not row.get("candidate_disallowed_cuis"):
            inferred = infer_candidate_disallowed_cuis(
                row,
                rank_limit=candidate_disallowed_rank_limit,
            )
            if inferred:
                inferred_disallowed_total += len(inferred)
                row["candidate_disallowed_cuis"] = "|".join(sorted(inferred))
        if infer_associations and not row.get("unavailable_association_pairs"):
            pairs = unavailable_association_pairs(
                row,
                available_relation_pairs=available_relation_pairs,
                max_pairs=max_association_pairs_per_query,
            )
            if pairs:
                unavailable_association_total += len(pairs)
                row["unavailable_association_pairs"] = "|".join(sorted(pairs))
        augmented_rows.append(row)
        evaluated_rows += 1
        raw_weight = failure_weight(row)
        if raw_weight <= 0:
            continue
        row_prevalence = row_prevalence_score(
            row,
            cui_label_map=cui_label_map or {},
            semantic_group_map=semantic_group_map or {},
            prevalence_prior_map=prevalence_prior_map or {},
        )
        weight = raw_weight * prevalence_multiplier(row_prevalence)
        contributing_rows += 1
        total_raw_failure_weight += raw_weight
        total_failure_weight += weight
        total_prevalence_score += row_prevalence
        for profile in profiles:
            applicability = profile_applicability(profile, row)
            if applicability <= 0:
                continue
            score = weight * applicability * profile.trust / max(profile.effort, 0.1)
            if score < minimum_score:
                continue
            seed = source_seed(profile, row)
            key = (profile.source, profile.action, seed)
            current = buckets.get(key)
            if current is None:
                current = AcquisitionRecommendation(
                    source=profile.source,
                    label=profile.label,
                    action=profile.action,
                    seed=seed,
                    rationale=profile.rationale,
                    suggested_command=suggested_command(profile, seed),
                )
                buckets[key] = current
            current.add_row(
                row,
                score=score,
                prevalence_score=row_prevalence,
                raw_failure_weight=raw_weight,
                weighted_failure_weight=weight,
            )

    recommendations = sorted(buckets.values(), key=recommendation_sort_key)
    if max_recommendations > 0:
        recommendations = recommendations[:max_recommendations]
    source_totals: dict[str, dict[str, object]] = {}
    for item in recommendations:
        total = source_totals.setdefault(
            item.source,
            {"source": item.source, "score": 0.0, "recommendations": 0, "queries": 0},
        )
        total["score"] = float(total["score"]) + item.priority_score
        total["recommendations"] = int(total["recommendations"]) + 1
        total["queries"] = int(total["queries"]) + item.query_count
    association_candidates = rank_association_candidates(
        augmented_rows,
        cui_label_map=cui_label_map or {},
        semantic_group_map=semantic_group_map or {},
        prevalence_prior_map=prevalence_prior_map or {},
        max_candidates=max_association_candidates,
    )
    return {
        "summary": {
            "evaluated_rows": evaluated_rows,
            "contributing_rows": contributing_rows,
            "total_failure_weight": round(total_failure_weight, 4),
            "total_raw_failure_weight": round(total_raw_failure_weight, 4),
            "average_prevalence_score": round(
                total_prevalence_score / contributing_rows,
                4,
            )
            if contributing_rows
            else 0.0,
            "recommendations": len(recommendations),
            "association_candidates": len(association_candidates),
            "public_default_only": include_public_default_only,
            "inferred_candidate_disallowed_cuis": inferred_disallowed_total,
            "candidate_disallowed_rank_limit": candidate_disallowed_rank_limit,
            "unavailable_association_pairs": unavailable_association_total,
            "association_relation_filter": available_relation_pairs is not None,
            "max_association_pairs_per_query": max_association_pairs_per_query,
            "max_association_candidates": max_association_candidates,
        },
        "source_totals": [
            {
                **value,
                "score": round(float(value["score"]), 4),
            }
            for value in sorted(source_totals.values(), key=lambda row: (-float(row["score"]), str(row["source"])))
        ],
        "association_candidates": association_candidates,
        "recommendations": [item.to_payload() for item in recommendations],
    }


def plan_source_acquisition_from_files(
    quality_summary_paths: Iterable[str | Path],
    *,
    query_spec_paths: Iterable[str | Path] = (),
    relation_index_paths: Iterable[str | Path] = (),
    label_index_paths: Iterable[str | Path] = (),
    semantic_type_index_paths: Iterable[str | Path] = (),
    prevalence_prior_paths: Iterable[str | Path] = (),
    max_recommendations: int = 25,
    max_association_candidates: int = 50,
    include_public_default_only: bool = True,
    minimum_score: float = 0.01,
    infer_disallowed: bool = True,
    candidate_disallowed_rank_limit: int = 10,
    infer_associations: bool = True,
    max_association_pairs_per_query: int = 12,
) -> dict:
    rows: list[dict[str, str]] = []
    inputs = []
    for path in quality_summary_paths:
        path = Path(path).expanduser()
        inputs.append(str(path))
        rows.extend(read_quality_summary_tsv(path))
    specs: dict[str, dict[str, set[str]]] = {}
    query_inputs = []
    for path in query_spec_paths:
        path = Path(path).expanduser()
        if not path.exists():
            continue
        query_inputs.append(str(path))
        specs.update(read_query_spec_tsv(path))
    if specs:
        rows = attach_query_specs(rows, specs)
    relation_inputs = []
    relation_paths = [Path(path).expanduser() for path in relation_index_paths]
    for path in relation_paths:
        if path.exists():
            relation_inputs.append(str(path))
    available_relation_pairs = load_relation_pairs(relation_paths) if relation_paths else None
    label_inputs = []
    label_paths = [Path(path).expanduser() for path in label_index_paths]
    for path in label_paths:
        if path.exists():
            label_inputs.append(str(path))
    semantic_type_inputs = []
    semantic_type_paths = [Path(path).expanduser() for path in semantic_type_index_paths]
    for path in semantic_type_paths:
        if path.exists():
            semantic_type_inputs.append(str(path))
    cuis = collect_cuis_from_rows(rows)
    cui_label_map = labels_from_rows(rows)
    if label_paths:
        cui_label_map.update(load_cui_labels(label_paths, cuis))
    semantic_group_map = (
        load_cui_semantic_groups(semantic_type_paths, cuis) if semantic_type_paths else {}
    )
    prevalence_prior_inputs = []
    prevalence_prior_map: dict[str, float] = {}
    for path in prevalence_prior_paths:
        path = Path(path).expanduser()
        if not path.exists():
            continue
        prevalence_prior_inputs.append(str(path))
        prevalence_prior_map.update(read_prevalence_prior_tsv(path))
    plan = plan_source_acquisition(
        rows,
        max_recommendations=max_recommendations,
        max_association_candidates=max_association_candidates,
        include_public_default_only=include_public_default_only,
        minimum_score=minimum_score,
        infer_disallowed=infer_disallowed,
        candidate_disallowed_rank_limit=candidate_disallowed_rank_limit,
        available_relation_pairs=available_relation_pairs,
        infer_associations=infer_associations,
        max_association_pairs_per_query=max_association_pairs_per_query,
        cui_label_map=cui_label_map,
        semantic_group_map=semantic_group_map,
        prevalence_prior_map=prevalence_prior_map,
    )
    plan["inputs"] = inputs
    plan["query_spec_inputs"] = query_inputs
    plan["relation_index_inputs"] = relation_inputs
    plan["label_index_inputs"] = label_inputs
    plan["semantic_type_index_inputs"] = semantic_type_inputs
    plan["prevalence_prior_inputs"] = prevalence_prior_inputs
    plan["summary"]["prevalence_prior_count"] = len(prevalence_prior_map)
    return plan


def write_plan_tsv(plan: dict, path: str | Path) -> None:
    fields = [
        "rank",
        "priority_score",
        "source",
        "action",
        "seed",
        "query_count",
        "prevalence_score",
        "prevalence_multiplier",
        "raw_failure_weight",
        "weighted_failure_weight",
        "missing_cuis",
        "disallowed_cuis",
        "candidate_disallowed_cuis",
        "association_pairs",
        "association_count",
        "sample_query_ids",
        "suggested_command",
        "rationale",
    ]
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for rank, item in enumerate(plan.get("recommendations") or [], start=1):
            row = dict(item)
            row["rank"] = rank
            row["missing_cuis"] = "|".join(row.get("missing_cuis") or [])
            row["disallowed_cuis"] = "|".join(row.get("disallowed_cuis") or [])
            row["candidate_disallowed_cuis"] = "|".join(row.get("candidate_disallowed_cuis") or [])
            row["association_pairs"] = "|".join(row.get("association_pairs") or [])
            row["sample_query_ids"] = "|".join(row.get("sample_query_ids") or [])
            writer.writerow({field: row.get(field, "") for field in fields})


def write_association_candidates_tsv(plan: dict, path: str | Path) -> None:
    fields = [
        "rank",
        "utility_score",
        "pair",
        "source_cui",
        "source_label",
        "target_cui",
        "target_label",
        "relationship_type",
        "relation_group",
        "direction",
        "relation_confidence",
        "prevalence_score",
        "prevalence_multiplier",
        "source_semantic_group",
        "target_semantic_group",
        "query_count",
        "missing_query_count",
        "evidence_sources",
        "sample_query_ids",
        "rationale",
        "review_status",
        "index_destination",
    ]
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for rank, item in enumerate(plan.get("association_candidates") or [], start=1):
            row = dict(item)
            row["rank"] = rank
            row["evidence_sources"] = "|".join(row.get("evidence_sources") or [])
            row["sample_query_ids"] = "|".join(row.get("sample_query_ids") or [])
            writer.writerow({field: row.get(field, "") for field in fields})


def write_association_candidates_jsonl(plan: dict, path: str | Path) -> None:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for rank, item in enumerate(plan.get("association_candidates") or [], start=1):
            payload = dict(item)
            payload["rank"] = rank
            handle.write(json.dumps(payload, sort_keys=True) + "\n")


def suggested_association_evidence_query(item: dict[str, Any]) -> str:
    source_label = str(item.get("source_label") or item.get("source_cui") or "").strip()
    target_label = str(item.get("target_label") or item.get("target_cui") or "").strip()
    relation = str(item.get("relationship_type") or "associated_with").strip()
    if relation == "treats":
        connector = "treatment"
    elif relation in {"causes", "contraindicated_with"}:
        connector = "adverse effect risk"
    elif relation == "diagnostic_evidence":
        connector = "diagnosis workup"
    elif str(item.get("relation_group") or "") == "drug_response":
        connector = "drug response pharmacogenomics"
    else:
        connector = "association"
    return " ".join(part for part in (source_label, target_label, connector) if part)


def association_review_rows(plan: dict) -> list[dict[str, Any]]:
    rows = []
    for rank, item in enumerate(plan.get("association_candidates") or [], start=1):
        evidence_sources = list(item.get("evidence_sources") or [])
        rows.append(
            {
                "rank": rank,
                "review_status": "needs_source_evidence",
                "review_decision": "",
                "candidate_pair": item.get("pair", ""),
                "utility_score": item.get("utility_score", 0),
                "prevalence_score": item.get("prevalence_score", 0),
                "prevalence_multiplier": item.get("prevalence_multiplier", 1),
                "proposed_subject_cui": item.get("source_cui", ""),
                "proposed_subject_label": item.get("source_label", ""),
                "proposed_object_cui": item.get("target_cui", ""),
                "proposed_object_label": item.get("target_label", ""),
                "proposed_relationship_type": item.get("relationship_type", ""),
                "proposed_relation_group": item.get("relation_group", ""),
                "proposed_direction": item.get("direction", ""),
                "proposed_confidence": item.get("relation_confidence", 0),
                "proposed_source": evidence_sources[0] if evidence_sources else "",
                "candidate_sources": "|".join(evidence_sources),
                "sample_query_ids": "|".join(item.get("sample_query_ids") or []),
                "evidence_search_query": suggested_association_evidence_query(item),
                "evidence_source": "",
                "source_url": "",
                "supporting_pmids": "",
                "supporting_doc_ids": "",
                "evidence_text": "",
                "reviewer": "",
                "reviewer_notes": "",
                "index_destination": "relationship_edges",
                "rationale": item.get("rationale", ""),
            }
        )
    return rows


ASSOCIATION_REVIEW_FIELDS = [
    "rank",
    "review_status",
    "review_decision",
    "candidate_pair",
    "utility_score",
    "prevalence_score",
    "prevalence_multiplier",
    "proposed_subject_cui",
    "proposed_subject_label",
    "proposed_object_cui",
    "proposed_object_label",
    "proposed_relationship_type",
    "proposed_relation_group",
    "proposed_direction",
    "proposed_confidence",
    "proposed_source",
    "candidate_sources",
    "sample_query_ids",
    "evidence_search_query",
    "evidence_source",
    "source_url",
    "supporting_pmids",
    "supporting_doc_ids",
    "evidence_text",
    "reviewer",
    "reviewer_notes",
    "index_destination",
    "rationale",
]


def write_association_review_tsv(plan: dict, path: str | Path) -> None:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=ASSOCIATION_REVIEW_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in association_review_rows(plan):
            writer.writerow({field: row.get(field, "") for field in ASSOCIATION_REVIEW_FIELDS})


def write_association_review_jsonl(plan: dict, path: str | Path) -> None:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in association_review_rows(plan):
            handle.write(json.dumps(row, sort_keys=True) + "\n")


APPROVED_REVIEW_DECISIONS = {"accept", "accepted", "approve", "approved", "include", "included", "yes", "y"}


def _split_review_list(value: Any) -> list[str]:
    items = []
    for raw in str(value or "").replace(",", "|").replace(";", "|").split("|"):
        item = raw.strip()
        if item:
            items.append(item)
    return items


def _review_path_rows(path: str | Path) -> Iterable[dict[str, Any]]:
    path = Path(path).expanduser()
    if path.suffix.lower() == ".jsonl":
        yield from iter_jsonl(path)
        return
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(
            (line for line in handle if line.strip() and not line.lstrip().startswith("#")),
            delimiter="\t",
        )
        for row in reader:
            yield dict(row)


def reviewed_association_edge_rows(
    review_paths: Iterable[str | Path],
    *,
    allow_missing_evidence: bool = False,
) -> list[dict[str, Any]]:
    edges = []
    for path in review_paths:
        for rank, row in enumerate(_review_path_rows(path), start=1):
            decision = str(row.get("review_decision") or "").strip().lower()
            if decision not in APPROVED_REVIEW_DECISIONS:
                continue
            subject_cui = str(row.get("proposed_subject_cui") or "").strip().upper()
            object_cui = str(row.get("proposed_object_cui") or "").strip().upper()
            if not subject_cui or not object_cui or subject_cui == object_cui:
                continue
            evidence_text = str(row.get("evidence_text") or "").strip()
            source_url = str(row.get("source_url") or "").strip()
            supporting_pmids = _split_review_list(row.get("supporting_pmids"))
            supporting_doc_ids = _split_review_list(row.get("supporting_doc_ids"))
            if not allow_missing_evidence and not (
                evidence_text or source_url or supporting_pmids or supporting_doc_ids
            ):
                continue
            source = str(row.get("evidence_source") or row.get("proposed_source") or "reviewed_source").strip()
            relationship_type = str(row.get("proposed_relationship_type") or "associated_with").strip()
            relation_group = str(row.get("proposed_relation_group") or relationship_type).strip()
            row_rank = _int(str(row.get("rank") or "")) or rank
            edge_seed = {
                "rank": row_rank,
                "supporting_pmids": supporting_pmids,
                "supporting_doc_ids": supporting_doc_ids,
                "support_count": max(len(supporting_pmids), len(supporting_doc_ids), 1 if evidence_text or source_url else 0),
            }
            edge = universal_relationship_edge(
                subject_cui=subject_cui,
                object_cui=object_cui,
                relation=relationship_type,
                rela=relationship_type,
                relation_group=relation_group,
                source=source,
                direction=str(row.get("proposed_direction") or ""),
                row=edge_seed,
                context={
                    "review_status": "approved",
                    "source_url": source_url,
                    "reviewer": str(row.get("reviewer") or "").strip(),
                    "reviewer_notes": str(row.get("reviewer_notes") or "").strip(),
                    "candidate_pair": str(row.get("candidate_pair") or "").strip(),
                    "sample_query_ids": _split_review_list(row.get("sample_query_ids")),
                },
            )
            confidence = _float(str(row.get("proposed_confidence") or ""))
            if confidence > 0:
                edge["confidence"] = min(max(confidence, 0.0), 1.0)
            if relationship_type:
                edge["type"] = relationship_type
            if evidence_text:
                edge["evidence"]["evidence_text"] = evidence_text
            if source_url:
                edge["evidence"]["source_url"] = source_url
            payload = {
                "source_class": "reviewed_source_acquisition",
                "subject_cui": subject_cui,
                "subject_label": str(row.get("proposed_subject_label") or subject_cui).strip(),
                "object_cui": object_cui,
                "object_label": str(row.get("proposed_object_label") or object_cui).strip(),
                "relationship_type": relationship_type,
                "relation": relationship_type,
                "rela": relationship_type,
                "relation_group": relation_group,
                "direction": str(row.get("proposed_direction") or "").strip(),
                "edge": edge,
                "review": {
                    "decision": decision,
                    "rank": row_rank,
                    "utility_score": row.get("utility_score", ""),
                    "prevalence_score": row.get("prevalence_score", ""),
                },
            }
            edges.append(payload)
    return edges


def write_reviewed_association_edges_jsonl(
    review_paths: Iterable[str | Path],
    path: str | Path,
    *,
    allow_missing_evidence: bool = False,
) -> int:
    edges = reviewed_association_edge_rows(
        review_paths,
        allow_missing_evidence=allow_missing_evidence,
    )
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for edge in edges:
            handle.write(json.dumps(edge, sort_keys=True) + "\n")
    return len(edges)


def _slug(value: str, *, max_length: int = 80) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", normalized_key(value)).strip("_")
    if not slug:
        slug = "seed"
    return slug[:max_length].strip("_") or "seed"


def source_action_seed_rows(plan: dict) -> list[dict[str, Any]]:
    rows = []
    for rank, item in enumerate(plan.get("recommendations") or [], start=1):
        rows.append(
            {
                "rank": rank,
                "source": item.get("source", ""),
                "action": item.get("action", ""),
                "seed": item.get("seed", ""),
                "seed_slug": _slug(str(item.get("seed") or "")),
                "priority_score": item.get("priority_score", 0),
                "prevalence_score": item.get("prevalence_score", 0),
                "prevalence_multiplier": item.get("prevalence_multiplier", 1),
                "query_count": item.get("query_count", 0),
                "sample_query_ids": "|".join(item.get("sample_query_ids") or []),
                "association_pairs": "|".join(item.get("association_pairs") or []),
                "suggested_command": item.get("suggested_command", ""),
                "rationale": item.get("rationale", ""),
            }
        )
    return rows


def literature_topic_rows(plan: dict, *, default_retmax: int = 25) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(
        *,
        source_hint: str,
        topic: str,
        term: str,
        rank: int,
        origin: str,
        score: Any,
        sample_query_ids: Iterable[str],
    ) -> None:
        key = (source_hint, normalized_key(term))
        if not term or key in seen:
            return
        seen.add(key)
        rows.append(
            {
                "topic": topic,
                "term": term,
                "retmax": default_retmax,
                "source_hint": source_hint,
                "rank": rank,
                "origin": origin,
                "score": score,
                "sample_query_ids": "|".join(sample_query_ids),
            }
        )

    for rank, item in enumerate(plan.get("recommendations") or [], start=1):
        source = str(item.get("source") or "")
        if source in {"pubmed", "europepmc", "pmc_oa"}:
            seed = str(item.get("seed") or "").strip()
            add(
                source_hint=source,
                topic=_slug(seed),
                term=seed,
                rank=rank,
                origin="recommendation",
                score=item.get("priority_score", 0),
                sample_query_ids=item.get("sample_query_ids") or [],
            )
    for rank, item in enumerate(plan.get("association_candidates") or [], start=1):
        sources = set(item.get("evidence_sources") or [])
        for source in ("pubmed", "europepmc", "pmc_oa"):
            if source not in sources:
                continue
            query = suggested_association_evidence_query(item)
            add(
                source_hint=source,
                topic=_slug(str(item.get("pair") or query)),
                term=query,
                rank=rank,
                origin="association_candidate",
                score=item.get("utility_score", 0),
                sample_query_ids=item.get("sample_query_ids") or [],
            )
    return rows


def source_subset_seed_rows(plan: dict) -> list[dict[str, Any]]:
    rows = []
    for rank, item in enumerate(plan.get("recommendations") or [], start=1):
        source = str(item.get("source") or "")
        if source not in {
            "clinicaltrials",
            "dailymed",
            "ncbi_bookshelf_oa",
            "nci",
            "cdc",
            "fda",
            "niddk",
            "medlineplus",
            "medlineplus_genetics",
            "hpo",
            "mondo",
        }:
            continue
        seed = str(item.get("seed") or "").strip()
        row = {
            "rank": rank,
            "source": source,
            "seed": seed,
            "seed_slug": _slug(seed),
            "priority_score": item.get("priority_score", 0),
            "prevalence_score": item.get("prevalence_score", 0),
            "sample_query_ids": "|".join(item.get("sample_query_ids") or []),
            "query": "",
            "drug_name": "",
            "term": "",
            "max_records": "",
            "suggested_out_dir": f"build/public/source_subsets/{source}_{_slug(seed)}",
        }
        if source == "dailymed":
            row["drug_name"] = seed
            row["max_records"] = 25
        elif source == "clinicaltrials":
            row["query"] = seed
            row["max_records"] = 100
        elif source == "ncbi_bookshelf_oa":
            row["term"] = seed
            row["max_records"] = 100
        elif source in {"nci", "cdc", "fda", "niddk", "medlineplus", "medlineplus_genetics"}:
            row["max_records"] = 0
        rows.append(row)
    return rows


def write_dict_tsv(rows: list[dict[str, Any]], path: str | Path, *, fields: list[str]) -> None:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_command_checklist(plan: dict, path: str | Path) -> None:
    lines = [
        "# Source acquisition command checklist",
        "# Uses build/umls_biomedicine_search_label_index.sqlite by default because source acquisition",
        "# needs broad drug, gene, condition, lab, procedure, and synonym coverage.",
        "# Review placeholders such as <topics.tsv>, <corpus.jsonl>, and <edges.jsonl> before running.",
        "",
    ]
    for rank, item in enumerate(plan.get("recommendations") or [], start=1):
        command = str(item.get("suggested_command") or "").strip()
        if not command:
            continue
        lines.append(f"# {rank}. {item.get('source')} / {item.get('seed')}")
        lines.append(command)
        lines.append("")
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_acquisition_bundle(plan: dict, out_dir: str | Path) -> dict[str, Any]:
    out_dir = Path(out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "plan_json": out_dir / "plan.json",
        "plan_md": out_dir / "plan.md",
        "recommendations_tsv": out_dir / "recommendations.tsv",
        "association_candidates_tsv": out_dir / "association_candidates.tsv",
        "association_candidates_jsonl": out_dir / "association_candidates.jsonl",
        "association_review_tsv": out_dir / "association_review.tsv",
        "association_review_jsonl": out_dir / "association_review.jsonl",
        "source_action_seeds_tsv": out_dir / "source_action_seeds.tsv",
        "literature_topics_tsv": out_dir / "literature_topics.tsv",
        "source_subset_seeds_tsv": out_dir / "source_subset_seeds.tsv",
        "commands_todo": out_dir / "commands.todo.sh",
        "manifest": out_dir / "manifest.json",
    }
    write_plan_json(plan, outputs["plan_json"])
    outputs["plan_md"].write_text(plan_markdown(plan), encoding="utf-8")
    write_plan_tsv(plan, outputs["recommendations_tsv"])
    write_association_candidates_tsv(plan, outputs["association_candidates_tsv"])
    write_association_candidates_jsonl(plan, outputs["association_candidates_jsonl"])
    write_association_review_tsv(plan, outputs["association_review_tsv"])
    write_association_review_jsonl(plan, outputs["association_review_jsonl"])

    source_rows = source_action_seed_rows(plan)
    literature_rows = literature_topic_rows(plan)
    subset_rows = source_subset_seed_rows(plan)
    write_dict_tsv(
        source_rows,
        outputs["source_action_seeds_tsv"],
        fields=[
            "rank",
            "source",
            "action",
            "seed",
            "seed_slug",
            "priority_score",
            "prevalence_score",
            "prevalence_multiplier",
            "query_count",
            "sample_query_ids",
            "association_pairs",
            "suggested_command",
            "rationale",
        ],
    )
    write_dict_tsv(
        literature_rows,
        outputs["literature_topics_tsv"],
        fields=[
            "topic",
            "term",
            "retmax",
            "source_hint",
            "rank",
            "origin",
            "score",
            "sample_query_ids",
        ],
    )
    write_dict_tsv(
        subset_rows,
        outputs["source_subset_seeds_tsv"],
        fields=[
            "rank",
            "source",
            "seed",
            "seed_slug",
            "priority_score",
            "prevalence_score",
            "sample_query_ids",
            "query",
            "drug_name",
            "term",
            "max_records",
            "suggested_out_dir",
        ],
    )
    write_command_checklist(plan, outputs["commands_todo"])
    manifest = {
        "outputs": {key: str(value) for key, value in outputs.items() if key != "manifest"},
        "counts": {
            "recommendations": len(plan.get("recommendations") or []),
            "association_candidates": len(plan.get("association_candidates") or []),
            "source_action_seeds": len(source_rows),
            "literature_topics": len(literature_rows),
            "source_subset_seeds": len(subset_rows),
        },
        "summary": plan.get("summary") or {},
    }
    outputs["manifest"].write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def plan_markdown(plan: dict) -> str:
    summary = plan.get("summary") or {}
    lines = [
        "# Measured Source-Aware Acquisition Plan",
        "",
        "This plan prioritizes source acquisition from measured search-quality gaps. It ranks the most useful evidence first, including missing positive associations that are not already available from relation indexes.",
        "",
        "## Summary",
        "",
        f"- Inputs: {', '.join(plan.get('inputs') or []) or 'in-memory rows'}",
        f"- Query specs: {', '.join(plan.get('query_spec_inputs') or []) or 'none'}",
        f"- Relation indexes: {', '.join(plan.get('relation_index_inputs') or []) or 'none'}",
        f"- Label indexes: {', '.join(plan.get('label_index_inputs') or []) or 'none'}",
        f"- Semantic type indexes: {', '.join(plan.get('semantic_type_index_inputs') or []) or 'none'}",
        f"- Prevalence priors: {', '.join(plan.get('prevalence_prior_inputs') or []) or 'heuristic commonness only'}",
        f"- Prevalence prior rows: {summary.get('prevalence_prior_count', 0)}",
        f"- Evaluated rows: {summary.get('evaluated_rows', 0)}",
        f"- Rows with acquisition signal: {summary.get('contributing_rows', 0)}",
        f"- Total weighted failure: {summary.get('total_failure_weight', 0)}",
        f"- Total raw failure: {summary.get('total_raw_failure_weight', 0)}",
        f"- Average prevalence/commonness score: {summary.get('average_prevalence_score', 0)}",
        f"- Inferred candidate disallowed CUIs: {summary.get('inferred_candidate_disallowed_cuis', 0)}",
        f"- Unavailable association pairs: {summary.get('unavailable_association_pairs', 0)}",
        f"- Ranked association candidates: {summary.get('association_candidates', 0)}",
        f"- Recommendations: {summary.get('recommendations', 0)}",
        "",
        "## Source Totals",
        "",
        "| Source | Score | Recommendations | Query hits |",
        "| --- | ---: | ---: | ---: |",
    ]
    for item in plan.get("source_totals") or []:
        lines.append(
            f"| {item.get('source')} | {float(item.get('score') or 0):.2f} | "
            f"{item.get('recommendations')} | {item.get('queries')} |"
        )
    lines.extend(
        [
            "",
            "## Best Association Evidence",
            "",
            "| Rank | Utility | Prevalence | Pair | Relation Hint | Evidence Sources | Evidence |",
            "| ---: | ---: | ---: | --- | --- | --- | --- |",
        ]
    )
    for rank, item in enumerate((plan.get("association_candidates") or [])[:15], start=1):
        pair_label = (
            f"{item.get('source_label') or item.get('source_cui')} "
            f"({item.get('source_cui')}) -> "
            f"{item.get('target_label') or item.get('target_cui')} "
            f"({item.get('target_cui')})"
        )
        evidence_bits = []
        if item.get("sample_query_ids"):
            evidence_bits.append("queries " + ", ".join(item["sample_query_ids"][:5]))
        if item.get("missing_query_count"):
            evidence_bits.append(f"missing-side support in {item.get('missing_query_count')} query row(s)")
        lines.append(
            f"| {rank} | {float(item.get('utility_score') or 0):.2f} | "
            f"{float(item.get('prevalence_score') or 0):.2f} | {pair_label} | "
            f"{item.get('relationship_type')} / {item.get('relation_group')} | "
            f"{', '.join(item.get('evidence_sources') or [])} | {'; '.join(evidence_bits)} |"
        )
    lines.extend(
        [
            "",
            "## Recommended Queue",
            "",
            "| Rank | Score | Prevalence | Source | Action | Seed | Evidence |",
            "| ---: | ---: | ---: | --- | --- | --- | --- |",
        ]
    )
    for rank, item in enumerate(plan.get("recommendations") or [], start=1):
        evidence_bits = []
        if item.get("sample_query_ids"):
            evidence_bits.append("queries " + ", ".join(item["sample_query_ids"]))
        if item.get("missing_cuis"):
            evidence_bits.append("missing " + ", ".join(item["missing_cuis"][:5]))
        if item.get("disallowed_cuis"):
            evidence_bits.append("false positives " + ", ".join(item["disallowed_cuis"][:5]))
        if item.get("candidate_disallowed_cuis"):
            evidence_bits.append("candidate false positives " + ", ".join(item["candidate_disallowed_cuis"][:5]))
        if item.get("association_pairs"):
            evidence_bits.append("associations " + ", ".join(item["association_pairs"][:5]))
        lines.append(
            f"| {rank} | {float(item.get('priority_score') or 0):.2f} | "
            f"{float(item.get('prevalence_score') or 0):.2f} | {item.get('source')} | "
            f"{item.get('action')} | {item.get('seed')} | {'; '.join(evidence_bits)} |"
        )
    lines.extend(["", "## Commands", ""])
    for rank, item in enumerate(plan.get("recommendations") or [], start=1):
        lines.append(f"{rank}. `{item.get('suggested_command')}`")
    return "\n".join(lines) + "\n"


def write_plan_json(plan: dict, path: str | Path) -> None:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
