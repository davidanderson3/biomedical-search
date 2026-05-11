# Semantic Group Scrollers

## Request

Give each semantic group card a scroller to see the full result set.

## Change

- Removed the five-card truncation from semantic group cards.
- Changed the related semantic bucket limit to `Number.POSITIVE_INFINITY`, so related items present in the API payload are no longer clipped by the old display limit.
- Added an internal vertical scroller to each semantic group item list:
  - `max-height: min(560px, 58vh)`
  - `overflow-y: auto`
  - stable scrollbar gutter

## Measured Effect

Before, each semantic group card showed at most 5 cards because `SEMANTIC_BUCKET_LIMIT = 5` and the final list used `.slice(0, SEMANTIC_BUCKET_LIMIT)`.

After, direct returned hits from the search payload are all rendered inside the group scroller.

Sample hidden direct hits that are now visible:

| Query | Semantic group | Direct hits now shown | Previously hidden after 5 |
|---|---:|---:|---:|
| `heart failure with reduced ejection fraction` | Diseases & Syndromes | 34 | 29 |
| `heart failure with reduced ejection fraction` | Findings & Symptoms | 17 | 12 |
| `heart failure with reduced ejection fraction` | Procedures | 6 | 1 |
| `egfr mutated non small cell lung cancer osimertinib` | Diseases & Syndromes | 41 | 36 |
| `brca1 breast cancer risk tamoxifen` | Procedures | 8 | 3 |
| `methotrexate rheumatoid arthritis dihydrofolate reductase` | Drugs | 7 | 2 |
| `methotrexate rheumatoid arthritis dihydrofolate reductase` | Genes, Amino Acids, Peptides, Proteins | 11 | 6 |

## Verification

- `node --check docs/search_quality/app.js` passed.
- Confirmed the running server is serving JavaScript with no five-card semantic bucket cap.
- Confirmed the running server is serving CSS with `.result-group-items` scrolling enabled.

## Result

Each semantic group card now stays compact on the page while allowing review of the full group-specific result list inside the card. Retrieval, ranking, and indexing are unchanged.
