# Result Details Compaction

## Request

In results, show only name and semantic type. Put the rest in details.

## Change

- Updated returned concept cards so the closed view shows only the concept name and one semantic type label.
- Updated related-suggestion cards the same way: visible label plus semantic type only.
- Moved rank, CUI, score, evidence count, match type, source mix, labels, source vocabularies, signal summaries, images, relations, definitions, mappings, evidence, and review controls into the card's `Details` disclosure.
- Removed the visible compact thumbnail slot and compact stat chips from result cards.

## Measured Effect

- Before: each closed compact result card exposed name, CUI, semantic type, rank, score, evidence count, match type, and up to three signal chips; image thumbnails could also appear.
- After: each closed result card exposes only two concept data fields: name and semantic type.
- The remaining metadata is still available without rerunning search by opening `Details`.

## Verification

- `node --check docs/search_quality/app.js` passed.
- Confirmed the served JavaScript contains `result-visible`, `result-semantic-type`, and `Result Metadata`.
- Confirmed the served CSS contains the new result compaction selectors and no longer contains the removed compact stat or thumbnail selectors.
- Confirmed `/api/status` is healthy on the running server.

## Result

This improves result scanning density and reduces visual noise. It does not change retrieval, ranking, indexing, semantic bucketing, or evaluation metrics.
