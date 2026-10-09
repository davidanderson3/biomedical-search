# Note-Format Explicit Active-Label Aliases

- Iteration: `SQI-2026-06-25-003`
- Backlog row: `SQB-015 Realistic note-format recall`
- Status: shipped; moved to P1 follow-up
- Type: data

## Problem

The 24-row realistic note-format lane still missed explicit note wording after
the secondary-equivalence replay. The misses were mostly short clinical phrases
or shorthand that appear naturally in notes: `O2 sat`, `glucose`, `A1c`,
`front wheeled walker`, `aPTT`, `cardiopulmonary bypass`, `acute ischemic
stroke`, `left breast lumpectomy`, and lactate trend wording.

## Change

Added context-gated active-label supplement rows for:

- `C0851238` left breast lumpectomy
- `C0523807` O2 sat
- `C0392201` glucose
- `C0043016` front wheeled walker
- `C0019018` A1c
- `C0948008` acute ischemic stroke
- `C0007202` cardiopulmonary bypass
- `C0376261` lactate decreased
- `C0030605` aPTT

Added a focused no-vector `SearchIndex` regression that verifies those explicit
note phrases recover their intended CUIs through the governed supplement layer.

## Result

The live local 24-row clinical text variety lane moved from 14/24 to 21/24
strict top 10 and from 104/115 to 112/115 expected concepts at top 10. It also
reported 113/115 expected concepts at top 20 and top 60, 22 good / 2 mixed / 0
poor rows, 24/24 top-on-target, 0 wrong-first rows, and 0 configured disallowed
concepts at top 10.

The whole-product scorecard rebuilt to raw 84.6 and published 85%.

## Verification

- `python3 scripts/validate_active_label_supplement.py`
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile tests/test_evidence_vectors.py scripts/run_search_quality_experiment.py scripts/build_whole_product_quality_scorecard.py`
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m pytest tests/test_evidence_vectors.py -k 'note_format_explicit_alias or radiology_note_supplements or therapy_note_supplements' -q`
- Live lane artifact: `build/search_quality_experiments/runs/SQI-2026-06-25-003-note-format-explicit-aliases-local_note-format-explicit-alias-active-labels-local/`
- Smoke verification: `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-25-003/verification.md`
- `PYTHONPYCACHEPREFIX=.pycache_local python3 scripts/build_whole_product_quality_scorecard.py`

## Follow-Up

Move `SQB-015` from P0 to P1 follow-up. The prior P0 target is met, but three
top-10 misses remain:

- pathology `C0678222` broad breast carcinoma, where specific `C1412014` is first
- operative `C0694551` right-lower-quadrant target, where the note wording may
  support anatomy/context more than pain
- MRI `C0948008` ischemic stroke, which is recovered by top 20 but not top 10

Continue active P0 work with `SQB-002` approved PubMed long-document recall.
