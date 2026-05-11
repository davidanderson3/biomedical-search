# Related Result Visual Parity

## Request

Drug and gene results looked different, probably because some were related suggestions. They should not look different.

## Change

- Added `compact-result-title` to related suggestion titles.
- Kept the related suggestion button behavior, but reset its compact-card header styling so it no longer inherits the pill-like `.related-concept` appearance.
- Changed related suggestion card background from pale blue-white to the same white background as normal result cards.

## Why This Was Needed

Direct drug/gene hits use `renderCompactResultCard()`. Related drug/gene suggestions use `renderCompactRelatedSuggestionCard()`. Even after both used the same three-column header, related suggestions still had visible differences because `.related-concept` applied:

- border
- rounded chip shape
- pale background
- extra padding
- inline-flex layout
- slightly different color/font sizing

That made related drug/gene results look like a different kind of card even when they are being shown in the same semantic bucket.

## Measured Effect

Before:

- Direct result card title: `concept-link compact-result-title`
- Related suggestion title: `related-concept related-suggestion-title`
- Related suggestion card background: `#fbfcfe`

After:

- Direct result card title: `concept-link compact-result-title`
- Related suggestion title: `related-concept compact-result-title related-suggestion-title`
- Related suggestion card background: `#fff`
- Compact related titles now explicitly reset the `.related-concept` border, padding, background, radius, and inline-flex layout inside compact summaries.

## Verification

- `node --check docs/search_quality/app.js` passed.
- Confirmed the running server is serving the updated JavaScript.
- Confirmed the running server is serving the updated CSS rules for `.result-related-suggestion` and `.compact-result-summary .related-concept.compact-result-title`.

## Result

Drug and gene related suggestions should now look like ordinary compact result cards in the closed state. This is visual parity only; retrieval, ranking, and related-concept selection are unchanged.
