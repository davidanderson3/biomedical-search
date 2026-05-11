from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .mrconso_labels import collect_labels
from .relation_index import read_doc_labels
from .universal_relationship import attach_universal_edge


TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS research_relations (
    source_cui TEXT NOT NULL,
    target_cui TEXT NOT NULL,
    category TEXT NOT NULL,
    relation_group TEXT NOT NULL,
    relation TEXT NOT NULL,
    rela TEXT NOT NULL,
    sab TEXT NOT NULL,
    direction TEXT NOT NULL,
    label TEXT NOT NULL,
    source_semantic_type TEXT NOT NULL,
    target_semantic_type TEXT NOT NULL,
    rank INTEGER NOT NULL
);
"""

INDEX_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_research_relations_source_category_rank
ON research_relations(source_cui, category, rank);

CREATE INDEX IF NOT EXISTS idx_research_relations_source_rank
ON research_relations(source_cui, rank);

CREATE INDEX IF NOT EXISTS idx_research_relations_target_rank
ON research_relations(target_cui, rank);
"""


SOURCE_CATEGORIES = {
    "condition": {
        "acquired abnormality",
        "cell or molecular dysfunction",
        "congenital abnormality",
        "disease or syndrome",
        "finding",
        "injury or poisoning",
        "mental or behavioral dysfunction",
        "neoplastic process",
        "pathologic function",
        "sign or symptom",
    },
    "gene_protein": {
        "amino acid, peptide, or protein",
        "enzyme",
        "gene or genome",
        "immunologic factor",
        "nucleic acid, nucleoside, or nucleotide",
        "receptor",
    },
    "drug_chemical": {
        "antibiotic",
        "biologically active substance",
        "chemical",
        "clinical drug",
        "hazardous or poisonous substance",
        "hormone",
        "inorganic chemical",
        "organic chemical",
        "pharmacologic substance",
        "steroid",
        "vitamin",
    },
    "procedure_test": {
        "diagnostic procedure",
        "health care activity",
        "laboratory procedure",
        "molecular biology research technique",
        "therapeutic or preventive procedure",
    },
    "device": {
        "medical device",
        "research device",
    },
    "organism": {
        "animal",
        "archaeon",
        "bacterium",
        "eukaryote",
        "fungus",
        "organism",
        "plant",
        "rickettsia or chlamydia",
        "virus",
    },
}

CATEGORY_PRIORITY = {
    "condition": 0,
    "phenotype": 1,
    "gene_protein": 2,
    "drug_chemical": 3,
    "procedure_test": 4,
    "device": 5,
    "organism": 6,
}

TARGET_LABELS = {
    "condition": "conditions",
    "phenotype": "phenotypes",
    "gene_protein": "genes and proteins",
    "drug_chemical": "drugs and chemicals",
    "procedure_test": "procedures and tests",
    "device": "devices",
    "organism": "organisms",
}

GENETIC_RELAS = {
    "associated_condition_of",
    "biological_process_involves_gene_product",
    "disease_has_associated_gene",
    "disease_mapped_to_gene",
    "gene_associated_with_disease",
    "gene_has_physical_location",
    "gene_plays_role_in_process",
    "genetic_biomarker_related_to",
    "has_phenotype",
}
TREATMENT_RELAS = {
    "disease_has_accepted_treatment_with_regimen",
    "may_be_treated_by",
    "may_treat",
}
SAFETY_RELAS = {
    "causative_agent_of",
    "contraindicated_with_disease",
    "has_adverse_reaction",
}
PROCEDURE_RELAS = {
    "associated_procedure_of",
    "clinically_associated_with",
    "finding_method_of",
    "focus_of",
    "has_method",
    "interprets",
}

SAB_PRIORITY = {
    "NCI": 0,
    "OMIM": 1,
    "MEDLINEPLUS": 2,
    "MED-RT": 3,
    "SNOMEDCT_US": 4,
    "MSH": 5,
    "LNC": 6,
    "RXNORM": 7,
    "MTH": 8,
}
GENETIC_SAB_PRIORITY = {
    "MSH": 0,
    "OMIM": 1,
    "NCI": 2,
    "MEDLINEPLUS": 3,
    "SNOMEDCT_US": 4,
    "MTH": 5,
}

RELATION_GROUP_PRIORITY = {
    "genetic_association": 0,
    "treatment": 0,
    "phenotype": 1,
    "procedure_or_test": 1,
    "safety_or_cause": 2,
    "associated": 3,
}

