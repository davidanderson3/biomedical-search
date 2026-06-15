# Consumer Lay-Language Active Aliases

## Problem

The consumer lay-language lane showed that everyday patient wording often missed
the intended clinical concept or ranked literal/noise concepts first. The
highest-signal failures were synonym problems, not broad ranking problems.

## Change

Added governed active-label supplement rows for:

- `water pill` -> diuretics
- `water pill furosemide` -> furosemide
- `pee test` -> urinalysis
- `belly pain` -> abdominal pain
- `sugar diabetes` -> diabetes mellitus
- `heart tracing` and `EKG` -> electrocardiography
- `colon scope` -> colonoscopy
- `stomach scope` -> endoscopy
- `blood thinner` -> anticoagulants

Each row includes a semantic type, field, rationale, specialty, and context
terms. This keeps the fix in the governed synonym layer instead of adding a new
ranking heuristic.

## Result

Direct in-process `SearchIndex` checks with no vectors put all 10 covered lay
phrases on the intended CUI first. `water pill furosemide` ranks furosemide
ahead of the broad diuretic class.

The live consumer benchmark was not rerun. A temporary API start on port 8769
was stopped while still loading vectors before the HTTP listener became
available.

## Verification

- `python3 scripts/validate_active_label_supplement.py`
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/active_label_supplement.py tests/test_evidence_vectors.py`
- `PYTHONPATH=src:scripts python3 -m pytest tests/test_evidence_vectors.py -k "active_label_supplement_file_passes or consumer_lay_language_supplements or active_label_supplement_validation" -q`
- `python3 scripts/build_search_rule_inventory.py`

## Follow-Up

Restart the search API, rerun the `consumer_lay_language` layer, and then work
any remaining literal/anatomy/device/gene drift as targeted suppression or
ranking guards.
