# Fix Semantic Bucket Runtime Error

## Problem

Search rendering could fail with `DISEASE_SYNDROME_TYPES is not defined` after semantic bucket definitions were moved into `config/search_quality_semantic_buckets.json`. One remaining frontend display helper still referenced the removed hard-coded constant.

## Change

Updated `docs/search_quality/app.js` so the semantic type display helper resolves disease/syndrome semantic types from the shared loaded bucket config instead of the deleted `DISEASE_SYNDROME_TYPES` constant.

## Improvement

The result renderer now stays aligned with the shared semantic bucket configuration and no longer depends on stale per-bucket JavaScript constants. This fixes the reported search-time frontend error without changing result ranking or backend behavior.

## Verification

- `rg` found no remaining references to removed semantic bucket constants.
- `node --check docs/search_quality/app.js` passed.
- `http://127.0.0.1:8766/search_quality_app.js` is serving the patched helper.
- A smoke search for `heart failure with reduced ejection fraction` returned API results successfully.