SKIP_RELATIONS = {"AQ", "QB", "SY"}
SKIP_HIERARCHY_RELATIONS = {"PAR", "CHD", "RB", "RN"}


@dataclass(frozen=True)
class ResearchRelationCandidate:
    source_cui: str
    target_cui: str
    category: str
    relation_group: str
    relation: str
    rela: str
    sab: str
    direction: str
    source_semantic_type: str
    target_semantic_type: str


@dataclass(frozen=True)
class ResearchRelationRow:
    source_cui: str
    target_cui: str
    category: str
    relation_group: str
    relation: str
    rela: str
    sab: str
    direction: str
    label: str
    source_semantic_type: str
    target_semantic_type: str


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def load_semantic_types(mrsty_path: str | Path) -> dict[str, set[str]]:
    semantic_types: dict[str, set[str]] = {}
    with Path(mrsty_path).expanduser().open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("|")
            if len(fields) < 4:
                continue
            cui, _, _, sty = fields[:4]
            if cui and sty:
                semantic_types.setdefault(cui, set()).add(sty.lower())
    return semantic_types


def semantic_category(types: set[str]) -> str:
    for category, wanted in sorted(CATEGORY_PRIORITY.items(), key=lambda item: item[1]):
        category_types = SOURCE_CATEGORIES.get(category)
        if category_types and types & category_types:
            return category
    return ""


def best_semantic_type(types: set[str], category: str) -> str:
    wanted = SOURCE_CATEGORIES.get(category) or set()
    for sty in sorted(types):
        if sty in wanted:
            return sty
    return sorted(types)[0] if types else ""


def relation_group_for(*, rela: str, relation: str, sab: str, source_category: str, target_category: str) -> str:
    rela = rela.lower()
    if rela in GENETIC_RELAS or (
        {"gene_protein", "condition"} == {source_category, target_category}
        and sab in {"MSH", "NCI", "OMIM", "MEDLINEPLUS"}
    ):
        return "genetic_association"
    if rela in TREATMENT_RELAS or (
        {source_category, target_category} == {"condition", "drug_chemical"} and sab == "MED-RT"
    ):
        return "treatment"
    if rela in PROCEDURE_RELAS or {source_category, target_category} == {"condition", "procedure_test"}:
        return "procedure_or_test"
    if rela in SAFETY_RELAS:
        return "safety_or_cause"
    return "associated"


def useful_cross_type_relation(
    *,
    relation: str,
    rela: str,
    source_category: str,
    target_category: str,
    sab: str,
) -> bool:
    if not source_category or not target_category or source_category == target_category:
        return False
    relation = relation.upper()
    rela = rela.lower()
    if relation in SKIP_RELATIONS:
        return False
    if relation in SKIP_HIERARCHY_RELATIONS and rela not in (
        GENETIC_RELAS | TREATMENT_RELAS | SAFETY_RELAS | PROCEDURE_RELAS
    ):
        return False
    if rela in GENETIC_RELAS | TREATMENT_RELAS | SAFETY_RELAS | PROCEDURE_RELAS:
        return True
    if relation in {"RO", "RQ"} and sab in {"NCI", "OMIM", "MEDLINEPLUS", "MED-RT", "SNOMEDCT_US", "MSH", "LNC"}:
        return True
    return False


def candidate_sab_priority(candidate: ResearchRelationCandidate) -> int:
    if candidate.category == "gene_protein" and candidate.relation_group == "genetic_association":
        return GENETIC_SAB_PRIORITY.get(candidate.sab, 99)
    return SAB_PRIORITY.get(candidate.sab, 99)


def candidate_sort_key(candidate: ResearchRelationCandidate) -> tuple[int, int, int, str, str]:
    return (
        CATEGORY_PRIORITY.get(candidate.category, 99),
        RELATION_GROUP_PRIORITY.get(candidate.relation_group, 99),
        candidate_sab_priority(candidate),
        candidate.rela or candidate.relation,
        candidate.target_cui,
    )


def add_candidate(
    buckets: dict[tuple[str, str], dict[str, ResearchRelationCandidate]],
    candidate: ResearchRelationCandidate,
    *,
    max_relations_per_category: int,
) -> None:
    key = (candidate.source_cui, candidate.category)
    bucket = buckets.setdefault(key, {})
    current = bucket.get(candidate.target_cui)
    if current is None or candidate_sort_key(candidate) < candidate_sort_key(current):
        bucket[candidate.target_cui] = candidate
    if len(bucket) > max_relations_per_category * 8:
        kept = sorted(bucket.values(), key=candidate_sort_key)[: max_relations_per_category * 4]
        buckets[key] = {item.target_cui: item for item in kept}


