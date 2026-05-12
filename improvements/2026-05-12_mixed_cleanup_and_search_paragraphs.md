# Mixed Cleanup and Search Paragraphs

## Problem

The full paragraph benchmark had one remaining `mixed` result: `paragraph_118`, where broad `Aortic Aneurysm` ranked above the clinically explicit `Ruptured abdominal aortic aneurysm`.

## Change

- Added an active label for `C0265012` `ruptured abdominal aortic aneurysm`, gated to vascular emergency context.
- Updated `paragraph_118` to expect the specific ruptured AAA concept directly instead of relying on broader acceptable alternatives.
- Added six search-style paragraphs covering common user queries: pulmonary embolism/DVT, acute ischemic stroke, asthma exacerbation, postpartum hemorrhage, acute otitis media, and AKI with hyperkalemia.
- Added active label support for `C0271429` `acute otitis media`.
- Added an acceptable alternative for hemoglobin finding when a paragraph says hemoglobin dropped.

## Result

Targeted evaluation of the changed/new rows improved from 6 `good` / 1 `mixed` to 7 `good` / 0 `mixed`, with recall@10 improving from 34/35 to 35/35.

Full benchmark now has 140 paragraphs and 702 expected concepts. It produced 140 `good` verdicts, no `mixed`, no `poor`, recall@10 700/702 (99.7%), recall@20 702/702 (100%), and recall@60 702/702 (100%).

## Verification

- `python3 -B -m pytest tests/test_evidence_vectors.py -k "active_label_supplement" -q`
- `python3 scripts/evaluate_paragraph_quality.py --queries /private/tmp/paragraph_118_135_140.tsv --output-dir build/improvements/2026-05-12_mixed_and_new_paragraphs_targeted_v2 --top-k 60`
- `python3 scripts/evaluate_paragraph_quality.py --output-dir build/improvements/2026-05-12_mixed_and_new_paragraphs_full --top-k 60`
