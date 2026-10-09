# Note-Format Radiology And Therapy Aliases

- Iteration: `SQI-2026-06-25-001`
- Backlog row: `SQB-015 Realistic note-format recall`
- Status: partial shipped
- Type: data

## Problem

The realistic note-format lane still missed explicit secondary concepts after
the lab-review replay. The radiology CTA row missed `CT angiogram` and `acute
segmental pulmonary embolism`. A fresh local-backend run also showed the therapy
hip-fracture row could put an off-target pelvis-fracture concept first while
missing occupational and physical therapy concepts.

## Change

Added context-gated active-label supplement rows for explicit note wording:

- `C1536105` CT angiogram
- `C2882221` acute segmental pulmonary embolism
- `C0019557` displaced hip fracture
- `C1318464` occupational therapy evaluation
- `C0949766` physical therapy

Focused regressions verify that the radiology and therapy note wording recovers
the intended CUIs through the governed supplement layer.

## Result

The live 24-row clinical text variety lane moved from 9/24 to 11/24 strict top
10, from 97/115 to 101/115 expected concepts at top 10, and from 10 good / 14
mixed to 12 good / 12 mixed rows. It preserved 24/24 top-on-target, 0 wrong-first
rows, 0 configured disallowed concepts at top 10, and 0 poor rows.

The whole-product scorecard rebuilt to raw 78.0 and published 78%. The prior
major-weakness cap is not active because realistic note formats now score above
60, but approved PubMed long abstracts remain below 60.

## Verification

- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile scripts/validate_active_label_supplement.py tests/test_evidence_vectors.py scripts/run_search_quality_experiment.py`
- `python3 scripts/validate_active_label_supplement.py`
- `PYTHONPATH=src:scripts PYTHONPYCACHEPREFIX=.pycache_local python3 -m pytest tests/test_evidence_vectors.py::test_radiology_note_supplements_recover_ct_angiogram_and_acute_segmental_pe tests/test_evidence_vectors.py::test_therapy_note_supplements_recover_hip_fracture_rehab_terms tests/test_evidence_vectors.py::test_paragraph_evaluator_counts_configured_lab_review_measurement_alternatives -q`
- Live lane artifact: `build/search_quality_experiments/runs/SQI-2026-06-25-001-note-format-radiology-therapy-aliases_sqb-015-note-format-radiology-and-therapy-aliases/`
- Smoke verification: `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-25-001/verification.md`
- `PYTHONPATH=src:scripts PYTHONPYCACHEPREFIX=.pycache_local python3 scripts/build_whole_product_quality_scorecard.py`

## Follow-Up

Keep `SQB-015` open. The next useful batch should target the remaining
pathology, operative, nursing/lab, MRI stroke, prior-authorization, home-health,
anticoagulation, and endocarditis secondary-concept misses.
