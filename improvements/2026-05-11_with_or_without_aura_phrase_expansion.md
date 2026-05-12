# With/Without Aura Phrase Expansion

## Problem

A status migrainosus paragraph explicitly mentioned `migraine with or without aura`, but `Migraine with Aura` did not appear in the useful result window. The phrase also contained `without`, which the denial logic treated like a negation and penalized disease concepts that should have been retained.

## Change

- Expanded label-fallback anchors for `X with or without Y` into both `X with Y` and `X without Y`.
- Added direct span matching so both variant labels can point to the same source phrase, `migraine with or without aura`.
- Updated denial scope handling so `with or without` is not interpreted as a denial context.
- Preserved exact disease variants during anchor-diverse ordering, preventing one variant from hiding the other solely because their tokens overlap.
- Added `paragraph_134` to the paragraph benchmark and corrected the expected CUI list to use sumatriptan (`C0075632`) rather than an unrelated thiamine CUI.

## Result

Before the denial/order fixes on the corrected benchmark, `paragraph_134` was `mixed`: recall@10 was 6/9, recall@20 was 7/9, and `Migraine with Aura` was outside the top 10 despite a high score. After the phrase, denial, ordering, and NSAID wording fixes, the paragraph is `good`: recall@10 improved to 8/9, recall@20 improved to 9/9, recall@60 stayed 9/9, `Migraine with Aura` appears at rank 6, and `Anti-Inflammatory Agents, Non-Steroidal` appears at rank 4.

The remaining miss at top 10 is `dihydroergotamine`, which appears at rank 15. That is a drug enrichment/evidence issue, not the original aura phrase parsing bug.

## Verification

- `python3 -B -m pytest tests/test_evidence_vectors.py -k "with_or_without or direct_query_span_matches_with_or_without or phrase_is_not_denial_scope" -q`
- `python3 scripts/evaluate_paragraph_quality.py --queries /private/tmp/status_migrainosus_query_v2.tsv --output-dir build/improvements/2026-05-11_status_migrainosus_after_v4 --top-k 60`
