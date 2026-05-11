# Standalone Modifier Fragment Penalty

## Request

For `heart failure with reduced ejection fraction`, penalize very broad findings/symptoms results like `Reduced`.

## Change

- Added standalone modifier fragment detection for broad one-word or modifier-only concepts such as `Reduced`, `Decreased`, `Elevated`, `Low`, `High`, `Mild`, `Moderate`, and `Severe`.
- Limited the penalty to modifier-only labels in broad semantic types:
  - `Finding`
  - `Clinical Attribute`
  - `Qualitative Concept`
  - `Quantitative Concept`
- Only applies when the query has other specific anchors beyond the modifier. A query that is only `reduced` is not penalized for asking for the broad modifier itself.
- Reused the existing `semantic_fragment_penalty` score field so the UI explanation remains simple.
- Added a focused regression test for `heart failure with reduced ejection fraction`.

## Measured Effect

Query: `heart failure with reduced ejection fraction`

Before:

- `C0392756` `Reduced`
  - rank: 6
  - rank score: 1.300
  - semantic fragment penalty: 0.000
- Findings-like top results included `Reduced` as the second finding, ahead of more useful ejection-fraction concepts.

After:

- `C0392756` `Reduced`
  - rank: 35
  - rank score: 0.680
  - semantic fragment penalty: 0.620
- Specific concepts were not penalized:
  - `C3839346` `Heart failure with reduced ejection fraction` remained rank 1.
  - `C4022792` `Reduced left ventricular ejection fraction` remained the top finding-like result with no semantic fragment penalty.

After top finding-like results:

1. `C4022792` `Reduced left ventricular ejection fraction`
2. `C2700378` `Ejection fraction`
3. `C2020641` `stress echo measurements ejection fraction`
4. `C4022793` `Mildly reduced left ventricular ejection fraction`
5. `C4022790` `Severely reduced left ventricular ejection fraction`

## Broad Benchmark Check

Ran the 80-paragraph quality evaluator after the change:

- Verdicts: 79 good, 1 mixed
- Recall@5: 309/410 (75.4%)
- Recall@10: 406/410 (99.0%)
- Recall@20: 409/410 (99.8%)
- Expected semantic group recall@10: 100.0%
- Queries with all expected concepts@10: 76/80
- Queries with all expected concepts@20: 79/80

The benchmark did not show a broad failure mode, but it is not a pure before/after comparison because the current loaded index has 42,408 records while earlier saved benchmark runs used 41,530 records.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py -k standalone_modifier -q` passed.
- `python3 -m py_compile` passed with bytecode directed into the workspace cache.
- Restarted the local search server on port 8766 and confirmed the HFrEF API output reflects the new penalty.
- Ran `scripts/evaluate_paragraph_quality.py` and saved results to `build/improvements/2026-05-08_modifier_fragment_penalty_after/`.

## Result

This improves result quality for composite clinical phrases by pushing standalone modifier concepts below clinically meaningful concepts that include the modifier plus the actual disease, measurement, or finding context.
