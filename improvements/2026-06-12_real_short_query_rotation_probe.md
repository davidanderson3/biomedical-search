# SQI-2026-06-12-001 Real Short-Query Rotation Probe

## Problem

The backlog rule was too linear: after each iteration it pointed back to the
first open P0 row. That made it easy to keep working `SQB-002` long-document
survival and miss nearby P0 work such as `SQB-013` speed, `SQB-003` short-query
expansion, `SQB-004` lay language, `SQB-005` frozen snapshots, and `SQB-006`
gene/protein gating.

Rotating to `SQB-003` exposed a real short-query weakness before any new rows
were promoted.

## Probe

I tested the existing 20 reviewed short-query rows plus six candidate
three-word/high-demand rows:

- `chronic kidney disease` -> `C1561643`
- `urinary tract infection` -> `C0042029`
- `acute kidney injury` -> `C2609414`
- `deep vein thrombosis` -> `C0149871`
- `systemic lupus erythematosus` -> `C0024141`
- `type 2 diabetes` -> `C0011860`

Live run:

```sh
PYTHONPATH=src python3 scripts/run_search_quality_experiment.py --base-url http://127.0.0.1:8766 --scope umls_evidence --run-family release --label 'SQI-2026-06-12-001 real short-query expansion' --run-id SQI-2026-06-12-001_real_short_query_expansion --queries config/search_quality_real_query_regression.tsv --query-limit 0 --search-system api --top-k 60 --timeout 120 --output-root build/search_quality_experiments --html-report docs/search_quality_experiments.html --require-api-backend elasticsearch
```

Artifact:
`build/search_quality_experiments/runs/SQI-2026-06-12-001_real_short_query_expansion_sqi-2026-06-12-001-real-short-query-expansion`

## Result

The candidate expansion failed:

- 19/26 expected concepts at top 10
- 19/26 top-on-target
- 19/26 strict top 10
- 7 poor rows
- 7 wrong-first rows
- 0 configured disallowed concepts at top 10
- 11.25 seconds elapsed with 2 API workers

The new rows were not promoted. The blocking short-query lane remains the
previously reviewed 20-row set.

## Failure Pattern

The live API can expose exact concepts as linked/mentioned evidence without
carrying them into the main ranked hits. Examples:

- `heart failure` showed `C0018801`/`C0018802` in linked evidence while ranking
  `C0018787` Heart first.
- `type 2 diabetes mellitus` showed `C0011860` as linked/mentioned evidence
  while ranking `C0011849` Diabetes Mellitus first.
- Candidate rows such as `chronic kidney disease`, `urinary tract infection`,
  `acute kidney injury`, and `deep vein thrombosis` ranked broader or
  over-specific variants above the expected clinical target.

## Decision

Keep the process change: iterations should cycle across the top backlog window
instead of repeatedly returning to the first open P0.

Reject the SQB-003 row promotion for now. Fix exact linked/mentioned label
carryover first, then rerun the 26-row candidate batch and promote only the rows
that pass.
