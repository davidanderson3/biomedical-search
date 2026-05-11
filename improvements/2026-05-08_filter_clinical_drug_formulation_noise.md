# Filter Clinical Drug Formulation Noise

## Problem

The Drugs bucket could show formulation-strength rows as related drug results. For example, `egfr mutated non small cell lung cancer osimertinib` showed `potassium chloride 20 MEQ` beside actual oncology therapies. That row is a specific clinical drug formulation and is not useful in the default related Drugs card for an oncology query.

## Change

Added a semantic bucket filter for related `Clinical Drug` rows that look like formulations: labels with numeric strengths and dose units such as `mg`, `mcg`, `meq`, `ml`, or labels containing dosage-form terms such as `tablet`, `capsule`, `solution`, or `injection`.

This applies only to related result display in the Drugs bucket. Ingredient and therapy concepts remain visible.

## Improvement

For `egfr mutated non small cell lung cancer osimertinib`, the Drugs bucket no longer shows:

- `potassium chloride 20 MEQ`

The bucket still shows therapeutically useful results:

- `osimertinib`
- `osimertinib mesylate`
- `hydroxyurea`
- `vinorelbine`
- `irinotecan`
- `paclitaxel`
- `topotecan`
- `pemetrexed`
- `kinase inhibitor [EPC]`

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py::test_semantic_buckets_route_proteins_to_gene_bucket_not_drugs tests/test_evidence_vectors.py::test_semantic_buckets_route_lab_procedures_to_observations_not_procedures tests/test_evidence_vectors.py::test_semantic_buckets_hide_weak_ccpss_procedure_associations` passed.
- `node --check docs/search_quality/app.js` passed.
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_semantic_buckets.py` passed.
- Restarted the live server on `http://127.0.0.1:8766/` and confirmed the EGFR/osimertinib Drugs bucket.
