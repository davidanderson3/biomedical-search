# MedMentions Benchmark

MedMentions is now scaffolded as a separate external benchmark lane. It is not
part of the locked clinical smoke score or the 2026AB production count report.

## Source

- Repository: <https://github.com/chanzuckerberg/MedMentions>
- Paper: <https://arxiv.org/abs/1902.09476>
- Format: PubTator title/abstract documents with mention spans, semantic type
  IDs, and UMLS CUIs.
- Corpus size: 4,392 PubMed title/abstract documents.
- Current first lane: `st21pv`, the information-retrieval-oriented subset.

Important caveat: MedMentions was annotated against UMLS 2017AA. Our current
indexes may use newer UMLS releases, so exact CUI misses can include real
version drift, retired concepts, or changed source practice. Treat this as an
external linking stress test, not as proof that the current 2026AB production
data is wrong.

## What The Script Does

`scripts/run_medmentions_benchmark.py` has two subcommands:

- `prepare`: downloads MedMentions, parses PubTator, assigns train/dev/test
  splits using the official PMID split files, and writes query TSVs. Use
  `--category clinical_useful` to build the product-improvement target and
  `--category suppression_audit` to build the low-value concept audit. Use
  `--query-style mention_only` for a pure linker-quality probe and the default
  `--query-style mention_context` for context-heavy retrieval stress.
- `evaluate`: runs prepared TSVs against `/api/search` and reports top-k CUI
  hit rates, mean recall, MRR, linked-concept hit rate, latency, and per-row
  outputs. Summaries label `clinical_useful_target` as the improvement target
  and `suppression_audit_guardrail` as a surfacing-risk guardrail.

The prepared TSVs intentionally keep extra metadata columns while preserving
the standard `id`, `query`, `expected_cuis`, `why`, and `disallowed_cuis`
columns used by existing search-quality tooling.

## Categories

Raw MedMentions should not be optimized as one score because it rewards broad
UMLS coverage, including concepts that are not useful in a clinical search UI.
The benchmark now writes and scores categories separately:

- `clinical_useful`: disorders/findings, drugs/chemicals, anatomy,
  procedures, devices, organisms, genes/proteins, labs, and clinical
  attributes. This is the improvement target.
- `biomedical_broad`: biology and physiology process concepts that may be
  useful for research search but are too noisy for the default clinical score.
- `suppression_audit`: geographic, group/population, abstract activity,
  research, intellectual product, and other low-value concepts. This score is
  useful only as a demotion/suppression audit; a higher hit rate is not better
  for the product.

## Generated Sample

Created from the ST21pv dev split:

```bash
python3 scripts/run_medmentions_benchmark.py prepare \
  --subset st21pv \
  --split dev \
  --mention-limit 1000 \
  --document-limit 200 \
  --output-dir build/medmentions/st21pv_dev_sample
```

Manifest:

- `build/medmentions/st21pv_dev_sample/medmentions_manifest.json`

Prepared query files:

- `build/medmentions/st21pv_dev_sample/medmentions_st21pv_mention_queries.tsv`
- `build/medmentions/st21pv_dev_sample/medmentions_st21pv_document_queries.tsv`
- `build/medmentions/st21pv_dev_sample/medmentions_st21pv_combined_queries.tsv`

## Initial Results

Run against the live Elasticsearch-backed API on `http://127.0.0.1:8766`.

Mention-context sample:

```bash
python3 scripts/run_medmentions_benchmark.py evaluate \
  build/medmentions/st21pv_dev_sample/medmentions_st21pv_mention_queries.tsv \
  --base-url http://127.0.0.1:8766 \
  --top-k 10 \
  --scope umls_evidence \
  --linked \
  --limit 100 \
  --output-dir build/medmentions/st21pv_dev_sample/eval_mentions_100
```

Result: 100 queries, top-1 exact CUI hit rate 15.0%, top-3 29.0%, top-5
41.0%, top-10 45.0%, MRR 0.248095, linked expected rate 52.0%, mean latency
817.2 ms/query.

Document-level sample:

```bash
python3 scripts/run_medmentions_benchmark.py evaluate \
  build/medmentions/st21pv_dev_sample/medmentions_st21pv_document_queries.tsv \
  --base-url http://127.0.0.1:8766 \
  --top-k 100 \
  --scope umls_evidence \
  --linked \
  --limit 20 \
  --output-dir build/medmentions/st21pv_dev_sample/eval_documents_20
```

Result: 20 abstracts, top-100 found at least one expected CUI in every row,
mean recall@10 0.250910, mean recall@100 0.443692, top-1 first-expected hit
rate 70.0%, MRR 0.829167, linked expected rate 100.0%, mean latency
6659.4 ms/query.

Filtered category samples:

```bash
python3 scripts/run_medmentions_benchmark.py prepare \
  --subset st21pv \
  --split dev \
  --category clinical_useful \
  --mention-limit 1000 \
  --document-limit 200 \
  --output-dir build/medmentions/st21pv_dev_clinical_useful

python3 scripts/run_medmentions_benchmark.py evaluate \
  build/medmentions/st21pv_dev_clinical_useful/medmentions_st21pv_clinical_useful_mention_queries.tsv \
  --base-url http://127.0.0.1:8766 \
  --top-k 10 \
  --scope umls_evidence \
  --linked \
  --limit 100 \
  --output-dir build/medmentions/st21pv_dev_clinical_useful/eval_mentions_100
```

