# Data source contribution analysis

## Scope

This report estimates how much value each source is contributing using local artifacts only.

Two measures are reported:

- **Index footprint**: how many concept documents and evidence items each source contributes to the active/default search inputs.
- **Retrieval contribution**: how often each source appears in the top 10 results for the 80-paragraph search-quality benchmark in `build/new_umls_iterations/iteration_010_more_paragraphs/paragraph_search_payloads.jsonl`.

The retrieval analysis gives fractional credit when a result has multiple sources.

## Index Footprint

| Source artifact | Docs | CUIs | Evidence items | Dominant sources |
|---|---:|---:|---:|---|
| Core PubMed/EuropePMC structured | 39,342 | 29,881 | 443,631 | PubMed and EuropePMC are the dominant sources |
| New CUI extensions | 13 | 13 | 65 | Existing concept documents |
| Wikipedia enrichment | 2 | 2 | 8 | Wikipedia |
| Drug enrichment | 9 | 9 | 511 | RxNorm, ATC, DrugBank, MTHSPL, PubMed bulk, EuropePMC |
| Open image enrichment | 21 | 21 | 37 | Wikimedia Commons |
| OpenAlex cited evidence | 878 | 878 | 2,340 | OpenAlex top-cited papers |

## Retrieval Contribution, Top 10

Across 80 paragraph queries, there are 800 top-10 result slots. Fractional source credit:

| Source | Top-10 credit | Share of top-10 | Rank-weighted credit | Top-5 credit | Top-1 credit | Expected-CUI@10 credit |
|---|---:|---:|---:|---:|---:|---:|
| PubMed | 491.5 | 61.4% | 153.56 | 261.5 | 56.0 | 210.0 |
| UMLS label fallback | 216.0 | 27.0% | 40.20 | 75.0 | 2.0 | 99.0 |
| EuropePMC | 60.5 | 7.6% | 27.45 | 41.5 | 16.0 | 33.0 |
| New CUI extension labels/documents | 17 total hits split across two co-sources | ~2.1% combined | 4.21 each split | 13 combined | 5 combined | 15 combined |
| Active label supplement | 2.5 | 0.3% | 0.43 | 1.0 | 0.0 | 2.5 |

## Interpretation

PubMed is currently the main value driver. It provides most index coverage and most useful retrieved concepts, including 57% of expected-CUI@10 credit.

UMLS label fallback is the second most valuable retrieval source even though it is not an evidence corpus. It contributes 27% of top-10 results and 27% of expected-CUI@10 credit. That means exact label search is still rescuing many concepts that the vector/evidence layer does not surface strongly enough.

EuropePMC is smaller than PubMed but high-leverage. It provides 7.6% of top-10 credit and 20% of top-1 credit in this benchmark, so it is contributing strong first-rank hits despite less total footprint.

The new CUI extension layer is small but efficient. Only 13 extension documents exist, yet extension concepts appear in 17 top-10 hits and account for 15 expected-CUI@10 source-credit units when counting the paired extension sources together. This is good evidence that curated/new concepts are high value per document.

Wikipedia, open image enrichment, drug enrichment, and OpenAlex cited evidence do not materially appear in the current paragraph benchmark top-10 outputs. That does not mean they are useless; it means this benchmark is not stressing the queries where those sources should help most, such as specific drug lookups, public concept summaries, images, and literature-heavy research concepts.

## Recommendations

1. Keep investing in PubMed and EuropePMC; they are the core evidence-retrieval sources.
2. Treat UMLS label fallback as essential, not a temporary crutch, but use ranking controls to keep generic labels from polluting results.
3. Expand new CUI creation because it has high return per document in the current benchmark.
4. Build source-specific evaluations for drug enrichment, Wikipedia, OpenAlex, and images instead of judging them only on the general clinical paragraph benchmark.
5. Add ablation testing next: run the same benchmark with each source disabled to measure marginal loss in recall and ranking, not just observed source presence.