def make_candidate(
    *,
    source_cui: str,
    target_cui: str,
    relation: str,
    rela: str,
    sab: str,
    direction: str,
    semantic_types: dict[str, set[str]],
) -> ResearchRelationCandidate | None:
    source_types = semantic_types.get(source_cui) or set()
    target_types = semantic_types.get(target_cui) or set()
    source_category = semantic_category(source_types)
    target_category = semantic_category(target_types)
    if not useful_cross_type_relation(
        relation=relation,
        rela=rela,
        source_category=source_category,
        target_category=target_category,
        sab=sab,
    ):
        return None
    return ResearchRelationCandidate(
        source_cui=source_cui,
        target_cui=target_cui,
        category=target_category,
        relation_group=relation_group_for(
            rela=rela,
            relation=relation,
            sab=sab,
            source_category=source_category,
            target_category=target_category,
        ),
        relation=relation,
        rela=rela,
        sab=sab,
        direction=direction,
        source_semantic_type=best_semantic_type(source_types, source_category),
        target_semantic_type=best_semantic_type(target_types, target_category),
    )


def collect_research_relation_candidates(
    *,
    mrrel_path: str | Path,
    source_cuis: set[str],
    semantic_types: dict[str, set[str]],
    max_relations_per_category: int = 12,
    include_inverse: bool = True,
    include_suppressed: bool = False,
) -> dict[tuple[str, str], list[ResearchRelationCandidate]]:
    buckets: dict[tuple[str, str], dict[str, ResearchRelationCandidate]] = {}
    with Path(mrrel_path).expanduser().open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("|")
            if len(fields) < 15:
                continue
            cui1, rel, cui2, rela, sab, suppress = (
                fields[0],
                fields[3],
                fields[4],
                fields[7],
                fields[10],
                fields[14],
            )
            if cui1 == cui2:
                continue
            if not include_suppressed and suppress == "Y":
                continue
            if cui1 in source_cuis:
                candidate = make_candidate(
                    source_cui=cui1,
                    target_cui=cui2,
                    relation=rel,
                    rela=rela,
                    sab=sab,
                    direction="outgoing",
                    semantic_types=semantic_types,
                )
                if candidate:
                    add_candidate(
                        buckets,
                        candidate,
                        max_relations_per_category=max_relations_per_category,
                    )
            if include_inverse and cui2 in source_cuis:
                candidate = make_candidate(
                    source_cui=cui2,
                    target_cui=cui1,
                    relation=rel,
                    rela=rela,
                    sab=sab,
                    direction="incoming",
                    semantic_types=semantic_types,
                )
                if candidate:
                    add_candidate(
                        buckets,
                        candidate,
                        max_relations_per_category=max_relations_per_category,
                    )
    return {
        key: sorted(bucket.values(), key=candidate_sort_key)[:max_relations_per_category]
        for key, bucket in buckets.items()
    }


def hpo_database_key(database_id: str) -> tuple[str, str] | None:
    if ":" not in database_id:
        return None
    prefix, code = database_id.split(":", 1)
    prefix = prefix.strip().upper()
    code = code.strip()
    if not code:
        return None
    sab = {
        "OMIM": "OMIM",
        "ORPHA": "ORPHANET",
        "ORPHANET": "ORPHANET",
        "DECIPHER": "DECIPHER",
        "MONDO": "MONDO",
    }.get(prefix)
    if not sab:
        return None
    return sab, code


def parse_hpo_obo(hpo_obo_path: str | Path) -> tuple[dict[str, str], dict[str, list[str]]]:
    labels: dict[str, str] = {}
    umls_xrefs: dict[str, list[str]] = {}
    current_id = ""
    current_name = ""
    current_xrefs: list[str] = []
    is_obsolete = False

    def flush() -> None:
        if not current_id or is_obsolete:
            return
        if current_name:
            labels[current_id] = current_name
        if current_xrefs:
            seen = set()
            umls_xrefs[current_id] = []
            for cui in current_xrefs:
                if cui not in seen:
                    umls_xrefs[current_id].append(cui)
                    seen.add(cui)

    with Path(hpo_obo_path).expanduser().open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if line == "[Term]":
                flush()
                current_id = ""
                current_name = ""
                current_xrefs = []
                is_obsolete = False
                continue
            if line.startswith("["):
                flush()
                current_id = ""
                current_name = ""
                current_xrefs = []
                is_obsolete = False
                continue
            if line.startswith("id: "):
                current_id = line[4:].strip()
            elif line.startswith("name: "):
                current_name = line[6:].strip()
            elif line == "is_obsolete: true":
                is_obsolete = True
            elif line.startswith("xref: UMLS:"):
                cui = line.split("xref: UMLS:", 1)[1].split()[0].strip()
                if cui:
                    current_xrefs.append(cui)
    flush()
    return labels, umls_xrefs


