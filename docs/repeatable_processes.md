# Repeatable Processes

Last updated: 2026-06-10

This report is the operating index for repeatable work in this repository. It
consolidates the runbooks that were previously spread across README, benchmark
docs, pipeline docs, API docs, and script help.

Scope: this covers processes that are currently documented or backed by scripts.
It does not replace the specialized docs; it tells you which repeatable process
to use, which command starts it, what inputs it expects, what artifacts it
writes, and how to verify the result.

## Ground Rules

- Run commands from the repository root.
- Treat `build/` as generated output and `data/` as local source input.
- Keep licensed or private inputs under ignored local paths. UMLS, LOINC,
  SNOMED CT, external CUI vectors, and raw real-query exports are not public
  fixtures.
- Use `/path/to/...` placeholders for local licensed files in docs and examples.
- Use `PYTHONPATH=src:scripts` for scripts that import both package code and
  sibling script utilities when the command examples include it.
- Keep executable script entrypoints stable at `scripts/<name>.py` or
  `scripts/<name>.sh`; use `scripts/README.md` and the category README files as
  the navigation layer.
- For docs-only or local-source layout changes, record why live smoke was not
  needed.
- For runtime search, ranking, source-code output, benchmark-label, judgment,
  or API behavior changes, run the standing clinical API smoke before marking
  the iteration shipped.
- For broad ranking/runtime or release-quality changes, also run the 50-query
  rotating smoke with gates.
- Record bounded search-quality work in `docs/search_quality_iterations.md` and
  `docs/search_quality_iterations.html`.

## Process Index

| Area | Process | Entrypoint | Main outputs | Verification |
| --- | --- | --- | --- | --- |
| Setup | Install public/dev dependencies | `pip install -r requirements-*.txt` | Local Python env | Targeted `pytest` or full test suite |
| Script catalog | Stable script entrypoint map | `scripts/README.md` | Category indexes under `scripts/*/README.md` | Existing `scripts/<name>.py` and `.sh` references remain valid |
| Public rebuild | Public/shareable rebuild wrapper | `scripts/run_public_rebuild.py` | `build/public/*` | Paragraph quality and precision audit |
| Reproducibility | Local artifact manifest | `scripts/reproducibility_manifest.py` | `build/reproducibility_manifest.json` | Manifest exists and records expected inputs |
| Source policy | Reference-source policy review | `evidence_vectors.py reference-source-policy` | Policy table output | Restricted sources remain blocked by default |
| Source acquisition | Measured acquisition plan | `evidence_vectors.py plan-source-acquisition` | Plan JSON/TSV/MD and review queues | Review plan plus source-acquisition progression |
| Source progression | Acquisition ledger validation | `scripts/source_acquisition_progression.py` | Progression manifest/report | `--fail-on-regression` after artifacts exist |
| Corpus fetch | Public corpus acquisition | `evidence_vectors.py fetch-*` | Corpus JSONL | Row counts and source/license metadata |
| Source subset | One-source incremental build | `evidence_vectors.py build-source-subset` | Corpus/evidence/docs/vectors | Source-specific benchmark and smoke as needed |
| UMLS indexes | Label/code/type indexes | `evidence_vectors.py build-*index` | SQLite indexes | Server can resolve labels, codes, CUIs |
| Linking | Corpus to CUI evidence | `evidence_vectors.py link-*` | Evidence JSONL shards | Evidence counts and profile mix |
| Concept docs | Evidence aggregation | `evidence_vectors.py build-docs*` | Concept document JSONL | Row counts and representative CUI docs |
| Embedding | Vector generation | `evidence_vectors.py embed` | Vector JSONL | Provider/model/dimensions match target |
| Incremental UMLS | Fingerprint, diff, vector reuse | `evidence_vectors.py build-atom-fingerprints`, `diff-atom-fingerprints`, `plan-vector-reuse` | Changed CUI TSV, reuse plan, assembled vectors | Strict assembly summary passes |
| Elasticsearch | Export/load/alias | `evidence_vectors.py export-elastic`, `load-elastic`, `alias-elastic` | Mapping, bulk parts, loaded index/alias | kNN query and live API status |
| Serving | Search API and browser UI | `scripts/search_quality_server.py` | Local API/UI on port | `/api/health`, `/api/status`, smoke |
| API regression | Standing clinical smoke | `scripts/evaluate_search_api.py` or `scripts/run_search_regression_benchmark.py` | TSV/JSON summaries | Expected CUIs rank within target top-k |
| Search experiment | Paragraph quality experiment | `scripts/run_search_quality_experiment.py` | Run directory, metrics, HTML update | Gates pass when `--fail-gates` is set |
| Post-iteration smoke | Automatic smoke-tier helper | `scripts/run_search_quality_experiment.py --iteration-smoke-gates` | Verification JSON/Markdown, HTML panel | Selected static/focused/live steps pass |
| Promotion gate | Weakness-to-code-or-evidence loop | Search experiment, source progression, and iteration ledger | Promote/reject decision record | Improved target with no unacceptable regression |
| Precision audit | Top-N visible FP audit | `scripts/audit_paragraph_precision.py` and `scripts/build_precision_audit_report.py` | Audit TSV/MD report | Reviewed residuals classified |
| Rule inventory | Heuristic/rule review | `scripts/build_search_rule_inventory.py` | `docs/search_rule_inventory.md` | Static report review and relevant unit tests |
| Label supplement | Active-label validation | `scripts/validate_active_label_supplement.py` | Validation result | Validation plus active-label tests |
| Judgments/reranker | Shadow ML reranker | `scripts/search_quality_shadow_reranker.py` | Canonical judgments, features, HTML report | Wins/losses/regressions reviewed; no production effect |
| PubMed benchmark | Strict PubMed literature benchmark | `scripts/fetch_pubmed_paragraph_queries.py`, `scripts/build_pubmed_long_document_slice.py` | Dev/heldout/focused query TSVs | Separate dev and heldout reports |
| MedMentions | External linking benchmark | `scripts/run_medmentions_benchmark.py` | Prepared queries and eval outputs | Category-specific metrics |
| TREC PM/CDS | External document-source benchmark | `scripts/run_trec_benchmark.py` | Topics, qrels, coverage, document-query TSVs | Coverage first; document/source metrics separate from CUI metrics |
| Real logs | Private query inventory | `scripts/build_real_query_inventory.py` | Local inventory/review queue | Raw data stays under `data/`/`build/` |
| OHDSI | Aggregate relationship mining | `scripts/mine_ohdsi_relationships.py` | Relationship-edge JSONL | Patient-level rows rejected |
| Procedures | Public procedure bundles | `scripts/build_procedure_bundles.py` | Concepts/relations/registry JSONL | CPT content rejected |
| Enrichment | Drug/OpenAlex/Wikipedia/image enrichments | `scripts/build_*enrichment.py` | Enrichment docs/vectors/metadata | Source-specific manifest and review |
| Dashboards | Source/progress/report generation | `scripts/build_source_evidence_dashboard.py`, `scripts/scaling_status.py`, report builders | HTML/JSON/MD reports | Static syntax/review checks |
| Translation | Locked translation benchmark report | `scripts/compare_to_gold_standard.py`, `scripts/build_translation_benchmark_report.py` | Translation JSON/HTML | Locked slices remain separate |
| Iteration loop | Existing-data/new-UMLS iteration | `scripts/run_existing_data_iteration.py` | Iteration manifest/report/artifacts | Iteration gates and smoke decision |

