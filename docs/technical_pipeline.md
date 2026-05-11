# UMLS Semantic Evidence Index Technical Pipeline

Last updated: 2026-05-06

This document is the living technical reference for the UMLS Semantic Evidence
Index. Update it whenever the pipeline shape, current artifacts, counts,
quality metrics, or scaling assumptions change.

## Purpose

The project is building a successor search layer on top of UMLS. UMLS remains
the concept identity layer: CUIs, labels, semantic types, and source vocabulary
metadata still define what each concept is. The new layer adds real-world
biomedical language, semantic vectors, provenance, search evaluation, and
incremental release artifacts.

When the evidence shows a useful biomedical idea that UMLS does not represent
cleanly, the pipeline can create a local extension concept. These extension
concepts use local `NEW#######` identifiers; they are not official NLM UMLS CUIs
unless they are later promoted through a terminology governance process.

The goal is not to create a larger synonym dump. Elasticsearch can already deal
with many lexical problems such as capitalization, punctuation, and word-order
variation. The hard problem is mapping real biomedical language to the right
CUI when the language is contextual, abbreviated, clinical, or evidence-driven.

## Current State

Current local status:

- UMLS input: current local indexes; the successor seed should use
  restriction-level-0/category-0 vocabularies identified in `MRSAB.RRF`, plus
  separately supplied direct LOINC files
- Latest reviewed PubMed batch loaded into the assessment path:
  `pubmed_bulk_recent_1321_1320`
- Current assessment server: `http://127.0.0.1:8767/`, hydrated through PubMed
  shards `1321` and `1320` for the latest review run
- Progress view: `http://127.0.0.1:8767/progress`
- Elasticsearch alias: `qe-scaling-sapbert-cls`
- Elasticsearch alias count after `1321/1320` promotion: `535,683`
- Search backend: resolver-first CUI/code lookup, Elasticsearch ANN, and UMLS label fallback
- Embedding model: `cambridgeltl/SapBERT-from-PubMedBERT-fulltext`
- Embedding provider: `transformers-cls`
- Pooling: CLS token
- Dimensions: `768`
- Loaded vector records in latest assessment server: `533,540`
- Full tracker CUI/view document rows represented by artifacts: `516,028`
- Indexed display provenance references: `1,531,116`
- Raw linked evidence rows represented by the current server/provenance set: `10,093,683`
- Evidence files loaded by server: `0` for provenance; source lookup is SQLite-backed
- Provenance index: `build/search_quality_provenance.sqlite`
- Provenance index size: about `736 MB`
- Compact vector exports: `build/compact_vectors/*.manifest.json`
- Compact vector export size: about `1.6 GB`, including the `1321/1320`
  compact float32 vectors
- Last measured assessment server startup time: `97.263s` at 533,540 vector
  records, down from the earlier eager-provenance `134.309s`
- UMLS search label index: `build/umls_biomedicine_search_label_index.sqlite`
- UMLS search label index size: about `961 MB`
- UMLS search label rows built: `7,049,993`
- UMLS CUI/code resolver index: `build/cui_code_index.sqlite`
- UMLS CUI/code resolver rows built: `9,112,359`
- UMLS CUI/code resolver index size: about `1.4 GB`
- UMLS semantic type index: `build/umls_semantic_types.sqlite`
- UMLS semantic type rows built: `3,876,927`
- Related-concepts mode: evidence-vector neighbors first, MRREL as supporting/fallback graph links
- Related-concepts index: `build/umls_related_concepts.sqlite`
- Related-concepts index size: about `48 MB`
- Related-concepts links indexed for search UI: `483,677` links across `88,773`
  source CUIs
- Research cross-type relation index: `build/umls_research_relations.sqlite`
- Research cross-type links indexed for search UI: `152,326` links across
  `24,061` source CUIs and seven target categories
- HPO external annotation files staged under `data/external/hpo/`
- Extension concept lane: implemented for local `NEW#######` concepts; no
  extension concepts are loaded into the current assessment alias yet
- MIMIC full data availability marker exists; full MIMIC ingest/linking remains
  paused until a restricted-data run is explicitly started and reviewed

Last reviewed quality sample:

