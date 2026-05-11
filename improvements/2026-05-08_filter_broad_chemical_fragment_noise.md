# Filter Broad Chemical Fragment Noise

## Problem

Drug queries can surface broad chemical fragment/class concepts in the Drugs bucket. For example, `preeclampsia magnesium sulfate proteinuria` returned `Sulfates, Inorganic` beside the clinically useful drug `magnesium sulfate`.

## Change

Added a Drugs-bucket display filter for broad comma-inverted chemical fragment labels such as `Sulfates, Inorganic`. The filter targets broad fragment/class labels with chemical class terms like sulfates, chlorides, nitrates, oxides, phosphates, or salts paired with broad modifiers like inorganic/organic.

This keeps active drugs and ingredient names visible while suppressing broad chemical fragments that are usually not useful as clinical search results.

## Improvement

Expected effect after server reload:

- `Sulfates, Inorganic` will no longer occupy the Drugs bucket.
- `magnesium sulfate` remains visible as a drug result.

This should also reduce similar broad chemical fragment noise in other drug queries without removing ingredient-level concepts.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py::test_semantic_buckets_route_proteins_to_gene_bucket_not_drugs` passed.
- `node --check docs/search_quality/app.js` passed.

Live API verification is deferred to the next server restart to avoid adding more shell/session pressure in the current long-running workflow.
