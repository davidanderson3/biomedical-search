# Memory Loss Active Anchor

## Change

Added `memory loss` as a context-gated active label supplement for existing CUI `C0751295`.

The row is limited to neurology/cognitive contexts such as `memory loss`, `dementia`, `alzheimer`, `cognitive`, `mini mental`, and `mmse`.

## Improvement

The latest paragraph benchmark showed one remaining mixed paragraph:

- `paragraph_55`: Alzheimer disease with progressive memory loss and dementia.
- Missing expected top-10 CUI: `C0751295` Memory Loss.

The stored payload showed that broader or less direct concepts such as `Memory observations`, `Response Declined`, and mental-state examination variants could occupy the useful result window while the explicit `memory loss` finding was absent. This change makes the exact phrase a curated active anchor so it can remain visible alongside Alzheimer disease, dementia, MMSE, and donepezil.

## Verification

Added a regression test that ranks `C0751295` ahead of generic memory-observation and response-declined concepts for the Alzheimer paragraph wording.

Commands run:

```sh
python3 -m pytest tests/test_evidence_vectors.py -k 'memory_loss_anchor or active_label_supplement' -q
PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py src/qe_evidence_vectors/search_rerank.py src/qe_evidence_vectors/search_service.py
```

Result: `7 passed, 172 deselected`.

## Remaining Limits

This does not rebuild or rerun the full paragraph benchmark. It addresses the specific missing explicit concept reported by the most recent stored benchmark artifact. The next full evaluation should confirm whether paragraph 55 moves from mixed to good and whether overall Recall@10 returns toward the prior best run.
