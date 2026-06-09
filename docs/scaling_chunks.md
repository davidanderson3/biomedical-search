# Scaling Chunks for the UMLS Semantic Evidence Index

These chunks build the successor search layer for UMLS: evidence-backed
SapBERT/CLS vectors, Elasticsearch indexes, provenance, and quality-review
artifacts. The chunks are additive because release-grade UMLS 2.0 artifacts
should be built, reviewed, and merged incrementally rather than regenerated as
one opaque batch.

The scaling loop should run in bounded chunks. Each chunk should finish in less
than 10 minutes on the local machine or stop at a clean intermediate artifact.

## Rules

- Fetch, link, aggregate, SapBERT/CLS embed, export, and load can be separate
  chunks.
- Prefer additive artifacts with a chunk name instead of overwriting the current
  baseline.
- Use small topic files first, then increase retmax or topic count after quality
  review.
- Keep DRG excluded.
- Keep the default chunk loop public-source only.
- After every chunk, check row counts and run a few search-quality queries before
  merging into the main artifact.
- Use `sapbert` or another CLS-pooled BERT provider for quality assessment.
  Hashing vectors are only a pipeline smoke test.
- Treat each chunk as a candidate release delta. It is not part of the successor
  product until search quality has been reviewed.

## Chunk 001: Gap Topics

Purpose: add a small amount of literature evidence for under-covered areas:
organisms, anatomy, genes/proteins, device safety, pathology, and molecular
testing.

Scope: PubMed and Europe PMC only.

Topic file:

```sh
config/scaling_chunk_001_gap_topics.tsv
```

Fetch outputs:

```sh
build/pubmed_scaling_chunk_001_gap_topics_corpus.jsonl
build/europepmc_scaling_chunk_001_gap_topics_corpus.jsonl
```

Link output directory:

```sh
build/profile_evidence_scaling_chunk_001_gap_topics/
```

Suggested chunk boundaries:

1. Fetch PubMed + Europe PMC topic corpora.
2. Link the chunk corpus through profile shards.
3. Build a chunk-only document/SapBERT vector/search export.
4. If quality is acceptable, merge the chunk evidence with the current baseline.

Success criteria:

- Fetch finishes under 10 minutes.
- Link finishes under 10 minutes.
- SapBERT/CLS embedding finishes under 10 minutes.
- No DRG sources.
- Search view shows source refs for evidence bullets.
- At least some new evidence lands in organisms, anatomy, and genes/proteins.

## Chunk 002: Common Clinical Language

Purpose: add breadth for common clinical search language across high-volume
conditions, symptoms, labs, imaging, pediatrics, oncology, psychiatry, renal,
liver, autoimmune, cardiopulmonary, and neurologic topics.

Scope: PubMed, Europe PMC, and PMC Open Access only.

Topic file:

```sh
config/scaling_chunk_002_common_clinical.tsv
```

Primary outputs:

```sh
build/scaling_chunk_002_common_clinical_concept_documents.jsonl
build/scaling_chunk_002_common_clinical_concept_vectors.sapbert_cls.jsonl
build/qe-scaling-chunk-002-common-clinical-sapbert-cls.elastic.bulk.part-*.ndjson
```

Elasticsearch:

```sh
qe-scaling-chunk-002-common-clinical-sapbert-cls
qe-scaling-sapbert-cls
```

The `qe-scaling-sapbert-cls` alias spans loaded SapBERT chunks and is the
preferred search target for cumulative assessment.

## Chunk 003: Abbreviation-Heavy Language

Purpose: add evidence around abbreviation-heavy clinical and biomedical queries
such as HFrEF, HFpEF, NSTEMI, COPD, DKA, CKD, TIA, SLE, NSCLC, UTI, MRI, GDM,
DOAC, PCI, CABG, TAVR, LVAD, and ECMO.

Scope: PubMed and Europe PMC only. Short abbreviations can be ambiguous, so this
chunk should get explicit quality review before merge.

Topic file:

```sh
config/scaling_chunk_003_abbreviation_language.tsv
```

Primary outputs:

```sh
build/scaling_chunk_003_abbreviation_language_concept_documents.jsonl
build/scaling_chunk_003_abbreviation_language_concept_vectors.sapbert_cls.jsonl
build/qe-scaling-chunk-003-abbreviation-language-sapbert-cls.elastic.bulk.part-*.ndjson
```

