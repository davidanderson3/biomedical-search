# Ranker Primary Label Refactor

## Change

Refactored repeated primary-label extraction in `search_ranking.py`. Several context filters were independently rebuilding the same list of candidate labels from:

- matched label
- preferred/name label
- first source labels

Those paths now use the shared `hit_primary_label_token_sets(...)` helper with options for whether to include the matched label and how many source labels to inspect.

Updated callers include:

- broad organism context detection
- broad infection/disease context detection
- yes/no answer filtering
- broad symptom aggregate filtering
- broad therapy/drug-class component filtering

## Why This Helps

This reduces duplicated tokenization logic in the ranker and makes future context filters less error-prone. The behavior remains the same, but new filters can reuse a single well-tested label-token path instead of rebuilding slightly different versions.

## Measured Impact

The refactor preserved search quality:

- `paragraphs`: 116
- `expected_concepts`: 570
- `recall_at_10`: 100.0%
- `recall_at_20`: 100.0%
- `queries_all_expected_at_10`: 116/116
- `verdict_counts`: 116 good
- calibrated suspect top-10 hits: 0

## Verification

- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py`
- `python3 -m pytest tests/test_evidence_vectors.py -k "systemic_symptoms or gestational_context or broad_drug_classes or bacteria or yes_no_answer or confirmation_status or infection_context"`
- `python3 scripts/evaluate_paragraph_quality.py --output-dir build/improvements/2026-05-11_ranker_primary_label_refactor_after --top-k 60`
- `python3 scripts/audit_paragraph_precision.py --payloads build/improvements/2026-05-11_ranker_primary_label_refactor_after/paragraph_search_payloads.jsonl --output-dir build/improvements/2026-05-11_ranker_primary_label_refactor_after --top-n 10`