## Environment And Test Setup

Use this when validating a fresh clone or preparing a development machine.

```sh
python3 -m pip install -r requirements-public.txt
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q
```

Inputs:

- `requirements-public.txt`
- `requirements-dev.txt`
- local Python 3 environment

Outputs:

- installed public and dev dependencies
- pytest results

Notes:

- The public hashing path is mostly standard-library only.
- Transformer embeddings need optional packages such as `torch` and
  `transformers`.
- Full `pytest -q` can be broader than needed for a small docs-only change; use
  targeted tests for bounded code changes and record why they are sufficient.

## Script Catalog

Use this when you need to find the right script without breaking existing
command references.

Primary index:

```sh
sed -n '1,220p' scripts/README.md
```

Inputs:

- current scripts under `scripts/`
- category README files under `scripts/pipeline/`, `scripts/serve/`,
  `scripts/quality/`, `scripts/benchmarks/`, `scripts/sources/`, and
  `scripts/reports/`

Outputs:

- stable script category map
- documented compatibility rule for future moves

Verification:

- Existing command examples should still point to `scripts/<name>.py` or
  `scripts/<name>.sh`.
- If a script is physically moved later, preserve the old path with a wrapper
  and add a focused test or dry run for the old command path.

## Public Rebuild

Use this to run the public/shareable rebuild path while keeping licensed UMLS
inputs local.

Dry-run first:

```sh
python3 scripts/run_public_rebuild.py \
  --umls-meta /path/to/UMLS/META \
  --out-dir build/public \
  --provider hashing \
  --dry-run
```

Run the rebuild:

```sh
python3 scripts/run_public_rebuild.py \
  --umls-meta /path/to/UMLS/META \
  --out-dir build/public \
  --provider hashing
```

Inputs:

- local UMLS META directory with `MRCONSO.RRF`, `MRSTY.RRF`, `MRREL.RRF`,
  `MRDEF.RRF`, and `MRSAB.RRF`
- public source topic/config files under `config/`

Outputs:

- bounded public corpora
- local UMLS-derived SQLite indexes
- linked evidence
- concept documents and vectors
- paragraph quality evaluation
- precision audit
- `build/public/reproducibility_manifest.json`
- `build/public/server_command.txt`

Verification:

- Review the wrapper output.
- Run the server command written to `build/public/server_command.txt`.
- Run paragraph quality and precision audit if the wrapper did not complete
  them for the current path.

## Reproducibility Manifest

Use this before publishing, comparing builds, or explaining which local source
drops were used.

```sh
python3 scripts/reproducibility_manifest.py \
  --umls-meta /path/to/UMLS/META \
  --loinc-dir data/local_sources/loinc/Loinc_2.82 \
  --snomed-zip /path/to/SnomedCT_release.zip \
  --hash-small-files \
  --out build/reproducibility_manifest.json
```

Inputs:

- optional local source paths for licensed inputs
- generated artifacts under `build/`

Outputs:

- `build/reproducibility_manifest.json`

Verification:

- Confirm expected inputs are present.
- Use `--full-hash` only when large artifact hashing is acceptable.

## Source Policy Review

Use this when deciding whether a source belongs in the public rebuild, a private
licensed deployment, or no automated path.

```sh
python3 scripts/evidence_vectors.py reference-source-policy
```

Inputs:

- `config/reference_source_policy.tsv`

Outputs:

- terminal policy report

Verification:

- Restricted clinician references remain excluded from the default public path.
- Private/licensed deployments use local permitted excerpts through explicit
  ingestion paths, not public-source fetch defaults.

## Corpus Acquisition

Use the `fetch-*` commands to materialize public corpus JSONL from upstream
sources.

Common examples:

```sh
python3 scripts/evidence_vectors.py fetch-pubmed-topics \
  --topics config/pubmed_biomedicine_topics.tsv \
  --retmax 500 \
  --out build/pubmed_biomedicine_topics_corpus.jsonl

python3 scripts/evidence_vectors.py fetch-europepmc-topics \
  --topics config/pubmed_biomedicine_topics.tsv \
  --max-records 500 \
  --out build/europepmc_biomedicine_topics_corpus.jsonl

python3 scripts/evidence_vectors.py fetch-pmc-oa-topics \
  --topics config/pubmed_biomedicine_topics.tsv \
  --max-records 200 \
  --out build/pmc_oa_biomedicine_topics_corpus.jsonl

python3 scripts/evidence_vectors.py fetch-clinicaltrials \
  --query 'cancer OR diabetes OR migraine OR sepsis OR pneumonia' \
  --max-records 100 \
  --out build/clinicaltrials_subset_corpus.jsonl

python3 scripts/evidence_vectors.py fetch-medlineplus \
  --max-records 0 \
  --include-spanish \
  --out build/medlineplus_full_corpus.jsonl

python3 scripts/evidence_vectors.py fetch-medlineplus-genetics \
  --max-records 500 \
  --out build/medlineplus_genetics_subset_corpus.jsonl

python3 scripts/evidence_vectors.py fetch-dailymed \
  --drug-name metformin \
  --drug-name pantoprazole \
  --max-labels-per-drug 1 \
  --max-records 20 \
  --out build/dailymed_subset_corpus.jsonl

python3 scripts/evidence_vectors.py fetch-bookshelf-oa \
  --term 'clinical guidelines' \
  --term 'expert panel report' \
  --max-books 3 \
  --max-records 100 \
  --out build/bookshelf_oa_subset_corpus.jsonl

python3 scripts/evidence_vectors.py fetch-obo-ontology \
  --source hpo \
  --out build/hpo_ontology_corpus.jsonl

python3 scripts/evidence_vectors.py fetch-reference-pages \
  --source nci \
  --max-records 25 \
  --out build/nci_reference_pages_corpus.jsonl
```

Inputs:

- topic TSVs under `config/`
- optional API keys for upstream rate limits, such as `NCBI` for E-utilities

Outputs:

- source-specific corpus JSONL files under `build/`

Verification:

- Confirm row counts.
- Confirm source metadata, URLs, identifiers, and license/provenance fields are
  preserved.
- For sources with restricted variants, confirm the public command did not use
  `--allow-restricted-reference-source`.

## PubMed Bulk Acquisition

Use this for bulk PubMed baseline shards rather than repeated topic API calls.

