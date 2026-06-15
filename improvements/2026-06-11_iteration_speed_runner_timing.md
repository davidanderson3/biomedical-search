# Iteration speed runner timing

`SQB-013` called out that focused PubMed iterations were slow and that the
benchmark runner serialized every live API request. This iteration removes that
client-side serialization path and adds enough timing output to identify whether
the runner or `/api/search` is the dominant cost.

## What changed

- Added `--workers` to `scripts/run_search_quality_experiment.py`.
- API runs now default to two worker threads; pass `--workers 1` for the old
  serial behavior.
- UMLS-only in-process runs stay serial because the shared index object is not
  treated as thread-safe.
- Each run now writes `query_timings.tsv` with per-query elapsed time, API
  response elapsed time, cache-hit status, backend, and hit count.
- `metrics.json` now includes `query_execution_wall_seconds`,
  `query_elapsed_sum_seconds`, `api_response_elapsed_sum_seconds`,
  `query_parallelism_saved_seconds`, `query_cache_hit_count`, and `workers`.

## Speed probe

To avoid exact full-response cache hits, the probe used nonce-suffixed copies of
the 7-row focused PubMed query file under `build/search_quality_speed_probe/`.

| Probe | Workers | Elapsed | Query wall | Sum API response time | Cache hits | Quality |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `SQI-2026-06-11-024_speed_probe_serial` | 1 | 142.080s | 142.064s | 141.989s | 0 | 7/7 strict@10, 7/7 top-on-target |
| `SQI-2026-06-11-024_speed_probe_workers2` | 2 | 140.684s | 140.669s | 243.649s | 0 | 7/7 strict@10, 7/7 top-on-target |
| `SQI-2026-06-11-024_speed_probe_parallel` | 4 | 142.820s | 142.805s | 439.541s | 0 | 7/7 strict@10, 7/7 top-on-target |

Two workers gave only a small local wall-clock improvement, and four workers
matched serial time while stretching per-request latency. That means the runner
is no longer the only serialized layer; the next useful speed iteration should
instrument and mitigate the server-side long-document path, especially chunk
KNN and raw retrieval reuse.

## Verification

- `python3 -m py_compile scripts/run_search_quality_experiment.py tests/test_search_quality_experiment_gates.py`
- `PYTHONPATH=src:scripts python3 -m pytest tests/test_search_quality_experiment_gates.py -q`
- Live nonce speed probes against `http://127.0.0.1:8766` with the
  Elasticsearch backend required.
