# Realistic Note-Format Source-Code Routing And Contained Finding Cleanup

- Iteration: `SQI-2026-06-17-005`
- Backlog row: `SQB-015 Realistic note-format recall`
- Status: partial shipped
- Type: routing, ranking

## Problem

The realistic clinical-note lane was weaker than the scorecard implied in a
fresh uncached run because several note-style inputs were being treated as
source-code lookups. Strings such as operative notes, MAR notes, and prior
authorization drafts contain a header before a colon followed by prose and
numeric values. The source-code path accepted those as code-like requests,
returned `backend: source_code`, and skipped normal search.

A separate note-format row also exposed a first-answer safety issue: an exact
contained finding for reduced ejection fraction could rank above the fuller
heart-failure-with-reduced-ejection-fraction condition when both were supported.

## Change

The source-code query detector now rejects parsed `system:code` values whose
code side contains whitespace. True code searches such as `MEDDRA:10021099`,
`ICD-10-CM:E11.9`, and bare source codes still route through source-code lookup.
Focused tests cover operative-note, MAR-note, prior-authorization, long section
header, and true source-code cases.

The ranker also applies a contained-finding penalty when a short exact finding
is contained inside a fuller disease candidate with similar support. This keeps
the reduced-ejection-fraction finding from outranking the HFrEF condition in the
note-format row.

## Result

Direct API checks confirmed that realistic note headers now use normal
Elasticsearch search instead of source-code fallback. The final uncached
`clinical_text_type_variety` rerun had 24/24 top-on-target rows, 0 wrong-first
rows, 0 configured disallowed concepts, and 0 cache hits.

This did not close `SQB-015`: the lane remains 8/24 complete at strict top 10
with 94/115 expected concepts found. The useful next work is focused recall for
the remaining secondary-concept misses by note type.

## Verification

- `python3 -m pytest -q tests/test_evidence_vectors.py -k 'hfref_condition_over_contained_ejection_fraction_finding or exact_primary_condition_over_later_treatment_drug or note_style_headers_with_numbers_do_not_trigger_source_code_mode or long_sample_section_label_does_not_trigger_source_code_mode or source_code_system'`
- Direct API check against `http://127.0.0.1:8767` confirmed `Brief Op Note: ... 10 mL` returns `backend: elasticsearch` with no cache hit.
- `python3 scripts/run_search_quality_suite.py --suite-id SQI-2026-06-17-005-note-format-routing-and-contained-finding --only clinical_text_type_variety --base-url http://127.0.0.1:8767 --command-timeout 600`
- Run artifact: `build/search_quality_experiments/runs/SQI-2026-06-17-005-note-format-routing-and-contained-finding-clinical_text_type_variety_search-quality-test-suite-clinical-text-type-variety/run.json`

## Follow-Up

Keep `SQB-015` open as the top active P0 recall lane. Work the remaining
radiology, pathology, operative, nursing, lab, therapy, and prior-authorization
misses in failure-class batches while preserving 0 wrong-first rows.
