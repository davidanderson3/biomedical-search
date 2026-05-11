# Pattern-Based Symptom Aggregate Filter

## Change

Replaced one-off cleanup of broad symptom labels with a pattern-based filter. The ranker now identifies broad aggregate symptom concepts by semantic type plus primary/matched label tokens, rather than requiring every noisy label to be listed explicitly.

The covered pattern includes labels such as:

- `systemic symptoms`
- `general symptom`
- `multiple symptoms`
- `respiratory symptoms`
- `no respiratory symptoms`
- `distressing symptoms`
- `signs and symptoms`

Direct lookup is preserved. A query like `systemic symptoms` or `distressing symptoms` can still return that concept; the filter only applies when the query has richer clinical context and more specific symptoms are present.

## Measured Impact

Before this change, the residual audit cleanup kept recall perfect but the precision audit kept surfacing replacement members of the same broad symptom family:

- `recall_at_10`: 100.0%
- `verdict_counts`: 116 good
- calibrated suspect top-10 hits: 1
- replacement examples included `Multiple symptoms` and `Distressing symptoms`

After the pattern-based filter:

- `paragraphs`: 116
- `expected_concepts`: 570
- `recall_at_10`: 100.0%
- `recall_at_20`: 100.0%
- `queries_all_expected_at_10`: 116/116
- `verdict_counts`: 116 good
- calibrated suspect top-10 hits: 0
- visible top-3 nonexpected suspects: 0

## Why This Is More Sustainable

This avoids chasing broad symptom aggregate labels one at a time. New labels with the same structure are handled by the same rule, while direct concept search remains intact because the filter only runs when the broader query contains clinical context beyond the aggregate label.

## Verification

- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py`
- `python3 -m pytest tests/test_evidence_vectors.py -k "systemic_symptoms or gestational_context or broad_drug_classes"`
- `python3 scripts/evaluate_paragraph_quality.py --output-dir build/improvements/2026-05-11_pattern_symptom_aggregate_filter_final_after --top-k 60`
- `python3 scripts/audit_paragraph_precision.py --payloads build/improvements/2026-05-11_pattern_symptom_aggregate_filter_final_after/paragraph_search_payloads.jsonl --output-dir build/improvements/2026-05-11_pattern_symptom_aggregate_filter_final_after --top-n 10`
