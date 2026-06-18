# Molecular association UI opt-in

- Iteration: `SQI-2026-06-15-004`
- Backlog row: `SQB-006 Gene/protein default gating`
- Status: shipped
- Type: UI/process

## Problem

The backend/API already defaulted relation-derived gene and protein associations off unless `molecular_associations=true`, but the public search UI did not expose that mode. Users could not intentionally explore molecular associations or see whether the current search was running in default clinical mode.

## Change

Added a default-off `Explore genes/proteins` checkbox in Search settings. The UI now sends `molecular_associations=0/1` for both single-search and query-set runs, records `molecular_associations_enabled` from the API response, reports the active mode in System Metrics, and renders opted-in relation-derived molecular candidates in a separate Molecular Associations panel.

## Verification

Static regression coverage checks that the checkbox exists, defaults off, the JavaScript sends the molecular association query parameter, client state consumes API metadata, and the metrics/panel labels are present.

- `node --check docs/search_quality/app.js`
- HTML parser checks for `docs/search_quality_server.html`, `docs/search_quality_progress_log.html`, and `docs/search_quality_iterations.html`
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile tests/test_public_search_docker.py`
- `PYTHONPATH=src:scripts python3 -m pytest tests/test_public_search_docker.py -k molecular -q` passed with 1 test and 6 deselected
- `PYTHONPATH=src:scripts PYTHONPYCACHEPREFIX=.pycache_local python3 -m pytest -q` passed with 504 tests and 1 skipped

## Remaining Work

Add live negative and positive examples: default cardiology, infection, and medication searches should not surface unrelated genes, while explicit EGFR, BRCA1, and CYP2C19 searches should still work.
