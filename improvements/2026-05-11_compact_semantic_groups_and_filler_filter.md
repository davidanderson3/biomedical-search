# Compact Semantic Groups and Filler Filter

## Problem

The semantic group cards still took more vertical space than needed, and several top-10 result lists contained low-value filler concepts. Examples included `Discharge summary`, `Living Alone`, `High`, `patient symptoms`, and unrelated `COVID-19 Testing` in richer clinical paragraphs.

## Change

- Reduced the semantic group result scroller height in `docs/search_quality/server.css` from `min(360px, 42vh)` to `min(260px, 34vh)`.
- Expanded low-value administrative/status labels in `src/qe_evidence_vectors/search_ranking.py`.
- Scoped admin/status filtering through the same context-beyond-primary-label guard used elsewhere, preserving direct searches such as `discharge summary`.
- Expanded low-value procedure fragment tokens so unrelated testing/procedure concepts are less likely to occupy visible slots when the query is not directly asking for that concept.
- Added regression coverage for the new filler cases and direct-search safeguards.

## Results

Baseline for this pass was `build/improvements/2026-05-08_after_low_value_procedure_fragment_filter`: 96 paragraphs, 467 expected concepts, recall@5 `367/467` (`0.7859`), recall@10 `467/467` (`1.0000`), recall@20 `467/467`, verdicts `96 good`.

Final benchmark is `build/improvements/2026-05-11_after_compact_groups_and_filler_filter`: 96 paragraphs, 467 expected concepts, recall@5 `367/467` (`0.7859`), recall@10 `467/467` (`1.0000`), recall@20 `467/467`, verdicts `96 good`.

The safety metrics stayed unchanged. Visible results improved in several rows: `Discharge summary`, `Living Alone`, `High`, `patient symptoms`, and unrelated `COVID-19 Testing` were removed from the checked top-10 examples. Some weak replacement concepts remain, which is a sign that the current recall-only benchmark is saturated and needs graded precision/noise judgments for further sustainable improvement.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py -k 'low_value_procedure_fragments or low_value_admin_status or low_value_context_status or procedure_siblings' -q`
- `python3 scripts/evaluate_paragraph_quality.py --output-dir build/improvements/2026-05-11_after_compact_groups_and_filler_filter --top-k 60`
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py`
