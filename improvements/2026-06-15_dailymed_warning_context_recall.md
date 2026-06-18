# DailyMed Warning-Context Recall

## Problem

The pruned core source-specific lane had one remaining blocking miss. For
`warfarin warning about serious bleeding`, the live run found `C0043031`
warfarin and `C0019080` Hemorrhage, but missed `C1550014` Warning in the first
10 answers.

## Change

Added a governed active-label supplement row for `C1550014` Warning with
`field=context`. The row is gated by drug-label context such as `warfarin`,
`serious bleeding`, `drug label`, `DailyMed`, or `boxed warning`, so the source
section concept can surface for the DailyMed warning query without globally
admitting a bare `warning` search as a useful generic result.

Added a focused no-vector `SearchIndex` regression that checks both sides of the
gate:

- `warfarin warning about serious bleeding` includes `C1550014`.
- `warning` alone does not include `C1550014`.

## Verification

- `python3 scripts/validate_active_label_supplement.py`
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile tests/test_evidence_vectors.py src/qe_evidence_vectors/search_rerank.py src/qe_evidence_vectors/search_service.py src/qe_evidence_vectors/active_label_supplement.py`
- `PYTHONPATH=src:scripts python3 -m pytest tests/test_evidence_vectors.py -k "active_label_supplement_file_passes or dailymed_warning_context_supplement or consumer_lay_language_supplements" -q`
- `PYTHONPATH=src:scripts python3 scripts/run_search_quality_suite.py --suite-id SQI-2026-06-15-003-dailymed-warning-context --only source_specific_evidence --fail-on blocking --command-timeout 180`
- `PYTHONPATH=src:scripts python3 scripts/run_search_quality_experiment.py --iteration-smoke-gates --iteration-id SQI-2026-06-15-003 --iteration-type data ... --skip-rotating-smoke --skip-patient-portal-smoke`

The live source-specific suite passed with 9/9 rows complete, 20/20 expected
CUIs at top 10, 0 missing rows, and 0 wrong-first rows. The target row now ranks
`C1550014` Warning - Alert level at rank 3. The formal smoke helper passed
static checks, focused pytest, and standing clinical API smoke; rotating and
patient-portal smoke were explicitly skipped because this was a scoped data fix.

## Remaining Work

This closes the blocking DailyMed warning-context recall miss, but it is not a
general DailyMed section model. Before expanding label coverage, add
section-aware checks for indications, warnings, contraindications, interactions,
populations, and pharmacology.
