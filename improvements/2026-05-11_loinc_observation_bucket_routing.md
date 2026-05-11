# LOINC Observation Bucket Routing

## Issue

LOINC concepts were present locally but did not show up reliably in `Observations & Lab Results`. Counts from the local indexes showed the data was available:

- `build/cui_code_index.sqlite`: `748,921` LNC code mappings across `244,017` distinct CUIs
- `build/umls_biomedicine_search_label_index.sqlite`: `434,522` LNC label rows across `177,445` distinct CUIs
- LNC CUIs with observation/lab semantic types: `116,557`
- LNC semantic-type distribution was dominated by `Clinical Attribute`, with far fewer `Laboratory Procedure` rows

## Root Cause

The UI had an `Observations & Lab Results` bucket, but the backend semantic group router did not have an observation group. It routed:

- `Clinical Attribute` into `PHYS`
- `Laboratory Procedure` into `PROC`
- `Laboratory or Test Result` into `PHYS`

The UI tried to rescue some of these by semantic type, but backend grouping and related-view categories still treated many LOINC-heavy concepts as physiology or procedures. Since LOINC is heavily typed as `Clinical Attribute`, that made observations underrepresented.

## Change

Added a first-class backend semantic group:

```text
OBS = Observations and Lab Results
```

Routed these semantic types to `OBS`:

- `Clinical Attribute`
- `Laboratory Procedure`
- `Laboratory or Test Result`

Updated both the config and frontend fallback bucket definitions so `Observations & Lab Results` matches `codes: ["OBS"]`.

## How It Improved Things

LOINC-heavy concepts now have a backend semantic group aligned with the displayed bucket. This should make lab and observation concepts easier to place, rank, display, and reason about consistently, instead of relying on UI-only remapping from `PROC` and `PHYS`.

## Validation

Focused tests passed:

```text
3 passed, 192 deselected
```

Also ran Python compile checks for the changed backend files and `node --check` for the frontend JS.

## Remaining Limitation

This fixes routing, not corpus coverage. Many LOINC concepts may still only exist in resolver/label indexes and not as vectorized concept documents with rich evidence. To increase recall further, the next step is to create a direct LOINC observation document/enrichment pass for common LOINC terms, components, panels, and clinical display names.
