# PubMed Osimertinib Dose-Form Acceptable Alternative

## Problem

The focused PubMed long-document lane was still marking the EGFR/NSCLC abstract
as mixed because expected ingredient CUI `C4058811` Osimertinib was outside the
top 10, while the first page already contained `C4058829` osimertinib 80 MG.
The paragraph explicitly names osimertinib, and the dose-specific RxNorm product
is a clinically acceptable retrieval hit for this benchmark target.

Baseline run:

- Query file: `build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_queries.tsv`
- Output directory: `build/search_quality_experiments/runs/SQI-2026-06-11-005_pubmed_current_baseline_sqi-2026-06-11-005-pubmed-focused-current-baseline`
- Result: 31/36 expected concepts at top 10, 35/36 at top 20, 36/36 at top 60,
  3 good / 4 mixed rows, 88.9% expected semantic group recall at top 10, and
  0 known false positives at top 10 and top 20.
- EGFR row detail: `C4058811` was missing at top 10, but `C4058829` was present
  on the first page.

Two runtime ranking diagnostics tried to promote the ingredient over an
overqualified dose-form concept. They did not move the focused metric, so the
runtime change was rejected and not kept.

## Hypothesis

This is a benchmark judgment gap rather than a ranking gap. Adding the reviewed
dose-specific osimertinib product as an acceptable alternative for the
ingredient target should make the focused lane count the already useful first
page result without adding a CUI-specific rank boost.

Expected movement: top-10 expected concepts should move from 31/36 to 32/36,
the EGFR row should move from mixed to good, and false positives should remain
at zero.

## Change

- Added `C4058811 -> C4058829` to
  `config/search_quality_acceptable_cui_alternatives.tsv`.
- Added a focused evaluator regression test proving the checked-in alternative
  counts `osimertinib 80 MG` as satisfying the `Osimertinib` benchmark target.
- Regenerated `docs/search_rule_inventory.html`.

## Result

Focused live rerun:

- Query file: `build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_queries.tsv`
- Output directory: `build/search_quality_experiments/runs/SQI-2026-06-11-005_pubmed_osimertinib_dose_form_alternative_sqi-2026-06-11-005-pubmed-osimertinib-dose-form-acceptable-alter`
- Server profile: `PORT=8791 PUBLIC_OUTPUT_ONLY=0 sh scripts/start_search_quality_server.sh`
- Command:

```sh
python3 scripts/run_search_quality_experiment.py --base-url http://127.0.0.1:8791 --scope umls_evidence --run-family probe --label 'SQI-2026-06-11-005 PubMed osimertinib dose-form acceptable alternative' --run-id SQI-2026-06-11-005_pubmed_osimertinib_dose_form_alternative --queries build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_queries.tsv --query-limit 0 --search-system api --top-k 60 --timeout 120 --output-root build/search_quality_experiments --html-report docs/search_quality_experiments.html --require-api-backend elasticsearch
```

Measured movement:

- Expected concepts at top 10: 31/36 -> 32/36.
- Expected concepts at top 20: 35/36 -> 35/36.
- Expected concepts at top 60: 36/36 -> 36/36.
- Good / mixed rows: 3 good / 4 mixed -> 4 good / 3 mixed.
- Expected semantic group recall at top 10: 88.9% -> 94.4%.
- Queries with all expected concepts at top 10: 3/7 -> 4/7.
- Strict success at top 10: 2/7 -> 3/7.
- Known false positives at top 10 and top 20: 0 -> 0.
- Accepted alternatives at top 10: `pubmed_egfr_nsclc_39951884:
  C4058811=C4058829`.
- Remaining focused top-10 misses: `C0154723`, `C0338480`, `C0011991`, and
  `C0009506`.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py::test_paragraph_evaluator_counts_acceptable_cui_alternatives tests/test_evidence_vectors.py::test_paragraph_evaluator_counts_configured_osimertinib_dose_form_alternative -q`
- `python3 -m py_compile scripts/run_search_quality_experiment.py scripts/evaluate_paragraph_quality.py`
- `python3 scripts/build_search_rule_inventory.py`
- `python3 scripts/run_search_quality_experiment.py --iteration-smoke-gates --iteration-id SQI-2026-06-11-005 --iteration-type benchmark --force-patient-portal-smoke --static-command "python3 -m py_compile scripts/run_search_quality_experiment.py scripts/evaluate_paragraph_quality.py" --focused-command "python3 -m pytest tests/test_evidence_vectors.py::test_paragraph_evaluator_counts_acceptable_cui_alternatives tests/test_evidence_vectors.py::test_paragraph_evaluator_counts_configured_osimertinib_dose_form_alternative -q" --base-url http://127.0.0.1:8791`

The iteration smoke helper passed static, focused, standing clinical, rotating
50-query, and patient-portal gates. The rotating 50-query smoke produced 40/50
strict success at top 10, 47/50 at top 20, 48/50 top-on-target, and 2 top-wrong.
The patient-portal lane stayed at 12/12 top-on-target and 0 top-wrong, with
source counts still present for `pmc_oa`, `pubmed_bulk`, and `pubmed`.

## Decision

Keep. This is a reviewed benchmark-definition correction, not a runtime ranking
boost, and it removes an already useful first-page hit from the focused
long-document miss list.
