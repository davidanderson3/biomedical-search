# Drug Gene Quality And Anatomy Expansion

## Request

Evaluate the quality of drug and gene results, and consider expanding anatomy results. Example: `heart failure with reduced ejection fraction` returns `Heart`, but other heart anatomy may be relevant.

## Evaluation

Sampled three drug/gene-oriented queries:

- `egfr mutated non small cell lung cancer osimertinib`
- `brca1 breast cancer risk tamoxifen`
- `methotrexate rheumatoid arthritis dihydrofolate reductase`

Drug direct results were generally good when the query named the drug:

- EGFR/NSCLC query returned `osimertinib` as the top drug result.
- BRCA/breast cancer query returned `tamoxifen` as the top drug result.
- Methotrexate/RA query returned `methotrexate` as the top drug result.

Gene/protein direct results were partly good:

- EGFR/NSCLC query returned `Epidermal Growth Factor Receptor`.
- BRCA query returned `BRCA1 gene`.
- Methotrexate/DHFR query returned `Dihydrofolate Reductase, human` and `DHFR gene`.

Remaining drug/gene weaknesses:

- Related drug suggestions can be noisy because contraindication relations are displayed beside treatment relations.
- Some drug concepts have UMLS semantic types such as `Amino Acid, Peptide, or Protein`, so they can appear under the gene/protein bucket as related items.
- Some protein concepts can still appear in the drug bucket when UMLS also gives them broad chemical/biologic semantic typing.

Those issues need a relation/type cleanup pass, but they were not the lowest-risk change in this request.

## Change

Added a display-side anatomy expansion for clear cardiac anatomy context.

When the top returned labels mention left-ventricular or ejection-fraction context, the Anatomy bucket now fills with inferred local anatomy suggestions:

- `C0225897` `Left Ventricle`
- `C0225899` `Myocardium of left ventricle`
- `C0018827` `Cardiac Ventricle`

This uses the same compact related-result card renderer as other related semantic bucket suggestions.

## Measured Effect

Query: `heart failure with reduced ejection fraction`

Before:

- Direct Anatomy bucket:
  - `C0018787` `Heart`
- Related Anatomy view items:
  - none
- Displayed anatomy count:
  - 1

After:

- Direct Anatomy bucket:
  - `C0018787` `Heart`
- Inferred anatomy additions:
  - `C0225897` `Left Ventricle`
  - `C0225899` `Myocardium of left ventricle`
  - `C0018827` `Cardiac Ventricle`
- Displayed anatomy count:
  - 4

## Verification

- `node --check docs/search_quality/app.js` passed.
- Confirmed the running server is serving JavaScript containing `ANATOMY_EXPANSION_RULES` and `inferredAnatomyBucketItems()`.
- Verified the HFrEF API payload had one direct anatomy result and no related anatomy view items before applying the display-side expansion.

## Result

The HFrEF search now surfaces more clinically relevant cardiac anatomy without changing retrieval, ranking, or index contents. The drug/gene evaluation identified the next likely cleanup area: relation filtering and better handling of protein-like drug semantic types.