def read_hpo_annotation_ids(
    *,
    phenotype_annotations_path: str | Path | None = None,
    genes_to_phenotype_path: str | Path | None = None,
) -> tuple[set[str], set[str], set[str], dict[str, str]]:
    disease_ids: set[str] = set()
    hpo_ids: set[str] = set()
    gene_symbols: set[str] = set()
    disease_labels: dict[str, str] = {}
    if phenotype_annotations_path:
        with Path(phenotype_annotations_path).expanduser().open(
            "r", encoding="utf-8", errors="replace"
        ) as handle:
            for line in handle:
                if line.startswith("#") or not line.strip():
                    continue
                fields = line.rstrip("\n").split("\t")
                if fields and fields[0] == "database_id":
                    continue
                if len(fields) < 4:
                    continue
                disease_id, disease_name, _qualifier, hpo_id = fields[:4]
                if disease_id:
                    disease_ids.add(disease_id)
                    if disease_name and disease_id not in disease_labels:
                        disease_labels[disease_id] = disease_name
                if hpo_id:
                    hpo_ids.add(hpo_id)
    if genes_to_phenotype_path:
        with Path(genes_to_phenotype_path).expanduser().open(
            "r", encoding="utf-8", errors="replace"
        ) as handle:
            for line in handle:
                if line.startswith("#") or not line.strip():
                    continue
                fields = line.rstrip("\n").split("\t")
                if fields and fields[0] == "ncbi_gene_id":
                    continue
                if len(fields) < 6:
                    continue
                _gene_id, symbol, hpo_id, _hpo_name, _frequency, disease_id = fields[:6]
                if symbol:
                    gene_symbols.add(symbol)
                if hpo_id:
                    hpo_ids.add(hpo_id)
                if disease_id:
                    disease_ids.add(disease_id)
    return disease_ids, hpo_ids, gene_symbols, disease_labels


def _gene_label_keys(symbols: set[str]) -> dict[str, str]:
    keys: dict[str, str] = {}
    for symbol in symbols:
        normalized = symbol.casefold()
        if normalized:
            keys[normalized] = symbol
            keys[f"{normalized} gene"] = symbol
    return keys


def collect_hpo_mrconso_mappings(
    *,
    mrconso_path: str | Path,
    disease_ids: set[str],
    gene_symbols: set[str],
    semantic_types: dict[str, set[str]],
) -> tuple[dict[str, set[str]], dict[str, tuple[str, str]], dict[str, str]]:
    disease_key_to_ids: dict[tuple[str, str], set[str]] = {}
    for disease_id in disease_ids:
        key = hpo_database_key(disease_id)
        if key:
            disease_key_to_ids.setdefault(key, set()).add(disease_id)

    disease_id_to_cuis: dict[str, set[str]] = {}
    gene_keys = _gene_label_keys(gene_symbols)
    gene_candidates: dict[str, tuple[tuple[int, int, int, str], str, str]] = {}
    gene_sab_rank = {"HGNC": 0, "NCI": 2, "OMIM": 3, "MEDLINEPLUS": 4, "LNC": 5, "MTH": 6}
    gene_tty_rank = {"ACR": 0, "MTH_ACR": 1, "PT": 2, "PN": 3, "SY": 4, "LPN": 5, "LPDN": 6}
    disease_labels: dict[str, str] = {}

    with Path(mrconso_path).expanduser().open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("|")
            if len(fields) < 17 or fields[1] != "ENG":
                continue
            cui = fields[0]
            sab = fields[11]
            tty = fields[12]
            code = fields[13]
            label = fields[14].strip()
            suppress = fields[16]
            if suppress != "N" or not label:
                continue
            disease_key = (sab, code)
            if disease_key in disease_key_to_ids and semantic_category(semantic_types.get(cui) or set()) == "condition":
                for disease_id in disease_key_to_ids[disease_key]:
                    disease_id_to_cuis.setdefault(disease_id, set()).add(cui)
                    disease_labels.setdefault(cui, label)
            symbol = gene_keys.get(label.casefold())
            if not symbol or semantic_category(semantic_types.get(cui) or set()) != "gene_protein":
                continue
            label_penalty = 0 if label.casefold() == symbol.casefold() else 1
            rank = (
                gene_sab_rank.get(sab, 99),
                label_penalty,
                gene_tty_rank.get(tty, 99),
                label.casefold(),
            )
            current = gene_candidates.get(symbol)
            if current is None or rank < current[0]:
                gene_candidates[symbol] = (rank, cui, label)

    gene_symbol_to_cui_label = {
        symbol: (cui, label) for symbol, (_rank, cui, label) in gene_candidates.items()
    }
    return disease_id_to_cuis, gene_symbol_to_cui_label, disease_labels


