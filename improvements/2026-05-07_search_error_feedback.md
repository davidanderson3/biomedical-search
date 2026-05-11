# Search Error Feedback

Date: 2026-05-07

## Goal

Make search failures visible in the interface instead of silently returning to an idle-looking state with stale or empty results.

## Change

- Added a hidden `searchFeedback` alert region below the search progress indicator in `docs/search_quality_server.html`.
- Added compact error styling in `docs/search_quality/server.css`.
- Added `setSearchFeedback()` in `docs/search_quality/app.js`.
- Updated `runSearch()` so:
  - empty searches show `Enter text, a CUI, or a source code before searching.`
  - each new valid search clears old feedback
  - successful searches keep the feedback area hidden
  - failed searches show the thrown error message in the query panel

## Measurement

- No ranking or recall change expected; search backend calls are unchanged.
- UI debuggability improved:
  - Before: a failed `/api/search` request only reset the header and could leave stale results on screen.
  - After: the user gets an inline error tied to the search controls, while successful searches remain visually clean.

## Verification

- `node --check docs/search_quality/app.js`
- `rg -n "searchFeedback|search-feedback|setSearchFeedback|Enter text, a CUI|Search failed|is-error" docs/search_quality_server.html docs/search_quality/server.css docs/search_quality/app.js`
  - Result: expected HTML, CSS, and JS hooks found.
- No paragraph benchmark rerun was needed because this change does not alter ranking, labels, relations, or vector data.
