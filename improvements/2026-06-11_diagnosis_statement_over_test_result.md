# Diagnosis Statement Over Test Result Ranking

## Problem

The wrong-first ledger identified `paragraph_111` as the active rotating
wrong-first row. The sentence explicitly says gestational diabetes was diagnosed
after an abnormal oral glucose tolerance test, but the test/result concept
ranked first over the diagnosis.

Baseline observations:

- SQI-2026-06-11-011 rotating smoke: `C1847425` Abnormal oral glucose tolerance
  ranked first and `C0085207` Gestational Diabetes ranked second.
- Full clinical rerun from 2026-06-10: `C0017741` Glucose tolerance test ranked
  first and Gestational Diabetes ranked fourth.

## Change

- Added `diagnosis_statement_component` to the ranker.
- The component applies only to central multi-token condition hits whose query
  span is syntactically tied to a diagnosis phrase such as `X was diagnosed` or
  `diagnosis of X`.
- Observation/procedure test concepts receive no component, and direct test
  queries remain protected.
- Added focused tests covering the gestational diabetes sentence and direct oral
  glucose tolerance test intent.
- Regenerated `docs/search_rule_inventory.html`.

## Result

Focused live probe on `http://127.0.0.1:8766` ranked Gestational Diabetes first
with `diagnosis_statement_component` 0.16. Abnormal oral glucose tolerance and
Glucose tolerance test stayed visible but no longer ranked first.

Comparable rotating rerun using the SQI-2026-06-11-011 sample seed improved from
1 wrong-first row to 0 wrong-first rows while keeping 42/50 strict top-10 rows.

The formal SQI-2026-06-11-013 smoke helper passed. The latest new rotating
sample still found 2 wrong-first rows, and the current full clinical rerun found
5 wrong-first rows, so the product score was not raised.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py::test_query_ranker_prefers_diagnosed_condition_over_supporting_glucose_tests tests/test_evidence_vectors.py::test_query_ranker_demotes_generic_diabetes_in_gestational_context -q`
- `python3 -m pytest tests/test_evidence_vectors.py -k "diagnosed_condition or gestational or first_sentence or primary_condition" -q`
- `python3 -m py_compile src/qe_evidence_vectors/search_ranking.py tests/test_evidence_vectors.py`
- Focused live API probe for `paragraph_111`.
- `python3 scripts/build_search_rule_inventory.py`
- SQI-2026-06-11-013 iteration smoke helper.
- Comparable SQI-2026-06-11-011 rotating sample seed check.
- Full 168-row clinical benchmark rerun.

## Decision

Keep. The target wrong-first class is closed without hiding test concepts, but
the refreshed broad benchmarks expose new wrong-first rows that should drive the
next iteration.
