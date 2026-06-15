# Patient Portal Evidence-Backed Label Fallback

## Problem

The `patient_portal_intent` lane had a source-retention regression: the same
patient portal queries still found useful concepts, but evidence-backed PubMed
and PMC hits for CUIs such as central venous catheter placement could be
replaced by higher-scoring pure UMLS label fallback hits for the same CUI. That
dropped `pmc_oa` and `pubmed_bulk` from the visible top-10 source mix and left
the lane at 11/12 top-on-target.

Stored failing run:

- Query file: `config/search_quality_patient_portal_queries.tsv`
- Output directory: `build/search_quality_experiments/runs/SQI-2026-06-10-025_patient_portal_sqi-2026-06-10-025-patient-portal-current-versus-history-lane`
- Result: gate failed; 11/12 top-on-target; 1 top-wrong; 73/88 expected concepts at top 10; `pmc_oa` 0 and `pubmed_bulk` 0 at top 10.

## Hypothesis

For the same CUI, label fallback should improve labels and matched-span metadata
without replacing an already evidence-backed hit. Preserving the evidence-backed
hit should restore PubMed/PMC source counts and the central-line top result
without adding a CUI-specific ranking rule.

## Change

- Updated `SearchRerankMixin.merge_label_fallback` so an existing evidence-backed
  `umls_label` hit keeps its vector/evidence record when a higher-scoring pure
  label fallback appears for the same CUI.
- The merge still records the stronger label fallback score and better matched
  span, but preserves evidence count, document id, source mix, and sources.
- Added a focused unit test covering an evidence-backed central venous catheter
  hit with `pubmed`/`pmc_oa` sources and a higher-scoring pure label fallback for
  the same CUI.

## Result

Focused live rerun:

- Query file: `config/search_quality_patient_portal_queries.tsv`
- Output directory: `build/search_quality_experiments/runs/SQI-2026-06-11-001_patient_portal_sqi-2026-06-11-001-patient-portal-evidence-backed-label-fallback`
- Command:

```sh
python3 scripts/run_search_quality_experiment.py --base-url http://127.0.0.1:8790 --scope umls_evidence --run-family patient_portal --label 'SQI-2026-06-11-001 patient portal evidence-backed label fallback' --run-id SQI-2026-06-11-001_patient_portal --queries config/search_quality_patient_portal_queries.tsv --query-limit 0 --search-system api --top-k 60 --timeout 120 --output-root build/search_quality_experiments --html-report docs/search_quality_experiments.html --require-api-backend elasticsearch --fail-gates
```

Measured movement:

- Gate result: failed -> passed.
- Top-on-target: 11/12 -> 12/12.
- Top-wrong: 1 -> 0.
- Good verdicts: 4 -> 5.
- Expected concepts at top 10: 73/88 -> 73/88.
- Top-10 source counts: `pmc_oa` 0 -> 39, `pubmed_bulk` 0 -> 60, `pubmed` 0 -> 6.

The suite layer still records one remaining threshold gap:
`found_at_10` is 73 and the `patient_portal_intent` threshold expects 74.
Artifact: `build/search_quality_suite/SQI-2026-06-11-001/suite.md`.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py::test_label_fallback_preserves_evidence_backed_umls_label_sources -q`
- `python3 -m pytest tests/test_evidence_vectors.py -k 'long_document' -q`
- `python3 -m pytest tests/test_search_quality_experiment_gates.py::test_source_quality_contribution_tracks_expected_and_bad_hits tests/test_search_quality_suite.py::test_thresholds_check_counts_and_sources -q`
- `python3 -m py_compile src/qe_evidence_vectors/search_rerank.py scripts/run_search_quality_experiment.py scripts/run_search_quality_suite.py`
- `python3 scripts/run_search_quality_suite.py --suite-id SQI-2026-06-11-001 --base-url http://127.0.0.1:8790 --only patient_portal_intent --fail-on any`

## Decision

Keep. This is a reusable merge-rule fix, not a one-CUI exception. It closes the
patient-portal source-retention failure and leaves a separate bounded follow-up
for the remaining patient-portal recall threshold.
