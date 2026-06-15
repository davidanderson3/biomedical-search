# Active Diagnosis Over Following Lab Result

Date: 2026-06-11

## Problem

WFN-011 showed a wrong-first trust issue in `paragraph_91`: the sentence said a
toddler had lead poisoning after an elevated blood lead level, but the abnormal
lab-result concept ranked just above the poisoning diagnosis.

The direct lab query still needs to stay lab-focused, so this could not be a
generic lead-poisoning boost or blood-lead demotion.

## Change

Added `active_diagnosis_component` for sentence-bounded, multi-token,
assertable disease hits where the query span is immediately preceded by
`had`, `has`, `have`, or `having` and immediately followed by `after` or
`following`.

The component is blocked for comparator, denied, negated, historical, and
family-history contexts, and is surfaced in both score breakdown and confidence
support.

## Result

Focused live probe on `http://127.0.0.1:8766` now ranks `C0023176` Lead
Poisoning first with `active_diagnosis_component` 0.14. `C0262463` Blood lead
level above reference range remains visible but no longer ranks first in the
diagnosis sentence.

The direct query `elevated blood lead level` does not give Lead Poisoning the
active-diagnosis boost and remains lab/result-focused.

## Verification

- Focused pytest: 3 passed.
- Focused ranker slice: 9 passed.
- `py_compile`: passed.
- SQI-2026-06-11-015 smoke helper: passed static, focused, standing clinical,
  rotating 50-query, and patient-portal gates.
- Comparable SQI-2026-06-11-011 rotating seed: passed with 0 wrong-first rows.
- Full 168-row clinical benchmark: passed with 844/874 expected concepts at top
  10, 148/168 rows complete at top 10, 146/168 strict top 10, and 2 wrong-first
  rows.

## Decision

Keep. This closes WFN-011 without hiding lab-result intent. WFN-009 and WFN-012
remain open.
