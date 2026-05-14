# NCBI Bookshelf Open Access Fetcher

## Problem

The public corpus had MedlinePlus, MedlinePlus Genetics, DailyMed, and
ClinicalTrials.gov subsets, but it did not use the NLM Bookshelf open-access
bulk route for guideline/report/book-chapter text.

## Change

- Added `fetch-bookshelf-oa`, backed by the NLM LitArch Open Access FTP
  `file_list.csv` and package tarballs.
- Added `ncbi_bookshelf_oa` to `build-source-subset` and the public rebuild
  wrapper.
- Kept the default bounded by title/publisher terms, max book packages, max
  records, and per-record character caps.
- Preserved package license text, archive path, accession ID, publisher, update
  timestamp, and Bookshelf URL in each corpus document.

## Notes

Bookshelf web pages are not scraped. Automated retrieval uses the NLM LitArch
Open Access FTP path because NCBI identifies that as the allowed route for the
open-access subset.
