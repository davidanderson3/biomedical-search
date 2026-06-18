# Consumer Lay-Language Literal Drift Cleanup

- Iteration: `SQI-2026-06-16-002`
- Backlog row: `SQB-004 Consumer lay-language lane`
- Status: shipped
- Type: ranking

## Problem

The previous consumer lay-language run found all 13 intended concepts and had no
wrong-first rows, but 7/13 rows still exposed configured bad first-page concepts.
The remaining drift was literal or near-literal: water and hydrotherapy for
`water pill`, sugar and carbohydrate concepts for `sugar diabetes`, heart/TRAC
noise for `heart tracing`, EKG finding for `EKG`, and anatomy/device concepts
for scope wording.

## Change

Active-label supplement hits now carry the supplement field and consumer-health
metadata through search hydration and reranking. The evidence-aware cutoff then
uses that metadata for a bounded short-query filter: when a reviewed consumer
active-label hit is present, non-curated literal subspans, same-phrase legacy
duplicates, and single-token abbreviation drift can be removed without hiding the
curated consumer hit itself.

## Result

The fresh live `consumer_lay_language` suite passed with 13/13 examples fully
found, 13/13 expected concepts at top 10, 0 missing rows, 0 wrong-first rows, and
0 configured disallowed concepts at top 10/top 20. The lane is still marked
nonblocking/known-weakness in the suite configuration until the gate-promotion
decision is made, but the SQB-004 ranking cleanup itself is green.

## Verification

- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py src/qe_evidence_vectors/search_rerank.py src/qe_evidence_vectors/search_service.py tests/test_evidence_vectors.py`
- `python3 -m pytest tests/test_evidence_vectors.py -k "consumer_lay or active_label_supplement or rankable_linked_label" -q`
- Direct API checks against `http://127.0.0.1:8772` confirmed the formerly noisy rows no longer returned configured disallowed CUIs in the checked first page.
- `python3 scripts/run_search_quality_suite.py --suite-id SQI-2026-06-16-002-consumer-lay-literal-drift --base-url http://127.0.0.1:8772 --only consumer_lay_language --fail-on never`
- Required smoke gates passed in `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-16-002/verification.md`: static check, focused pytest, focused consumer suite, standing clinical API smoke, and rotating 50-query smoke. The rotating smoke had 42/50 strict top 10, 48/50 top-on-target, 2 wrong-first rows, 44 good rows, and 6 mixed rows. Patient-portal smoke was explicitly skipped.

## Follow-Up

Decide whether to promote `consumer_lay_language` to a blocking release gate or
keep it as a monitored diagnostic with explicit thresholds. Next P0 ranking work
should move to the fresh rotating wrong-first rows and the realistic note-format
recall lane.
