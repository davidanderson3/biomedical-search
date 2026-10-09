# UMLS Search Appliance Reproduction Specification

This folder describes the production search appliance, not its evaluation or
benchmark tooling. It is intended to give another developer enough information
to rebuild the data model, indexes, and query path.

## Short version

The appliance accepts a word, phrase, UMLS identifier, vocabulary code,
paragraph, abstract, or clinical note and returns ranked UMLS concepts.

The current implementation uses:

- SapBERT to create one 768-dimensional vector for each search document and
  each incoming free-text query.
- Elasticsearch kNN to retrieve semantically similar search documents.
- SQLite sidecar databases for exact label/code resolution and for attaching
  definitions, semantic types, relationships, and citations.
- Python code to merge candidates by CUI, add exact and structured candidates,
  rerank them, apply filters, and build the API response.

SQLite is not the semantic-search fallback. The code contains a local vector
scan fallback, but the packaged Docker deployment starts with
`--require-elasticsearch`, so that fallback is disabled.

For a new implementation, the recommended design is Elasticsearch-only at
runtime. Use several purpose-specific Elasticsearch indices instead of one
large nested document. SQLite may still be convenient as an intermediate build
format, but it does not need to be part of the serving path.

## Runtime architecture

```text
UMLS + permitted evidence sources
              |
              v
    normalized evidence records
              |
              v
  one search document per (CUI, view)
              |
       +------+------+
       |             |
       v             v
  SapBERT vector   result details
       |             |
       v             v
 search-documents  search-details
 Elasticsearch     Elasticsearch

UMLS labels/codes/types/definitions --> concepts Elasticsearch index
UMLS and derived relationships ------> relations Elasticsearch index

Query --> exact resolver + SapBERT kNN --> merge by CUI --> hybrid rerank
      --> filters --> batched detail hydration --> API response
```

## Two valid reproduction targets

### Faithful reproduction of the current application

