# Relation Result Font Alignment

## Goal

Make related/relation result rows use the same title font size as regular concept results inside semantic group cards.

## What changed

- Pinned relation-card titles in `.compact-result-summary .related-concept.compact-result-title` to the same compact title typography as regular result titles:
  - `font-size: 11px`
  - `font-weight: 850`
  - `line-height: 1.15`

## Impact

Relations still render in dark red and retain the `Related` marker, but they no longer appear typographically larger than regular results in the same semantic group box.

## Verification

Static CSS cascade check: the scoped selector now overrides the later generic `.related-concept { font-size: 12px; }` rule for relation cards inside compact result summaries.
