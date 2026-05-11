# Demote Recent Condition Context for Active Queries

## Problem

Active acute-condition searches can surface temporal variants too prominently. For example, `acute myocardial infarction troponin` can return `Recent myocardial infarction` even though the query is asking for the acute MI concept and troponin testing, not a timing-context variant.

## Change

Extended the temporal condition context penalty to include labels beginning with or containing `recent`. The penalty is skipped when the raw query itself asks for recent timing using `recent` or `recently`.

This builds on the prior `old` and `periprocedural` condition-context penalties.

## Improvement

In the focused regression case:

- Query: `acute myocardial infarction troponin`
- `Acute myocardial infarction` ranks above `Recent myocardial infarction`
- `Recent myocardial infarction` receives a `clinical_context_sense_penalty`

For an explicit query such as `recent myocardial infarction`, the recent concept is not penalized.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py::test_query_ranker_demotes_prior_and_periprocedural_context_for_active_condition` passed.
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py` passed.

Live API verification is deferred to the next server restart to avoid adding more shell/session pressure in the current long-running workflow.
