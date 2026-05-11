# Precision Audit And Generic Filler Filter

## What Changed

- Added `scripts/audit_paragraph_precision.py`, a reusable paragraph precision audit that reads saved search payloads and flags visible top-N results that are not expected CUIs or accepted alternatives and have low-specificity signals.
- Extended the evidence-aware ranker to suppress more generic visible fillers in clinical paragraph context, including labels such as `Suspected diagnosis`, `Compatible`, `Critical`, `Baseline`, `Granular`, `mg/dL`, `per 4.0 Milliliters`, `High dose`, `Singular`, `Cohort Studies`, and similar status/unit/qualifier fragments.
- Added tests to keep these fillers suppressed in paragraph-like clinical context while preserving direct queries for the same concepts.
- Added a guard test for `Progression-Free Survival`, because an intermediate version treated it as generic even though it is a clinically meaningful oncology endpoint.

## Measured Impact

Before this change, the precision audit over the 106 paragraph payloads found:

- Suspect top-10 hits: 84
- Suspect hits per paragraph: 0.79
- Generic/status-label audit flags: 19
- Low-specificity semantic type flags: 35
- Other/uncategorized flags: 27

After this change:

- Suspect top-10 hits: 71
- Suspect hits per paragraph: 0.67
- Generic/status-label audit flags: 0
- Low-specificity semantic type flags: 21
- Other/uncategorized flags: 14

The paragraph quality benchmark stayed intact:

- Paragraphs: 106
- Expected concepts: 516
- Recall@10: 516/516 (100.0%)
- Queries with all expected concepts@10: 106/106
- Verdicts: 106 good

## Interpretation

This improved precision without losing expected concept recall. The audit is intentionally conservative: nonexpected does not mean false positive, because the expected CUI list is not exhaustive. The useful improvement is that obvious generic/status/unit fillers no longer occupy visible top-10 result slots in multi-concept clinical paragraphs, while direct searches for those concepts still work.

Remaining low-hanging precision work is mostly in relation/source weighting and benchmark curation, not broad semantic filtering. Frequent remaining audit targets such as `Prescribed medications`, `Virus Diseases`, and some broader disease/procedure concepts need case-specific review because some are reasonable related concepts depending on the paragraph.
