# Related Result Visual Treatment

## Problem

Related semantic-bucket items looked visually different from normal concept rows. They used a separate related-result style, which made them feel like a separate widget instead of concepts in the same result list.

## Change

Related items now keep the same compact three-column result-row structure and font size as normal results. The related rows are visually marked with dark red styling and a small `Related` marker in the semantic-type column.

## Improvement

The semantic group cards should now scan more consistently: normal and related concepts occupy the same amount of visual space, while related concepts remain distinguishable by color and label.

## Verification

- `node --check docs/search_quality/app.js` passed.
