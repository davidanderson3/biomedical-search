# PubMed Migraine With-Or-Without-Aura Aggregate Alternative

## Problem

The focused PubMed long-document lane still counted `C0154723` Migraine with
Aura and `C0338480` Common Migraine as top-10 misses for the status
migrainosus review abstract. The abstract explicitly says `migraine with or
without aura`, and the search result set already had the exact aggregate
concept `C3808875` Migraine, with or without aura lower in the list.

Baseline run:

- Query file: `build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_queries.tsv`
- Output directory: `build/search_quality_experiments/runs/SQI-2026-06-11-007_pubmed_current_baseline_sqi-2026-06-11-007-pubmed-focused-current-baseline`
- Result: 33/36 expected concepts at top 10, 35/36 at top 20, 36/36 at top 60,
  4 good / 3 mixed rows, 5/7 rows complete at top 10, 4/7 strict success at top
  10, and 0 known false positives.
- Status migrainosus row detail: `C3808875` was present but outside the first
  page, while the two subtype targets were also outside the first page.

## Hypothesis

This should not be solved by broadly accepting `Migraine Disorders` for both
aura subtype targets. The paragraph uses the exact aggregate phrase, so the
durable route is to make that aggregate concept visible with active-label
evidence and count it as a reviewed acceptable alternative for both subtype
expectations when the wording is explicit.

Expected movement: focused top-10 expected concepts should move from 33/36 to
35/36, all-expected rows from 5/7 to 6/7, and known false positives should stay
at zero.

## Change

- Added `C0154723 -> C3808875` and `C0338480 -> C3808875` to
  `config/search_quality_acceptable_cui_alternatives.tsv`.
- Added an active-label supplement row for `migraine with or without aura` so
  the exact aggregate phrase remains first-page visible in status migrainosus
  review abstracts.
- Added a focused evaluator regression test proving one first-page
  `C3808875` hit satisfies both aura subtype expectations.
- Regenerated `docs/search_rule_inventory.html`.

## Result

Focused live rerun:

- Query file: `build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_queries.tsv`
- Output directory: `build/search_quality_experiments/runs/SQI-2026-06-11-007_pubmed_migraine_with_or_without_aura_final_8766_sqi-2026-06-11-007-pubmed-migraine-aggregate-final-8766`
- Server profile: `PORT=8766 PUBLIC_OUTPUT_ONLY=0 sh scripts/start_search_quality_server.sh`
- Command:

```sh
python3 scripts/run_search_quality_experiment.py --base-url http://127.0.0.1:8766 --scope umls_evidence --run-family probe --label 'SQI-2026-06-11-007 PubMed migraine aggregate final 8766' --run-id SQI-2026-06-11-007_pubmed_migraine_with_or_without_aura_final_8766 --queries build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_queries.tsv --query-limit 0 --search-system api --top-k 60 --timeout 120 --output-root build/search_quality_experiments --html-report docs/search_quality_experiments.html --require-api-backend elasticsearch
```

Measured movement:

- Expected concepts at top 10: 33/36 -> 35/36.
- Expected concepts at top 20: 35/36 -> 35/36.
- Expected concepts at top 60: 36/36 -> 36/36.
- Queries with all expected concepts at top 10: 5/7 -> 6/7.
- Strict success at top 10: 4/7 -> 5/7.
- Good / mixed rows: 4 good / 3 mixed -> 5 good / 2 mixed.
- Known false positives at top 10 and top 20: 0 -> 0.
- Status migrainosus row accepted alternatives at top 10:
  `C0154723=C3808875|C0338480=C3808875`.
- `C3808875` moved to rank 7 in the status migrainosus row.
- Remaining focused top-10 miss: `C0009506` Complement 3 in the
  lupus/preeclampsia row.

## Verification

- `python3 scripts/validate_active_label_supplement.py`
- `python3 -B -m pytest tests/test_evidence_vectors.py::test_paragraph_evaluator_counts_configured_migraine_aggregate_alternative tests/test_evidence_vectors.py::test_paragraph_evaluator_counts_configured_antibiotic_diarrhea_alternative tests/test_evidence_vectors.py::test_direct_query_span_matches_with_or_without_variants tests/test_evidence_vectors.py::test_with_or_without_phrase_is_not_denial_scope -q`
- `python3 -m py_compile scripts/run_search_quality_experiment.py scripts/evaluate_paragraph_quality.py src/qe_evidence_vectors/active_label_supplement.py`
- `python3 scripts/build_search_rule_inventory.py`
- `python3 scripts/run_search_quality_experiment.py --iteration-smoke-gates --iteration-id SQI-2026-06-11-007 --iteration-type benchmark --iteration-type data --iteration-type long-document --base-url http://127.0.0.1:8766 --require-api-backend elasticsearch --force-rotating-smoke --force-patient-portal-smoke --static-command 'python3 -m py_compile scripts/run_search_quality_experiment.py scripts/evaluate_paragraph_quality.py src/qe_evidence_vectors/active_label_supplement.py && python3 scripts/validate_active_label_supplement.py' --focused-command 'python3 -B -m pytest tests/test_evidence_vectors.py::test_paragraph_evaluator_counts_configured_migraine_aggregate_alternative tests/test_evidence_vectors.py::test_direct_query_span_matches_with_or_without_variants tests/test_evidence_vectors.py::test_with_or_without_phrase_is_not_denial_scope -q' --verification-out build/search_quality_verification/SQI-2026-06-11-007.json --verification-md-out build/search_quality_verification/SQI-2026-06-11-007.md`

The iteration smoke helper passed static, focused, standing clinical, rotating
50-query, and patient-portal gates. The rotating 50-query smoke produced 43/50
strict success at top 10, 47/50 at top 20, 47/50 top-on-target, and 3 top-wrong.
The patient-portal lane stayed at 12/12 top-on-target and 0 top-wrong, with
top-10 source counts still present for `pmc_oa`, `pubmed_bulk`, and `pubmed`.

## Decision

Keep. This keeps the fix tied to the exact phrase used by the abstract and the
specific aggregate CUI, avoiding a broad migraine-disorder substitution or a
runtime CUI-specific rank boost.
