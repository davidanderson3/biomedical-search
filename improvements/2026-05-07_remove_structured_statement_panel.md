# Remove Structured Statement Panel

Date: 2026-05-07

## Goal

Remove the structured-statement section because the current heuristic subject-predicate-object extraction can produce misleading triples and qualifiers.

## Change

- Removed the visible `Structured Statements` panel from `docs/search_quality_server.html`.
- Removed the UI element registration and renderer calls from `docs/search_quality/app.js`.
- Removed the now-unused `renderStructuredStatement` function so the stale `structuredStatement` and `statementStatus` element references are gone.

## Measurement

- No search ranking or recall change expected.
- Interface clarity improved: search results now move directly from `Find Concepts` to `Returned CUIs`, with no generated SPO section in between.
- The served page no longer contains `Structured Statements`, `structuredStatement`, or `statementStatus`.

## Verification

- `node --check docs/search_quality/app.js`
- `rg -n "Structured Statements|structuredStatement|statementStatus|renderStructuredStatement" docs/search_quality_server.html docs/search_quality/app.js`
  - Result: no matches
- `curl -sS http://127.0.0.1:8766/`
  - Confirmed the page shows `Find Concepts` followed by `Returned CUIs`.
