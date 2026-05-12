# EGFR Linked Statement Highlight

## Change

Allowed short uppercase gene symbols to participate in linked-statement highlighting when the corresponding search hit is already categorized as `GENE`.

Previously, the linked-statement highlighter suppressed most one-token labels shorter than six characters to avoid noisy fragments. That correctly blocks many bad labels, but it also filtered `EGFR` even though the API returned `C1414313 EGFR gene` with `matched_query_span=egfr`.

## Result

Verification passed:

- `node --check docs/search_quality/app.js`
- The oncology paragraph API response includes `C1414313 EGFR gene` as a `GENE` hit with `matched_query_span=egfr`.
- A local highlighter simulation now includes `EGFR` in the label candidates for the EGFR gene hit.
- Served JS at `http://127.0.0.1:8766/search_quality_app.js` contains the new `isShortGeneSymbolLabel` guard.

## Impact

This improves linked-statement coverage for common gene symbols such as EGFR without weakening short-label suppression for non-gene noise like generic findings or administrative labels.
