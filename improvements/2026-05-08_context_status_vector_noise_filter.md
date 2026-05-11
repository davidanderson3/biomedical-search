# Context Status and Vector Noise Filter

## Problem

After direct-anchor coverage was fixed, expected concept recall was saturated, but some top-10 result slots were still spent on generic context/status concepts. The migraine paragraph showed `Negative`, `Recurrent Condition`, `Negative predictive value`, and `Incidence Proportion` even though the paragraph used those words as context around migraine, CT, and treatment rather than asking for status or epidemiology concepts.

## Change

- Added a context-sensitive visibility filter in `src/qe_evidence_vectors/search_ranking.py`.
- Filtered generic status/statistical concepts only when the query has additional biomedical anchors beyond the candidate's own primary labels.
- Included direct-search safeguards so queries like `negative`, `recurrent condition`, `negative predictive value`, and `attack rate` still return those concepts.
- Extended regression tests for generic status, confirmation status, low-value administrative status, mortality outcome, and vector-sourced status/statistical noise.

## Results

Baseline for this pass was `build/improvements/2026-05-08_after_direct_anchor_coverage`: 96 paragraphs, 467 expected concepts, recall@5 `367/467` (`0.7859`), recall@10 `467/467` (`1.0000`), recall@20 `467/467`, verdicts `96 good`.

Final benchmark is `build/improvements/2026-05-08_after_context_status_vector_noise_filter`: 96 paragraphs, 467 expected concepts, recall@5 `367/467` (`0.7859`), recall@10 `467/467` (`1.0000`), recall@20 `467/467`, verdicts `96 good`.

The safety metrics stayed unchanged. The visible result list improved for the migraine paragraph: `Negative`, `Recurrent Condition`, `Negative predictive value`, and `Incidence Proportion` no longer occupy top-10 slots, and the expected `Photophobia` concept moved from rank 10 to rank 8.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py -k 'low_value_context_status or mortality_outcome or low_value_admin_status or generic_prose_status or confirmation_status' -q`
- `python3 scripts/evaluate_paragraph_quality.py --output-dir build/improvements/2026-05-08_after_context_status_vector_noise_filter --top-k 60`
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py`
