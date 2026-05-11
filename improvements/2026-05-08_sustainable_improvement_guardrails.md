# Sustainable Improvement Guardrails

## Change

Added executable guardrails for the curated active-label supplement:

- New validator module: `src/qe_evidence_vectors/active_label_supplement.py`.
- New CLI: `scripts/validate_active_label_supplement.py`.
- New tests requiring the actual `config/active_label_supplement.tsv` file to pass validation.
- New sustainability policy doc: `docs/search_quality_sustainable_improvements.md`.

The validator checks:

- Required TSV columns are present.
- CUIs look valid.
- Labels normalize to searchable text.
- `ispref` is `Y` or `N`.
- `semantic_type`, `field`, `sab`, `tty`, and `why` are present.
- `field` is one of the expected local categories.
- Non-preferred short labels and abbreviations have `context_any`, unless they are drug roll-up aliases.
- Duplicate CUI/label pairs and duplicate normalized context/block values are rejected.
- The same normalized label cannot silently map to multiple CUIs.

## Improvement

This makes recent gains more sustainable because the active-label supplement has become a key mechanism for exact clinical anchors, abbreviations, and drug aliases. Without validation, it would be easy to add an unsafe abbreviation or ambiguous short label that improves one example and hurts many others.

The validator immediately found and fixed one real cleanup issue: the `STEMI` row had both `non st` and `non-st` in `block_any`, which normalize to the same value.

## Verification

Commands run:

```sh
python3 scripts/validate_active_label_supplement.py
python3 -m pytest tests/test_evidence_vectors.py -k 'active_label_supplement or emergency_setting_concept or explicit_single_token_symptom_and_drug_anchors' -q
PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/active_label_supplement.py src/qe_evidence_vectors/search_ranking.py scripts/validate_active_label_supplement.py
```

Results:

- Active supplement validation passed.
- Unit tests: `10 passed, 173 deselected`.
- Python compile checks passed.

## Remaining Limits

This does not replace full search evaluation. It prevents a specific class of unsustainable curated-row changes. Broader sustainability still depends on periodic full paragraph benchmark runs, focused regression tests for every ranking rule, and documentation of measured improvement in `improvements/`.
