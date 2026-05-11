# Faster Related View Computation

## Request

Determine whether computing related views can be made faster.

## Change

Added bounded related-view computation:

- `related_source_limit`, default `16`, limits MRREL/research/external related-view source concepts to the top returned hits.
- `expensive_related_source_limit`, default `0`, disables local brute-force evidence-vector neighbor scans by default.
- `--related-source-limit` and `--expensive-related-source-limit` CLI flags expose those limits.
- MRREL related rows and research relation rows are now cached per CUI.
- Semantic view rendering now reuses already-attached empty relation lists instead of recomputing relations for hits with no related rows.
- `/api/status` reports the related source limits.

The default keeps MRREL, research relations, and BioConceptVec/cui2vec external embedding neighbors, but avoids local evidence-vector neighbor scans unless explicitly enabled.

## Measured Effect

Query: `heart failure with reduced ejection fraction`

Parameters: `k=60`, `related=1`, local vector backend.

Before this optimization:

- `elapsed_ms`: about `48000.0`

After only bounding related sources and caching relation bundles:

- `elapsed_ms`: `27598.7`

After disabling local evidence-vector related scans by default:

- cold `elapsed_ms`: `3460.2`
- warm `elapsed_ms`: `2258.6`

For comparison, `related=0` on the same query was `2481.7` ms.

## Output Shape

The final `related=1` run still returned:

- `60` hits
- `9` semantic view sources
- `7` semantic group views
- MRREL and external embedding neighbors for top related-source hits
- research relations where available

Evidence-vector related concepts are now `0` by default in the local backend because that path was the major cold-query cost.

## Tradeoff

This improves interactive speed substantially, but it no longer shows local evidence-vector related neighbors unless the server is started with a positive `--expensive-related-source-limit`.

Recommended default for local development:

```sh
python3 scripts/search_quality_server.py \
  --port 8766 \
  --label-index build/umls_biomedicine_search_label_index.sqlite
```

Recommended if Elasticsearch is available and evidence-neighbor lookups are cheap:

```sh
python3 scripts/search_quality_server.py \
  --port 8766 \
  --label-index build/umls_biomedicine_search_label_index.sqlite \
  --elastic-url http://localhost:9200 \
  --elastic-index <index-name> \
  --expensive-related-source-limit 3
```

## Verification

- `env PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_service.py src/qe_evidence_vectors/search_related.py scripts/search_quality_server.py` passed.
- Restarted the local server on `http://127.0.0.1:8766/`.
- Verified `/api/status` reports `related_source_limit: 16` and `expensive_related_source_limit: 0`.
