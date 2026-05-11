# Filter Drug Bucket Molecular and Dosage Noise

## Problem

On genomics-heavy drug queries such as `egfr mutated non small cell lung cancer osimertinib`, the Drugs bucket included non-therapy concepts:

- `Exons`
- `Enteric Coated Tablet Dosage Form`

These are not useful therapy/drug results beside actual treatments such as osimertinib, pemetrexed, paclitaxel, and osimertinib mesylate.

## Change

Added `nucleic acid, nucleoside, or nucleotide` to the Genes/Proteins semantic bucket and expanded molecular label markers to include exon/intron/codon/promoter terms. Added a dosage-form filter that suppresses `Biomedical or Dental Material` rows from Drugs when their label contains `dosage form`.

## Improvement

For `egfr mutated non small cell lung cancer osimertinib`:

- `Exons` moved from Drugs to `Genes, Amino Acids, Peptides, Proteins`.
- `Fusion Proteins, bcr-abl` remains in Genes/Proteins.
- `Enteric Coated Tablet Dosage Form` is no longer shown in Drugs.
- Actual therapies and drug classes remain in Drugs, including `osimertinib`, `osimertinib mesylate`, `pemetrexed`, `paclitaxel`, `vinorelbine`, `irinotecan`, `topotecan`, and `kinase inhibitor [EPC]`.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py::test_semantic_buckets_route_proteins_to_gene_bucket_not_drugs tests/test_evidence_vectors.py::test_semantic_buckets_route_lab_procedures_to_observations_not_procedures tests/test_evidence_vectors.py::test_semantic_buckets_hide_weak_ccpss_procedure_associations` passed.
- `node --check docs/search_quality/app.js` passed.
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_semantic_buckets.py` passed.
- `python3 -m json.tool config/search_quality_semantic_buckets.json` passed.
- Restarted the live server on `http://127.0.0.1:8766/` and confirmed the EGFR/osimertinib bucket behavior.
