# Reproducibility Guide

This project can be reproduced externally, but not from the repository alone. The code and benchmark configuration can be shared; several source vocabularies and generated indexes must be rebuilt locally because they are licensed or too large to commit.

For a fresh GitHub clone, start with
[GitHub Quickstart](github_quickstart.md). It separates commands that work
without local artifacts from commands that require a completed local build.

## Reproducibility Levels

### Level 1: Benchmark Reproduction On An Existing Build

Use this when a machine already has the generated `build/` artifacts.

```sh
python3 scripts/reproducibility_manifest.py \
  --hash-small-files \
  --out build/reproducibility_manifest.json

python3 scripts/evaluate_paragraph_quality.py \
  --output-dir build/improvements/reproduce_current_quality \
  --top-k 60

python3 scripts/audit_paragraph_precision.py \
  --payloads build/improvements/reproduce_current_quality/paragraph_search_payloads.jsonl \
  --output-dir build/improvements/reproduce_current_quality \
  --top-n 10
```

Expected current quality:

- 116 paragraph queries
- 570 expected concepts
- 100% recall@10
- 116/116 good verdicts
- 0 calibrated suspect top-10 hits

### Level 2: Public/Shareable Build

Use this for an external public build that avoids real EHR data. Public/shareable inputs may include PubMed, PMC Open Access, Europe PMC, bounded ClinicalTrials.gov, MedlinePlus, MedlinePlus Genetics, DailyMed subsets, NCBI Bookshelf / NLM LitArch Open Access packages, reusable government reference pages such as NCI/CDC/FDA/NIDDK, OpenAlex metadata, Wikipedia/Wikimedia-derived enrichment where license-compatible, public OHDSI aggregate artifacts, and any open source vocabularies that can be redistributed under their terms.

This level should not use MIMIC or other credentialed EHR data by default.

### Level 3: Licensed Local Build

Use this when the builder has local rights to UMLS, LOINC, SNOMED CT, or other restricted vocabularies. Generated indexes derived from those sources should not be redistributed unless the source license permits it.

## Required Source Inputs

Repo-provided configuration:

- `config/search_quality_paragraph_queries.tsv`
- `config/search_quality_acceptable_cui_alternatives.tsv`
- `config/search_quality_useful_extra_cuis.tsv`
- `config/active_label_supplement.tsv`
- source-topic configs under `config/`

External public sources:

- PubMed abstracts through NCBI E-utilities
- PMC Open Access full text through NCBI/PMC OA
- Europe PMC abstracts
- ClinicalTrials.gov API v2 study subsets
- MedlinePlus health topic XML subsets
- MedlinePlus Genetics summary XML subsets
- DailyMed SPL drug label subsets
- NCBI Bookshelf / NLM LitArch Open Access subset packages through the FTP file list
- HPO and MONDO OBO ontology term corpora, with HPO annotation files for opt-in relation augmentation after source-specific reuse review
- OpenAlex cited-work metadata
- Wikipedia/Wikimedia open content where license-compatible
- Public OHDSI aggregate artifacts, not patient-level data

Licensed or local-only sources:

- UMLS Metathesaurus files, especially `MRCONSO.RRF`, `MRSTY.RRF`, `MRREL.RRF`, and `MRDEF.RRF`
- LOINC release files when direct LOINC enrichment is used
- SNOMED CT only where deployment/license terms permit it
- External CUI vectors such as cui2vec/BioConceptVec only under their own licenses
- MIMIC or other credentialed EHR data should stay out of the public default path

## Core Generated Artifacts

The current search server expects document/vector artifacts plus several SQLite indexes:

- concept documents JSONL
- concept vectors JSONL or Elasticsearch/OpenSearch vector index
- `build/umls_biomedicine_search_label_index.sqlite`
- `build/cui_code_index.sqlite`
- `build/umls_semantic_types.sqlite`
- `build/umls_related_concepts.sqlite`
- `build/umls_research_relations.sqlite`
- `build/umls_definitions.sqlite`
- optional `build/relationship_edges.sqlite` for relationship display
- optional `build/external_cui_vector_neighbors.sqlite`

Run this to inventory what exists locally:

```sh
python3 scripts/reproducibility_manifest.py \
  --umls-meta /path/to/UMLS/META \
  --loinc-dir /path/to/Loinc_2.82 \
  --snomed-zip /path/to/SnomedCT_release.zip \
  --hash-small-files \
  --out build/reproducibility_manifest.json
```

