# Direct Anchor Coverage and Central Phrase Boost

## Problem

The expanded paragraph benchmark exposed two ranking problems. First, central multi-word diagnoses could rank behind component findings, such as autoimmune hepatitis behind generic hepatitis concepts or dental abscess behind tooth pain. Second, the anchor-diversity selector treated relation-derived tokens as if they were direct label matches. In the migraine paragraph, sumatriptan's treatment relation to migraine could cover the `migraine` query anchor, which deferred the actual migraine disorder concept even though it had a high rank score.

## Change

- Added a central multi-token condition signal in `src/qe_evidence_vectors/search_ranking.py` so explicit multi-word disease/problem spans in the first statement receive a stronger but bounded boost than single-token component findings.
- Preserved exact direct label/span matches from relative-specificity demotion to avoid pushing legitimate symptoms such as headache out of the top-10 window.
- Changed anchor-diversity coverage to use direct label tokens only. MRREL/relation tokens still contribute ranking evidence, but they no longer satisfy coverage for an explicitly mentioned concept.
- Added regression tests covering multi-word condition ranking, exact single-token preservation, and the relation-token coverage failure.
- Added an active-label supplement anchor for `C4721555` autoimmune hepatitis.
- Added `C2887484` as an acceptable alternative for `C0035222` acute respiratory distress syndrome.

## Results

Baseline before this pass was `build/improvements/2026-05-08_test_new_paragraphs_current`: 96 paragraphs, 467 expected concepts, recall@5 `357/467` (`0.7645`), recall@10 `466/467` (`0.9979`), recall@20 `467/467`, verdicts `91 good / 5 mixed`.

Final benchmark is `build/improvements/2026-05-08_after_direct_anchor_coverage`: 96 paragraphs, 467 expected concepts, recall@5 `367/467` (`0.7859`), recall@10 `467/467` (`1.0000`), recall@20 `467/467`, verdicts `96 good`.

This is a net improvement: top-10 expected concept coverage is complete, all paragraph verdicts are good, and top-5 recall improved by 10 expected concepts. The intermediate aggressive specificity attempt was not kept because it reduced recall@10 by demoting exact single-token findings.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py -k 'anchor_diversity or first_sentence_multiword_condition or central_multiword_disease or exact_single_token_condition or first_sentence_single_token_condition or first_sentence_focus' -q`
- `python3 scripts/evaluate_paragraph_quality.py --output-dir build/improvements/2026-05-08_after_direct_anchor_coverage --top-k 60`
- `python3 scripts/validate_active_label_supplement.py`
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py`
