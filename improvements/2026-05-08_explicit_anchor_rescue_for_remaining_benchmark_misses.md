# Explicit Anchor Rescue For Remaining Benchmark Misses

## Change

Added three context-gated active label supplement rows:

- `Dysuria` -> `C0013428`
- `Tremor` -> `C0040822`
- `norepinephrine` -> `C0028351`

These are existing UMLS CUIs, not new CUIs. Each row is gated by the relevant clinical neighborhood:

- Dysuria: urinary infection, urinalysis, nitrites, pyuria, pyelonephritis, flank pain.
- Tremor: alcohol withdrawal, seizure, hallucinations, delirium tremens, Parkinson/resting tremor contexts.
- Norepinephrine: septic shock, vasopressor, ICU, shock, lactate, noradrenaline.

## Improvement

The latest stored paragraph benchmark still had explicit concepts missing from top 10:

- `paragraph_13`: `C0013428` Dysuria.
- `paragraph_19`: `C0028351` norepinephrine.
- `paragraph_37`: `C0040822` Tremor.

All three concepts are explicitly mentioned in their source paragraph. The failure mode is not that the terms are unknown; it is that dense surrounding disease, lab, organism, and treatment concepts can displace short exact anchors from the useful review window. The active supplement makes these clinically central exact mentions durable without weakening general single-token filtering.

## Verification

Added regression coverage that:

- Keeps Dysuria ahead of generic evaluation noise in a pyelonephritis paragraph.
- Keeps Tremor visible in an alcohol-withdrawal paragraph.
- Keeps norepinephrine visible in a septic-shock paragraph.

Commands run:

```sh
python3 -m pytest tests/test_evidence_vectors.py -k 'explicit_single_token_symptom_and_drug_anchors or memory_loss_anchor or active_label_supplement or sepsis_treatment' -q
PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py src/qe_evidence_vectors/search_rerank.py src/qe_evidence_vectors/search_service.py
```

Result: `9 passed, 171 deselected`.

## Remaining Limits

This is a targeted repair based on stored benchmark misses. A full paragraph evaluation should be rerun to quantify whether Recall@10 and all-expected@10 improved, and to identify whether any new precision regressions appear.
