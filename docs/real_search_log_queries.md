# Real Search Log Queries

The raw UMLS search log query exports live in:

```text
data/local_search_logs/umls_query_exports/
```

They were moved out of the repository root because they are local source inputs,
not public project fixtures. `data/` is gitignored, which is the right default
for raw log-derived data.

## Shape

Each CSV has:

- `search_term`
- `unique_users`

Current aggregate inventory, counted on 2026-06-05:

| File | Rows | Sum of per-term `unique_users` | Max `unique_users` |
| --- | ---: | ---: | ---: |
| `one-word-real-queries.csv` | 10,000 | 68,287 | 60 |
| `two-word-real-queries.csv` | 10,000 | 48,003 | 47 |
| `three-word-real-queries.csv` | 10,000 | 32,593 | 36 |
| `four-word-real-queries.csv` | 10,000 | 18,115 | 38 |
| `five-word-real-queries.csv` | 10,000 | 12,358 | 11 |
| `six-word-real-queries.csv` | 10,000 | 10,755 | 12 |
| `seven-word-real-queries.csv` | 10,000 | 10,261 | 8 |
| `eight-word-real-queries.csv` | 10,000 | 10,088 | 4 |
| `nine-word-real-queries.csv` | 6,887 | 6,915 | 3 |
| `ten-word-real-queries.csv` | 4,720 | 4,734 | 3 |
| `eleven-word-real-queries.csv` | 3,199 | 3,197 | 2 |
| `12-13-word-real-queries.csv` | 3,532 | 3,529 | 2 |
| `14-or-more-word-real-queries.csv` | 3,384 | 3,383 | 1 |
| Total | 101,722 | 232,218 | 60 |

The row count is unique within these bucket files. The `unique_users` values are
per term and should not be interpreted as a globally deduplicated user count.

## Handling Rules

Treat these exports as restricted local log data.

- Keep raw CSVs under `data/` or another ignored local path.
- Do not publish raw terms in docs, release candidates, examples, or public
  benchmark files.
- Before deriving artifacts, flag and review possible identifiers. The
  inventory found 3 email-like rows, 5 phone-like rows, 83 long digit runs, and
  797 rows with non-ASCII characters.
- Checked-in outputs should be aggregate-only or manually curated and
  de-identified.

## Useful Workflows

These files are most useful as a private query-demand signal, not as direct
training data.

1. Build a local query inventory with term length, `unique_users`, normalization
   features, and privacy flags.
2. Run sampled or high-frequency terms against the current search server and
   collect no-hit, low-confidence, and wrong-intent cases.
3. Manually map reviewed failure cases to expected CUIs, then add only safe rows
   to a private benchmark or a curated public benchmark.
4. Use reviewed `query -> CUI` mappings as `query_language` evidence through
   the existing `ingest-query-log` command. The current command expects TSV rows
   with `query` and `cui`; these raw CSVs do not include CUIs.
5. Mine durable lexical issues: abbreviations, misspellings, punctuation,
   Greek-letter variants, pluralization, pasted article titles, and numeric
   procedure or code-like searches.
6. Feed recurring, reviewed fixes into the existing improvement hierarchy:
   source coverage first, semantic bucket/profile changes second, active-label
   supplement rows third, and ranker rules only for reusable error classes.
7. Use aggregate demand to prioritize public evidence acquisition topics, while
   keeping trial/literature/query-language evidence clearly separated.

## Suggested Next Step

Create a local generated inventory under `build/local_search_logs/`, then use it
to drive focused review. The cheap, no-server path is:

```sh
python3 scripts/build_real_query_inventory.py
```

This writes:

- `build/local_search_logs/query_inventory.tsv`
- `build/local_search_logs/query_inventory_summary.json`

The inventory columns are:

```text
source_file	source_row	token_bucket	search_term	unique_users	normalized_term	normalized_token_count	privacy_flags	server_hit_count	server_top_cui	server_top_label	server_score	server_error	review_status	reviewed_cui	review_note
```

For a prioritized local queue without calling the search server, use demand order:

```sh
python3 scripts/build_real_query_inventory.py \
  --sort demand \
  --max-rows 5000 \
  --out build/local_search_logs/query_inventory_demand_top5000.tsv \
  --summary-out build/local_search_logs/query_inventory_demand_top5000_summary.json \
  --review-queue-out build/local_search_logs/query_review_queue.tsv
```

When the search server is running, score a bounded batch and fill the `server_*`
columns:

```sh
python3 scripts/build_real_query_inventory.py \
  --sort demand \
  --max-rows 1000 \
  --score-api \
  --out build/local_search_logs/query_inventory_scored_top1000.tsv \
  --summary-out build/local_search_logs/query_inventory_scored_top1000_summary.json \
  --review-queue-out build/local_search_logs/query_review_queue.tsv
```

`--score-api` requires either `--max-rows` or `--score-all` so a command does
not accidentally issue the full 101k-query batch. The review queue adds
`review_priority` and `review_reasons` ahead of the inventory columns. Reasons
include privacy flags, no server hit, server errors, low top score, high demand,
code-like terms, punctuation variants, and long pasted queries.

That keeps the raw export private, makes failure review repeatable, and produces
the right shape for later curated benchmark rows or reviewed query-log evidence.
