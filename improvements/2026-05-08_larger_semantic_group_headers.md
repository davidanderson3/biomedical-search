# Larger Semantic Group Headers

## Request

Make the semantic group names bigger.

## Change

- Increased `.result-group-title` from `12px` to `15px`.
- Increased `.result-group-code` and `.result-group-count` from `10px` to `11px` so the header metadata scales with the larger group name.

## Measured Effect

Before:

- Semantic group title font size: `12px`
- Group code/count font size: `10px`

After:

- Semantic group title font size: `15px`
- Group code/count font size: `11px`

This is a 25% increase for the group names while preserving compact cards and scrollers.

## Verification

- Confirmed the running server is serving the updated CSS.

## Result

Semantic group names should be easier to scan without changing retrieval, ranking, grouping, or card contents.
