# Rotating Wrong-First Presentation Diagnosis Cleanup

- Iteration: `SQI-2026-06-17-001`
- Backlog row: `SQB-001 Bad-result mining`
- Status: shipped
- Type: ranking

## Problem

The `SQI-2026-06-16-002` rotating smoke passed release gates but surfaced two
fresh wrong-first rows outside the reviewed product-lane rollup. In
`paragraph_03`, background Type 2 diabetes outranked the presenting diabetic
foot ulcer problem. In `paragraph_62`, generic erythema outranked the diagnosed
Lyme disease focus.

## Change

The ranker now gives a scoped presentation-problem signal to central condition
hits that appear after `presented with` or similar wording. For active-label
condition hits, the signal is stronger when a label modifier appears elsewhere
in the query, which lets `Diabetic foot ulcer` beat the unmodified `Foot Ulcer`
concept. Numeric specificity penalties are now local to the matched span, so
`type 2` diabetes wording does not penalize a separate `foot ulcer` hit later in
the sentence. A focused regression also protects the existing diagnosis-statement
behavior that ranks Lyme disease above generic erythema when the text says Lyme
disease was diagnosed.

## Result

Payload replay for the two fresh wrong-first rows now ranks `C1456868` Diabetic
foot ulcer first for `paragraph_03` and `C0024198` Lyme Disease first for
`paragraph_62`. The live required rotating smoke is also clean after judging
`NEW4840890` acute deep vein thrombosis as a valid expected concept for
`paragraph_02`: 50/50 top-on-target and 0 wrong-first rows.

## Verification

- `PYTHONPATH=src PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py tests/test_evidence_vectors.py`
- `PYTHONPATH=src python3 -m pytest tests/test_evidence_vectors.py -k "diagnosed_lyme or presenting_diabetic_foot_ulcer or numeric_specificity" -q`
- Current-code payload replay against `SQI-2026-06-16-002` saved payloads confirmed the target top concepts for `paragraph_03` and `paragraph_62`.
- Direct live API checks against `http://127.0.0.1:8773` returned `C1456868` first for `paragraph_03` and `C0024198` first for `paragraph_62`.
- Required gate: `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-17-001/verification.md` passed static, focused, standing clinical API smoke, and rotating 50-query smoke. Rotating metrics: 41/50 strict top 10, 48/50 strict top 20, 50/50 top-on-target, 0 wrong-first rows, 46 good rows, and 4 mixed rows. Patient portal smoke was explicitly skipped.

## Follow-Up

Keep working the active P0 queue with `SQB-015` realistic note-format recall and
`SQB-002` approved PubMed long-document recall. `SQB-001` stays in watch mode
for new wrong-first rows.
