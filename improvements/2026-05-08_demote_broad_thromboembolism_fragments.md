# Demote broad thromboembolism fragments in specific thromboembolism queries

## Problem

Specific queries such as `pulmonary embolism apixaban right heart strain` can still surface very broad fragment concepts like `Embolus` near or above the specific disorder concept `Pulmonary Embolism`. That hurts the core goal of returning all relevant concepts from different semantic groups without letting generic fragments crowd out clinically actionable concepts.

## Change

Added a ranking penalty for broad thromboembolism-only labels (`Embolus`, `Emboli`, `Thrombus`, `Thromboembolus`, etc.) when the query contains both a thromboembolism term and a site/context term such as `pulmonary`, `venous`, `arterial`, `cerebral`, or `coronary`.

The rule is intentionally conservative: a broad query like `embolus` is not penalized because the broad concept may be the intended result.

## Result

The focused ranking test now verifies that:

- `Pulmonary Embolism` ranks above `Embolus` for `pulmonary embolism apixaban right heart strain`.
- `Embolus` is not penalized for the broad query `embolus`.

## Verification

Ran:

```sh
PYTHONPYCACHEPREFIX=.pycache_local PYTHONPATH=src python3 -m pytest tests/test_evidence_vectors.py -k broad_thromboembolism_fragment -q
PYTHONPYCACHEPREFIX=.pycache_local PYTHONPATH=src python3 -m py_compile src/qe_evidence_vectors/search_ranking.py tests/test_evidence_vectors.py
```

Live API verification was deferred because the current environment is already at the open process limit; the backend change will apply after the search server is restarted.