Use `--full-hash` only when you are willing to spend time hashing large generated artifacts.

The manifest does not copy any source data. It records existence, size,
timestamps, license class, and optional SHA-256 hashes so another builder can
tell whether they are using the same local source drops.

## Source Acquisition Progression

Evidence acquisition should be replayable as a measured sequence, not just a
set of generated files. The stage ledger in
`config/source_acquisition_progression.tsv` records each acquisition attempt
with its hypothesis, scope, query set, metrics, artifacts, decision rule, and
decision. Run this after adding or retesting source evidence:

```sh
python3 scripts/source_acquisition_progression.py \
  --fail-on-regression \
  --out-json build/source_acquisition/progression_manifest.json \
  --out-md build/source_acquisition/progression_report.md
```

The generated manifest inventories every listed artifact, hashes small files,
records the stage-config hash, and evaluates deterministic gates. Diagnostic
stages are recorded for learning; `no_regression` stages must not lose recall or
add disallowed top-ranked concepts relative to the previous retained stage in
the same group; `promote` stages must also show a useful improvement. Rejected
diagnostic stages are recorded without lowering the next gate. Final group
deltas are still reported against the group's baseline so the net improvement
remains visible.

Fresh clones do not have the historical `build/source_acquisition/` metrics.
Use this non-strict inspection mode before local artifacts have been rebuilt:

```sh
python3 scripts/source_acquisition_progression.py \
  --allow-missing-stage-metrics \
  --out-json build/source_acquisition/progression_manifest.json \
  --out-md build/source_acquisition/progression_report.md
```

Use `--fail-on-regression` only after the referenced local artifacts exist.

## Runtime Dependencies

The public-first hashing build path is intentionally standard-library only. It
does not require `pip install` for ingestion, UMLS/LOINC/SNOMED local indexing,
hashing embeddings, local vector search, the search UI, or the paragraph
evaluator.

`requirements-public.txt` is intentionally empty except for comments. It exists
so external users have a stable install step:

```sh
python3 -m pip install -r requirements-public.txt
```

Optional features have separate dependencies:

- SapBERT/transformer embeddings: `torch` and `transformers`
- sentence-transformer embeddings: `sentence-transformers`
- external CUI vector indexing: `numpy`
- Elasticsearch/OpenSearch serving: a running Elasticsearch/OpenSearch service;
  the Python client code uses the standard-library HTTP stack

## Minimal Public-First Build Outline

The exact corpus size can vary, but the reproducible public path is now wrapped
by one command:

```sh
python3 scripts/run_public_rebuild.py \
  --umls-meta /path/to/UMLS/META \
  --out-dir build/public \
  --provider hashing
```

For a command plan without network calls or file writes:

```sh
python3 scripts/run_public_rebuild.py \
  --umls-meta /path/to/UMLS/META \
  --out-dir build/public \
  --provider hashing \
  --dry-run
```

The wrapper fetches public corpora, builds UMLS-derived indexes from local
licensed files, links corpus text to CUIs with multiword semantic-profile
shards, builds concept documents/vectors, builds provenance and relationship
indexes, runs paragraph evaluation plus precision audit, writes a
reproducibility manifest, and writes the server command to
`build/public/server_command.txt`.

The same steps are shown below for debugging or custom builds.

```sh
python3 scripts/evidence_vectors.py fetch-pubmed-topics \
  --topics config/pubmed_biomedicine_topics.tsv \
  --retmax 500 \
  --out build/public/pubmed_topics_corpus.jsonl

python3 scripts/evidence_vectors.py fetch-europepmc-topics \
  --topics config/pubmed_biomedicine_topics.tsv \
  --max-records 500 \
  --out build/public/europepmc_topics_corpus.jsonl

python3 scripts/evidence_vectors.py fetch-pmc-oa-topics \
  --topics config/pubmed_biomedicine_topics.tsv \
  --max-records 200 \
  --out build/public/pmc_oa_topics_corpus.jsonl
```

Build UMLS-derived indexes locally from licensed files:

```sh
python3 scripts/evidence_vectors.py build-label-index \
  --mrconso /path/to/MRCONSO.RRF \
  --mrsty /path/to/MRSTY.RRF \
  --profile biomedicine \
  --out build/umls_biomedicine_search_label_index.sqlite \
  --replace

python3 scripts/evidence_vectors.py build-profile-indexes \
  --mrconso /path/to/MRCONSO.RRF \
  --mrsty /path/to/MRSTY.RRF \
  --out-dir build/public/indexes/profile_indexes \
  --replace

python3 scripts/evidence_vectors.py build-code-index \
  --mrconso /path/to/MRCONSO.RRF \
  --out build/cui_code_index.sqlite \
  --replace

python3 scripts/evidence_vectors.py build-semantic-type-index \
  --mrsty /path/to/MRSTY.RRF \
  --out build/umls_semantic_types.sqlite \
  --replace
```

