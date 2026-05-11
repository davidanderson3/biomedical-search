# Low-Value Procedure Fragment Filter

## Problem

After status and context-only disease noise were reduced, the remaining top-10 filler often came from generic procedure fragments. Examples included standalone `tomography`, `Computed (procedure)`, and broad preventive pharmacotherapy concepts. These matched query words but did not add useful concept coverage when a more specific procedure or clinical concept was already present.

## Change

- Added a low-value procedure fragment filter in `src/qe_evidence_vectors/search_ranking.py`.
- Suppressed procedure/test results whose only direct overlap is low-information procedure wording such as `computed`, `tomography`, `testing`, `treatment`, `pharmacotherapy`, or `prescribed`.
- Added a fallback for low-signal semantic-vector procedure hits with no exact span and only weak lexical support.
- Kept explicit procedure-query safeguards so searches like `appendectomy surgical procedure` still retain related procedure candidates, and exact specific procedures like `computed tomography angiography` remain available.

## Results

Baseline for this pass was `build/improvements/2026-05-08_after_context_only_anchor_noise_filter`: 96 paragraphs, 467 expected concepts, recall@5 `367/467` (`0.7859`), recall@10 `467/467` (`1.0000`), recall@20 `467/467`, verdicts `96 good`.

Final benchmark is `build/improvements/2026-05-08_after_low_value_procedure_fragment_filter`: 96 paragraphs, 467 expected concepts, recall@5 `367/467` (`0.7859`), recall@10 `467/467` (`1.0000`), recall@20 `467/467`, verdicts `96 good`.

The safety metrics stayed unchanged. Visible results improved in the migraine and influenza examples: standalone `tomography`, `Computed (procedure)`, and preventive pharmacotherapy no longer occupy top-10 slots. Some more specific CT variants remain near the bottom, which is preferable to single-token procedure fragments and should be handled separately if needed.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py -k 'low_value_procedure_fragments or low_value_context_status or self_synonym_fragments or procedure_siblings' -q`
- `python3 scripts/evaluate_paragraph_quality.py --output-dir build/improvements/2026-05-08_after_low_value_procedure_fragment_filter --top-k 60`
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py`
