# Remove Load Set Button

## Request

Remove the `Load set` button.

## Change

- Removed the `Load set` button from the Paragraph tests dropdown area.
- Removed the unused `loadParagraphsBtn` DOM lookup.
- Removed the `loadParagraphTestsIntoQuerySet()` click handler path.
- Removed CSS rules that only existed for the button/header wrapper.

## Measured Effect

Before:

- Paragraph tests had a dropdown plus a `Load set` button.
- Clicking `Load set` copied all paragraph tests into the query-set textarea, adding a second workflow beside the dropdown and `Run query set`.

After:

- Paragraph tests show only the dropdown.
- Selecting a paragraph still runs that paragraph as a search.
- The evaluation panel still has `Run query set` for manually entered query sets.
- No remaining references to `Load set`, `loadParagraphsBtn`, `loadParagraphTestsIntoQuerySet`, or `suggestion-picker-head` exist in the UI HTML, JS, or CSS.

## Verification

- `node --check docs/search_quality/app.js` passed.
- Confirmed the running server is serving HTML/JS/CSS with no `Load set` references.

## Result

The top search panel is simpler and has one less control competing with paragraph-test search. This is UI cleanup only; search, ranking, indexing, and query-set execution are unchanged.
