# Documented API Contract

## Problem

The application had a useful HTTP API, but it was primarily documented by the browser UI and implementation code. External users could call `/api/search`, `/api/detail`, `/api/resolve`, `/api/related`, and `/api/judgments`, but there was no single API guide, no machine-readable contract, no cheap health endpoint, and error responses were plain `{"error":"..."}` objects.

That made the API usable for the UI but less robust for clients that need stable request parameters, response expectations, and predictable errors.

## Change

- Added `API_VERSION` and a machine-readable OpenAPI 3.1 contract exposed at `/api/openapi.json`.
- Added `/api/health` as a cheap readiness check with `ok`, `api_version`, `records`, and `backend`.
- Standardized API errors as:

```json
{
  "error": {
    "code": "missing_parameter",
    "message": "missing q",
    "status": 400
  }
}
```

- Updated the browser API helper to render structured error messages correctly.
- Added `docs/api.html` with endpoint parameters, aliases, important response fields, assertion metadata, error shape, and curl examples.
- Linked the API guide from `README.md` and `docs/technical_pipeline.html`.
- Exported the API contract helpers through `scripts/search_quality_server.py` for tests and external imports.

## Current Endpoints

- `GET /api/health`
- `GET /api/status`
- `GET /api/search`
- `GET /api/detail`
- `GET /api/resolve`
- `GET /api/related`
- `GET /api/judgments`
- `POST /api/judgments`
- `GET /api/openapi.json`

## Verification

```bash
python3 -B -m pytest tests/test_evidence_vectors.py -k "api_exports_documented_contract or parse_bounded_int_param" -q
PYTHONPYCACHEPREFIX=/private/tmp/query-expansion-pycache python3 -m py_compile src/qe_evidence_vectors/search_quality_http.py scripts/search_quality_server.py
```

Result: `1 passed, 239 deselected`.

## Remaining Work

The API is now documented and predictable, but it is still a local research API. The next hardening steps for hosted production would be authentication, request size limits, rate limiting, structured API-version negotiation, and generated JSON Schema components for every response object.