Link public corpus text to CUIs, build concept documents, and embed:

```sh
python3 scripts/evidence_vectors.py link-profile-shards \
  --corpus build/public/pubmed_topics_corpus.jsonl build/public/europepmc_topics_corpus.jsonl build/public/pmc_oa_topics_corpus.jsonl build/public/clinicaltrials_subset_corpus.jsonl build/public/medlineplus_subset_corpus.jsonl build/public/medlineplus_genetics_subset_corpus.jsonl build/public/dailymed_subset_corpus.jsonl build/public/bookshelf_oa_subset_corpus.jsonl \
  --index-dir build/public/indexes/profile_indexes \
  --out-dir build/public/profile_evidence \
  --run-name public_corpus \
  --matcher trie \
  --materialize-corpus

python3 scripts/evidence_vectors.py build-docs-sqlite \
  --evidence build/public/profile_evidence/public_corpus_*_evidence.jsonl \
  --sqlite build/public/public_docs.sqlite \
  --mrconso /path/to/MRCONSO.RRF \
  --out build/public/public_concept_documents.jsonl \
  --replace

python3 scripts/evidence_vectors.py embed \
  --docs build/public/public_concept_documents.jsonl \
  --out build/public/public_concept_vectors.hashing.jsonl \
  --provider hashing
```

Build a provenance index so evidence bullets can resolve to public citations on
demand without loading every evidence row into the server:

```sh
python3 scripts/evidence_vectors.py build-provenance-index \
  --evidence build/public/profile_evidence/public_corpus_*_evidence.jsonl \
  --docs build/public/public_concept_documents.jsonl \
  --sqlite build/search_quality_provenance.sqlite \
  --replace
```

Build optional relationship and definition indexes:

```sh
python3 scripts/evidence_vectors.py build-relation-index \
  --mrrel /path/to/MRREL.RRF \
  --mrconso /path/to/MRCONSO.RRF \
  --docs build/public/public_concept_documents.jsonl \
  --out build/umls_related_concepts.sqlite \
  --replace

python3 scripts/evidence_vectors.py build-research-relation-index \
  --mrrel /path/to/MRREL.RRF \
  --mrconso /path/to/MRCONSO.RRF \
  --mrsty /path/to/MRSTY.RRF \
  --docs build/public/public_concept_documents.jsonl \
  --out build/umls_research_relations.sqlite \
  --replace

python3 scripts/evidence_vectors.py build-definition-index \
  --mrdef /path/to/MRDEF.RRF \
  --docs build/public/public_concept_documents.jsonl \
  --out build/umls_definitions.sqlite \
  --replace
```

Run the server against public artifacts:

```sh
python3 scripts/search_quality_server.py \
  --port 8766 \
  --vectors build/public/public_concept_vectors.hashing.jsonl \
  --docs build/public/public_concept_documents.jsonl \
  --label-index build/umls_biomedicine_search_label_index.sqlite \
  --code-index build/cui_code_index.sqlite \
  --semantic-type-index build/umls_semantic_types.sqlite \
  --relation-index build/umls_related_concepts.sqlite \
  --research-relation-index build/umls_research_relations.sqlite \
  --definition-index build/umls_definitions.sqlite \
  --provenance-index build/search_quality_provenance.sqlite \
  --active-label-supplement config/active_label_supplement.tsv
```

Then open:

```text
http://127.0.0.1:8766/
```

Evaluate the same rebuilt docs/vectors directly, without renaming them to the
current local defaults:

```sh
python3 scripts/evaluate_paragraph_quality.py \
  --vectors build/public/public_concept_vectors.hashing.jsonl \
  --docs build/public/public_concept_documents.jsonl \
  --label-index build/umls_biomedicine_search_label_index.sqlite \
  --code-index build/cui_code_index.sqlite \
  --semantic-type-index build/umls_semantic_types.sqlite \
  --relation-index build/umls_related_concepts.sqlite \
  --research-relation-index build/umls_research_relations.sqlite \
  --definition-index build/umls_definitions.sqlite \
  --active-label-supplement config/active_label_supplement.tsv \
  --output-dir build/public/paragraph_quality_eval \
  --top-k 60

python3 scripts/audit_paragraph_precision.py \
  --payloads build/public/paragraph_quality_eval/paragraph_search_payloads.jsonl \
  --output-dir build/public/paragraph_quality_eval \
  --top-n 10
```

