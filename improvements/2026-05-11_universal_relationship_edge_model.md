# Universal Relationship Edge Model

## Change

Implemented a reusable universal relationship edge model in `src/qe_evidence_vectors/universal_relationship.py` and attached it to relation rows from MRREL, research-relation indexes, metadata-mined relations, incoming/inverse relations, drug rollups, external CUI embeddings, and evidence-vector neighbors.

Each relation row now preserves the older fields (`relation`, `rela`, `source`, `direction`, etc.) and adds an additive `edge` object with:

- `subject`
- `object`
- `type`
- numeric `strength`
- `strength_metric`
- `directionality`
- `evidence.method`
- `evidence.provenance`
- structured `context`
- numeric `confidence`

## How It Improved Things

This makes relationships consistently machine-readable instead of source-specific display strings. Curated hierarchy rows, mined drug-indication rows, inverse relations, rollup relations, embedding neighbors, and evidence-vector neighbors can now be compared through the same contract. Rollup relations also carry structured context showing which adjacent drug concept supplied the relationship.

The search UI details panel now exposes the normalized edge fields as compact chips on related result cards, so users can see whether a relation is curated, literature-mined, embedding-derived, strong/weak, and directional without losing the compact card layout.

## Validation

Ran focused tests covering the new contract:

```text
8 passed, 187 deselected
```

Covered cases include metadata-mined Wikipedia drug indication, MRREL outgoing/incoming relations, research relation indexes, inverse search relations, drug rollup context, external embedding neighbors, and the universal edge builder itself.

## Remaining Limitations

Most current strengths are normalized scores derived from source/method/rank/support heuristics, not true effect sizes. The model now has a place for quantitative strength, but higher-value sources should later populate real odds ratios, probabilities, correlations, hazard ratios, or trial effect sizes when available.