Clinical-useful result: 100 queries, top-1 exact CUI hit rate 11.0%, top-3
20.0%, top-5 32.0%, top-10 36.0%, MRR 0.187357, linked expected rate 53.0%,
mean latency 991.4 ms/query.

```bash
python3 scripts/run_medmentions_benchmark.py prepare \
  --subset st21pv \
  --split dev \
  --category suppression_audit \
  --mention-limit 1000 \
  --document-limit 200 \
  --output-dir build/medmentions/st21pv_dev_suppression_audit

python3 scripts/run_medmentions_benchmark.py evaluate \
  build/medmentions/st21pv_dev_suppression_audit/medmentions_st21pv_suppression_audit_mention_queries.tsv \
  --base-url http://127.0.0.1:8766 \
  --top-k 10 \
  --scope umls_evidence \
  --linked \
  --limit 100 \
  --output-dir build/medmentions/st21pv_dev_suppression_audit/eval_mentions_100
```

Suppression-audit result: 100 queries, top-1 exact CUI hit rate 15.0%, top-3
21.0%, top-5 23.0%, top-10 27.0%, MRR 0.185206, linked expected rate 36.0%,
mean latency 1108.5 ms/query. For this category, the useful direction is not
to increase the hit rate; it is to keep these concepts low-ranked unless the
user explicitly asks for broad UMLS linking.

## First Improvement Iteration

The context-heavy mention rows exposed a benchmark-shape problem: the search
query was `mention. Context: nearby sentence`, so abstract entities around the
mention often outranked the annotated span. Exact search mode did not fix this:
clinical-useful stayed at top-1 11.0% and top-10 36.0%; suppression-audit stayed
at top-1 15.0% and top-10 27.0%.

`--query-style mention_only` now isolates the linker task:

```bash
python3 scripts/run_medmentions_benchmark.py prepare \
  --subset st21pv \
  --split dev \
  --category clinical_useful \
  --query-style mention_only \
  --mention-limit 1000 \
  --document-limit 0 \
  --output-dir build/medmentions/st21pv_dev_clinical_useful_mention_only

python3 scripts/run_medmentions_benchmark.py evaluate \
  build/medmentions/st21pv_dev_clinical_useful_mention_only/medmentions_st21pv_clinical_useful_mention_only_mention_queries.tsv \
  --base-url http://127.0.0.1:8766 \
  --top-k 10 \
  --scope umls_evidence \
  --linked \
  --limit 100 \
  --output-dir build/medmentions/st21pv_dev_clinical_useful_mention_only/eval_mentions_100
```

Clinical-useful mention-only result: 100 queries, top-1 exact CUI hit rate
40.0%, top-3 45.0%, top-5 45.0%, top-10 45.0%, MRR 0.421667, linked expected
rate 48.0%.

Suppression-audit mention-only guardrail:

```bash
python3 scripts/run_medmentions_benchmark.py prepare \
  --subset st21pv \
  --split dev \
  --category suppression_audit \
  --query-style mention_only \
  --mention-limit 1000 \
  --document-limit 0 \
  --output-dir build/medmentions/st21pv_dev_suppression_audit_mention_only

python3 scripts/run_medmentions_benchmark.py evaluate \
  build/medmentions/st21pv_dev_suppression_audit_mention_only/medmentions_st21pv_suppression_audit_mention_only_mention_queries.tsv \
  --base-url http://127.0.0.1:8766 \
  --top-k 10 \
  --scope umls_evidence \
  --linked \
  --limit 100 \
  --output-dir build/medmentions/st21pv_dev_suppression_audit_mention_only/eval_mentions_100
```

Suppression-audit result: 100 queries, top-1 surfacing rate 30.0%, top-10
surfacing rate 32.0%, MRR 0.310000, linked expected rate 33.0%. This is not a
win condition. It means exact mention linking can recover broad UMLS labels like
research and military service, but default clinical search should not optimize
for surfacing them.

## Interpretation

Mention-only queries are the clean linker test: each query is the annotated span
and expects that exact CUI. This is where synonyms, broad concepts, retired
2017AA CUIs, and abbreviation handling show up quickly.

Mention-context queries are still useful, but they are a harder retrieval stress
test rather than a pure linker score. They reveal whether the ranker can keep a
target span above nearby abstract context entities.

Document-level queries ask whether a full title/abstract returns the annotated
CUI set anywhere in the ranked concepts. They are useful for long-document
recall, but they are not mention-level F1 because the current `/api/search`
contract is ranked concept retrieval, not a complete span extraction API.

Next work for a full external benchmark:

- Add UMLS 2017AA to current-release CUI mapping or exclusion accounting.
- Add anchored-context ranker support so clinical-useful mention-context improves
  without increasing suppression-audit surfacing.
- Run a larger dev sample in batches and track latency separately.
- Track two gates: clinical-useful recall should improve, while
  suppression-audit top-k surfacing should not increase.
- Score span-level precision/recall once the API exposes stable mention offsets
  for the full input text.
- Keep MedMentions results separate from production count checks and internal
  clinical smoke regression scores.
