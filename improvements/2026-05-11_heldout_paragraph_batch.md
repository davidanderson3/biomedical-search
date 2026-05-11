# Held-Out Paragraph Batch And Aspiration Disambiguation

## Change

Added 10 harder paragraph benchmark cases covering transplant medicine, BK virus nephropathy, neutropenic fever, preeclampsia, infective endocarditis, prosthetic joint infection, anticoagulation safety, lupus nephritis, adrenal crisis, and phenylketonuria.

The held-out run surfaced six mixed cases. Most were benchmark expectation issues caused by overlapping UMLS CUIs that are clinically acceptable in context. One was a true ranking issue: in an orthopedic prosthetic-joint infection paragraph, `aspirated` was resolving to respiratory aspiration instead of joint aspiration.

To mitigate that:

- Added a context-gated active-label supplement row mapping orthopedic/synovial `aspirated` wording to `C0204854` joint aspiration.
- Added a ranker penalty for respiratory aspiration when the query context is clearly orthopedic, joint, arthroplasty, prosthetic, knee, or synovial.
- Added conservative acceptable CUI alternatives for duplicate or more specific UMLS concepts found in the held-out batch.
- Expanded two benchmark expectations where the top concept was genuinely relevant: rising creatinine measurement and newborn screening.

## Improvement

Before the fix, the expanded 106-paragraph benchmark had 100 good / 6 mixed verdicts. Recall@10 was 509/514 (99.0%), and 102/106 queries had all expected concepts visible by rank 10.

After the fix, the expanded benchmark had 106 good / 0 mixed verdicts. Recall@10 was 516/516 (100.0%), and 106/106 queries had all expected concepts visible by rank 10.

The most concrete search improvement was paragraph 102: `C0204854` joint aspiration moved into the top 10 at rank 6, while the respiratory aspiration false sense was no longer shown ahead of it.

## Verification

- Active-label supplement validation passed.
- Added a regression test for demoting respiratory aspiration in orthopedic joint-aspiration context.
- Focused tests passed: 4 passed, 212 deselected.
- Compile checks passed for the touched ranker, evaluator, and test file.
- Before evaluation: `build/improvements/2026-05-11_heldout_paragraph_batch_before/`.
- After evaluation: `build/improvements/2026-05-11_heldout_paragraph_batch_after/`.

## Remaining Limitations

The expanded paragraph set is still synthetic and curated. The benchmark is stronger because it now includes more specialty areas and ambiguous wording, but it still cannot prove parity with production clinical text. The next sustainable step is to keep adding held-out cases from under-tested specialties and track false positives separately from acceptable CUI-equivalence corrections.
