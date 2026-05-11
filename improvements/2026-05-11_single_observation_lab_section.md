# Single Observation Lab Section

## Change

Merged related-result items into their matching semantic group card in the search UI instead of rendering a second related-only card with the same semantic group label.

## Improvement

Searches that have both direct and related `Observations & Lab Results` content now show one `Observations & Lab Results` section. The card can contain direct hits and related items together, preserving the related marker on related rows.

## Verification

Ran a JavaScript syntax check for `docs/search_quality/app.js` and added a regression test confirming direct observation hits and related observation items use the same `CLIN_ATTR` bucket key.

## Remaining Limitations

The merge is a display-layer fix. It does not change ranking, semantic bucket assignment, or the returned API payload.