- Query count: `8`
- Judgments: `40`
- Mean weighted P@5: `0.750`
- Mean MRR: `1.0`
- Relevant top-1 queries: `8 / 8`
- Judgment file: `build/scaling_runs/pubmed_bulk_recent_1321_1320/search_quality_judgments.csv`
- Summary file: `build/scaling_runs/pubmed_bulk_recent_1321_1320/search_quality_summary.json`
- Additional 10-query mixed clinical smoke: `10 / 10` relevant top-1,
  mean weighted P@5 `0.570`, mean MRR `1.0`

Current full-pipeline tracker progress:

- Artifact readiness: `79 / 83` steps
- Effort-weighted progress: `72.4%`
- Next planned processing step: full PubMed baseline/update bulk ingest as
  bounded, review-gated shards

## Design Principles

- Use UMLS CUIs as stable identifiers.
- Use local `NEW#######` extension IDs, not official-looking NLM CUIs, for useful
  evidence-backed concepts that are missing or poorly represented in UMLS.
- Use real-world evidence to represent how concepts are actually discussed.
- Use SapBERT or another biomedical BERT model for quality-bearing vectors.
- Do not use mean pooling for the current quality path.
- Do not use hashing vectors except as a smoke test.
- Keep raw evidence and searchable product artifacts separable.
- Keep provenance pointers so a user can inspect why a result was retrieved.
- Gate every scale increase with search-quality review.
- Keep chunks small enough to iterate. Local chunk work should target 10
  minutes or less where possible.
- Exclude DRG-derived evidence.
- Do not pull new synonym sources from vocabularies already present in UMLS as
  if they were independent evidence.
- Do not emit extension concepts into the release surface without evidence,
  review status, and UMLS anchor metadata where a close, broader, or related CUI
  exists.
- Do not ingest or ship CPT codes or CPT descriptors in the open procedure
  layer. Procedure coverage should use open/permitted vocabularies, including
  SNOMED CT by default in local procedure bundles, structured procedure bundles,
  evidence-backed `NEW#######` concepts, and an optional private CPT adapter for
  licensed deployments. See
  `docs/procedure_coverage_without_cpt.md`.

## Data Model

The core record types live in `src/qe_evidence_vectors/schema.py`.

### CorpusDocument

Raw source text normalized into a common local shape.

Fields:

- `doc_id`: stable source document id
- `source`: source family, such as `pubmed`, `pubmed_bulk`, `europepmc`, or
  future MIMIC sources
- `text`: title, abstract, snippet, or other evidence text
- `title`: optional title
- `metadata`: source-specific fields such as PMID, PMCID, DOI, file name, table,
  or item id

### EvidenceRecord

A linked mention of a UMLS CUI in a source document.

Fields:

- `evidence_id`: stable id for this linked evidence item
- `cui`: UMLS CUI
- `text`: evidence text that should support retrieval
- `source`: source family
- `evidence_type`: typed view, for example `pubmed_clinical_context`
- `weight`: evidence weight
- `metadata`: provenance and linker metadata

For extension concepts, `cui` contains the local `NEW#######` id. Extension
evidence keeps `extension_concept_id`, preferred label, and review status in
metadata so it remains auditable.

### Universal Relationship Edge

Mined relationship artifacts can be stored as JSONL rows with an `edge` object.
The edge object contains `subject`, `object`, `type`, numeric `strength`,
`strength_metric`, `directionality`, `evidence`, structured `context`, and
numeric `confidence`. Public aggregate OHDSI artifacts and procedure-bundle
relations use this path when they need to contribute relationships rather than
new text evidence.

Build the searchable relationship-edge index with:

```sh
python3 scripts/evidence_vectors.py build-relationship-edge-index \
  --edges config/curated_relationship_edges.jsonl \
  --out build/relationship_edges.sqlite \
  --replace
```

The search-quality server loads `build/relationship_edges.sqlite` by default
when present. Those edges are merged into related semantic views and use their
stored strength/confidence for related-result gating.

`config/curated_relationship_edges.jsonl` is a small seed layer for stable
clinical relationships and procedure-bundle attributes. Mined public aggregate
files, such as OHDSI cohort edges, should be appended to `--edges` as they
become available.

### ExtensionConcept

A reviewed local concept that represents a useful biomedical idea not covered
cleanly by an existing UMLS CUI.

The input is JSONL. Required fields:

- `preferred_label`
- `evidence`: one or more evidence text entries unless the command is run with
  a lower `--min-evidence`

Recommended fields:

