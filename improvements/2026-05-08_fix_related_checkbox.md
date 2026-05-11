# Make the Related checkbox a hard off switch

## Problem

The `Related` checkbox could appear ineffective. The frontend correctly sent `related=0`, but the backend still built semantic relation views with a reduced source limit and then inserted those relation items into `semantic_result_buckets`. The frontend also added local inferred/related semantic-bucket suggestions regardless of the checkbox state. Finally, opening lazy `Details` always requested `related=1`.

## Change

Changed the behavior so `related=0` means no relation-derived UI content:

- Backend `semantic_response_metadata(..., include_related=False)` now returns empty `semantic_views`, `semantic_view_sources`, and `semantic_group_views`.
- Backend semantic result buckets receive no relation items when related is disabled.
- Frontend semantic result buckets no longer add inferred or related suggestion cards unless the checkbox was checked for that search.
- Lazy details now request `related=0` when the current search had related disabled, and the detail cache key includes the related state.

## Result

When `Related` is unchecked, returned semantic group cards should contain only returned hits, not related suggestions. When it is checked, related semantic views and related suggestion cards remain available.

## Verification

Ran:

```sh
PYTHONPYCACHEPREFIX=.pycache_local PYTHONPATH=src python3 -m pytest tests/test_evidence_vectors.py -k related_bundle_returns_graph_vector_neighbors_and_mappings -q
PYTHONPYCACHEPREFIX=.pycache_local PYTHONPATH=src python3 -m py_compile src/qe_evidence_vectors/search_related.py src/qe_evidence_vectors/search_semantic_buckets.py tests/test_evidence_vectors.py
node --check docs/search_quality/app.js
```

Live API verification was deferred because the environment is already at the open process limit; the backend and frontend changes will apply after the search server is restarted and the browser reloads the app script.