```sh
python3 scripts/evidence_vectors.py download-pubmed-baseline \
  --year 2026 \
  --latest-number 1334 \
  --count 2 \
  --out-dir data/pubmed/baseline \
  --manifest build/pubmed_baseline_download_manifest.json

python3 scripts/evidence_vectors.py ingest-pubmed-baseline \
  --input data/pubmed/baseline/pubmed26n1334.xml.gz data/pubmed/baseline/pubmed26n1333.xml.gz \
  --out build/pubmed_bulk_recent_corpus.jsonl
```

Inputs:

- PubMed baseline XML/XML.GZ files, downloaded locally

Outputs:

- baseline download manifest
- PubMed corpus JSONL

Verification:

- MD5 verification remains enabled unless there is a deliberate reason to pass
  `--no-verify-md5`.
- For pilots, use bounded shard counts and run search-quality review before
  alias promotion.

## Targeted PubMed Weakness Acquisition

Use this before adding more arbitrary PubMed baseline shards. The queue lives in
`config/search_quality_targeted_pubmed_weaknesses.tsv` and starts from judged
query misses, not source availability.

Workflow:

1. Re-run the focused PubMed long-document lane and identify expected CUIs that
   are missing at rank 10.
2. If the expected CUI appears by rank 20 or 60, treat it as a merge/rerank or
   section-linking issue first.
3. If the expected CUI is absent after expanded retrieval, inspect local labels,
   linked evidence, and source snippets before acquiring new PubMed records.
4. Add or relink only the PubMed evidence needed for the benchmarked query and
   expected CUI.
5. Promote the change only when the focused PubMed lane improves and the
   standing smoke, rotating 50-query gate, and patient-portal lane still pass.

Outputs:

- updated target queue or per-query notes
- targeted acquisition summary under
  `build/scaling_runs/targeted_pubmed_weakness_acquisition/`
- focused PubMed and regular smoke-gate verification reports

## One-Source Incremental Build

Use this when adding or refreshing one public source slice without rerunning the
full public rebuild.

```sh
python3 scripts/evidence_vectors.py build-source-subset \
  --source dailymed \
  --drug-name pantoprazole \
  --label-index build/public/indexes/umls_biomedicine_search_label_index.sqlite \
  --mrconso /path/to/UMLS/META/MRCONSO.RRF \
  --out-dir build/public/source_subsets/dailymed_pantoprazole \
  --update-docs build/public/permitted_sources_concept_documents.jsonl \
  --update-vectors build/public/permitted_sources_concept_vectors.hashing.jsonl
```

Inputs:

- source seed arguments
- local label index
- optional MRCONSO for display labels

Outputs:

- source-local corpus, evidence, concept docs, vectors, and manifest
- optional aggregate docs/vectors update

Verification:

- Run a source-specific benchmark from `config/source_benchmarks/` when the
  source has a matching gate.
- Run the normal smoke tier if the source affects active runtime behavior.

## UMLS Identity Indexes

Use this after changing UMLS release files or when building a new local runtime.

```sh
python3 scripts/evidence_vectors.py build-profile-indexes \
  --mrconso /path/to/UMLS/META/MRCONSO.RRF \
  --mrsty /path/to/UMLS/META/MRSTY.RRF \
  --out-dir build/profile_indexes \
  --replace

python3 scripts/evidence_vectors.py build-label-index \
  --mrconso /path/to/UMLS/META/MRCONSO.RRF \
  --mrsty /path/to/UMLS/META/MRSTY.RRF \
  --profile biomedicine \
  --out build/umls_biomedicine_search_label_index.sqlite \
  --replace

python3 scripts/evidence_vectors.py build-code-index \
  --mrconso /path/to/UMLS/META/MRCONSO.RRF \
  --out build/cui_code_index.sqlite \
  --replace

python3 scripts/evidence_vectors.py build-semantic-type-index \
  --mrsty /path/to/UMLS/META/MRSTY.RRF \
  --out build/umls_semantic_types.sqlite \
  --replace
```

Inputs:

- UMLS `MRCONSO.RRF`
- UMLS `MRSTY.RRF`

Outputs:

- `build/profile_indexes/*.sqlite`
- `build/umls_biomedicine_search_label_index.sqlite`
- `build/cui_code_index.sqlite`
- `build/umls_semantic_types.sqlite`

Verification:

- `/api/resolve` can resolve CUIs, labels, and source vocabulary codes when the
  indexes are loaded by the server.

## Evidence Linking

Use this to anchor corpus text to CUIs through UMLS labels.

For a single label index:

```sh
python3 scripts/evidence_vectors.py link-corpus \
  --corpus build/pubmed_corpus.jsonl build/europepmc_corpus.jsonl \
  --label-index build/umls_label_index.sqlite \
  --out build/corpus_evidence.jsonl \
  --matcher trie
```

For semantic profile shards:

```sh
python3 scripts/evidence_vectors.py link-profile-shards \
  --corpus build/pubmed_corpus.jsonl build/europepmc_corpus.jsonl build/dailymed_subset_corpus.jsonl \
  --index-dir build/profile_indexes \
  --out-dir build/profile_evidence \
  --run-name public_corpus \
  --matcher trie \
  --materialize-corpus
```

Inputs:

- corpus JSONL
- label/profile SQLite indexes

Outputs:

- evidence JSONL
- profile-sharded evidence JSONL

Verification:

- Inspect evidence counts by source/profile.
- Confirm ambiguous labels are not over-linked; keep `--max-ambiguity` tight
  unless the run is explicitly exploratory.

## Reviewed Local Evidence

Use this only after manual review has mapped private/query examples to safe
CUIs.

```sh
python3 scripts/evidence_vectors.py ingest-query-log \
  --input /path/to/reviewed_query_log.tsv \
  --out build/query_evidence.jsonl \
  --source local_search_log

python3 scripts/evidence_vectors.py ingest-snippets \
  --input /path/to/reviewed_snippets.tsv \
  --out build/snippet_evidence.jsonl \
  --source reviewed_notes
```

Inputs:

- reviewed TSVs with required `query,cui` or `cui,text`

Outputs:

- evidence JSONL

Verification:

- Do not ingest raw, unreviewed, or identifying real-query exports directly into
  public artifacts.

## Concept Documents

Use this to aggregate evidence rows into CUI/view documents.

```sh
python3 scripts/evidence_vectors.py build-docs-sqlite \
  --evidence build/profile_evidence/*.jsonl \
  --mrconso /path/to/UMLS/META/MRCONSO.RRF \
  --sqlite build/literature_docs.sqlite \
  --replace \
  --out build/literature_concept_documents.jsonl
```

Inputs:

- evidence JSONL
- optional MRCONSO for CUI labels

Outputs:

- concept document JSONL
- optional SQLite work database

Verification:

- Check row counts.
- Spot-check representative CUIs for labels, evidence views, evidence counts,
  and source list.

## Extension Concepts

Use this only when a useful biomedical idea is not represented cleanly by
existing UMLS or local concepts.

