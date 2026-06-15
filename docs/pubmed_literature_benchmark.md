# PubMed Literature Benchmark

This benchmark exists because the clinical paragraph smoke test can overstate
general literature performance. PubMed abstracts are longer, contain more study
design language, and often require secondary concepts such as treatments,
outcomes, biomarkers, and cohort attributes to remain visible.

## Policy

- Do not score fetched abstracts with topic-level expected CUIs.
- Every scored abstract must have an approved per-PMID row in
  `config/pubmed_literature_abstract_curation.tsv`.
- Keep `dev` and `heldout` outputs separate.
- Use `dev` for diagnosis and iteration.
- Use `heldout` for periodic checks; do not tune from row-level held-out misses
  without first moving the affected row into a new dev iteration and replacing
  the held-out row.

## Seed Set

The current seed curation has 13 approved abstracts:

- Dev: 7 abstracts.
- Held-out: 6 abstracts.
- Source curation: `config/pubmed_literature_abstract_curation.tsv`.

Generate the strict scored files:

```bash
python3 scripts/fetch_pubmed_paragraph_queries.py \
  --topics config/pubmed_paragraph_topics.tsv \
  --curation config/pubmed_literature_abstract_curation.tsv \
  --strict-curation \
  --output-dir build/pubmed_literature_benchmark_seed
```

This writes:

- `build/pubmed_literature_benchmark_seed/pubmed_literature_dev_queries.tsv`
- `build/pubmed_literature_benchmark_seed/pubmed_literature_heldout_queries.tsv`
- `build/pubmed_literature_benchmark_seed/pubmed_review_queue.tsv`
- `build/pubmed_literature_benchmark_seed/benchmark_manifest.json`

## Focused Long-Document Slice

SQI-2026-06-10-004 adds a focused dev-only slice for the next long-document
iteration. The slice intentionally uses reviewed PubMed dev rows and should be
run before section/chunk linking or reranking changes.

Slice selector:

- `config/search_quality_pubmed_long_document_slice.tsv`

Materialize the evaluator-ready TSV from the strict seed files:

```bash
python3 scripts/build_pubmed_long_document_slice.py
```

This writes:

- `build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_queries.tsv`
- `build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_manifest.json`

Score the focused slice against the current search API:

```bash
PYTHONPATH=src:scripts python3 scripts/run_search_quality_experiment.py \
  --queries build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_queries.tsv \
  --base-url http://127.0.0.1:8766 \
  --scope umls_evidence \
  --search-system api \
  --run-family probe \
  --label "PubMed long-document focused slice"
```

Use this slice to diagnose long-text recall failures on secondary concepts:
treatments, outcomes, biomarkers, organisms, complications, and cohort
attributes. Keep held-out scoring separate.
For timing probes, compare `--workers 1` against the default two-worker API run
and inspect `query_timings.tsv` in the run directory; exact-repeat cache hits
should not be counted as uncached speed wins.

Baseline run on 2026-06-10 against the local API on port `8766`:

| Slice | Rows | Overall | All Expected@10 | Recall@10 | Recall@20 | Top On Target | Verdicts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Focused dev | 7 | 29.0 | 1/7 | 24/36 | 30/36 | 6/7 | 6 mixed, 1 poor |

Run artifact:
`build/search_quality_experiments/runs/20260610T172821Z_pubmed-long-document-focused-slice/paragraph_quality_report.md`.

The first baseline confirms the target failure mode: the top result is usually
on topic, but secondary concepts still fall out of the first result page.

## Current Seed Results

Run on 2026-06-09 against the live Elasticsearch-backed API on port `8767`:

| Split | Rows | Overall | Strict@10 | Recall@10 | Top On Target | Verdicts |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Dev | 7 | 39.3 | 1/7 | 26/36 | 6/7 | 1 good, 6 mixed |
| Held-out | 6 | 40.2 | 1/6 | 17/24 | 6/6 | 2 good, 4 mixed |

The seed result confirms the original assessment: the system usually finds the
main abstract topic but is still incomplete on secondary literature concepts.

## Scaling To 50-100 Abstracts

Use `config/pubmed_literature_candidate_topics.tsv` to fetch a review queue of
about 100 candidate abstracts:

```bash
python3 scripts/fetch_pubmed_paragraph_queries.py \
  --topics config/pubmed_literature_candidate_topics.tsv \
  --output-dir build/pubmed_literature_candidates
```

Then review `build/pubmed_literature_candidates/pubmed_review_queue.tsv`.
Promote only reviewed rows into `config/pubmed_literature_abstract_curation.tsv`
with:

- `pmid`
- `split` as `dev` or `heldout`
- `review_status` set to `approved`
- `expected_cuis` supported by the actual fetched title/abstract text
- `disallowed_cuis` for known distracting false positives
- a short `why` note

After curation, rerun strict generation and score the split files:

```bash
PYTHONPATH=src:scripts python3 scripts/run_search_quality_experiment.py \
  --queries build/pubmed_literature_benchmark_seed/pubmed_literature_dev_queries.tsv \
  --base-url http://127.0.0.1:8767 \
  --scope umls_evidence \
  --search-system api \
  --run-family probe \
  --label "PubMed literature dev"

PYTHONPATH=src:scripts python3 scripts/run_search_quality_experiment.py \
  --queries build/pubmed_literature_benchmark_seed/pubmed_literature_heldout_queries.tsv \
  --base-url http://127.0.0.1:8767 \
  --scope umls_evidence \
  --search-system api \
  --run-family probe \
  --label "PubMed literature heldout"
```

Keep these results separate from `config/search_quality_paragraph_queries.tsv`.
The clinical smoke score answers whether the clinical regression set still
works. The PubMed literature score answers whether long biomedical abstracts are
complete enough for research text.
