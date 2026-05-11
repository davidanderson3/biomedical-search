# Keep Linked Statement, Remove Structured Triples

## Change

Removed the rendered structured statement/triple section from the search results panel while keeping the linked statement text with CUI links and concatenation markers.

## Result

The results page keeps the useful linked sentence display but no longer shows the subject/predicate/object/qualifier cards. This reduces vertical clutter and avoids presenting low-confidence extracted triples as if they were authoritative.

## Verification

- `node --check docs/search_quality/app.js`
