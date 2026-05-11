# Query Set Expected Coverage

Date: 2026-05-07

## Goal

Make query-set results useful when a query has multiple expected CUIs.

## Change

- Added `Found` and `Missing expected` columns to the query-set results table.
- Changed query-set evaluation to compute ranks for every expected CUI on a row, not only the first/best expected CUI.
- Kept `Expected rank` as the best found expected rank for quick scanning.
- Changed top-result score display to prefer `rank_score` over raw retrieval `score`, matching the main result cards.

## Measurement

- No ranking or recall change expected; only browser-side batch evaluation display changed.
- Multi-expected rows are now auditable:
  - Before: `migraine\tC0149931|C0075632|C0000000` could show only best rank `1`, hiding that one expected CUI was missing.
  - After: the same row shows `Found = 2/3`, `Expected rank = 1`, and `Missing expected = C0000000`.
- Single-expected rows keep the same behavior, with `Found` shown as `1/1` or `0/1`.

## Verification

- `node --check docs/search_quality/app.js`
- `rg -n "expectedFound|missingExpected|rank_score|Missing expected|<th>Found</th>" docs/search_quality/app.js`
  - Result: expected evaluation and table-rendering hooks found.
- Logic spot check:
  - Expected CUIs: `C0149931|C0075632|C0000000`
  - Hits: `C0075632`, `C0149931`
  - Output: `Expected rank = 1`, `Found = 2/3`, `Missing expected = C0000000`

## Scope

- No search backend, ranking, vector, label, or relation changes.
- No paragraph benchmark rerun was needed because this changes only the browser-side query-set summary table.
