# Semantic Group Dropdown

## Goal

Make the semantic group picker compact and aligned with the other search controls.

## What changed

- Replaced the visible multi-select semantic group list with a standard single-row dropdown.
- Added an explicit `All semantic groups` option so the default behavior is clear.
- Removed the extra help text under the control to keep the search bar height aligned.
- Kept the existing semantic bucket API parameter behavior: choosing a group still sends `semantic_buckets=<group key>`, while `All semantic groups` sends no filter.

## Impact

The search controls now stay on one aligned row at desktop widths, and the semantic group filter no longer consumes vertical space in the primary search panel.

## Verification

Static checks confirmed:

- `docs/search_quality_server.html` now renders `semanticGroupFilter` as a normal dropdown.
- `docs/search_quality/app.js` preserves the selected bucket and treats the empty option as no filter.
- `docs/search_quality/server.css` sets the dropdown to the same 38px control height as the other search inputs.
