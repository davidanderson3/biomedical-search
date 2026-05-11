# Cervical Sense Disambiguation

## Change

Added a targeted ranking rule for the ambiguous adjective `cervical`.

The ranker now detects whether the query context is gynecologic/cervix-related or spine/neck-related:

- Gynecology context: `pelvic`, `motion`, `tenderness`, `cervix`, `uterine`, `vaginal`, `HPV`, `Pap`, `dysplasia`, `PID`, etc.
- Spine/neck context: `spine`, `spinal`, `neck`, `vertebra`, `stenosis`, `radiculopathy`, `myelopathy`, `MRI`, etc.

When the query clearly uses one sense, labels from the opposite sense receive a clinical context sense penalty. The anchor-fill step now also deprioritizes strongly sense-mismatched hits so they do not come back merely because they share the word `cervical`.

## Improvement

This improves precision for an important source of ambiguity:

- `cervical motion tenderness with pelvic inflammatory disease` should favor gynecology concepts and not surface cervical spine/neck anatomy ahead of them.
- `cervical spine stenosis with neck pain` should favor spine concepts and not surface cervical cancer merely because it shares the word `cervical`.

This is a narrow improvement, but it addresses a common problem in CUI assignment: one surface form maps to clinically different semantic neighborhoods.

## Verification

Added regression tests for both directions:

- Gynecology context demotes `Cervical spine`.
- Spine context demotes `Cervical cancer`.

Commands run:

```sh
python3 -m pytest tests/test_evidence_vectors.py -k 'cervical or mortality_outcome or confirmation_status or generic_prose_status' -q
PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py
```

Result: `5 passed, 173 deselected`.

## Remaining Limits

This is still rule-based. The scalable version should be a learned or table-driven sense inventory for high-frequency ambiguous modifiers and abbreviations, using local semantic neighborhoods and evaluation failures to propose new sense gates.
