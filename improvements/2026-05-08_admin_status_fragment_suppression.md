# Administrative/status fragment suppression

## Why

After generic status concepts were suppressed, the next visible precision problem was administrative or result-fragment CUIs occupying top-10 slots in clinical searches. Examples included `Positive` (`C1446409`), `Dosage` (`C0178602`), `Patient Discharge` (`C0030685`), `Scheduled - procedure status` (`C0205539`), and `Developed Countries` (`C0282613`). These are usually note wording or status fragments, not useful returned CUIs.

## Change

- Added `is_low_value_admin_status_result()` in `src/qe_evidence_vectors/search_ranking.py`.
- Suppressed a small reusable set of low-value administrative/status display labels from clinical result windows when the query has real biomedical context.
- Treated `Positive` as suppressible when it appears with lab/test context, including biopsy/testing terms.
- Preserved direct searches such as `positive`.
- Added regression coverage in `tests/test_evidence_vectors.py`.

## Result

- Targeted admin/status fragments in top-10 paragraph windows dropped from `13` to `0`.
- Paragraph benchmark remained stable:
  - Recall@10: `410/410` before, `410/410` after.
  - Recall@20: `410/410` before, `410/410` after.
  - Paragraph verdicts: `80 good` before, `80 good` after.
  - Recall@5 stayed `312/410`.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py -k 'generic_prose_status or confirmation_status or primary_label_for_generic_status_noise or low_value_admin_status_fragments or mortality_outcome' -q`
- `python3 scripts/evaluate_paragraph_quality.py --output-dir build/improvements/2026-05-08_after_admin_status_fragment_suppression --top-k 60`
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py`