```sh
python3 scripts/evidence_vectors.py build-extension-concepts \
  --input config/extension_concepts.new.jsonl \
  --out-docs build/extension_concept_documents.jsonl \
  --out-evidence build/extension_concept_evidence.jsonl \
  --out-registry build/extension_concept_registry.jsonl
```

Inputs:

- reviewed extension concept JSONL

Outputs:

- local `NEW#######` concept documents
- extension evidence
- extension registry

Verification:

- Reject duplicate/synonym-only concepts.
- Preserve broader, related, or close-match anchors when available.
- State clearly if concepts are built but not loaded into the active search
  index.

## Vector Embedding

Use SapBERT/CLS for quality-bearing vectors. Use hashing only for dependency-free
pipeline smoke.

```sh
python3 scripts/evidence_vectors.py embed \
  --docs build/literature_concept_documents.jsonl \
  --out build/literature_concept_vectors.sapbert_cls.jsonl \
  --provider sapbert \
  --local-files-only \
  --max-seq-length 128 \
  --batch-size 32 \
  --omit-text \
  --vector-precision 6
```

Hashing smoke example:

```sh
python3 scripts/evidence_vectors.py embed \
  --docs build/concept_documents.jsonl \
  --out build/concept_vectors.debug.hashing.jsonl \
  --provider hashing \
  --dim 384
```

Inputs:

- concept document JSONL
- optional local model cache for transformer providers

Outputs:

- vector JSONL

Verification:

- Confirm vector dimensions, provider, model, pooling, and text hash metadata.
- Do not treat hashing-vector quality as a semantic search-quality signal.

## Incremental UMLS And Vector Reuse

Use this when moving between UMLS releases or avoiding re-embedding unchanged
documents.

```sh
python3 scripts/evidence_vectors.py build-atom-fingerprints \
  --mrconso /path/to/2025AB/META/MRCONSO.RRF \
  --release 2025AB \
  --out build/incremental/umls_atom_fingerprints_2025AB.tsv

python3 scripts/evidence_vectors.py build-atom-fingerprints \
  --mrconso /path/to/2026AA/META/MRCONSO.RRF \
  --release 2026AA \
  --out build/incremental/umls_atom_fingerprints_2026AA.tsv

python3 scripts/evidence_vectors.py diff-atom-fingerprints \
  --old build/incremental/umls_atom_fingerprints_2025AB.tsv \
  --new build/incremental/umls_atom_fingerprints_2026AA.tsv \
  --old-release 2025AB \
  --new-release 2026AA \
  --out build/incremental/changed_cuis_2025AB_to_2026AA.tsv \
  --summary-out build/incremental/changed_cuis_2025AB_to_2026AA.summary.json

python3 scripts/evidence_vectors.py build-document-manifest \
  --docs build/old_concept_documents.jsonl \
  --release 2025AB \
  --out build/incremental/concept_document_manifest_2025AB.tsv

python3 scripts/evidence_vectors.py plan-vector-reuse \
  --old-manifest build/incremental/concept_document_manifest_2025AB.tsv \
  --new-docs build/new_concept_documents.jsonl \
  --old-vectors build/old_concept_vectors.sapbert_cls.jsonl \
  --old-release 2025AB \
  --new-release 2026AA \
  --out-plan build/incremental/vector_reuse_plan_2025AB_to_2026AA.tsv \
  --out-reused-vectors build/incremental/reused_vectors_2025AB_to_2026AA.jsonl \
  --out-docs-to-embed build/incremental/docs_to_embed_2026AA.jsonl \
  --out-new-manifest build/incremental/concept_document_manifest_2026AA.tsv \
  --require-old-vector-text-hash \
  --summary-out build/incremental/vector_reuse_plan_2025AB_to_2026AA.summary.json

python3 scripts/evidence_vectors.py assemble-incremental-vectors \
  --manifest build/incremental/concept_document_manifest_2026AA.tsv \
  --vectors build/incremental/reused_vectors_2025AB_to_2026AA.jsonl build/incremental/fresh_vectors_2026AA.sapbert_cls.jsonl \
  --expect-provider transformers-cls \
  --expect-model cambridgeltl/SapBERT-from-PubMedBERT-fulltext \
  --expect-pooling cls \
  --expect-dims 768 \
  --require-text-hash \
  --release 2026AA \
  --out build/new_concept_vectors.sapbert_cls.jsonl \
  --summary-out build/incremental/assembled_vectors_2026AA.summary.json
```

Inputs:

- old and new UMLS MRCONSO files
- old/new concept documents
- old vectors

Outputs:

- atom fingerprint TSVs
- changed-CUI TSV and summary
- vector reuse plan
- reused vector JSONL
- docs-to-embed JSONL
- assembled vector JSONL

Verification:

- `assemble-incremental-vectors` must pass strict validation before the vector
  set is considered usable.

## Provenance, Relations, And Definitions

Use these indexes to hydrate search details and related-concept views without
loading all raw evidence into memory.

```sh
python3 scripts/evidence_vectors.py build-provenance-index \
  --evidence build/profile_evidence/*.jsonl \
  --docs build/literature_concept_documents.jsonl \
  --sqlite build/search_quality_provenance.sqlite \
  --sources-per-text 5 \
  --max-document-items 6 \
  --replace

python3 scripts/evidence_vectors.py build-relation-index \
  --mrrel /path/to/UMLS/META/MRREL.RRF \
  --mrconso /path/to/UMLS/META/MRCONSO.RRF \
  --docs build/literature_concept_documents.jsonl \
  --out build/umls_related_concepts.sqlite \
  --max-relations-per-cui 8 \
  --replace

python3 scripts/evidence_vectors.py build-research-relation-index \
  --mrrel /path/to/UMLS/META/MRREL.RRF \
  --mrconso /path/to/UMLS/META/MRCONSO.RRF \
  --mrsty /path/to/UMLS/META/MRSTY.RRF \
  --docs build/literature_concept_documents.jsonl \
  --out build/umls_research_relations.sqlite \
  --max-relations-per-category 12 \
  --replace

python3 scripts/evidence_vectors.py build-definition-index \
  --mrdef /path/to/UMLS/META/MRDEF.RRF \
  --docs build/literature_concept_documents.jsonl \
  --out build/umls_definitions.sqlite \
  --replace

python3 scripts/evidence_vectors.py build-relationship-edge-index \
  --edges config/curated_relationship_edges.jsonl \
  --out build/relationship_edges.sqlite \
  --replace
```

Verification:

- `/api/detail` can hydrate evidence and mappings.
- `/api/related` shows relation and edge categories when indexes are present.

## Elasticsearch Export And Load

Use this to create ANN indexes and aliases for live search.

