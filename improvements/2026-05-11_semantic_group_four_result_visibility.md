# Semantic Group Four-Result Visibility

## Change

Removed the bottom fade overlay from scrollable semantic result buckets and changed the scrollable threshold from more than 3 items to more than 4 items.

## How It Improved Things

Semantic group buckets with exactly four results no longer render the fourth result under a visual fade. Larger buckets still get the visible right-side scroll indicator, but content is no longer obscured by an overlay that can make the final item unrevealable when there is no actual scroll range.

## Validation

Inspected the relevant render path in `docs/search_quality/app.js` and bucket CSS in `docs/search_quality/server.css`. This is a CSS/UI-only fix; no backend tests were needed.
