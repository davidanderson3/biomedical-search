# Residual Noise Finish

## What Changed

- Added final high-confidence residual artifact filters for:
  - negated-state pain artifacts such as `Had No Pain`
  - ordinal/unit artifacts such as `Second Unit of Plane Angle`
  - generic scoring/status artifacts such as `Symptoms score`
  - generic benefit artifacts in non-risk/benefit clinical context
- Added useful-extra audit rows for explicit, clinically useful results that were being counted as suspects only because they were not in the core expected set:
  - `Diaphoretic`
  - `Suicidal ideation`
  - `sodium` in the sodium zirconium cyclosilicate paragraph
  - `Fluctuant`
  - `Irregular`
- Added regression coverage for the new residual artifact patterns while preserving direct searches for broad/status concepts.

## Measured Impact

Compared with the previous calibrated audit:

- Suspect top-10 hits: 10 -> 4
- Suspect hits per paragraph: 0.09 -> 0.04
- Low-specificity semantic type flags: 7 -> 2
- Other/uncategorized flags: 5 -> 1
- Useful extra top-10 hits: 41 -> 46

Search quality remained stable:

- Paragraphs: 106
- Expected concepts: 516
- Recall@10: 516/516 (100.0%)
- Queries with all expected concepts@10: 106/106
- Verdicts: 106 good
- Recall@5: 404/516

## Interpretation

This ends the current precision-cleanup loop. The remaining four audit suspects are mixed: `Right side of heart` is arguably useful in a right-heart-strain paragraph, while `systemic symptoms`, `Rate of urine output, function`, and `Risks and Benefits` are lower-value but not recurring. Further single-case suppression would risk overfitting. The next higher-value step is to broaden evaluation coverage with new paragraph domains or improve semantic typing/bucketing for awkward-but-useful concepts.
