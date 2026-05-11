from __future__ import annotations


SEMANTIC_PROFILES: dict[str, set[str] | None] = {
    "all-biomedicine": None,
    "clinical": {
        "Acquired Abnormality",
        "Anatomical Abnormality",
        "Cell or Molecular Dysfunction",
        "Congenital Abnormality",
        "Disease or Syndrome",
        "Experimental Model of Disease",
        "Finding",
        "Injury or Poisoning",
        "Mental or Behavioral Dysfunction",
        "Neoplastic Process",
        "Pathologic Function",
        "Sign or Symptom",
    },
    "chemicals-drugs": {
        "Antibiotic",
        "Biomedical or Dental Material",
        "Chemical",
        "Chemical Viewed Functionally",
        "Chemical Viewed Structurally",
        "Clinical Drug",
        "Element, Ion, or Isotope",
        "Hazardous or Poisonous Substance",
        "Hormone",
        "Immunologic Factor",
        "Indicator, Reagent, or Diagnostic Aid",
        "Inorganic Chemical",
        "Organic Chemical",
        "Pharmacologic Substance",
        "Receptor",
        "Vitamin",
    },
    "genes-proteins": {
        "Amino Acid, Peptide, or Protein",
        "Biologically Active Substance",
        "Enzyme",
        "Gene or Genome",
        "Molecular Function",
        "Nucleic Acid, Nucleoside, or Nucleotide",
    },
    "anatomy": {
        "Anatomical Structure",
        "Body Location or Region",
        "Body Part, Organ, or Organ Component",
        "Body Space or Junction",
        "Cell",
        "Cell Component",
        "Embryonic Structure",
        "Fully Formed Anatomical Structure",
        "Tissue",
    },
    "procedures-devices": {
        "Diagnostic Procedure",
        "Educational Activity",
        "Health Care Activity",
        "Laboratory Procedure",
        "Medical Device",
        "Molecular Biology Research Technique",
        "Research Activity",
        "Therapeutic or Preventive Procedure",
    },
    "organisms": {
        "Alga",
        "Amphibian",
        "Animal",
        "Archaeon",
        "Bacterium",
        "Bird",
        "Eukaryote",
        "Fish",
        "Fungus",
        "Human",
        "Invertebrate",
        "Mammal",
        "Organism",
        "Plant",
        "Reptile",
        "Rickettsia or Chlamydia",
        "Vertebrate",
        "Virus",
    },
    "labs-measurements": {
        "Clinical Attribute",
        "Laboratory Procedure",
        "Laboratory or Test Result",
        "Qualitative Concept",
        "Quantitative Concept",
    },
}

DEFAULT_BIOMEDICINE_PROFILES = (
    "clinical",
    "chemicals-drugs",
    "genes-proteins",
    "anatomy",
    "procedures-devices",
    "organisms",
    "labs-measurements",
)


def profile_names() -> list[str]:
    return sorted(SEMANTIC_PROFILES)


def biomedicine_profile_names() -> list[str]:
    return list(DEFAULT_BIOMEDICINE_PROFILES)


def resolve_profiles(profile_values: list[str] | None) -> set[str] | None:
    if not profile_values:
        return set()
    resolved: set[str] = set()
    for profile in profile_values:
        if profile not in SEMANTIC_PROFILES:
            raise ValueError(f"unknown semantic profile: {profile}")
        values = SEMANTIC_PROFILES[profile]
        if values is None:
            return None
        resolved.update(values)
    return resolved
