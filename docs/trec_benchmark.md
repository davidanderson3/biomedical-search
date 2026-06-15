# TREC PM/CDS Benchmark

This lane imports TREC Precision Medicine or TREC Clinical Decision Support
topics and qrels as an external document/source retrieval benchmark.

It is intentionally separate from MedMentions and CUI recall checks:

- MedMentions evaluates whether text links to expected UMLS CUIs.
- TREC PM/CDS evaluates whether retrieved results expose judged PubMed IDs or
  ClinicalTrials.gov IDs.
- Unjudged returned documents are unknown, not false positives.

## Workflow

Prepare:

```sh
python3 scripts/run_trec_benchmark.py prepare \
  --track precision_medicine \
  --topics data/trec/precision_medicine/topics2019.xml \
  --qrels data/trec/precision_medicine/qrels-treceval-abstracts.2019.txt \
  --qrels data/trec/precision_medicine/qrels-treceval-trials.38.txt \
  --output-dir build/trec/precision_medicine
```

If `--corpus` is omitted, the importer discovers the existing local
PubMed/Europe PMC/PMC OA and ClinicalTrials.gov corpus JSONL artifacts under
`build/`. Pass explicit `--corpus` paths to pin a release corpus.

Evaluate:

```sh
python3 scripts/run_trec_benchmark.py evaluate \
  build/trec/precision_medicine/trec_precision_medicine_resolved_document_queries.tsv \
  --base-url http://127.0.0.1:8766 \
  --top-k 10 \
  --scope umls_evidence \
  --output-dir build/trec/precision_medicine/eval
```

Use `--track clinical_decision_support` for TREC CDS topics/qrels.

## Outputs

- `trec_<track>_topics.tsv`: normalized topic text.
- `trec_<track>_qrels.tsv`: normalized qrels, including relevance and source
  type.
- `trec_<track>_corpus_coverage.tsv`: one row per judged document/trial ID,
  with local-corpus resolution status.
- `trec_<track>_document_queries.tsv`: evaluator-ready topic rows whose
  `expected_doc_ids` contain all qrels positives. Use this for corpus-expansion
  accounting, because many judged positives may be absent locally.
- `trec_<track>_resolved_document_queries.tsv`: evaluator-ready topic rows whose
  `expected_doc_ids` contain only judged positives resolved in the local corpus.
  Use this for local document/source retrieval scoring.
- `trec_<track>_manifest.json`: coverage-first summary.
- `eval/rows.tsv` and `eval/summary.json`: document/source retrieval metrics.

## Scoring Contract

The lane uses qrels rows with `relevance > 0` as positives. It does not score
unknown/unjudged returned documents as false positives and does not substitute
CUI retrieval metrics for source-document retrieval.

Run evaluation against a local/internal API configuration that exposes source
identifiers in hits or evidence items. A public-output-only API can still search
concepts, but it may suppress PMID/NCT evidence identifiers and therefore cannot
produce meaningful TREC document/source retrieval scores.

## Current Local Import

The first imported lane uses the public NIST TREC 2019 Precision Medicine test
topics and both trec-eval qrels files:

- Track page: <https://trec.nist.gov/data/precmed2019.html>
- Topics: <https://trec.nist.gov/data/precmed/topics2019.xml>
- Abstract qrels: <https://trec.nist.gov/data/precmed/qrels-treceval-abstracts.2019.txt>
- Clinical trial qrels: <https://trec.nist.gov/data/precmed/qrels-treceval-trials.38.txt>

```sh
python3 scripts/run_trec_benchmark.py prepare \
  --track precision_medicine \
  --topics build/trec/precision_medicine_2019/raw/topics2019.xml \
  --qrels build/trec/precision_medicine_2019/raw/qrels-treceval-abstracts.2019.txt \
  --qrels build/trec/precision_medicine_2019/raw/qrels-treceval-trials.38.txt \
  --output-dir build/trec/precision_medicine_2019
```

Coverage came first:

- 40 topics.
- 31,312 judgments.
- 7,729 judged positives.
- 511,844 local corpus records scanned by default discovery.
- 74 judged positives resolved locally: 73 PubMed IDs and 1 ClinicalTrials.gov ID.

The resolved-local query file has 10 topic rows. The public-output API smoke
produced zero document/source hits because the running public API suppresses
underlying PMID/NCT evidence identifiers. A follow-up non-public API run on port
`8768` also completed against the same resolved-local rows and wrote
`build/trec/precision_medicine_2019/eval_non_public_20260610/summary.json`, but
still found `0/74` expected source documents at rank 10. The next implementation
work is therefore source-document identifier exposure or a source-document
retrieval path, not another public/private API rerun.