Elasticsearch:

```sh
qe-scaling-chunk-003-abbreviation-language-sapbert-cls
qe-scaling-sapbert-cls
```

## Chunk 004: Drug Safety and Therapeutics

Purpose: add evidence for medication safety, adverse reactions, drug classes,
therapeutic use, renal dosing, pregnancy/lactation medication questions, and
high-value drug domains such as anticoagulation, diabetes therapy, oncology
therapy, antimicrobials, immunosuppression, psychiatry, neurology, and pain.

Scope: PubMed and Europe PMC only.

Topic file:

```sh
config/scaling_chunk_004_drug_safety_therapeutics.tsv
```

Primary outputs:

```sh
build/scaling_chunk_004_drug_safety_therapeutics_concept_documents.jsonl
build/scaling_chunk_004_drug_safety_therapeutics_concept_vectors.sapbert_cls.jsonl
build/qe-scaling-chunk-004-drug-safety-therapeutics-sapbert-cls.elastic.bulk.part-*.ndjson
```

Elasticsearch:

```sh
qe-scaling-chunk-004-drug-safety-therapeutics-sapbert-cls
qe-scaling-sapbert-cls
```

## Chunk 005: Diagnostics, Procedures, and Devices

Purpose: add evidence for imaging, invasive procedures, biopsies, laboratory
diagnostics, critical care devices, orthopedic devices, neurologic devices,
women's health procedures, urologic procedures, and device complications.

Scope: PubMed and Europe PMC only.

Topic file:

```sh
config/scaling_chunk_005_diagnostics_procedures_devices.tsv
```

Primary outputs:

```sh
build/scaling_chunk_005_diagnostics_procedures_devices_concept_documents.jsonl
build/scaling_chunk_005_diagnostics_procedures_devices_concept_vectors.sapbert_cls.jsonl
build/qe-scaling-chunk-005-diagnostics-procedures-devices-sapbert-cls.elastic.bulk.part-*.ndjson
```

Elasticsearch:

```sh
qe-scaling-chunk-005-diagnostics-procedures-devices-sapbert-cls
qe-scaling-sapbert-cls
```

## PubMed Bulk Recent Baseline Pilot

Purpose: validate the bulk-download path before attempting all of PubMed.
Topic search is useful for fast iteration, but full biomedical coverage should
come from PubMed baseline and update files.

Current pilot input:

```sh
data/pubmed/baseline/pubmed26n1334.xml.gz
```

Primary outputs:

```sh
build/pubmed_bulk_recent_baseline_corpus.jsonl
build/profile_evidence_pubmed_bulk_recent_baseline/*.jsonl
build/pubmed_bulk_recent_baseline_concept_documents.jsonl
build/pubmed_bulk_recent_baseline_concept_vectors.sapbert_cls.jsonl
build/scaling_runs/pubmed_bulk_recent_baseline/search_quality_judgments.csv
build/scaling_runs/pubmed_bulk_recent_baseline/search_quality_summary.json
```

Current quality sample:

```text
queries: 8
judgments: 40
mean weighted P@5: 0.575
mean MRR: 1.0
relevant top-1 queries: 6 / 8
```

After quality review, the eventual scaling target is full PubMed
baseline/update bulk ingest with manifests, resume support, and incremental
changed-document re-embedding.

## PubMed Bulk Recent Next-Two-Shards Pilot

Purpose: increase the bulk-ingest scale from one unusually small high-numbered
baseline file to two larger recent baseline files while keeping the work small
enough to inspect.

Current pilot inputs:

```sh
data/pubmed/baseline/pubmed26n1333.xml.gz
data/pubmed/baseline/pubmed26n1332.xml.gz
```

Primary outputs:

```sh
build/pubmed_bulk_recent_next2_corpus.jsonl
build/profile_evidence_pubmed_bulk_recent_next2/*.jsonl
build/pubmed_bulk_recent_next2_concept_documents.jsonl
build/pubmed_bulk_recent_next2_concept_vectors.sapbert_cls.jsonl
build/scaling_runs/pubmed_bulk_recent_next2/progress.md
```

Current scale:

```text
corpus documents: 59,859
linked evidence records: 804,542
CUI/view documents: 54,906
SapBERT vectors: 54,906
Elasticsearch alias count after load: 108,703
```

