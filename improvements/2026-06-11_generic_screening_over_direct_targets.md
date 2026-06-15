# Generic Screening Over Direct Targets

- Iteration: SQI-2026-06-11-020
- Type: ranking
- Status: kept with smoke caveat

## Weakness

The source-specific query `colonoscopy screening and colorectal cancer literature`
ranked broad `C0199230` Screening for cancer first, ahead of the directly named
procedure `C0009378` colonoscopy and disease endpoint `C0009402` Colorectal
Carcinoma.

## Change

Added `generic_screening_context_penalty` for broad screening labels when the
query contains screening intent plus direct biomedical target anchors that the
candidate does not support. The rule preserves direct generic screening queries
such as `cancer screening literature` and preserves specific screening concepts
such as Screening for Colorectal Cancer.

## Evidence

- Focused ranker tests passed: 5 tests.
- Live WFN-013 probe now returns colonoscopy first, Colorectal Carcinoma second,
  and Screening for cancer fifth.
- Source-specific rerun
  `SQI-2026-06-11-020_source_specific_generic_screening` has 14/15 rows complete
  at top 10, 34/35 expected concepts at top 10, 15/15 top-on-target, and
  0 wrong-first rows.
- Formal SQI-2026-06-11-020 smoke helper passed static, focused, standing
  clinical, and rotating 50-query checks. It failed the patient-portal step on
  `source_count_no_unexpected_collapse` because current public-output payloads
  no longer include top-level source-code `source_contributions`; patient-portal
  quality metrics were unchanged from SQI-2026-06-11-019.

## Remaining

The source-specific lane still misses DailyMed warning context `C1550014`. The
patient-portal source-count gate also needs normalization for public-output
payloads that omit top-level source-contribution summaries.
