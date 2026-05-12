# Biomedical Concept Search API

This project exposes a local HTTP API from `scripts/search_quality_server.py`.
The API powers the browser UI, but it is also intended for direct client use.

Start the server:

```sh
python3 scripts/search_quality_server.py --port 8766
```

Base URL:

```text
http://127.0.0.1:8766
```

Machine-readable contract:

```text
GET /api/openapi.json
```

## Stability

The documented top-level fields are the stable contract. New fields may be
added over time, so clients should ignore fields they do not recognize.

Error responses use a consistent envelope:

```json
{
  "error": {
    "code": "missing_parameter",
    "message": "missing q",
    "status": 400
  }
}
```

## Endpoints

### `GET /api/health`

Cheap liveness/readiness check.

Example:

```sh
curl -s "http://127.0.0.1:8766/api/health"
```

Response fields:

- `ok`: boolean readiness flag
- `api_version`: API contract version
- `records`: loaded search-record count
- `backend`: `local` or `elasticsearch`

### `GET /api/status`

Returns loaded artifact paths, record counts, backend, cache counters, and
relationship/index availability.

Example:

```sh
curl -s "http://127.0.0.1:8766/api/status"
```

### `GET /api/search`

Search free text for biomedical concepts.

Parameters:

- `q` required: free text, CUI, source code, phrase, sentence, or paragraph
- `k` optional: result limit, 1-100, default 10
- `mode` optional: `balanced`, `exact`, or `comprehensive`
- `include_related` optional: boolean, default true
- `semantic_bucket` optional: comma-separated custom semantic bucket keys

Aliases:

- `top_k` and `limit` are accepted aliases for `k`
- `related` is accepted as an alias for `include_related`
- `search_mode` is accepted as an alias for `mode`
- `bucket`, `buckets`, `semantic_group`, and `semantic_groups` are accepted as
  aliases for `semantic_bucket`

Example:

```sh
curl -s "http://127.0.0.1:8766/api/search?q=No%20evidence%20of%20pulmonary%20embolism&k=5&mode=balanced&include_related=false"
```

Important response fields:

- `query`: normalized request query
- `top_k`: requested result count
- `search_mode`: active search mode
- `backend`: active retrieval backend
- `scoring`: retrieval/ranking summary
- `hits`: ranked concept hits
- `semantic_result_buckets`: custom semantic group organization for hits

Important hit fields:

- `cui`: concept identifier
- `name`: display label
- `rank_score`: final ranking score
- `semantic_group` and `semantic_group_label`: custom group assignment
- `semantic_types`: source semantic types
- `matched_query_span`: exact span when available
- `assertion`: mention status, such as `current`, `negated`, `uncertain`,
  `historical`, `family_history`, `planned`, or `confirmed`
- `score_breakdown`: rank components and penalties
- `details_lazy`: true when expensive details are omitted from the search result

Fetch details for a hit with `/api/detail`.

### `GET /api/detail`

Fetch lazy details for a concept hit.

Parameters:

- `doc_id` optional if `cui` is present
- `cui` optional if `doc_id` is present
- `include_related` optional: boolean, default true

Example:

```sh
curl -s "http://127.0.0.1:8766/api/detail?cui=C0034065&include_related=true"
```

### `GET /api/resolve`

Resolve direct identifiers or labels before full search.

Parameters:

- `q` required
- `limit` optional, 1-100, default 10

Example:

```sh
curl -s "http://127.0.0.1:8766/api/resolve?q=C0034065"
```

### `GET /api/related`

Fetch related concepts, mappings, and relationship evidence for a CUI.

Parameters:

- `cui` required
- `k` optional, 1-100, default 10
- `vocab` optional, repeatable or comma-separated source vocabulary filter

Example:

```sh
curl -s "http://127.0.0.1:8766/api/related?cui=C0004238&k=10&vocab=ICD10CM"
```

### `GET /api/judgments`

Read local search-quality judgments.

### `POST /api/judgments`

Replace local search-quality judgments.

Request body:

```json
{
  "judgments": [
    {
      "query": "chest pain",
      "doc_id": "C0008031:example",
      "cui": "C0008031",
      "view": "example",
      "score": 1.23,
      "grade": "relevant",
      "labels": ["Chest Pain"]
    }
  ]
}
```

Valid `grade` values:

- `relevant`
- `partial`
- `wrong`
