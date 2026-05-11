# Precomputed Semantic Group Buckets

## Change
- Added backend semantic result bucket assembly in `src/qe_evidence_vectors/search_semantic_buckets.py`.
- Added `semantic_result_buckets` to `/api/search` responses from `search_related.py`.
- Updated `docs/search_quality/app.js` to prefer precomputed buckets and fall back to browser-side bucket construction when absent.
- Kept local semantic expansion profiles in the browser so profile-driven additions still render after backend bucket assignment.
- Added derived `semantic_group` and `semantic_group_label` fields to Elasticsearch hits in `search_execution.py`, matching local search hit metadata.

## Why It Helps
- The browser no longer needs to rebuild direct and related semantic buckets from scratch on every render.
- Bucket membership is computed once per search response, close to the semantic metadata and relation-view generation.
- Bucket items are compact references (`kind`, `cui`, `doc_id`, `rank`) rather than duplicated full hit objects, so lazy result details remain lazy.
- API consumers now get the same bucketed semantic result structure as the web UI.

## Verification
- `node --check docs/search_quality/app.js` passed.
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile ...` passed for the changed Python modules.
- HFrEF test query returned:
  - `60` hits
  - `8` semantic result buckets
  - `details_lazy: true`
  - first hit semantic group: `DISO / Disorders`
  - no nested full hit objects inside `semantic_result_buckets`
- Example HFrEF bucket summary:
  - Diseases & Syndromes: `28` returned, `10` related
  - Findings & Symptoms: `19` returned
  - Procedures: `5` returned, `12` related
  - Anatomy: `3` returned

## Tradeoff
- The HFrEF response size was `218,561` bytes because the response now includes precomputed bucket references and related bucket items. This is still compact relative to duplicating full hit detail payloads, but it is a modest payload increase for less browser-side render work.