The same query set is calibrated against the current local benchmark. A smaller
public corpus may score lower; record that in the manifest rather than treating
it as a build failure.

## Source And License Matrix

| Source | Required | Redistributable in repo | Used for | Notes |
| --- | --- | --- | --- | --- |
| Repo config TSVs | yes | yes | benchmark, active labels, topics | Versioned with code. |
| PubMed abstracts | public build yes | derived outputs depend on NCBI terms | literature evidence | Fetched by topic at rebuild time. |
| PMC Open Access | public build recommended | license varies by article | full-text evidence | Keep license/provenance metadata. |
| Europe PMC | public build recommended | derived outputs depend on source terms | literature evidence | De-duplicated downstream by identifiers. |
| MedlinePlus / MedlinePlus Genetics / DailyMed | public build optional | yes with attribution and source caveats | lay language, genetics, drug labels | Keep bounded subsets and source URLs. |
| NCBI Bookshelf / NLM LitArch Open Access subset | public build optional | license varies by package | clinical guidelines, evidence reports, book chapters | Fetch only through the NLM LitArch FTP service and preserve package license metadata. |
| HPO / MONDO OBO ontologies | public build optional | yes with attribution/version metadata | phenotype and disease labels, definitions, synonyms, xrefs, hierarchy text | Use `fetch-obo-ontology`; HPO annotation files can augment research relations with disease/gene/phenotype links when explicitly enabled after source-specific reuse review. |
| NCI / CDC / FDA / NIDDK reference pages | public build optional | yes for reusable text, with source caveats | diagnostic and disease reference language | The rebuild fetches small default subsets; check page-level exceptions. |
| Merck/MSD Manual Professional / AAFP / Medscape / BMJ Best Practice / NICE CKS / Patient.info Professional / GPnotebook | no for public build | no without permission or licensed access | high-value clinician reference language | Tracked in `config/reference_source_policy.tsv`; use only in private/licensed deployments. |
| NCBI Bookshelf StatPearls / WikEM | no for public build | restricted by per-source license and access terms | open-access clinician reference language | Not default rebuild sources; require explicit license review, attribution/share-alike handling where applicable, and no prohibited automated access. |
| UMLS META | licensed build yes | no | CUI backbone, labels, types, relations, definitions | External users supply their own local release. |
| LOINC | optional | no unless terms permit | observation enrichment | Manifested when supplied. |
| SNOMED CT | optional | no unless deployment license permits | procedures, disorders, findings | Manifested when supplied. |
| OpenAlex/Wikipedia/Wikimedia | optional | usually yes with attribution/license handling | enrichment, images, cited evidence | Keep source URLs and licenses. |
| OHDSI aggregate artifacts | optional | only if public/shareable aggregate data | relationship edges | Do not use patient-level EHR data in public rebuilds. |
| MIMIC/EHR data | no for public build | no | local-only experimentation | Excluded from the public rebuild wrapper. |

## What Not To Redistribute

Do not commit or publish:

- `build/` artifacts derived from licensed vocabularies unless the source licenses permit redistribution
- raw UMLS, LOINC, or SNOMED CT release files
- MIMIC or other credentialed clinical corpora
- raw patient-level OHDSI/EHR data

The repository `.gitignore` already excludes `build/`, `data/`, local LOINC drops, and SNOMED release archives.

## External Release Checklist

Before publishing an external reproducibility package:

1. Generate `build/reproducibility_manifest.json` with all local source paths
   supplied.
2. Confirm the public server command uses only public corpus docs/vectors plus
   locally rebuilt licensed indexes.
3. Run `scripts/evaluate_paragraph_quality.py` with explicit `--vectors` and
   `--docs` paths.
4. Run `scripts/audit_paragraph_precision.py` on the evaluator payloads.
5. Publish the code, configs, benchmark TSVs, docs, and manifest; do not publish
   restricted source files or generated indexes derived from non-redistributable
   sources.

## Practical Bundle Split

For an external release, create two artifact bundles:

- Public bundle: code, configs, public benchmark queries, public-only enrichment outputs, and reproducibility manifests.
- Local build bundle: scripts and instructions for rebuilding UMLS/LOINC/SNOMED-derived indexes from locally licensed files.
