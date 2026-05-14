# Irrelevant Concept Results Strategy

## Current Baseline

Live Elasticsearch-backed paragraph audit, refreshed May 14, 2026:

- Paragraph queries: 161
- Top-10 result slots reviewed: 1,610
- Non-expected top-10 hits: 746
- Useful-extra top-10 hits: 43
- Suspect review targets: 70
- Suspect review targets per paragraph: 0.43

The important point is that `non-expected` does not mean `irrelevant`. The current root-cause buckets are:

| Bucket | Count | Meaning |
| --- | ---: | --- |
| `expected_set_gap_or_valid_secondary` | 38 | A result is textually/clinically plausible but not currently listed as expected/useful. |
| `literal_auxiliary_concept` | 15 | A directly mentioned drug, test, imaging method, or procedure appears high, even when the paragraph's main concept is a condition. |
| `low_specificity_semantic_type` | 10 | Broad attributes/classes such as clinical attributes or uncategorized concepts still surface. |
| `unanchored_vector_drift` | 6 | Vector similarity retrieves a concept without enough local lexical or relation evidence. |
| `penalty_not_strong_enough` | 1 | A result is recognized as context/specificity-mismatched but only demoted, not removed. |

## Definition Of The Problem

The search app should find the right concept for the user's search, not every concept that is statistically nearby. A result should be considered relevant only if it satisfies at least one of these conditions:

- It is directly anchored in the query text by a meaningful label, synonym, code, or abbreviation.
- It is a clinically useful normalization of a direct query mention.
- It is a close, query-supported parent/child/sibling that helps identify the intended concept.
- It is intentionally allowed for the current search mode, such as a drug/procedure view or an all-mentioned-concepts view.

A result should be treated as irrelevant if it is only connected by generic prose, broad semantic relatedness, weak vector similarity, or an ontology/relation edge that is not supported by the query text.

## Strategy

1. Separate expected-set gaps from false positives.

   Many current flagged rows are real paragraph concepts: for example directly mentioned imaging, drugs, symptoms, organisms, and procedures. These should be judged as either `expected`, `useful_extra`, or `not relevant for this search mode`. Do not add filters until a result is actually judged irrelevant.

2. Add judgment-driven feedback before more filters.

   Each reviewed top result should store: query id, CUI, rank, judgment, root cause, and desired action. Recommended judgment labels:

   - `expected`: central concept the benchmark should require.
   - `useful_extra`: valid but not required.
   - `mode_mismatch`: valid mention, wrong for the current view.
   - `generic_or_low_specificity`: too broad to show.
   - `unanchored_vector_drift`: no local query support.
   - `context_mismatch`: wrong sense, population, negation, or scope.

3. Make anchor strength a first-class cutoff.

   A result should not be visible high in default search unless it has one of:

   - Exact or near-exact label/span match on content tokens.
   - Accepted abbreviation/code match.
   - Definition/evidence overlap on rare query tokens.
   - Relation support plus lexical overlap.

   Vector-only hits should need a higher score and stronger rare-token overlap than label-anchored hits.

4. Treat component-only concepts as scoring evidence, not standalone answers.

   Concepts such as colors, counts, scalar values, levels, quantities, ratios, percentages, and qualitative/quantitative attributes are often useful only inside a larger concept. For example, `white` and `count` help identify `white blood cell count`, but `White color` or `Count of entities` should not be independent answers to that query.

   General rule:

   - Keep a component concept if the user searches for it directly.
   - Suppress it if a more specific result covers the same query tokens plus additional biomedical context.
   - Let it contribute to composite scoring, but do not let it occupy a visible result slot by itself.

5. Use search modes instead of one universal ranking.

   The current default mixes conditions, drugs, tests, procedures, organisms, attributes, and documents. That makes literal auxiliary concepts look like false positives in condition-focused paragraphs. Add or formalize modes:

   - `all`: all useful concepts mentioned in the text.
   - `problems`: diseases, findings, symptoms, pathologic functions.
   - `treatments`: drugs and therapeutic procedures.
   - `diagnostics`: labs, imaging, tests, procedures.
   - `identifiers`: exact code/string/concept lookup.

   The default should probably be `all` for UMLS concept lookup, but the paragraph quality benchmark should evaluate each mode separately.

6. Convert repeated low-specificity patterns into general rules.

   Prefer reusable rules over one-off CUI blocks:

   - Low-specificity semantic types need exact query support.
   - Broad category concepts should not outrank more specific mentioned concepts.
   - Penalized results that recur as false positives should be removed after penalty, not only demoted.
   - Ontology/relation edges should support ranking, not create visible results without query anchors.

7. Keep source contribution separate from search relevance.

   A source can be useful for recall but harmful for precision if its labels are broad or relation-heavy. Source weighting should be based on judged search outcomes, not source size. Track false-positive rate by source bundle, semantic type, and retrieval kind.

## Immediate Next Steps

1. Review the 70 current suspect rows in `build/search_quality_live_audit/paragraph_precision_audit.tsv`.
2. Promote true expected-set gaps to `expected_cuis` or `search_quality_useful_extra_cuis.tsv`.
3. For the remaining real false positives, implement rules in this order:
   - component-only broad concept suppression,
   - low-specificity semantic type gating,
   - unanchored vector drift cutoff,
   - context mismatch cutoffs,
   - source/type weighting.
4. Re-run the paragraph audit after each change and require:
   - zero missing expected concepts,
   - zero configured disallowed concepts,
   - decreasing `unanchored_vector_drift` and `low_specificity_semantic_type` counts.

## Tooling Added

`scripts/audit_paragraph_precision.py` now emits:

- `root_cause`
- `recommended_action`
- `root_cause_counts`

This gives each flagged result a next action instead of treating every non-expected result as an irrelevant concept.
