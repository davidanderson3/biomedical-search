# OHDSI Aggregate Relationship Mining

Implemented a local OHDSI aggregate-artifact miner for public/shareable outputs only. The miner reads ATLAS cohort JSON, CohortDiagnostics aggregate tables, CohortMethod/PLE estimation result tables, PLP feature-importance tables, and literature-backed OHDSI study rows. It emits universal relationship edges with numeric strength, evidence method/provenance, structured context, directionality, and confidence.

What improved:

- ATLAS cohort JSON can now produce `Drug -> likely_indication -> Condition` relationships from target drug concept sets and inclusion condition concept sets.
- CohortDiagnostics can add quantitative `P(condition | drug cohort)` evidence via `conditional_prevalence` and temporal `Condition -> precedes -> Drug` edges when baseline/prior windows are present.
- Population-level estimation results retain raw HR/RR/OR values and confidence intervals in `edge.evidence.quantitative` while keeping normalized ranking strength.
- PLP feature outputs are represented as predictive, explicitly non-causal `predicts` edges with feature-importance evidence.
- The importer rejects rows with patient-level identifiers such as `person_id`, `personId`, `visit_occurrence_id`, and `note_id`, so this path does not depend on real EHR data.
- Added `scripts/mine_ohdsi_relationships.py` so these artifacts can be converted to relationship-edge JSONL without writing custom glue code.

What did not improve yet:

- This does not fetch OHDSI artifacts from the web; it mines files supplied locally.
- OMOP concept resolution still depends on an OMOP-to-CUI map or the existing source-code index. Unmapped OMOP concept IDs are reported in unresolved output rather than minted automatically.
- The mined edge JSONL is not yet wired into the default search index build; it is a reusable ingestion stage ready for the next indexing pass.
