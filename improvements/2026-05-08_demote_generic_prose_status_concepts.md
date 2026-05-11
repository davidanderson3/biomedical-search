# Demote generic prose/status concepts in biomedical queries

## Problem

Search results still sometimes include chart-prose concepts such as `Confirmation`, `Documented`, `Prescribed`, `Administration (procedure)`, `Testing Was Performed`, and `Follow-up status` beside more clinically meaningful diseases, drugs, observations, and procedures. These concepts can match common verbs in clinical paragraphs but usually do not represent the biomedical content the user is trying to retrieve.

## Change

Added a conservative ranking penalty for generic prose/status labels when the query contains other biomedical anchors. The rule applies to labels made only of status/action prose tokens such as `confirmation`, `documented`, `prescribed`, `administration`, `testing`, `started`, `reviewed`, or `follow up`.

The rule does not penalize direct status/documentation queries such as `confirmation documented`, where those concepts may be the intended target.

## Result

The focused regression test verifies that in:

`urine culture confirmed acute pyelonephritis and ceftriaxone was administered`

`Acute pyelonephritis` and `ceftriaxone` outrank generic `Administration (procedure)` and `Confirmation`, while a direct status query keeps `Confirmation` unpenalized.

## Verification

Ran:

```sh
PYTHONPYCACHEPREFIX=.pycache_local PYTHONPATH=src python3 -m pytest tests/test_evidence_vectors.py -k generic_prose_status -q
PYTHONPYCACHEPREFIX=.pycache_local PYTHONPATH=src python3 -m py_compile src/qe_evidence_vectors/search_ranking.py tests/test_evidence_vectors.py
```

Live API verification was deferred because the environment is already at the open process limit; the change will apply after the search server is restarted.