```sh
python3 scripts/evidence_vectors.py export-elastic \
  --vectors build/literature_concept_vectors.sapbert_cls.jsonl \
  --index qe-literature-sapbert-cls \
  --out-mapping build/qe-literature-sapbert-cls.elastic.mapping.json \
  --out-bulk build/qe-literature-sapbert-cls.elastic.bulk.ndjson \
  --similarity cosine \
  --bulk-docs-per-file 5000

python3 scripts/evidence_vectors.py load-elastic \
  --url http://localhost:9200 \
  --index qe-literature-sapbert-cls \
  --mapping build/qe-literature-sapbert-cls.elastic.mapping.json \
  --bulk build/qe-literature-sapbert-cls.elastic.bulk.ndjson \
  --create-index

python3 scripts/evidence_vectors.py alias-elastic \
  --url http://localhost:9200 \
  --index qe-literature-sapbert-cls \
  --alias qe-scaling-sapbert-cls
```

Verification:

```sh
python3 scripts/evidence_vectors.py search-elastic \
  --url http://localhost:9200 \
  --index qe-scaling-sapbert-cls \
  --query 'pseudomonas aeruginosa wound abscess' \
  --provider sapbert \
  --local-files-only \
  --max-seq-length 128 \
  --k 10 \
  --num-candidates 100
```

Promotion rule:

- Move aliases only after the relevant quality review passes and rollback is
  possible.

## Search API And UI

Use this to serve the local API and browser search UI.

```sh
python3 scripts/search_quality_server.py --port 8766
```

Public-output-only mode:

```sh
python3 scripts/search_quality_server.py --port 8766 --public-output-only
```

Health and status:

```sh
curl -s "http://127.0.0.1:8766/api/health"
curl -s "http://127.0.0.1:8766/api/status"
```

Common API checks:

```sh
curl -s "http://127.0.0.1:8766/api/search?q=No%20evidence%20of%20pulmonary%20embolism&k=5&mode=balanced&include_related=false"
curl -s "http://127.0.0.1:8766/api/detail?cui=C0034065&include_related=true"
curl -s "http://127.0.0.1:8766/api/resolve?q=SNOMED:49436004"
curl -s "http://127.0.0.1:8766/api/related?cui=C0004238&k=10&vocab=ICD10CM"
```

Verification:

- `/api/health` returns `ok: true`.
- `/api/status` reports expected artifact paths and backend.
- Runtime/ranking/API changes also need the relevant smoke command below.

## Standing Clinical Smoke And Regression

Use this as the first live check after runtime search behavior changes.

```sh
python3 scripts/evaluate_search_api.py \
  --queries config/search_quality_clinical_queries.tsv \
  --base-url http://127.0.0.1:8766 \
  --top-k 5
```

For CSV/JSON summary outputs:

```sh
scripts/run_search_regression_benchmark.py config/search_quality_clinical_queries.tsv \
  --base-url http://127.0.0.1:8766 \
  --top-k 10 \
  --rows-out build/search_regression_rows.csv \
  --json-out build/search_regression_summary.json
```

Inputs:

- running API
- query TSV with expected CUIs

Outputs:

- terminal TSV rows, or rows/summary files

Verification:

- Expected CUIs appear within the configured top-k.
- Record any rank-2 or lower expected hits if the row expects top-1 behavior.

## Paragraph Quality Experiment

Use this for release-quality paragraph evaluation and 50-query rotating smoke.

```sh
python3 scripts/run_search_quality_experiment.py \
  --queries config/search_quality_paragraph_queries.tsv \
  --query-limit 50 \
  --query-selection rotate \
  --search-system api \
  --scope umls_evidence \
  --fail-gates
```

Use `--query-limit 0` intentionally for the full judged pool.
Live API runs default to two worker threads; pass `--workers 1` when you need
strict serial timing. UMLS-only in-process runs remain serial.

Inputs:

- running API
- paragraph query TSV

Outputs:

- `build/search_quality_experiments/runs/<run>/`
- metrics JSON
- `query_timings.tsv` with per-query API elapsed time, cache-hit status, backend,
  and hit count
- paragraph quality report
- source-quality summaries
- updated experiment report when configured by the script

Verification:

- Strict success@10 gate.
- No known false positives in the first 10.
- Source-quality summaries reviewed for source drift.

## Patient Portal Benchmark Lane

Use this to gate long patient-portal messages where active/current visit
concepts should rank above copied-forward history while old medications and
diagnoses remain available lower in the result set.

```sh
python3 scripts/run_search_quality_experiment.py \
  --queries config/search_quality_patient_portal_queries.tsv \
  --query-limit 0 \
  --search-system api \
  --scope umls_evidence \
  --run-family patient_portal \
  --label "Patient portal current-versus-history lane" \
  --fail-gates
```

Inputs:

- running API
- `config/search_quality_patient_portal_queries.tsv`

Outputs:

- `build/search_quality_experiments/runs/<run>/`
- metrics JSON
- paragraph quality report
- payloads for portal-lane review

Verification:

- Active/current concepts are visible in the first page.
- Old-history context CUIs remain recoverable lower in the results.
- Configured portal meta/noise disallowed CUIs do not appear in the top 10.
- Runtime ranking changes still need the post-iteration smoke helper.

## Post-Iteration Smoke Helper

Use this after an iteration to choose and run the right verification tier from
the iteration type. The helper writes a JSON summary, a Markdown verification
note, and updates the Post-Iteration Smoke Gates panel in
`docs/search_quality_experiments.html`.

Dry-run the plan:

```sh
python3 scripts/run_search_quality_experiment.py \
  --iteration-smoke-gates \
  --iteration-id SQI-YYYY-MM-DD-NNN \
  --iteration-type ranking \
  --focused-command "python3 -m pytest tests/test_evidence_vectors.py -k '<selector>' -q" \
  --base-url http://127.0.0.1:8766 \
  --dry-run
```

Run the selected checks:

```sh
python3 scripts/run_search_quality_experiment.py \
  --iteration-smoke-gates \
  --iteration-id SQI-YYYY-MM-DD-NNN \
  --iteration-type ranking \
  --focused-command "python3 -m pytest tests/test_evidence_vectors.py -k '<selector>' -q" \
  --base-url http://127.0.0.1:8766
```

Useful flags:

- `--docs-only-change`: record a docs/local-layout decision and skip live smoke
  unless forced.
- `--ui-report-only-change`: record a UI/report-only decision and skip live
  smoke unless forced.
- `--broad-change` or `--release-quality`: force standing and 50-query rotating
  smoke.
- `--static-command`: add syntax/static checks such as `node --check` or
  `py_compile`.
- `--focused-command`: add targeted unit tests or focused rebuild checks before
  live smoke.
- `--force-standing-smoke` and `--force-rotating-smoke`: override the inferred
  tier.
- `--force-patient-portal-smoke` and `--skip-patient-portal-smoke`: override
  the current-versus-history patient portal lane.

Default live-smoke selection:

- `ranking` and `benchmark`: standing clinical smoke, 50-query rotating smoke
  with gates, and the patient portal current-versus-history lane.
- `long-document`: standing clinical smoke plus 50-query rotating smoke with
  gates.
- `source-code`, `data`, and `audit`: standing clinical smoke.
- `process` and `ui`: static/focused checks only, unless another type or force
  flag requires live smoke.

