# Note-Format Secondary Equivalence Replay

- Iteration: `SQI-2026-06-25-002`
- Backlog row: `SQB-015 Realistic note-format recall`
- Status: partial shipped
- Type: benchmark-equivalence

## Problem

The latest note-format run still marked three rows incomplete even though the
saved first page already contained clinically specific equivalents supported by
the note wording:

- home-health heart failure: `Leg edema` for the edema target
- endocarditis consult: `Transthoracic echocardiography` for the echocardiography target
- stroke discharge: `Anticoagulation Therapy` for the anticoagulation target

This was a benchmark scoring gap, not a runtime ranking gap.

## Change

Added reviewed acceptable-CUI alternatives for those note-format equivalents in
`config/search_quality_acceptable_cui_alternatives.tsv`.

Added a focused paragraph-evaluator regression covering the three replayed
cases so the equivalence behavior stays explicit.

## Result

The saved-payload replay moved the clinical text variety lane from 11/24 to
14/24 strict top 10 and from 101/115 to 104/115 expected concepts at top 10. It
also reported 107/115 expected concepts at top 20 and top 60, 15 good / 9 mixed
/ 0 poor rows, 24/24 top-on-target, 0 wrong-first rows, and 0 configured
disallowed concepts at top 10.

The whole-product scorecard rebuilt to raw 80.0 and published 80%.

## Verification

- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile tests/test_evidence_vectors.py scripts/evaluate_paragraph_quality.py scripts/run_search_quality_experiment.py scripts/build_whole_product_quality_scorecard.py`
- `python3 -m pytest tests/test_evidence_vectors.py -k 'note_format_equivalence_replay or lab_review_measurement_alternatives'`
- Saved replay artifact: `build/search_quality_experiments/runs/SQI-2026-06-25-002_note-format-secondary-equivalence-replay/`
- Smoke verification: `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-25-002/verification.md`
- `python3 scripts/build_whole_product_quality_scorecard.py`

## Follow-Up

Keep `SQB-015` open. Ten note-format rows still miss at least one expected
secondary concept at top 10. The next batch should target pathology,
operative-note, nursing/lab, MRI stroke, prior-authorization, therapy device,
and heparin aPTT misses as real recall work rather than additional scoring
exceptions.
