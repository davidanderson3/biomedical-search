# Missed Test Area Audit

## Current Coverage Snapshot

The paragraph benchmark currently has 116 paragraphs. It is broad across common inpatient medicine, cardiology, infectious disease, endocrine, pulmonary, GI, renal, oncology, transplant, obstetrics, pediatrics, ophthalmology, ENT, rheumatology, toxicology, and procedures.

The coverage audit found these weak or missing areas:

| Area | Current matching paragraphs | Gap |
| --- | ---: | --- |
| Vascular emergencies | 0 | No aortic dissection, aneurysm rupture, acute limb ischemia, mesenteric ischemia. |
| Family history / inherited risk | 0 | No family history, carrier status, BRCA/Lynch-style risk, inherited cancer risk. |
| Social determinants | 0 | No housing insecurity, food insecurity, transportation barriers, insurance/access, domestic violence. |
| Nutrition / obesity / eating disorders | 0 | No malnutrition, obesity medicine, bariatric complications, anorexia/bulimia, refeeding syndrome. |
| Palliative / end-of-life care | 0 | No hospice, DNR/code status, goals of care, comfort-focused medication concepts. |
| Broader psychiatry | 0 for schizophrenia/PTSD/anxiety/OCD/ADHD/autism | Current psych coverage is mostly depression, bipolar disorder, and substance use. |
| Pharmacogenomics | 1 weak proxy | HLA-B27 appears, but no CYP2C19, CYP2D6, DPYD, TPMT, HLA-B*5701 medication-safety use cases. |
| Device complications | 2 | Limited pacemaker/ICD/shunt/prosthesis/catheter malfunction or infection coverage. |
| Microbiology susceptibility / resistance | 1 | Little ESBL, VRE, carbapenem resistance, susceptibility-directed therapy. |
| Negation / uncertainty | 5 negation, 13 uncertainty | Present, but still sparse compared with how often clinical text uses absence, rule-out, and differential language. |

## Highest-Value Paragraphs To Add Next

Add test paragraphs in these categories first:

1. **Aortic dissection / vascular emergency**
   - chest/back pain, CTA, Stanford type A/B, blood pressure control, vascular/cardiothoracic surgery.
2. **Family history and inherited cancer risk**
   - breast/ovarian cancer family history, BRCA1/BRCA2 testing, genetic counseling, prophylactic surgery/surveillance.
3. **Social determinants**
   - homelessness, missed insulin because of cost, food insecurity, transportation barriers, care coordination.
4. **Nutrition/eating disorder**
   - anorexia nervosa, hypokalemia, prolonged QT, refeeding risk, phosphate monitoring.
5. **Palliative care**
   - metastatic cancer, goals-of-care discussion, DNR, hospice referral, morphine for dyspnea.
6. **Broader psychiatry**
   - schizophrenia with auditory hallucinations, antipsychotic, extrapyramidal symptoms or metabolic monitoring.
7. **Pharmacogenomics**
   - clopidogrel nonresponse with CYP2C19 loss-of-function, abacavir/HLA-B*5701, DPYD/fluoropyrimidine toxicity.
8. **Device complication**
   - pacemaker lead infection, ICD shock, ventriculoperitoneal shunt malfunction, prosthetic valve thrombosis.
9. **Resistant organism / susceptibility**
   - ESBL E. coli UTI, carbapenem-resistant Enterobacterales, VRE bacteremia, susceptibility-guided antibiotic choice.
10. **More hard language**
   - “no evidence of,” “ruled out,” “family history of,” “screened for,” “at risk for,” and “differential includes.”

## How This Improves Testing

These additions would stress areas that are clinically useful but underrepresented in the current benchmark. They also test whether the search interface can distinguish:

- Current patient findings from family history and risk factors.
- Diagnoses from screening/prevention concepts.
- Social/behavioral context from diseases.
- Drug response/safety relations from ingredient-only drug matches.
- Device/anatomy/procedure bundles from generic procedure labels.

## Verification

Ran a local TSV coverage scan over `config/search_quality_paragraph_queries.tsv`.

Key counts:

- Vascular emergencies: 0
- Family history / genetic risk: 0
- Social determinants: 0
- Nutrition / eating disorders: 0
- Palliative / end-of-life: 0
- Broader psychiatry terms: 0
- Pharmacogenomics: 1 weak proxy
- Negation / absence language: 5
- Cohort / research language: 6

## Follow-Up

Implemented the highest-value gaps in `config/search_quality_paragraph_queries.tsv` as paragraphs 117-133. The measured post-change evaluation is documented in `improvements/2026-05-11_search_style_gap_paragraphs.md`.