Outputs:

- `build/search_quality_experiments/iteration_smoke_gates/<iteration>/verification.json`
- `build/search_quality_experiments/iteration_smoke_gates/<iteration>/verification.md`
- `build/search_quality_experiments/iteration_smoke_gates.json`
- refreshed `docs/search_quality_experiments.html`

Verification:

- The helper exits nonzero when any selected live or focused command fails.
- Copy the Markdown summary path and headline metrics into the iteration record.

## Focused Paragraph Evaluation And Precision Audit

Use this for targeted failure analysis or full benchmark audit outside the
experiment ledger.

```sh
python3 scripts/evaluate_paragraph_quality.py \
  --queries /path/to/focused_queries.tsv \
  --output-dir build/improvements/<run_name> \
  --top-k 60

python3 scripts/audit_paragraph_precision.py \
  --payloads build/improvements/<run_name>/paragraph_search_payloads.jsonl \
  --output-dir build/improvements/<run_name> \
  --top-n 10
```

Use the full benchmark periodically:

```sh
python3 scripts/evaluate_paragraph_quality.py \
  --output-dir build/improvements/<run_name> \
  --top-k 60
```

Outputs:

- paragraph summaries and payloads
- `paragraph_precision_audit.tsv`
- `paragraph_precision_metrics.json`
- `paragraph_precision_report.md`

Verification:

- Convert reviewed suspect rows into
  `config/search_quality_precision_audit_review.tsv`.
- Regenerate the precision-audit report:

```sh
python3 scripts/build_precision_audit_report.py
```

## Rule Inventory And Active Labels

Use this whenever changing suppression rules, assertion cues, portal language
handling, audit rows, or active-label supplement rows.

```sh
python3 scripts/build_search_rule_inventory.py

python3 scripts/validate_active_label_supplement.py

python3 -m pytest tests/test_evidence_vectors.py -k active_label_supplement -q
```

Inputs:

- ranker/assertion/filter code
- `config/active_label_supplement.tsv`
- precision/useful-extra configs

Outputs:

- `docs/search_rule_inventory.md`
- validation/test results

Verification:

- Every rule class has a clear purpose and a benchmark/audit/test reason.
- Risky labels have context or block guards.

## Canonical Judgments And Shadow Reranker

Use this to keep labels centralized and test ML rank changes without affecting
production ranking.

```sh
python3 scripts/search_quality_shadow_reranker.py run-all
```

Equivalent explicit steps:

```sh
python3 scripts/search_quality_shadow_reranker.py seed-judgments
python3 scripts/search_quality_shadow_reranker.py extract-features
python3 scripts/search_quality_shadow_reranker.py train-shadow
python3 scripts/search_quality_shadow_reranker.py evidence-report
```

To test a reviewed evidence policy as shadow-only features:

```sh
python3 scripts/search_quality_shadow_reranker.py extract-features \
  --evidence-policy build/search_quality_shadow_reranker/evidence_shadow_policy.tsv \
  --out build/search_quality_shadow_reranker/feature_rows.evidence_policy.tsv
python3 scripts/search_quality_shadow_reranker.py train-shadow \
  --features build/search_quality_shadow_reranker/feature_rows.evidence_policy.tsv \
  --out-dir build/search_quality_shadow_reranker/evidence_policy_shadow
```

Inputs:

- expected CUI rows
- useful-extra audit rows
- true false positives
- patient portal rows
- PubMed long-document slice
- saved search payloads

Outputs:

- `config/search_quality_judgments.tsv`
- feature rows under `build/search_quality_shadow_reranker/`
- HTML report comparing current rank vs ML rank
- shadow evidence promotion/demotion TSV, examples TSV, summary JSON, and HTML
  report under `build/search_quality_shadow_reranker/`
- `build/search_quality_shadow_reranker/evidence_shadow_policy.tsv` as a
  review-only policy artifact; runtime ranking does not read it

Verification:

- Review wins, losses, and regressions.
- Treat unjudged evidence rows as unknown, not bad.
- Keep current-capture promotion reports separate from historical negative
  probes when older payloads are needed to surface demotion candidates.
- Promote or demote evidence only after the shadow report shows repeated judged
  signal and the same benchmark slice has no unacceptable regression.
- Do not wire the model into runtime ranking until regressions are triaged and
  live smoke passes.

## PubMed Literature Benchmark

Use this because long biomedical abstracts behave differently from the clinical
paragraph smoke.

Strict seed generation:

```sh
python3 scripts/fetch_pubmed_paragraph_queries.py \
  --topics config/pubmed_paragraph_topics.tsv \
  --curation config/pubmed_literature_abstract_curation.tsv \
  --strict-curation \
  --output-dir build/pubmed_literature_benchmark_seed
```

Focused long-document slice:

```sh
python3 scripts/build_pubmed_long_document_slice.py

PYTHONPATH=src:scripts python3 scripts/run_search_quality_experiment.py \
  --queries build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_queries.tsv \
  --base-url http://127.0.0.1:8766 \
  --scope umls_evidence \
  --search-system api \
  --run-family probe \
  --label "PubMed long-document focused slice"
```

For timing probes, compare `--workers 1` against the default two-worker API
path and inspect the run's `query_timings.tsv`. If summed API response time grows
while wall time stays flat, the next optimization target is server-side search
work rather than runner scheduling.

Candidate expansion:

```sh
python3 scripts/fetch_pubmed_paragraph_queries.py \
  --topics config/pubmed_literature_candidate_topics.tsv \
  --output-dir build/pubmed_literature_candidates
```

Verification:

- Do not score fetched abstracts with inherited topic-level expected CUIs.
- Tune on dev only.
- Keep held-out rows separate from the clinical smoke headline.

## MedMentions Benchmark

Use this as an external linking stress test, separate from internal smoke.

Prepare:

```sh
python3 scripts/run_medmentions_benchmark.py prepare \
  --subset st21pv \
  --split dev \
  --category clinical_useful \
  --query-style mention_only \
  --mention-limit 1000 \
  --document-limit 0 \
  --output-dir build/medmentions/st21pv_dev_clinical_useful_mention_only
```

Evaluate:

```sh
python3 scripts/run_medmentions_benchmark.py evaluate \
  build/medmentions/st21pv_dev_clinical_useful_mention_only/medmentions_st21pv_clinical_useful_mention_only_mention_queries.tsv \
  --base-url http://127.0.0.1:8766 \
  --top-k 10 \
  --scope umls_evidence \
  --linked \
  --limit 100 \
  --output-dir build/medmentions/st21pv_dev_clinical_useful_mention_only/eval_mentions_100
```

Verification:

- Report category-specific metrics.
- Do not optimize suppression-audit surfacing upward.
- Account for UMLS 2017AA vs current-release CUI drift.

## TREC PM/CDS Document-Source Benchmark

