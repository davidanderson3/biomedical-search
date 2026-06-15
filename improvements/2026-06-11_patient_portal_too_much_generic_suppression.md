# Patient Portal Too Much Generic Suppression

## Problem

The `patient_portal_intent` suite layer still failed one threshold after the
evidence-backed label fallback fix. In
`portal_02_hypoglycemia_old_diabetes`, expected CUI `C0021641` Insulin was rank
11 while generic prose concept `C3843660` Too much occupied rank 8. The suite
therefore stayed at 73/88 expected concepts at top 10 against a threshold of 74.

Stored failing run:

- Query file: `config/search_quality_patient_portal_queries.tsv`
- Output directory: `build/search_quality_experiments/runs/SQI-2026-06-11-001_patient_portal_sqi-2026-06-11-001-patient-portal-evidence-backed-label-fallback`
- Result: patient-portal focused gates passed, but named suite layer still failed
  `found_at_10` with 73 actual versus 74 expected.

## Hypothesis

`Too much` should be suppressed as a standalone generic/prose concept in the same
rule class as the already-blocked `Too little`. Suppressing standalone
`C3843660` should let the directly mentioned insulin concept move into the top
10 without blocking the longer clinical phrase `too much insulin`.

## Change

- Added `too much` to `BLOCKED_GENERIC_LABELS`.
- Added `C3843660` to `BLOCKED_GENERIC_CUIS`.
- Added unit coverage that blocks standalone `Too much` and `too much`, while
  preserving `too much insulin` as a non-blocked query phrase.
- Regenerated `docs/search_rule_inventory.md`.

## Result

Focused live rerun:

- Query file: `config/search_quality_patient_portal_queries.tsv`
- Output directory: `build/search_quality_experiments/runs/SQI-2026-06-11-003_patient_portal_sqi-2026-06-11-003-patient-portal-current-versus-history-lane`
- Server profile: `PORT=8791 PUBLIC_OUTPUT_ONLY=0 sh scripts/start_search_quality_server.sh`
- Command:

```sh
python3 scripts/run_search_quality_experiment.py --base-url http://127.0.0.1:8791 --scope umls_evidence --run-family patient_portal --label 'SQI-2026-06-11-003 patient portal current-versus-history lane' --run-id SQI-2026-06-11-003_patient_portal --queries config/search_quality_patient_portal_queries.tsv --query-limit 0 --search-system api --top-k 60 --timeout 90.0 --output-root build/search_quality_experiments --html-report docs/search_quality_experiments.html --require-api-backend elasticsearch --fail-gates
```

Measured movement:

- Named patient-portal suite layer: failed -> passed.
- Expected concepts at top 10: 73/88 -> 74/88.
- Top-on-target: 12/12 -> 12/12.
- Top-wrong: 0 -> 0.
- Strict full-row success at top 10: 0/12 -> 1/12.
- `portal_02_hypoglycemia_old_diabetes`: Insulin moved from rank 11 to rank 10.
- Top-10 source counts remained present: `pmc_oa` 41, `pubmed_bulk` 58, and
  `pubmed` 7.

The rotating 50-query smoke also passed gates: 42/50 strict success at top 10,
48/50 strict success at top 20, 50/50 top-on-target, 0 top-wrong, and 45 good /
5 mixed verdicts.

## Verification

- `python3 scripts/build_search_rule_inventory.py`
- `python3 -m py_compile src/qe_evidence_vectors/generic_filters.py scripts/build_search_rule_inventory.py`
- `python3 -m pytest tests/test_evidence_vectors.py::test_generic_filter_blocks_known_bad_concepts tests/test_evidence_vectors.py::test_generic_filter_blocks_standalone_fragments_but_allows_watchlist_contexts -q`
- `python3 scripts/run_search_quality_suite.py --suite-id SQI-2026-06-11-003-full --base-url http://127.0.0.1:8791 --only patient_portal_intent --fail-on any`
- `python3 scripts/run_search_quality_experiment.py --iteration-smoke-gates --iteration-id SQI-2026-06-11-003 --iteration-type ranking --broad-change --force-patient-portal-smoke --static-command "python3 -m py_compile src/qe_evidence_vectors/generic_filters.py scripts/build_search_rule_inventory.py" --focused-command "python3 -m pytest tests/test_evidence_vectors.py::test_generic_filter_blocks_known_bad_concepts tests/test_evidence_vectors.py::test_generic_filter_blocks_standalone_fragments_but_allows_watchlist_contexts -q" --base-url http://127.0.0.1:8791`

## Decision

Keep. This closes the patient-portal `found_at_10` suite threshold with a
reusable generic-fragment suppression and keeps the clinical phrase
`too much insulin` available for search.
