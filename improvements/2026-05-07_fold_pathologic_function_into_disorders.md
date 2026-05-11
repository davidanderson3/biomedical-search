# Fold Pathologic Function Into Disorders

Date: 2026-05-07

## Goal

Remove the separate `Pathologic Function` result area and include those concepts under the Disorders `Diseases & Syndromes` bucket.

## Change

- Removed the standalone `DISO_PATHOLOGIC_FUNCTION` result bucket from `docs/search_quality/app.js`.
- Added `pathologic function` to the semantic type list used by the `Diseases & Syndromes` Disorders bucket.
- Left individual result semantic type chips unchanged, so a concept can still show its true UMLS semantic type as `Pathologic Function` while being grouped with Disorders.

## Measurement

- No ranking or recall change expected.
- UI grouping simplified: one fewer result column/area, and DISO pathologic-function concepts now appear in `Diseases & Syndromes`.

## Verification

- `node --check docs/search_quality/app.js`
- `rg -n "DISO_PATHOLOGIC_FUNCTION|label: \"Pathologic Function\"|PATHOLOGIC_FUNCTION_TYPES" docs/search_quality/app.js docs/search_quality_server.html`
  - Result: no matches
- Restarted the local search server on port `8766`; `/api/status` loaded with `active_label_supplement_labels: 46`.
