# Elasticsearch Vector Retrieval

## Request

Move vector retrieval to Elasticsearch.

## Change

Loaded the current hashing vector corpus into Elasticsearch and made it the default search backend for the local search-quality server.

New Elasticsearch index:

- index: `qe-umls-biomedicine-hashing-current-v1`
- alias: `qe-umls-biomedicine-hashing-current`
- documents loaded: `42,408`
- mapping: `build/elasticsearch/qe-umls-biomedicine-hashing-current.mapping.json`
- marker: `build/scaling_runs/elasticsearch_loaded_umls_biomedicine_hashing_current.marker`

The server now defaults to:

- `--elastic-url http://localhost:9200`
- `--elastic-index qe-umls-biomedicine-hashing-current`

This keeps the current `hashing` query embedder aligned with the indexed vectors. I did not point the server at the existing SapBERT alias because that would mix hashing query vectors with SapBERT document vectors.

## Implementation Notes

Exported and loaded the same vector files used by the current UI server:

- `build/scaling_chunk_002_common_clinical_concept_vectors.sapbert_cls.jsonl`
- `build/new_umls_iterations/iteration_002_existing_data/extension_concept_vectors.cumulative.hashing.jsonl`
- `build/wikipedia_enrichment/wikipedia_concept_vectors.hashing.jsonl`
- `build/drug_enrichment/drug_enrichment_concept_vectors.hashing.jsonl`
- `build/open_image_enrichment/open_image_concept_vectors.hashing.jsonl`
- `build/openalex_cited_evidence/openalex_top_cited_concept_vectors.hashing.jsonl`

Elasticsearch initially refused to allocate the new shard because the local node was above its default disk high watermark. I adjusted transient local watermarks to allow allocation:

- low: `94%`
- high: `96%`
- flood stage: `98%`

The first load had `10,000` errors because the shard was still unassigned. After allocation, replaying the same bulk files loaded all `42,408` documents with `0` errors.

## Bug Fix

Fixed the ES KNN request builder to include `size: k`.

Without this, Elasticsearch returned only its default `10` hits even when the KNN `k` was higher. That caused the server to return only `15` final results for a `k=60` search after label fallback. After the fix, ES returns enough candidates and the server returns the full requested result set.

## Measured Effect

Query: `heart failure with reduced ejection fraction`

Parameters: `k=60`, `related=1`.

Previous local-vector backend:

- first uncached request after related-view speedup: `3412.6` ms
- repeated cached request: `8.6` ms

Elasticsearch backend:

- first uncached request: `2145.9` ms
- repeated cached request: `6.6` ms
- returned hits: `60`
- semantic group views: `7`

With `related=0`:

- Elasticsearch request: `873.3` ms
- returned hits: `60`

## Verification

- `env PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/elastic_client.py scripts/search_quality_server.py` passed.
- `curl http://localhost:9200/qe-umls-biomedicine-hashing-current-v1/_count` returned `42,408`.
- `/api/status` reports:
  - `search_backend: elasticsearch`
  - `elastic_url: http://localhost:9200`
  - `elastic_index: qe-umls-biomedicine-hashing-current`
- Restarted the local search UI server at `http://127.0.0.1:8766/`.

## Remaining Issue

This makes vector retrieval use Elasticsearch, but result hydration still loads the JSONL/vector records into memory at startup. The next scalability step is to stop loading local vectors when Elasticsearch is configured and keep only document metadata needed for hydration.
