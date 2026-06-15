# Asserted Diagnosis Over Symptom/Test Noise

Date: 2026-06-11

## Problem

Two current wrong-first rows shared the same trust issue:

- `paragraph_05` ranked heat intolerance and suppressed TSH above suspected thyrotoxicosis.
- `paragraph_87` ranked chronic cough above genetically confirmed cystic fibrosis.

Both queries clearly assert a diagnosis, but first-sentence symptoms/tests had enough local support to outrank the disease target.

## Change

Added `asserted_diagnosis_component` for disease concepts tied to same-sentence `suspected` or `confirmed` wording. The signal also handles matched spans where the cue is embedded, such as `suspected thyrotoxicosis`.

The component is limited to assertable disease semantic types and guarded from historical, family-history, negated, denied, and comparator-arm contexts. Asserted diagnosis hits also get a semantic-context exemption so nearby lab/test wording does not demote the diagnosis.

## Result

Focused live probes now rank:

- `C0040156` Thyrotoxicosis first with `asserted_diagnosis_component` 0.38.
- `C0010674` Cystic Fibrosis first with `asserted_diagnosis_component` 0.40.

The direct query `genetic testing chronic cough sweat chloride test for cystic fibrosis` still ranks `C0428295` Cystic fibrosis sweat test first and gives Cystic Fibrosis no asserted-diagnosis boost.

## Verification

- Focused pytest: 2 passed.
- Focused ranker slice: 8 passed.
- `py_compile`: passed.
- SQI-2026-06-11-014 smoke helper: passed static, focused, standing clinical, rotating 50-query, and patient-portal gates.
- Comparable SQI-2026-06-11-011 rotating seed: passed with 0 wrong-first rows.
- Full 168-row clinical benchmark: passed with 844/874 expected concepts at top 10, 148/168 rows complete at top 10, and 3 wrong-first rows.

## Decision

Keep. This closes WFN-008/WFN-010 without hiding tests or symptoms, but WFN-009/WFN-011/WFN-012 remain open.
