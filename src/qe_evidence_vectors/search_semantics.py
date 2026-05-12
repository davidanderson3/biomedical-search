from __future__ import annotations


SEMANTIC_VIEW_CATEGORY_LABELS = {
    "anatomy": "Anatomy",
    "condition": "Disorders",
    "phenotype": "Phenomena and Phenotypes",
    "gene_protein": "Genes and Molecular Sequences",
    "drug_chemical": "Chemicals and Drugs",
    "observation_lab": "Observations and Lab Results",
    "procedure_test": "Procedures",
    "device": "Devices",
    "organism": "Living Beings",
}
SEMANTIC_GROUP_LABELS = {
    "ACTI": "Activities and Behaviors",
    "ANAT": "Anatomy",
    "CHEM": "Chemicals and Drugs",
    "CONC": "Concepts and Ideas",
    "DEVI": "Devices",
    "DISO": "Disorders",
    "GENE": "Genes and Molecular Sequences",
    "GEOG": "Geographic Areas",
    "LIVB": "Living Beings",
    "OBS": "Observations and Lab Results",
    "OBJC": "Objects",
    "OCCU": "Occupations",
    "ORGA": "Organizations",
    "PHEN": "Phenomena",
    "PHYS": "Physiology",
    "PROC": "Procedures",
}
RELATION_CATEGORY_SEMANTIC_GROUPS = {
    "anatomy": "ANAT",
    "condition": "DISO",
    "phenotype": "PHEN",
    "gene_protein": "GENE",
    "drug_chemical": "CHEM",
    "observation_lab": "OBS",
    "procedure_test": "PROC",
    "device": "DEVI",
    "organism": "LIVB",
}
EXTERNAL_EMBEDDING_GROUP_CATEGORIES = {
    "DISO": "condition",
    "CHEM": "drug_chemical",
    "GENE": "gene_protein",
    "PROC": "procedure_test",
    "DEVI": "device",
    "LIVB": "organism",
    "ANAT": "anatomy",
    "PHEN": "phenotype",
    "PHYS": "phenotype",
    "OBS": "observation_lab",
}
SEMANTIC_VIEW_CATEGORY_ORDER = {
    "drug_chemical": 0,
    "gene_protein": 1,
    "phenotype": 2,
    "observation_lab": 3,
    "procedure_test": 4,
    "anatomy": 5,
    "condition": 6,
    "device": 7,
    "organism": 8,
}
SEMANTIC_GROUP_VIEW_ORDER = {
    "CHEM": 0,
    "GENE": 1,
    "PHEN": 2,
    "OBS": 3,
    "PROC": 4,
    "DISO": 5,
    "DEVI": 6,
    "ANAT": 7,
    "LIVB": 8,
}
SEMANTIC_GROUP_VIEW_PRESETS = {
    "DISO": ("drug_chemical", "gene_protein", "phenotype", "observation_lab", "procedure_test", "anatomy", "organism"),
    "GENE": ("condition", "phenotype", "drug_chemical", "observation_lab", "procedure_test"),
    "CHEM": ("condition", "gene_protein", "phenotype", "observation_lab", "procedure_test"),
    "PROC": ("condition", "device", "anatomy", "observation_lab", "phenotype", "gene_protein"),
    "DEVI": ("procedure_test", "condition", "drug_chemical"),
    "LIVB": ("condition", "drug_chemical", "procedure_test"),
    "ANAT": ("condition", "procedure_test", "phenotype", "gene_protein"),
    "OBS": ("condition", "drug_chemical", "procedure_test", "phenotype", "anatomy"),
    "PHEN": ("condition", "gene_protein", "drug_chemical", "observation_lab", "procedure_test"),
    "PHYS": ("condition", "gene_protein", "drug_chemical", "observation_lab", "procedure_test"),
    "OTHER": ("condition", "drug_chemical", "gene_protein", "phenotype", "observation_lab", "procedure_test"),
}
LOCAL_EXTENSION_SEMANTIC_TYPES = {
    "disease or syndrome": {"tui": "T047", "stn": "B2.2.1.2.1", "name": "Disease or Syndrome"},
    "finding": {"tui": "T033", "stn": "A2.2", "name": "Finding"},
    "pathologic function": {"tui": "T046", "stn": "B2.2.1.2", "name": "Pathologic Function"},
    "sign or symptom": {"tui": "T184", "stn": "A2.2.2", "name": "Sign or Symptom"},
    "diagnostic procedure": {"tui": "T060", "stn": "B1.3.1.2.1", "name": "Diagnostic Procedure"},
    "laboratory procedure": {"tui": "T059", "stn": "B1.3.1.2.1", "name": "Laboratory Procedure"},
    "therapeutic or preventive procedure": {
        "tui": "T061",
        "stn": "B1.3.1.2.2",
        "name": "Therapeutic or Preventive Procedure",
    },
    "medical device": {"tui": "T074", "stn": "A1.3", "name": "Medical Device"},
    "clinical attribute": {"tui": "T201", "stn": "A2.3.3", "name": "Clinical Attribute"},
    "gene or genome": {"tui": "T028", "stn": "A1.2.3.5", "name": "Gene or Genome"},
}
LOCAL_EXTENSION_FIELD_SEMANTIC_TYPES = {
    "condition": "Disease or Syndrome",
    "complication": "Pathologic Function",
    "context": "Finding",
    "finding": "Finding",
    "gene": "Gene or Genome",
    "result": "Finding",
    "symptom": "Sign or Symptom",
    "procedure": "Therapeutic or Preventive Procedure",
    "test": "Diagnostic Procedure",
    "device": "Medical Device",
}
SEMANTIC_GROUP_RELATION_CATEGORIES = {
    semantic_group: category
    for category, semantic_group in RELATION_CATEGORY_SEMANTIC_GROUPS.items()
}
CONDITION_VIEW_SEMANTIC_TYPES = {
    "acquired abnormality",
    "anatomical abnormality",
    "cell or molecular dysfunction",
    "congenital abnormality",
    "disease or syndrome",
    "experimental model of disease",
    "finding",
    "injury or poisoning",
    "mental or behavioral dysfunction",
    "neoplastic process",
    "pathologic function",
    "sign or symptom",
}
GENE_PROTEIN_VIEW_SEMANTIC_TYPES = {
    "amino acid, peptide, or protein",
    "enzyme",
    "gene or genome",
    "immunologic factor",
    "nucleic acid, nucleoside, or nucleotide",
    "receptor",
}
DRUG_CHEMICAL_VIEW_SEMANTIC_TYPES = {
    "antibiotic",
    "biologically active substance",
    "biomedical or dental material",
    "chemical",
    "chemical viewed functionally",
    "chemical viewed structurally",
    "clinical drug",
    "element, ion, or isotope",
    "hazardous or poisonous substance",
    "indicator, reagent, or diagnostic aid",
    "inorganic chemical",
    "organic chemical",
    "pharmacologic substance",
    "steroid",
    "vitamin",
}
PROCEDURE_TEST_VIEW_SEMANTIC_TYPES = {
    "diagnostic procedure",
    "health care activity",
    "molecular biology research technique",
    "research activity",
    "therapeutic or preventive procedure",
}
OBSERVATION_LAB_VIEW_SEMANTIC_TYPES = {
    "clinical attribute",
    "laboratory or test result",
    "laboratory procedure",
}
DEVICE_VIEW_SEMANTIC_TYPES = {
    "drug delivery device",
    "medical device",
    "research device",
}
ORGANISM_VIEW_SEMANTIC_TYPES = {
    "amphibian",
    "animal",
    "archaeon",
    "bacterium",
    "bird",
    "eukaryote",
    "fish",
    "fungus",
    "human",
    "invertebrate",
    "mammal",
    "organism",
    "plant",
    "reptile",
    "rickettsia or chlamydia",
    "virus",
}
ANATOMY_VIEW_SEMANTIC_TYPES = {
    "anatomical structure",
    "body location or region",
    "body part, organ, or organ component",
    "body space or junction",
    "cell",
    "cell component",
    "embryonic structure",
    "fully formed anatomical structure",
    "tissue",
}
PHENOMENA_VIEW_SEMANTIC_TYPES = {
    "environmental effect of humans",
    "human-caused phenomenon or process",
    "natural phenomenon or process",
    "phenomenon or process",
}
PHYSIOLOGY_VIEW_SEMANTIC_TYPES = {
    "biologic function",
    "cell function",
    "genetic function",
    "mental process",
    "molecular function",
    "organ or tissue function",
    "organism attribute",
    "organism function",
    "physiologic function",
}


