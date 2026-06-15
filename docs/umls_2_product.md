# UMLS 2.0 Product Plan

## Position

The UMLS Semantic Evidence Index is a successor architecture to the traditional
UMLS search experience. It does not discard UMLS. It uses UMLS CUIs as the
identity layer, then adds real-world biomedical language, semantic embeddings,
provenance, and evaluation on top.

Traditional UMLS artifacts answer:

- What strings and source vocabulary records are attached to this concept?
- How do concepts relate inside source vocabularies?

The successor product should answer:

- What UMLS concept best matches this biomedical query?
- Why did the system retrieve it?
- Which real-world evidence supports that match?
- How well does the retrieval layer perform on reviewed queries?

This project is not an official NLM UMLS release. It is a release design for a
UMLS 2.0-style product built on top of licensed UMLS inputs and public or
credentialed real-world evidence.

## Product Thesis

The next UMLS should be a semantic evidence index, not a bigger synonym table.
Search should be driven by biomedical BERT vectors, lexical signals, source
provenance, and measured relevance. Synonyms still matter, but they should serve
as anchors and metadata rather than the entire retrieval model.

## Core Release Artifacts

### 1. CUI/View Embedding Pack

One CUI should have multiple view vectors when the evidence language differs.
Examples:

- `pubmed_clinical_context`
- `europepmc_clinical_context`
- `pubmed_labs_measurements_context`
- `pubmed_procedures_devices_context`
- `open_guideline_context`, optional when source terms permit it
- `labels_only`, optional baseline

Each vector record should include:

- `doc_id`
- `cui`
- `view`
- vector dimensions and precision
- embedding model
- pooling method
- evidence count
- source list
- UMLS release

The current preferred embedding path is SapBERT/CLS:

```text
model: cambridgeltl/SapBERT-from-PubMedBERT-fulltext
pooling: CLS
dimensions: 768
```

### 2. Search Index Bundle

Release an Elasticsearch/OpenSearch-ready bundle and, later, a compact ANN index
for offline deployments.

Current index shape:

```text
dense_vector: 768 dimensions
similarity: cosine
metadata: CUI, view, labels, sources, evidence count, model
```

The index bundle should be loadable without rebuilding the source evidence.

### 3. Evidence Provenance Pack

Release provenance pointers, not uncontrolled full-text dumps. Public literature
provenance can include:

- PMID
- PMCID
- DOI
- source system
- matched UMLS label
- CUI
- evidence view
- evidence weight
- corpus document id

For credentialed clinical sources, release only what licensing and privacy
review allow. Raw patient text should not be part of a public artifact.

### 4. Related Concept Graph Pack

Search results should expose nearby concepts from UMLS relationships, not just
ranked vector hits. A compact graph pack can be derived from `MRREL.RRF` and
`MRCONSO.RRF`, restricted to CUIs present in the search product.

Each related-concept row should include:

- source CUI
- related CUI
- relationship code and RELA when available
- source vocabulary abbreviation
- direction
- display label
- rank within the source CUI

This is a navigation and review aid. It should not replace search relevance
judgments, and it should stay small enough to ship with the searchable product.

The search UI now also has a narrower research relation pack built from
`MRREL.RRF`, `MRCONSO.RRF`, `MRSTY.RRF`, and staged HPO annotation files. It
keeps cross-semantic-type links that researchers are likely to ask for directly:
conditions to drugs, genes or proteins, procedures or tests, phenotypes,
organisms, devices, safety causes, and the inverse directions for drug, gene,
and procedure searches. The current local build uses UMLS 2025AB plus HPO
annotations and stores `152,326` links in `build/umls_research_relations.sqlite`.

### 5. Extension Concept Registry

The successor product can include provisional extension concepts when evidence
shows a useful biomedical idea that UMLS does not cover cleanly. These records
must not be presented as official NLM UMLS CUIs. They use local `NEW#######`
CUIs and carry explicit governance metadata.

Each extension concept should include:

- local `NEW#######` CUI
- preferred label and useful aliases
- semantic type or local semantic class
- definition
- status: `candidate`, `reviewed`, `promoted`, `rejected`, or `deprecated`
- evidence count and provenance pointers
- broader, related, or close-match UMLS CUIs where available
- reviewer/rationale metadata

Extension concepts are useful only if they improve retrieval or coverage. They
should be embedded, searched, and judged through the same quality loop as UMLS
CUI/view documents. Human feedback can tune the loop, but human approval is not
required before creating a high-confidence local CUI.

### 6. Evaluation Benchmark

The benchmark is part of the product, not a side file. It should contain:

- reviewed biomedical queries
- expected CUI when known
- result judgments: relevant, partial, wrong
- query type: abbreviation, lay phrase, clinical phrase, literature phrase,
  lab/procedure/device, rare disease, organism, gene/protein
- metrics: P@5, MRR, recall@k

No release should be considered good solely because the pipeline ran. It needs
reviewed search quality.

### 7. Build Manifest

Every release should include a manifest with:

- UMLS release version
- source corpora and harvest dates
- query/topic files used for literature harvests
- model name, model hash if available, pooling method
- build command versions
- row counts
- file sizes
- file hashes
- known exclusions and restricted artifacts
- related-concept graph source and build parameters
- extension concept registry version and review policy