Operational note: bulk parts around 195 MB failed locally with a broken pipe.
Re-exporting into 11 parts of about 38-39 MB loaded successfully. Keep local
bulk exports near 5,000 documents per part unless Elasticsearch HTTP limits are
tuned.

Next step: review search quality for this new chunk before adding more PubMed
baseline files.

Reviewed quality sample:

```text
queries: 8
judgments: 40
mean weighted P@5: 0.588
mean MRR: 1.0
relevant top-1 queries: 7 / 8
```

This was acceptable for continuing with another small PubMed bulk chunk.

## PubMed Bulk Recent Shards 1331 and 1330

Purpose: continue bounded PubMed bulk scaling with the next two high-numbered
2026 baseline files after `pubmed_bulk_recent_next2`.

Current pilot inputs:

```sh
data/pubmed/baseline/pubmed26n1331.xml.gz
data/pubmed/baseline/pubmed26n1330.xml.gz
```

Primary outputs:

```sh
build/pubmed_bulk_recent_1331_1330_corpus.jsonl
build/profile_evidence_pubmed_bulk_recent_1331_1330/*.jsonl
build/pubmed_bulk_recent_1331_1330_concept_documents.jsonl
build/pubmed_bulk_recent_1331_1330_concept_vectors.sapbert_cls.jsonl
build/scaling_runs/pubmed_bulk_recent_1331_1330/progress.md
```

Current scale:

```text
corpus documents: 59,892
linked evidence records: 797,823
CUI/view documents: 55,216
SapBERT vectors: 55,216
Elasticsearch alias count after load: 163,919
assessment-server evidence refs after load, before efficiency gate: 1,891,603
assessment-server startup time after load, before efficiency gate: 134s
```

Reviewed quality sample:

```text
queries: 8
judgments: 40
mean weighted P@5: 0.575
mean MRR: 1.0
relevant top-1 queries: 7 / 8
```

This passed the small top-1 quality gate, but lower-rank noise increased for
appendectomy, sepsis, and organism-adjacent queries. Before adding many more
PubMed files, move provenance lookup out of eager JSONL loading and into an
indexed/on-demand store.

## Efficiency Gate: Indexed Provenance and Compact Vectors

Purpose: remove the assessment-server startup bottleneck and define smaller
release-shaped artifacts before continuing toward full PubMed.

Primary outputs:

```sh
build/search_quality_provenance.sqlite
build/compact_vectors/*.manifest.json
build/compact_vectors/*.vectors.f32
build/compact_vectors/*.metadata.jsonl
build/scaling_runs/indexed_provenance_compact_storage.marker
```

Current efficiency result after the latest provenance refresh:

```text
raw linked evidence rows considered: 2,718,077
indexed display source refs: 667,003
concept docs with indexed provenance: 117,056
provenance index size: 304 MB
compact vector artifact size: 787 MB
assessment-server startup before: 134.309s
assessment-server startup after: 33.616s
```

The provenance index intentionally stores only what the search-quality UI can
display: the first six evidence bullets per concept document and up to five
source citations per bullet. The lookup key is a 128-bit hash of normalized
evidence text, so the index does not store the full evidence text as a key.

This gate is complete. The next scaling step can move to full PubMed
baseline/update ingestion, but it should keep this shape: chunked downloads,
streamed linking, display-scoped provenance, compact vectors, Elasticsearch
bulk parts around 5,000 documents, and quality review before alias promotion.

## PubMed Bulk Recent Shards 1329 and 1328

Purpose: continue bounded PubMed bulk scaling with the next two high-numbered
2026 baseline files after `pubmed_bulk_recent_1331_1330`, while using the
indexed provenance and compact-vector efficiency path.

Current pilot inputs:

```sh
data/pubmed/baseline/pubmed26n1329.xml.gz
data/pubmed/baseline/pubmed26n1328.xml.gz
```

Primary outputs:

```sh
build/pubmed_bulk_recent_1329_1328_corpus.jsonl
build/profile_evidence_pubmed_bulk_recent_1329_1328/*.jsonl
build/pubmed_bulk_recent_1329_1328_concept_documents.jsonl
build/pubmed_bulk_recent_1329_1328_concept_vectors.sapbert_cls.jsonl
build/compact_vectors/pubmed_bulk_recent_1329_1328_sapbert_cls.manifest.json
build/scaling_runs/pubmed_bulk_recent_1329_1328/progress.md
```

