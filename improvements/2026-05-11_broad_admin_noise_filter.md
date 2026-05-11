# Broad Disease And Admin Noise Filter

## What Changed

- Suppressed `Prescribed medications` as generic administrative noise when a query contains real biomedical context beyond the prescribing action.
- Added broad infection-family filtering for concepts such as `Virus Diseases`, `Viral illness`, and `Communicable Diseases` when more specific clinical concepts are present.
- Kept direct searches intact: `prescribed medications` and `viral illness` still return their concepts when the query is actually about those broad/admin terms.
- Updated the paragraph precision audit's generic/status label list so those broad/admin concepts are tracked consistently.

## Measured Impact

Compared with the prior precision-audit pass:

- Suspect top-10 hits decreased from 71 to 66.
- Suspect hits per paragraph decreased from 0.67 to 0.62.
- Low-specificity semantic type flags decreased from 21 to 19.
- Visible top-3 nonexpected flags decreased from 47 to 45.
- `Prescribed medications` and `Virus Diseases` no longer appear as repeated top suspect CUIs.

Paragraph benchmark quality remained stable:

- Paragraphs: 106
- Expected concepts: 516
- Recall@10: 516/516 (100.0%)
- Queries with all expected concepts@10: 106/106
- Verdicts: 106 good
- Recall@5 improved from 400/516 to 402/516.

## Interpretation

This was a useful narrow cleanup. It removes repeated low-value concepts without penalizing direct broad/admin queries or specific infection concepts like BK virus nephropathy. Remaining audit findings are mostly one-off cases, and several are arguably useful nonexpected concepts rather than clear false positives.
