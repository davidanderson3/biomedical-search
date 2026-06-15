# Structured Clinical Context Buckets Prospectus

## Purpose

The search interface should help users see not only which concepts were found,
but what role each concept plays in the text. A long clinical note can mention
the active complaint, current assessment, tests, treatment plan, copied-forward
history, and return precautions in the same paragraph. Those should not appear
as one flat concept list.

This prospectus defines the first product layer for role-aware clinical
structure. It is English-only for now.

## Initial Buckets

| Bucket | Meaning | Example from stroke note |
| --- | --- | --- |
| Chief Concern | Why the patient is seeking care now. | Worsening left sided weakness. |
| Active Assessment | Current diagnosis or working assessment. | Acute ischemic stroke. |
| Exam & Findings | Observed signs and bedside findings. | Facial droop. |
| Tests & Objective Data | Imaging, labs, procedures, and measured findings. | Brain MRI showed acute infarct in right MCA territory. |
| Plan & Treatment | Treatment, workup, and management decisions. | Aspirin, statin, and thrombolysis evaluation. |
| Watch For | Warning signs, return precautions, and safety checks. | Persistent neurologic deficit, recurrent weakness, worsening facial droop. |
| Older History / Not Active | Copied-forward or explicitly inactive history. | Generalized tonic clonic seizure, prior levetiracetam, no active status epilepticus decision. |
| Handoff & Documentation | Repeated chart text, handoffs, and routine note language. | ED note, consultant note, discharge summary, medication list, nursing handoff, patient instructions. |
| Follow-Up | Next review, monitoring, and unresolved decisions. | Follow-up to review brain MRI, aspirin/statin management, and whether thrombolysis evaluation is still needed. |

## Status Dimensions

Buckets should not be the only structure. Each mention or bucket item also needs
status attributes:

- `current`: active in the present encounter.
- `historical`: old or copied-forward chart context.
- `negated`: explicitly absent or not active.
- `planned`: intended but not completed.
- `completed`: performed or already resulted.
- `instructional`: patient education, return precaution, or follow-up wording.
- `administrative`: scheduling, handoff, repeated-note, or routine chart text.

For example, `acute ischemic stroke` is current, `brain MRI` is completed
objective data, `thrombolysis evaluation` is planned or open, `status
epilepticus` is negated/not active, and `generalized tonic clonic seizure` is
historical.

## Interface Direction

The current prototype adds a compact **Clinical Context** panel below the ranked
search results. It uses client-side section cues and linked concept spans to
group the submitted text into the initial buckets. This is intentionally a
display prototype, not the final extraction engine.

The target interface should:

- Keep semantic concept groups first, then add role buckets below the ranked
  results as a secondary review surface.
- Show the exact text snippet that triggered each bucket.
- Show linked concepts inside each bucket as clickable CUI chips.
- Keep copied-forward history visible but clearly separated from current
  assessment and plan.
- Show warning signs and follow-up needs as their own review surfaces.
- Avoid treating routine handoff/documentation language as clinical evidence.

## Data Contract Target

The API should eventually return a structured context object alongside hits:

```json
{
  "clinical_context": {
    "buckets": [
      {
        "key": "active_assessment",
        "label": "Active Assessment",
        "items": [
          {
            "text": "The active assessment is acute ischemic stroke.",
            "start": 72,
            "end": 120,
            "status": "current",
            "concepts": [
              {
                "cui": "C0948008",
                "label": "Acute ischemic stroke",
                "semantic_group": "DISO",
                "role": "diagnosis"
              }
            ]
          }
        ]
      }
    ]
  }
}
```

The client-side prototype can be replaced by this payload without changing the
visual layout.

## Benchmark Plan

Add judged rows that evaluate role assignment, not only CUI recall:

- Current diagnosis outranks copied-forward history.
- Completed tests are distinct from planned tests.
- Watch-for concepts are visible but not treated as active diagnoses.
- Medication list history is separate from current treatment.
- Repeated handoff text does not create duplicate apparent evidence.

The stroke note supplied for this prospectus should become the first structured
context fixture once the API returns bucket annotations.
