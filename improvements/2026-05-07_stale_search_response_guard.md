# Stale Search Response Guard

Date: 2026-05-07

## Goal

Prevent the interface from showing stale results when a user starts another search before the previous `/api/search` request finishes.

## Change

- Added a monotonically increasing `searchRequestSeq` to the browser app state.
- Added `searchAbortController` support for `/api/search`.
- Passed `AbortController.signal` through the shared `api()` wrapper.
- Updated `runSearch()` so:
  - starting a new search aborts the previous request when supported
  - only the latest request may update `lastQuery`, result buckets, metrics, and progress state
  - aborted requests are ignored instead of being treated as server failures

## Measurement

- No ranking or recall change expected; search backend calls and scoring are unchanged.
- UI correctness improved for rapid interactions:
  - Before: clicking a paragraph/example search while a slower previous request was still running could allow the older response to overwrite newer results.
  - After: stale responses are ignored, and the progress indicator/Search button state is cleared only by the latest active request.

## Verification

- `node --check docs/search_quality/app.js`
- `rg -n "searchRequestSeq|searchAbortController|AbortController|AbortError|options.signal|setSearchInFlight" docs/search_quality/app.js`
  - Result: expected request sequencing, cancellation, and progress-state hooks found.
- No paragraph benchmark rerun was needed because this change does not alter search ranking, labels, relations, or vector data.
