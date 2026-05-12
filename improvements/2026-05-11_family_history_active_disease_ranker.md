# Family History vs Active Disease Ranker

## Goal

Improve family-history searches so active cancer concepts do not outrank family-history concepts when the query explicitly says `family history`.

## What changed

- Added a `family_history_context_penalty` to the ranker.
- The penalty applies only when:
  - the query contains both `family` and `history`;
  - the candidate is an active condition/neoplasm concept;
  - the candidate shares the target disease tokens from the query; and
  - the candidate label is not itself a family-history/risk/susceptibility concept.
- Active neoplasm concepts receive a stronger penalty because cancer family-history searches commonly retrieve active breast/ovarian cancer concepts through exact disease-name matches and definition text.
- Added the new penalty to the web UI match-reason labels and evaluator score summary.

## Measured impact

Targeted paragraph evaluation on `paragraph_120`:

- Query: `family history of breast cancer and family history of ovarian cancer`
- Verdict: `good`
- Recall@10: `7/7`
- Expected semantic-group recall@10: `100%`
- Top result changed to `C0490017 | Family history of malignant neoplasm of ovary`.
- `C0559119 | Family history of breast cancer` is now rank 3.
- Active breast/ovarian cancer concepts no longer appear in the top 10 for this targeted local evaluation.

## Verification

- Python AST syntax check passed for `src/qe_evidence_vectors/search_ranking.py` and `scripts/evaluate_search_api.py`.
- `node --check docs/search_quality/app.js` passed.
- Synthetic ranker check confirmed `Family history of breast cancer` outranks active `Malignant neoplasm of breast` when the query is `family history of breast cancer`.
- Targeted evaluator output written to `build/improvements/2026-05-11_family_history_ranker_eval/`.

## Remaining Risk

This is intentionally narrow. It should not penalize active cancer concepts when the user searches for active disease, cancer treatment, staging, diagnosis, or screening without explicit family-history wording.
