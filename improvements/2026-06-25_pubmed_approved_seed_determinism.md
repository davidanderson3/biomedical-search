# PubMed Approved Seed Determinism

- Iteration: `SQI-2026-06-25-004`
- Backlog row: `SQB-002 Long-document survival`
- Status: shipped; SQB-002 remains P0
- Type: benchmark/data/process

## Problem

The progress log described the approved PubMed long-document lane as a 23-row
benchmark, but rebuilding `build/pubmed_literature_benchmark_seed/` from the
documented command produced only 22 approved rows. The missing row was curated
PMID `8659509`, the title-only hypocomplementemia/proteinuria row. It was not
materialized because several approved topics still depended on a live NCBI topic
search instead of explicit reviewed PMIDs.

## Change

Pinned the reviewed approved PMIDs in `config/pubmed_paragraph_topics.tsv` for
the PubMed topics that previously depended on topic-search ranking. Updated the
PubMed lane risk note in `config/whole_product_quality_scorecard.json` to match
the restored current run. Added a static regression test that requires every approved PMID in
`config/pubmed_literature_abstract_curation.tsv` to appear in the topic file's
explicit `pmids` column.

## Result

The strict seed rebuild now produces 23 approved abstracts, split as 12 dev and
11 held-out rows, with `topic_fallback_rows` at 0. The restored held-out file
includes `pubmed_lupus_preeclampsia_8659509`, and the focused dev slice still
materializes to 7 rows.

The live approved PubMed rerun against `http://127.0.0.1:8766` wrote
`SQI-2026-06-25-004_pubmed_seed_deterministic_approved_sqi-2026-06-25-004-deterministic-approved-pubmed-seed`.
It measured 7/23 strict top 10 rows, 78/106 expected concepts at top 10, 82/106
at top 20, 90/106 at top 60, 20/23 top-on-target, 3 wrong-first rows, and 0
configured disallowed concepts at top 10.

The whole-product scorecard reconciled that current PubMed artifact to raw 84.3
and published 84%.

## Verification

- `python3 scripts/fetch_pubmed_paragraph_queries.py --topics config/pubmed_paragraph_topics.tsv --curation config/pubmed_literature_abstract_curation.tsv --strict-curation --output-dir build/pubmed_literature_benchmark_seed`
- `python3 scripts/build_pubmed_long_document_slice.py`
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile scripts/fetch_pubmed_paragraph_queries.py scripts/build_pubmed_long_document_slice.py tests/test_pubmed_paragraph_queries.py`
- `python3 -m pytest tests/test_pubmed_paragraph_queries.py -q`
- `PYTHONPATH=src:scripts python3 scripts/run_search_quality_experiment.py --queries build/pubmed_literature_benchmark_seed/pubmed_literature_approved_queries.tsv --base-url http://127.0.0.1:8766 --scope umls_evidence --search-system api --run-family probe --query-limit 0 --query-selection first --top-k 60 --timeout 240 --workers 2 --run-id SQI-2026-06-25-004_pubmed_seed_deterministic_approved --label "SQI-2026-06-25-004 deterministic approved PubMed seed"`
- `PYTHONPYCACHEPREFIX=.pycache_local python3 scripts/build_whole_product_quality_scorecard.py`

## Follow-Up

Keep `SQB-002` as the active P0 item. The restored run reopens first-answer
trust work for three approved PubMed rows:

- `pubmed_lupus_preeclampsia_33977794`: `C0003243` Antibodies, Antinuclear first
- `pubmed_covid_ards_shock_37633303`: `C0242488` Acute Lung Injury first
- `pubmed_cystic_fibrosis_modulator_31697873`: `C0056889` CFTR first

The next ranking iteration should triage those wrong-first rows before broader
secondary-concept recall work.