def add_research_relation_row(
    buckets: dict[tuple[str, str], dict[str, tuple[tuple, ResearchRelationRow]]],
    row: ResearchRelationRow,
    sort_key: tuple,
    *,
    max_relations_per_category: int,
) -> None:
    key = (row.source_cui, row.category)
    bucket = buckets.setdefault(key, {})
    current = bucket.get(row.target_cui)
    if current is None or sort_key < current[0]:
        bucket[row.target_cui] = (sort_key, row)
    if len(bucket) > max_relations_per_category * 8:
        kept = sorted(bucket.values(), key=lambda item: item[0])[: max_relations_per_category * 4]
        buckets[key] = {item.target_cui: (sort_key, item) for sort_key, item in kept}


def source_semantic_type_for(cui: str, semantic_types: dict[str, set[str]]) -> str:
    types = semantic_types.get(cui) or set()
    return best_semantic_type(types, semantic_category(types))


def collect_hpo_research_relation_rows(
    *,
    hpo_obo_path: str | Path,
    phenotype_annotations_path: str | Path,
    genes_to_phenotype_path: str | Path,
    mrconso_path: str | Path,
    semantic_types: dict[str, set[str]],
    source_cuis: set[str],
    max_relations_per_category: int = 12,
) -> list[tuple[ResearchRelationRow, int]]:
    hpo_labels, hpo_umls_xrefs = parse_hpo_obo(hpo_obo_path)
    disease_ids, _hpo_ids, gene_symbols, annotation_disease_labels = read_hpo_annotation_ids(
        phenotype_annotations_path=phenotype_annotations_path,
        genes_to_phenotype_path=genes_to_phenotype_path,
    )
    disease_id_to_cuis, gene_symbol_to_cui_label, mrconso_disease_labels = collect_hpo_mrconso_mappings(
        mrconso_path=mrconso_path,
        disease_ids=disease_ids,
        gene_symbols=gene_symbols,
        semantic_types=semantic_types,
    )
    buckets: dict[tuple[str, str], dict[str, tuple[tuple, ResearchRelationRow]]] = {}
    evidence_rank = {"PCS": 0, "TAS": 1, "IEA": 2}

    with Path(phenotype_annotations_path).expanduser().open(
        "r", encoding="utf-8", errors="replace"
    ) as handle:
        for line in handle:
            if line.startswith("#") or not line.strip():
                continue
            fields = line.rstrip("\n").split("\t")
            if fields and fields[0] == "database_id":
                continue
            if len(fields) < 12:
                continue
            disease_id, disease_name, qualifier, hpo_id, _reference, evidence = fields[:6]
            aspect = fields[10]
            if qualifier == "NOT" or aspect != "P":
                continue
            target_cuis = hpo_umls_xrefs.get(hpo_id) or []
            if not target_cuis:
                continue
            target_label = hpo_labels.get(hpo_id) or hpo_id
            for source_cui in disease_id_to_cuis.get(disease_id, set()):
                if source_cui not in source_cuis:
                    continue
                for target_cui in target_cuis[:1]:
                    row = ResearchRelationRow(
                        source_cui=source_cui,
                        target_cui=target_cui,
                        category="phenotype",
                        relation_group="phenotype",
                        relation="RO",
                        rela="has_phenotype",
                        sab="HPO",
                        direction="outgoing",
                        label=target_label,
                        source_semantic_type=source_semantic_type_for(source_cui, semantic_types),
                        target_semantic_type="human phenotype",
                    )
                    add_research_relation_row(
                        buckets,
                        row,
                        (
                            evidence_rank.get(evidence, 9),
                            target_label.casefold(),
                            target_cui,
                            disease_name.casefold(),
                        ),
                        max_relations_per_category=max_relations_per_category,
                    )

    gene_disease_counts: dict[tuple[str, str], int] = {}
    gene_phenotype_counts: dict[tuple[str, str], int] = {}
    gene_phenotype_names: dict[str, str] = {}
    gene_disease_names: dict[str, str] = {}
    with Path(genes_to_phenotype_path).expanduser().open(
        "r", encoding="utf-8", errors="replace"
    ) as handle:
        for line in handle:
            if line.startswith("#") or not line.strip():
                continue
            fields = line.rstrip("\n").split("\t")
            if fields and fields[0] == "ncbi_gene_id":
                continue
            if len(fields) < 6:
                continue
            _gene_id, symbol, hpo_id, hpo_name, _frequency, disease_id = fields[:6]
            if symbol and disease_id:
                gene_disease_counts[(symbol, disease_id)] = gene_disease_counts.get((symbol, disease_id), 0) + 1
            if symbol and hpo_id:
                gene_phenotype_counts[(symbol, hpo_id)] = gene_phenotype_counts.get((symbol, hpo_id), 0) + 1
                if hpo_name:
                    gene_phenotype_names.setdefault(hpo_id, hpo_name)
            if disease_id:
                gene_disease_names.setdefault(disease_id, annotation_disease_labels.get(disease_id, disease_id))

    for (symbol, disease_id), count in gene_disease_counts.items():
        gene_mapping = gene_symbol_to_cui_label.get(symbol)
        disease_cuis = disease_id_to_cuis.get(disease_id) or set()
        if not gene_mapping or not disease_cuis:
            continue
        gene_cui, gene_label = gene_mapping
        disease_label = (
            annotation_disease_labels.get(disease_id)
            or gene_disease_names.get(disease_id)
            or disease_id
        )
        for disease_cui in disease_cuis:
            if disease_cui in source_cuis:
                row = ResearchRelationRow(
                    source_cui=disease_cui,
                    target_cui=gene_cui,
                    category="gene_protein",
                    relation_group="genetic_association",
                    relation="RO",
                    rela="disease_has_associated_gene",
                    sab="HPO",
                    direction="outgoing",
                    label=gene_label,
                    source_semantic_type=source_semantic_type_for(disease_cui, semantic_types),
                    target_semantic_type=source_semantic_type_for(gene_cui, semantic_types),
                )
                add_research_relation_row(
                    buckets,
                    row,
                    (-count, gene_label.casefold(), gene_cui),
                    max_relations_per_category=max_relations_per_category,
                )
            if gene_cui in source_cuis:
                row = ResearchRelationRow(
                    source_cui=gene_cui,
                    target_cui=disease_cui,
                    category="condition",
                    relation_group="genetic_association",
                    relation="RO",
                    rela="gene_associated_with_disease",
                    sab="HPO",
                    direction="outgoing",
                    label=mrconso_disease_labels.get(disease_cui) or disease_label,
                    source_semantic_type=source_semantic_type_for(gene_cui, semantic_types),
                    target_semantic_type=source_semantic_type_for(disease_cui, semantic_types),
                )
                add_research_relation_row(
                    buckets,
                    row,
                    (-count, row.label.casefold(), disease_cui),
                    max_relations_per_category=max_relations_per_category,
                )

    for (symbol, hpo_id), count in gene_phenotype_counts.items():
        gene_mapping = gene_symbol_to_cui_label.get(symbol)
        target_cuis = hpo_umls_xrefs.get(hpo_id) or []
        if not gene_mapping or not target_cuis:
            continue
        gene_cui, _gene_label = gene_mapping
        if gene_cui not in source_cuis:
            continue
        target_label = hpo_labels.get(hpo_id) or gene_phenotype_names.get(hpo_id) or hpo_id
        for target_cui in target_cuis[:1]:
            row = ResearchRelationRow(
                source_cui=gene_cui,
                target_cui=target_cui,
                category="phenotype",
                relation_group="phenotype",
                relation="RO",
                rela="gene_has_phenotype",
                sab="HPO",
                direction="outgoing",
                label=target_label,
                source_semantic_type=source_semantic_type_for(gene_cui, semantic_types),
                target_semantic_type="human phenotype",
            )
            add_research_relation_row(
                buckets,
                row,
                (-count, target_label.casefold(), target_cui),
                max_relations_per_category=max_relations_per_category,
            )

    rows: list[tuple[ResearchRelationRow, int]] = []
    for (_source_cui, _category), bucket in buckets.items():
        for rank, (_sort_key, row) in enumerate(
            sorted(bucket.values(), key=lambda item: item[0])[:max_relations_per_category],
            start=1,
        ):
            rows.append((row, rank))
    return rows


