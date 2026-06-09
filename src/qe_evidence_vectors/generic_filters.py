from __future__ import annotations

from .text import normalized_key


# Narrow, audited suppression list for UMLS labels that behave like ordinary
# prose/research phrasing rather than useful biomedical retrieval anchors.
BLOCKED_GENERIC_LABELS = {
    "abnormal",
    "at home",
    "at least daily",
    "at work",
    "chart [medical device]",
    "code system type internal",
    "control aspects",
    "control veterinary product",
    "developing countries",
    "developing country",
    "degree or extent",
    "disease management",
    "domestic",
    "elevated",
    "entity risk aggressive",
    "examined",
    "extremely limited",
    "fluid behavior",
    "found down",
    "greater",
    "greater than",
    "greater than or equal to",
    "hormones",
    "increase in pressure medical device problem",
    "identified",
    "intact",
    "intake",
    "intake treatment",
    "intimate",
    "intent",
    "irregular",
    "inconsistent",
    "less than",
    "less than or equal to",
    "lower risk",
    "large blood vessel structure",
    "levels",
    "levels qualifier value",
    "management",
    "mechanical treatments",
    "mediation analysis",
    "needs",
    "narrowing",
    "notable",
    "organism strain",
    "other than",
    "pain pressure",
    "partial",
    "partial thickness",
    "pigmented",
    "placement",
    "placement action",
    "present",
    "prescription procedure",
    "pressure",
    "pressure finding",
    "problem",
    "prevent product",
    "preventive monitoring",
    "primary",
    "patient history",
    "rather",
    "range",
    "removed",
    "residual",
    "restart",
    "revealed",
    "reveals",
    "rnix intake",
    "rnax nursing therapy actions",
    "second degree",
    "setting",
    "settings",
    "settings qualitative",
    "sterile",
    "sterile qualifier value",
    "study results",
    "stones unit",
    "source",
    "structure of large artery",
    "take",
    "thick",
    "too little",
    "tests",
    "tests and testing",
    "therapeutic procedure",
    "true control status",
    "uncomplicated",
    "unable",
    "validation",
    "watery",
}

BLOCKED_GENERIC_QUERIES = BLOCKED_GENERIC_LABELS | {
    "large",
}

BLOCKED_GENERIC_CUIS = {
    "C0205161",  # Abnormal
    "C0205307",  # Normal
    "C0205266",  # Intact
    "C0150312",  # Present
    "C0007963",  # chart [medical device]
    "C0027552",  # Needs
    "C0033213",  # Problem
    "C0033080",  # Prescription (procedure)
    "C0087111",  # Therapeutic procedure
    "C0150369",  # Preventive monitoring
    "C0243148",  # control aspects
    "C0308718",  # CONTROL veterinary product
    "C0376636",  # Disease Management / management
    "C0439090",  # Less Than or Equal To
    "C0439091",  # Greater Than or Equal To
    "C0439092",  # Less Than
    "C0439093",  # Greater Than
    "C0439661",  # Acquired (qualifier value)
    "C0441889",  # Levels (qualifier value)
    "C0441994",  # Lower
    "C0442809",  # Inconsistent
    "C0443334",  # Uncomplicated
    "C0449286",  # Degree or extent
    "C0449416",  # Source
    "C0332128",  # Examined
    "C0444611",  # Fluid behavior
    "C0547044",  # Smaller / Less
    "C0549177",  # Large / Big
    "C0699756",  # Intimate (qualifier value)
    "C0309872",  # PREVENT (product)
    "C1553872",  # Code System Type - Internal
    "C0699886",  # Mechanical Treatments
    "C0700321",  # Small
    "C0683954",  # Study Results
    "C0683443",  # tests and testing
    "C0814912",  # Mediation Analysis
    "C0225990",  # Large blood vessel structure
    "C0226003",  # Structure of large artery
    "C0679831",  # Patient History
    "C0205217",  # Increased
    "C0205250",  # Higher
    "C0205396",  # Identified
    "C0849355",  # Removed
    "C1280412",  # Thick
    "C1264633",  # Fraction of
    "C1457868",  # Worse
    "C1514902",  # Restart (start again)
    "C1514721",  # Range
    "C1519941",  # Validation
    "C1515187",  # Take - dosing instruction imperative
    "C4521161",  # Intake (treatment) - generic health-care activity fragment
    "C1548802",  # Body Site Modifier - Lower
    "C0443289",  # Revealed / reveals
    "C0028678",  # RNAx nursing therapy actions
    "C4534363",  # At home
    "C0744212",  # Found down
    "C1299582",  # Unable
    "C1318139",  # {Setting}
    "C1704243",  # Greater / Larger
    "C1550458",  # Abnormal
    "C3274648",  # True Control Status
    "C0022885",  # Tests
    "C1881187",  # Increase in Pressure Medical Device Problem
    "C3647129",  # pain pressure
    "C3843661",  # Too little
    "C3845350",  # At least daily
    "C3842633",  # At work
    "C4288581",  # Notable
    "C4489374",  # Extremely Limited
    "C4533435",  # Settings (qualitative)
    "C4698491",  # Rather
    "C4723751",  # Other Than
    "C3870121",  # Long advance-directive survey narrative
    "C5777012",  # Lower risk
    "C0011750",  # Developing Countries
    "C0019932",  # Hormones
}


def is_blocked_generic_label(label: str) -> bool:
    return normalized_key(label) in BLOCKED_GENERIC_LABELS


def is_blocked_generic_query(query: str) -> bool:
    return normalized_key(query) in BLOCKED_GENERIC_QUERIES


def is_blocked_generic_cui(cui: str) -> bool:
    return cui in BLOCKED_GENERIC_CUIS


def is_blocked_generic_concept(cui: str, label: str) -> bool:
    return is_blocked_generic_cui(cui) or is_blocked_generic_label(label)
