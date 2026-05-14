# Clinician Reference Source Policy

## Problem

Merck/MSD Manual Professional, AAFP, Medscape, and similar clinician reference
sites are useful for symptom-to-differential language, but free-to-read access is
not the same as permission to scrape, redistribute, embed, or publish derived
artifacts.

## Change

- Kept NCI, CDC, FDA, and NIDDK as the public default reference-page sources.
- Added policy entries for BMJ Best Practice, NICE CKS, NCBI Bookshelf
  StatPearls, Patient.info Professional Reference, GPnotebook, and WikEM.
- Marked these added clinician references as blocked by default unless a private
  deployment has permission, licensed content, or a compliant source-specific
  reuse strategy.
- Added a test that keeps `config/reference_source_policy.tsv` aligned with the
  fetcher policy registry.

## Notes

Useful source classes for private deployment:

- General clinician references: Merck/MSD Manual Professional, Medscape,
  StatPearls, BMJ Best Practice.
- Primary-care diagnostic reasoning: AAFP, NICE CKS, GPnotebook, Patient.info
  Professional Reference.
- Emergency medicine differential/workup language: WikEM.

All restricted sources should be ingested as locally supplied permitted excerpts
or through source-specific licensed APIs, not as default public rebuild inputs.
