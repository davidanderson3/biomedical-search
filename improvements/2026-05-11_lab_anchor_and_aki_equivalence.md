# Lab Anchor Exact Credit And AKI Equivalence

## Change

Treated `Laboratory Procedure` as a useful exact-span semantic type in the ranker. This lets curated active-label lab anchors, such as `Ketones`, receive the same exact-match and curated-label credit that lab result concepts already receive.

Also added an acceptable benchmark equivalence from `C2609414` Acute kidney injury to `C0022660` Kidney Failure, Acute. In the paragraph output, `C0022660` is clinically on target because it is returned with the matched label `Acute kidney injury`.

## Improvement

Before this change, the DKA paragraph returned `C0202110` Ketone bodies measurement at rank 30 even though the query explicitly said `serum ketones` and the active-label supplement already contained a curated `Ketones` row. After the change, `C0202110` moved to rank 4 with exact-span and curated-label credit.

The contrast-associated kidney injury paragraph was previously counted as mixed because the expected CUI was absent from the first 10, even though the top result was the clinically equivalent acute kidney failure concept with an acute kidney injury matched label. The benchmark now records that equivalence instead of treating it as a failure.

## Verification

- Added a regression test for curated exact credit on a lab-procedure anchor.
- Focused tests passed: 11 passed, 204 deselected.
- Compile checks passed for the touched ranker, evaluator, and test file.
- Paragraph evaluation wrote results to `build/improvements/2026-05-11_lab_anchor_and_aki_equivalence_eval/`.

Benchmark change from the previous run:

- Verdicts improved from 94 good / 2 mixed to 96 good / 0 mixed.
- Recall@10 improved from 463/467 (99.1%) to 467/467 (100.0%).
- Queries with all expected concepts at 10 improved from 92/96 to 96/96.
- `paragraph_39` moved `C0202110` Ketone bodies measurement from rank 30 to rank 4.

## Remaining Limitations

This does not mean the broader search problem is solved. The benchmark is still a finite set of curated paragraphs, and acceptable CUI equivalences should remain conservative. The sustainable part of this change is the semantic fix for lab-procedure exact anchors; future equivalences should only be added when the returned concept is clinically interchangeable in the specific query context.
