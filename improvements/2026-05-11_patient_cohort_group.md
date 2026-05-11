# Patient Cohort Group

## Change

Added a lightweight patient cohort inference/display pass to the search UI. The result page now tries to identify the patient or research cohort from the query text and displays it as a `Patient Cohort` group before the semantic concept cards.

The cohort detector uses:

- subject text from the existing linked-statement extraction
- text patterns for common cohort phrases such as `pregnant patient`, `ICU patient`, `postoperative patient`, `child with ...`, and `patients receiving ...`
- linked CUI spans that fall inside the inferred cohort phrase

## Result

This makes cohort context visible instead of burying it among findings, diseases, drugs, and procedures. Examples it is designed to surface include:

- `ICU patient with septic shock`
- `pregnant patient at 34 weeks`
- `postoperative patient`
- `patients receiving vancomycin for diabetic foot osteomyelitis`
- `child with fever and barking cough`

The cohort card includes linked CUI chips when concepts are matched inside the cohort phrase.

## Limitations

This is intentionally heuristic and UI-side only. It should help review typical clinical paragraphs, but it is not yet a validated cohort-definition miner. Complex inclusion/exclusion criteria, comparator arms, and temporal eligibility windows still need a structured backend model.

## Verification

- `node --check docs/search_quality/app.js`