- `aliases`: concise labels that are genuinely useful, not capitalization or
  permutation variants
- `semantic_type`: UMLS-style semantic type or local semantic class
- `definition`
- `status`: `candidate`, `reviewed`, `promoted`, `rejected`, or `deprecated`
- `broader_cuis`, `related_cuis`, `close_match_cuis`: anchors back to UMLS
- `metadata`: reviewer, rationale, harvest/build references, or notes

Generated ids are deterministic from preferred label plus semantic type:

```text
NEW#######
```

The builder rejects ids that look like official UMLS CUIs (`C` followed by
seven digits). This prevents accidental publication of local concepts as if
they were assigned by NLM.

### ConceptDocument

An aggregate search document for one CUI and one evidence view.

Fields:

- `doc_id`: usually `{CUI}:{view}`
- `cui`: UMLS CUI
- `view`: context-specific view
- `text`: UMLS labels plus selected real-world evidence
- `evidence_count`: total linked evidence records contributing to the document
- `sources`: source families represented in selected evidence
- `labels`: selected UMLS labels
- `metadata`: build metadata

The text format is intentionally simple:

```text
CUI: C0036983
Evidence view: pubmed_clinical_context
UMLS labels:
- Septic shock
- Shock, Septic
Real-world evidence:
- ...
```

### VectorRecord

A semantic vector for one `ConceptDocument`.

Fields:

- `doc_id`
- `cui`
- `view`
- `vector`
- `text`, optionally omitted for compact exports
- `metadata`, including embedding provider, model, pooling, labels, source list,
  and evidence count

## Pipeline Stages

### 1. Build UMLS Label Indexes

The pipeline builds semantic profile indexes from `MRCONSO.RRF` and `MRSTY.RRF`.
These indexes let the linker restrict matching to broad biomedical profiles:

- `clinical`
- `chemicals-drugs`
- `genes-proteins`
- `anatomy`
- `procedures-devices`
- `organisms`
- `labs-measurements`

There is also a separate search-only UMLS label fallback index:

```text
build/umls_biomedicine_search_label_index.sqlite
```

That index includes single-token labels because it is used at search time, not
as the evidence linker. It is intentionally separate from profile linking so
exact UMLS labels can rescue missing evidence hits without changing the linked
evidence corpus.

There is now a separate CUI/code resolver index:

```text
build/cui_code_index.sqlite
```

It is built from `MRCONSO.RRF` and stores `cui`, `sab`, `code`, `scui`,
`sdui`, `tty`, `label`, `ispref`, and `suppress`. The resolver uses it before
ANN search so direct CUI inputs and source vocabulary code inputs such as
`ICD10CM:I48.91` or unqualified code-like strings can resolve to candidate CUIs
deterministically instead of being embedded as arbitrary text.

Generic labels and generic concepts are suppressed through
`src/qe_evidence_vectors/generic_filters.py`.

### 2. Acquire Real-World Evidence

Current sources:

- PubMed topic harvests through E-utilities
- Europe PMC topic harvests
- PubMed bulk baseline pilot from NCBI FTP

Planned or paused sources:

- Full PubMed baseline and update files
- MIMIC full data, paused until the local download is ready

The project started with E-utilities topic chunks for iteration. The scaling
path is bulk PubMed ingestion because repeated search API calls are not the
right way to cover all of PubMed.

Current PubMed bulk pilot:

```text
data/pubmed/baseline/pubmed26n1334.xml.gz
build/pubmed_bulk_recent_baseline_corpus.jsonl
```

The second bulk pilot adds:

```text
data/pubmed/baseline/pubmed26n1333.xml.gz
data/pubmed/baseline/pubmed26n1332.xml.gz
build/pubmed_bulk_recent_next2_corpus.jsonl
```

The third bulk pilot adds:

```text
data/pubmed/baseline/pubmed26n1331.xml.gz
data/pubmed/baseline/pubmed26n1330.xml.gz
build/pubmed_bulk_recent_1331_1330_corpus.jsonl
```

The fourth bulk pilot adds:

```text
data/pubmed/baseline/pubmed26n1329.xml.gz
data/pubmed/baseline/pubmed26n1328.xml.gz
build/pubmed_bulk_recent_1329_1328_corpus.jsonl
```

The fifth bulk pilot adds:

