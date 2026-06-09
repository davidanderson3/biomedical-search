# HPO And MONDO Ontology Relationship Coverage

Date: 2026-05-13

## Summary

Added structured OBO ingestion for HPO and MONDO, refreshed the source
contribution report, and made the public rebuild pass staged HPO annotation
files into the research-relation index when they are available.

## Details

- Added `fetch-obo-ontology` for `hpo` and `mondo`.
- Preserved term labels, definitions, synonyms, xrefs, parent IDs, relationship
  text, source license, source URL, and ontology version metadata.
- Built the HPO source subset into `build/public/source_subsets/hpo`.
- Built the MONDO source subset into `build/public/source_subsets/mondo` and
  upserted its concept documents/vectors into the permitted-source aggregate.
- Confirmed the local research-relation index already contains HPO-derived
  `has_phenotype`, `gene_has_phenotype`, `gene_associated_with_disease`, and
  `disease_has_associated_gene` rows.
- Updated `run_public_rebuild.py` so clean rebuilds can include staged HPO
  annotation-derived research relations with `--include-hpo-research-relations`
  after reviewing HPO/OMIM/Orphanet reuse terms. Orphanet should be handled
  through UMLS/source-code crosswalks rather than fetched as a duplicate source.

## Remaining Gap

HPO and MONDO native xrefs and hierarchy are now preserved in corpus metadata
and text, but not yet exposed as a first-class xref/hierarchy edge index.
