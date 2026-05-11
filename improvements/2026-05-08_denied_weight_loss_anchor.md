# Denied Weight Loss Anchor

## Change
- Added a narrow denial-anchor exception for the span `weight loss`.
- `label_fallback_anchor_queries()` now generates `no weight loss` and `weight loss absent` from denial contexts such as `denies ... recent unintentional weight loss`.
- Kept the exception scoped to denial-anchor generation, so positive broad matching for `weight loss` is not expanded globally.
- Added a regression test for the denied weight-loss anchor.

## Why It Helps
- The label index already contained `C4528142` / `No Weight Loss`, but it was not retrieved because the span `weight loss` was suppressed as too broad.
- In a denial sentence, `weight loss` is clinically meaningful and should generate a negated-label lookup.

## Measured Effect
Query: `Denies nausea vomiting fever chills or recent unintentional weight loss`

Before:
- `C4528142` / `No Weight Loss` was not returned in the top 10.
- Positive concepts still appeared:
  - `C2363736` / `Unintentional weight loss`
  - `C1262477` / `Weight Loss`

After:
- `C4528142` / `No Weight Loss` is rank 2.
- Matched span: `no weight loss`.
- Positive weight-loss concepts remain penalized by denial logic:
  - `Unintentional weight loss`: denial penalty `0.52`
  - `Weight Loss`: denial penalty `0.52`

Small clinical benchmark:
- Before: 3 expected CUIs missing from top 10.
- After: 2 expected CUIs missing from top 10.
- The fixed query moved from missing to expected rank 2.

## Broad Check
Ran the 80-paragraph quality evaluator after the change:

- Verdicts: 79 good, 1 mixed.
- Recall@5: 308/410 (75.1%).
- Recall@10: 406/410 (99.0%).
- Recall@20: 409/410 (99.8%).
- Expected semantic group recall@10: 100.0%.
- Queries with all expected concepts@10: 76/80.
- Queries with all expected concepts@20: 79/80.

The broader result set stayed stable. Recall@5 is one expected concept lower than the prior modifier-fragment report, but top-10/top-20 recall and verdict counts stayed the same.

## Verification
- `python3 -m pytest tests/test_evidence_vectors.py -k "denial_context or negated_denial_spans or denied_weight_loss" -q` passed.
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile ...` passed for the changed ranking modules.
- Restarted `http://127.0.0.1:8766/`.
- Saved paragraph evaluator outputs under `build/improvements/2026-05-08_denied_weight_loss_anchor_after/`.