```text
data/pubmed/baseline/pubmed26n1327.xml.gz
data/pubmed/baseline/pubmed26n1326.xml.gz
build/pubmed_bulk_recent_1327_1326_corpus.jsonl
```

The sixth bulk pilot adds:

```text
data/pubmed/baseline/pubmed26n1325.xml.gz
data/pubmed/baseline/pubmed26n1324.xml.gz
build/pubmed_bulk_recent_1325_1324_corpus.jsonl
```

The seventh bulk pilot adds:

```text
data/pubmed/baseline/pubmed26n1323.xml.gz
data/pubmed/baseline/pubmed26n1322.xml.gz
build/pubmed_bulk_recent_1323_1322_corpus.jsonl
```

These pilots start with high-numbered 2026 baseline files because those files
are newer PMID ranges and are useful for testing recent language.

### 3. Link Evidence To UMLS CUIs

The linker matches corpus documents against profile-specific UMLS label indexes.
Evidence is emitted as JSONL shards, usually one file per semantic profile.

Current example:

```text
build/profile_evidence_pubmed_bulk_recent_baseline/*.jsonl
```

The linker records provenance in each evidence record. For PubMed and Europe
PMC this includes PMID, PMCID, DOI where available, corpus document id, and the
matched label. For future MIMIC data, public artifacts must not include raw
patient text.

### 4. Aggregate Evidence Into CUI/View Documents

Evidence records are grouped by `(CUI, evidence_view)`. The document builder
deduplicates evidence text, keeps top weighted evidence, attaches selected UMLS
labels, and writes one `ConceptDocument` per CUI/view.

Current bulk pilot output:

```text
build/pubmed_bulk_recent_baseline_concept_documents.jsonl
build/pubmed_bulk_recent_next2_concept_documents.jsonl
build/pubmed_bulk_recent_1331_1330_concept_documents.jsonl
build/pubmed_bulk_recent_1329_1328_concept_documents.jsonl
build/pubmed_bulk_recent_1327_1326_concept_documents.jsonl
build/pubmed_bulk_recent_1325_1324_concept_documents.jsonl
build/pubmed_bulk_recent_1323_1322_concept_documents.jsonl
```

### 4A. Create Reviewed Extension Concepts When Needed

Extension concepts are used only when they add a useful biomedical entity or
meaningful concept boundary that UMLS does not currently cover well. They are
not a synonym-mining mechanism.

Example input row:

```json
{"preferred_label":"post-viral exertional intolerance phenotype","aliases":["post viral exertional intolerance"],"semantic_type":"Finding","definition":"Persistent exertional intolerance after viral illness.","status":"reviewed","broader_cuis":["C0012634"],"close_match_cuis":["C5203670"],"evidence":[{"text":"Patients described persistent exertional intolerance after infection.","source":"pmc_oa","weight":1.5,"metadata":{"pmcid":"PMC1"}}],"metadata":{"reviewer":"local-review"}}
```

Build command pattern:

```sh
python3 scripts/evidence_vectors.py build-extension-concepts \
  --input config/extension_concepts.new.jsonl \
  --out-docs build/extension_concept_documents.jsonl \
  --out-evidence build/extension_concept_evidence.jsonl \
  --out-registry build/extension_concept_registry.jsonl
```

Outputs:

- `extension_concept_documents.jsonl`: search documents that can be embedded
  with the same SapBERT CLS path
- `extension_concept_evidence.jsonl`: provenance-bearing evidence records
- `extension_concept_registry.jsonl`: release/governance registry for local
  extension ids

Before alias promotion, extension concepts should be evaluated in the search UI
and by Codex/LLM judging. Human feedback is useful, but human approval is not a
hard gate for creating a local `NEW#######` CUI. Promotion means the record can
be shipped as a UMLS Semantic Evidence Index extension record. It does not mean
it has become an official UMLS CUI.

The broader `NEW#######` iteration loop is codified in
`docs/new_umls_iteration_loop.md`.

### 5. Embed Documents

Quality-bearing embeddings use SapBERT with CLS pooling:

```text
provider: sapbert
model: cambridgeltl/SapBERT-from-PubMedBERT-fulltext
pooling: CLS
max sequence length: 128 in the current server path
dimensions: 768
```

Hashing vectors remain useful only for pipeline smoke tests. They should not be
used for quality judgments or release artifacts.

Current bulk pilot vector output:

