# Paragraph Noise Mitigation

## Evaluation

I evaluated the full paragraph test set with `scripts/evaluate_paragraph_quality.py` before and after the mitigation. The set contains 96 paragraph searches with 467 expected concepts. The baseline was already strong, but manual review of top-15 results showed recurring concepts that did not belong clinically:

- `C0168634` BaseLine dental cement for "baseline creatinine"
- `C0179686` Orthopedic Cast for urinary "granular casts"
- `C1875843` ultrasound device for ultrasound imaging mentions
- `C0023899` liver extract for liver anatomy/disease mentions
- `C3815497` Cough (guaifenesin) for cough as a symptom

## Change

Added contextual false-positive handling in `src/qe_evidence_vectors/search_ranking.py`. The new logic only suppresses these classes when the paragraph has richer clinical context indicating the intended sense. Direct searches such as "orthopedic cast", "ultrasound device", "liver extract", and "cough guaifenesin" still return the corresponding concepts.

Regression tests were added in `tests/test_evidence_vectors.py` for:

- baseline dental cement and orthopedic cast false positives in acute kidney injury notes
- ultrasound device and liver extract false positives in imaging/anatomy notes
- cough/guaifenesin false positives in influenza or symptom notes

## Result

Quality metrics were unchanged, so the mitigation did not harm expected-concept recall:

- Verdicts: 94 good, 2 mixed before; 94 good, 2 mixed after
- Recall@5: 363/467 (77.7%) before and after
- Recall@10: 463/467 (99.1%) before and after
- Recall@20: 466/467 (99.8%) before and after
- Recall@60: 467/467 (100.0%) before and after

The targeted false-positive count in the top 15 dropped from 11 to 0:

| CUI | Concept | Before top-15 count | After top-15 count |
| --- | --- | ---: | ---: |
| C0168634 | BaseLine dental cement | 1 | 0 |
| C0179686 | Orthopedic Cast | 1 | 0 |
| C1875843 | ultrasound device | 4 | 0 |
| C0023899 | liver extract | 3 | 0 |
| C3815497 | Cough (guaifenesin) | 2 | 0 |

Remaining known misses at rank 10 were unchanged: procalcitonin measurement, lactic acid measurement, acute kidney injury canonical CUI versus acute renal failure, and potassium. These are ranking/alternative-mapping issues, not the false-positive noise addressed here.

## Verification

- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m pytest tests/test_evidence_vectors.py -k "contextual_false_positive_anchor or contextual_device_and_extract or cough_medicine_homonym or low_value_admin_status"`
- `PYTHONPYCACHEPREFIX=.pycache_local python3 scripts/evaluate_paragraph_quality.py --output-dir build/improvements/2026-05-11_paragraph_noise_after --top-k 60`
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py`

Artifacts:

- Before: `build/improvements/2026-05-11_paragraph_noise_before/`
- After: `build/improvements/2026-05-11_paragraph_noise_after/`
