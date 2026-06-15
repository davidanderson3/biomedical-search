# Script Index

Last updated: 2026-06-10

This directory intentionally keeps executable entrypoints at `scripts/<name>.py`.
Many docs, tests, subprocess calls, and shell snippets refer to those paths.
The category folders in this directory are indexes only; they make the script
set easier to scan without changing any command paths.

## Compatibility Rule

- Keep existing `scripts/<name>.py` and `scripts/<name>.sh` paths stable.
- If a script implementation moves later, leave a compatibility wrapper at the
  old path and test both the old command path and the new implementation path.
- Update this index, the matching category README, and
  `docs/repeatable_processes.md` when adding or moving a repeatable entrypoint.
- Prefer imports that work from the repository root with `PYTHONPATH=src:scripts`.

## Pipeline And Rebuild

| Script | Purpose |
| --- | --- |
| `evidence_vectors.py` | Main CLI for source policy, corpus fetching, UMLS index builds, evidence linking, concept docs, embeddings, Elasticsearch export/load, and related pipeline tasks. |
| `run_public_rebuild.py` | Public/shareable rebuild wrapper for licensed-local inputs and public outputs. |
| `run_existing_data_iteration.py` | Existing-data/new-UMLS iteration runner. |
| `reproducibility_manifest.py` | Records local source inputs and generated artifact fingerprints. |
| `source_acquisition_progression.py` | Validates source acquisition progression and regression status. |
| `check_source_rebuild_delta.py` | Compares source rebuild outputs. |
| `scaling_status.py` | Summarizes scaling/build status artifacts. |
| `sitecustomize.py` | Local Python path helper for script execution contexts. |

See `pipeline/README.md`.

## Serving

| Script | Purpose |
| --- | --- |
| `search_quality_server.py` | Local search API and browser UI server. |
| `start_search_quality_server.sh` | Shell launcher for the search-quality server. |

See `serve/README.md`.

## Search Quality And Evaluation

| Script | Purpose |
| --- | --- |
| `run_search_quality_suite.py` | Repeatable suite runner for static checks, full clinical coverage, rotating regression samples, portal intent, and PubMed long-document weakness probes. |
| `run_search_quality_experiment.py` | Paragraph/search-quality experiments, reports, and post-iteration smoke gates. |
| `evaluate_search_api.py` | Standing API smoke and search regression evaluation. |
| `run_search_regression_benchmark.py` | Regression benchmark runner. |
| `evaluate_paragraph_quality.py` | Paragraph quality evaluation. |
| `audit_paragraph_precision.py` | Top-result precision audit queue generation. |
| `build_precision_audit_report.py` | Reviewed precision-audit report generation. |
| `analyze_search_judgments.py` | Judgment file analysis. |
| `search_quality_shadow_reranker.py` | Feature extraction, shadow reranker training, and current-vs-ML rank report. |
| `build_search_rule_inventory.py` | Static rule and heuristic inventory report. |
| `validate_active_label_supplement.py` | Active label supplement validation. |

See `quality/README.md`.

## Benchmarks

| Script | Purpose |
| --- | --- |
| `fetch_pubmed_paragraph_queries.py` | PubMed paragraph query acquisition for literature benchmarks. |
| `build_pubmed_long_document_slice.py` | Focused PubMed long-document benchmark slice materializer. |
| `run_medmentions_benchmark.py` | MedMentions linking benchmark runner. |
| `run_trec_benchmark.py` | TREC Precision Medicine / Clinical Decision Support document-source benchmark runner. |
| `compare_to_gold_standard.py` | Locked translation/gold-standard comparison. |
| `compare_umls_api.py` | UMLS API comparison helper. |
| `run_private_real_query_diagnostic.py` | Private real-query diagnostic runner. |

See `benchmarks/README.md`.

## Sources And Enrichment

| Script | Purpose |
| --- | --- |
| `build_openalex_cited_evidence.py` | OpenAlex cited-evidence builder. |
| `build_drug_enrichment.py` | Drug enrichment builder. |
| `build_wikipedia_enrichment.py` | Wikipedia enrichment builder. |
| `build_open_image_enrichment.py` | Open image enrichment builder. |
| `build_procedure_bundles.py` | Public procedure bundle builder. |
| `mine_ohdsi_relationships.py` | Aggregate OHDSI relationship mining. |
| `build_real_query_inventory.py` | Private real-query inventory builder. |
| `fetch_pubmed_ui_samples.py` | PubMed UI sample fetcher. |
| `generate_typical_sentences.py` | Typical sentence generation helper. |

See `sources/README.md`.

## Reports And Dashboards

| Script | Purpose |
| --- | --- |
| `build_source_evidence_dashboard.py` | Source evidence dashboard builder. |
| `build_translation_benchmark_report.py` | Translation benchmark HTML report builder. |

See `reports/README.md`.
