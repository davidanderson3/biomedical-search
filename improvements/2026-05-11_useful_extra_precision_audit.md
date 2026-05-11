# Useful Extra Precision Audit

## What Changed

- Added `config/search_quality_useful_extra_cuis.tsv` for explicit, clinically useful paragraph results that are not part of the core expected CUI set.
- Updated `scripts/audit_paragraph_precision.py` to read the useful-extra file and remove those CUIs from suspect precision counts while still counting them separately.
- Added a regression test showing that an explicit useful extra, such as `Leg edema` in a heart failure paragraph, no longer appears as a precision-audit suspect.

## Measured Impact

This does not change search ranking. It improves the evaluation layer so we stop treating useful explicit concepts as false precision failures.

Using the latest paragraph payloads:

- Suspect top-10 hits before calibration: 66
- Suspect top-10 hits after calibration: 25
- Suspect hits per paragraph: 0.62 -> 0.24
- Useful extra top-10 hits separated from suspects: 41
- Configured useful-extra rows: 41
- Visible top-3 nonexpected suspect flags: 45 -> 5

Search quality metrics from the same payloads remain:

- Paragraphs: 106
- Expected concepts: 516
- Recall@10: 516/516 (100.0%)
- Queries with all expected concepts@10: 106/106
- Verdicts: 106 good

## Interpretation

This is a sustainability improvement. The remaining audit target list is now much cleaner and mostly contains actual low-value candidates such as ordinals, administrative state, generic qualifiers, and weak unanchored measurement units. The next ranker pass should focus on that smaller set instead of suppressing useful explicit clinical concepts like `Leg edema`, `MRSA infection`, `Viral Load result`, or `Knee pain`.
