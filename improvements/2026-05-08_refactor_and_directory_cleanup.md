# Refactor and Directory Cleanup

## Change
- Moved search quality UI implementation assets into `docs/search_quality/`:
  - `app.js`
  - `server.css`
  - `suggestions.json`
  - `paragraphs.json`
  - `expansion_profiles.json`
- Moved the short replacement proposal into `docs/proposals/search_driven_umls_replacement.md`.
- Added `docs/search_quality/README.md` and `docs/proposals/README.md` to document the new layout.
- Updated `src/qe_evidence_vectors/search_quality_http.py` so existing browser routes still work after the file move.
- Added `.gitignore` entries for generated build artifacts, local vocabulary drops, Python caches, SQLite WAL/SHM files, and local machine files.
- Removed local `.DS_Store`, `.zsh_history`, and `.pytest_cache/`.
- Updated documentation references from the old search-quality asset paths to the new organized paths.

## Improvement
- Runtime-facing URLs did not change, so the browser still loads `/search_quality_app.js`, `/search_quality_server.css`, and the existing JSON endpoints.
- Source files are now more clearly separated from generated artifacts and local data drops.
- Search UI assets are grouped in one directory instead of mixed with broader documentation pages.
- Proposal documents now have a dedicated home under `docs/proposals/`.

## Verification
- `node --check docs/search_quality/app.js` passed.
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile ...` passed for the changed server modules.
- JSON validation passed for:
  - `docs/search_quality/suggestions.json`
  - `docs/search_quality/paragraphs.json`
  - `docs/search_quality/expansion_profiles.json`
- Restarted `http://127.0.0.1:8766/`.
- Verified runtime routes:
  - `/` returned `200`
  - `/search_quality_app.js` returned `200`
  - `/search_quality_server.css` returned `200`
  - `/search_quality_suggestions.json` returned `200`
  - `/search_quality_paragraphs.json` returned `200`
  - `/search_quality_expansion_profiles.json` returned `200`
- HFrEF smoke search returned Elasticsearch results with `20` hits, `8` semantic buckets, lazy details enabled, and top CUI `C3839346`.
