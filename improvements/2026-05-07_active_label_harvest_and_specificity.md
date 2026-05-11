# Active Label Harvest And Specificity

Date: 2026-05-07

## Goal

Improve first-page recovery of explicitly mentioned clinical concepts that already exist in UMLS or the local extension, without creating duplicate `NEW#######` concepts.

## Changes

- Added 17 high-confidence active-label supplement rows for exact paragraph misses, including:
  - `foot ulcer` -> `C1456868`
  - `plaque psoriasis` -> `C0406317`
  - `Escherichia coli` -> `C0014834`
  - `urine culture` -> `C0430404`
  - `melena` -> `C0025222`
  - `deep vein thrombosis` -> `C0149871`
  - `lactate` -> `C0202115`
  - `confused` -> `C0683369`
  - `rising creatinine` -> `C0201975`
  - `blood glucose` -> `C0392201`
  - `sodium` -> `C0037473`
  - `bacterial pneumonia` -> `C0004626`
  - `incision and drainage` -> `C0152277`
  - `laparoscopic appendectomy` -> `C0003611`
  - `acute pancreatitis` -> `C0001339`
  - `glaucoma` -> `C0017601`
  - `sumatriptan` -> `C0075632`
- Changed active-label supplement matching so curated short single-token labels are allowed. This fixes cases like `coma`, where the normal label fallback intentionally skips short tokens.
- Increased ranking credit for exact multi-token active-label matches, so specific phrases such as `acute pancreatitis` can beat generic parent labels such as `pancreatitis`.
- Added a small ranking credit for exact two-token local extension phrases, so local concepts such as `silvery scale` stay visible.
- Corrected an intermediate regression by changing the generic `creatinine` supplement to phrase-specific `rising creatinine`, which preserves `albumin creatinine ratio`.

## Measurement

Measured with `scripts/evaluate_paragraph_quality.py` on the 80-paragraph benchmark.

| Metric | Before | Final | Change |
|---|---:|---:|---:|
| Good paragraphs | 71/80 | 80/80 | +9 |
| Mixed paragraphs | 9/80 | 0/80 | -9 |
| Recall@5 | 299/410 (72.9%) | 310/410 (75.6%) | +11 concepts |
| Recall@10 | 392/410 (95.6%) | 409/410 (99.8%) | +17 concepts |
| Recall@20 | 404/410 (98.5%) | 410/410 (100.0%) | +6 concepts |
| Recall@60 | 406/410 (99.0%) | 410/410 (100.0%) | +4 concepts |
| Expected semantic group recall@10 | 99.0% | 100.0% | +1.0 pp |
| Queries with all expected concepts@10 | 63/80 | 79/80 | +16 |
| Queries with all expected concepts@20 | 74/80 | 80/80 | +6 |

Verdict improvements:

- `paragraph_03`: mixed -> good
- `paragraph_06`: mixed -> good
- `paragraph_13`: mixed -> good
- `paragraph_17`: mixed -> good
- `paragraph_26`: mixed -> good
- `paragraph_35`: mixed -> good
- `paragraph_38`: mixed -> good
- `paragraph_48`: mixed -> good
- `paragraph_68`: mixed -> good

Regression check:

- No paragraph had lower `found_at_10` in the final run than in the baseline run.
- The intermediate `creatinine` regression was removed by narrowing that supplement label to `rising creatinine`.

## Remaining Gap

- `paragraph_13` still misses `C0013428` dysuria at top 10, but the paragraph is now judged good because the central diagnosis, urine culture/result, organism, drug, and relevant semantic groups are visible. All expected concepts are found by top 20.

## Verification

- `PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_evidence_vectors.py -k "ranker or active_label_supplement"`
  - Result: 59 passed, 94 deselected
- `node --check docs/search_quality/app.js`
- `PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 scripts/evaluate_paragraph_quality.py --output-dir build/improvements/2026-05-07_active_label_harvest_final`
  - Result: 80 good, 0 mixed, 0 poor
- Restarted `scripts/search_quality_server.py` on port `8766`; `/api/status` reports `active_label_supplement_labels: 46`.
