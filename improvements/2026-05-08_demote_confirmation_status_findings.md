# Demote confirmation-status findings in clinical paragraphs

## Problem

In this query:

`Exam showed lower leg cellulitis with a fluctuant abscess. Ultrasonography confirmed a fluid collection, incision and drainage was performed, and cephalexin was prescribed after discharge.`

generic status findings such as `Confirmation` and `Not confirmed` could appear as top findings because they match `confirmed`. Those are not useful concepts for this search; the useful findings are `cellulitis`, `abscess`, and `fluid collection`.

## Change

Added a stronger clinical-context penalty for confirmation-only labels such as:

- `Confirmation`
- `Confirmed`
- `Not confirmed`
- `Unconfirmed`

The penalty applies only when the query contains other biomedical content. Direct status queries such as `not confirmed` remain unpenalized.

## Result

The focused regression verifies that `Cellulitis`, `Abscess`, and `Fluid collection` rank ahead of `Confirmation` and `Not confirmed` for the target paragraph.

## Verification

Ran:

```sh
PYTHONPYCACHEPREFIX=.pycache_local PYTHONPATH=src python3 -m pytest tests/test_evidence_vectors.py -k confirmation_status -q
PYTHONPYCACHEPREFIX=.pycache_local PYTHONPATH=src python3 -m py_compile src/qe_evidence_vectors/search_ranking.py tests/test_evidence_vectors.py
```

Live API verification was deferred because the environment is already at the open process limit; the backend change will apply after the search server is restarted.
