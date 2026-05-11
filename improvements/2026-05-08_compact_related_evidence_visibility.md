# Compact Related Evidence Visibility

## Request

Work on the next logical high-impact improvement and document exactly how it improved things.

## Change

- Added `renderRelatedEvidenceSections()` in `docs/search_quality/app.js`.
- Reused that single related-evidence renderer in both result-card paths.
- Added related evidence to the compact result card details, including:
  - research cross-type relations
  - external embedding neighbors from `cui2vec` and `BioConceptVec`
  - evidence-vector related concepts
  - MRREL graph support

## Why This Was Next

The app is now optimized around compact semantic-group cards, but those cards only showed metadata, score contribution, source mix, images, and review controls. The API was already returning related concepts, external embedding neighbors, research relations, and MRREL support, but most of that relationship evidence was hidden from the main UI path.

This was especially important after confirming that `cui2vec` and `BioConceptVec` are integrated as an external CUI-neighbor index rather than as the primary search vector space. If that provenance is not visible in the result details, users cannot tell when a concept is being supported by external embedding relationships.

## Measured Effect

Server status confirms external embedding integration:

- External CUI vector index: `build/external_cui_vector_neighbors.sqlite`
- External embedding sources: `BioConceptVec`, `cui2vec`
- External embedding source CUIs: 40,330
- External embedding links: 378,488

Sample query: `heart failure reduced ejection fraction`

- Top 10 returned results: 10
- Results with external embedding neighbors: 5
- Results with research cross-type relations: 5
- Results with MRREL related concepts: 9

Before this change, those related-evidence sections were not rendered in compact result details, so the compact UI exposed 0 of those relation sections. After this change, opening `Details` on compact cards exposes the same relation evidence that the older full-card renderer already had.

## Verification

- `node --check docs/search_quality/app.js` passed.
- `/api/status` is healthy and reports `BioConceptVec` plus `cui2vec` external embedding sources.
- Confirmed the running server is serving the updated JavaScript with `renderRelatedEvidenceSections()`.
- Ran the sample search above and counted relation-bearing top-10 results from the API response.

## Result

This does not change retrieval or ranking. It improves interpretability and debuggability by making already-returned relationship evidence visible in the compact interface, including the external embedding evidence that would otherwise look like it was not integrated.