Use this as an external document/source retrieval lane, separate from CUI
linking benchmarks. Supply TREC topics and qrels locally; this workflow does not
download track data.

Prepare and report corpus coverage:

```sh
python3 scripts/run_trec_benchmark.py prepare \
  --track precision_medicine \
  --topics data/trec/precision_medicine/topics2019.xml \
  --qrels data/trec/precision_medicine/qrels-treceval-abstracts.2019.txt \
  --qrels data/trec/precision_medicine/qrels-treceval-trials.38.txt \
  --output-dir build/trec/precision_medicine
```

If `--corpus` is omitted, the importer discovers local PubMed, Europe PMC,
PMC OA, and ClinicalTrials.gov corpus artifacts under `build/`. Pass explicit
`--corpus` values when a release run must be pinned to a known corpus set.

Evaluate document/source retrieval:

```sh
python3 scripts/run_trec_benchmark.py evaluate \
  build/trec/precision_medicine/trec_precision_medicine_resolved_document_queries.tsv \
  --base-url http://127.0.0.1:8766 \
  --top-k 10 \
  --scope umls_evidence \
  --output-dir build/trec/precision_medicine/eval
```

Inputs:

- local TREC Precision Medicine or Clinical Decision Support topics
- local TREC qrels
- local PubMed/PMC and ClinicalTrials.gov corpus JSON/JSONL paths
- running API for evaluation only

Outputs:

- normalized topic TSV
- normalized qrels TSV
- corpus coverage TSV and manifest summary
- all-judged-positive document-query TSV for corpus-expansion accounting
- resolved-local judged-positive document-query TSV for retrieval scoring
- evaluation rows, summary, and payloads

Verification:

- Review corpus coverage before scoring retrieval.
- Evaluate document/source retrieval separately from CUI retrieval.
- Treat qrels `relevance > 0` rows as positives.
- Treat unjudged returned documents as unknown, not false positives.
- Run retrieval scoring against an internal/local API that exposes source
  identifiers in hits or evidence items; public-output-only APIs may suppress
  PMID/NCT identifiers and produce zero document/source matches.

## Private Real-Query Workflows

Use this to inspect real query demand without publishing raw terms.

Inventory only:

```sh
python3 scripts/build_real_query_inventory.py
```

Demand-prioritized review queue:

```sh
python3 scripts/build_real_query_inventory.py \
  --sort demand \
  --max-rows 5000 \
  --out build/local_search_logs/query_inventory_demand_top5000.tsv \
  --summary-out build/local_search_logs/query_inventory_demand_top5000_summary.json \
  --review-queue-out build/local_search_logs/query_review_queue.tsv
```

Score a bounded batch:

```sh
python3 scripts/build_real_query_inventory.py \
  --sort demand \
  --max-rows 1000 \
  --score-api \
  --out build/local_search_logs/query_inventory_scored_top1000.tsv \
  --summary-out build/local_search_logs/query_inventory_scored_top1000_summary.json \
  --review-queue-out build/local_search_logs/query_review_queue.tsv
```

UMLS API comparison for private diagnostics:

```sh
python3 scripts/run_private_real_query_diagnostic.py \
  --base-url http://127.0.0.1:8766 \
  --scope umls \
  --api-key "$UMLS_API_KEY"
```

Verification:

- Raw exports remain under `data/local_search_logs/umls_query_exports/`.
- Public configs receive only safe, manually reviewed query/CUI rows.

## Source Acquisition Planning

Use this to turn measured failures into source and relationship-edge review
queues.

```sh
python3 scripts/evidence_vectors.py plan-source-acquisition \
  --quality-summary build/improvements/<run>/paragraph_quality_summary.tsv \
  --out-json build/source_acquisition/plan.json \
  --out-tsv build/source_acquisition/recommendations.tsv \
  --out-associations-tsv build/source_acquisition/association_candidates.tsv \
  --out-association-review-tsv build/source_acquisition/association_review.tsv \
  --out-bundle-dir build/source_acquisition/bundle \
  --out-md build/source_acquisition/plan.md
```

After review:

```sh
python3 scripts/evidence_vectors.py build-reviewed-association-edges \
  --review build/source_acquisition/association_review.tsv \
  --out build/source_acquisition/reviewed_relationship_edges.jsonl
```

Progression ledger:

```sh
python3 scripts/source_acquisition_progression.py \
  --fail-on-regression \
  --out-json build/source_acquisition/progression_manifest.json \
  --out-md build/source_acquisition/progression_report.md
```

Fresh clone inspection:

```sh
python3 scripts/source_acquisition_progression.py \
  --allow-missing-stage-metrics \
  --out-json build/source_acquisition/progression_manifest.json \
  --out-md build/source_acquisition/progression_report.md
```

Verification:

- Approved stages do not regress deterministic gates.
- Rejected diagnostic stages do not lower the next retained gate.

## Weakness-To-Promotion Gate

Use this for every search-quality change, whether the proposed fix is a code
change or newly procured evidence.

The loop is:

1. Determine the weakness from a real query, benchmark miss, audit row, or
   source-code failure.
2. Record the baseline result before changing anything.
3. Choose exactly one route:
   - code route: change parsing, ranking, filtering, source-code output, UI, or
     benchmark handling;
   - evidence route: procure or integrate authoritative, license-compatible
     evidence targeted to the weakness.
4. Rebuild/restart only what the route requires.
5. Re-run the same benchmark slice plus the required smoke tier.
6. Promote only if the target weakness improves and there is no unacceptable
   regression in false positives, assertion status, source policy, code output,
   or held-out/standing smoke.
7. If the route does not improve things, reject it:
   - code route: revert or remove the change before it enters the shipped path;
   - evidence route: exclude the evidence from the default/search-ranking path
     and record the source/query/scope as a rejected acquisition so the same
     procurement is not repeated without a new hypothesis.

Required records:

- For code changes, add or update a search-quality iteration entry with
  `Decision: Keep`, `Decision: Revise`, or `Decision: Revert`.
- For evidence changes, add or update `config/source_acquisition_progression.tsv`
  with `decision_rule` set to `promote`, `no_regression`, or `diagnostic`, and
  `decision` set to `accept`, `neutral`, or `reject`.
- Rejected evidence can remain in `build/` as an audit artifact, but it must not
  be included in the promoted corpus, alias, routing, or default-ranking
  manifest.

Practical rule: do not acquire broad evidence because it seems generally useful.
Acquire evidence only to test a named weakness. If it fails the gate, preserve
the negative result and stop reacquiring that same evidence shape.

## Source Delta Checks

Use this before releasing source rebuilds.

```sh
python3 scripts/check_source_rebuild_delta.py \
  --previous build/source_manifests/previous.json \
  --current build/source_manifests/current.json \
  --out build/source_manifests/source_delta_report.json
```

Verification:

- Source identity, source date/release, fetch date, hash, records fetched,
  records changed, CUI gains/losses, relationship gains/losses, and benchmark
  source changes are present.
- Unexpected source-count collapses block release unless explained and reviewed.

