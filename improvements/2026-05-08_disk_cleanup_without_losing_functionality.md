# Disk Cleanup Without Losing Search Functionality

## Problem

The workspace was using about 73 GB, mostly under `build/`. The request was to clear space without losing current search functionality.

## Removed

Removed reproducible or non-default artifacts:

- Local Python/test caches: `.pytest_cache`, `.pycache_local`
- Reproducible Elasticsearch bulk export files: `build/*.elastic.bulk*.ndjson`, `build/*.elastic.mapping.json`
- Previous provenance backup: `build/search_quality_provenance.prev.sqlite*`
- Local restricted-source pilot artifacts that are not used by the default search server

## Preserved

Preserved the default search UI artifacts, including:

- `build/scaling_chunk_002_common_clinical_concept_documents.jsonl`
- `build/scaling_chunk_002_common_clinical_concept_vectors.sapbert_cls.jsonl`
- `build/umls_biomedicine_search_label_index.sqlite`
- `build/search_quality_provenance.sqlite`
- `build/drug_enrichment/drug_enrichment_concept_documents.jsonl`
- `build/drug_enrichment/drug_enrichment_concept_vectors.hashing.jsonl`

## Script Safety

Updated `scripts/start_search_quality_server.sh` so optional vector/doc shards are included only if present. This prevents the optional startup path from failing if removed pilot files are absent.

## Result

Workspace size changed from about 73 GB to about 48 GB. Approximately 25 GB was freed.

## Verification

- `sh -n scripts/start_search_quality_server.sh` passed.
- Rechecked active default search artifacts; all listed preserved files exist.
