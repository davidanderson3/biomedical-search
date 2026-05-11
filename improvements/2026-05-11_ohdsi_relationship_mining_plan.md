# OHDSI Relationship Mining Plan

## Change

Added `docs/ohdsi_relationship_mining.md` and linked it from `docs/technical_pipeline.md`.

## How It Improved Things

This turns the OHDSI idea into an implementation-ready source plan for the universal relationship model. It separates five source types:

- ATLAS cohort definitions
- CohortDiagnostics aggregate outputs
- Population-level estimation / CohortMethod results
- PatientLevelPrediction feature-importance outputs
- Literature-backed OHDSI studies and study packages

For each source, the plan specifies relationship direction, relationship type, strength metric, evidence method/provenance, structured context, and confidence inputs. It also makes the governance boundary explicit: mine public or shareable aggregate artifacts first and do not use patient-level EHR data in this path.

## Practical Impact

The highest-value next implementation is ATLAS cohort JSON plus CohortDiagnostics aggregate outputs. That can produce drug-to-likely-indication edges with quantitative `P(condition | drug cohort)` strength and temporal support, without relying on MIMIC or restricted clinical data.

## Limitation

No OHDSI parser was implemented in this step because no local ATLAS/CohortDiagnostics/PLE/PLP artifacts are present in the workspace yet. The plan defines the expected file classes and edge outputs so implementation can be added once artifacts are available.
