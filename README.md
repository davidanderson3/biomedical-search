# UMLS Semantic Evidence Index

This project is an evidence-backed semantic retrieval layer over biomedical
concepts. It uses UMLS CUIs as the stable concept backbone, then adds searchable
context from PubMed, Europe PMC, PMC Open Access, and other permitted biomedical
evidence.

The goal is to make CUI lookup more useful for real biomedical language:
provenance-rich, evaluable, reproducible, and responsive to new evidence while
preserving source vocabulary identifiers and local licensing boundaries.

The basic idea is:

1. Keep UMLS CUIs as the concept identity layer.
2. Collect real-world prose from PubMed, Europe PMC, PMC Open Access, and
   similar permitted corpora.
3. Use high-precision UMLS label matches to anchor corpus contexts to CUIs.
4. Build multiple evidence views per CUI instead of one centroid.
5. Embed those views with biomedical BERT models and index the vectors.
6. Return CUIs with evidence, source provenance, and quality judgments.
7. Release reproducible vector/index/evidence manifests that can be updated in
   bounded deltas.

## Architecture Goals

The release artifact should be a **semantic evidence index for UMLS CUIs**. The
core product is not another synonym file; it is a ranked retrieval layer that
understands biomedical language as it appears in literature and clinical text.

Release-grade artifacts should include:

- CUI/view embedding packs, currently SapBERT/CLS vectors.
- Elasticsearch/OpenSearch/ANN index exports.
- Evidence-to-CUI provenance pointers, such as PMID, PMCID, DOI, source, matched
  UMLS label, and evidence weight.
- Public benchmark query sets with relevance judgments.
- Build manifests with UMLS release, corpus snapshot, model name, pooling
  method, counts, and file hashes.
- Delta packs for new or changed evidence and re-embedded CUI views.

Restricted or credentialed clinical corpora should remain separate from public
literature artifacts and should never redistribute raw clinical text.

For external rebuilds and artifact boundaries, see
[Reproducibility Guide](docs/reproducibility.md). It separates public/shareable
artifacts from licensed/local inputs such as UMLS, LOINC, SNOMED CT, external
CUI vectors, and any credentialed clinical data.

For a fresh clone workflow, see [GitHub Quickstart](docs/github_quickstart.md).
It covers public dependencies, dry-run rebuild planning, required local UMLS
files, missing high-citation article acquisition, and the difference between
historical local progression reports and strict local validation.
Use `requirements-public.txt` for the standard-library public build path and
`requirements-dev.txt` when you want to run the pytest checks.

For the HTTP contract used by external clients and the browser UI, see
[Biomedical Concept Search API](docs/api.md). The server also exposes a
machine-readable OpenAPI document at `/api/openapi.json`.

## Attribution And Licensing

This project uses UMLS CUIs as concept identifiers and may use locally supplied
UMLS-derived indexes under the user's UMLS license. Licensed vocabularies such
as SNOMED CT, LOINC, RxNorm, and other local source files should only be used
and redistributed where the deployment has the necessary rights.

