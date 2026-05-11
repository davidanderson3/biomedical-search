# Route Lab Procedures to Observations

## Problem

UMLS commonly types measurement concepts as `Laboratory Procedure`, which placed lab tests under the Procedures card. For search users, concepts such as `Hemoglobin A1c measurement`, `Glycated Hemoglobin Measurement`, `Blood Glucose Measurement`, and `Troponin measurement` are better surfaced under `Observations & Lab Results`.

## Change

Added `laboratory procedure` to the `Observations & Lab Results` semantic bucket. Updated backend and frontend bucket logic so laboratory procedure hits and related rows are excluded from the Procedures bucket and included in Observations. Also extended the broad CCPSS clinical-association filter to Observations so unrelated lab rows do not appear just because they became eligible for that bucket.

## Improvement

For `type 2 diabetes hemoglobin a1c`:

- Procedures changed from 12 items to 4.
- Observations & Lab Results changed from 4 items to 12.
- `blood hemoglobin A1C measurement`, `Hemoglobin A1c measurement`, `Blood Glucose Measurement`, `Glycated Hemoglobin Measurement`, and related HbA1c measurement rows now appear under Observations instead of Procedures.

For `acute myocardial infarction troponin`:

- Procedures changed from 2 items to 1.
- Observations & Lab Results now contains `Troponin measurement`.
- The unrelated CCPSS `BUN MG DL CR MG DL` row was filtered out.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py::test_semantic_buckets_route_lab_procedures_to_observations_not_procedures tests/test_evidence_vectors.py::test_semantic_buckets_route_proteins_to_gene_bucket_not_drugs tests/test_evidence_vectors.py::test_semantic_buckets_hide_weak_ccpss_procedure_associations` passed.
- `node --check docs/search_quality/app.js` passed.
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_semantic_buckets.py` passed.
- `python3 -m json.tool config/search_quality_semantic_buckets.json` passed.
- Restarted the live server on `http://127.0.0.1:8766/` and confirmed the diabetes/A1c and MI/troponin before/after behavior.
