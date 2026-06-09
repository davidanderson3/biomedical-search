# Search Quality UI Assets

This directory contains static assets served by `scripts/search_quality_server.py`.

The browser-facing routes stay stable:

- `/search_quality_app.js` -> `docs/search_quality/app.js`
- `/search_quality_server.css` -> `docs/search_quality/server.css`
- `/search_quality_suggestions.json` -> `docs/search_quality/suggestions.json`
- `/search_quality_paragraphs.json` -> `docs/search_quality/paragraphs.json`
- `/search_quality_expansion_profiles.json` -> `docs/search_quality/expansion_profiles.json`
- `/search_quality_semantic_buckets.json` -> `config/search_quality_semantic_buckets.json`

`paragraphs.json` includes the generated full-page samples from `config/full_page_sample_queries.tsv`;
the UI's **Long sample** button filters for those long entries.
It also includes short PubMed excerpt samples from `config/pubmed_ui_sample_queries.tsv`.

Keep `docs/search_quality_server.html` at its current path unless the server default HTML path is updated at the same time.
