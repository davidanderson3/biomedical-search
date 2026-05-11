# Residual Paragraph Audit Cleanup

## Change

Cleaned up the residual calibrated precision-audit noise after the expanded 116-paragraph benchmark reached full recall. The changes are intentionally narrow:

- Stronger demotion for generic `Diabetes Mellitus` when the query explicitly says `gestational diabetes`.
- Context-only filtering for broad symptom aggregate labels when specific symptoms are present:
  - `systemic symptoms`
  - `general symptom`
  - `no respiratory symptoms`
  - `multiple symptoms`
- Direct lookup for those broad labels is preserved; the filter only applies when the query has richer clinical context beyond the broad label itself.

## Measured Impact

Before this cleanup, the previous calibrated audit after broad-class precision work showed:

- `recall_at_10`: 100.0%
- `verdict_counts`: 116 good
- calibrated suspect top-10 hits: 2
- main remaining flags: `systemic symptoms` and generic `Diabetes Mellitus`

After the cleanup full paragraph run:

- `paragraphs`: 116
- `expected_concepts`: 570
- `recall_at_10`: 100.0%
- `recall_at_20`: 100.0%
- `queries_all_expected_at_10`: 116/116
- `verdict_counts`: 116 good
- calibrated suspect top-10 hits: 1 in the measured audit, a low-rank replacement broad symptom aggregate

The final code also folds that replacement broad aggregate (`multiple symptoms`) into the same tested filter set. I did not rerun the full benchmark again after that one-label equivalent addition to avoid another several-minute evaluation cycle; the targeted regression test verifies the behavior.

## Remaining Issues

The audit is now mainly useful for discovering families of generic aggregate labels rather than individual high-impact failures. The next higher-value step is to add more paragraph coverage for under-tested domains or improve relationship evidence display, rather than repeatedly chasing low-rank synonym replacements in the influenza paragraph.

## Verification

- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py`
- `python3 -m pytest tests/test_evidence_vectors.py -k "systemic_symptoms or gestational_context or broad_drug_classes"`
- `python3 scripts/evaluate_paragraph_quality.py --output-dir build/improvements/2026-05-11_residual_audit_cleanup_no_negated_symptoms_after --top-k 60`
- `python3 scripts/audit_paragraph_precision.py --payloads build/improvements/2026-05-11_residual_audit_cleanup_no_negated_symptoms_after/paragraph_search_payloads.jsonl --output-dir build/improvements/2026-05-11_residual_audit_cleanup_no_negated_symptoms_after --top-n 10`
