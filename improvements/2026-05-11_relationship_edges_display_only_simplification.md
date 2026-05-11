# Relationship Edges Display-Only Simplification

## Question

Can we simplify the search stack and keep similar concept-assignment quality?

## Ablations

I added evaluator flags to disable optional indexes and measured the 116-paragraph benchmark.

Disabling broad relationship machinery was not safe:

- Disabled: code index, external CUI vectors, MRREL relation index, research relation index, relationship edge index
- `recall_at_10`: 98.4%
- `verdict_counts`: 101 good, 15 mixed

Disabling only code lookup and external CUI vectors was also not safe:

- Disabled: code index, external CUI vectors
- `recall_at_10`: 98.8%
- `verdict_counts`: 107 good, 9 mixed

Disabling mined relationship-edge ranking was safe:

- Disabled for ranking only: mined universal relationship edges
- Relationship edges still load for related/semantic views.
- `recall_at_10`: 100.0%
- `verdict_counts`: 116 good
- calibrated suspect top-10 hits: 0

## Change

The default search path now treats `relationship_edges.sqlite` as display/related-view evidence, not as a concept-ranking signal. A new `relationship_edges_rank` option controls this behavior:

- Default: `False`
- CLI opt-in: `--rank-relationship-edges`

This simplifies concept ranking while preserving the relationship display work.

## Measured Impact

After the change:

- `paragraphs`: 116
- `expected_concepts`: 570
- `recall_at_10`: 100.0%
- `recall_at_20`: 100.0%
- `queries_all_expected_at_10`: 116/116
- `verdict_counts`: 116 good
- calibrated suspect top-10 hits: 0
- `relationship_edges_rank`: false

## Verification

- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile scripts/evaluate_paragraph_quality.py scripts/search_quality_server.py src/qe_evidence_vectors/search_service.py src/qe_evidence_vectors/search_related.py src/qe_evidence_vectors/search_rerank.py`
- `python3 -m pytest tests/test_evidence_vectors.py -k "relationship_edge_index or broad_drug_classes or systemic_symptoms or paragraph"`
- `python3 scripts/evaluate_paragraph_quality.py --output-dir build/improvements/2026-05-11_relationship_edges_display_only_after --top-k 60`
- `python3 scripts/audit_paragraph_precision.py --payloads build/improvements/2026-05-11_relationship_edges_display_only_after/paragraph_search_payloads.jsonl --output-dir build/improvements/2026-05-11_relationship_edges_display_only_after --top-n 10`
