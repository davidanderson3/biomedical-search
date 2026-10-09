# Note-Format Lab-Review Equivalence Replay

- Iteration: `SQI-2026-06-24-001`
- Backlog row: `SQB-015 Realistic note-format recall`
- Status: partial shipped
- Type: benchmark-equivalence, process

## Problem

The realistic note-format lane had one `poor` row after the June 17 routing fix:
`clinical_text_variety_17_lab_anemia`. The saved API payload already returned
clinically useful first-page concepts for the lab-review note: iron deficiency
anemia, packed red blood cell transfusion, hemoglobin measurement, and ferritin
measurement.

The benchmark only accepted the broader blood-transfusion, hemoglobin, and
ferritin CUIs, so the row was scored as a severe recall miss even though the
specific measurement/procedure results were clinically acceptable for the
numeric lab-review wording.

## Change

Added reviewed acceptable-CUI alternatives for this context:

- `C0005841` Blood Transfusion accepts `C0199962` Transfusion of packed red
  blood cells when the note explicitly says packed red blood cell transfusion.
- `C0019046` Hemoglobin accepts `C0518015` Hemoglobin measurement when the note
  gives a numeric hemoglobin result.
- `C0015879` Ferritin accepts `C0373607` Ferritin measurement when the note gives
  a numeric ferritin result.

A focused paragraph-evaluator regression now verifies that the lab-review row
counts these three accepted alternatives and becomes `good`.

## Result

Saved June 17 note-format API payloads were replayed with the updated acceptable
CUI table. The lane moved from 8/24 to 9/24 strict top 10, from 94/115 to 97/115
expected concepts at top 10, from 102/115 to 105/115 at top 20, and from
9 good / 14 mixed / 1 poor rows to 10 good / 14 mixed / 0 poor rows.

This did not close `SQB-015`. The lane is still diagnostic and remains the top
P0 recall lane because 15/24 note-format rows still miss at least one expected
concept in the first page.

## Verification

- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile tests/test_evidence_vectors.py scripts/evaluate_paragraph_quality.py scripts/run_search_quality_experiment.py`
- `python3 -m pytest tests/test_evidence_vectors.py::test_paragraph_evaluator_counts_configured_lab_review_measurement_alternatives -q`
- Saved-payload replay artifact: `build/search_quality_experiments/runs/SQI-2026-06-24-001_note-format-lab-equivalence-replay/`
- Verification note: `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-24-001/verification.md`
- `python3 scripts/build_whole_product_quality_scorecard.py`

## Follow-Up

Keep `SQB-015` open. The next note-format iteration should improve actual
secondary-concept recall in radiology, pathology, operative, nursing, therapy,
home-health, and prior-authorization rows rather than relying on additional
equivalence exceptions.
