# Broad Bacteria Result Filter

## Change

Added a conservative ranking/filter rule for broad organism concepts such as `Bacteria`.

The rule applies when:

- the hit is typed as an organism, such as `Bacterium`;
- the primary label is broad, such as `Bacteria`, `Bacterium`, or `Bacterial organism`;
- the query has additional clinical context beyond asking for bacteria itself.

Direct broad-organism searches such as `bacteria` are preserved.

## Why

`Bacteria` is usually too broad for clinical/research paragraph search. In infectious disease searches, the useful results are usually the specific disorder, specimen/culture concept, antibiotic, or named organism. A generic `Bacteria` hit can consume limited result space without adding clinically actionable meaning.

## Measured Impact

Focused regression:

- `PYTHONPYCACHEPREFIX=.pycache_local PYTHONPATH=src python3 -m pytest tests/test_evidence_vectors.py -k 'broad_bacteria or resistant_organism' -q`
- Result: `2 passed`

Paragraph benchmark:

- Output: `build/improvements/2026-05-11_broad_bacteria_filter`
- Paragraph quality: `96/96 good`
- Expected concept recall at 10: `467/467`
- Expected concept recall at 20: `467/467`
- Recall at 5: `367/467`
- Mean search time: `1616.4 ms`
- Median search time: `1266.5 ms`

Net result: broad `Bacteria` is removed from specific infectious-context searches, while direct `bacteria` lookup still returns the broad concept. No measured recall loss on the current paragraph benchmark.

