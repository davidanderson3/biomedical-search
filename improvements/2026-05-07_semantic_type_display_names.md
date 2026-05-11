# Semantic Type Display Names

Date: 2026-05-07

## Goal

Stop displaying `Finding or Symptom` as though it were a UMLS term type or semantic type.

## Change

- Updated `docs/search_quality/app.js` so linked concepts display the actual MRSTY-style semantic type name:
  - `Sign or Symptom`
  - `Finding`
- Left the combined result bucket in place because it is only a UI grouping column, not a claimed UMLS semantic type or TTY.

## Measurement

- No ranking or recall change expected.
- Terminology correctness improved: the invalid display phrase no longer appears in runtime code, configuration, tests, scripts, or product docs.

## Verification

- `node --check docs/search_quality/app.js`
- `rg -n "Finding or Symptom|finding or symptom" docs src config tests scripts`
  - Result: no matches
