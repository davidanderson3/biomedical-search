# PubMed Curated Lab and Condition Recall

## Problem

The focused PubMed long-document lane still had one expected top-10 miss:
`C0009506` Complement 3 in the lupus/preeclampsia abstract. The paragraph
explicitly says `normal C3 and C4 complement levels`, but the C3 concept was
treated as a gene/protein-style immunologic factor rather than a lab analyte in
semantic-context ranking.

Baseline run:

- Query file: `build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_queries.tsv`
- Output directory: `build/search_quality_experiments/runs/SQI-2026-06-11-007_pubmed_migraine_with_or_without_aura_final_8766_sqi-2026-06-11-007-pubmed-migraine-aggregate-final-8766`
- Result: 35/36 expected concepts at top 10, 35/36 at top 20, 36/36 at top 60,
  5 good / 2 mixed rows, 6/7 rows complete at top 10, 5/7 strict success at top
  10, and 0 known false positives.
- Lupus row detail: `C0009506` Complement 3 was rank 21. `C0024141` Systemic
  lupus erythematosus was present at top 10 but had a low score because denial
  cues in the paragraph suppress disease concepts that remain central to the
  abstract frame.

## Hypothesis

The active-label supplement already reviewed `complement C3` as a `lab` field,
but that local field was not preserved for UMLS semantic types such as
`Immunologic Factor`. Preserving the reviewed local field should let the ranker
treat C3 as an observation/lab hit instead of a gene/protein mismatch. A small
curated-exact first-page recall pass should then preserve explicitly mentioned,
active-label supported lab and condition concepts in long documents without a
CUI-specific boost.

Expected movement: focused top-10 expected concepts should move from 35/36 to
36/36, all-expected rows from 6/7 to 7/7, and known false positives should stay
at zero.

## Change

- Preserved active-label supplement semantic rows even when the reviewed
  `semantic_type` is a UMLS semantic type outside the local-extension map, so
  rows such as `Immunologic Factor` keep `local_field=lab`.
- Added active-label local-field role handling in semantic-context ranking, so
  curated `lab` rows behave as `observation_lab` even when UMLS also classifies
  the CUI as an immunologic factor/protein.
- Added a bounded curated-exact long-document first-page recall pass after the
  existing long-document promotion step. It only considers active-label context
  supported, exact curated labels for lab and high-support condition mentions.
- Added focused tests for preserved active-label local fields, lab-role ranking,
  unreviewed immunologic-factor protection, and the combined Complement 3/SLE
  first-page recall shape.
- Regenerated `docs/search_rule_inventory.html`.

Rejected diagnostic:

- Output directory:
  `build/search_quality_experiments/runs/SQI-2026-06-11-008_pubmed_active_label_lab_role_complement_c3_sqi-2026-06-11-008-pubmed-active-label-lab-role-complement-c3`
- Result: no useful movement because the active-label semantic row was not
  present on the hit, so the ranker never saw `local_field=lab`.
- A later loader-only candidate moved C3 to rank 11 but displaced SLE from the
  first page, proving the final change also needed the curated-exact recall
  pass.

## Result

Focused live rerun:

- Query file: `build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_queries.tsv`
- Output directory: `build/search_quality_experiments/runs/SQI-2026-06-11-009_pubmed_curated_lab_condition_recall_final_8766_sqi-2026-06-11-009-pubmed-curated-lab-condition-recall-final-876`
- Server profile: `PORT=8766 PUBLIC_OUTPUT_ONLY=0 sh scripts/start_search_quality_server.sh`
- Command:

```sh
python3 scripts/run_search_quality_experiment.py --base-url http://127.0.0.1:8766 --scope umls_evidence --run-family probe --label 'SQI-2026-06-11-009 PubMed curated lab condition recall final 8766' --run-id SQI-2026-06-11-009_pubmed_curated_lab_condition_recall_final_8766 --queries build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_queries.tsv --query-limit 0 --search-system api --top-k 60 --timeout 120 --output-root build/search_quality_experiments --html-report docs/search_quality_experiments.html --require-api-backend elasticsearch
```

Measured movement:

- Expected concepts at top 10: 35/36 -> 36/36.
- Expected concepts at top 20: 35/36 -> 36/36.
- Expected concepts at top 60: 36/36 -> 36/36.
- Queries with all expected concepts at top 10: 6/7 -> 7/7.
- Strict success at top 10: 5/7 -> 6/7.
- Good / mixed rows: 5 good / 2 mixed -> 6 good / 1 mixed.
- Known false positives at top 10 and top 20: 0 -> 0.
- Lupus row: `C0009506` Complement 3 moved from rank 21 to rank 4 and
  `C0024141` Systemic lupus erythematosus stayed first-page visible at rank 5.
- Remaining focused issue: the CYP2C19 row is still mixed because aspirin is
  rank 1, even though no expected CUI is missing at top 10.

## Verification

- `python3 scripts/build_search_rule_inventory.py`
- `python3 -B -m pytest tests/test_evidence_vectors.py::test_active_label_supplement_preserves_umls_semantic_type_local_field tests/test_evidence_vectors.py::test_ranker_uses_active_label_lab_field_for_immunologic_factor_context tests/test_evidence_vectors.py::test_ranker_keeps_unreviewed_immunologic_factor_as_gene_protein_context tests/test_evidence_vectors.py::test_long_document_first_page_promotes_curated_lab_and_condition_recall -q`
- `python3 -m py_compile src/qe_evidence_vectors/search_ranking.py src/qe_evidence_vectors/search_service.py scripts/run_search_quality_experiment.py scripts/evaluate_paragraph_quality.py`
- `python3 scripts/run_search_quality_experiment.py --iteration-smoke-gates --iteration-id SQI-2026-06-11-009 --iteration-type ranking --iteration-type data --iteration-type long-document --base-url http://127.0.0.1:8766 --require-api-backend elasticsearch --force-rotating-smoke --force-patient-portal-smoke --static-command 'python3 -m py_compile src/qe_evidence_vectors/search_ranking.py src/qe_evidence_vectors/search_service.py scripts/run_search_quality_experiment.py scripts/evaluate_paragraph_quality.py && python3 scripts/validate_active_label_supplement.py' --focused-command 'python3 -B -m pytest tests/test_evidence_vectors.py::test_active_label_supplement_preserves_umls_semantic_type_local_field tests/test_evidence_vectors.py::test_ranker_uses_active_label_lab_field_for_immunologic_factor_context tests/test_evidence_vectors.py::test_ranker_keeps_unreviewed_immunologic_factor_as_gene_protein_context tests/test_evidence_vectors.py::test_long_document_first_page_promotes_curated_lab_and_condition_recall -q' --verification-out build/search_quality_verification/SQI-2026-06-11-009.json --verification-md-out build/search_quality_verification/SQI-2026-06-11-009.md`

The iteration smoke helper passed static, focused, standing clinical, rotating
50-query, and patient-portal gates. The rotating 50-query smoke produced 43/50
strict success at top 10, 47/50 at top 20, 47/50 top-on-target, and 3 top-wrong.
The patient-portal lane stayed at 12/12 top-on-target and 0 top-wrong.

## Decision

Keep. This fixes a reusable active-label metadata gap for reviewed lab concepts
and adds a bounded long-document recall guard for curated exact lab/condition
mentions without adding a CUI-specific runtime boost or accepting a weaker
substitution for SLE.
