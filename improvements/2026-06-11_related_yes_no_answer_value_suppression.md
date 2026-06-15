# Related Yes/No Answer-Value Suppression

## Problem

The progress log still listed a trust issue where cardiology queries about ST
elevation, right coronary artery occlusion, and PCI could surface a related-panel
value concept labeled `no`. Ranked results and semantic views already had partial
protection, but raw MRREL/research relation arrays and related-bucket fallback
paths still needed source-level filtering.

## Hypothesis

Only standalone answer values should be suppressed from related output. A narrow
normalized-label filter for `yes` and `no` should remove answer-value concepts
from MRREL concepts, research relations, and related result buckets while
preserving useful clinical labels such as `No vomiting` and direct ranked
searches for `yes` or `no`.

## Change

- Added a relation-value filter for standalone normalized labels `yes` and `no`
  in `search_related.py`.
- Applied it to MRREL related-concept merging and research-relation merging, so
  raw API payloads and detail panels do not expose those relation values.
- Added the same guard to `relation_visible_in_semantic_bucket`, so precomputed
  and fallback related result buckets cannot reintroduce those values.
- Added focused tests proving ranked `yes`/`no` direct searches are preserved,
  standalone relation values are hidden, and `No vomiting` remains visible.
- Regenerated `docs/search_rule_inventory.md`.

## Result

Live probes on `http://127.0.0.1:8766` for the cardiology portal-style sentence
and a direct ST-elevation/RCA-occlusion/PCI sentence returned zero standalone
`yes`/`no` leaks across:

- hit `research_relations`
- hit `external_embedding_neighbors`
- hit `mrrel_related_concepts`
- hit `related_concepts`
- `semantic_views`
- `semantic_view_sources`
- `semantic_group_views`
- `related_result_buckets`

The latest rotating smoke changed from 44/50 strict top 10 and 2 wrong-first
results to 42/50 strict top 10 and 1 wrong-first result. This iteration closes a
visible related-panel noise class but does not raise the product score because
strict rotating coverage decreased.

## Verification

- `python3 -m py_compile src/qe_evidence_vectors/search_related.py src/qe_evidence_vectors/search_semantic_buckets.py tests/test_evidence_vectors.py`
- `python3 -m pytest tests/test_evidence_vectors.py::test_query_ranker_filters_yes_no_answer_findings_in_clinical_context tests/test_evidence_vectors.py::test_related_outputs_filter_standalone_yes_no_answer_values -q`
- `python3 scripts/build_search_rule_inventory.py`
- Live cardiology related-output probe against `http://127.0.0.1:8766`
- `python3 scripts/run_search_quality_experiment.py --iteration-smoke-gates --iteration-id SQI-2026-06-11-011 --iteration-type ranking --iteration-type ui --static-command "python3 -m py_compile src/qe_evidence_vectors/search_related.py src/qe_evidence_vectors/search_semantic_buckets.py tests/test_evidence_vectors.py" --focused-command "python3 -m pytest tests/test_evidence_vectors.py::test_query_ranker_filters_yes_no_answer_findings_in_clinical_context tests/test_evidence_vectors.py::test_related_outputs_filter_standalone_yes_no_answer_values -q" --base-url http://127.0.0.1:8766 --force-rotating-smoke --force-patient-portal-smoke --verification-out build/search_quality_verification/SQI-2026-06-11-011.json --verification-md-out build/search_quality_verification/SQI-2026-06-11-011.md`

The iteration smoke helper passed static, focused, standing clinical, rotating
50-query, and patient-portal gates.

## Decision

Keep. This removes a user-visible answer-value relation leak without broad
generic suppression and without hiding useful negated clinical concepts.