```text
build/pubmed_bulk_recent_baseline_concept_vectors.sapbert_cls.jsonl
build/pubmed_bulk_recent_next2_concept_vectors.sapbert_cls.jsonl
build/pubmed_bulk_recent_1331_1330_concept_vectors.sapbert_cls.jsonl
build/pubmed_bulk_recent_1329_1328_concept_vectors.sapbert_cls.jsonl
build/pubmed_bulk_recent_1327_1326_concept_vectors.sapbert_cls.jsonl
build/pubmed_bulk_recent_1325_1324_concept_vectors.sapbert_cls.jsonl
build/pubmed_bulk_recent_1323_1322_concept_vectors.sapbert_cls.jsonl
build/pubmed_bulk_recent_1321_1320_concept_vectors.sapbert_cls.jsonl
```

The `pubmed_bulk_recent_next2`, `pubmed_bulk_recent_1331_1330`,
`pubmed_bulk_recent_1329_1328`, `pubmed_bulk_recent_1327_1326`, and
`pubmed_bulk_recent_1325_1324`, `pubmed_bulk_recent_1323_1322`, and
`pubmed_bulk_recent_1321_1320` vector files omit duplicated document text and
therefore must be loaded with their matching concept document JSONL files when
using the assessment server.

### 6. Export And Load Elasticsearch

Vector JSONL is exported to Elasticsearch mapping JSON and bulk NDJSON. The
mapping uses a `dense_vector` field with cosine similarity and metadata fields
for CUI, view, labels, evidence counts, source list, embedding provider, and
embedding model.

The cumulative alias is:

```text
qe-scaling-sapbert-cls
```

The assessment server searches the alias rather than a single chunk index.

Local bulk-load note: a 195 MB NDJSON bulk request failed with a broken pipe
while loading `pubmed_bulk_recent_next2`. Re-exporting the same 54,906 documents
into 11 parts of about 38-39 MB loaded with zero Elasticsearch errors. Keep
future local bulk parts around 5,000 documents or roughly 40 MB unless the local
Elasticsearch HTTP limits are tuned.

Assessment-server note: eager provenance loading previously took `134s` at an
earlier scale because sources were loaded from many JSONL files. The current
server uses `build/search_quality_provenance.sqlite` for on-demand provenance
lookup and last measured startup around `97s` after the 1321/1320 review
restart.

### 6A. Indexed Provenance And Compact Vectors

The assessment UI does not need every mention-level source row at startup. It
only displays source provenance for the first six evidence bullets per hit, with
up to five citations per bullet. The current indexed provenance artifact stores
that display/audit surface only:

```text
build/search_quality_provenance.sqlite
```

Build command pattern:

```sh
python3 scripts/evidence_vectors.py build-provenance-index \
  --sqlite build/search_quality_provenance.sqlite \
  --replace \
  --sources-per-text 5 \
  --max-document-items 6 \
  --docs ...concept_documents.jsonl \
  --evidence ...evidence.jsonl
```

The lookup key is a 128-bit BLAKE2b hash of normalized evidence text. This keeps
the index compact while still allowing the server to look up sources from the
displayed evidence bullet text.

SapBERT JSONL vector files are also exported to compact float32 files plus
metadata JSONL:

```text
build/compact_vectors/*.vectors.f32
build/compact_vectors/*.metadata.jsonl
build/compact_vectors/*.manifest.json
```

The compact files are not yet the primary server input, but they define the
smaller reusable vector artifact shape for larger releases.

### 7. Search And Label Fallback

The server in `scripts/search_quality_server.py` provides the assessment UI and
JSON endpoints.

Search flow:

1. Resolve direct identifiers before ANN search.
   - `C\d{7}` inputs resolve as direct CUIs.
   - `SAB:CODE` inputs resolve through `build/cui_code_index.sqlite`.
   - Code-like strings are looked up as source vocabulary codes before falling
     through to text search.
2. For text inputs, embed the query with the same SapBERT CLS model.
3. Search Elasticsearch ANN against `qe-scaling-sapbert-cls`.
4. Deduplicate to the best hit per CUI.
5. Merge in UMLS label fallback hits from the search label index. When a label
   fallback wins and the CUI has an evidence-bearing document, the server
   returns that document instead of a zero-evidence label-only hit.
6. Attach related concepts from the result CUI's own evidence vectors. MRREL
   graph links are still returned separately and are used as a fallback when a
   CUI has no evidence-vector neighbors.
