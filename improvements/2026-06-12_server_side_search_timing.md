# Server-side search timing

## What changed

`SQB-013` needed a server-side view of the slow focused PubMed loop. The
benchmark runner already proved client parallelism was not enough, but it could
not say whether the remaining time came from embedding, KNN retrieval, long
document chunk search, mention extraction, ranking, or response compaction.

- Added `server_timing` to search API responses.
- Added stage timings for cache lookup, resolve, embedding, base vector search,
  hit hydration, long-document chunk vector search, long-document mention
  extraction, active-label support, support signals, merge/rank, filtering,
  related/linked extraction, metadata, and response compaction.
- Cached responses now expose the current cache-hit timing and preserve the
  original uncached timing under `uncached_server_timing`.
- `query_timings.tsv` and `metrics.json` now summarize server timing columns for
  embedding, base vector search, long-document chunk vector search, mention
  extraction, ranking, and response compaction.

## Measured effect

Fresh uncached focused PubMed run:

- Wall time: 148.291s.
- Cache hits: 0.
- Quality: 7/7 strict top 10, 7/7 top-on-target, 0 wrong-first rows.
- Server total: 148.059s.
- Long-document mention extraction: 108.329s.
- Ranking, support, and filtering outside the mention extractor: 34.326s.
- Embedding: 1.479s.
- Base vector search: 0.214s.
- Long-document chunk vector search: 0.626s.
- Response compaction: 0.001s.

The bottleneck is therefore not vector search or response serialization. The
next speed iteration should optimize long-document mention extraction first.

Run artifact:

- `build/search_quality_experiments/runs/SQI-2026-06-12-006_pubmed_server_timing_sqi-2026-06-12-006-focused-pubmed-server-timing`

## Verification

- `python3 -m py_compile src/qe_evidence_vectors/search_execution.py src/qe_evidence_vectors/search_rerank.py scripts/run_search_quality_experiment.py tests/test_search_quality_experiment_gates.py`
- `PYTHONPATH=src:scripts python3 -m pytest tests/test_search_quality_experiment_gates.py -k "timings or api_response_requires" -q`
- `PYTHONPATH=src:scripts python3 scripts/run_search_quality_experiment.py --label "SQI-2026-06-12-006 focused PubMed server timing" --run-id SQI-2026-06-12-006_pubmed_server_timing --run-family custom --queries build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_queries.tsv --query-limit 0 --base-url http://127.0.0.1:8768 --require-api-backend elasticsearch --scope umls_evidence --search-system api --top-k 60 --timeout 180 --workers 1 --output-root build/search_quality_experiments --html-report docs/search_quality_experiments.html`
- `PYTHONPATH=src:scripts python3 scripts/run_search_quality_experiment.py --iteration-smoke-gates --iteration-id SQI-2026-06-12-006 --iteration-type process --iteration-type long-document --static-command 'python3 -m py_compile src/qe_evidence_vectors/search_execution.py src/qe_evidence_vectors/search_rerank.py scripts/run_search_quality_experiment.py tests/test_search_quality_experiment_gates.py' --focused-command 'PYTHONPATH=src:scripts python3 -m pytest tests/test_search_quality_experiment_gates.py -k "timings or api_response_requires" -q' --base-url http://127.0.0.1:8768 --force-standing-smoke --skip-rotating-smoke --skip-patient-portal-smoke`

## Remaining work

Keep `SQB-013` open, but narrow it. The next implementation should reduce
`query_entity_mentions` cost in the long-document path before spending time on
chunk KNN batching or response compaction.
