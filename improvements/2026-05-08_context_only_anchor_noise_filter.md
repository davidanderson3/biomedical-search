# Context-Only Anchor Noise Filter

## Problem

The previous status filter removed direct generic labels such as `Negative` and `Recurrent Condition`, but vector and label-enriched results could still enter the top 10 when they matched only context words. Examples included `Absence of necrosis` from the word `negative`, `Recurrent tonsillitis` from `recurrent`, and `Positive Finding` from positive test wording. These results are technically lexical matches, but they do not represent the clinical concepts in the paragraph.

## Change

- Added a context-only anchor filter in `src/qe_evidence_vectors/search_ranking.py`.
- The filter suppresses results whose only useful query overlap is generic context/status wording such as `positive`, `negative`, `absence`, `recurrent`, `attack`, `incidence`, or `treatment`.
- Preserved explicitly negated clinical findings with a real negation signal, such as `pain absent`, so denial-context concepts are not incorrectly removed.
- Kept direct-query safeguards for `negative`, `recurrent condition`, `negative predictive value`, `attack rate`, `absence of necrosis`, and `recurrent tonsillitis`.

## Results

Baseline for this pass was `build/improvements/2026-05-08_after_context_status_vector_noise_filter`: 96 paragraphs, 467 expected concepts, recall@5 `367/467` (`0.7859`), recall@10 `467/467` (`1.0000`), recall@20 `467/467`, verdicts `96 good`.

Final benchmark is `build/improvements/2026-05-08_after_context_only_anchor_noise_filter`: 96 paragraphs, 467 expected concepts, recall@5 `367/467` (`0.7859`), recall@10 `467/467` (`1.0000`), recall@20 `467/467`, verdicts `96 good`.

The safety metrics stayed unchanged. Visible results improved in several rows: `Positive Finding` was removed from osteomyelitis, influenza, and STI examples; `Absence of necrosis` and `Recurrent tonsillitis` were removed from the migraine example. The remaining bottom-of-top-10 filler is now mostly procedure/anatomy fragments, which is a better next target than status/negation disease noise.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py -k 'low_value_context_status or mortality_outcome or low_value_admin_status or generic_prose_status or confirmation_status' -q`
- `python3 scripts/evaluate_paragraph_quality.py --output-dir build/improvements/2026-05-08_after_context_only_anchor_noise_filter --top-k 60`
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py`
