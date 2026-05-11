# Semantic Group Height Around Seven Results

## Request

Set the height of each semantic group box at around seven results.

## Change

- Reduced `.result-group-items` max height from `min(560px, 58vh)` to `min(360px, 42vh)`.
- Kept the internal semantic group scroller behavior.

## Measured Effect

Before:

- Semantic group item scroller max height: `min(560px, 58vh)`
- Large buckets could show substantially more than seven compact cards before scrolling.

After:

- Semantic group item scroller max height: `min(360px, 42vh)`
- The visible area is closer to roughly seven compact result rows, depending on whether opened `Details` sections increase individual row height.

## Verification

- Confirmed the running server is serving the updated CSS value.

## Result

Semantic group boxes are shorter and easier to scan across the three-column layout while still allowing full group review via scrolling.