Public evidence and enrichment may come from
[NCBI E-utilities for PubMed and PMC](https://www.ncbi.nlm.nih.gov/books/NBK25497/),
[Europe PMC](https://europepmc.org/),
[ClinicalTrials.gov](https://clinicaltrials.gov/data-api/api),
[MedlinePlus](https://medlineplus.gov/xml.html),
[MedlinePlus Genetics](https://medlineplus.gov/genetics/),
[DailyMed](https://dailymed.nlm.nih.gov/dailymed/),
[NCBI Bookshelf / NLM LitArch Open Access](https://www.ncbi.nlm.nih.gov/books/about/openaccess/),
[NCI](https://www.cancer.gov/policies/copyright-reuse),
[CDC](https://www.cdc.gov/other/agencymaterials.html),
[FDA](https://www.fda.gov/about-fda/about-website/website-policies),
[NIDDK](https://www.niddk.nih.gov/copyright),
[Human Phenotype Ontology](https://human-phenotype-ontology.github.io/license.html),
[Mondo Disease Ontology](https://monarch-initiative.github.io/monarch-documentation/Repositories/mondo/),
[OpenAlex](https://developers.openalex.org/api-reference/introduction),
and open Wikipedia/Wikimedia content when compatible with the source license.
Images retain per-file source and license metadata where available.

Clinician reference sites such as Merck/MSD Manual Professional, AAFP,
Medscape, BMJ Best Practice, NICE CKS, StatPearls on NCBI Bookshelf,
Patient.info Professional Reference, GPnotebook, and WikEM are tracked as useful
candidate sources. They are excluded from the public rebuild unless a deployment
supplies licensed/permitted content locally and can satisfy the source-specific
reuse, automated-access, attribution, and derivative-artifact terms. See
`config/reference_source_policy.tsv` and:

```sh
python3 scripts/evidence_vectors.py reference-source-policy
```

SNOMED CT content is subject to the
[NLM SNOMED CT Affiliate License Agreement](https://www.nlm.nih.gov/research/umls/knowledge_sources/metathesaurus/release/license_agreement_snomed.html).
LOINC content, when present, is copyrighted by Regenstrief Institute, Inc. and
the LOINC Committee and is governed by the
[LOINC license](https://loinc.org/kb/license/).

The public-first rebuild entrypoint is:

```sh
python3 scripts/run_public_rebuild.py \
  --umls-meta /path/to/UMLS/META \
  --out-dir build/public \
  --provider hashing
```

The rebuild fetches bounded public subsets and links them through multiword
semantic-profile shards by default. When a standalone permitted-source pack is
also present, the search server loads
`build/public/permitted_sources_concept_documents.jsonl` and
`build/public/permitted_sources_concept_vectors.hashing.jsonl` automatically.
Use `--dry-run` first on a fresh clone to print the full command plan without
network calls or file writes.

## Data Model

Evidence is stored as JSONL:

```json
{"evidence_id":"...","cui":"C0004238","text":"a fib","source":"local_search_log","evidence_type":"failed_query","weight":12.0,"metadata":{"baseline_rank":"99"}}
```

Concept documents are also JSONL:

```json
{"doc_id":"C0004238:query_language","cui":"C0004238","view":"query_language","text":"...","evidence_count":3,"sources":["local_search_log"],"labels":["Atrial Fibrillation"]}
```

Vectors are JSONL:

```json
{"doc_id":"C0004238:query_language","cui":"C0004238","view":"query_language","vector":[0.01,...],"text":"...","metadata":{...}}
```

## Commands

Most ingestion, linking, aggregation, and export commands use the Python
standard library. Semantic embedding requires `torch` and `transformers`; the
preferred current model is `cambridgeltl/SapBERT-from-PubMedBERT-fulltext` with
CLS pooling.

### 1. Fetch or ingest real-world corpus text

#### PubMed abstracts

Uses NCBI E-utilities `ESearch` followed by `EFetch`. The fetcher uses the
`NCBI` environment variable as the E-utilities `api_key` by default, with
`APIKEY` as a fallback for shells that already export the NCBI key under that
name.

```sh
python3 scripts/evidence_vectors.py fetch-pubmed \
  --term 'atrial fibrillation OR diabetes mellitus' \
  --retmax 500 \
  --out build/pubmed_corpus.jsonl
```

The data is returned directly to `--out`. `--email` is optional NCBI contact
metadata only; it is not used for delivery.

For broader harvesting, use a topic TSV with `topic`, `term`, and optional
`retmax` columns. PMIDs are de-duplicated across topics and the topic is retained
in each document's metadata:

```sh
python3 scripts/evidence_vectors.py fetch-pubmed-topics \
  --topics config/pubmed_biomedicine_topics.tsv \
  --retmax 500 \
  --out build/pubmed_biomedicine_topics_corpus.jsonl
```

#### Europe PMC abstracts

This uses the Europe PMC article search API as a literature source. It does not
use Europe PMC/UMLS vocabulary annotations as synonym sources.

```sh
python3 scripts/evidence_vectors.py fetch-europepmc \
  --query 'atrial fibrillation OR diabetes mellitus' \
  --max-records 500 \
  --out build/europepmc_corpus.jsonl
```

The same topic TSV used for PubMed can be used for Europe PMC:

```sh
python3 scripts/evidence_vectors.py fetch-europepmc-topics \
  --topics config/pubmed_biomedicine_topics.tsv \
  --max-records 500 \
  --out build/europepmc_biomedicine_topics_corpus.jsonl
```

When multiple corpus files are linked together, records are de-duplicated by
document id, PMID, PMCID, DOI, and normalized title. Put PubMed first when you
want overlapping PubMed/Europe PMC abstracts to retain `source=pubmed`.

#### PMC Open Access full text

This uses NCBI E-utilities with `db=pmc` and automatically adds
`open_access[filter]`. The result is full-text PMC Open Access articles in the
same corpus JSONL shape used by PubMed and Europe PMC. Downstream evidence rows
retain `source=pmc_oa`, PMCID/PMID/DOI, license metadata when present, and a PMC
article URL.

```sh
python3 scripts/evidence_vectors.py fetch-pmc-oa \
  --query 'sepsis OR pneumonia OR urinary tract infection' \
  --max-records 200 \
  --out build/pmc_oa_corpus.jsonl
```

The same topic TSV used for PubMed can be used for PMC OA. Rows are de-duplicated
by PMCID/PMID/DOI across topics:

```sh
python3 scripts/evidence_vectors.py fetch-pmc-oa-topics \
  --topics config/pubmed_biomedicine_topics.tsv \
  --max-records 200 \
  --out build/pmc_oa_biomedicine_topics_corpus.jsonl
```

#### ClinicalTrials.gov subset

ClinicalTrials.gov adds structured trial language for conditions,
interventions, eligibility criteria, outcomes, and study populations. Treat it
as trial-design evidence, not as proof that an intervention works.

```sh
python3 scripts/evidence_vectors.py fetch-clinicaltrials \
  --query 'cancer OR diabetes OR migraine OR sepsis OR pneumonia' \
  --max-records 100 \
  --out build/clinicaltrials_subset_corpus.jsonl
```

#### MedlinePlus health topic snapshot

MedlinePlus XML adds patient-facing phrasing, lay synonyms, topic groupings, and
consumer health language. Use `--max-records 0` for the full discovered
MedlinePlus health-topic XML/ZIP feed, and `--include-spanish` when the snapshot
should include Spanish health topics as well as English topics.

```sh
python3 scripts/evidence_vectors.py fetch-medlineplus \
  --max-records 0 \
  --include-spanish \
  --out build/medlineplus_full_corpus.jsonl
```

#### MedlinePlus Genetics subset

MedlinePlus Genetics adds gene, genetic condition, chromosome, inheritance,
synonym, and related-condition language. Keep it bounded for public smoke builds
and expand when you want broader genetics coverage.

```sh
python3 scripts/evidence_vectors.py fetch-medlineplus-genetics \
  --max-records 500 \
  --out build/medlineplus_genetics_subset_corpus.jsonl
```

#### DailyMed drug label subset

DailyMed adds structured public drug-label language for indications, dosage,
contraindications, warnings, adverse reactions, drug interactions, populations,
and clinical pharmacology. Keep this bounded by drug names or SPL set IDs. If
you already have UMLS locally, DailyMed SPL set IDs can also be extracted from
`MRSAT.RRF`.

```sh
python3 scripts/evidence_vectors.py fetch-dailymed \
  --drug-name metformin \
  --drug-name pantoprazole \
  --drug-name osimertinib \
  --max-labels-per-drug 1 \
  --max-records 20 \
  --out build/dailymed_subset_corpus.jsonl
```

#### NCBI Bookshelf Open Access subset

Bookshelf contains many traditionally copyrighted books, so the public fetcher
uses only the NLM LitArch Open Access subset and its FTP file list. Licenses vary
by package; generated corpus records retain the package license text, archive
path, accession ID, publisher, and source URL.

```sh
python3 scripts/evidence_vectors.py fetch-bookshelf-oa \
  --term 'clinical guidelines' \
  --term 'expert panel report' \
  --max-books 3 \
  --max-records 100 \
  --out build/bookshelf_oa_subset_corpus.jsonl
```

#### OBO ontology subsets

HPO and MONDO are handled as structured OBO sources rather than scraped
reference pages. The fetcher preserves term identifiers, labels, definitions,
synonyms, xrefs, parent IDs, relationship text, source license, and source
version metadata.

```sh
python3 scripts/evidence_vectors.py fetch-obo-ontology \
  --source hpo \
  --out build/hpo_ontology_corpus.jsonl
```

The public rebuild can also augment the research relation index with staged HPO
annotation files under `data/external/hpo/` when
`--include-hpo-research-relations` is supplied. Those files add
disease-phenotype, gene-phenotype, disease-gene, and gene-disease links that are
not recoverable from UMLS alone. Treat Orphanet coverage as UMLS/source-code
crosswalk coverage rather than a separate fetch target; review HPO annotation
and upstream OMIM/Orphanet reuse terms before redistributing derived relation
artifacts.

#### Reference page subsets

The public rebuild can also fetch small, attributable subsets from reusable
government reference pages. This covers some of the same practical diagnostic
ground as Merck/MSD, AAFP, and Medscape without pulling copyrighted reference
articles into public artifacts.

```sh
python3 scripts/evidence_vectors.py fetch-reference-pages \
  --source nci \
  --max-records 25 \
  --out build/nci_reference_pages_corpus.jsonl
```

Supported source policy keys are `nci`, `cdc`, `fda`, `niddk`,
`ncbi_bookshelf_oa`, `hpo`, `mondo`, `merck_manual_professional`,
`msd_manual_professional`, `aafp`, `medscape`, `bmj_best_practice`, `nice_cks`,
`ncbi_bookshelf_statpearls`, `patient_info_professional`, `gpnotebook`, and
`wikem`. Only `nci`, `cdc`, `fda`, and `niddk` are default public
reference-page sources; `ncbi_bookshelf_oa` uses the dedicated
`fetch-bookshelf-oa` command, and `hpo`/`mondo` use `fetch-obo-ontology`
instead of HTML page fetching. The restricted keys are blocked by default; use
them only for private/licensed deployments, and prefer locally supplied permitted
excerpts through `ingest-tabular-corpus`.

#### Incremental source subset build

For one-source additions, use `build-source-subset` instead of rerunning the full
public rebuild. It fetches the bounded source subset, assigns CUIs with the local
MRCONSO-backed label index, writes source-specific corpus/evidence/docs/vectors,
and can upsert the resulting docs/vectors into aggregate JSONL files.

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

Search responses include per-response `source_contributions` and
`source_bundle_contributions`. Add `debug=1` to `/api/search` to include
`vector_path`, `vector_row`, and retrieval lineage for each returned hit.

#### Measured source acquisition plan

Use measured paragraph-quality output to decide which source slices, labels, or
relationship edges to acquire next. The planner joins query specs to recover
expected CUIs, infers review-only candidate false positives from top-ranked
non-expected hits, and filters expected-CUI association pairs against existing
relation indexes when those SQLite files are available. It also emits a ranked
association-candidate queue. All recommendation scores use measured gap weight
plus a bounded prevalence/commonness multiplier; pair candidates additionally use
relation clarity, sourceability, and text proximity so common conditions, lab
tests, procedures, and drugs are reviewed early. The command automatically loads
`config/source_acquisition_prevalence_priors.tsv` when present; pass
`--prevalence-prior <tsv>` to add another prior or
`--no-default-prevalence-prior` to rely only on heuristic commonness. When
`build/umls_biomedicine_search_label_index.sqlite` exists, it is used by default
for acquisition labeling because measured source builds need broad drug, gene,
condition, lab, procedure, and synonym coverage.

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

`--out-bundle-dir` writes the plan plus source seed TSVs, literature topic TSVs,
review templates, and a command checklist for the highest-utility acquisition
actions.

To make acquisition progressions reproducible, record each tested stage in
`config/source_acquisition_progression.tsv` and regenerate the progression
manifest/report:

```sh
python3 scripts/source_acquisition_progression.py --fail-on-regression
```

The progression command inventories all listed artifacts, hashes small files,
compares each stage to the previous retained stage in its group, and fails if
an incremental gate regresses recall or adds top-ranked disallowed concepts.
Rejected diagnostic stages are recorded without lowering the next gate. It
writes `build/source_acquisition/progression_manifest.json` and
`build/source_acquisition/progression_report.md`.

On a fresh clone before historical `build/` artifacts exist, inspect the ledger
without failing on missing local metrics:

```sh
python3 scripts/source_acquisition_progression.py --allow-missing-stage-metrics
```

After review, approved rows can be converted into relationship-edge JSONL:

```sh
python3 scripts/evidence_vectors.py build-reviewed-association-edges \
  --review build/source_acquisition/association_review.tsv \
  --out build/source_acquisition/reviewed_relationship_edges.jsonl
```

### 2. Build a UMLS label index

This index is used only for anchoring real-world text spans to CUIs. You can keep
it broad, or restrict by semantic type to reduce ambiguous matches and runtime.

```sh
python3 scripts/evidence_vectors.py build-label-index \
  --mrconso /path/to/UMLS/META/MRCONSO.RRF \
  --mrsty /path/to/UMLS/META/MRSTY.RRF \
  --semantic-type 'Disease or Syndrome' \
  --semantic-type 'Sign or Symptom' \
  --semantic-type T047 \
  --replace \
  --out build/umls_label_index.sqlite
```

For broad biomedical coverage, prefer semantic-profile shards over one giant
untyped matcher:

```sh
python3 scripts/evidence_vectors.py list-semantic-profiles

python3 scripts/evidence_vectors.py build-label-index \
  --mrconso /path/to/UMLS/META/MRCONSO.RRF \
  --mrsty /path/to/UMLS/META/MRSTY.RRF \
  --profile clinical \
  --min-tokens 2 \
  --replace \
  --out build/umls_clinical_profile_multiword_label_index.sqlite

python3 scripts/evidence_vectors.py build-label-index \
  --mrconso /path/to/UMLS/META/MRCONSO.RRF \
  --mrsty /path/to/UMLS/META/MRSTY.RRF \
  --profile chemicals-drugs \
  --min-tokens 2 \
  --replace \
  --out build/umls_chemicals_drugs_profile_multiword_label_index.sqlite
```

To build the default production shards for biomedicine in one pass:

```sh
python3 scripts/evidence_vectors.py build-profile-indexes \
  --mrconso /path/to/UMLS/META/MRCONSO.RRF \
  --mrsty /path/to/UMLS/META/MRSTY.RRF \
  --out-dir build/profile_indexes \
  --replace
```

Available profiles are:

- `clinical`
- `chemicals-drugs`
- `genes-proteins`
- `anatomy`
- `procedures-devices`
- `organisms`
- `labs-measurements`
- `all-biomedicine`

`all-biomedicine` is unrestricted English MRCONSO coverage. It is useful for
experiments, but for production-scale linking the profile shards are usually
cleaner because broad UMLS labels include many generic concepts.

Build a separate CUI/code resolver index from MRCONSO when the search surface
needs to accept CUIs and source vocabulary codes before semantic ANN search:

```sh
python3 scripts/evidence_vectors.py build-code-index \
  --mrconso /path/to/UMLS/META/MRCONSO.RRF \
  --out build/cui_code_index.sqlite \
  --replace
```

The resolver index stores `cui`, `sab`, `code`, `scui`, `sdui`, `tty`, `label`,
`ispref`, and `suppress`. The assessment server can then resolve inputs such as
`C0004238`, `ICD10CM:I48.91`, or unqualified code-like strings before embedding
normal text queries.

### 3. Link corpus contexts to CUIs

This scans corpus documents, finds exact normalized UMLS label matches, and emits
context windows as evidence. Ambiguous labels are skipped by default unless the
number of matching CUIs is within `--max-ambiguity`.

```sh
python3 scripts/evidence_vectors.py link-corpus \
  --corpus build/pubmed_corpus.jsonl build/europepmc_corpus.jsonl build/pmc_oa_corpus.jsonl build/clinicaltrials_subset_corpus.jsonl build/medlineplus_subset_corpus.jsonl build/medlineplus_genetics_subset_corpus.jsonl build/dailymed_subset_corpus.jsonl build/bookshelf_oa_subset_corpus.jsonl \
  --label-index build/umls_label_index.sqlite \
  --out build/corpus_evidence.jsonl \
  --matcher trie
```

Use `--matcher trie` for large corpora. It loads the label index once and scans
each document token stream, avoiding per-span SQLite lookups.

For broad biomedical linking, prefer running the same corpus through each
multiword profile shard and tagging the output evidence by profile:

```sh
python3 scripts/evidence_vectors.py link-profile-shards \
  --corpus build/pubmed_corpus.jsonl build/europepmc_corpus.jsonl build/medlineplus_subset_corpus.jsonl build/dailymed_subset_corpus.jsonl build/bookshelf_oa_subset_corpus.jsonl \
  --index-dir build/profile_indexes \
  --out-dir build/profile_evidence \
  --run-name public_corpus \
  --matcher trie \
  --materialize-corpus
```

This writes one JSONL file per profile, such as
`pubmed_europepmc_clinical_evidence.jsonl` and
`pubmed_europepmc_chemicals_drugs_evidence.jsonl`. Evidence types are also
tagged, for example `pubmed_clinical_context`, so document building can preserve
separate clinical, drug, anatomy, organism, procedure, gene/protein, and
lab/measurement views.

### 4. Optional: ingest manually reviewed evidence

Input TSV needs `query` and `cui`. Optional columns include `count`, `weight`,
`baseline_rank`, `clicked`, `source`, and `note`.

```sh
python3 scripts/evidence_vectors.py ingest-query-log \
  --input examples/query_log.tsv \
  --out build/query_evidence.jsonl \
  --source local_search_log
```

### 5. Optional: ingest reviewed snippets

Input TSV needs `cui` and `text`. Optional columns include `source`,
`evidence_type`, `weight`, and `note`.

```sh
python3 scripts/evidence_vectors.py ingest-snippets \
  --input examples/snippets.tsv \
  --out build/snippet_evidence.jsonl \
  --source reviewed_notes
```

### 6. Build concept evidence documents

MRCONSO labels are used only as anchors for evidence-bearing CUIs.

```sh
python3 scripts/evidence_vectors.py build-docs \
  --evidence build/corpus_evidence.jsonl build/snippet_evidence.jsonl \
  --mrconso /path/to/UMLS/META/MRCONSO.RRF \
  --out build/concept_documents.jsonl
```

For larger evidence sets, use the SQLite-backed builder instead of the in-memory
builder:

```sh
python3 scripts/evidence_vectors.py build-docs-sqlite \
  --evidence build/pubmed_corpus_evidence.jsonl build/europepmc_corpus_evidence.jsonl build/pmc_oa_corpus_evidence.jsonl \
  --mrconso /path/to/UMLS/META/MRCONSO.RRF \
  --sqlite build/literature_docs.sqlite \
  --replace \
  --out build/literature_concept_documents.sqlite.jsonl
```

The builder emits separate views such as `pubmed_context`,
`europepmc_context`, `pmc_oa_context`, `query_language`, and `prose_evidence`
instead of forcing all evidence into one centroid. That usually gives better
retrieval because literature language, open full-text prose, and user queries
can be very different.

### 7. Embed documents

For quality testing and Elasticsearch indexing, use a biomedical BERT model. The
preferred local path is SapBERT with CLS pooling, not a generic mean-pooled
SentenceTransformer wrapper:

```sh
python3 scripts/evidence_vectors.py embed \
  --docs build/scaling_chunk_001_gap_topics_concept_documents.jsonl \
  --out build/scaling_chunk_001_gap_topics_concept_vectors.sapbert_cls.jsonl \
  --provider sapbert \
  --local-files-only \
  --max-seq-length 128 \
  --batch-size 32 \
  --omit-text \
  --vector-precision 6
```

This uses `cambridgeltl/SapBERT-from-PubMedBERT-fulltext` by default and stores
`embedding_pooling=cls` in vector metadata. The concept document JSONL remains
the source of truth for text. The vector JSONL keeps `doc_id`, `cui`, `view`,
labels, sources, evidence count, `document_text_hash`, and the vector. The
text hash proves which source text was embedded even when `--omit-text` is set.
Use
`--include-document-metadata` only for debugging because it makes vector and
Elasticsearch bulk files much larger.

For a dependency-free smoke test only:

```sh
python3 scripts/evidence_vectors.py embed \
  --docs build/concept_documents.jsonl \
  --out build/concept_vectors.debug.hashing.jsonl \
  --provider hashing \
  --dim 384
```

The `hashing` provider is not a semantic model and should not be used for search
quality decisions.

The `embed` command streams document JSONL and writes vectors batch-by-batch; use
`--batch-size` to control memory and model throughput. You can run other BERTs
with the same CLS-pooling backend:

```sh
python3 scripts/evidence_vectors.py embed \
  --docs build/concept_documents.jsonl \
  --out build/concept_vectors.pubmedbert_cls.jsonl \
  --provider transformers-cls \
  --model microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract \
  --local-files-only
```

Use `--local-files-only` when you want a cached model run and do not want the
Hugging Face client to attempt downloads.

For faster iteration, run a bounded BERT pass before committing to a full
embedding run:

```sh
python3 scripts/evidence_vectors.py embed \
  --docs build/biomedicine_scaled_top12_concept_documents.jsonl \
  --out build/biomedicine_scaled_top12_sapbert_first5k_vectors.jsonl \
  --provider sapbert \
  --local-files-only \
  --max-seq-length 128 \
  --max-docs 5000
```

`--sample-docs` gives a reproducible random sample. `--max-docs` is useful for a
fast ordered prefix chunk. `--max-seq-length` keeps local transformer runs from
spending CPU on text that would be truncated anyway.

### 8. Reuse unchanged SapBERT vectors

For UMLS release updates, avoid re-embedding unchanged concept documents. Build
a manifest for the previous document set, plan reuse against the new document
set, embed only `docs_to_embed_*.jsonl`, and then assemble the final vector set
with manifest validation:

```sh
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
  --vectors \
    build/incremental/reused_vectors_2025AB_to_2026AA.jsonl \
    build/incremental/fresh_vectors_2026AA.sapbert_cls.jsonl \
  --expect-provider transformers-cls \
  --expect-model cambridgeltl/SapBERT-from-PubMedBERT-fulltext \
  --expect-pooling cls \
  --expect-dims 768 \
  --require-text-hash \
  --release 2026AA \
  --out build/new_concept_vectors.sapbert_cls.jsonl \
  --summary-out build/incremental/assembled_vectors_2026AA.summary.json
```

`--require-old-vector-text-hash` keeps reuse conservative: old vectors without
proof of the previous manifest text are sent back through embedding.
`assemble-incremental-vectors` is strict: it fails on missing, duplicate,
unknown, or stale `doc_id`/`cui`/`view` records before writing the final vector
JSONL. It also rejects empty vectors, mixed dimensions, and mixed embedding
provider/model/pooling metadata so hashing or non-SapBERT shards cannot be
silently combined with SapBERT output. `--require-text-hash` requires every
vector to prove it was embedded from the manifest text, even when vector text is
omitted. With `--summary-out`, validation failures still write diagnostic
samples.

### 9. Test retrieval locally

```sh
python3 scripts/evidence_vectors.py search \
  --vectors build/scaling_chunk_001_gap_topics_concept_vectors.sapbert_cls.jsonl \
  --query "a fib" \
  --provider sapbert \
  --local-files-only \
  --max-seq-length 128 \
  --top-k 10
```

The local `search` command streams vector JSONL and keeps only the best score per
CUI in memory. It is still a validation tool, not a replacement for a production
ANN index.

### 10. Export vectors for Elasticsearch kNN

Export a mapping with a `dense_vector` field plus bulk NDJSON. For large exports,
split the bulk payload into part files:

```sh
python3 scripts/evidence_vectors.py export-elastic \
  --vectors build/scaling_chunk_001_gap_topics_concept_vectors.sapbert_cls.jsonl \
  --index qe-scaling-chunk-001-gap-topics-sapbert-cls \
  --out-mapping build/qe-scaling-chunk-001-gap-topics-sapbert-cls.elastic.mapping.json \
  --out-bulk build/qe-scaling-chunk-001-gap-topics-sapbert-cls.elastic.bulk.ndjson \
  --similarity cosine \
  --bulk-docs-per-file 5000
```

Load into Elasticsearch:

```sh
curl -X PUT 'http://localhost:9200/qe-concept-vectors' \
  -H 'Content-Type: application/json' \
  --data-binary @build/qe-concept-vectors.elastic.mapping.json

for f in build/qe-concept-vectors.elastic.bulk.part-*.ndjson; do
  curl -X POST 'http://localhost:9200/_bulk' \
    -H 'Content-Type: application/x-ndjson' \
    --data-binary @"$f"
done
```

The exported mapping uses Elasticsearch `dense_vector` with indexing enabled for
kNN retrieval. The bulk files are newline-delimited JSON with action/source line
pairs and a final newline.

You can also load with the project CLI. If `--bulk` points to a non-existent base
file, the loader will automatically use matching `part-*` files:

```sh
python3 scripts/evidence_vectors.py load-elastic \
  --url http://localhost:9200 \
  --index qe-scaling-chunk-001-gap-topics-sapbert-cls \
  --mapping build/qe-scaling-chunk-001-gap-topics-sapbert-cls.elastic.mapping.json \
  --bulk build/qe-scaling-chunk-001-gap-topics-sapbert-cls.elastic.bulk.ndjson \
  --create-index
```

Run an Elasticsearch kNN query using the same embedding provider used to build
the vectors:

```sh
python3 scripts/evidence_vectors.py search-elastic \
  --url http://localhost:9200 \
  --index qe-scaling-chunk-001-gap-topics-sapbert-cls \
  --query 'pseudomonas aeruginosa wound abscess' \
  --provider sapbert \
  --local-files-only \
  --max-seq-length 128 \
  --k 10 \
  --num-candidates 100
```

For search quality assessment, keep the query encoder and indexed vector model
identical. Do not compare SapBERT queries against hashing vectors or
mean-pooled wrappers.

The browser assessment can use the same Elasticsearch index:

```sh
python3 scripts/search_quality_server.py \
  --port 8766 \
  --vectors build/scaling_chunk_001_gap_topics_concept_vectors.sapbert_cls.jsonl \
  --docs build/scaling_chunk_001_gap_topics_concept_documents.jsonl \
  --evidence build/profile_evidence_scaling_chunk_001_gap_topics_materialized/*.jsonl \
  --provider sapbert \
  --local-files-only \
  --max-seq-length 128 \
  --elastic-url http://localhost:9200 \
  --elastic-index qe-scaling-chunk-001-gap-topics-sapbert-cls
```

Run the standing clinical smoke test against the live API when checking ranking
changes:

```sh
python3 scripts/evaluate_search_api.py \
  --queries config/search_quality_clinical_queries.tsv \
  --base-url http://127.0.0.1:8766 \
  --top-k 5
```

The output is one TSV row per query with the top CUI/name, semantic type,
expected-CUI rank when configured, visible source mix, and the main score
components. Use it as the first pass before deeper relevance review.

## Recommended Evidence Sources

High-value evidence:

- PubMed abstracts and PMC/Europe PMC open literature text
- bounded ClinicalTrials.gov subsets for trial condition, intervention,
  eligibility, outcome, and population language
- bounded MedlinePlus XML subsets for patient-facing synonyms and lay phrasing
- bounded MedlinePlus Genetics subsets for genes, genetic conditions,
  chromosomes, inheritance, and related-condition language
- bounded DailyMed label subsets for indications, warnings, interactions,
  adverse reactions, populations, and pharmacology language
- bounded NCBI Bookshelf / NLM LitArch Open Access packages for clinical
  guidelines, evidence reports, and book chapters with per-package licenses
- RxNorm/RxClass, LOINC, MeSH, NCI/NCIt, HPO, and other permitted public
  biomedical sources
- OpenAlex citation-linked evidence when it adds useful literature context
- manually reviewed examples when available

Lower-value evidence should be kept separate or down-weighted:

- weak automatic mappings
- unreviewed acronym expansions
- generic snippets where the concept is not the main referent

## Why Label Anchoring

PubMed, Europe PMC, PMC Open Access, and other permitted sources give us real
language, but they do not directly give trustworthy UMLS CUI labels for every
useful snippet. The linker therefore uses UMLS itself as a high-precision anchor:
when a corpus span exactly matches a UMLS label, the surrounding context becomes
evidence for that CUI. The context may contain abbreviations, lay phrasing,
spelling variants, and neighboring wording that are not good MRCONSO additions
but are useful for vector retrieval.
