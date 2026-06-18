# PubMed Pharmacogenomic Response Top Result

## Problem

The focused PubMed long-document lane no longer had any expected top-10 misses,
but the CYP2C19/clopidogrel row still counted as mixed. Aspirin ranked first
because it was explicitly mentioned as background antiplatelet therapy, while
the pharmacogenomic target and response concepts were present but lower.

Baseline after SQI-2026-06-11-009:

- Query file: `build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_queries.tsv`
- Result: 36/36 expected concepts at top 10 and top 20, 7/7 rows complete at
  top 10, 6 good / 1 mixed rows, and 0 known false positives.
- Remaining focused issue: the CYP2C19 row was mixed because aspirin was the top
  result even though the paragraph was about CYP2C19 loss-of-function and
  clopidogrel response.

## Hypothesis

Pharmacogenomic response queries need a local context signal that recognizes
direct CYP/gene, metabolizer/response, and local drug spans. The signal should
be sentence-bounded around the hit span so a background drug mention does not
inherit pharmacogenomic wording from a later sentence.

Expected movement: the CYP2C19 row should become good, the focused lane should
move from 6 good / 1 mixed row to 7 good / 0 mixed rows, and focused top-10
recall should stay at 36/36.

## Change

- Added a `pharmacogenomic_response_component` to search ranking.
- Required the whole query to contain both pharmacogenomic anchor wording and
  response/metabolizer wording before the component applies.
- Required direct overlap between specific query tokens and hit label tokens.
- Used sentence-bounded local context around the matched span, preventing aspirin
  from picking up pharmacogenomic context from the next sentence.
- Added focused regression tests for the CYP2C19/clopidogrel/aspirin ranking
  shape and for the no-boost ordinary drug-query case.
- Regenerated `docs/search_rule_inventory.html`.

## Result

Focused live rerun:

- Query file: `build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_queries.tsv`
- Output directory: `build/search_quality_experiments/runs/20260611T161508Z_sqi-2026-06-11-010-pubmed-pharmacogenomic-response-top-result-fu`
- Server profile: `PORT=8766 PUBLIC_OUTPUT_ONLY=0 sh scripts/start_search_quality_server.sh`
- Command:

```sh
python3 scripts/run_search_quality_experiment.py --label "SQI-2026-06-11-010 pubmed pharmacogenomic response top result full profile" --queries build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_queries.tsv --run-family probe --query-limit 0 --query-selection first --search-system api --scope umls_evidence --top-k 60 --base-url http://127.0.0.1:8766 --timeout 120 --html-report docs/search_quality_experiments.html
```

Measured movement:

- Good / mixed rows: 6 good / 1 mixed -> 7 good / 0 mixed.
- Expected concepts at top 10: 36/36 -> 36/36.
- Expected concepts at top 20: 36/36 -> 36/36.
- Queries with all expected concepts at top 10: 7/7 -> 7/7.
- Top-on-target rows: 7/7.
- Wrong-first rows: 0.
- Overall focused score: 100.0.
- CYP2C19 row top results: clopidogrel rank 1, aspirin rank 2, CYP2C19 gene
  rank 3, ticagrelor rank 4, and Poor metabolizer rank 6.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py::test_query_ranker_prefers_pharmacogenomic_response_targets_over_background_drug tests/test_evidence_vectors.py::test_query_ranker_does_not_add_pharmacogenomic_boost_without_response_context -q`
- `python3 -m pytest tests/test_evidence_vectors.py -k "pharmacogenomic or treatment_drug or long_document" -q`
- `python3 -m py_compile src/qe_evidence_vectors/search_ranking.py scripts/run_search_quality_experiment.py scripts/search_quality_server.py`
- `python3 scripts/build_search_rule_inventory.py`
- `python3 scripts/run_search_quality_experiment.py --iteration-smoke-gates --iteration-id SQI-2026-06-11-010 --iteration-type ranking --iteration-type long-document --focused-command "python3 -m pytest tests/test_evidence_vectors.py -k 'pharmacogenomic or treatment_drug or long_document' -q" --base-url http://127.0.0.1:8766 --force-rotating-smoke --force-patient-portal-smoke --verification-out build/search_quality_verification/SQI-2026-06-11-010.json --verification-md-out build/search_quality_verification/SQI-2026-06-11-010.md`

The iteration smoke helper passed focused, standing clinical, rotating 50-query,
and patient-portal gates. The rotating 50-query smoke produced 44/50 strict
success at top 10, 48/50 at top 20, 48/50 top-on-target, and 2 top-wrong. The
patient-portal lane stayed at 12/12 top-on-target and 0 top-wrong.

## Decision

Keep. This closes the focused pharmacogenomic wrong-first/mixed row with a
reusable sentence-bounded context rule rather than a CUI-specific aspirin
demotion.
