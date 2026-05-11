# Right Heart Catheterization Final Benchmark

## Change

Added `right heart catheterization` as a curated active-label supplement for existing CUI `C0189896`.

This is a specific diagnostic procedure that was explicitly present in the pulmonary hypertension paragraph but ranked just outside the top-10 result window behind the broader `Cardiac Catheterization Procedures` CUI.

## Improvement

Before this change, the full paragraph benchmark had one remaining mixed paragraph:

- `paragraph_72`: missing `C0189896` Right heart catheterization at top 10.
- Full benchmark before: Recall@10 `409/410`, all expected concepts@10 `79/80`, verdicts `79 good / 1 mixed`.

Focused evaluation after adding the active anchor:

- `paragraph_72`: Recall@10 `5/5`, verdict `good`.

Full benchmark after the change:

- Paragraphs: 80.
- Expected concepts: 410.
- Recall@5: `311/410` (75.9%).
- Recall@10: `410/410` (100.0%).
- Recall@20: `410/410` (100.0%).
- Expected semantic group recall@10: `100.0%`.
- Queries with all expected concepts@10: `80/80`.
- Verdicts: `80 good`.

## Verification

Commands run:

```sh
python3 scripts/validate_active_label_supplement.py
python3 -m pytest tests/test_evidence_vectors.py -k 'right_heart_catheterization or active_label_supplement' -q
python3 scripts/evaluate_paragraph_quality.py --queries /tmp/paragraph_72_query.tsv --output-dir build/improvements/2026-05-08_right_heart_catheterization_eval --top-k 60
python3 scripts/evaluate_paragraph_quality.py --output-dir build/improvements/2026-05-08_full_after_right_heart_catheterization --top-k 60
PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/active_label_supplement.py src/qe_evidence_vectors/search_ranking.py scripts/validate_active_label_supplement.py
```

Results:

- Active-label validation passed.
- Unit tests: `9 passed, 175 deselected`.
- Focused paragraph 72 evaluation: Recall@10 `100.0%`, verdict `good`.
- Full benchmark: Recall@10 `100.0%`, all expected concepts@10 `80/80`, verdicts `80 good`.

## Remaining Limits

This benchmark is still curated and finite. The result is strong for the current paragraph set, but future improvements should focus on broader examples, external validation, and preventing precision regressions rather than only maximizing this benchmark.
