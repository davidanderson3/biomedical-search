# Exact Mention Retention And Related-Rail Removal

Date: 2026-05-07

## Goal

Improve high-confidence recovery of concepts that are explicitly mentioned in clinical paragraphs but were falling below the useful result window. Also remove the extra `Additional Related Semantic Groups` rail from the web interface because the result columns already show related semantic buckets.

## Changes

- Removed the related semantic-group sidebar from `docs/search_quality/app.js`.
- Added active-label supplement rows for repeated exact-mention misses:
  - `C0030794` Pelvic pain
  - `C0042109` Urticaria
  - `C0043144` Wheezing
  - `C0079304` Endoscopy
  - `C0202110` Ketones
  - `C2098283` urine culture grew Escherichia coli
  - `C0521654` neurologic deficit
- Fixed active-label supplement merging so curated active labels still affect ranking when the same CUI is also found through the native UMLS label index.
- Changed the ranker so curated exact-label hits are treated as anchor-quality hits rather than ordinary zero-evidence fallbacks.
- Kept the earlier ranking improvements in place:
  - first-sentence single-token clinical conditions can receive primary-intent credit
  - later culture-grown organisms can be mildly demoted when a first-sentence infection diagnosis is the focus
  - generic `Infection` is demoted when more specific STI/infection anchors are present

## Targeted Measurement

Measured with the local hashing search stack and `top_k=20`.

| Paragraph | Target CUI | Before | After | Result |
|---|---|---:|---:|---|
| pyelonephritis / urine culture | `C2098283` | 13 | 1 | improved |
| upper GI bleed / endoscopy | `C0079304` | 20 | 3 | improved |
| anaphylaxis / urticaria | `C0042109` | not in top 20 | 4 | improved |
| anaphylaxis / wheezing | `C0043144` | 8 | 7 | slight improvement |
| PID / pelvic pain | `C0030794` | not in top 20 | 3 | improved |
| diabetic retinopathy / retinal examination | `C3640037` | not in top 20 | 6 | improved |
| celiac / gluten-free diet | `C0344351` | 1 | 1 | no change, already good |

## Verification

- `node --check docs/search_quality/app.js`
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_rerank.py src/qe_evidence_vectors/search_ranking.py`
- `PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_evidence_vectors.py -k "ranker or active_label_supplement"`
  - Result: 56 passed, 94 deselected

## Limitations

- This was a targeted spot-check, not a full 80-paragraph benchmark rerun.
- The top result did not always become the central diagnosis; this pass focused on retaining explicitly mentioned missing concepts in the useful window.
- The local browser server is still using the local hashing index, not the full SapBERT/Elasticsearch stack.
