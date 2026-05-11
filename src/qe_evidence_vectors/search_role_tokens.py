from __future__ import annotations


PROCEDURE_ROLE_TOKENS = {
    "operation",
    "operative",
    "procedure",
    "surgery",
    "surgical",
}
DRUG_ROLE_QUERY_TOKENS = {
    "agent",
    "agents",
    "drug",
    "drugs",
    "medication",
    "pharmacologic",
    "therapy",
    "therapeutic",
}
THERAPEUTIC_ACTION_QUERY_TOKENS = {
    "manage",
    "management",
    "prevent",
    "prophylaxis",
    "treat",
    "treatment",
}
PHARMACOLOGIC_SEMANTIC_TYPES = {
    "antibiotic",
    "biologically active substance",
    "clinical drug",
    "pharmacologic substance",
}
PROCEDURE_SEMANTIC_TYPES = {
    "diagnostic procedure",
    "health care activity",
    "therapeutic or preventive procedure",
}

ACTION_OBSERVATION_LABEL_TOKENS = {
    "assessment",
    "assessing",
    "evaluation",
    "evaluating",
    "measurement",
    "measuring",
    "monitoring",
    "taking",
    "testing",
}
ACTION_OBSERVATION_QUERY_TOKENS = ACTION_OBSERVATION_LABEL_TOKENS | PROCEDURE_ROLE_TOKENS | {
    "exam",
    "examination",
    "examining",
    "followup",
    "follow",
    "initiate",
    "initiating",
    "measure",
    "measured",
    "monitor",
    "monitored",
    "obtain",
    "obtained",
    "perform",
    "performed",
    "schedule",
    "scheduled",
    "scheduling",
}
OBSERVATION_STATE_QUERY_TOKENS = {
    "acute",
    "deficit",
    "deficits",
    "distress",
    "intact",
    "limit",
    "normal",
    "stable",
    "vital",
}
