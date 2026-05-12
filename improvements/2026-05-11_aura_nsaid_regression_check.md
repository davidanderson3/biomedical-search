# Aura and NSAID Regression Check

## Question

Checked whether the `migraine with or without aura` phrase handling and the `nonsteroidal anti-inflammatories` active label affected other paragraph search results.

## Result

The full paragraph benchmark now has 134 paragraphs and 671 expected concepts. It produced 133 `good` and 1 `mixed` verdict, with recall@10 of 99.70%, recall@20 of 100%, and recall@60 of 100%.

Compared with the latest 133-paragraph benchmark artifact, the 133 shared paragraph IDs had no verdict regressions. One shared paragraph improved: `paragraph_120` changed from `mixed` to `good` because family-history concepts now outrank active cancer concepts. Three rows had small rank-window changes but stayed `good`: `paragraph_34` and `paragraph_102` lost one expected item from the top 5 only, while still preserving all expected concepts by top 10; `paragraph_112` and `paragraph_121` changed top concept to a more central disease concept while preserving expected coverage.

The new `paragraph_134` is `good`: 8/9 expected concepts appear by top 10 and 9/9 by top 20. The remaining top-10 miss is `dihydroergotamine`, which appears at rank 15.

## Verification

- `python3 -B -m pytest tests/test_evidence_vectors.py -k "with_or_without or direct_query_span_matches_with_or_without or phrase_is_not_denial_scope or active_label_supplement" -q`
- `python3 scripts/evaluate_paragraph_quality.py --output-dir build/improvements/2026-05-11_aura_nsaid_regression_check --top-k 60`
