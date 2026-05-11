# Demote Prior and Periprocedural Condition Context

## Problem

Active-condition searches can surface temporal or procedure-context variants too prominently. For example, `acute myocardial infarction troponin` can return `Old myocardial infarction` or `Periprocedural myocardial infarction` even though the query is about an active acute MI and troponin testing.

## Change

Added conservative clinical-context sense penalties for condition labels containing:

- `old`
- `periprocedural`

The `old` penalty is skipped when the query asks for prior context using terms such as `old`, `past`, `prior`, `previous`, or `history`. The `periprocedural` penalty is skipped when the query asks for periprocedural/procedural context.

## Improvement

For active acute-condition queries, active concepts should rank above prior/procedure-context variants. In the focused regression case:

- Query: `acute myocardial infarction troponin`
- `Acute myocardial infarction` ranks above `Old myocardial infarction`
- `Acute myocardial infarction` ranks above `Periprocedural myocardial infarction`
- Both contextual variants receive a `clinical_context_sense_penalty`

For explicit queries such as `old myocardial infarction` or `periprocedural myocardial infarction`, those concepts are not penalized.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py::test_query_ranker_demotes_prior_and_periprocedural_context_for_active_condition` passed.
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py` passed.

Live API verification is deferred to the next server restart to avoid adding more shell/session pressure in the current long-running workflow.
