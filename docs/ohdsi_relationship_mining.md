# OHDSI Relationship Mining Plan

## Short Answer

Yes. OHDSI artifacts are a strong fit for the universal relationship edge model, especially because they can supply quantitative strength and confidence fields instead of only heuristic relatedness. The safe default is to mine only public cohort definitions, published/shared aggregate outputs, and study packages/results that are explicitly shareable. Do not ingest patient-level EHR rows, local CDM extracts, or restricted site outputs unless a separate governance path approves that data.

## Source Classes

### A. ATLAS Cohort Definitions

ATLAS cohort JSON and concept-set JSON can be mined for curated domain knowledge. If a target cohort is a drug-exposure cohort and inclusion criteria require condition concept sets before or around index, create:

```text
Drug CUI -> likely_indication -> Condition CUI
```

Recommended edge fields:

- `type`: `likely_indication`
- `strength`: normalized rule strength initially; replace with `P(condition | drug)` when CohortDiagnostics aggregate counts are available
- `strength_metric`: `cohort_rule_score` or `conditional_prevalence`
- `directionality`: `subject_to_object`
- `evidence.method`: `curated`
- `evidence.provenance`: `atlas_cohort_definition`
- `context`: cohort id/name, concept set id/name, inclusion rule id/name, index window, domain, source URL/package
- `confidence`: higher for published/validated cohorts, lower for local drafts

Useful extraction logic:

- Identify target cohorts whose initial event is `DrugExposure`, `DrugEra`, ingredient descendants, or RxNorm-related concept sets.
- Extract condition/procedure/measurement concept sets from inclusion criteria and temporal windows.
- Map OMOP concept IDs to source vocabulary IDs and then to UMLS CUIs through the existing code index where possible.
- Prefer ingredient-level drug CUIs by rolling up salts, brands, clinical drugs, and formulations.

### B. CohortDiagnostics Aggregate Outputs

CohortDiagnostics can supply aggregate cohort characterization, temporal comparison, inclusion attrition, index-event breakdown, cohort counts, overlap, and incidence-style summaries. These outputs are valuable because they let us separate "concept appears in a definition" from "concept actually appears frequently before drug initiation."

Recommended relationships:

```text
Drug CUI -> likely_indication -> Condition CUI
Drug CUI -> associated_with -> Finding/Procedure/Measurement CUI
Condition CUI -> temporal_precedes -> Drug CUI
```

Recommended strength metrics:

- `P(condition | drug_cohort)` from characterization/prevalence
- `lift_vs_background` when database-wide or comparator prevalence is available
- `temporal_precedence_score` from temporal distributions
- `inclusion_rule_prevalence` from attrition/inclusion-rule contribution

Confidence should increase with sample size, multi-database agreement, temporal precedence, and consistency with cohort JSON rules. Confidence should decrease when the relationship only appears as broad background comorbidity.

### C. Population-Level Estimation / CohortMethod Results

Comparative effectiveness and safety studies are the best OHDSI source for true quantitative edge strength. Target/comparator/outcome outputs can create:

```text
Exposure CUI -> affects_risk_of -> Outcome CUI
Exposure CUI -> increases_risk_of -> Outcome CUI
Exposure CUI -> decreases_risk_of -> Outcome CUI
```

Recommended edge fields:

- `type`: `affects_risk_of`, `increases_risk_of`, or `decreases_risk_of`
- `strength`: the reported effect estimate when the edge model supports raw values; otherwise a normalized transform of `abs(log(HR))`
- `strength_metric`: `hazard_ratio`, `risk_ratio`, `odds_ratio`, or `log_hazard_ratio_normalized`
- `directionality`: `subject_to_object`
- `evidence.method`: `temporal_analysis`
- `evidence.provenance`: `ohdsi_cohort_method` or study package id
- `context`: target cohort, comparator cohort, outcome cohort, time-at-risk, adjustment method, database/network, analysis id
- `confidence`: derived from confidence interval width, calibrated p-value if present, diagnostics, negative-control calibration, sample size, and replication across databases

Store raw quantitative fields inside evidence/context even if the display strength remains normalized:

```json
{
  "estimate": 1.42,
  "lower_95": 1.18,
  "upper_95": 1.71,
  "measure": "hazard_ratio"
}
```

### D. PatientLevelPrediction Outputs

PatientLevelPrediction can provide predictor relationships when shared model artifacts include covariates and feature importance. These should not be treated as causal. They are useful for search and hypothesis generation:

```text
Condition CUI -> predicts -> Drug CUI
Condition CUI -> predicts -> Outcome CUI
Measurement CUI -> predicts -> Outcome CUI
```

