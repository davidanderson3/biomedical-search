# Benchmark Script Index

Index-only category. Executable entrypoints remain at `../<script>.py` so
existing command references keep working.

- `../fetch_pubmed_paragraph_queries.py` - PubMed paragraph query acquisition.
- `../build_pubmed_long_document_slice.py` - focused long-document slice
  materializer.
- `../run_medmentions_benchmark.py` - MedMentions benchmark runner.
- `../run_trec_benchmark.py` - TREC Precision Medicine / Clinical Decision
  Support document-source benchmark runner.
- `../compare_to_gold_standard.py` - locked gold-standard comparison.
- `../compare_umls_api.py` - UMLS API comparison helper.
- `../audit_real_queries_umls_api.py` - reproducible private real-query sample,
  official UMLS API audit, and reviewed false-negative-rate scorer.
- `../compare_umls_vector_search.py` - blinded pooled comparison of saved UMLS
  API results with the existing SapBERT-backed `/api/search` interface.
- `../run_umls_query_expansion_audit.py` - frozen language-expansion union
  diagnostic with strategy-specific candidate-result accounting.
- `../run_private_real_query_diagnostic.py` - private real-query diagnostic
  runner.