def semantic_type_name_set(types: list[dict] | tuple[dict, ...]) -> set[str]:
    names = set()
    for item in types or []:
        if isinstance(item, dict):
            value = item.get("name") or item.get("sty") or item.get("semantic_type") or ""
        else:
            value = str(item)
        value = str(value).strip().lower()
        if value:
            names.add(value)
    return names


def local_extension_semantic_type_rows(
    semantic_type: str,
    *,
    field: str = "",
) -> list[dict]:
    semantic_type = str(semantic_type or "").strip()
    field = str(field or "").strip()
    mapped_name = semantic_type
    if semantic_type.lower() == "clinical concept":
        mapped_name = LOCAL_EXTENSION_FIELD_SEMANTIC_TYPES.get(field.lower(), "Finding")
    row_template = LOCAL_EXTENSION_SEMANTIC_TYPES.get(mapped_name.lower())
    if not row_template:
        return []
    row = dict(row_template)
    row["sty"] = row["name"]
    row["atui"] = "LOCAL_EXTENSION"
    row["source"] = "local_extension"
    if semantic_type and semantic_type != row["name"]:
        row["local_semantic_type"] = semantic_type
    if field:
        row["local_field"] = field
    return [row]


def semantic_group_from_types(types: list[dict] | tuple[dict, ...]) -> str:
    names = semantic_type_name_set(types)
    if names & CONDITION_VIEW_SEMANTIC_TYPES:
        return "DISO"
    if names & DRUG_CHEMICAL_VIEW_SEMANTIC_TYPES:
        return "CHEM"
    if names & GENE_PROTEIN_VIEW_SEMANTIC_TYPES:
        return "GENE"
    if names & OBSERVATION_LAB_VIEW_SEMANTIC_TYPES:
        return "OBS"
    if names & PROCEDURE_TEST_VIEW_SEMANTIC_TYPES:
        return "PROC"
    if names & DEVICE_VIEW_SEMANTIC_TYPES:
        return "DEVI"
    if names & ORGANISM_VIEW_SEMANTIC_TYPES:
        return "LIVB"
    if names & ANATOMY_VIEW_SEMANTIC_TYPES:
        return "ANAT"
    if names & PHENOMENA_VIEW_SEMANTIC_TYPES:
        return "PHEN"
    if names & PHYSIOLOGY_VIEW_SEMANTIC_TYPES:
        return "PHYS"
    return "OTHER"


def semantic_group_metadata(types: list[dict] | tuple[dict, ...]) -> dict:
    group = semantic_group_from_types(types)
    return {
        "semantic_group": group,
        "semantic_group_label": SEMANTIC_GROUP_LABELS.get(group, "Other"),
    }
