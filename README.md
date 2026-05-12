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

For the HTTP contract used by external clients and the browser UI, see
[Biomedical Concept Search API](docs/api.md). The server also exposes a
machine-readable OpenAPI document at `/api/openapi.json`.

The public-first rebuild entrypoint is:

```sh
python3 scripts/run_public_rebuild.py \
  --umls-meta /path/to/UMLS/META \
  --out-dir build/public \
  --provider hashing
```

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

### 2. Build a UMLS label index

This index is used only for anchoring real-world text spans to CUIs. You can keep
it broad, or restrict by semantic type to reduce ambiguous matches and runtime.

```sh
python3 scripts/evidence_vectors.py build-label-index \
  --mrconso ~/Downloads/2026AA/META/MRCONSO.RRF \
  --mrsty ~/Downloads/2026AA/META/MRSTY.RRF \
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
  --mrconso ~/Downloads/2026AA/META/MRCONSO.RRF \
  --mrsty ~/Downloads/2026AA/META/MRSTY.RRF \
  --profile clinical \
  --min-tokens 2 \
  --replace \
  --out build/umls_clinical_profile_multiword_label_index.sqlite

python3 scripts/evidence_vectors.py build-label-index \
  --mrconso ~/Downloads/2026AA/META/MRCONSO.RRF \
  --mrsty ~/Downloads/2026AA/META/MRSTY.RRF \
  --profile chemicals-drugs \
  --min-tokens 2 \
  --replace \
  --out build/umls_chemicals_drugs_profile_multiword_label_index.sqlite
```

To build the default production shards for biomedicine in one pass:

```sh
python3 scripts/evidence_vectors.py build-profile-indexes \
  --mrconso ~/Downloads/2026AA/META/MRCONSO.RRF \
  --mrsty ~/Downloads/2026AA/META/MRSTY.RRF \
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
  --mrconso ~/Downloads/2026AA/META/MRCONSO.RRF \
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
  --corpus build/pubmed_corpus.jsonl build/europepmc_corpus.jsonl build/pmc_oa_corpus.jsonl \
  --label-index build/umls_label_index.sqlite \
  --out build/corpus_evidence.jsonl \
  --matcher trie
```

Use `--matcher trie` for large corpora. It loads the label index once and scans
each document token stream, avoiding per-span SQLite lookups.

For broad biomedical linking, run the same corpus through each profile shard and
tag the output evidence by profile:

```sh
python3 scripts/evidence_vectors.py link-profile-shards \
  --corpus build/pubmed_corpus.jsonl build/europepmc_corpus.jsonl \
  --index-dir build/profile_indexes \
  --out-dir build/profile_evidence \
  --run-name pubmed_europepmc \
  --matcher trie
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
  --mrconso ~/Downloads/2026AA/META/MRCONSO.RRF \
  --out build/concept_documents.jsonl
```

For larger evidence sets, use the SQLite-backed builder instead of the in-memory
builder:

```sh
python3 scripts/evidence_vectors.py build-docs-sqlite \
  --evidence build/pubmed_corpus_evidence.jsonl build/europepmc_corpus_evidence.jsonl build/pmc_oa_corpus_evidence.jsonl \
  --mrconso ~/Downloads/2026AA/META/MRCONSO.RRF \
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
labels, sources, evidence count, and the vector. Use
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

### 8. Test retrieval locally

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

### 9. Export vectors for Elasticsearch kNN

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
- DailyMed, RxNorm/RxClass, LOINC, MeSH, NCI/NCIt, HPO, and other permitted
  public biomedical sources
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
