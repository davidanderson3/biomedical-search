# Three Column Compact Card Headers

## Request

Use three columns within each result card for the concept name, semantic type, and `Details`, and make sure this applies to Drugs and Genes as well.

## Change

- Changed compact result cards to use a single `details` element whose summary is a three-column grid:
  - concept name
  - semantic type
  - `Details`
- Applied the same three-column summary to related suggestion cards, which are used to fill semantic buckets including Drugs and Genes.
- Preserved concept-link behavior inside the clickable details summary by stopping link/button click propagation.
- Added width constraints to related suggestion titles so long drug, gene, peptide, and protein labels truncate cleanly instead of forcing stacked layout.

## Why This Was Needed

Direct search hits already flow through `renderCompactResultCard()`, which is shared by all semantic buckets, including:

- `Drugs`
- `Genes, Amino Acids, Peptides, Proteins`

However, related semantic-bucket suggestions use a separate renderer, `renderCompactRelatedSuggestionCard()`. That path still displayed the concept label, semantic type, and `Details` one above the other. Drug and gene buckets can include those related suggestion cards, so the layout needed to be applied there too.

## Measured Effect

Before:

- Direct compact results could use the three-column header after the first layout change.
- Related suggestion cards still used stacked rows: label, semantic type, then `Details`.
- Drug/gene related suggestions could therefore still appear taller and less scannable than disease/finding cards.

After:

- Both compact card renderers now emit `summary.compact-result-summary`.
- `renderCompactResultCard()` covers all direct results in all semantic buckets, including Drugs and Genes.
- `renderCompactRelatedSuggestionCard()` now uses the same three-column summary for related drug/gene suggestions.

## Verification

- `node --check docs/search_quality/app.js` passed.
- Confirmed `Drugs` and `Genes, Amino Acids, Peptides, Proteins` are defined in `SEMANTIC_RESULT_BUCKETS`.
- Confirmed both compact render paths now contain `compact-result-summary`.
- Confirmed the running server is serving the updated JavaScript and CSS.

## Result

The compact results now use the requested name/type/details columns consistently for disease, drug, gene/protein, and related-suggestion cards. This is a UI layout improvement only; retrieval, ranking, and indexing are unchanged.
