# Demote Susceptibility Context for Active Queries

## Problem

Active-condition searches can surface genetic/risk-context concepts too prominently. For example, `asthma albuterol wheezing` can return `ASTHMA, SUSCEPTIBILITY TO`, even though the user is likely looking for active asthma, treatment, and symptom concepts.

## Change

Added a conservative clinical-context sense penalty for labels containing susceptibility/risk context, including:

- `susceptibility`
- `susceptible`
- `predisposition`
- `risk`

The penalty is skipped when the query explicitly asks for genetic/risk context using terms such as `susceptibility`, `risk`, `gene`, `genetic`, `variant`, `family`, or `familial`.

## Improvement

For active condition queries, active disease concepts should rank above susceptibility/risk findings. In the focused regression case:

- Query: `asthma albuterol wheezing`
- `Asthma` ranks above `ASTHMA, SUSCEPTIBILITY TO`
- `ASTHMA, SUSCEPTIBILITY TO` receives a `clinical_context_sense_penalty`

For a genetics query such as `asthma susceptibility gene`, the susceptibility concept is not penalized.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py::test_query_ranker_demotes_susceptibility_context_when_query_is_active_condition` passed.
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py` passed.

Live API verification is deferred to the next server restart to avoid adding more shell/session pressure in the current long-running workflow.
