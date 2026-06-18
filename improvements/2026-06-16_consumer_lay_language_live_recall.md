# Consumer Lay-Language Live Recall

- Iteration: `SQI-2026-06-16-001`
- Backlog row: `SQB-004 Consumer lay-language lane`
- Status: shipped
- Type: data, public output

## Problem

The governed consumer aliases added on June 15 passed in-process checks, but the
live public API still did not expose all intended concepts as normal search
hits. In particular, `blood thinner` was promoted internally to `C0003280`
Anticoagulants, but the public-output layer dropped the hit because ranking had
added the internal `umls_definition` source to the hit source list.

## Change

Added `abdominal pain` as an active-label supplement row for `C0000737` and
allowed active-label supplement candidates to become rankable when the full
multi-token query span matches. In the public-output layer, `umls_definition` is
now treated as an internal ranking signal: it is stripped from returned source
lists instead of making otherwise public hits fail the source filter. Raw
`matched_definition` payloads are also dropped from public search hits.

## Result

The fresh live `consumer_lay_language` suite improved from 9/13 expected
concepts at top 10, 4 missing rows, 4 wrong-first rows, and 7 disallowed rows to
13/13 expected concepts at top 10, 0 missing rows, and 0 wrong-first rows. The
lane remains a known weakness because 7/13 rows still include configured
disallowed literal, anatomy, device, or gene drift in the first 10 answers.

## Verification

- `python3 scripts/validate_active_label_supplement.py`
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/public_output.py src/qe_evidence_vectors/search_rerank.py tests/test_public_output.py tests/test_evidence_vectors.py`
- `python3 -m pytest tests/test_public_output.py -q`
- `python3 -m pytest tests/test_evidence_vectors.py -k "consumer_lay or active_label_supplement or rankable_linked_label" -q`
- Live `blood thinner` API check returned `C0003280` as a normal hit with public sources `active_label_supplement` and `pmc_oa`.
- `python3 scripts/run_search_quality_suite.py --suite-id SQI-2026-06-16-001-consumer-lay-public-definition-source --base-url http://127.0.0.1:8771 --only consumer_lay_language --fail-on never`
- Required smoke gates passed in `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-16-001-required-gates/verification.md`.

## Follow-Up

Continue `SQB-004` on the remaining disallowed-at-10 drift classes: literal
water/hydrotherapy for water-pill queries, sugar/carbohydrate concepts for
diabetes wording, heart/TRAC noise for heart tracing, anatomy/device concepts
for colon/stomach scope wording, and similar first-page cleanup.
