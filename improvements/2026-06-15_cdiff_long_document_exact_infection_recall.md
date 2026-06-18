# C. difficile long-document exact infection recall

- Iteration: `SQI-2026-06-15-005`
- Backlog row: `SQB-002 Long-document survival`
- Status: shipped
- Type: ranking, long-document

## Problem

The approved PubMed row `pubmed_cdiff_antibiotic_diarrhea_21288078` repeatedly mentions C. difficile infection, but `C0343386` Clostridium difficile infection stayed outside the first 10 answers. The row was complete by rank 20, but the first page was crowded by drug/product, organism, toxin, and generic infection hits.

## Change

Added a narrow long-document recall path for exact disease/finding mentions with strong evidence. A low-ranked candidate can now pass the first-page recall candidate gate only when it has all of the following:

- DISO/FIND semantic group
- at least three direct label tokens from the query
- both `chunk_vector` and `mention` support
- at least two supported chunks and two mentions
- high section weight
- a low but nonzero rank-score floor

This avoids a CUI-specific boost and does not accept organism or generic infection concepts as substitutes for the disease concept.

## Verification

The focused unit slice passed, including a regression modeled on the fidaxomicin-versus-vancomycin row. A targeted live run against a fresh `http://127.0.0.1:8768` API found all 3 expected CUIs in the first 10 answers, with `C0343386` at rank 10 and 0 configured disallowed concepts. The formal smoke helper passed standing clinical API smoke.

## Remaining Work

Rerun the full 13-row approved PubMed suite on this code. If the C. difficile result holds, continue with the EGFR progression-free-survival/regimen miss, status-migrainosus aura-variant misses, or hypocomplementemia/Complement 3.
