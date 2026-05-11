# Split AAPP Drugs from Gene/Protein Concepts

## Problem

The previous gene/protein bucket improvement treated all `Amino Acid, Peptide, or Protein` concepts as gene/protein results. That fixed BRCA1/BRCA2 protein leakage into Drugs, but it also moved clinically drug-like concepts such as `vancomycin`, `osimertinib`, and `Streptogramins` away from the Drugs bucket.

## Change

Refined bucket routing for `Amino Acid, Peptide, or Protein` concepts. The system now treats this semantic type as ambiguous:

- Gene/protein when the label contains markers such as `protein`, `proteins`, `gene`, `receptor`, `hemoglobin`, `enzyme`, `kinase`, `factor`, or similar molecular terms.
- Drug/chemical when it lacks those markers and otherwise belongs to the chemical/drug semantic group or relation category.

This keeps true gene/protein concepts in `Genes, Amino Acids, Peptides, Proteins` while preserving peptide/protein-typed drugs in `Drugs`.

## Improvement

For `diabetic foot osteomyelitis vancomycin bone biopsy`:

- `vancomycin` now appears in the Drugs bucket.
- `Streptogramins` remains in Drugs.
- Gene/protein relations still include true gene/protein items such as `ATL1 gene`, `ITGB2 gene`, and `Cephalosporinase`.

For `egfr mutated non small cell lung cancer osimertinib`:

- `osimertinib` now appears in Drugs.
- `osimertinib mesylate` remains in Drugs.
- `Epidermal Growth Factor Receptor`, `Soluble ErbB-1`, and `Fusion Proteins, bcr-abl` appear in Genes/Proteins instead of Drugs.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py::test_semantic_buckets_route_proteins_to_gene_bucket_not_drugs tests/test_evidence_vectors.py::test_semantic_buckets_route_lab_procedures_to_observations_not_procedures tests/test_evidence_vectors.py::test_semantic_buckets_hide_weak_ccpss_procedure_associations` passed.
- `node --check docs/search_quality/app.js` passed.
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_semantic_buckets.py` passed.
- Restarted the live server on `http://127.0.0.1:8766/` and confirmed the diabetic foot osteomyelitis/vancomycin and EGFR/osimertinib bucket behavior.
