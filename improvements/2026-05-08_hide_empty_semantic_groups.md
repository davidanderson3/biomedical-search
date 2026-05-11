# Hide Empty Semantic Groups

## Request

Work on the next logical high-impact improvement and document exactly how it improved things.

## Change

- Updated result bucketing so semantic groups with no visible returned or related concepts are not rendered.
- Removed the empty-panel message and unused empty-group CSS.
- Kept a fallback message for the edge case where search returns hits but none map to a displayed semantic group.

## Why This Was Next

After switching semantic groups to a 3-column grid, empty groups consumed full grid cells and reduced scan density. Removing empty groups gives more space to groups that actually contain concepts.

## Measured Effect

Before this change, the result grid always rendered all 8 semantic groups.

Sample searches after the change:

- `heart failure with reduced ejection fraction`: 5 of 8 groups populated, 3 empty panels removed.
- `semaglutide adverse events`: 5 of 8 groups populated, 3 empty panels removed.
- `central venous catheter placement ultrasound guided`: 4 of 8 groups populated, 4 empty panels removed.

## Verification

- `node --check docs/search_quality/app.js` passed.
- Confirmed served JavaScript contains the non-empty group filter.
- Confirmed served CSS no longer contains `result-group-empty`.
- Confirmed `/api/status` is healthy on the running server.

## Result

This improves scan density and reduces wasted space in the returned-CUI grid. It is presentation-only and does not change retrieval, ranking, evidence, indexing, or evaluation metrics.
