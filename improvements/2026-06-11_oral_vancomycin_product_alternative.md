# SQI-2026-06-11-023 Oral vancomycin product alternative

## Problem

The approved PubMed long-document row
`pubmed_cdiff_antibiotic_diarrhea_21288078` ranked `C0360373` vancomycin Oral
Product first for an abstract that explicitly says `oral vancomycin`, while
the benchmark expected the ingredient `C0042313` vancomycin. The same row still
missed `C0343386` Clostridium difficile infection at top 10.

## Decision

Count `C0360373` as an acceptable alternative for `C0042313` only when the
result set is evaluating the vancomycin ingredient target. This matches the
existing accepted-alternative policy for specific drug forms such as
`C4058829` osimertinib 80 MG satisfying the `C4058811` osimertinib ingredient
target.

This is not a full row fix. The separate C. difficile infection target remains
missing at top 10 and must stay visible as the next recall/rerank issue.

## What changed

- Added `C0042313 -> C0360373` to
  `config/search_quality_acceptable_cui_alternatives.tsv`.
- Added a focused evaluator regression proving the oral product can satisfy the
  vancomycin target while `C0343386` remains missing and the row stays mixed.
- Reran the 13-row approved PubMed suite.

## Result

Approved PubMed moved from:

- 11/13 top-on-target.
- 2 wrong-first rows.
- 9/13 strict top 10.
- 9/13 strict top 20.
- Overall score 75.6.

To:

- 12/13 top-on-target.
- 1 wrong-first row.
- 9/13 strict top 10.
- 10/13 strict top 20.
- Overall score 76.7.

The C. difficile row is now top-on-target and strict at top 20, but it remains
mixed at top 10 because `C0343386` Clostridium difficile infection is rank 16.

## Verification

- `PYTHONPATH=src python3 -m py_compile tests/test_evidence_vectors.py scripts/run_search_quality_experiment.py`
- `PYTHONPATH=src python3 -m pytest -q tests/test_evidence_vectors.py::test_paragraph_evaluator_counts_oral_vancomycin_product_without_hiding_infection_miss tests/test_evidence_vectors.py::test_paragraph_evaluator_counts_configured_antibiotic_diarrhea_alternative tests/test_evidence_vectors.py::test_paragraph_evaluator_counts_configured_osimertinib_dose_form_alternative`
- `PYTHONPATH=src python3 scripts/run_search_quality_experiment.py --label "SQI-2026-06-11-023 oral vancomycin product alternative" --run-id SQI-2026-06-11-023_pubmed_oral_vancomycin_alternative --run-family probe --queries build/pubmed_literature_benchmark_seed/pubmed_literature_approved_queries.tsv --query-limit 0 --base-url http://127.0.0.1:8766 --require-api-backend elasticsearch --scope umls_evidence --mode balanced --search-system api --top-k 60 --timeout 180 --output-root build/search_quality_experiments --html-report docs/search_quality_experiments.html`
- Formal SQI-2026-06-11-023 smoke helper passed static, focused, standing
  clinical API, rotating 50-query, and patient-portal gates.

Artifacts:

- `build/search_quality_experiments/runs/SQI-2026-06-11-023_pubmed_oral_vancomycin_alternative_sqi-2026-06-11-023-oral-vancomycin-product-alternative/`
- `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-11-023/verification.md`

## Next action

Keep `SQB-002` at P0. The next bounded implementation target is
`pubmed_status_migrainosus_30198804`, where broad `C0001617` Adrenal Cortex
Hormones still ranks first above the status-migrainosus and migraine anchors.
