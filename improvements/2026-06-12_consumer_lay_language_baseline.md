# SQI-2026-06-12-002 Consumer Lay-Language Baseline

## Problem

`SQB-004` needed a first-class lane for short patient wording. The existing
MedlinePlus rows cover only a few lay-language examples, and patient-portal
messages are long enough that they do not catch terse searches such as `water
pill`, `pee test`, `belly pain`, `heart tracing`, `colon scope`, or `blood
thinner`.

## Change

Added `config/search_quality_consumer_lay_queries.tsv` with 13 reviewed rows.
Each row has an expected clinical CUI; rows with known literal drift also have
explicit disallowed CUIs.

Added the `consumer_lay_language` layer to `config/search_quality_suite.json` as
a nonblocking known-weakness probe. It uses strict future thresholds:

- 13/13 rows complete at top 10
- 13/13 expected concepts found at top 10
- 0 missing expected concepts
- 0 disallowed concepts at top 10
- 0 wrong-first rows

## Baseline

Live run:

```sh
PYTHONPATH=src python3 scripts/run_search_quality_experiment.py --base-url http://127.0.0.1:8766 --scope umls_evidence --run-family probe --label 'SQI-2026-06-12-002 consumer lay-language baseline' --run-id SQI-2026-06-12-002_consumer_lay_language_baseline --queries config/search_quality_consumer_lay_queries.tsv --query-limit 0 --search-system api --top-k 60 --timeout 90 --output-root build/search_quality_experiments --html-report docs/search_quality_experiments.html --require-api-backend elasticsearch
```

Artifact:
`build/search_quality_experiments/runs/SQI-2026-06-12-002_consumer_lay_language_baseline_sqi-2026-06-12-002-consumer-lay-language-baseline`

Result:

- 5/13 expected concepts found at top 10
- 5/13 rows complete at top 10
- 3/13 top-on-target
- 2/13 strict success at top 10
- 8 rows missing expected concepts
- 8 rows with configured disallowed concepts at top 10
- 10 wrong-first rows
- Overall score 24.6

## Failure Groups

- Literal medication drift: `water pill` ranks water, Water Specimen, and
  Hydrotherapy instead of Diuretics.
- Lay-to-clinical vocabulary gaps: `pee test` and `blood thinner` return no
  visible expected clinical result.
- Anatomy/noise drift: `heart tracing`, `colon scope`, and `stomach scope` rank
  anatomy or unrelated device/gene concepts above ECG, colonoscopy, or EGD.
- Over-specific or literal diabetes wording: `sugar diabetes` ranks the literal
  Sugar Diabetes label and sugar chemicals above Diabetes Mellitus.
- Exact clinical control gap: even `abdominal pain` currently misses the
  expected Abdominal Pain concept at top 10.

## Decision

Keep the lane as a known weakness. Do not make it blocking until it has a green
baseline. Next fixes should add governed lay alias handling and literal-drift
suppression for the rows above, then rerun this lane before promotion.