7. Attach a researcher-focused cross-semantic relation pack when available.
   This uses full MRREL plus MRSTY semantic categories to expose disease-drug,
   disease-gene/protein, disease-procedure/test, organism, device, and safety
   links without relying on generic nearest-neighbor search.
8. Attach mined universal relationship edges when `build/relationship_edges.sqlite`
   exists. This is the serving path for public aggregate edges such as
   OHDSI-derived `Drug -> likely_indication -> Condition` relationships and
   structured procedure-bundle relationships.
9. Rank and return results with labels, evidence snippets, provenance, and
   related concepts. Each returned CUI is hydrated with MRSTY semantic type
   metadata for display.

The UMLS label fallback is coverage-aware. It can rescue exact missing labels
such as `Appendectomy`, but single-token component hits should not dominate
multi-term evidence queries such as `sepsis lactate vasopressor`.

The related-concepts panel is evidence-first. For each returned CUI, the server
uses that CUI's own CUI/view evidence vectors as seed vectors and asks
Elasticsearch for nearby CUI/view documents. Those neighbors are collapsed by
target CUI and displayed as evidence-related concepts. This is the main related
concept signal because it reflects how concepts co-occur or behave similarly in
real-world evidence text.

MRREL graph support is still available as a secondary/fallback signal through:

```text
build/umls_related_concepts.sqlite
```

A separate research relation index is available through:

```text
build/umls_research_relations.sqlite
```

It is intentionally narrower than the generic MRREL index. It keeps
cross-semantic-type links that are useful for biomedical research workflows:
conditions to genes/proteins, drugs/chemicals, procedures/tests, devices,
organisms, causes, safety relationships, phenotypes, and inverse directions
where the queried CUI is the drug, gene, procedure, organism, or phenotype-linked
gene.

Build command pattern:

```sh
python3 scripts/evidence_vectors.py build-code-index \
  --mrconso ~/Downloads/2026AA/META/MRCONSO.RRF \
  --out build/cui_code_index.sqlite \
  --replace
```

Build relation index command pattern:

```sh
python3 scripts/evidence_vectors.py build-relation-index \
  --mrrel ~/Downloads/2026AA/META/MRREL.RRF \
  --mrconso ~/Downloads/2026AA/META/MRCONSO.RRF \
  --docs ...concept_documents.jsonl \
  --out build/umls_related_concepts.sqlite \
  --max-relations-per-cui 8 \
  --replace
```

The MRREL builder restricts links to CUIs present in the current search
documents, keeps a small ranked set per source CUI, and stores display labels
from MRCONSO. This avoids scanning the 6 GB relationship file on server startup
or query execution. MRREL should be interpreted as vocabulary graph support,
not as the primary evidence-relatedness signal.

Build research relation index command pattern:

```sh
python3 scripts/evidence_vectors.py build-research-relation-index \
  --mrrel ~/Downloads/2025AB/META/MRREL.RRF \
  --mrconso ~/Downloads/2025AB/META/MRCONSO.RRF \
  --mrsty ~/Downloads/2025AB/META/MRSTY.RRF \
  --docs ...concept_documents.jsonl \
  --out build/umls_research_relations.sqlite \
  --max-relations-per-category 12 \
  --hpo-obo data/external/hpo/hp.obo \
  --hpo-phenotype-annotations data/external/hpo/phenotype.hpoa \
  --hpo-genes-to-phenotype data/external/hpo/genes_to_phenotype.txt \
  --replace
```

The HPO augmentation adds direct disease-phenotype and gene-phenotype links,
plus disease-gene and gene-disease links derived from `genes_to_phenotype.txt`
where both sides can be mapped back to UMLS CUIs.

OHDSI artifacts are a high-value source for quantitative relationship edges.
Public ATLAS cohort definitions can supply curated drug/condition cohort logic;
CohortDiagnostics aggregate outputs can supply conditional prevalence and
temporal precedence; population-level estimation outputs can supply hazard
ratios, odds ratios, risk ratios, confidence intervals, and diagnostic quality
signals; PatientLevelPrediction outputs can supply predictive, non-causal
feature links. The local miner emits universal relationship-edge JSONL, and the
default serving path is:

```sh
python3 scripts/evidence_vectors.py build-relationship-edge-index \
  --edges build/ohdsi_relationship_edges.jsonl \
  --out build/relationship_edges.sqlite \
  --replace
```

