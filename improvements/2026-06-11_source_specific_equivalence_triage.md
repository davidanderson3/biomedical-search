# Source-Specific Equivalence Triage

## Weakness

The source-specific evidence lane failed at 10/15 rows complete at top 10. Review
showed four misses were acceptable CUI splits rather than search failures:
HbA1c measurement/analyte wording, DailyMed adverse-reaction wording, and EGFR
receptor/protein versus EGFR gene in PubTator3 relationship rows.

## Change

- Accepted `C0019018` and `C5979904` for `C0202054` HbA1c measurement wording.
- Accepted `C0413696` and `C0559546` for `C0041755` adverse-reaction wording.
- Accepted `C1414313` for `C0034802` in EGFR relationship queries.
- Opened `WFN-013` for the remaining wrong-first row instead of accepting
  broad `C0199230` Screening for cancer as a substitute.

## Result

`SQI-2026-06-11-019_source_specific_equivalence_triage` improved to 14/15 rows
complete at top 10 and 34/35 expected concepts at top 10. The lane remains
blocking because `dailymed_label_02` still misses `C1550014` and
`pubmed_pmc_lit_02` still ranks broad cancer screening first.
