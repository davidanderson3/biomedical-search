# GitHub Quickstart

This repository is usable from a fresh clone, but a full rebuild needs local
UMLS files that cannot be committed here. Public corpora can be fetched from
their upstream sources; UMLS-derived indexes must be rebuilt from your licensed
UMLS Metathesaurus download.

## Clone And Check The Public Tooling

```sh
git clone <repo-url>
cd query-expansion
python3 -m pip install -r requirements-public.txt
```

Install the small dev requirements file if you want to run the test checks:

```sh
python3 -m pip install -r requirements-dev.txt
python3 -m pytest tests/test_openalex_cited_evidence.py tests/test_source_acquisition_progression.py -q
```

The public hashing path uses the Python standard library. Optional transformer
embeddings require extra packages such as `torch` and `transformers`.

## Plan A Public Rebuild

Use `--dry-run` first. It prints every command without network calls or file
writes, so it works before your local source files are in place:

```sh
python3 scripts/run_public_rebuild.py \
  --umls-meta /path/to/UMLS/META \
  --out-dir build/public \
  --provider hashing \
  --dry-run
```

For a real build, `/path/to/UMLS/META` must contain at least `MRCONSO.RRF`,
`MRSTY.RRF`, `MRREL.RRF`, `MRDEF.RRF`, and `MRSAB.RRF` from your UMLS release:

```sh
python3 scripts/run_public_rebuild.py \
  --umls-meta /path/to/UMLS/META \
  --out-dir build/public \
  --provider hashing
```

The wrapper fetches bounded public corpora, builds local UMLS-derived indexes,
links text to CUIs, writes concept documents/vectors, runs paragraph quality
evaluation, writes `build/public/reproducibility_manifest.json`, and writes the
server command to `build/public/server_command.txt`.

## Acquire Missing High-Citation Articles

After the public rebuild has created the label and semantic-type indexes, you
can reproduce the recent high-citation OpenAlex acquisition:

```sh
python3 scripts/build_openalex_cited_evidence.py \
  --out-dir build/source_acquisition/openalex_missing_high_citation \
  --label-index build/public/indexes/umls_biomedicine_search_label_index.sqlite \
  --semantic-type-index build/public/indexes/umls_semantic_types.sqlite \
  --query-file config/openalex_missing_high_citation_queries.tsv \
  --from-date 2021-05-14 \
  --to-date 2026-05-14 \
  --max-per-query 60 \
  --per-page 60 \
  --min-cited-by-count 500 \
  --exclude-corpus build/openalex_cited_evidence/openalex_top_cited_corpus.jsonl \
  --exclude-corpus build/pubmed_bulk_recent_baseline_corpus.jsonl \
  --exclude-corpus build/pubmed_bulk_recent_next2_corpus.jsonl \
  --articles-tsv build/source_acquisition/openalex_missing_high_citation/articles.tsv
```

Missing `--exclude-corpus` files are ignored, so the same command works whether
or not you have the local historical corpora. The output includes an article
TSV, corpus JSONL, evidence JSONL, concept documents, vectors, and a manifest.

## Inspect Historical Progression

The checked-in progression ledger references local `build/` artifacts from the
measured acquisition rounds. A fresh clone can still inspect the ledger shape:

```sh
python3 scripts/source_acquisition_progression.py \
  --allow-missing-stage-metrics \
  --out-json build/source_acquisition/progression_manifest.json \
  --out-md build/source_acquisition/progression_report.md
```

After you have rebuilt or recreated the referenced artifacts, use strict mode:

```sh
python3 scripts/source_acquisition_progression.py --fail-on-regression
```

Strict mode fails if any listed artifact is missing or if a retained stage
regresses its deterministic gate.

## License Boundary

Source data licenses are separate from this repository's code. UMLS, LOINC,
SNOMED CT, external CUI vectors, and credentialed clinical datasets must not be
redistributed unless your license permits it. Before publishing this repository
publicly, add a project-level `LICENSE` file so GitHub users have clear rights
for the code itself.
