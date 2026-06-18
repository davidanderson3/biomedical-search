# Procedure Coverage Without CPT

## Change

Added `docs/procedure_coverage_without_cpt.html` and linked the policy from `docs/technical_pipeline.html`.

## How It Improved Things

The procedure strategy now has an explicit licensing boundary: the open UMLS 2.0 layer should not ship CPT codes, CPT descriptors, or public CPT-derived crosswalks. Instead, procedure coverage should come from open or permitted vocabularies, structured procedure bundles, literature/open-reference evidence, and local `NEW#######` concepts where clinically useful procedure granularity is missing.

The plan also defines a safe private-adapter pattern for licensed deployments: users can load CPT locally, mappings stay private, and public artifacts continue to contain only open/local concept IDs.

## Practical Impact

This lets the system improve procedure search without waiting for CPT:

- build granular procedure bundles from action + anatomy + approach + modality + intent
- map bundles to MeSH, LOINC, ICD-10-PCS, HCPCS Level II, SNOMED CT where permitted, NCI/NCIt, and other allowed anchors
- create evidence-backed `NEW#######` concepts for important missing procedures
- penalize generic procedure fragments in search results

## Limitation

This is a policy/design improvement, not a parser implementation. The next code step is a procedure-bundle extractor and ranker rules that prefer clinically meaningful procedure bundles over generic action/modifier concepts.
