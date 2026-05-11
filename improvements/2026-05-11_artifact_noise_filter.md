# Artifact Noise Filter

## What Changed

- Added narrow filters for high-confidence artifact concepts that were still visible after useful-extra calibration.
- Suppressed weak unit/ordinal artifacts such as `Milliliter per Second`, `Sixty Four`, and `Second - ordinal` in multi-concept clinical paragraphs.
- Suppressed generic status/action concepts such as `Update`, `Pending - Day type`, `Wound status`, `Disease susceptibility`, and generic discharge `Teaching`.
- Suppressed broad category concepts such as `Neoplasms`, `Vitamins`, and `Thyroid Hormones` when more specific clinical concepts are present.
- Added tests to verify the artifacts are removed in paragraph context while direct searches for broad/category terms still work.

## Measured Impact

Compared with the calibrated useful-extra audit:

- Suspect top-10 hits: 25 -> 10
- Suspect hits per paragraph: 0.24 -> 0.09
- Low-specificity semantic type flags: 17 -> 7
- Other/uncategorized flags: 13 -> 5
- Visible top-3 nonexpected suspect flags: 5 -> 2

Paragraph search quality remained stable:

- Paragraphs: 106
- Expected concepts: 516
- Recall@10: 516/516 (100.0%)
- Queries with all expected concepts@10: 106/106
- Verdicts: 106 good
- Recall@5 improved from 402/516 to 404/516.

## Interpretation

This is a real precision improvement rather than just evaluation calibration. The remaining 10 audit suspects include several clinically useful explicit findings such as `Diaphoretic`, `Suicidal ideation`, `Fluctuant`, and `Irregular`, plus a few residual artifacts like `Had No Pain`, `Symptoms score`, and `Second Unit of Plane Angle`. The next pass should either add the clinically useful explicit findings to useful extras or build a small generalized rule for residual negated-state/unit artifacts.
