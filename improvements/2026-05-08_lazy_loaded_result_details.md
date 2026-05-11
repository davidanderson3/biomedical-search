# Lazy-Loaded Result Details

## Request

Lazy-load expensive details.

## Change

Search responses now return compact hits and defer heavy per-result data until a result's `Details` panel is opened.

Removed from each `/api/search` hit payload:

- `evidence_items`
- `definitions`
- `images`
- `mappings`
- `text`
- `source_mix`
- per-hit related lists:
  - `research_relations`
  - `external_embedding_neighbors`
  - `mrrel_related_concepts`
  - `related_concepts`
  - `evidence_related_concepts`

Added `/api/detail?doc_id=...&cui=...&related=1`, which returns the full detail bundle for one result on demand.

The UI now renders result cards with only name and semantic type up front. Opening `Details` fetches the detail endpoint, renders metadata, score/source mix, definitions, mappings, related evidence, and evidence text, then caches that detail payload client-side.

## Measured Effect

Query: `heart failure with reduced ejection fraction`

Parameters: `k=60`, `related=1`, Elasticsearch backend.

Before lazy details:

- `/api/search` response size: `827,189` bytes
- first uncached request after smaller candidate pool: `1818.8` ms

After lazy details:

- `/api/search` response size: `189,862` bytes
- first uncached request: `1553.9` ms
- returned hits: `60`
- semantic group views: `7`

Detail endpoint check for the top HFrEF hit:

- `/api/detail` response size: `20,081` bytes
- evidence items: `12`
- mappings: `5`
- external embedding neighbors: `8`
- MRREL neighbors: `8`

## Why It Improved Things

The user usually scans result names and semantic types first. The previous response sent all evidence text, mappings, images, definitions, and per-hit related rows even when no result details were opened. The new path keeps scan-time search payloads much smaller and moves detail cost to the specific concepts the user inspects.

## Verification

- `node --check docs/search_quality/app.js` passed.
- `env PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_execution.py src/qe_evidence_vectors/search_hydration.py src/qe_evidence_vectors/search_quality_http.py` passed.
- Restarted the search UI server on `http://127.0.0.1:8766/`.
- Verified `/api/search` hits have `details_lazy: true` and do not include heavy detail fields.
- Verified `/api/detail` returns the deferred fields for `C3839346:europepmc_clinical_context`.

## Tradeoff

Opening a result now performs an extra request. That is the intended tradeoff: faster scanning and smaller search payloads, with detail cost paid only for opened concepts.
