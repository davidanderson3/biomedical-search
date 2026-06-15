# PubMed Long-Document Post-Rerank Recall Preservation

## Problem

The focused PubMed long-document lane regressed on the current code path after
the patient-portal changes. The 7-row focused slice still found every expected
concept by top 60, but several explicitly mentioned secondary concepts fell out
of the first page after the post-merge rerank.

Baseline run:

- Query file: `build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_queries.tsv`
- Output directory: `build/search_quality_experiments/runs/SQI-2026-06-11-004_pubmed_long_document_baseline_sqi-2026-06-11-004-pubmed-long-document-current-baseline`
- Result: 28/36 expected concepts at top 10, 33/36 at top 20, 36/36 at top 60,
  2 good / 5 mixed rows, 6/7 top-on-target, and 1 top-wrong row.

The active misses included `Progression-Free Survival` in the EGFR/NSCLC row,
`Antibiotic-associated diarrhea` in the C. diff row, and systemic lupus in the
lupus nephritis row.

## Hypothesis

The existing long-document first-page promotion worked before a later
linked-label rerank, but the final API order could still leave strongly
supported candidates just outside top 10. Reapplying the same bounded promotion
after the post-merge rerank should recover section-supported secondary concepts.
The replacement rule also needed a guard so a promoted candidate could not trade
away a stronger, high-support central top-10 concept.

Educational/rank grade concepts (`School Grade`, `Grade three rank`) were also
leaking from oncology `grade >=3 adverse event` phrasing and were added to the
audited generic suppression class.

## Change

- Added `School Grade` / `C3244287` and `Grade three rank` / `C0450094` to the
  generic suppression list.
- Reapplied bounded long-document first-page recall preservation after the API
  post-merge linked-label rerank in both local and Elasticsearch search paths.
- Tightened long-document replacement so a candidate does not displace a
  high-support top-10 concept that already covers at least as many direct query
  tokens.
- Added focused unit tests for post-rerank recovery, strong top-10 concept
  protection, and the grade-rank generic suppression class.
- Regenerated `docs/search_rule_inventory.md`.

## Result

Focused live rerun:

- Query file: `build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_queries.tsv`
- Output directory: `build/search_quality_experiments/runs/SQI-2026-06-11-004_pubmed_long_document_post_rerank_recall_sqi-2026-06-11-004-pubmed-long-document-post-rerank-recall-prese`
- Server profile: `PORT=8791 PUBLIC_OUTPUT_ONLY=0 sh scripts/start_search_quality_server.sh`
- Command:

```sh
python3 scripts/run_search_quality_experiment.py --base-url http://127.0.0.1:8791 --scope umls_evidence --run-family probe --label 'SQI-2026-06-11-004 PubMed long-document post-rerank recall preservation' --run-id SQI-2026-06-11-004_pubmed_long_document_post_rerank_recall --queries build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_queries.tsv --query-limit 0 --search-system api --top-k 60 --timeout 120 --output-root build/search_quality_experiments --html-report docs/search_quality_experiments.html --require-api-backend elasticsearch
```

Measured movement:

- Expected concepts at top 10: 28/36 -> 31/36.
- Expected concepts at top 20: 33/36 -> 35/36.
- Expected concepts at top 60: 36/36 -> 36/36.
- Good / mixed rows: 2 good / 5 mixed -> 3 good / 4 mixed.
- Expected semantic group recall at top 10: 83.3% -> 88.9%.
- Known false positives at top 10 and top 20: 0 -> 0.
- Remaining focused top-10 misses: `C0154723`, `C0338480`, `C4058811`,
  `C0011991`, and `C0009506`.

## Verification

- `python3 scripts/build_search_rule_inventory.py`
- `python3 -m py_compile src/qe_evidence_vectors/generic_filters.py src/qe_evidence_vectors/search_ranking.py src/qe_evidence_vectors/search_execution.py scripts/build_search_rule_inventory.py`
- `python3 -m pytest tests/test_evidence_vectors.py::test_long_document_first_page_promotes_post_rerank_outcome_and_repeated_drug tests/test_evidence_vectors.py::test_long_document_first_page_keeps_stronger_supported_top10_concept tests/test_evidence_vectors.py::test_generic_filter_blocks_known_bad_concepts tests/test_evidence_vectors.py::test_generic_filter_blocks_standalone_fragments_but_allows_watchlist_contexts -q`
- `python3 scripts/run_search_quality_experiment.py --iteration-smoke-gates --iteration-id SQI-2026-06-11-004 --iteration-type ranking --iteration-type long-document --broad-change --force-patient-portal-smoke --static-command "python3 -m py_compile src/qe_evidence_vectors/generic_filters.py src/qe_evidence_vectors/search_ranking.py src/qe_evidence_vectors/search_execution.py scripts/build_search_rule_inventory.py" --focused-command "python3 -m pytest tests/test_evidence_vectors.py::test_long_document_first_page_promotes_post_rerank_outcome_and_repeated_drug tests/test_evidence_vectors.py::test_long_document_first_page_keeps_stronger_supported_top10_concept tests/test_evidence_vectors.py::test_generic_filter_blocks_known_bad_concepts tests/test_evidence_vectors.py::test_generic_filter_blocks_standalone_fragments_but_allows_watchlist_contexts -q" --base-url http://127.0.0.1:8791`

The iteration smoke helper passed static, focused, standing clinical, rotating
50-query, and patient-portal gates. The rotating 50-query smoke produced 44/50
strict success at top 10, 48/50 at top 20, 48/50 top-on-target, and 2 top-wrong.
The patient-portal lane stayed at 74/88 expected concepts at top 10, 12/12
top-on-target, and 0 top-wrong.

## Decision

Keep. This is a reusable long-document ranking fix with a measured focused-lane
gain and no observed patient-portal or rotating-smoke gate regression.
