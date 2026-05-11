# Faster Default Candidate Pool

## Change

Reduced the default rerank candidate pool from `3x requested results, minimum 50` to `1x requested results, minimum 40`.

This affects:

- `src/qe_evidence_vectors/search_service.py`
- `src/qe_evidence_vectors/search_execution.py`
- `scripts/search_quality_server.py`
- `scripts/evaluate_paragraph_quality.py`

The paragraph evaluator now records `candidate_pool_multiplier`, `candidate_pool_min`, and `candidate_pool_for_top_k` in its metrics output so future speed/quality comparisons are explicit.

## Why

Search was spending extra time hydrating and reranking vector candidates that were not needed for the current quality benchmark. The label fallback, definition fallback, relation signals, and final semantic ranking still run after vector candidate selection, so reducing the vector candidate pool trims work while preserving the later precision logic.

## Measured Impact

Baseline from `build/improvements/2026-05-11_after_compact_groups_and_filler_filter`:

- Candidate pool: `3x`, minimum `50`
- Paragraph quality: `96/96 good`
- Expected concept recall at 10: `467/467`
- Mean search time: `1934.6 ms`
- Median search time: `1622.6 ms`
- p90 search time: `2011.1 ms`
- p95 search time: `2188.7 ms`

Default-path verification from `build/improvements/2026-05-11_faster_default_candidate_pool`:

- Candidate pool: `1x`, minimum `40`
- Paragraph quality: `96/96 good`
- Expected concept recall at 10: `467/467`
- Mean search time: `1602.7 ms`
- Median search time: `1296.2 ms`
- p90 search time: `1663.6 ms`
- p95 search time: `1892.4 ms`

Net improvement on the 96-paragraph benchmark:

- Mean latency improved by `331.9 ms` (`17.2%`)
- Median latency improved by `326.4 ms` (`20.1%`)
- p90 latency improved by `347.5 ms` (`17.3%`)
- p95 latency improved by `296.3 ms` (`13.5%`)
- No measured loss in paragraph quality or expected concept recall

## Notes

An alternate top-N implementation using heap selection was tested first and rejected because it was slower on this workload. The kept change is the candidate-pool default reduction because it produced a measurable latency improvement without quality loss on the current benchmark.

