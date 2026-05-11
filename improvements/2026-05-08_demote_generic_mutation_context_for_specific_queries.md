# Demote Generic Mutation Context for Specific Queries

## Problem

Specific oncology/genomics searches can surface generic mutation concepts too prominently. For example, `egfr mutated non small cell lung cancer osimertinib` can return `Mutation Abnormality`, even though the query contains more specific disease, gene/receptor, and therapy intent.

## Change

Added a conservative clinical-context sense penalty for generic mutation labels such as `Mutation Abnormality` when the query includes mutation language plus additional specific context. The penalty does not apply when the query itself is generic, such as `mutation abnormality`.

## Improvement

In the focused regression case:

- Query: `egfr mutated non small cell lung cancer osimertinib`
- `Non-Small Cell Lung Carcinoma` ranks above `Mutation Abnormality`
- `Mutation Abnormality` receives a `clinical_context_sense_penalty`

For `mutation abnormality`, the generic mutation concept is not penalized.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py::test_query_ranker_demotes_generic_mutation_context_when_specific_context_present` passed.
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py` passed.

Live API verification is deferred to the next server restart to avoid adding more shell/session pressure in the current long-running workflow.
