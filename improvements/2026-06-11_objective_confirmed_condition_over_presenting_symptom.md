# Objective-Confirmed Condition Over Presenting Symptom

- Iteration: SQI-2026-06-11-017
- Date: 2026-06-11
- Type: ranking, benchmark
- Status: shipped

## Problem

The full clinical benchmark still had one wrong-first row. In `paragraph_135`,
the query said CT angiography showed pulmonary embolism after presenting
pleuritic chest pain and dyspnea, but the ranker returned `C0008031` Chest Pain
above `C0034065` Pulmonary Embolism.

## Change

Added `objective_confirmed_condition_component` for assertable disease spans
that immediately follow same-sentence objective confirmation verbs such as
`showed`, `demonstrated`, `revealed`, or `confirmed` when the same sentence has
an imaging or procedure source token such as CT, angiography, ultrasound, MRI,
biopsy, pathology, or echocardiography.

The component is guarded so direct symptom or procedure lookups do not inherit
the diagnosis boost. The same condition also exempts the confirmed disease hit
from the procedure-context semantic penalty that was pushing the diagnosis below
the presenting symptom.

The ranking change exposed `C5395033` Severe aortic valve stenosis as the top
result for an echocardiography paragraph that explicitly says severe aortic
valve stenosis. That concept was already reviewed as a useful extra, so the
iteration also promoted it to an acceptable alternative for the broader
`C0003507` Aortic Valve Stenosis target.

## Verification

- Focused unit tests: 5 passed.
- Focused ranker slice: 9 passed.
- Static syntax check: `py_compile` passed.
- Live target probe: Pulmonary Embolism ranked first with
  `objective_confirmed_condition_component` 0.56 and no semantic-context
  penalty.
- Direct controls: `pleuritic chest pain` still ranked Chest Pain first, and
  `CT angiography` still ranked Computed Tomography Angiography first; neither
  received the new component.
- Formal SQI-2026-06-11-017 smoke helper passed static, focused, standing
  clinical, rotating 50-query, and patient-portal gates.
- Comparable SQI-2026-06-11-011 rotating seed stayed at 0 wrong-first rows.
- Final full clinical rerun had 844/874 expected concepts at top 10, 148/168
  rows complete at top 10, 166/168 strict top 20, 168/168 top-on-target, and
  0 wrong-first rows.
