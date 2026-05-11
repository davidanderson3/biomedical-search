# Context-Gated Specialist Abbreviation Lexicon

## Problem

Specialist abbreviations can improve CUI assignment parity, but many are unsafe as unconditional label aliases. Examples include `RA` for rheumatoid arthritis versus right atrium or room air, and `MS` for multiple sclerosis versus mitral stenosis, morphine sulfate, or mass spectrometry.

## Change

Extended the active label supplement to support optional context gating columns:

- `specialty`
- `context_any`
- `block_any`

Rows with `context_any` only fire when at least one pipe-separated context phrase appears in the query. Rows with `block_any` are suppressed when a blocked context phrase appears. Existing supplement rows continue to work because these columns are optional.

Added initial high-value specialist abbreviation rows for:

- `HFrEF`
- `NSTEMI`
- `DKA`
- `RA`
- `MS`
- `PID`
- `VTE`
- `AFib`
- `a fib`
- `T2DM`
- `COPD`
- `TIA`

## Improvement

This adds a scalable path for specialist lexicons without hard-coding one-off ranking rules. It should improve short-form clinical language retrieval while reducing false positives from ambiguous abbreviations.

Example behavior added by test:

- `RA flare with synovitis treated with methotrexate` resolves `RA` to rheumatoid arthritis.
- `RA pressure was estimated from the right atrium tracing` does not resolve `RA` to rheumatoid arthritis.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py -k 'active_label_supplement or specialist_abbreviations' -q` passed: 5 passed.
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_service.py src/qe_evidence_vectors/search_rerank.py` passed.

## Operational Note

The search server loads `config/active_label_supplement.tsv` at startup, so restart the server before evaluating these new abbreviation rows in the web UI.
