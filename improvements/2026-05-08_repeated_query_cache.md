# Repeated Query Cache

## Request

Cache repeated queries.

## Change

Added an in-memory LRU cache for `/api/search` responses.

Cache key includes:

- query text
- `top_k`
- `include_related`
- related-source limits
- Elasticsearch backend settings

The server default is `--query-cache-size 128`. Use `--query-cache-size 0` to disable it.

Cached responses are deep-copied before return, marked with:

- `cached: true`
- `cache_hit: true`
- `uncached_elapsed_ms`

`/api/status` now reports:

- `query_cache_size`
- `query_cache_entries`
- `query_cache_hits`
- `query_cache_misses`

## Measured Effect

Query: `heart failure with reduced ejection fraction`

Parameters: `k=60`, `related=1`, local vector backend.

First request:

- `elapsed_ms`: `3412.6`
- `cached`: `false`
- `semantic_group_views`: `7`
- `hits`: `60`

Repeated identical request:

- `elapsed_ms`: `8.6`
- `cached`: `true`
- `uncached_elapsed_ms`: `3412.6`
- `semantic_group_views`: `7`
- `hits`: `60`

The first 10 result CUIs were identical between the first and cached response.

Status after the test:

- `query_cache_size`: `128`
- `query_cache_entries`: `1`
- `query_cache_hits`: `1`
- `query_cache_misses`: `1`

## Tradeoff

This improves repeated-query latency but does not help first-time searches. Cache is process-local and clears when the search server restarts.

## Verification

- `env PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_execution.py src/qe_evidence_vectors/search_service.py scripts/search_quality_server.py` passed.
- Restarted the local server on `http://127.0.0.1:8766/`.
- Verified first versus repeated `/api/search` timings.
