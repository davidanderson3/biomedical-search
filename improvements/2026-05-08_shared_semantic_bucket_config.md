# Shared Semantic Bucket Config

## Change
- Added `config/search_quality_semantic_buckets.json` as the ordered source of truth for semantic result buckets.
- Updated `src/qe_evidence_vectors/search_semantic_buckets.py` so backend precomputed buckets load that JSON spec.
- Added `/search_quality_semantic_buckets.json` to the search quality server.
- Updated `docs/search_quality/app.js` so the browser loads the same bucket spec before rendering results, with the prior embedded list kept only as a fallback.
- Updated `docs/search_quality/README.html` to document the new route.

## Improvement
- Reduces drift risk between backend bucket precomputation and browser fallback rendering.
- Future bucket order, label, code, or semantic-type edits can be made in one config file instead of separately in Python and JavaScript.
- Keeps existing public browser URLs and search behavior intact.

## Verification
- `node --check docs/search_quality/app.js` passed.
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile ...` passed for the changed Python modules.
- `python3 -m json.tool config/search_quality_semantic_buckets.json` passed.
- Restarted `http://127.0.0.1:8766/`.
- Verified `/search_quality_semantic_buckets.json` returns `200`.
- Verified backend loaded the config order:
  `Diseases & Syndromes`, `Findings & Symptoms`, `Drugs`, `Procedures`, `Observations & Lab Results`, `Genes, Amino Acids, Peptides, Proteins`, `Devices`, `Organisms`, `People & Populations`, `Anatomy`.
- Smoke searches still returned precomputed semantic buckets with lazy details enabled.
