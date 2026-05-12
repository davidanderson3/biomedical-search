# Remove Patient Cohort UI

## Change

Removed the client-side Patient Cohort result group. This deletes the heuristic cohort phrase detector, cohort card renderer, and cohort-specific CSS from the search quality UI.

The backend OHDSI/cohort mining code was left intact because it feeds relationship artifacts and is separate from the visible Patient Cohort card.

## Result

Verification passed:

- `node --check docs/search_quality/app.js`
- No remaining `Patient Cohort`, `renderPatientCohortGroup`, `buildPatientCohort`, or cohort-specific CSS identifiers in the docs UI assets.
- Served JS/CSS from `http://127.0.0.1:8766/` no longer contain the removed Patient Cohort UI identifiers.

## Impact

This simplifies the results display and removes an inferred UI group that could distract from the ranked semantic groups. Search behavior, ranking, and indexed content are unchanged.