Recommended strength metrics:

- permutation feature importance
- standardized model coefficient
- AUC delta when a feature is removed
- model-derived feature contribution when available

Recommended confidence inputs:

- external validation present
- calibration performance
- discrimination performance
- feature stability across folds/databases
- feature prevalence

### E. Literature-Backed OHDSI Studies

Published OHDSI studies and shared study packages are a high-value bridge between curated definitions and quantitative results. Mine them in two passes:

1. Definitions pass: extract target/comparator/outcome cohorts and concept sets.
2. Results pass: extract aggregate estimates, diagnostics, and published interpretation.

These should produce stronger relationship edges than generic literature co-occurrence because the cohorts encode domain-specific design choices and the results include quantitative estimates.

## Product Rules

- Mine aggregate/public OHDSI artifacts first; do not depend on any real EHR source.
- Keep `evidence.method` distinct from `confidence`: a relationship can be literature-mined but low confidence, or curated but weakly quantified.
- Do not promote `likely_indication` solely from common comorbidity prevalence. Require at least one of: explicit inclusion criterion, temporal precedence, high lift, published study intent, or repeated network agreement.
- Always preserve the original OMOP concept IDs, cohort IDs, concept set IDs, and source package URLs as provenance.
- Convert concept IDs to UMLS CUIs through existing resolver indexes. If no UMLS concept exists and the relationship is clinically useful, route it to the `NEW#######` concept lane.

## Minimal Implementation Order

1. Add an OHDSI artifact reader for exported ATLAS cohort JSON and concept-set JSON.
2. Add OMOP concept ID to UMLS CUI resolution using the existing source-code index.
3. Emit JSONL relationship candidates using the universal edge object.
4. Add a CohortDiagnostics aggregate reader for characterization and temporal-precedence tables.
5. Add an estimation-results reader for hazard/risk/odds ratios and confidence intervals.
6. Add PLP feature-importance ingestion only after the causal/effect-estimate path is stable, because PLP edges are predictive, not causal.

## Implemented Local Miner

The repository now includes a local aggregate-artifact miner at `scripts/mine_ohdsi_relationships.py`. It reads files already present on disk and rejects rows with patient-level fields such as `person_id`, `personId`, `visit_occurrence_id`, or `note_id`. This keeps the implementation aligned with the data-governance rule: mine public/shareable cohort definitions and aggregate results, not real EHR extracts.

Example:

```sh
python3 scripts/mine_ohdsi_relationships.py \
  --atlas path/to/cohort_definition.json \
  --cohort-diagnostics path/to/cohort_diagnostics.csv \
  --estimation-results path/to/cohort_method_results.csv \
  --plp-output path/to/plp_feature_importance.csv \
  --literature-study path/to/published_ohdsi_results.csv \
  --omop-cui-map path/to/omop_cui_map.tsv \
  --code-index build/umls_biomedicine_code_index.sqlite \
  --out build/ohdsi_relationship_edges.jsonl \
  --unresolved-out build/ohdsi_unresolved.jsonl \
  --summary-out build/ohdsi_relationship_summary.json
```

The output JSONL rows contain the existing universal edge object plus source-class labels. ATLAS cohort JSON produces `Drug -> likely_indication -> Condition` edges with `cohort_rule_score`. CohortDiagnostics characterization produces `conditional_prevalence` edges and, when baseline/prior temporal windows are present, `Condition -> precedes -> Drug` edges. Population-level estimation outputs retain raw `hazard_ratio`, `risk_ratio`, or `odds_ratio` values and confidence intervals in `edge.evidence.quantitative` while keeping ranking strength normalized. PLP feature outputs create `predicts` edges with `context.noncausal = true`.

To make mined edges visible in the search interface, build the generic relationship-edge index:

```sh
python3 scripts/evidence_vectors.py build-relationship-edge-index \
  --edges build/ohdsi_relationship_edges.jsonl \
  --out build/relationship_edges.sqlite \
  --replace
```

`scripts/search_quality_server.py` loads `build/relationship_edges.sqlite` by default when it exists. These edges are merged into related semantic views and the separate related result buckets, where their numeric `strength` and `confidence` are used for evidence gating.

## Open Design Adjustment

The current edge implementation stores normalized `strength` with `strength_metric = normalized_score`. OHDSI effect estimates should add raw quantitative measure fields, either by allowing non-normalized `strength` when `strength_metric` is an effect measure or by adding `raw_strength` and keeping display strength normalized. The second option is safer for ranking because it avoids comparing hazard ratios directly with probabilities and embedding scores.
