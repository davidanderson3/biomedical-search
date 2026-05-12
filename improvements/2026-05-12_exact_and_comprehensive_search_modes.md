# Exact and Comprehensive Search Modes

## Change

Added an explicit search mode control with three modes: `balanced`, `exact`, and `comprehensive`. The UI now exposes the mode as a dropdown, `/api/search` accepts `mode=` or `search_mode=`, and the backend includes the mode in cache keys so exact and broad searches do not reuse each other's results.

`exact` mode filters ranked results to concepts with literal label/name/span/local-extension evidence, which gives users a tighter lookup mode for terms they expect to resolve directly. `comprehensive` mode widens the reranking candidate pool and has the UI request a larger result pool, which is slower but better for finding lower-ranked concepts that may otherwise be missed.

## Result

Targeted verification passed:

- `py_compile` for the modified search backend modules.
- `node --check docs/search_quality/app.js`.
- `pytest tests/test_evidence_vectors.py -k "search_modes or search_api_filters_results_by_custom_semantic_bucket or label_fallback_hydrates_semantic_group" -q` passed with 3 tests.
- Live API smoke test on `http://127.0.0.1:8766/`:
  - `mode=exact` for `blood culture` returned HTTP 200, reported `search_mode: exact`, and returned 2 literal-match hits with `Blood culture` first.
  - `mode=comprehensive` for `blood culture` returned HTTP 200, reported `search_mode: comprehensive`, and returned 5 hits with `Blood culture` first.

## Impact

This improves control rather than changing the default behavior. Balanced search remains the default. Exact mode should reduce false positives from semantic-only matches when the user wants a literal concept lookup, while comprehensive mode gives a deliberate escape hatch for recall-sensitive searches.
