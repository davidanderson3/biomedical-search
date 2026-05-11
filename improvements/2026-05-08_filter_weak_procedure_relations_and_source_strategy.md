# Filter Weak Procedure Relations and Source Strategy

## Problem

The `heart failure with reduced ejection fraction` result set still showed weak related procedure items from broad CCPSS `clinically_associated_with` rows, including amputations. These rows are structured but too nonspecific for the default semantic group cards when the procedure label does not overlap the source concept.

## Change

Added a semantic bucket visibility filter for procedure relations from broad CCPSS `clinically_associated_with` rows. The filter hides those rows unless the related label shares meaningful lexical overlap with the source concept. Stronger relation types such as SNOMED `focus_of`, MEDLINEPLUS `related_to`, and embedding-supported neighbors remain visible.

## Improvement

For `heart failure with reduced ejection fraction`, the Procedures bucket changed from 12 related procedure items to 8. The four removed items were CCPSS broad associations:

- `AMPUTATION`
- `Amputation above-knee (procedure)`
- `Amputation of Leg Through Tibia and Fibula`
- `Replacement of aortic valve (procedure)`

Kept items included `heart transplantation`, `CARDIAC REHABILITATION`, `Heart failure screen`, `Documentation of heart failure medication action plan`, and `Nutrition therapy for congestive heart failure`.

## Source Strategy

More PubMed content will help, but only if it is targeted. Broadly adding more abstracts will mostly increase vector volume and ambiguous co-occurrence. The next PubMed work should focus on high-citation, recent, review/guideline, and topic-gap queries where current buckets miss clinically obvious relations.

Other sources are likely higher yield than indiscriminate PubMed expansion: DailyMed/openFDA labels for drug indications, contraindications, adverse reactions, and monitoring; LOINC and clinical measurement catalogs for observations; HPO/Orphanet-style phenotype links for gene/disease/finding coverage; Wikipedia/OpenAlex as readable open evidence and citation-prioritized literature triage. The useful pattern is source-specific relation extraction plus provenance, not just more text.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py::test_semantic_buckets_hide_weak_ccpss_procedure_associations` passed.
- `node --check docs/search_quality/app.js` passed.
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_semantic_buckets.py` passed.
- The live server was restarted on `http://127.0.0.1:8766/` and the HFrEF smoke query showed the expected reduction in weak procedure relations.
