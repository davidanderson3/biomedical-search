# Specialist Abbreviation Lexicon Expansion

## Change

Expanded `config/active_label_supplement.tsv` with additional context-gated specialist abbreviations that already resolve to local CUIs:

- `STEMI` -> `C1536220`
- `NSCLC` -> `C0007131`
- `CKD` -> `C1561643`
- `UTI` -> `C0042029`
- `MRI` -> `C0024485`
- `GDM` -> `C0085207`
- `SLE` -> `C0024141`
- `T1DM` -> `C0011854`
- `HHS` -> `C3888846`
- `BRBPR` -> `C0018932`
- `UGIB` -> `C0041909`

Each row has `context_any` terms so the abbreviation only fires in a relevant clinical neighborhood. `STEMI` also has `block_any` terms for `NSTEMI`, `non-st`, and `non st` to avoid adding the wrong myocardial infarction subtype.

## Improvement

This improves recall for common clinical shorthand in paragraphs and notes without making the label fallback broadly permissive. The highest-value cases are abbreviations that are common in real clinical writing but either absent as active labels or unsafe as bare short tokens: kidney disease (`CKD`), urinary infection (`UTI`), radiology procedures (`MRI`), rheumatology (`SLE`), oncology (`NSCLC`), GI bleeding (`BRBPR`, `UGIB`), and endocrine emergencies (`T1DM`, `HHS`, `GDM`).

The expected effect is better concept assignment for shorthand-heavy clinical text while preserving precision through local context requirements.

## Verification

Added a regression test covering:

- `STEMI with ST elevation myocardial infarction...` returns `C1536220`.
- `SLE with lupus nephritis...` returns `C0024141`.
- `Brain MRI showed acute infarct...` returns `C0024485`.
- `BRBPR with rectal bleeding...` returns `C0018932`.
- `non ST elevation myocardial infarction` does not incorrectly trigger `STEMI`.

Commands run:

```sh
python3 -m pytest tests/test_evidence_vectors.py -k 'active_label_supplement or specialist_abbreviations' -q
PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_service.py src/qe_evidence_vectors/search_rerank.py
```

Result: `6 passed, 170 deselected`.

## Remaining Limits

The expansion is still curated and intentionally conservative. More abbreviations should be added in batches only when the target CUI is verified locally and enough context/block terms are available to avoid ambiguous clinical meanings.
