# Admin Review False Positive Guard

## Problem

Clinical and literature paragraphs often use ordinary prose such as `reviewed` or `review article`. The ranker already handled some single-token prose status concepts, but `Peer Review`, `Reviewed By`, `Not reviewed`, and chart/drug-utilization review concepts could still surface because they carried extra administrative tokens like `peer`, `chart`, or `utilization`.

The tests were too lenient because reviewed paragraphs only asserted expected clinical CUIs. They did not fail when a high-ranking administrative review artifact appeared beside the real clinical results.

## Change

- Added `review`, `reviewed`, and `reviews` to low-specificity query tokens so those words no longer act as strong anchors in clinical prose.
- Added an admin-review artifact detector for concepts such as `Peer Review`, `Reviewed By`, `Not reviewed`, `Medical Chart Review`, and `Drug Utilization Review`.
- Preserved direct searches such as `peer review` and `chart review` so the concepts remain retrievable when the user explicitly asks for them.
- Added disallowed review-artifact CUIs to reviewed clinical paragraphs and added a new review-article paragraph to test a realistic publication-style query.

## Results

Targeted reviewed/review paragraph evaluation:

- Paragraphs: 8
- Expected concepts: 44
- Recall@10: 44/44 (100.0%)
- Recall@20: 44/44 (100.0%)
- Known false positives@10: 0/8
- Known false positives@20: 0/8
- Verdicts: 8 good

Full paragraph evaluation:

- Paragraphs: 142
- Expected concepts: 711
- Recall@10: 708/711 (99.6%)
- Recall@20: 711/711 (100.0%)
- Known false positives@10: 0/142
- Known false positives@20: 0/142
- Verdicts: 141 good, 1 mixed

The remaining mixed paragraph is unchanged in nature: paragraph_130 has `Blood culture` at rank 11 while all expected concepts are present by rank 20.

## Verification

```bash
python3 -B -m pytest tests/test_evidence_vectors.py -k "admin_review or confirmation_status or generic_prose_status or low_value_admin_status or reads_query_tsv or false_positives" -q
PYTHONPYCACHEPREFIX=/private/tmp/query-expansion-pycache python3 -m py_compile src/qe_evidence_vectors/search_ranking.py scripts/evaluate_paragraph_quality.py scripts/evaluate_search_api.py
python3 scripts/evaluate_paragraph_quality.py --queries /private/tmp/review_paragraphs.tsv --output-dir build/improvements/2026-05-12_admin_review_false_positive_after --top-k 60 --candidate-pool-multiplier 3 --candidate-pool-min 50
python3 scripts/evaluate_paragraph_quality.py --output-dir build/improvements/2026-05-12_admin_review_false_positive_full_after --top-k 60 --candidate-pool-multiplier 3 --candidate-pool-min 50
```
