# PubMed Antibiotic-Associated Diarrhea Acceptable Alternative

## Problem

The focused PubMed long-document lane still listed `C0011991` Diarrhea as a
top-10 miss for the C. difficile review abstract. The first page already
contained `C0578159` Antibiotic-associated diarrhea at rank 8, and the abstract
explicitly links diarrhea to antibiotic exposure and C. difficile infection.

Baseline run:

- Query file: `build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_queries.tsv`
- Output directory: `build/search_quality_experiments/runs/SQI-2026-06-11-006_pubmed_current_baseline_sqi-2026-06-11-006-pubmed-focused-current-baseline`
- Result: 32/36 expected concepts at top 10, 35/36 at top 20, 36/36 at top 60,
  4 good / 3 mixed rows, 5/7 strict success at top 20, and 0 known false
  positives at top 10 and top 20.

## Hypothesis

This is a benchmark hierarchy issue, not a runtime ranking failure. For
antibiotic/C. difficile wording, the specific `Antibiotic-associated diarrhea`
concept is clinically acceptable evidence for the broader `Diarrhea` symptom
target. Adding that reviewed acceptable alternative should move the focused
top-10 count from 32/36 to 33/36 without changing runtime ranking.

## Change

- Added `C0011991 -> C0578159` to
  `config/search_quality_acceptable_cui_alternatives.tsv`.
- Added a focused evaluator regression test proving that a first-page
  `Antibiotic-associated diarrhea` hit can satisfy the broader `Diarrhea`
  target while still counting as its own expected concept.
- Regenerated `docs/search_rule_inventory.html`.

## Result

Focused live rerun:

- Query file: `build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_queries.tsv`
- Output directory: `build/search_quality_experiments/runs/SQI-2026-06-11-006_pubmed_antibiotic_diarrhea_alternative_sqi-2026-06-11-006-pubmed-antibiotic-diarrhea-acceptable-alterna`
- Server profile: `PORT=8766 PUBLIC_OUTPUT_ONLY=0 sh scripts/start_search_quality_server.sh`
- Command:

```sh
python3 scripts/run_search_quality_experiment.py --base-url http://127.0.0.1:8766 --scope umls_evidence --run-family probe --label 'SQI-2026-06-11-006 PubMed antibiotic diarrhea acceptable alternative' --run-id SQI-2026-06-11-006_pubmed_antibiotic_diarrhea_alternative --queries build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_queries.tsv --query-limit 0 --search-system api --top-k 60 --timeout 120 --output-root build/search_quality_experiments --html-report docs/search_quality_experiments.html --require-api-backend elasticsearch
```

Measured movement:

- Expected concepts at top 10: 32/36 -> 33/36.
- Expected concepts at top 20: 35/36 -> 35/36.
- Expected concepts at top 60: 36/36 -> 36/36.
- Queries with all expected concepts at top 10: 4/7 -> 5/7.
- Strict success at top 10: 3/7 -> 4/7.
- Good / mixed rows: 4 good / 3 mixed -> 4 good / 3 mixed.
- Known false positives at top 10 and top 20: 0 -> 0.
- Accepted alternatives at top 10 now include
  `pubmed_cdiff_antibiotic_diarrhea_30945014: C0011991=C0578159`.
- Remaining focused top-10 misses: `C0154723`, `C0338480`, and `C0009506`.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py::test_paragraph_evaluator_counts_acceptable_cui_alternatives tests/test_evidence_vectors.py::test_paragraph_evaluator_counts_configured_osimertinib_dose_form_alternative tests/test_evidence_vectors.py::test_paragraph_evaluator_counts_configured_antibiotic_diarrhea_alternative -q`
- `python3 -m py_compile scripts/run_search_quality_experiment.py scripts/evaluate_paragraph_quality.py`
- `python3 scripts/build_search_rule_inventory.py`
- `python3 scripts/run_search_quality_experiment.py --iteration-smoke-gates --iteration-id SQI-2026-06-11-006 --iteration-type benchmark --force-patient-portal-smoke --static-command "python3 -m py_compile scripts/run_search_quality_experiment.py scripts/evaluate_paragraph_quality.py" --focused-command "python3 -m pytest tests/test_evidence_vectors.py::test_paragraph_evaluator_counts_acceptable_cui_alternatives tests/test_evidence_vectors.py::test_paragraph_evaluator_counts_configured_osimertinib_dose_form_alternative tests/test_evidence_vectors.py::test_paragraph_evaluator_counts_configured_antibiotic_diarrhea_alternative -q" --base-url http://127.0.0.1:8766`

The iteration smoke helper passed static, focused, standing clinical, rotating
50-query, and patient-portal gates. The rotating 50-query smoke produced 42/50
strict success at top 10, 47/50 at top 20, 47/50 top-on-target, and 3 top-wrong.
The patient-portal lane stayed at 12/12 top-on-target and 0 top-wrong.

## Decision

Keep. This is a reviewed benchmark-definition correction for a specific-to-broad
clinical hierarchy, and it removes the C. diff row from the focused PubMed
top-10 miss list without adding a ranker rule.