### 8. Delta Packs

The product should update through deltas:

- new corpus documents
- new linked evidence
- changed CUI/view documents
- changed vectors
- deleted or superseded records
- index alias updates

Users should not need to rebuild all of PubMed to accept a monthly update.

## Current Prototype Status

The living technical status is maintained in `docs/technical_pipeline.md`; the
plain-language status is maintained in `docs/explain_like_im_5.md`.

As of 2026-05-01, the current local prototype has five topic chunks plus seven
reviewed PubMed bulk baseline pilots loaded through the cumulative Elasticsearch
alias:

```text
qe-scaling-chunk-001-gap-topics-sapbert-cls
qe-scaling-chunk-002-common-clinical-sapbert-cls
qe-scaling-chunk-003-abbreviation-language-sapbert-cls
qe-scaling-chunk-004-drug-safety-therapeutics-sapbert-cls
qe-scaling-chunk-005-diagnostics-procedures-devices-sapbert-cls
pubmed bulk recent baseline vectors loaded into qe-scaling-sapbert-cls
pubmed bulk recent next-two vectors loaded into qe-scaling-sapbert-cls
pubmed bulk recent 1331/1330 vectors loaded into qe-scaling-sapbert-cls
pubmed bulk recent 1329/1328 vectors loaded into qe-scaling-sapbert-cls
pubmed bulk recent 1327/1326 vectors loaded into qe-scaling-sapbert-cls
pubmed bulk recent 1325/1324 vectors loaded into qe-scaling-sapbert-cls
pubmed bulk recent 1323/1322 vectors loaded into qe-scaling-sapbert-cls
pubmed bulk recent 1321/1320 vectors loaded into qe-scaling-sapbert-cls
```

The latest two-file pilot, `pubmed_bulk_recent_1321_1320`, is loaded and
reviewed:

```text
corpus documents: 59,881
linked evidence rows: 821,042
CUI/view documents: 55,371
SapBERT vectors: 55,371
compact float32 vector export: build/compact_vectors/pubmed_bulk_recent_1321_1320_sapbert_cls.manifest.json
Elasticsearch bulk export: 12 part files for qe-scaling-pubmed-bulk-recent-1321-1320-sapbert-cls
quality gate: 8 queries, 40 judgments, mean weighted P@5 0.750, mean MRR 1.0, relevant top-1 8 / 8
```

The cumulative assessment alias is:

```text
qe-scaling-sapbert-cls
```

Current cumulative scale:

```text
vector records loaded by latest assessment server: 533,540
Elasticsearch cumulative alias records: 535,683
full-tracker CUI/view document rows represented by artifacts: 516,028
indexed display provenance refs: 1,531,116
raw linked evidence rows in current artifacts: 10,093,683
embedding model: SapBERT-from-PubMedBERT-fulltext
pooling: CLS
dimensions: 768
search label index rows: 7,049,993
related-concept links: 483,677
assessment startup: 97.263s with indexed provenance and related-concept index, down from the earlier 134.309s eager-provenance path
```

The prototype now has an extension-concept lane. It can emit local
`NEW#######` concept documents, matching evidence records, and a registry for
concepts that UMLS does not cover cleanly. No extension concepts are loaded into
the current cumulative alias yet.

Last reviewed quality sample:

```text
queries: 8
judgments: 40
mean weighted P@5: 0.750
mean MRR: 1.0
relevant top-1 queries: 8 / 8
```

The latest reviewed chunk is `pubmed_bulk_recent_1321_1320`. The post-chunk
efficiency gate remains in place: the prototype has indexed display provenance
and compact float32 vector exports. The next processing step is targeted PubMed
weakness acquisition and promotion, not broad baseline expansion. The latest
reviewed batch matches the prior `1323/1322` quality gate (`0.750` mean weighted
P@5, MRR `1.0`, `8 / 8` relevant top-1). A harder 10-query mixed clinical smoke
pass also kept relevant top-1 for all 10 queries, but its mean weighted P@5 was
`0.570` because lower ranks still contain generic follow-up, anatomy, and
denied-positive concepts. Remaining cleanup is mostly related-concept
specificity below rank 1
and composite drug/adverse-event or diagnosis/lab queries where component
concepts still outrank the combined concept, so scale alone should not be
treated as quality improvement.

## Release Boundaries

Public release candidate:

- literature-derived vectors
- public provenance pointers
- index mappings and bulk exports
- benchmark queries and judgments
- build manifests
- reviewed extension concept registry, clearly marked as local/non-official

Restricted release candidate:

- credentialed-source vectors or aggregate evidence, only if licensing/privacy
  review approves
- reproducible scripts for credentialed users to build local-only artifacts

Do not release:

- raw patient text
- raw copyrighted full text unless licensing is settled
- hashing vectors as product quality vectors
- unreviewed synonym dumps presented as new terminology
- provisional extension concepts presented as official UMLS CUIs

## Success Criteria

The successor product is ready when:

- query review shows clear improvement over lexical UMLS search
- every result can show why it was retrieved
- evidence sources are traceable
- release artifacts can be loaded without running the whole pipeline
- updates can be applied incrementally
- noisy chunks are gated by evaluation, not blindly merged
