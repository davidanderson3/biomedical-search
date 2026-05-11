# Generic status-noise suppression

## Why

Several clinical paragraph searches still showed non-useful prose/status CUIs in visible result slots, especially `Confirmation` (`C0750484`), `Confirmed by` (`C0521093`), `Response Declined` (`C1709925`), and `Evaluation` (`C0220825`). These are usually verbs or workflow/status words in a note, not useful returned clinical concepts.

## Change

- Added primary-label status-noise detection in `src/qe_evidence_vectors/search_ranking.py`, so the ranker checks the display/matched label instead of relying only on the full synonym token bag.
- Expanded generic prose/status tokens for `evaluation`, `evaluated`, `response`, and `declined`.
- Increased clinical-note penalties for generic prose/status concepts while preserving direct searches such as `not confirmed` and `response declined`.
- Added `is_generic_status_noise_result()` to suppress high-penalty prose/status concepts from normal clinical result windows.
- Added regression coverage in `tests/test_evidence_vectors.py`.

## Result

- Paragraph benchmark remained stable:
  - Recall@10: `410/410` before, `410/410` after.
  - Recall@20: `410/410` before, `410/410` after.
  - Paragraph verdicts: `80 good` before, `80 good` after.
  - Recall@5 improved slightly from `311/410` to `312/410`.
- Targeted noisy status CUIs in top-10 paragraph windows dropped from `10` before to `0` after.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py -k 'generic_prose_status or confirmation_status or primary_label_for_generic_status_noise or mortality_outcome' -q`
- `python3 scripts/evaluate_paragraph_quality.py --output-dir build/improvements/2026-05-08_after_generic_status_suppression --top-k 60`
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py`
