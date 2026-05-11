# Yes/No Finding Filter

## Change

Added a conservative filter for answer-status findings whose primary label is `Yes` or `No`.

The rule:

- strongly penalizes `Yes` and `No` findings in normal clinical/research paragraph queries;
- filters them from result windows when they are high-penalty status noise;
- preserves direct lookup for `yes` and `no`.

## Why

`Yes` and `No` are generally not useful returned findings. They are answer/status values, not clinically meaningful concepts in most note or paragraph searches. They can crowd out better findings such as symptoms, diagnoses, lab results, or procedures.

## Measured Impact

Focused regression:

- `PYTHONPYCACHEPREFIX=.pycache_local PYTHONPATH=src python3 -m pytest tests/test_evidence_vectors.py -k 'yes_no_answer or confirmation_status or generic_status_noise' -q`
- Result: `3 passed`

Paragraph benchmark:

- Output: `build/improvements/2026-05-11_yes_no_finding_filter`
- Paragraph quality: `96/96 good`
- Expected concept recall at 10: `467/467`
- Expected concept recall at 20: `467/467`
- Recall at 5: `367/467`
- Mean search time: `1677.2 ms`
- Median search time: `1310.7 ms`

Net result: `Yes` and `No` findings are filtered from clinical-context searches without degrading the current paragraph recall benchmark or breaking direct `yes`/`no` lookup.