Current scale:

```text
corpus documents: 59,980
linked evidence records: 822,419
CUI/view documents: 55,448
SapBERT vectors: 55,448
Elasticsearch alias count after load: 219,367
assessment-server display provenance refs: 667,003
assessment-server startup time after load: 33.616s
```

Reviewed quality sample:

```text
queries: 8
judgments: 40
mean weighted P@5: 0.613
mean MRR: 1.0
relevant top-1 queries: 6 / 8
```

This passed the small review gate, with the same persistent caveat as earlier
chunks: exact-label fallback is strong, but lower-rank noise remains for sepsis,
appendectomy, and broad asthma-related queries.

## PubMed Bulk Recent Shards 1327 Through 1322

Purpose: continue bounded PubMed bulk scaling with three more two-file 2026
baseline pilots after `pubmed_bulk_recent_1329_1328`.

Reviewed quality samples:

```text
1327/1326: queries 8, judgments 40, mean weighted P@5 0.600, mean MRR 1.0, relevant top-1 6 / 8
1325/1324: queries 8, judgments 40, mean weighted P@5 0.600, mean MRR 1.0, relevant top-1 6 / 8
1323/1322: queries 8, judgments 40, mean weighted P@5 0.750, mean MRR 1.0, relevant top-1 8 / 8
```

All three passed the small continuation gate. The `1323/1322` sample was
clearly above the earlier `1329/1328` score of `0.613` after ranker changes
that retrieve exact query-anchor labels, preserve vector evidence when labels
enrich an existing hit, demote anatomy-only fragments in multi-anchor clinical
queries, add related procedure-neighbor candidates for exact procedure anchors,
prefer composite clinical evidence over duplicate component labels, and promote
sepsis-shock concepts for sepsis queries with hemodynamic-treatment anchors. A
follow-up component-noise pass now keeps lactate/vasopressor-only hits below the
top 5 for the sepsis composite query. A mixed-query smoke pass also found and
mitigated denial-scope noise: the ranker now searches negated labels and
penalizes positive findings when the query says symptoms are denied. The stable
remaining failure modes are below-rank-1 related-concept specificity and
component-heavy mixed queries, where top results may still be correct components
rather than the combined diagnosis, adverse event, or treatment concept.

## PubMed Bulk Recent Shards 1321 And 1320

Purpose: continue bounded PubMed bulk scaling with the next two high-numbered
2026 baseline files after `pubmed_bulk_recent_1323_1322`.

Current pilot inputs:

```sh
data/pubmed/baseline/pubmed26n1321.xml.gz
data/pubmed/baseline/pubmed26n1320.xml.gz
```

Primary outputs:

```sh
build/pubmed_bulk_recent_1321_1320_corpus.jsonl
build/profile_evidence_pubmed_bulk_recent_1321_1320/*.jsonl
build/pubmed_bulk_recent_1321_1320_concept_documents.jsonl
build/pubmed_bulk_recent_1321_1320_concept_vectors.sapbert_cls.jsonl
build/compact_vectors/pubmed_bulk_recent_1321_1320_sapbert_cls.manifest.json
build/qe-scaling-pubmed-bulk-recent-1321-1320-sapbert-cls.elastic.mapping.json
build/qe-scaling-pubmed-bulk-recent-1321-1320-sapbert-cls.elastic.bulk.part-*.ndjson
build/scaling_runs/pubmed_bulk_recent_1321_1320/progress.md
```

Current scale:

```text
corpus documents: 59,881
linked evidence records: 821,042
CUI/view documents: 55,371
SapBERT vectors: 55,371
compact float32 vectors: 55,371
Elasticsearch bulk parts: 12
Elasticsearch index records: 55,371
```

Reviewed quality sample:

```text
queries: 8
judgments: 40
mean weighted P@5: 0.750
mean MRR: 1.0
relevant top-1 queries: 8 / 8
```

This batch passed the comparable continuation gate and was added to the
`qe-scaling-sapbert-cls` cumulative alias. A separate 10-query mixed clinical
smoke pass also returned relevant top-1 for all 10 queries, with lower mean
weighted P@5 (`0.570`) from generic follow-up, anatomy, and denied-positive
lower-rank hits.

For the full current technical state, use:

```sh
docs/technical_pipeline.md
docs/explain_like_im_5.md
```
