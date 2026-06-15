# Coverage Representativeness Audit

## Problem

The search-quality loop was increasingly driven by specific reviewed failures.
That is useful for regression safety, but it did not answer whether the tested
CUIs were representative of common clinical use or concentrated in a few
semantic groups.

## Change

Added `scripts/build_search_quality_coverage_audit.py` to read current
search-quality target files, classify expected and risk CUIs by semantic group
and source file, and write JSON, Markdown, and TSV audit outputs.

Added `coverage_representativeness_audit` as a nonblocking known-weakness suite
layer. The suite runner now expands `{suite_id}` and `{layer_id}` placeholders
for command layers so generated audit outputs are tied to a suite run.

## Result

The audit found 609 unique target CUIs, 2,210 target mentions, and 87 unique
risk/disallowed CUIs. Disorders are the largest group at 48.3% of target
mentions. Anatomy, Phenomena, and Physiology each have fewer than 5 unique
target CUIs.

This means the suite is broader than a handful of examples, but it is not yet a
prevalence- or workflow-weighted clinical coverage model.

## Verification

- `python3 -m json.tool config/search_quality_suite.json >/dev/null`
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile scripts/build_search_quality_coverage_audit.py scripts/run_search_quality_suite.py tests/test_search_quality_coverage_audit.py tests/test_search_quality_suite.py`
- `PYTHONPATH=src:scripts python3 -m pytest tests/test_search_quality_coverage_audit.py tests/test_search_quality_suite.py -q`
- `PYTHONPATH=src:scripts python3 scripts/run_search_quality_suite.py --suite-id SQI-2026-06-15-001-coverage-audit --only coverage_representativeness_audit --fail-on never --command-timeout 60`

## Follow-Up

Build a representative common-clinical target list with reviewed quotas by
semantic group and workflow, and keep it separate from one-off regression rows.
