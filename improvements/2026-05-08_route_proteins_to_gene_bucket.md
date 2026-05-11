# Route Proteins to Gene/Protein Bucket

## Problem

`BRCA1 breast cancer` showed BRCA1 and BRCA2 protein concepts under the Drugs bucket because UMLS places `Amino Acid, Peptide, or Protein` in a chemical-style semantic area. That made gene/protein results look like drug results and reduced trust in the semantic group cards.

## Change

Expanded the `Genes, Amino Acids, Peptides, Proteins` semantic bucket to include:

- `amino acid sequence`
- `amino acid, peptide, or protein`
- `gene or genome`
- `nucleotide sequence`

Updated backend and frontend bucket logic so semantic type matches and semantic group code matches are additive. Protein/gene items are explicitly prevented from occupying the Drugs bucket, while normal pharmacologic substances still remain in Drugs.

## Improvement

For `BRCA1 breast cancer`, the Drugs bucket previously contained:

- `BRCA2 Protein`
- `BRCA1 Protein`

After the change, the Drugs bucket no longer contains those protein rows. They now appear in `Genes, Amino Acids, Peptides, Proteins` alongside BRCA1 gene and other gene/protein relations.

Smoke checks showed normal drug searches still work:

- `sumatriptan`: Drugs bucket still has the ingredient result.
- `oliceridine`: Drugs bucket still has ingredient/brand/class results, while receptor/protein relations remain in the gene/protein bucket.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py::test_semantic_buckets_hide_weak_ccpss_procedure_associations tests/test_evidence_vectors.py::test_semantic_buckets_route_proteins_to_gene_bucket_not_drugs` passed.
- `node --check docs/search_quality/app.js` passed.
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_semantic_buckets.py` passed.
- `python3 -m json.tool config/search_quality_semantic_buckets.json` passed.
- Restarted the live server on `http://127.0.0.1:8766/` and confirmed the BRCA1 before/after behavior.