`scripts/search_quality_server.py` auto-loads `build/relationship_edges.sqlite`
when it exists. The detailed mining plan is in
`docs/ohdsi_relationship_mining.md`. Mine public or shareable aggregate
artifacts first; do not ingest patient-level EHR data into this path.

The server also exposes:

- `/api/resolve?q=...`: returns candidate CUIs for direct CUI, source-code, or
  text-label inputs.
- `/api/related?cui=C0004238&k=10&vocab=ICD10CM`: returns evidence-first
  related concepts, full evidence-vector neighbors from the seed CUI's own
  CUI/view vectors, MRREL graph neighbors, cross-semantic research relations,
  and source vocabulary mappings for the requested vocabularies.

### 8. Review Search Quality

The server-backed UI persists judgments to CSV through `/api/judgments`.

Judgment values:

- `relevant`: the result is a good answer for the query
- `partial`: the result is related or useful but not the full answer
- `wrong`: the result should not be retrieved for this query

Current metrics are computed from the top five results:

- weighted P@5: relevant = 1.0, partial = 0.5, wrong = 0.0
- MRR: first relevant or partial result
- relevant top-1 count: how often rank 1 is fully relevant

The quality gate is deliberately small right now. It is useful for catching
ranking regressions, but it is not yet a release benchmark. The benchmark needs
many more reviewed queries across clinical conditions, drugs, procedures, labs,
organisms, genes, abbreviations, and lay language.

### 9. Track Progress

Progress plans live in `config/*.plan.json`. The reporter is:

```sh
python3 scripts/scaling_status.py \
  --plan config/full_pipeline.plan.json \
  --out-json build/scaling_runs/full_pipeline/progress.json \
  --out-markdown build/scaling_runs/full_pipeline/progress.md
```

The progress percentages are artifact and effort weighted. They are not
wall-clock ETAs and should not be presented as time remaining.

## Important Local Commands

Start the current assessment server:

```sh
python3 scripts/search_quality_server.py \
  --port 8767 \
  --vectors \
    build/scaling_chunk_001_gap_topics_concept_vectors.sapbert_cls.jsonl \
    build/scaling_chunk_002_common_clinical_concept_vectors.sapbert_cls.jsonl \
    build/scaling_chunk_003_abbreviation_language_concept_vectors.sapbert_cls.jsonl \
    build/scaling_chunk_004_drug_safety_therapeutics_concept_vectors.sapbert_cls.jsonl \
    build/scaling_chunk_005_diagnostics_procedures_devices_concept_vectors.sapbert_cls.jsonl \
    build/pubmed_bulk_recent_baseline_concept_vectors.sapbert_cls.jsonl \
    build/pubmed_bulk_recent_next2_concept_vectors.sapbert_cls.jsonl \
    build/pubmed_bulk_recent_1331_1330_concept_vectors.sapbert_cls.jsonl \
    build/pubmed_bulk_recent_1329_1328_concept_vectors.sapbert_cls.jsonl \
    build/pubmed_bulk_recent_1327_1326_concept_vectors.sapbert_cls.jsonl \
    build/pubmed_bulk_recent_1325_1324_concept_vectors.sapbert_cls.jsonl \
    build/pubmed_bulk_recent_1323_1322_concept_vectors.sapbert_cls.jsonl \
    build/pubmed_bulk_recent_1321_1320_concept_vectors.sapbert_cls.jsonl \
    build/mimic_iv_note_local_pilot_concept_vectors.sapbert_cls.jsonl \
  --docs \
    build/scaling_chunk_001_gap_topics_concept_documents.jsonl \
    build/scaling_chunk_002_common_clinical_concept_documents.jsonl \
    build/scaling_chunk_003_abbreviation_language_concept_documents.jsonl \
    build/scaling_chunk_004_drug_safety_therapeutics_concept_documents.jsonl \
    build/scaling_chunk_005_diagnostics_procedures_devices_concept_documents.jsonl \
    build/pubmed_bulk_recent_baseline_concept_documents.jsonl \
    build/pubmed_bulk_recent_next2_concept_documents.jsonl \
    build/pubmed_bulk_recent_1331_1330_concept_documents.jsonl \
    build/pubmed_bulk_recent_1329_1328_concept_documents.jsonl \
    build/pubmed_bulk_recent_1327_1326_concept_documents.jsonl \
    build/pubmed_bulk_recent_1325_1324_concept_documents.jsonl \
    build/pubmed_bulk_recent_1323_1322_concept_documents.jsonl \
    build/pubmed_bulk_recent_1321_1320_concept_documents.jsonl \
    build/mimic_iv_note_local_pilot_concept_documents.jsonl \
  --evidence \
  --provenance-index build/search_quality_provenance.sqlite \
  --provider sapbert \
  --local-files-only \
  --max-seq-length 128 \
  --elastic-url http://localhost:9200 \
  --elastic-index qe-scaling-sapbert-cls \
  --elastic-num-candidates 300 \
  --label-index build/umls_biomedicine_search_label_index.sqlite \
  --code-index build/cui_code_index.sqlite \
  --relation-index build/umls_related_concepts.sqlite \
  --progress-plan config/pubmed_bulk_recent_1321_1320.plan.json \
  --judgments-out build/scaling_runs/pubmed_bulk_recent_1321_1320/search_quality_judgments.csv
```

