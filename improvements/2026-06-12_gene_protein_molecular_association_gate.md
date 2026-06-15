# Gene/protein molecular association gate

## What changed

Default search now separates directly mentioned molecular concepts from relation-derived gene/protein associations.

- Added a `molecular_associations` / `include_molecular_associations` search flag.
- Added the flag to the search cache key and response metadata.
- Kept product, review, benchmark, and UMLS-only profiles defaulting molecular associations off.
- Hid relation-anchor GENE/protein candidates unless molecular associations are explicitly enabled.
- Hid unanchored gene/protein association results from the main ranked list by default.
- Preserved direct molecular queries and explicit gene/protein contexts.

## Verification

- `python3 -m py_compile src/qe_evidence_vectors/search_ranking.py src/qe_evidence_vectors/search_rerank.py src/qe_evidence_vectors/search_execution.py src/qe_evidence_vectors/search_quality_http.py tests/test_evidence_vectors.py`
- `PYTHONPATH=src:scripts python3 -m pytest tests/test_evidence_vectors.py -k "related_anchor_candidates or gene_protein_associations or contextless_list_gene or contextless_large_gene or brca_breast_cancer" -q`
- `PYTHONPATH=src:scripts python3 scripts/run_search_quality_experiment.py --iteration-smoke-gates --iteration-id SQI-2026-06-12-004 --iteration-type ranking --static-command "python3 -m py_compile src/qe_evidence_vectors/search_ranking.py src/qe_evidence_vectors/search_rerank.py src/qe_evidence_vectors/search_execution.py src/qe_evidence_vectors/search_quality_http.py tests/test_evidence_vectors.py" --focused-command "PYTHONPATH=src:scripts python3 -m pytest tests/test_evidence_vectors.py -k 'related_anchor_candidates or gene_protein_associations or contextless_list_gene or contextless_large_gene or brca_breast_cancer' -q" --base-url http://127.0.0.1:8766 --skip-rotating-smoke --skip-patient-portal-smoke`

## Remaining work

Add the UI affordance and provenance-heavy molecular association panel, then seed live negative controls plus EGFR, BRCA1, and CYP2C19 positives before closing `SQB-006`.
