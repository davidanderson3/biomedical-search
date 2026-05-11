# Demote Staging Context for Active Cancer Queries

## Problem

Active cancer/drug/mutation searches can surface staging concepts too prominently. For example, `egfr mutated non small cell lung cancer osimertinib` can return `stage, non-small cell lung cancer` even though the query is mainly asking for the disease, mutation/gene, and therapy concepts.

## Change

Added a conservative clinical-context sense penalty for labels containing staging context:

- `stage`
- `staging`

The penalty is skipped when the query explicitly asks for staging using terms such as `stage`, `staging`, or `TNM`.

## Improvement

For active cancer queries, active disease concepts should rank above staging-context concepts. In the focused regression case:

- Query: `egfr mutated non small cell lung cancer osimertinib`
- `Non-Small Cell Lung Carcinoma` ranks above `stage, non-small cell lung cancer`
- `stage, non-small cell lung cancer` receives a `clinical_context_sense_penalty`

For a staging query such as `stage non small cell lung cancer`, the staging concept is not penalized.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py::test_query_ranker_demotes_staging_context_when_query_is_active_condition` passed.
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py` passed.

Live API verification is deferred to the next server restart to avoid adding more shell/session pressure in the current long-running workflow.
