# Route Measurement Tests to Observations

## Problem

Some measurement/test concepts are typed by UMLS as `Diagnostic Procedure`, so they appear under Procedures even though users expect them in `Observations & Lab Results`. Examples include:

- `Ejection fraction measurement`
- `Urine protein test`

This makes the Procedures card mix true procedures such as biopsy/catheterization with measurement concepts.

## Change

Added routing logic for diagnostic/laboratory procedure labels that look like measurements or tests. Labels containing markers such as `measurement`, `test`, `panel`, `assay`, `level`, or `ratio` now route to `Observations & Lab Results` and are excluded from Procedures.

True procedures without those markers, such as `Biopsy`, remain in Procedures.

## Improvement

Expected effect after server reload:

- `Ejection fraction measurement` moves from Procedures to Observations.
- `Urine protein test` moves from Procedures to Observations.
- True diagnostic/therapeutic procedures remain in Procedures.

This should make semantic cards better match clinical expectations: testable/measurable clinical facts in Observations, interventions in Procedures.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py::test_semantic_buckets_route_lab_procedures_to_observations_not_procedures` passed.
- `node --check docs/search_quality/app.js` passed.

Live API verification is deferred to the next server restart to avoid adding more shell/session pressure in the current long-running workflow.
