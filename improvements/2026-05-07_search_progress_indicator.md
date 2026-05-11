# Search Progress Indicator

Date: 2026-05-07

## Goal

Show visible progress while a search request is running, especially for paragraph searches that can take a few seconds.

## Change

- Added a hidden `searchProgress` status region below the query controls in `docs/search_quality_server.html`.
- Added an indeterminate progress bar animation in `docs/search_quality/server.css`.
- Added `setSearchInFlight()` in `docs/search_quality/app.js` to show the progress indicator when `/api/search` starts and hide it in the request `finally` block.
- Set `aria-busy` on the results area while a search is in flight.

## Measurement

- No ranking or recall change expected.
- UI feedback improved: search now visibly enters a busy state beyond disabling the `Search` button.

## Verification

- `node --check docs/search_quality/app.js`
- `rg -n "searchProgress|search-progress|setSearchInFlight|aria-busy" docs/search_quality_server.html docs/search_quality/server.css docs/search_quality/app.js`
  - Result: expected HTML, CSS, and JS hooks found.
- Local server process is listening on `127.0.0.1:8766`; sandbox loopback `curl` was intermittently denied with `Operation not permitted`, so served-page verification was limited to static file checks.
