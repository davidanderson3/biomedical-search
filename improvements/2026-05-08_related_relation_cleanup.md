# Related Relation Cleanup

## Request

Address remaining related-result weaknesses:

- contraindication relations can show beside treatment relations
- UMLS semantic typing can put some drugs/proteins in awkward buckets

## Change

- Added a display filter for top-level related semantic group cards.
- Suppressed contraindication relations from semantic group cards.
- Suppressed drug-like treatment/classification rows from the `Genes, Amino Acids, Peptides, Proteins` related-suggestion bucket when they are only there because UMLS typed the target as protein-like.
- Kept direct hits unchanged.
- Kept underlying API/ranker/index output unchanged.

The filtered rows are removed from the top-level semantic group cards only. The source data and detailed relation evidence are still available from result details/API payloads.

## Measured Effect

Measured on saved API payloads for four representative queries.

| Query | Bucket | Related before | Related after | Removed |
|---|---:|---:|---:|---:|
| `heart failure with reduced ejection fraction` | Drugs | 12 | 4 | 8 |
| `heart failure with reduced ejection fraction` | Genes/proteins | 12 | 7 | 5 |
| `brca1 breast cancer risk tamoxifen` | Drugs | 12 | 4 | 8 |
| `brca1 breast cancer risk tamoxifen` | Genes/proteins | 12 | 11 | 1 |
| `methotrexate rheumatoid arthritis dihydrofolate reductase` | Diseases & Syndromes | 9 | 3 | 6 |
| `methotrexate rheumatoid arthritis dihydrofolate reductase` | Drugs | 12 | 7 | 5 |
| `methotrexate rheumatoid arthritis dihydrofolate reductase` | Genes/proteins | 9 | 7 | 2 |

Across the sampled payloads:

- Related suggestions before filtering: 192
- Related suggestions after filtering: 157
- Contraindication rows removed from top-level cards: 29
- Drug-like rows removed from the gene/protein bucket: 8

Examples removed:

- `acebutolol`, `atenolol`, `verapamil`: `contraindicated_with_disease` rows under HFrEF drug suggestions
- `estetrol`, `medroxyprogesterone`, `norethindrone`: `contraindicated_with_disease` rows under breast-cancer drug suggestions
- `captopril`, `enalapril`, `lisinopril`: `may_be_treated_by` rows that appeared under gene/protein because of amino-acid/protein semantic typing
- `Blood coagulation disorder`, `HIV infection`, `kidney failure`: methotrexate contraindication rows removed from top-level disease suggestions

## Verification

- `node --check docs/search_quality/app.js` passed.
- Confirmed the running server is serving the updated JavaScript with `relationVisibleInSemanticBucket()`.

## Result

The top-level semantic group cards now emphasize direct hits and constructive related concepts instead of mixing treatment-looking suggestions with contraindications. The gene/protein related bucket is less likely to show drug ingredients or drug classes solely because UMLS assigns protein-like semantic types.
