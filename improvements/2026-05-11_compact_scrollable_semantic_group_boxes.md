# Compact Scrollable Semantic Group Boxes

## Change

Reduced the semantic group result box height and made overflow visibly scrollable.

UI changes:

- lowered `.result-group-items` from `max-height: min(260px, 34vh)` to `max-height: min(188px, 28vh)`;
- added a `result-group-scrollable` class when a semantic group has more than three visible rows;
- added keyboard focus to scrollable result lists with `tabindex="0"`;
- added visible scrollbar styling, a right scroll rail, and a bottom fade cue for buckets with hidden content.

## Why

The semantic group boxes were still taking too much vertical space. The browser could scroll each group, but on systems with overlay scrollbars it was not obvious that more content was available.

## Measured Impact

This is a UI-only change. It does not alter search ranking, vector retrieval, labels, relations, semantic bucketing, or benchmark recall.

Static verification:

- `result-group-scrollable` is applied in `docs/search_quality/app.js` when `group.items.length > 3`.
- `.result-group-items` now has a lower max height and explicit scrollbar styling in `docs/search_quality/server.css`.

Expected result: semantic group cards fit more densely on the page, and users can see when a group has additional scrollable content.

