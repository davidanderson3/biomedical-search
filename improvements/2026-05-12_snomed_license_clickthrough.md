# SNOMED License Clickthrough

## Change

Added a SNOMED CT license acknowledgement dialog to the search UI. The dialog appears before first use and blocks search/query-set execution until the user checks the acknowledgement box and clicks Continue.

The acknowledgement is stored in browser `localStorage` under `qe_snomed_license_ack_v1`, so it shows only once per browser user unless the key is cleared or the acknowledgement version is intentionally changed. If browser storage is unavailable, the acknowledgement still works for the current page session.

## Result

Verification passed:

- `node --check docs/search_quality/app.js`
- Served page at `http://127.0.0.1:8766/` contains `snomedLicenseDialog`.
- Served JS contains the SNOMED acknowledgement key and search/query-set gate.
- Served CSS contains the dialog and modal styles.

## Impact

This adds a visible license gate for deployments that include SNOMED CT-derived content without changing search ranking, indexing, or result quality. The main limitation is that this is a UI/browser acknowledgement, not a server-side identity system.
