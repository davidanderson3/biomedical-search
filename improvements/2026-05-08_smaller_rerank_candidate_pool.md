# Smaller Rerank Candidate Pool

## Request

Use a smaller candidate set before reranking.

## Change

Replaced the hard-coded pre-rerank vector candidate pools with one configurable pool:

- `candidate_pool_multiplier`, default `3`
- `candidate_pool_min`, default `50`

The previous behavior was:

- Elasticsearch KNN raw candidates: `max(k * 6, 50)`
- local vector pre-rerank candidates: `max(k * 10, 50)`
- Elasticsearch post-KNN pre-rerank cap: `max(k * 10, 50)`

The new behavior is:

- vector candidates before reranking: `max(k, candidate_pool_min, k * candidate_pool_multiplier)`

For `k=60`, this reduces the ES KNN/rerank candidate pool from `360` raw ES candidates to `180`.

The search cache key and `/api/status` now include the candidate-pool settings so cache entries do not cross incompatible retrieval configurations.

## Measured Effect

Query: `heart failure with reduced ejection fraction`

Parameters: `k=60`, Elasticsearch backend.

Before:

- `related=1`: `2145.9` ms
- `related=0`: `873.3` ms
- returned hits: `60`

After:

- `related=1`: `1818.8` ms
- `related=0`: `494.9` ms
- repeated cached `related=1`: `20.1` ms
- returned hits: `60`

The top 15 HFrEF results stayed the same after reducing the pool.

## Configuration

Default command still works:

```sh
python3 scripts/search_quality_server.py \
  --port 8766 \
  --label-index build/umls_biomedicine_search_label_index.sqlite
```

To give the reranker more recall:

```sh
python3 scripts/search_quality_server.py \
  --port 8766 \
  --label-index build/umls_biomedicine_search_label_index.sqlite \
  --candidate-pool-multiplier 6
```

To make it more aggressive:

```sh
python3 scripts/search_quality_server.py \
  --port 8766 \
  --label-index build/umls_biomedicine_search_label_index.sqlite \
  --candidate-pool-multiplier 2
```

## Verification

- `env PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_execution.py src/qe_evidence_vectors/search_service.py scripts/search_quality_server.py` passed.
- Restarted the search UI server.
- `/api/status` reports:
  - `candidate_pool_multiplier: 3`
  - `candidate_pool_min: 50`
  - `search_backend: elasticsearch`

## Tradeoff

This is a speed/recall knob. The default is now faster and still preserved the HFrEF top result set in testing, but unusual broad queries may benefit from a larger multiplier.
