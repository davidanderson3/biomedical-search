# Global Relevance Before Semantic Grouping

Implemented global relevance gating before semantic group display. Semantic group boxes now organize only results that already clear a rank-score threshold, and groups are ordered by the best result score in each group with the configured clinical order used only as a tie-breaker.

What improved:

- Main semantic boxes no longer try to fill every category; empty or low-relevance groups stay hidden.
- Low-rank results are filtered before grouping, so broad or weak hits are less likely to appear just because their group exists.
- Group order now follows the best globally ranked result, not the fixed semantic group order.
- Related concepts no longer enter the main semantic result boxes.
- Related concepts are exposed through a separate related bucket path and require explicit `related=1` plus stronger edge evidence.
- The web UI renders related concepts in a separate section when related results are enabled.

What did not improve yet:

- The relevance threshold is a conservative fixed threshold (`0.25`) rather than a learned per-query cutoff.
- Related evidence thresholds are also fixed (`strength >= 0.58`, `confidence >= 0.50`).
- This changes organization and filtering behavior, not the underlying vector retrieval or reranker scoring model.
