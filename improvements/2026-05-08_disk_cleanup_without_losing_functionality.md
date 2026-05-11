# Disk Cleanup Without Losing Search Functionality

## Problem

The workspace was using about 73 GB, mostly under `build/`. The request was to clear space without losing current search functionality.

## Removed

Removed reproducible or non-default artifacts:

- Local Python/test caches: `.pytest_cache`, `.pycache_local`
- Reproducible Elasticsearch bulk export files: `build/*.elastic.bulk*.ndjson`, `build/*.elastic.mapping.json`
- Previous provenance backup: `build/search_quality_provenance.prev.sqlite*`
- Local MIMIC-IV note pilot derived artifacts that are not used by the default search server:
  - `build/mimic_iv_note_local_pilot/`
  - `build/profile_evidence_mimic_iv_note_local_pilot/`
  - `build/mimic_iv_note_local_pilot_concept_documents.jsonl`
  - `build/mimic_iv_note_local_pilot_concept_vectors.sapbert_cls.jsonl`
  - `build/mimic_iv_note_local_pilot_docs.sqlite*`

## Preserved

Preserved the default search UI artifacts, including:

- `build/biomedicine_expanded_literature_mimic_structured_top12_concept_documents.jsonl`
- `build/biomedicine_expanded_literature_mimic_structured_top12_concept_vectors.lean.hashing.jsonl`
- `build/umls_biomedicine_search_label_index.sqlite`
- `build/search_quality_provenance.sqlite`
- `build/drug_enrichment/drug_enrichment_concept_documents.jsonl`
- `build/drug_enrichment/drug_enrichment_concept_vectors.hashing.jsonl`

## Script Safety

Updated `scripts/start_search_quality_server.sh` so optional vector/doc shards are included only if present. This prevents the optional startup path from failing if removed MIMIC note pilot files are absent.

## Result

Workspace size changed from about 73 GB to about 48 GB. Approximately 25 GB was freed.

## Verification

- `sh -n scripts/start_search_quality_server.sh` passed.
- Rechecked active default search artifacts; all listed preserved files exist.
