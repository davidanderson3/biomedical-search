# Source Strategy Pruning And Embedding Policy

Date: 2026-06-12

## Decision

Default search-quality source evidence should stay conservative:

- UMLS remains the identity, label, source-code, semantic-type, definition, and relation backbone.
- DailyMed, MedlinePlus, and PubMed/PMC are the core source-specific evidence lane.
- SapBERT remains the active query/document embedding baseline.
- CUI2Vec and BioConceptVec stay in the loop only as opt-in association-signal probes and ablations.
- ClinicalTrials.gov is opt-in posted-results-only, not default evidence.
- PubTator3 stays a sampled relation-candidate stub, not default evidence.

## Why DailyMed Stays Core

DailyMed adds value beyond UMLS `MTHSPL` source rows because the direct label text carries sectioned relationships:

- drug to indication,
- drug to warning,
- drug to adverse event,
- drug to contraindication,
- drug to interaction,
- drug to population,
- drug to pharmacology.

Audit evidence in `config/search_quality_source_strategy_audit.tsv`:

- `dailymed_top_drugs_vs_mthspl`: 253 unique linked CUIs, 253 outside the `MTHSPL` source-CUI set.
- `dailymed_round4_vs_mthspl`: 376 unique linked CUIs, 360 outside the `MTHSPL` source-CUI set.
- `medlineplus_full_vs_medlineplus_sab`: 7,885 unique linked CUIs, 6,141 outside the `MEDLINEPLUS` source-CUI set.

These counts do not prove every linked relation is useful, but they prove the direct feeds are not just duplicating source-SAB labels.

## What Was Pruned

- Removed ClinicalTrials.gov and PubTator3 from the default source-specific benchmark lane.
- Deleted the default source benchmark TSVs for ClinicalTrials.gov and PubTator3 relation correctness.
- Pruned `config/search_quality_source_specific_queries.tsv` to 9 core rows across DailyMed, MedlinePlus, and PubMed/PMC.
- Updated `config/search_quality_suite.json` source-specific thresholds to the 9-row core lane.
- Made the search-quality server external CUI-vector index opt-in instead of auto-loaded when present.
- Reclassified PubTator3 in the source dashboard generator as a candidate stub and removed ClinicalTrials.gov from cross-source support weighting.

## Test Result

The pruned 9-row live source lane ran as
`SQI-2026-06-12-003_core_source_specific_pruned`:

- 8/9 rows complete at top 10,
- 19/20 expected concepts at top 10,
- 9/9 top-on-target,
- 0 wrong-first rows,
- 0 disallowed rows,
- overall score 92.0.

The only remaining miss is `dailymed_label_02`: warfarin and hemorrhage are
present, but `C1550014` warning context is still absent.

## Remaining Work

Fix `C1550014`, then add section-aware DailyMed checks before expanding
DailyMed coverage. Reintroduce ClinicalTrials.gov, PubTator3, CUI2Vec, or
BioConceptVec only after a measured gap and an ablation show value without
default-result drift.
