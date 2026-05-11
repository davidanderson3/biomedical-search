# People And Population Bucket

## Request

Work on the next logical high-impact improvement and document exactly how it improved things.

## Change

- Added a `People & Populations` semantic result bucket.
- Kept it separate from `Organisms` so bacteria, viruses, and fungi do not mix with patients, age groups, and population groups.
- Added targeted semantic types: Human, Group, Age Group, Family Group, Population Group, Patient or Disabled Group, and Professional or Occupational Group.

## Why This Was Next

After adding organisms, the remaining `LIVB` gap was human and population concepts. Pregnancy, pediatric, geriatric, cohort, and occupational-health queries often retrieve people/population CUIs that were not displayed in any semantic bucket.

## Measured Effect

- `pregnant woman gestational diabetes insulin fetal ultrasound`
  - Before: 5 displayed groups: DISO disease, DISO finding, CHEM, PROC, Observations & Lab Results.
  - After: 6 displayed groups: DISO disease, DISO finding, People & Populations, CHEM, PROC, Observations & Lab Results.
  - Newly displayed people concept: Human, Female adult.

- `pediatric asthma exacerbation child wheezing albuterol`
  - Before: 5 displayed groups: DISO disease, DISO finding, CHEM, PROC, Observations & Lab Results.
  - After: 6 displayed groups: DISO disease, DISO finding, People & Populations, CHEM, PROC, Observations & Lab Results.
  - Newly displayed people concept: Child Individual.

- `older adult falls frailty delirium nursing home`
  - No displayed-group count change in the sampled top 60 results because no matching people/population CUI appeared in that result set.

## Verification

- `node --check docs/search_quality/app.js` passed.
- Confirmed the running server is serving the updated JavaScript with `People & Populations`.
- Confirmed `/api/status` is healthy.

## Result

This improves display coverage for clinically relevant demographic and population concepts without broadening the organism bucket. It is a display-bucketing change only; retrieval, ranking, evidence, and indexing are unchanged.
