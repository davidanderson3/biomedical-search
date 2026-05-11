# Suggestion Dropdowns

## Request

Put clinical note and paragraph suggestions in a dropdown to save space.

## Change

- Replaced the visible clinical note suggestion button grid with a single `Clinical note suggestions` select control.
- Replaced the visible paragraph test cards with a single `Paragraph tests` select control plus the existing `Load set` command.
- Preserved the behavior where choosing an example copies it into the search box and immediately runs search.
- Guarded the placeholder option so an empty dropdown value does not accidentally run the first example.
- Removed the rotating "More" controls because the dropdowns expose the full local suggestion sets directly.
- Updated responsive CSS so the two compact selectors collapse to one column on small screens.

## Measured Effect

- Clinical examples available: 200.
- Paragraph tests available: 80.
- Previous visible suggestion controls: 12 at a time, made up of 8 clinical note buttons and 4 paragraph test cards.
- New visible suggestion controls: 3, made up of 2 dropdowns and 1 `Load set` button.
- Visible suggestion controls were reduced by 75% while keeping all 280 examples accessible from the same search panel.

## Verification

- `node --check docs/search_quality/app.js` passed.
- Confirmed the old rotating suggestion IDs/classes are no longer referenced by the app or stylesheet.

## Result

This improves layout density and should reduce vertical scrolling in the main search panel. It does not change concept retrieval, ranking, indexing, or evaluation behavior.
