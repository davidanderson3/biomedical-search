# OpenAlex Top-Cited Recent Evidence

## Request

Get evidence from the most cited papers from the last 5 years.

## Source Choice

- Used OpenAlex because the Works API supports `from_publication_date`, `to_publication_date`, article type filtering, and `sort=cited_by_count:desc`.
- Used OpenAlex title/abstract metadata, not full text. Abstracts are reconstructed from OpenAlex `abstract_inverted_index`.
- Reference docs: OpenAlex work filters (`https://docs.openalex.org/api-entities/works/filter-works`), work object fields (`https://docs.openalex.org/api-entities/works/work-object`), and sort syntax (`https://docs.openalex.org/how-to-use-the-api/get-lists-of-entities/sort-entity-lists`).

## Change

- Added `scripts/build_openalex_cited_evidence.py`.
- The script fetches highly cited recent OpenAlex works, links paper title/abstract text to local UMLS CUIs with the existing label trie, applies citation-count weighting, builds concept documents, and emits hashing vectors.
- Added a semantic/generic filter to suppress low-value paper-language matches such as broad quantitative/qualitative concepts, generic study language, and boilerplate words.
- Added OpenAlex citation formatting to provenance rendering.
- Wired the new OpenAlex document/vector shard into the default search-quality server paths.

## Build Parameters

- Date window: `2021-05-07` to `2026-05-07`.
- Query set:
  - `clinical medicine`
  - `diagnosis treatment disease`
  - `drug therapy adverse effects`
  - `biomarkers genomics disease`
  - `surgery procedure outcomes`
  - `laboratory diagnostics biomarkers`
- Per-query cap: 40 works.

## Measured Effect

- Fetched and deduplicated 124 OpenAlex papers.
- Citation count range among fetched papers: 869 to 21,684.
- Raw linked evidence records: 6,210.
- Low-value/generic evidence records removed: 3,870.
- Final evidence records: 2,340.
- Final OpenAlex concept documents: 878.
- Final OpenAlex vectors: 878.
- Active server after reload: 42,408 loaded vectors/docs across 6 document/vector shards.
- Active server provenance after reload: 453,016 evidence source refs across 22 evidence files.

## Verification

- Syntax check passed for `scripts/build_openalex_cited_evidence.py`.
- Rebuilt `build/openalex_cited_evidence/openalex_top_cited_concept_documents.jsonl`.
- Rebuilt `build/openalex_cited_evidence/openalex_top_cited_concept_vectors.hashing.jsonl`.
- Restarted `scripts/search_quality_server.py` on port 8766.
- `/api/status` confirms the OpenAlex doc/vector paths are loaded.
- Test search for `GLOBOCAN estimates incidence mortality worldwide cancers` returned OpenAlex-backed hits in the result pool, including cervical cancer, cancer-related death, colorectal carcinoma, and related-to-cancer concepts.

## Result

This adds a current, citation-prioritized biomedical evidence layer. It improves coverage for concepts appearing in influential recent guidelines, reviews, trials, disease-burden papers, drug papers, biomarker papers, and procedure/outcomes papers.

## Limitations

- This does not yet harvest most-cited papers per individual CUI; it uses broad biomedical query buckets.
- Existing PubMed, drug, label, and relation shards can still outrank OpenAlex evidence when they have stronger lexical or curated support.
- OpenAlex metadata is not a substitute for curated clinical guideline extraction or full-text relation extraction.
