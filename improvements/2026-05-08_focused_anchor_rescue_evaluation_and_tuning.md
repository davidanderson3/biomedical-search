# Focused Anchor Rescue Evaluation And Tuning

## Change

Reran a focused paragraph evaluation for the four paragraphs that had recent or stored top-10 misses:

- `paragraph_13`: dysuria in pyelonephritis.
- `paragraph_19`: norepinephrine in septic shock.
- `paragraph_37`: seizure/tremor in alcohol withdrawal.
- `paragraph_55`: memory loss in Alzheimer disease.

Then made two narrow improvements:

- Added `Seizure` -> `C0036572` as a context-gated active label supplement.
- Demoted generic `Emergency/Emergencies [Disease/Finding]` when the query uses emergency only as a care setting, such as `Emergency department`.
- Increased the curated exact single-token active-label component from `0.18` to `0.30`, so high-confidence explicit anchors like Dysuria are less likely to fall just outside the top-10 window.

## Improvement

Focused evaluation before the final tuning:

- Paragraphs: 4.
- Recall@10: 21/23 (91.3%).
- Recall@20: 22/23 (95.7%).
- Verdicts: 3 good, 1 mixed.
- Remaining mixed paragraph: alcohol withdrawal, missing `C0036572` Seizure at top 10.

Focused evaluation after tuning:

- Paragraphs: 4.
- Recall@10: 23/23 (100.0%).
- Recall@20: 23/23 (100.0%).
- Queries with all expected concepts@10: 4/4.
- Verdicts: 4 good.

This confirms the recent active-anchor work improved the specific misses it targeted, and the final tuning moved Dysuria from just outside the top-10 window into top 10 without changing the broader retrieval mechanism.

## Verification

Commands run:

```sh
python3 -m pytest tests/test_evidence_vectors.py -k 'explicit_single_token_symptom_and_drug_anchors or emergency_setting_concept or active_label_supplement' -q
python3 scripts/evaluate_paragraph_quality.py --queries /tmp/focused_paragraph_queries.tsv --output-dir build/improvements/2026-05-08_focused_anchor_rescue_eval_final --top-k 60
PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py src/qe_evidence_vectors/search_rerank.py src/qe_evidence_vectors/search_service.py
```

Results:

- Unit tests: `8 passed, 173 deselected`.
- Focused evaluation: Recall@10 `100.0%`, all expected concepts@10 `4/4`, verdicts `4 good`.

## Remaining Limits

This is not a full 80-paragraph benchmark run. The focused set validates the known misses, but the full evaluation should still be rerun periodically to detect regressions outside these four paragraphs.
