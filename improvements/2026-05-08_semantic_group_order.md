# Semantic Group Order

## Change
- Reordered semantic result buckets in `docs/search_quality/app.js`.
- Reordered backend precomputed semantic result buckets in `src/qe_evidence_vectors/search_semantic_buckets.py`.
- Kept Anatomy as an existing semantic group after the requested sequence so existing anatomy functionality remains available.

## New Order
1. Diseases & Syndromes
2. Findings & Symptoms
3. Drugs
4. Procedures
5. Observations & Lab Results
6. Genes, Amino Acids, Peptides, Proteins
7. Devices
8. Organisms
9. People & Populations
10. Anatomy

## Verification
- `node --check docs/search_quality/app.js` passed.
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile ...` passed for the backend semantic bucket module.
- Restarted `http://127.0.0.1:8766/`.
- HFrEF smoke query returned the visible bucket order:
  `Diseases & Syndromes`, `Findings & Symptoms`, `Drugs`, `Procedures`, `Observations & Lab Results`, `Genes, Amino Acids, Peptides, Proteins`, `Devices`, `Anatomy`.
- Mixed organism query showed `Organisms` after `Devices`.
- People/population query showed `People & Populations` after `Organisms`.
