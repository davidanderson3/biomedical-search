# Promote composite lab-result concepts over their component parts

## Problem

Paragraph evaluation showed that result-level concepts can lose to their separate components. For example, in a urinary infection paragraph, `Urine culture` and `Escherichia coli` can appear ahead of the more informative composite result concept `urine culture Escherichia coli`, even though the text states that the culture grew that organism.

That weakens the goal of returning concepts from different semantic groups because the interface should show both the procedure/organism and the clinically meaningful result statement when it exists.

## Change

Added a ranking component for `Laboratory or Test Result` concepts when:

- the label contains a test/result anchor such as `culture`, `urine`, `test`, `PCR`, or `antibody`;
- the query contains result context such as `grew`, `positive`, `detected`, `showed`, or `result`;
- the concept label matches both the test anchor and a non-test biomedical anchor from the query.

This avoids boosting generic lab procedures and only promotes result-level composites that encode more of the statement.

## Result

The focused regression verifies that `urine culture Escherichia coli` outranks both `Urine culture` and `Escherichia coli` for:

`urine culture grew Escherichia coli and ceftriaxone was given for acute pyelonephritis`

The separate procedure and organism concepts still remain retrievable; the composite result now gets a clear ranking signal.

## Verification

Ran:

```sh
PYTHONPYCACHEPREFIX=.pycache_local PYTHONPATH=src python3 -m pytest tests/test_evidence_vectors.py -k composite_lab_result -q
PYTHONPYCACHEPREFIX=.pycache_local PYTHONPATH=src python3 -m py_compile src/qe_evidence_vectors/search_ranking.py tests/test_evidence_vectors.py
```

Live API verification was deferred because the environment is already at the open process limit; the backend change will apply after the search server is restarted.
