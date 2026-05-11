# Filter Broad CCPSS Gene and Drug Relations

## Problem

After routing proteins into the gene/protein bucket, `acute pancreatitis` still showed `Hemoglobin SS` as a related gene/protein item. The row came from a broad CCPSS `inverse clinically associated with` relation, which is too weak for default semantic cards when the related label has no meaningful overlap with the source concept.

## Change

Expanded the broad CCPSS clinical-association filter from Procedures to Drugs and Genes/Proteins as well. The filter now handles both normalized and inverse display forms:

- `clinically_associated_with`
- `clinically associated with`
- `inverse clinically associated with`
- `inverse_clinically_associated_with`

Rows from those broad CCPSS relations remain visible only when the related label overlaps the source concept.

## Improvement

For `acute pancreatitis`, the `Genes, Amino Acids, Peptides, Proteins` bucket changed from 4 items to 3:

- Removed: `Hemoglobin SS` from CCPSS `inverse clinically associated with`
- Kept: `LPL gene`, `SPINK1 gene`, `SPINK1 wt Allele`

This improves precision in the gene/protein bucket without removing higher-confidence HPO/NCI gene-disease relations.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py::test_semantic_buckets_hide_weak_ccpss_procedure_associations tests/test_evidence_vectors.py::test_semantic_buckets_route_proteins_to_gene_bucket_not_drugs` passed.
- `node --check docs/search_quality/app.js` passed.
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_semantic_buckets.py` passed.
- Restarted the live server on `http://127.0.0.1:8766/` and confirmed `acute pancreatitis` no longer returns `Hemoglobin SS` in semantic result buckets.
