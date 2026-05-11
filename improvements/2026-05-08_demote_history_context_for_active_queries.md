# Demote History Context for Active Queries

## Problem

Active-condition searches can return history-context concepts too prominently. For example, a query such as `asthma albuterol wheezing` can surface `H/O: asthma` even though the user is looking for the active disease, drug, and symptom concepts.

## Change

Added a conservative clinical-context sense penalty for labels that indicate history context, including:

- `H/O: ...`
- `History of ...`
- `Past history of ...`
- `Personal history of ...`

The penalty is not applied when the query itself asks for historical context using terms such as `history`, `past`, `prior`, `previous`, or `family`.

## Improvement

For active condition queries, active concepts should rank above history-context findings. In the focused regression case:

- Query: `asthma albuterol wheezing`
- `Asthma` ranks above `H/O: asthma`
- `H/O: asthma` receives a `clinical_context_sense_penalty`

For a history query such as `past history of asthma`, the history-context concept is not penalized.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py::test_query_ranker_demotes_history_context_when_query_is_active_condition` passed.
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py` passed.

Live API verification is deferred to the next server restart to avoid adding more shell/session pressure in the current long-running workflow.
