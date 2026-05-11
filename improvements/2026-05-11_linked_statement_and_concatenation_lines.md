# Linked Statement And Concatenation Lines

## Change

Restored the linked statement display above the semantic result groups and added visual concatenation connectors between linked concepts that can be read as one combined expression.

UI behavior:

- statement-like queries show a compact `Linked Statement` panel above returned CUI groups;
- each recognized concept span in the original text links to its CUI in UTS;
- structured subject/predicate/object output is available in a collapsed details block instead of taking over the results area;
- non-statement text can still show `Linked Text` when adjacent concept spans have a likely concatenation bridge;
- likely concatenations get a green inline line/bridge between linked concept spans.

## Why

The previous full structured-statement area was too prominent and sometimes noisy, but the linked original sentence was useful because it shows exactly which text span mapped to which CUI. The restored version keeps that value while keeping the semantic result groups primary.

The connector line helps identify cases where adjacent returned concepts should be read together as a composite idea, such as a condition linked to a modifying clinical attribute, rather than as unrelated separate hits.

## Verification

Static checks:

- `node --check docs/search_quality/app.js`
- Confirmed linked statement rendering is wired into `renderResults()`.
- Confirmed concatenation connector styles exist in `docs/search_quality/server.css`.

This is a browser UI rendering change. It does not alter search ranking, vector retrieval, semantic buckets, or benchmark recall.