Use the current Elasticsearch vector index plus the SQLite databases described
under [Why the current application uses SQLite](#why-the-current-application-uses-sqlite).
This is the lowest-risk approach if the goal is to match the current behavior.

The main implementation references are:

- `src/qe_evidence_vectors/documents.py`: search-document aggregation and text
  construction.
- `src/qe_evidence_vectors/embeddings.py`: SapBERT tokenization, CLS pooling,
  and normalization.
- `src/qe_evidence_vectors/elastic_export.py`: Elasticsearch document and
  mapping generation.
- `src/qe_evidence_vectors/search_execution.py`: end-to-end request routing,
  kNN retrieval, filtering, and response assembly.
- `src/qe_evidence_vectors/search_rerank.py`: lexical, definition, code, and
  relation candidate merging.
- `src/qe_evidence_vectors/search_ranking.py`: the complete production ranking
  formula and domain-specific controls.
- `scripts/start_search_quality_server.sh`: the exact runtime configuration.

### Recommended clean reproduction

Use Elasticsearch for the entire runtime path:

1. `search-documents`: one lean vector document per `(CUI, view)`.
2. `concepts`: one document per CUI with labels, identifiers, codes,
   definitions, and semantic types.
3. `relations`: one document per directed relationship edge.
4. `search-details`: one document per `(CUI, view)` containing display text,
   evidence excerpts, and citations.

This keeps vector retrieval fast while removing the dual Elasticsearch/SQLite
serving architecture. Candidate hydration should use `_mget` or one batched
terms query rather than one request per result.

The mappings in `elasticsearch/` implement this layout.

## Input data

A functionally equivalent build needs the following UMLS data, subject to the
applicable UMLS and source-vocabulary licenses:

| Input | Runtime purpose |
| --- | --- |
| MRCONSO | CUIs, labels, synonyms, source abbreviations, codes, AUIs, SCUIs, SDUIs, term types, preferred/suppressed flags |
| MRSTY | Semantic types and semantic-group assignment |
| MRDEF | Definitions and definition text matching |
| MRREL | Related concepts and optional ranking support |
| MRSAT or other identifier files, if used | Legacy or source-specific identifier resolution |
| Permitted evidence corpora | Evidence-backed text used to create semantic search documents |

The evidence corpus is optional for a minimal UMLS-only search engine. It is
required to reproduce the current `UMLS + evidence` behavior.

## Evidence record specification

Evidence is normalized before it is aggregated into search documents. A
normalized evidence record has this logical form:

```json
{
  "evidence_id": "stable source-specific identifier",
  "cui": "C0018801",
  "text": "A bounded excerpt associated with the concept.",
  "source": "pubmed",
  "evidence_type": "clinical_context",
  "weight": 1.0,
  "metadata": {
    "pmid": "12345678",
    "title": "Optional source title"
  }
}
```

Required invariants:

- `evidence_id` is stable across rebuilds.
- `cui` is already resolved. Search-document construction is not the place to
  guess an unresolved concept.
- `text` is the bounded text that may be displayed and embedded.
- `source` is a stable machine key, not a presentation label.
- `evidence_type` determines the document view.
- `weight` is finite and positive. It is used for deduplication and ordering;
  it is not an Elasticsearch document score.
- Citation and license metadata remain associated with the source record.

## Search document specification

### Granularity

The unit of semantic retrieval is one document per `(cui, view)`, not one
document per CUI. One CUI can therefore have several vectors representing
different contexts, such as literature, clinical prose, drugs, or procedures.

The stable identifier is:

```text
doc_id = "<cui>:<view>"
```

The Elasticsearch `_id` must equal `doc_id`.

### Required fields

| Field | Type | Meaning |
| --- | --- | --- |
| `doc_id` | string | Stable unique key for the CUI/view document |
| `cui` | string | UMLS concept identifier or governed local concept identifier |
| `view` | string | Stable context/category key |
| `text` | string | Canonical text passed to SapBERT |
| `evidence_count` | integer | Number of source evidence rows before the display cap |
| `sources` | string array | Deduplicated source keys represented by the document |
| `labels` | string array | Ordered labels; preferred display label first where possible |
| `metadata` | object | Builder and lineage metadata |

The machine-readable definition is
[`concept-document.schema.json`](concept-document.schema.json), and a concrete
record is in [`concept-document.example.json`](concept-document.example.json).

### Canonical text

The current implementation embeds this exact structure:

```text
CUI: <cui>
Evidence view: <view>
UMLS labels:
- <preferred label>
- <synonym 1>
- <synonym 2>
Real-world evidence:
- <highest-weight unique evidence text>
- <next evidence text> (weight 1.5)
```

Construction rules:

1. Group evidence by `(cui, normalized evidence view)`.
2. Normalize evidence text for deduplication.
3. For duplicate normalized text, retain the record with the highest weight.
4. Sort retained records by descending weight, then text.
5. Keep at most 100 evidence items per document.
6. Attach at most eight ordered UMLS labels in the current build.
7. Set `evidence_count` to the number of input rows, not the number retained
   after deduplication and capping.
8. Set `sources` to the sorted distinct source keys of the retained records.
9. Set `metadata.total_weight` to the sum of all input weights.
10. Preserve citation lookup data separately or embed it in `search-details`.

The line headings and list markers matter in a faithful reproduction because
the runtime parser recognizes `Real-world evidence:` or
`Open literature evidence:` followed by lines beginning with `- `.

### Views

The current generic view conversion lowercases and underscore-normalizes the
evidence type, with these special cases:

- Query-like evidence becomes `query_language`.
- Prose, note, and patient-language evidence becomes `prose_evidence`.
- Source-specific pipelines may create more specific views such as
  `pubmed_clinical_context`.

View names must be stable. Changing a view changes `doc_id`, which causes a new
vector document and invalidates cached details.

## Embedding specification

The production embedding signature is:

| Setting | Value |
| --- | --- |
| Model | `cambridgeltl/SapBERT-from-PubMedBERT-fulltext` |
| Implementation | Hugging Face `AutoTokenizer` and `AutoModel` |
| Pooling | First token from `last_hidden_state` (`CLS`) |
| Dimensions | 768 |
| Maximum sequence length | 128 tokens |
| Truncation | Enabled |
| Padding | Per batch |
| Vector normalization | L2 normalization |
| Elasticsearch similarity | Cosine |

The query and document encoder must be identical. A different tokenizer,
pooling method, maximum length, normalization method, model revision, or text
template creates a different vector space and requires a complete re-embed.

Store an embedding signature with each build:

```json
{
  "model": "cambridgeltl/SapBERT-from-PubMedBERT-fulltext",
  "pooling": "cls",
  "dimensions": 768,
  "max_sequence_length": 128,
  "normalized": true,
  "document_template_version": "cui-view-evidence-v1"
}
```

For deterministic incremental builds, also store a SHA-256 hash of the exact
canonical text and reuse a vector only when both the text hash and embedding
signature match.

## Elasticsearch schemas

The folder contains these create-index request bodies:

- [`elasticsearch/search-documents-index.json`](elasticsearch/search-documents-index.json):
  vector retrieval index.
- [`elasticsearch/concepts-index.json`](elasticsearch/concepts-index.json):
  CUI, exact labels, source codes, definitions, and semantic types.
- [`elasticsearch/relations-index.json`](elasticsearch/relations-index.json):
  directed relation edges.
- [`elasticsearch/search-details-index.json`](elasticsearch/search-details-index.json):
  display text, evidence, and citation payloads.

Example HTTP requests are in
[`elasticsearch/requests.http`](elasticsearch/requests.http).

### Vector index rules

- `_id` is exactly `doc_id`.
- `vector` contains exactly 768 finite numbers.
- Do not return `vector` in normal search responses. Use `_source.excludes`.
- `cui`, `doc_id`, `view`, and `sources` are `keyword` fields.
- `labels` supports both full text and exact keyword access.
- Use one primary shard and zero replicas for a single-machine appliance.
  Production clusters should set shard and replica counts for their topology.
- Bulk-load with refresh disabled, refresh once, then restore the normal refresh
  interval.
- Put a version in the physical index name and expose it through an alias.

The current packaged index contains approximately 190,051 active Elasticsearch
documents. The source vector shards contain 474,543 rows, but repeated
`doc_id` values overwrite earlier rows during indexing. A clean rebuild should
resolve duplicates before indexing and record which source row won rather than
depending silently on bulk-load order.

## Detailed query logic

### 1. Normalize the request

- Trim the query and apply the same Unicode, case, punctuation, and lexical
  normalization used when creating label/code keys.
- Normalize options such as result depth, search mode, semantic groups, source
  vocabulary selection, and whether related concepts are requested.
- Check a bounded response cache using the normalized query and all options.
- Reject empty or explicitly blocked generic queries.

### 2. Resolve identifiers before semantic search

Try deterministic lookups in this order:

1. Exact CUI or governed local concept identifier.
2. UMLS identifiers such as AUI, TUI, ATUI, or RUI when supported.
3. A source-qualified code such as `RXNORM:12345`.
4. An unqualified code when it resolves unambiguously or the requested source
   vocabulary constrains it.

If a direct identifier resolves, return or rank those concepts without forcing
the identifier string through SapBERT.

In the Elasticsearch-only design, these are `term` or nested `term` queries
against `concepts`, using precomputed normalized keyword fields.

### 3. Build free-text retrieval inputs

- The complete query is always an embedding input.
- For long text, identify bounded sections or chunks and embed them separately.
- Keep chunk positions, section names, and weights so chunk hits can later
  support the corresponding concept rather than becoming unrelated results.
- Extract exact phrase/code/label candidates independently of embeddings.

### 4. Run vector retrieval

Embed all retrieval inputs with the same SapBERT configuration used for the
documents. Run approximate kNN against `search-documents`.

Current defaults:

- Requested result depth: usually 60.
- Candidate pool: at least `max(top_k, 40)` in balanced mode.
- Elasticsearch `num_candidates`: at least the candidate pool and normally 50
  in the packaged launcher.
- Similarity: cosine over normalized vectors.

Retrieve only lean metadata. Exclude the vector and large detail fields.

### 5. Collapse document hits to concepts

Several CUI/view documents can represent the same concept. Keep the highest
vector-scoring document for each CUI as the initial concept candidate, while
retaining provenance about the winning view and document.

Do not return multiple result rows for the same CUI unless the API explicitly
exposes views as separate results.

### 6. Add exact and structured candidates

Search the `concepts` index for:

- Exact or high-coverage normalized label spans.
- Clinical spelling and abbreviation variants.
- Exact codes and identifiers.
- Definition full-text matches for sufficiently specific multi-token queries.
- Optional relation-anchored candidates when an exactly matched concept
  supports a related concept.

Merge these candidates into the same map keyed by CUI. Exact evidence enriches
an existing vector hit; it should not create a duplicate result row.

### 7. Rerank the merged concepts

The production implementation is a hybrid rule-based reranker. Its score is
not the raw Elasticsearch kNN score. The broad shape is:

```text
rank score =
    lexical label relevance
  + bounded vector component
  + exact label/name/span/code boosts
  + definition and relationship support
  + evidence and long-document support
  + semantic/context/specificity boosts
  - generic, mismatch, negation, fragment, and ambiguity penalties
```

Important current details:

- The raw cosine score is converted to a bounded component; it does not
  dominate exact biomedical identity signals.
- Exact primary-name and exact span matches receive strong boosts.
- A result with evidence gets a small positive component; a concept with no
  evidence is penalized in the evidence-backed search scope.
- Semantic types and query context are used to suppress role mismatches, such
  as a procedure fragment winning a disease-oriented query.
- Negation, family history, numeric specificity, and long-document support are
  handled explicitly.
- Results receive a confidence annotation and can be removed by an
  evidence-aware cutoff.

For bit-for-bit ranking parity, reuse or port
`src/qe_evidence_vectors/search_ranking.py`. A simpler reimplementation can
start with lexical relevance, exact-match boosts, normalized vector similarity,
definition support, and semantic-type compatibility, but its ranking will not
match the current appliance.

### 8. Filter and select

- Apply exact/balanced mode rules.
- Apply semantic-group filters.
- Remove results below the configured relevance threshold.
- Apply public-output and vocabulary-license rules.
- Select the requested number of distinct CUIs.

### 9. Hydrate only the selected results

Use one `_mget` or batched terms query per index to attach:

- Preferred label and accepted synonyms.
- Semantic types and semantic group.
- Requested source-vocabulary code mappings.
- Definitions.
- Evidence excerpts and citations.
- Related concepts when requested.

Never perform one Elasticsearch request per result. Batch by the selected CUI
and `doc_id` values.

### 10. Return a compact response

The first response should contain identifiers, names, scores, semantic types,
matching reason, confidence, and small evidence summaries. Large definitions,
relation sets, images, and citation collections should be lazy-loaded by a
detail endpoint.

Minimum public endpoints:

- `GET /api/health`
- `GET /api/search`
- `GET /api/resolve`
- `GET /api/detail`
- `GET /api/related`
- `GET /api/openapi.json`

## Why the current application uses SQLite

The current runtime separates approximate search from structured lookup:

| SQLite data | Where it is used |
| --- | --- |
| Normalized labels | Exact/span candidate generation and mention extraction |
| CUI/code/identifier mappings | Direct resolution and returned code mappings |
| Semantic types | Filtering, reranking, and response hydration |
| Definitions and FTS | Definition candidate generation and detail hydration |
| UMLS and research relations | Related-concept expansion and optional ranking support |
| Provenance | Citation lookup for displayed evidence text |

Reasons this was reasonable for the packaged local application:

- The UMLS lookup tables are immutable during a release and are naturally
  represented as compact read-only files.
- Exact point/range lookups happen in-process without an Elasticsearch network
  round trip.
- SQLite makes the licensed UMLS payload easy to package, inspect, and replace.
- The vector index stays small and focused on kNN retrieval.
- The original application evolved from file and SQLite artifacts before the
  Elasticsearch serving layer was added.

Costs of that choice:

- Two storage technologies must be built, versioned, deployed, and kept in
  sync.
- The application loads 474,543 vector metadata rows and document details at
  startup even though Elasticsearch performs retrieval.
- Runtime behavior depends on several large sidecar files.
- Updates and horizontal scaling are more complicated.

The logical DDL of the current runtime stores is included in
[`sqlite/current-runtime-schema.sql`](sqlite/current-runtime-schema.sql).

## Is Elasticsearch-only efficient?

Yes, provided the indices are separated and hydration is batched.

At the current scale—roughly 190,000 active vector documents, 7 million label
rows, 9 million code-mapping rows, 3.9 million semantic-type rows, about
636,000 primary relation rows, and 1.5 million provenance links—Elasticsearch
can comfortably serve both semantic and exact retrieval on an appropriately
sized local node.

Expected tradeoffs:

- Elasticsearch exact `keyword` queries are fast but consume more disk and
  heap than SQLite B-trees.
- A local SQLite point lookup can have lower single-call latency because it is
  in-process.
- Elasticsearch removes startup loading and multiple-file coordination, and it
  scales and updates more cleanly.
- The vector index must remain lean; large evidence and relation payloads
  belong in separate indices.

Efficiency requirements for the Elasticsearch-only version:

1. Use precomputed normalized keyword fields for exact matching.
2. Use nested fields only where field pairing matters, especially `sab + code`.
3. Keep vectors out of returned `_source`.
4. Collapse by CUI before detail hydration.
5. Batch `_mget` and terms queries.
6. Cache repeated exact resolutions and concept hydration.
7. Use versioned indices and atomically switch aliases after a complete load.
8. Measure shard size before adding shards; one shard is appropriate for the
   current single-node vector index.

## Build sequence

1. Select and record the UMLS release and permitted source vocabularies.
2. Parse UMLS inputs into normalized concepts, labels, codes, types,
   definitions, and relations.
3. Normalize and license-filter evidence records.
4. Resolve every retained evidence record to a governed CUI.
5. Aggregate evidence into stable `(CUI, view)` search documents.
6. Validate the documents with `validate_concept_documents.py`.
7. Embed canonical document text with the pinned SapBERT configuration.
8. Create versioned Elasticsearch indices from the supplied mappings.
9. Bulk-load search documents, concepts, relations, and details.
10. Refresh and verify counts, uniqueness, vector dimensions, and embedding
    signatures.
11. Point aliases at the new indices.
12. Start the API with the same model and text normalization configuration.

## Reproducibility invariants

A build should fail if any of these checks fail:

- Duplicate final `doc_id` values.
- A `doc_id` whose CUI or view disagrees with its fields.
- Empty CUI, view, text, or labels where the selected profile requires labels.
- Non-finite or non-768-dimensional vectors.
- Mixed embedding signatures in one index.
- A vector whose recorded text hash differs from the canonical document.
- A relation whose source or target CUI is absent from the governed concept set,
  unless external targets are explicitly allowed.
- Citation payloads that cannot be tied to a document and evidence-text hash.
- A physical index count that differs from the final unique document count.

Run the included validator with:

```sh
python3 docs/search-appliance-reproduction/validate_concept_documents.py \
  build/scaling_chunk_001_gap_topics_concept_documents.jsonl.gz
```

## Artifact inventory

| Artifact | Purpose |
| --- | --- |
| `concept-document.schema.json` | Machine-readable source document contract |
| `concept-document.example.json` | Concrete canonical document example |
| `validate_concept_documents.py` | Standard-library JSON/JSONL/GZIP validator |
| `elasticsearch/search-documents-index.json` | Semantic retrieval mapping |
| `elasticsearch/concepts-index.json` | Exact resolver and concept catalog mapping |
| `elasticsearch/relations-index.json` | Relationship edge mapping |
| `elasticsearch/search-details-index.json` | Evidence and provenance detail mapping |
| `elasticsearch/requests.http` | Example create, load, resolve, kNN, and hydrate requests |
| `sqlite/current-runtime-schema.sql` | Current SQLite logical DDL for comparison |
