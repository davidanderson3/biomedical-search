# Open Literature Drug Enrichment Without EHR Sources

## Problem

Drug enrichment needed to improve, but it should not rely on real EHR/clinical-note data. The previous drug-enrichment shard was separate from the main evidence shards, but the builder did not explicitly enforce a no-EHR source policy and covered only a small set of drug targets.

## Change

Drug enrichment now has an explicit source policy: `open_literature_and_drug_vocabularies_only_no_ehr`. The enrichment scanner skips corpus paths and source metadata that look like EHR, electronic medical records, or clinical notes, even if those files are present locally or passed on the command line. Drug-enrichment document text now calls these snippets `Open literature evidence` rather than `Real-world evidence`.

Expanded ingredient-level drug targets from 9 to 27 by adding common drugs seen in clinical/research examples: apixaban, sildenafil, lisinopril, levodopa, lorazepam, aspirin, tamoxifen, levetiracetam, hydrocortisone, amoxicillin, cephalexin, ceftriaxone, doxycycline, albuterol, methotrexate, pantoprazole, timolol, and oseltamivir. Added conservative literature-derived relation rules for drug classes, indications/uses, monitoring/effects, and high-signal adverse events.

The builder was also made faster: it now scans corpus files once with a combined label matcher instead of rescanning the same open literature files separately for each target drug.

## Improvement

Rebuilt `build/drug_enrichment/` using open literature and drug-vocabulary sources only.

- Drug enrichment concepts: 27
- Open literature mentions: 1,674
- Literature-derived relation rows: 61
- Corpus paths used: 12
- EHR corpus paths in manifest: none

Examples of newly supported drug relations:

- `apixaban` -> anticoagulants, atrial fibrillation, venous thrombosis, pulmonary embolism, bleeding
- `sildenafil` -> pulmonary hypertension
- `lorazepam` -> alcohol withdrawal syndrome, seizures
- `cephalexin` -> antibiotics, cellulitis
- `doxycycline` -> antibiotics, Lyme disease, pelvic inflammatory disease
- `albuterol` -> asthma, wheezing

## Limits

These are high-confidence rule-driven relations, not a full drug knowledge graph. Some valid relations are still missing because they require better open label extraction, RxClass/ATC class normalization, or curated contraindication/adverse-event parsing. The main server can still load older non-drug evidence shards depending on runtime configuration; this change specifically makes the drug-enrichment bundle open literature/vocabulary only.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py -k drug_enrichment -q` passed: 5 passed.
- `python3 scripts/build_drug_enrichment.py` wrote 27 documents and 27 vectors.
- Rebuilt artifact check: 27 docs, 61 relations, 1,674 mentions, `Open literature evidence` heading present.
- `node --check docs/search_quality/app.js` passed.
