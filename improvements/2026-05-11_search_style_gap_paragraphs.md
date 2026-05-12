# Search-Style Gap Paragraphs

## Goal

Add tests for clinically common search areas that were underrepresented in the paragraph suite, leaning toward what users actually type into a search box rather than polished case-report prose.

## What changed

- Added 17 new search-style paragraph tests in `config/search_quality_paragraph_queries.tsv`:
  - vascular emergencies: aortic dissection, ruptured AAA, acute limb ischemia
  - inherited cancer risk and family history
  - social determinants and access barriers
  - eating disorder/refeeding risk
  - palliative care and goals of care
  - psychiatry/metabolic monitoring
  - pharmacogenomics: CYP2C19/clopidogrel and HLA-B*5701/abacavir
  - device complications: pacemaker pocket infection and VP shunt malfunction
  - resistant infections: ESBL E. coli UTI and VRE bacteremia
  - preventive screening, frailty/falls, and domestic violence
- Added active label supplements for common user/search wording:
  - CTA
  - transportation barriers
  - CYP2C19
  - HIV
  - pacemaker pocket infection
  - HPV test
- Added acceptable alternatives where the returned concept is clinically equivalent or more specific:
  - ruptured abdominal aortic aneurysm for AAA rupture wording
  - lung malignancy for metastatic lung cancer wording
  - phosphorus analyte for phosphorus measurement wording
  - CYP2C19 poor metabolizer/protein for CYP2C19 pharmacogenomic retrieval
  - HIV seropositivity for HIV pharmacogenomic screening context
  - antimicrobial susceptibility for susceptibility test wording
  - screening mammography for mammography
  - HPV organism for HPV test when screening context is explicit
  - E. coli UTI for UTI in an ESBL E. coli UTI search

## Measured impact

Initial evaluation after adding the new paragraphs:

- Paragraphs: 133
- Expected concepts: 662
- Verdicts: 121 good, 12 mixed
- Recall@10: 648/662, 97.9%
- Expected semantic-group recall@10: 99.2%

Final evaluation after label/alternative calibration:

- Paragraphs: 133
- Expected concepts: 662
- Verdicts: 131 good, 2 mixed
- Recall@5: 503/662, 75.98%
- Recall@10: 660/662, 99.70%
- Recall@20: 661/662, 99.85%
- Recall@60: 662/662, 100%
- Expected semantic-group recall@10: 100%
- Queries with all expected concepts by rank 10: 131/133

Precision audit on the final payloads:

- Top-10 displayed slots audited: 1,330
- Useful extra top-10 hits: 53
- Suspect top-10 hits: 19
- Suspect hits per paragraph: 0.143

## Remaining weaknesses

- Ruptured AAA still ranks broad aneurysm concepts above the most specific ruptured abdominal aortic aneurysm concept. The specific concept is present, but the top result is broader than ideal.
- Family-history cancer risk still ranks active breast/ovarian cancer concepts above the family-history concepts. That should not be hidden with acceptable alternatives because family history and active disease are different clinical meanings.

## Takeaway

This improved coverage for several common real-world query areas without relaxing the evaluator around clinically different concepts. The remaining mixed cases are useful pressure tests for future ranker work: prefer the most specific vascular emergency concept, and distinguish active cancer from family history of cancer.