def insert_research_relation_rows(
    conn: sqlite3.Connection,
    rows: list[tuple[ResearchRelationRow, int]],
) -> None:
    conn.executemany(
        """
        INSERT INTO research_relations(
            source_cui, target_cui, category, relation_group, relation, rela, sab,
            direction, label, source_semantic_type, target_semantic_type, rank
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row.source_cui,
                row.target_cui,
                row.category,
                row.relation_group,
                row.relation,
                row.rela,
                row.sab,
                row.direction,
                row.label,
                row.source_semantic_type,
                row.target_semantic_type,
                rank,
            )
            for row, rank in rows
        ],
    )


def build_research_relation_index(
    *,
    mrrel_path: str | Path,
    mrconso_path: str | Path,
    mrsty_path: str | Path,
    out_path: str | Path,
    doc_paths: Iterable[str | Path] = (),
    source_cuis: set[str] | None = None,
    max_relations_per_category: int = 12,
    include_inverse: bool = True,
    include_suppressed: bool = False,
    hpo_obo_path: str | Path | None = None,
    hpo_phenotype_annotations_path: str | Path | None = None,
    hpo_genes_to_phenotype_path: str | Path | None = None,
    replace: bool = True,
) -> dict[str, int]:
    doc_labels, doc_cuis = read_doc_labels(doc_paths)
    cuis = set(source_cuis or set())
    cuis.update(doc_cuis)
    semantic_types = load_semantic_types(mrsty_path)
    candidates = collect_research_relation_candidates(
        mrrel_path=mrrel_path,
        source_cuis=cuis,
        semantic_types=semantic_types,
        max_relations_per_category=max_relations_per_category,
        include_inverse=include_inverse,
        include_suppressed=include_suppressed,
    )
    target_cuis = {candidate.target_cui for values in candidates.values() for candidate in values}
    missing_label_cuis = target_cuis - set(doc_labels)
    mrconso_labels = collect_labels(mrconso_path, missing_label_cuis, max_labels=1)
    conn = connect(out_path)
    if replace:
        conn.execute("DROP TABLE IF EXISTS research_relations")
    conn.executescript(TABLE_SCHEMA)
    batch = []
    for (_source_cui, category), values in candidates.items():
        for rank, candidate in enumerate(sorted(values, key=candidate_sort_key), start=1):
            label = doc_labels.get(candidate.target_cui)
            if not label:
                label = (mrconso_labels.get(candidate.target_cui) or [candidate.target_cui])[0]
            batch.append(
                (
                    candidate.source_cui,
                    candidate.target_cui,
                    category,
                    candidate.relation_group,
                    candidate.relation,
                    candidate.rela,
                    candidate.sab,
                    candidate.direction,
                    label,
                    candidate.source_semantic_type,
                    candidate.target_semantic_type,
                    rank,
                )
            )
    conn.executemany(
        """
        INSERT INTO research_relations(
            source_cui, target_cui, category, relation_group, relation, rela, sab,
            direction, label, source_semantic_type, target_semantic_type, rank
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        batch,
    )
    conn.executescript(INDEX_SCHEMA)
    hpo_rows: list[tuple[ResearchRelationRow, int]] = []
    if hpo_obo_path and hpo_phenotype_annotations_path and hpo_genes_to_phenotype_path:
        hpo_rows = collect_hpo_research_relation_rows(
            hpo_obo_path=hpo_obo_path,
            phenotype_annotations_path=hpo_phenotype_annotations_path,
            genes_to_phenotype_path=hpo_genes_to_phenotype_path,
            mrconso_path=mrconso_path,
            semantic_types=semantic_types,
            source_cuis=cuis,
            max_relations_per_category=max_relations_per_category,
        )
        insert_research_relation_rows(conn, hpo_rows)
        conn.executescript(INDEX_SCHEMA)
    conn.commit()
    conn.close()
    return {
        "source_cuis": len(cuis),
        "sources_with_relations": len({key[0] for key in candidates} | {row.source_cui for row, _ in hpo_rows}),
        "target_cuis": len(target_cuis | {row.target_cui for row, _ in hpo_rows}),
        "relations": len(batch) + len(hpo_rows),
        "hpo_relations": len(hpo_rows),
        "categories": len({key[1] for key in candidates} | {row.category for row, _ in hpo_rows}),
    }


class ResearchRelationIndex:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self._local = threading.local()
        self.cache: dict[tuple[str, int], list[dict]] = {}

    def connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = connect(self.path)
            self._local.conn = conn
        return conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def source_count(self) -> int:
        row = self.connection().execute(
            "SELECT COUNT(DISTINCT source_cui) AS count FROM research_relations"
        ).fetchone()
        return int(row["count"] or 0)

    def relation_count(self) -> int:
        row = self.connection().execute("SELECT COUNT(*) AS count FROM research_relations").fetchone()
        return int(row["count"] or 0)

    def lookup(self, cui: str, *, limit_per_category: int = 6) -> list[dict]:
        key = (cui, limit_per_category)
        cached = self.cache.get(key)
        if cached is not None:
            return [dict(item) for item in cached]
        rows = self.connection().execute(
            """
            SELECT target_cui, category, relation_group, relation, rela, sab, direction,
                   label, source_semantic_type, target_semantic_type, rank
            FROM research_relations
            WHERE source_cui = ?
            ORDER BY
              CASE category
                WHEN 'drug_chemical' THEN 0
                WHEN 'gene_protein' THEN 1
                WHEN 'phenotype' THEN 2
                WHEN 'procedure_test' THEN 3
                WHEN 'condition' THEN 4
                WHEN 'organism' THEN 5
                WHEN 'device' THEN 6
                ELSE 99
              END,
              rank ASC,
              CASE sab WHEN 'HPO' THEN 0 WHEN 'MED-RT' THEN 1 WHEN 'MSH' THEN 2 ELSE 9 END,
              label ASC
            """,
            (cui,),
        )
        category_counts: dict[str, int] = {}
        seen: set[tuple[str, str]] = set()
        results = []
        for row in rows:
            category = row["category"]
            dedupe_key = (category, row["target_cui"])
            if dedupe_key in seen:
                continue
            if category_counts.get(category, 0) >= limit_per_category:
                continue
            seen.add(dedupe_key)
            category_counts[category] = category_counts.get(category, 0) + 1
            results.append(
                attach_universal_edge(
                    {
                        "source_cui": cui,
                        "target_cui": row["target_cui"],
                        "cui": row["target_cui"],
                        "category": category,
                        "category_label": TARGET_LABELS.get(category, category),
                        "relation_group": row["relation_group"],
                        "relation": row["relation"],
                        "rela": row["rela"],
                        "source": row["sab"],
                        "direction": row["direction"],
                        "label": row["label"],
                        "source_semantic_type": row["source_semantic_type"],
                        "semantic_type": row["target_semantic_type"],
                        "rank": int(row["rank"] or 0),
                    },
                    subject_cui=cui,
                    object_cui=row["target_cui"],
                )
            )
        self.cache[key] = [dict(item) for item in results]
        return results

    def lookup_incoming(self, cui: str, *, limit: int = 48) -> list[dict]:
        key = (f"incoming:{cui}", limit)
        cached = self.cache.get(key)
        if cached is not None:
            return [dict(item) for item in cached]
        rows = self.connection().execute(
            """
            SELECT source_cui, target_cui, category, relation_group, relation, rela, sab,
                   direction, label, source_semantic_type, target_semantic_type, rank
            FROM research_relations
            WHERE target_cui = ?
            ORDER BY rank ASC, label ASC
            LIMIT ?
            """,
            (cui, limit),
        )
        results = [
            attach_universal_edge(
                {
                    "source_cui": row["source_cui"],
                    "target_cui": row["target_cui"],
                    "category": row["category"],
                    "category_label": TARGET_LABELS.get(row["category"], row["category"]),
                    "relation_group": row["relation_group"],
                    "relation": row["relation"],
                    "rela": row["rela"],
                    "source": row["sab"],
                    "direction": row["direction"],
                    "label": row["label"],
                    "source_semantic_type": row["source_semantic_type"],
                    "target_semantic_type": row["target_semantic_type"],
                    "rank": int(row["rank"] or 0),
                },
                subject_cui=row["source_cui"],
                object_cui=row["target_cui"],
            )
            for row in rows
        ]
        self.cache[key] = [dict(item) for item in results]
        return results
