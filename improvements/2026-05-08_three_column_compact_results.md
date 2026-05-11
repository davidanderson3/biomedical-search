# Three-Column Compact Results

## Request

Display semantic groups 3 per row and compact concept results even more.

## Change

- Replaced the returned semantic-group result rail with a responsive CSS grid.
- Desktop layout now displays semantic groups in 3 columns.
- Medium screens switch to 2 columns.
- Mobile screens switch to 1 column.
- Removed the fixed 220px group-width rail behavior and horizontal scroll behavior.
- Reduced result-group padding, group gaps, concept-card padding, title font size, semantic-type font size, and details spacing.

## Measured Effect

- Semantic groups per desktop row: changed from a horizontal single-row scroll rail to 3 visible columns per row.
- Result group width: changed from fixed 220px columns to fluid `minmax(0, 1fr)` grid columns.
- Compact result card padding: changed from `6px` to `5px 6px`.
- Compact result card gap: changed from `5px` to `3px`.
- Concept title font size: changed from `12px` to `11px`.
- Semantic type font size: changed from `11px` to `10px`.
- Compact closed-card details spacing: removed the card-level details border and reduced summary line height.

## Verification

- Confirmed the served CSS contains the new 3-column results grid.
- Confirmed the served CSS no longer contains the removed fixed `220px` result-group width or horizontal scroll rail rules.
- Confirmed `/api/status` is healthy on the running server.

## Result

This makes the result area denser and easier to scan across semantic groups. It is a presentation-only change and does not affect retrieval, ranking, evidence, indexing, or evaluation metrics.
