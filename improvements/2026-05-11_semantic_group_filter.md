# Semantic Group Filter

## Change

Added a custom semantic group filter to the search UI and API. The filter uses the project's semantic bucket definitions from `config/search_quality_semantic_buckets.json`, so choices are the same custom categories shown in the result cards, such as `Diseases & Syndromes`, `Findings & Symptoms`, `Drugs`, `Procedures`, `Observations & Lab Results`, `Genes, Amino Acids, Peptides, Proteins`, `Devices`, `Organisms`, `People & Populations`, and `Anatomy`.

The API now accepts `semantic_buckets`, `semantic_bucket`, `bucket`, `buckets`, `semantic_group`, or `semantic_groups` as comma-separated parameters. Example:

```text
/api/search?q=ceftriaxone%20for%20bacterial%20pneumonia&k=60&related=0&semantic_buckets=CHEM,DISO_DISEASE
```

Filtering happens server-side before semantic result buckets and related metadata are built. The search cache key includes the filter, and unknown bucket names now return a `ValueError` instead of silently producing confusing output.

## Result

The filter changes the actual result set, not just the visible cards. In a focused API-equivalent check:

- No filter returned both `C0007561` ceftriaxone and `C0004626` bacterial pneumonia.
- `semantic_bucket_keys=["CHEM"]` returned only `C0007561`.
- `semantic_bucket_keys=["DISO_DISEASE"]` returned only `C0004626`.

This improves relevance review when the user wants only certain clinical categories and avoids making every semantic group look equally important.

## Verification

- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m pytest tests/test_evidence_vectors.py -k "custom_semantic_bucket or unknown_semantic_bucket"`
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_execution.py src/qe_evidence_vectors/search_hydration.py src/qe_evidence_vectors/search_related.py src/qe_evidence_vectors/search_semantic_buckets.py src/qe_evidence_vectors/search_quality_http.py`
- `node --check docs/search_quality/app.js`

Note: an earlier broader pytest selector also matched an unrelated pre-existing compact-response expectation in `test_label_fallback_hydrates_with_best_evidence_document`; the two new semantic-filter tests passed.