## Relationship Mining

Use this for public/shareable aggregate OHDSI artifacts, not patient-level EHR
data.

```sh
python3 scripts/mine_ohdsi_relationships.py \
  --atlas path/to/cohort_definition.json \
  --cohort-diagnostics path/to/cohort_diagnostics.csv \
  --estimation-results path/to/cohort_method_results.csv \
  --plp-output path/to/plp_feature_importance.csv \
  --literature-study path/to/published_ohdsi_results.csv \
  --omop-cui-map path/to/omop_cui_map.tsv \
  --code-index build/cui_code_index.sqlite \
  --out build/ohdsi_relationship_edges.jsonl \
  --unresolved-out build/ohdsi_unresolved.jsonl \
  --summary-out build/ohdsi_relationship_summary.json

python3 scripts/evidence_vectors.py build-relationship-edge-index \
  --edges build/ohdsi_relationship_edges.jsonl \
  --out build/relationship_edges.sqlite \
  --replace
```

Verification:

- Inputs with patient-level fields such as `person_id`, `visit_occurrence_id`,
  or `note_id` are rejected.
- Quantitative fields stay in provenance/context even when display strength is
  normalized.

## Procedure Bundles

Use this for open/public procedure concepts and relations while keeping CPT out
of public artifacts.

```sh
python3 scripts/build_procedure_bundles.py \
  --input config/procedure_bundles.jsonl \
  --out-concepts build/procedure_bundle_concepts.jsonl \
  --out-relations build/procedure_bundle_relations.jsonl \
  --out-registry build/procedure_bundle_registry.jsonl
```

Verification:

- CPT/CPT4 content is rejected for public bundles.
- SNOMED CT anchors are allowed by default only where the deployment license
  permits them; use `--no-snomed` where needed.

## Enrichment Builders

Use enrichment scripts for targeted add-on slices. These are not substitutes for
primary source evidence or smoke tests.

OpenAlex high-citation evidence:

```sh
python3 scripts/build_openalex_cited_evidence.py \
  --out-dir build/source_acquisition/openalex_missing_high_citation \
  --label-index build/public/indexes/umls_biomedicine_search_label_index.sqlite \
  --semantic-type-index build/public/indexes/umls_semantic_types.sqlite \
  --query-file config/openalex_missing_high_citation_queries.tsv \
  --from-date 2021-05-14 \
  --to-date 2026-05-14 \
  --max-per-query 60 \
  --per-page 60 \
  --min-cited-by-count 500 \
  --articles-tsv build/source_acquisition/openalex_missing_high_citation/articles.tsv
```

Other targeted builders:

```sh
python3 scripts/build_drug_enrichment.py
python3 scripts/build_wikipedia_enrichment.py
python3 scripts/build_open_image_enrichment.py
```

Verification:

- Review generated manifests and source metadata.
- Keep OpenAlex and image outputs as enrichment/metadata unless they are
  explicitly linked to source-quality claims by a benchmark.

## Reports And Dashboards

Use these to regenerate static operational reports.

```sh
python3 scripts/build_source_evidence_dashboard.py

python3 scripts/scaling_status.py \
  --plan config/full_pipeline.plan.json \
  --out-json build/scaling_runs/full_pipeline/progress.json \
  --out-markdown build/scaling_runs/full_pipeline/progress.md

python3 scripts/reconcile_pubmed_shard_reviews.py

python3 scripts/build_translation_benchmark_report.py
```

Inputs:

- local artifacts under `build/`
- plan JSONs under `config/`
- translation lock `config/translation_benchmark_lock.json`

Outputs:

- `docs/source_evidence_dashboard.html`
- progress JSON/Markdown
- PubMed shard review/export reconciliation JSON/Markdown
- `docs/translation_benchmark_report.html`
- report-specific JSON outputs when configured

Verification:

- Run static syntax checks for embedded JavaScript when editing HTML reports.
- For recent PubMed shard gates, require row-level
  `search_quality_judgments.csv` files before marking quality-review steps
  complete. Aggregate `search_quality_summary.json` files are not enough to
  reconstruct reviewed row judgments.
- Treat load markers without matching Elasticsearch mapping/bulk export
  artifacts as reconciliation findings that must be restored or regenerated
  before broader ingest/release decisions.
- Treat generated reports as snapshots of current local artifacts; do not assume
  a fresh clone has all historical `build/` inputs.

## Translation And Gold-Standard Comparison

Use this when comparing the current search API against locked translation slices
or UMLS API behavior.

```sh
python3 scripts/compare_to_gold_standard.py \
  --base-url http://127.0.0.1:8766

python3 scripts/compare_umls_api.py \
  --base-url http://127.0.0.1:8766 \
  --api-key "$UMLS_API_KEY"
```

Verification:

- Keep clinical smoke, PubMed literature, exact/UMLS API comparison, and code
  mapping coverage as separate slices.
- Do not tune held-out rows from row-level misses without moving affected
  examples into a new dev iteration and replacing the held-out row.

## New-UMLS Existing-Data Iteration

Use this for bounded iterations that create or evaluate local `NEW#######`
concept candidates using existing artifacts.

```sh
python3 scripts/run_existing_data_iteration.py \
  --iteration iteration_003_search_quality \
  --out-dir build/new_umls_iterations/iteration_003_search_quality
```

Inputs:

- current UMLS indexes
- local LOINC path when supplied at `data/local_sources/loinc/Loinc_2.82`
- prior extension concepts
- query/evidence/source artifacts

Outputs:

- iteration manifest
- candidate review
- promoted/deferred concept records
- relation artifacts
- iteration report

Verification:

- Each iteration has one primary purpose.
- Search-quality iterations run the required smoke tier before being marked
  shipped unless the report records a blocker or a docs-only/local-layout
  exception.

## Iteration Records

Create or update an iteration record when a change is meant to affect
search-quality behavior, benchmark labels, source-code output, ranking,
judgments, source acquisition, release gates, or the process itself.

For each entry, record:

- trigger
- expected behavior
- what changed
- artifacts
- verification
- decision
- next bounded step

Primary files:

- `docs/search_quality_iterations.md`
- `docs/search_quality_iterations.html`

Verification:

- Markdown entry and HTML entry agree.
- HTML inline JavaScript parses after edits.
- Docs-only/process entries record why no live smoke was needed.

## Documentation Maintenance

When a process changes, update the nearest specialized doc and this report in
the same change. Also update `docs/explain_like_im_5.md` when the user-facing
mental model changes, a new canonical artifact appears, or the current status
changes.

Useful checks:

```sh
rg -n "new command or artifact name" docs README.md scripts config
node --check /tmp/search_quality_iterations_inline.js
python3 -m py_compile scripts/<changed_script>.py
python3 -m pytest <targeted_tests> -q
```

Docs-only verification is static review and syntax checks. Live search smoke is
not needed unless the docs change is coupled to runtime behavior, labels,
ranking, benchmarks, judgments, or API output.
