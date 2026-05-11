# Demote Resistant Organism Context for Drug Queries

## Problem

Drug-treatment queries can surface resistant-organism concepts too prominently when the organism label starts with the drug name. For example, `diabetic foot osteomyelitis vancomycin bone biopsy` can return `Vancomycin-Resistant Enterococci`, even though the query is about vancomycin treatment and bone biopsy rather than VRE culture.

## Change

Added a conservative clinical-context sense penalty for organism concepts whose labels include resistance context:

- `resistant`
- `resistance`

The penalty applies only to organism semantic types such as bacterium/fungus/virus and is skipped when the query explicitly asks for resistant organisms using terms such as `resistant`, `resistance`, `VRE`, `MRSA`, `culture`, `cultures`, `grew`, or `growth`.

## Improvement

For drug-context queries, active drug concepts should rank above resistant-organism concepts. In the focused regression case:

- Query: `diabetic foot osteomyelitis vancomycin bone biopsy`
- `vancomycin` ranks above `Vancomycin-Resistant Enterococci`
- `Vancomycin-Resistant Enterococci` receives a `clinical_context_sense_penalty`

For an organism query such as `vancomycin resistant enterococci culture`, the resistant-organism concept is not penalized.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py::test_query_ranker_demotes_resistant_organism_when_query_is_drug_context` passed.
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py` passed.

Live API verification is deferred to the next server restart to avoid adding more shell/session pressure in the current long-running workflow.
