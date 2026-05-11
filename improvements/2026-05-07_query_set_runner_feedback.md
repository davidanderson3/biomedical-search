# Query Set Runner Feedback

Date: 2026-05-07

## Goal

Make the query-set evaluator easier to use and safer when a batch run fails midstream.

## Change

- Added a `querySetFeedback` status region below the query-set action buttons.
- Added `setQuerySetFeedback()` in `docs/search_quality/app.js`.
- Updated `runQuerySet()` so:
  - empty query sets show an inline error
  - batch runs show `Running X of N queries`
  - partial results render after each completed query
  - failures show how many queries completed before the error
  - the `Run query set` button is always re-enabled in a `finally` block
  - the query-set results table uses `aria-busy` while the batch is running

## Measurement

- No ranking or recall change expected; individual `/api/search` calls are unchanged.
- Evaluation workflow reliability improved:
  - Before: a failed query-set run could leave the button disabled and provide no useful failure context.
  - After: progress is visible, partial results remain available, and failure state is explicit.

## Verification

- `node --check docs/search_quality/app.js`
- `rg -n "querySetFeedback|setQuerySetFeedback|Running 0 of|Query set stopped|Finished .*queries|aria-busy" docs/search_quality_server.html docs/search_quality/app.js`
  - Result: expected HTML and JS hooks found.
- No paragraph benchmark rerun was needed because this change does not alter ranking, labels, relations, or vector data.
