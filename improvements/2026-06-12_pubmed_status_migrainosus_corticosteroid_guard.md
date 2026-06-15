# PubMed status-migrainosus corticosteroid-class guard

## What changed

The approved PubMed status-migrainosus abstract no longer ranks the broad corticosteroid class first.

- Added a scoped `broad_corticosteroid_class_penalty` score component.
- The penalty applies only to broad steroid/corticosteroid class matches in long treatment-review queries with multiple non-class anchors.
- Direct short corticosteroid searches are not penalized.
- The target row now ranks `C0003211` Anti-Inflammatory Agents, Non-Steroidal first instead of `C0001617` Adrenal Cortex Hormones.

## Measured effect

Approved PubMed suite:

- Before: 9/13 rows complete at top 10, 10/13 at top 20, 53/60 expected concepts at top 10, 57/60 at top 20, 12/13 top-on-target, 1 wrong-first row, overall score 76.7.
- After: 9/13 rows complete at top 10, 11/13 at top 20, 53/60 expected concepts at top 10, 57/60 at top 20, 13/13 top-on-target, 0 wrong-first rows, overall score 77.9.

Run artifact:

- `build/search_quality_experiments/runs/SQI-2026-06-12-005_pubmed_corticosteroid_guard_sqi-2026-06-12-005-approved-pubmed-corticosteroid-guard`

## Verification

- `python3 -m py_compile src/qe_evidence_vectors/search_ranking.py tests/test_evidence_vectors.py`
- `PYTHONPATH=src:scripts python3 -m pytest tests/test_evidence_vectors.py -k "corticosteroid or status_migrainosus or long_document_supported_secondary_concept or condition_variants_from_crowded_drug_tail or pharmacologic" -q`
- `PYTHONPATH=src:scripts python3 scripts/run_search_quality_experiment.py --label "SQI-2026-06-12-005 approved PubMed corticosteroid guard" --run-id SQI-2026-06-12-005_pubmed_corticosteroid_guard --run-family custom --queries build/pubmed_literature_benchmark_seed/pubmed_literature_approved_queries.tsv --query-limit 0 --base-url http://127.0.0.1:8767 --require-api-backend elasticsearch --scope umls_evidence --search-system api --top-k 60 --timeout 180 --workers 1 --output-root build/search_quality_experiments --html-report docs/search_quality_experiments.html`
- `PYTHONPATH=src:scripts python3 scripts/run_search_quality_experiment.py --iteration-smoke-gates --iteration-id SQI-2026-06-12-005 --iteration-type ranking --iteration-type long-document --static-command "python3 -m py_compile src/qe_evidence_vectors/search_ranking.py tests/test_evidence_vectors.py" --focused-command "PYTHONPATH=src:scripts python3 -m pytest tests/test_evidence_vectors.py -k 'corticosteroid or status_migrainosus or long_document_supported_secondary_concept or condition_variants_from_crowded_drug_tail or pharmacologic' -q" --base-url http://127.0.0.1:8767 --skip-rotating-smoke --skip-patient-portal-smoke`

## Remaining work

`SQB-002` still has recall work: C. difficile infection, EGFR/PFS/platinum/regimen concepts, and hypocomplementemia/Complement 3. The wrong-first phase is closed.
