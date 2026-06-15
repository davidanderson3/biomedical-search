# Reaction Diagnosis Over Trigger Exposure

Date: 2026-06-11

## Problem

WFN-009 showed a wrong-first trust issue in `paragraph_43`: the sentence said
the patient developed anaphylaxis after a bee sting, but the trigger concept
ranked above the reaction diagnosis.

Direct trigger lookup still needs to stay trigger-focused, so this could not be
a generic Bee sting demotion.

## Change

Added `reaction_diagnosis_component` for sentence-bounded condition hits where
the span immediately follows `developed` and the same sentence has an earlier
`after` or `following` trigger clause.

The component is blocked for comparator, denied, negated, historical, and
family-history contexts. Exact primary-name matches get a larger component than
alternate-label matches so the plain Anaphylaxis concept can outrank
Anaphylactic shock when the query text says `anaphylaxis`.

## Result

Focused live probe on `http://127.0.0.1:8766` now ranks `C0002792` Anaphylaxis
first with `reaction_diagnosis_component` 0.62. `C0413120` Bee sting remains
visible but no longer ranks first in the reaction sentence.

The direct query `bee sting` still ranks Bee sting first and does not give
Anaphylaxis the reaction-diagnosis boost.

## Verification

- Focused pytest: 4 passed.
- Focused ranker slice: 8 passed.
- `py_compile`: passed.
- SQI-2026-06-11-016 smoke helper: passed static, focused, standing clinical,
  rotating 50-query, and patient-portal gates.
- Comparable SQI-2026-06-11-011 rotating seed: passed with 0 wrong-first rows.
- Full 168-row clinical benchmark: passed with 844/874 expected concepts at top
  10, 148/168 rows complete at top 10, 147/168 strict top 10, and 1 wrong-first
  row.

## Decision

Keep. This closes WFN-009 without hiding direct trigger intent. WFN-012 remains
open.
