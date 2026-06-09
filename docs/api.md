# Biomedical Concept Search API

This project exposes a local HTTP API from `scripts/search_quality_server.py`.
The API powers the browser UI, but it is also intended for direct client use.

Start the server:

```sh
python3 scripts/search_quality_server.py --port 8766
```

For an unauthenticated/public deployment, start the server with public-output
filtering enabled:

```sh
python3 scripts/search_quality_server.py --port 8766 --public-output-only
```

In this mode, restricted source-vocabulary content can still be used internally
for retrieval and ranking, but API responses use only labels, definitions, and
MRREL relation rows from the configured public display source allowlist. Source
code mappings are not returned, and concepts without an allowed display label
are suppressed from public responses.

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
  - Source-code lookup accepts `SYSTEM:CODE`, bare codes, and common copied
    forms like `SNOMED CT US 49436004`, `SNOMEDCT_US 49436004`,
    `LOINC LA17084-7`, or `ICD 10 CM I48.91`.
  - Identifier lookup accepts `CUI:C0004238`, `AUI:A0000001`,
    `LUI:L0000001`, `SUI:S0000001`, `SCUI:...`, `SDUI:...`, `TUI:T047`,
    `ATUI:AT1`, and rebuilt relation indexes can resolve `RUI:...`.
    Source-specific `SYSTEM:CODE` lookup also checks CODE, SCUI, and SDUI.
- `k` optional: result limit, 1-100, default 10
- `mode` optional: `balanced`, `exact`, or `comprehensive`
- `scope` optional: `umls_evidence` default, or `umls` for UMLS-only
  CUI/code/label lookup without evidence vector retrieval or evidence snippets
- `include_related` optional: boolean, default true
- `include_linked_concepts` optional: boolean, default true. When enabled,
  the response includes span-level `mentions` as well as linked concept hits.
- `semantic_bucket` optional: comma-separated custom semantic bucket keys
- `codes` optional: source-asserted code systems to return: `default`, `none`,
  `all`, or comma-separated SABs such as `SNOMEDCT_US,RXNORM,ICD10CM,LNC`

When `--public-output-only` is enabled, source-code mapping fields are omitted
from responses even if `codes=all` or a specific source-code system is requested.

Aliases:

- `top_k` and `limit` are accepted aliases for `k`
- `related` is accepted as an alias for `include_related`
- `search_mode` is accepted as an alias for `mode`
- `search_scope` is accepted as an alias for `scope`
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
- `search_scope`: active source scope
- `backend`: active retrieval backend
- `scoring`: retrieval/ranking summary
- `hits`: ranked concept hits
- `mentions`: dictionary/entity-recognition spans found in the input text,
  including `start`, `end`, `text`, `cui`, `name`, `assertion`, `section`,
  `sentence_index`, and compact `codes` when available
- `mention_count`: count of returned span-level mentions
- `linked_concepts`: exact linked concept hits used by the browser UI
- `semantic_result_buckets`: custom semantic group organization for hits

Important hit fields:

- `cui`: concept identifier
- `name`: display label
- `rank_score`: final ranking score
- `semantic_group` and `semantic_group_label`: custom group assignment
- `semantic_types`: source semantic types
- `codes`: compact source-asserted code summaries for common vocabularies
  (`SNOMEDCT_US`, `RXNORM`, `ICD10CM`, and `LNC`/LOINC when available)
- `source_asserted_codes`: same compact code summaries with source-code metadata
  (`source_asserted_code`, `source_cui`/SCUI, and `source_dui`/SDUI)
- `matched_query_span`: exact span when available
- `assertion`: mention status, such as `current`, `negated`, `uncertain`,
  `historical`, `family_history`, `planned`, or `confirmed`
- `confidence`: result confidence metadata with `level` (`high`, `medium`,
  or `low`), numeric `score`, `abstain` flag, and short `reasons`
- `score_breakdown`: rank components and penalties
- `details_lazy`: true when expensive details are omitted from the search result

Fetch details for a hit with `/api/detail`.

### `GET /api/detail`

Fetch lazy details for a concept hit.

Parameters:

- `doc_id` optional if `cui` is present
- `cui` optional if `doc_id` is present
- `q` optional: current search query, used to put the most relevant evidence snippets first
- `include_related` optional: boolean, default true
- `scope` optional: same values as `/api/search`; `umls` suppresses evidence
  snippets and evidence-neighbor relations in the detail payload
- `codes` optional: source-asserted code systems to return, using the same
  values as `/api/search`

Detail responses also include `mappings`, a broader set of CUI-to-source-code
rows from the local code index.

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

Identifier examples:

```sh
curl -s "http://127.0.0.1:8766/api/resolve?q=SNOMED:49436004"
curl -s "http://127.0.0.1:8766/api/resolve?q=TUI:T047"
curl -s "http://127.0.0.1:8766/api/resolve?q=AUI:A0000001"
```

The current runtime can resolve only identifier classes present in its SQLite
indexes. Rebuild the code, definition, semantic-type, or relation indexes to
enable newly added AUI/LUI/SUI/ATUI/RUI columns.

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

## Quality Benchmark

Run a repeatable search-quality smoke or regression benchmark against a running
server:

```sh
scripts/run_search_regression_benchmark.py config/search_quality_clinical_queries.tsv \
  --base-url http://127.0.0.1:8766 \
  --top-k 10 \
  --rows-out build/search_regression_rows.csv \
  --json-out build/search_regression_summary.json
```

The runner accepts headered CSV/TSV files with a `query`/`q` column and optional
expected CUI columns such as `expected_cui`, `acceptable_cuis`, `target_cui`, or
`gold_cuis`. Headerless one-query-per-line files are also accepted. When expected
CUIs are present, the summary includes top-1, top-3, top-k, and MRR.

### Private Real-Query Diagnostic

Raw UMLS query exports stay out of public smoke tests. To inspect real query
behavior, run a private diagnostic against an Elasticsearch-backed local API and
the actual UMLS UTS API:

```sh
python3 scripts/run_private_real_query_diagnostic.py \
  --base-url http://127.0.0.1:8766 \
  --scope umls \
  --api-key "$UMLS_API_KEY"
```

The diagnostic requires `--api-key` or `UMLS_API_KEY`; it does not use fallback
environment variables and it does not provide a local-only mode.
If your local interactive zsh exports the key as `APIKEY`, pass it explicitly
with `zsh -ic 'python3 scripts/run_private_real_query_diagnostic.py ... --api-key "$APIKEY"'`.

Each run defaults to 50 queries. By default, those are the next unseen real
queries from the export files, ordered by demand. The rotation state lives in
`build/private_real_query_diagnostics/seen_query_ids.json`; use
`--reset-seen-state` only when you intentionally want to start the rotation over.

The diagnostic writes raw query text only under
`build/private_real_query_diagnostics/`. It measures local no-hit rate,
low-score rate, UMLS API no-hit rate, top-result agreement, and creates a
top-result review queue. Do not auto-promote rows. After human review, copy only
safe query/CUI pairs into `config/search_quality_real_query_regression.tsv`, then
run that reviewed file with:

```sh
python3 scripts/run_search_regression_benchmark.py \
  config/search_quality_real_query_regression.tsv \
  --base-url http://127.0.0.1:8766 \
  --scope umls \
  --top-k 10
```

## Display Name Overrides

Poor CUI display names can be fixed without rebuilding UMLS indexes:

```sh
python3 scripts/search_quality_server.py \
  --display-name-overrides config/display_name_overrides.tsv
```

The override file is TSV or CSV with `CUI` and `display_name` columns. Overrides
are applied after active/suppressed CUI checks and before source-preferred terms.