`build/umls_research_relations.sqlite` and `build/relationship_edges.sqlite`
are loaded automatically by the server when present, so the basic start command
does not need explicit flags for them.

Check server status:

```sh
curl -s http://127.0.0.1:8767/api/status
```

Update full-pipeline progress:

```sh
python3 scripts/scaling_status.py \
  --plan config/full_pipeline.plan.json \
  --out-json build/scaling_runs/full_pipeline/progress.json \
  --out-markdown build/scaling_runs/full_pipeline/progress.md
```

Run tests:

```sh
python3 -m pytest -q
```

## Scaling Plan

The latest reviewed chunk is `pubmed_bulk_recent_1321_1320`: it has `59,881`
corpus documents, `821,042` linked evidence rows, `55,371` CUI/view documents,
`55,371` SapBERT CLS vectors, a compact float32 export, and 12 Elasticsearch
bulk part files. It loaded cleanly into
`qe-scaling-pubmed-bulk-recent-1321-1320-sapbert-cls`, passed the comparable
8-query quality gate at `0.750` mean weighted P@5 with mean MRR `1.0` and
`8 / 8` relevant top-1 queries, and was then added to the cumulative
`qe-scaling-sapbert-cls` alias. A harder 10-query mixed clinical smoke pass
also had `10 / 10` relevant top-1 queries, but lower mean weighted P@5 (`0.570`)
from generic follow-up, anatomy, and denied-positive lower-rank hits.

The previous three reviewed two-file pilots were: `1327/1326` and `1325/1324`
at `0.600` mean weighted P@5, then `1323/1322` at `0.750` after the
anchor-recall, fragment-precision, procedure-neighbor, composite-context, and
sepsis-shock intent ranker updates. The broader scale path remains full PubMed
baseline/update bulk ingest, run as bounded resumable shards with manifests and
quality gates. Remaining ranking cleanup is mostly below-rank-1 specificity and
component-heavy mixed queries.

A sound full-scale path should:

1. Download PubMed baseline and update files with manifests and MD5 checks.
2. Stream-parse XML into compact corpus records.
3. Link documents through profile shards without holding all PubMed in memory.
4. Aggregate evidence into CUI/view documents.
5. Re-embed only new or changed CUI/view documents where possible.
6. Export sharded Elasticsearch bulk files.
7. Load into versioned indexes.
8. Move the cumulative alias only after quality review.
9. Preserve manifests so future changes can be incremental.
10. Keep provenance indexes display-scoped or shard-scoped; do not build a
    monolithic mention-level provenance database for all PubMed.

Expected storage should stay closer to the compact/reproducible path than the
naive JSONL-for-everything path. Keep full raw intermediates only when they are
needed for reproducibility or debugging.

## Documentation Maintenance

When the pipeline changes, update this file and
`docs/explain_like_im_5.md` in the same turn.

Update this file when:

- a new source is added
- a source is paused or removed
- a pipeline stage changes
- a new artifact becomes canonical
- Elasticsearch aliases or index names change
- vector model, pooling, dimensions, or sequence length change
- quality metrics change
- progress-plan steps change
- scale, runtime, or storage estimates change

At minimum, update:

- `Last updated`
- `Current State`
- `Current quality sample`
- `Current full-pipeline progress`
- `Scaling Plan`
