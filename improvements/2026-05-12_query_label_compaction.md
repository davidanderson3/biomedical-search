# Query Label Compaction

## Change

Removed the visible `Text, CUI, or code` label above the main search box to save vertical space. The input keeps the same wording as an `aria-label`, so screen readers still have an accessible name for the field.

## Result

Verified in `docs/search_quality_server.html` that the visible label was removed and the search input now carries `aria-label="Text, CUI, or code"`.

## Impact

This is a layout-only cleanup. It does not change search behavior, ranking, filters, or API requests.
