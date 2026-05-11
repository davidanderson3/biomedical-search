# Demote metadata/status noise in clinical-result ranking

## Problem

Paragraph evaluations showed several non-clinical metadata/status concepts appearing in the first result page because they match ordinary prose words:

- `DeviceAlertLevel - Critical` can match `critical coronary stenosis`.
- `Wake After Sleep Onset` can match ordinary `after`/`onset` wording in non-sleep contexts.
- `To be developed` and `Newly Diagnosed` can match narrative status words while real disease concepts are present.

These are usually not useful returned concepts for clinical note search unless the user is directly asking about device alerts, sleep metrics, or status/documentation metadata.

## Change

Added narrow clinical-context penalties for:

- device-alert metadata labels unless the query asks for device alert metadata;
- sleep metric labels unless the query is actually about sleep/wake concepts;
- status prose labels such as `developed`, `new onset`, and `newly diagnosed` when stronger biomedical anchors are present.

## Result

Focused tests now verify that:

- `Non-ST Elevated Myocardial Infarction` and `Coronary Stenosis` outrank `DeviceAlertLevel - Critical` and `Wake After Sleep Onset` for a cardiac paragraph.
- `Multiple Sclerosis` and `Optic Neuritis` outrank `To be developed` and `Newly Diagnosed` for a neurologic paragraph.
- Direct metadata queries such as `critical device alert level`, `wake after sleep onset`, and `newly diagnosed` are not penalized.

## Verification

Ran:

```sh
PYTHONPYCACHEPREFIX=.pycache_local PYTHONPATH=src python3 -m pytest tests/test_evidence_vectors.py -k 'device_alert or new_diagnosis' -q
PYTHONPYCACHEPREFIX=.pycache_local PYTHONPATH=src python3 -m py_compile src/qe_evidence_vectors/search_ranking.py tests/test_evidence_vectors.py
```

Live API verification was deferred because the environment is already at the open process limit; the backend change will apply after the search server is restarted.
