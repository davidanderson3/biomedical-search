# Search Quality Test & Weakness Ledger

This report is the running ledger for search-quality tests, audits, and changes.
It is meant to make each test reviewable after the fact: what weakness it found,
what evidence exposed that weakness, what solution was recommended, whether the
solution was implemented, and what should happen next.

The filterable HTML report is `docs/search_quality_iterations.html`.

Full numeric results live in these generated artifacts:

- `docs/search_quality_experiments.html`: repeated run table and latest
  benchmark results.
- `build/search_quality_experiments/runs/*/metrics.json`: machine-readable
  metrics for saved search-quality runs.
- `build/search_quality_experiments/iteration_smoke_gates/*/verification.md`:
  post-iteration smoke commands and pass/fail details.
- `build/source_acquisition/progression_report.md`: source-acquisition stage
  metrics, deltas, and accept/reject decisions.

## Iteration Contract

Every search-quality iteration should be small enough to review and should have
one primary purpose. Use this order:

1. Open `docs/search_quality_progress_log.html` first and use the latest
   current-loop cards, prioritized backlog task IDs, open-work items, and
   chronology to choose the next problem to investigate.
   Choose from the top rotating backlog window instead of repeatedly taking the
   first open P0 row. The current window is `SQB-002`, `SQB-013`, `SQB-003`,
   `SQB-014`, `SQB-004`, `SQB-005` source strategy and opt-in probes, and `SQB-006`, with
   `SQB-001` kept as continuous bad-result mining. Advance to the next unresolved row after each iteration
   unless a release-blocking regression or explicit blocker justifies a skip;
   record the skip reason in the progress log.
2. If this is the first iteration started on a new calendar day, summarize the
   previous day's shipped improvements in lay language in
   `docs/search_quality_daily_accomplishments.html` before choosing the next
   failure. Keep `docs/search_quality_progress_log.html` linked to that file.
   Skip this only when the previous day already has a plain-language summary.
3. Name the failure.
4. Classify the iteration type.
5. State the expected behavior before changing code or data.
6. Choose one route: make a code change, or procure/integrate targeted
   authoritative evidence.
7. Add or update a benchmark row, audit row, unit test, or report artifact.
8. Re-run the same benchmark slice used to name the weakness.
9. Promote only if the target improves without unacceptable regression;
   otherwise revert the code change or reject the evidence so the same
   acquisition is not repeated without a new hypothesis.
10. Restart the search API when runtime behavior changed.
11. Run and record the right smoke check before marking runtime/search-quality
   changes shipped.
12. Record the result here with the exact verification that was run.
13. Update `docs/search_quality_progress_log.html` whenever the headline status,
    latest-result cards, open-work list, or readable chronology changes. Do not
    mark an iteration shipped while the progress log still describes the
    previous result as current.
14. Refresh the prioritized backlog table in `docs/search_quality_progress_log.html`
    on every iteration. Each touched row should keep a stable task ID, priority,
    current gap, next diff, primary artifact, and done condition. Mark the
    active row closed, downgraded, blocked, or still-next with measured evidence;
    explicitly leave it unchanged only when the current backlog is still accurate
    after the iteration.
15. If the shipped iteration changes user-visible behavior, a major benchmark
    or smoke signal, source transparency, or a top known quality risk, update
    the whole-product quality percentage and history in
    `docs/search_quality_progress_log.html#whole-product-quality`.
16. If the iteration acquires, tests, promotes, rejects, reroutes, or changes
    source evidence, update `docs/search_quality_evidence_buckets.html` so the
    evidence remains bucketed by approval and test status.

Do not mix unrelated goals in one iteration. If a ranking fix uncovers a UI
problem, close the ranking iteration and open a UI/API iteration.

Smoke rule:

- For docs-only or local-source layout changes, record why a live smoke was not
  needed.
- For UI/report-only changes, run static syntax checks and a visual/static
  artifact check.
- For runtime search, source-code output, ranking, benchmark-label, judgment, or
  API behavior changes, run the standing clinical API smoke after the change.
- For broad ranking/runtime changes, benchmark definition changes, or anything
  used as a release-quality signal, also run the 50-query rotating smoke with
  gates.
- Do not mark a runtime search-quality iteration as `shipped` without either a
  passing smoke result or an explicit blocker/follow-up recorded in the entry.

## Iteration Types

Use these type labels so the HTML report can filter the ledger consistently:

| Type | Use when |
| --- | --- |
| `benchmark` | Adding or changing benchmark rows, smoke rows, or expected-result definitions. |
| `ranking` | Changing rerank, assertion, current-vs-history, semantic filtering, or generic suppression behavior. |
| `source-code` | Changing source vocabulary output such as RxNorm, SNOMED CT, LOINC, ICD, or source-code detail hydration. |
| `long-document` | Improving section/chunk linking, PubMed abstracts, long clinical notes, or merge/rerank across chunks. |
| `audit` | Classifying suspect rows, false positives, useful extras, or precision-review queues. |
| `ui` | Changing the search UI, report display, filters, links, or explainability presentation. |
| `process` | Changing the iteration process, report shape, release checklist, or documentation standard. |
| `data` | Changing source acquisition, active-label supplement rows, evidence sources, or generated indexes. |

## Entry Template

Copy this block for new entries:

```md
### SQI-YYYY-MM-DD-NNN: Short title

- Date: YYYY-MM-DD
- Status: proposed | in_progress | shipped | reverted | blocked
- Types: `ranking`, `benchmark`
- Weakness found: User example, benchmark failure, audit queue, or planned lane.
- Benchmark result: The headline x/y, recall, pass/fail, or `not a benchmark run`.
- Recommended solution: One or two sentences describing the target behavior or fix route.
- Solution implemented: Plain-language summary of the actual change, or `not implemented yet`.
- Artifacts: Files, reports, benchmark rows, or scripts.
- Test evidence: Commands, API checks, screenshots, manual checks, or audit rows.
- Implementation status: Keep, revise, revert, split follow-up, blocked, or not implemented.
- Remaining action: The next bounded step.
```

## Current Ledger

### SQI-2026-06-15-003: DailyMed warning-context recall

- Date: 2026-06-15
- Status: shipped
- Types: `data`, `benchmark`
- Weakness found: `SQB-005` had one remaining blocking miss in the pruned core source-specific lane. `dailymed_label_02` returned `C0043031` warfarin and `C0019080` Hemorrhage, but not `C1550014` Warning for `warfarin warning about serious bleeding`.
- Benchmark result: Before this change, the core source-specific lane was 8/9 rows complete with 19/20 expected CUIs at top 10. After this change, `SQI-2026-06-15-003-dailymed-warning-context` passed the blocking source-specific layer with 9/9 rows complete, 20/20 expected CUIs at top 10, 0 missing rows, and 0 wrong-first rows. The target row now ranks `C1550014` Warning - Alert level at rank 3.
- Recommended solution: Use governed, context-gated source-section label support for the suppressed generic Warning CUI. Do not globally admit the standalone `warning` label or add a broad ranking heuristic.
- Solution implemented: Added a context-gated active-label supplement row for `C1550014` Warning requiring drug-label or serious-bleeding context such as `warfarin`, `serious bleeding`, `drug label`, `DailyMed`, or `boxed warning`. Added a focused no-vector `SearchIndex` regression proving the DailyMed warning query surfaces `C1550014` while a bare `warning` query does not.
- Artifacts: `config/active_label_supplement.tsv`; `tests/test_evidence_vectors.py`; `build/search_quality_suite/SQI-2026-06-15-003-dailymed-warning-context/suite.md`; `build/search_quality_experiments/runs/SQI-2026-06-15-003-dailymed-warning-context-source_specific_evidence_search-quality-test-suite-source-specific-evidence`; `docs/search_quality_progress_log.html`; `docs/search_quality_evidence_buckets.html`; `docs/search_quality_iterations.html`; `docs/search_quality_test_suite.md`; `improvements/2026-06-15_dailymed_warning_context_recall.md`.
- Test evidence: `python3 scripts/validate_active_label_supplement.py` passed. `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile tests/test_evidence_vectors.py src/qe_evidence_vectors/search_rerank.py src/qe_evidence_vectors/search_service.py src/qe_evidence_vectors/active_label_supplement.py` passed. `PYTHONPATH=src:scripts python3 -m pytest tests/test_evidence_vectors.py -k "active_label_supplement_file_passes or dailymed_warning_context_supplement or consumer_lay_language_supplements" -q` passed with 4 tests. A fresh API on `http://127.0.0.1:8766` loaded the updated supplement and `PYTHONPATH=src:scripts python3 scripts/run_search_quality_suite.py --suite-id SQI-2026-06-15-003-dailymed-warning-context --only source_specific_evidence --fail-on blocking --command-timeout 180` passed the source-specific blocking layer. A direct API check for `warfarin warning about serious bleeding` returned `C1550014` at rank 3. The temporary API was stopped after verification.
- Implementation status: Keep. This closes the blocking DailyMed warning-context recall miss in the core source-specific lane, but it is a scoped supplement fix rather than full section-aware DailyMed relationship modeling.
- Remaining action: Add section-aware DailyMed relationship checks for indications, warnings, contraindications, interactions, populations, and pharmacology before expanding DailyMed coverage. Continue the next rotation row with `SQB-006` unless a release blocker interrupts.

### SQI-2026-06-15-002: Consumer lay-language active aliases

- Date: 2026-06-15
- Status: shipped
- Types: `data`, `benchmark`
- Weakness found: `SQB-004` had a failing 13-row consumer wording lane. The highest-signal failures were real patient phrases such as `water pill`, `pee test`, `belly pain`, `sugar diabetes`, `heart tracing`, `EKG`, `colon scope`, `stomach scope`, and `blood thinner`, which should be governed aliases rather than new ranking heuristics.
- Benchmark result: The last live consumer lane remains the 2026-06-12 baseline: 5/13 expected concepts in the first 10 answers, 3/13 top-on-target, 8 disallowed rows, and 10 wrong-first rows. After this change, direct in-process `SearchIndex` checks with no vectors put all 10 newly covered lay phrases on the intended CUI first, including `water pill furosemide` ranking furosemide ahead of the broad diuretic class.
- Recommended solution: Add reviewed active-label supplement rows for the main consumer lay phrases, validate the supplement, then rerun the live consumer lane from a freshly restarted API. If the expected CUIs are present but literal/anatomy/device/gene concepts remain visible, work those as targeted drift suppressions.
- Solution implemented: Added 10 consumer-health rows to `config/active_label_supplement.tsv` for water pill/diuretic, water pill plus furosemide, pee test/urinalysis, belly pain/abdominal pain, sugar diabetes/diabetes mellitus, heart tracing/EKG/electrocardiography, colon scope/colonoscopy, stomach scope/endoscopy, and blood thinner/anticoagulants. Added focused tests for configuration, governance fields, and no-vector `SearchIndex` first-result behavior. Regenerated the search rule inventory.
- Artifacts: `config/active_label_supplement.tsv`; `tests/test_evidence_vectors.py`; `docs/search_rule_inventory.md`; `docs/search_quality_progress_log.html`; `docs/search_quality_test_suite.md`; `improvements/2026-06-15_consumer_lay_language_active_aliases.md`.
- Test evidence: `python3 scripts/validate_active_label_supplement.py` passed. `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/active_label_supplement.py tests/test_evidence_vectors.py` passed. `PYTHONPATH=src:scripts python3 -m pytest tests/test_evidence_vectors.py -k "active_label_supplement_file_passes or consumer_lay_language_supplements or active_label_supplement_validation" -q` passed with 4 tests. `python3 scripts/build_search_rule_inventory.py` regenerated `docs/search_rule_inventory.md`. A temporary API start on port 8769 was attempted with a fresh supplement load, but it was stopped while still loading vectors before the HTTP listener was available, so no live consumer lane rerun was recorded.
- Implementation status: Keep as a partial `SQB-004` fix. The synonym/alias part is governed and tested; the live lane result is still pending.
- Remaining action: Restart the search API, rerun `consumer_lay_language`, and then address any remaining disallowed literal/anatomy/device/gene drift.

### SQI-2026-06-15-001: Coverage representativeness audit

- Date: 2026-06-15
- Status: shipped
- Types: `benchmark`, `audit`, `process`
- Weakness found: The iteration loop was improving very specific concept failures, but we did not have a repeatable answer to whether the asserted test targets represent broad clinical coverage or mostly the concepts that happened to appear in reviewed regressions and focused probes.
- Benchmark result: The static audit found 609 unique target CUIs, 2,210 target mentions, 87 unique risk/disallowed CUIs, and Disorders as the largest group at 48.3% of target mentions. Thin core semantic groups with fewer than 5 unique target CUIs are Anatomy, Phenomena, and Physiology.
- Recommended solution: Make evaluation coverage visible as a routine suite layer, then add a separate prevalence- or workflow-weighted common-clinical target list instead of relying only on one-off regression rows.
- Solution implemented: Added `scripts/build_search_quality_coverage_audit.py`, which reads the suite's expected, disallowed, wrong-first, source-anchor, and embedding-probe CUIs; enriches them with UMLS semantic groups and labels; and writes summary JSON, Markdown, and TSV detail reports. Added a nonblocking known-weakness command layer to the suite, added command-template support for suite IDs, and added focused tests.
- Artifacts: `scripts/build_search_quality_coverage_audit.py`; `tests/test_search_quality_coverage_audit.py`; `scripts/run_search_quality_suite.py`; `tests/test_search_quality_suite.py`; `config/search_quality_suite.json`; `docs/search_quality_progress_log.html`; `docs/search_quality_daily_accomplishments.html`; `docs/search_quality_test_suite.md`; `build/search_quality_coverage_audit/SQI-2026-06-15-001-coverage-audit/coverage_summary.md`; `build/search_quality_suite/SQI-2026-06-15-001-coverage-audit/suite.md`; `improvements/2026-06-15_coverage_representativeness_audit.md`.
- Test evidence: `python3 -m json.tool config/search_quality_suite.json >/dev/null` passed. `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile scripts/build_search_quality_coverage_audit.py scripts/run_search_quality_suite.py tests/test_search_quality_coverage_audit.py tests/test_search_quality_suite.py` passed. `PYTHONPATH=src:scripts python3 -m pytest tests/test_search_quality_coverage_audit.py tests/test_search_quality_suite.py -q` passed with 18 tests. The direct audit wrote `build/search_quality_coverage_audit/SQI-2026-06-15-001` and the suite command layer wrote `build/search_quality_coverage_audit/SQI-2026-06-15-001-coverage-audit` plus `build/search_quality_suite/SQI-2026-06-15-001-coverage-audit`, with status passed.
- Implementation status: Keep. This is an evaluation/process layer and does not claim the coverage problem is solved.
- Remaining action: Build the representative common-clinical target list for `SQB-014`, with reviewed quotas by semantic group and workflow, and keep it separate from one-off regression cases.

### SQI-2026-06-12-006: Server-side search timing

- Date: 2026-06-12
- Status: shipped
- Types: `process`, `long-document`
- Weakness found: `SQB-013` still had a 140s-plus focused PubMed loop after client-side API workers were added. The runner showed the remaining cost was inside `/api/search`, but it could not tell whether embedding, KNN retrieval, long-document chunk search, mention extraction, ranking, or response compaction was responsible.
- Benchmark result: The fresh uncached focused PubMed timing run took 148.291s wall time with 0 cache hits and preserved quality at 7/7 strict top 10, 7/7 top-on-target, and 0 wrong-first rows. Of 148.059s server time, 108.329s was long-document mention extraction, 34.326s was ranking/support/filtering outside that extractor, 1.479s was embedding, 0.214s was base vector search, 0.626s was long-document chunk vector search, and 0.001s was response compaction.
- Recommended solution: Add server-side timing to the search response and benchmark timing artifacts, preserve uncached timing for cached responses, then use the measured stage profile to narrow the next speed fix. Optimize long-document mention extraction before spending effort on chunk KNN batching or response compaction.
- Solution implemented: Added `server_timing` stage collection in `src/qe_evidence_vectors/search_execution.py`, nested long-document merge timings in `src/qe_evidence_vectors/search_rerank.py`, cached-response `uncached_server_timing`, and server timing columns/summaries in `scripts/run_search_quality_experiment.py`. Added focused tests for timing TSV aggregation and cached-response timing selection.
- Artifacts: `src/qe_evidence_vectors/search_execution.py`; `src/qe_evidence_vectors/search_rerank.py`; `scripts/run_search_quality_experiment.py`; `tests/test_search_quality_experiment_gates.py`; `docs/search_quality_progress_log.html`; `docs/search_quality_experiments.html`; `build/search_quality_experiments/runs/SQI-2026-06-12-006_pubmed_server_timing_sqi-2026-06-12-006-focused-pubmed-server-timing`; `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-12-006/verification.md`; `improvements/2026-06-12_server_side_search_timing.md`.
- Test evidence: `python3 -m py_compile src/qe_evidence_vectors/search_execution.py src/qe_evidence_vectors/search_rerank.py scripts/run_search_quality_experiment.py tests/test_search_quality_experiment_gates.py` passed. `PYTHONPATH=src:scripts python3 -m pytest tests/test_search_quality_experiment_gates.py -k "timings or api_response_requires" -q` passed with 2 tests. A fresh server on `http://127.0.0.1:8768` ran the focused PubMed timing probe with `--workers 1`, `--top-k 60`, and `--require-api-backend elasticsearch`, producing the metrics above. The formal smoke helper passed static, focused pytest, a direct live `server_timing` API assertion, and standing clinical API smoke; rotating and patient-portal smoke were explicitly skipped because this was a metadata/timing change and not a ranking change.
- Implementation status: Keep. `SQB-013` remains open, but the next target is now precise: reduce long-document mention extraction cost.
- Remaining action: Profile and optimize `query_entity_mentions` in the long-document path. Candidate next diffs are label-index prefiltering by document tokens, repeated-span caps, exact-label span reuse from earlier ranking work, or a cheaper final-only speed tier when ranking code does not touch long-document mention logic.

### SQI-2026-06-12-005: PubMed status-migrainosus corticosteroid-class guard

- Date: 2026-06-12
- Status: shipped
- Types: `ranking`, `long-document`
- Weakness found: `SQB-002` still had one approved PubMed wrong-first row. In `pubmed_status_migrainosus_30198804`, the long treatment-review abstract ranked broad `C0001617` Adrenal Cortex Hormones first because the text mentioned corticosteroids, even though the expected first-page concepts were status migrainosus, migraine variants, NSAIDs, and magnesium sulfate.
- Benchmark result: Before this change, the current approved PubMed lane had 9/13 rows complete at top 10, 10/13 complete at top 20, 53/60 expected concepts at top 10, 57/60 at top 20/60, 12/13 top-on-target, 1 wrong-first row, and overall score 76.7. After the change, `SQI-2026-06-12-005_pubmed_corticosteroid_guard` has 9/13 rows complete at top 10, 11/13 complete at top 20, 53/60 expected concepts at top 10, 57/60 at top 20/60, 13/13 top-on-target, 0 wrong-first rows, and overall score 77.9.
- Recommended solution: Add a scoped ranking guard for broad steroid/corticosteroid class hits in long treatment-review contexts with multiple non-class anchors. Do not add a generic filter, and do not break direct corticosteroid searches.
- Solution implemented: Added `broad_corticosteroid_class_penalty_for_hit`, a 0.18 rank penalty that only applies to broad corticosteroid/steroid class matches in long treatment-review queries with at least two specific non-class anchors. The penalty is included in score breakdowns and confidence context penalties. Added a focused regression test proving the broad class is no longer first for the status-migrainosus review fixture and that direct `corticosteroid treatment` still returns the corticosteroid class without the penalty.
- Artifacts: `src/qe_evidence_vectors/search_ranking.py`; `tests/test_evidence_vectors.py`; `docs/search_quality_progress_log.html`; `docs/search_quality_experiments.html`; `build/search_quality_experiments/runs/SQI-2026-06-12-005_pubmed_corticosteroid_guard_sqi-2026-06-12-005-approved-pubmed-corticosteroid-guard`; `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-12-005/verification.md`; `improvements/2026-06-12_pubmed_status_migrainosus_corticosteroid_guard.md`.
- Test evidence: `python3 -m py_compile src/qe_evidence_vectors/search_ranking.py tests/test_evidence_vectors.py` passed. `PYTHONPATH=src:scripts python3 -m pytest tests/test_evidence_vectors.py -k "corticosteroid or status_migrainosus or long_document_supported_secondary_concept or condition_variants_from_crowded_drug_tail or pharmacologic" -q` passed with 4 tests. A fresh server on `http://127.0.0.1:8767` ran the approved PubMed suite with `PYTHONPATH=src:scripts python3 scripts/run_search_quality_experiment.py --label "SQI-2026-06-12-005 approved PubMed corticosteroid guard" --run-id SQI-2026-06-12-005_pubmed_corticosteroid_guard --run-family custom --queries build/pubmed_literature_benchmark_seed/pubmed_literature_approved_queries.tsv --query-limit 0 --base-url http://127.0.0.1:8767 --require-api-backend elasticsearch --scope umls_evidence --search-system api --top-k 60 --timeout 180 --workers 1 --output-root build/search_quality_experiments --html-report docs/search_quality_experiments.html`, producing the improved metrics above. `PYTHONPATH=src:scripts python3 scripts/run_search_quality_experiment.py --iteration-smoke-gates --iteration-id SQI-2026-06-12-005 --iteration-type ranking --iteration-type long-document --static-command "python3 -m py_compile src/qe_evidence_vectors/search_ranking.py tests/test_evidence_vectors.py" --focused-command "PYTHONPATH=src:scripts python3 -m pytest tests/test_evidence_vectors.py -k 'corticosteroid or status_migrainosus or long_document_supported_secondary_concept or condition_variants_from_crowded_drug_tail or pharmacologic' -q" --base-url http://127.0.0.1:8767 --skip-rotating-smoke --skip-patient-portal-smoke` passed static, focused, and standing clinical smoke. Rotating and patient-portal smoke were explicitly skipped because the approved PubMed run was the heavier targeted long-document verification.
- Implementation status: Keep. The wrong-first phase of `SQB-002` is closed, but long-document recall remains open.
- Remaining action: Continue `SQB-002` recall work later in the rotation, starting with C. difficile infection in the fidaxomicin versus vancomycin abstract or the EGFR progression-free-survival/platinum/regimen misses.

### SQI-2026-06-12-004: Gene/protein molecular association opt-in gate

- Date: 2026-06-12
- Status: shipped
- Types: `ranking`
- Weakness found: `SQB-006` had no explicit default boundary between directly mentioned genes/proteins and relation-derived molecular associations. Ordinary clinical queries could admit GENE candidates through semantic/vector association paths, while the product still needs EGFR, BRCA1, CYP2C19, and other directly mentioned molecular concepts to work.
- Benchmark result: Focused unit slice passed with 6 tests. Post-iteration smoke helper passed static, focused, and standing clinical API smoke; rotating 50-query and patient-portal smoke were explicitly skipped because this was a narrow molecular default gate rather than a broad ranking retune.
- Recommended solution: Keep directly anchored molecular concepts available by default, but require an explicit molecular-association mode for relation-derived or unanchored gene/protein candidates in the main ranked results.
- Solution implemented: Added `molecular_associations` / `include_molecular_associations` as an API/search flag, included it in the search cache key and response metadata, threaded it through local and Elasticsearch rerank, blocked relation-anchor GENE/protein candidates when the flag is off, and added a default cutoff for unanchored gene/protein association results while preserving explicit molecular-context queries.
- Artifacts: `src/qe_evidence_vectors/search_ranking.py`; `src/qe_evidence_vectors/search_rerank.py`; `src/qe_evidence_vectors/search_execution.py`; `src/qe_evidence_vectors/search_quality_http.py`; `tests/test_evidence_vectors.py`; `docs/search_quality_experiments.html`; `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-12-004/verification.md`; `improvements/2026-06-12_gene_protein_molecular_association_gate.md`.
- Test evidence: `python3 -m py_compile src/qe_evidence_vectors/search_ranking.py src/qe_evidence_vectors/search_rerank.py src/qe_evidence_vectors/search_execution.py src/qe_evidence_vectors/search_quality_http.py tests/test_evidence_vectors.py` passed. `PYTHONPATH=src:scripts python3 -m pytest tests/test_evidence_vectors.py -k "related_anchor_candidates or gene_protein_associations or contextless_list_gene or contextless_large_gene or brca_breast_cancer" -q` passed with 6 tests. A fresh `scripts/start_search_quality_server.sh` process loaded 474,543 vectors, 190,051 docs, 0 external embedding links, and served `http://127.0.0.1:8766`; the API check showed `molecular_associations_enabled` toggles false/true from the query parameter. `PYTHONPATH=src:scripts python3 scripts/run_search_quality_experiment.py --iteration-smoke-gates --iteration-id SQI-2026-06-12-004 --iteration-type ranking --static-command "python3 -m py_compile src/qe_evidence_vectors/search_ranking.py src/qe_evidence_vectors/search_rerank.py src/qe_evidence_vectors/search_execution.py src/qe_evidence_vectors/search_quality_http.py tests/test_evidence_vectors.py" --focused-command "PYTHONPATH=src:scripts python3 -m pytest tests/test_evidence_vectors.py -k 'related_anchor_candidates or gene_protein_associations or contextless_list_gene or contextless_large_gene or brca_breast_cancer' -q" --base-url http://127.0.0.1:8766 --skip-rotating-smoke --skip-patient-portal-smoke` passed.
- Implementation status: Keep. The backend/API default gate is shipped, but the product affordance is not complete until there is a visible molecular-association control and a live negative/positive benchmark lane.
- Remaining action: Add the UI/provenance panel for molecular associations, then add live cardiology, infection, and medication negative controls plus EGFR, BRCA1, and CYP2C19 positives before closing `SQB-006`.

### SQI-2026-06-12-003: Source strategy pruning and opt-in embedding probes

- Date: 2026-06-12
- Status: shipped
- Types: `process`, `benchmark`, `audit`, `data`
- Weakness found: The default source-specific lane had drifted into a mixed bundle of core source evidence, research-relation candidates, trial registry text, and external CUI-neighbor associations. DailyMed and MedlinePlus also needed a concrete overlap answer against UMLS `MTHSPL` and `MEDLINEPLUS` SAB rows.
- Benchmark result: The targeted suite rerun passed the opt-in external embedding policy layer and failed the blocking source-specific layer only on the known DailyMed miss: the pruned 9-row live core source lane found 8/9 rows complete at top 10, 19/20 expected concepts at top 10, 9/9 top-on-target, 0 wrong-first rows, and 0 disallowed rows. The only remaining miss is `dailymed_label_02`, where warfarin ranks first, hemorrhage ranks second, and `C1550014` warning context is still absent. Static source strategy audit also found DailyMed direct evidence slices map many CUIs outside UMLS `MTHSPL` source-CUI coverage: 253/253 outside in the top-drugs slice and 360/376 outside in the corrected round-4 slice. The MedlinePlus full direct feed had 6,141/7,885 direct linked CUIs outside UMLS `MEDLINEPLUS` source-CUI coverage.
- Recommended solution: Keep DailyMed, MedlinePlus, and PubMed/PMC as the routine source-specific evidence lane. Keep DailyMed specifically for sectioned drug-label relationships: indications, adverse reactions, warnings, contraindications, interactions, populations, and pharmacology. Keep SapBERT as the active query/document embedding baseline. Keep CUI2Vec and BioConceptVec in the loop as opt-in association-signal probes and ablations, not default source evidence. Treat ClinicalTrials.gov posted outcomes as opt-in only, and keep PubTator3 as a sampled relation-candidate stub unless validated against PubMed/PMC for a measured gap.
- Solution implemented: Pruned `config/search_quality_source_specific_queries.tsv` to 9 core rows, pruned `config/source_specific_benchmarks.tsv`, removed ClinicalTrials.gov and PubTator3 benchmark files from the default source-specific lane, added `config/search_quality_source_strategy_audit.tsv`, added `config/search_quality_external_embedding_neighbor_probe.tsv`, made the search-quality server external CUI-vector index opt-in instead of auto-loaded by default, and updated source/test-suite documentation.
- Artifacts: `config/search_quality_source_specific_queries.tsv`; `config/source_specific_benchmarks.tsv`; `config/search_quality_suite.json`; `config/search_quality_source_strategy_audit.tsv`; `config/search_quality_external_embedding_neighbor_probe.tsv`; `scripts/search_quality_server.py`; `src/qe_evidence_vectors/search_service.py`; `tests/test_search_quality_suite.py`; `docs/search_quality_test_suite.md`; `docs/new_umls_iteration_loop.md`; `docs/search_quality_evidence_buckets.html`; `docs/search_quality_progress_log.html`; `docs/source_contribution_report.md`; `improvements/2026-06-12_source_strategy_pruning_and_embedding_policy.md`.
- Test evidence: `python3 -m json.tool config/search_quality_suite.json >/dev/null` passed. `python3 -m py_compile scripts/search_quality_server.py scripts/run_search_quality_suite.py scripts/run_search_quality_experiment.py scripts/build_source_evidence_dashboard.py tests/test_search_quality_suite.py src/qe_evidence_vectors/search_service.py src/qe_evidence_vectors/pubtator3.py` passed. `PYTHONPATH=src:scripts python3 -m pytest tests/test_search_quality_suite.py -q` passed with 15 tests. `PYTHONPATH=src:scripts python3 -m pytest tests/test_pubtator3.py -q` passed with 2 tests. HTML parser checks passed for touched reports, and `docs/search_quality_iterations.html` script passed `node --check`. `PYTHONPATH=src:scripts python3 scripts/run_search_quality_suite.py --suite-id SQI-2026-06-12-003-pruning-verification --only external_embedding_neighbor_probe --only source_specific_evidence --fail-on never --command-timeout 180` wrote `build/search_quality_suite/SQI-2026-06-12-003-pruning-verification`, passed the embedding layer, and failed the source layer at 8/9 rows complete and 19/20 expected concepts. The existing `http://127.0.0.1:8766` API still reports external CUI embeddings loaded because it predates the server default change, while the static server-default test verifies a fresh process will not auto-load them.
- Implementation status: Keep. This is a source-policy and benchmark-scope change, not a claim that ClinicalTrials.gov, PubTator3, CUI2Vec, or BioConceptVec have no value. It means they have no default-source claim yet.
- Remaining action: Fix the `dailymed_label_02` warning-context miss for `C1550014`, then add section-aware DailyMed relationship checks for label sections before expanding DailyMed coverage.

### SQI-2026-06-12-002: Consumer lay-language baseline

- Date: 2026-06-12
- Status: shipped
- Types: `benchmark`, `audit`, `process`
- Weakness found: `SQB-004` had no first-class short consumer wording lane. Existing MedlinePlus rows covered only three examples, while patient-portal rows were too long to catch terse searches such as `water pill`, `pee test`, `belly pain`, `sugar diabetes`, `heart tracing`, `colon scope`, `stomach scope`, and `blood thinner`.
- Benchmark result: The live 13-row consumer lay-language baseline found 5/13 expected concepts at top 10, 5/13 rows complete at top 10, 3/13 top-on-target, 2/13 strict success, 8 rows missing expected concepts, 8 rows with configured disallowed concepts at top 10, 10 wrong-first rows, and overall score 24.6.
- Recommended solution: Add a reviewed consumer lay-language probe with expected CUIs and explicit disallowed literal-drift CUIs, keep it nonblocking while it is red, and use the baseline to drive governed lay alias handling before promotion.
- Solution implemented: Added `config/search_quality_consumer_lay_queries.tsv` with 13 rows, added the `consumer_lay_language` known-weakness layer to the suite, added focused suite tests for the new layer and row set, and ran the live baseline against the Elasticsearch-backed API.
- Artifacts: `config/search_quality_consumer_lay_queries.tsv`; `config/search_quality_suite.json`; `tests/test_search_quality_suite.py`; `docs/search_quality_test_suite.md`; `docs/search_quality_progress_log.html`; `docs/search_quality_iterations.html`; `docs/search_quality_experiments.html`; `improvements/2026-06-12_consumer_lay_language_baseline.md`; `build/search_quality_experiments/runs/SQI-2026-06-12-002_consumer_lay_language_baseline_sqi-2026-06-12-002-consumer-lay-language-baseline`.
- Test evidence: `python3 -m json.tool config/search_quality_suite.json >/dev/null` passed. `python3 -m py_compile scripts/run_search_quality_suite.py scripts/run_search_quality_experiment.py tests/test_search_quality_suite.py` passed. `PYTHONPATH=src:scripts python3 -m pytest tests/test_search_quality_suite.py -q` passed with 12 tests. The live consumer lay-language baseline completed against `http://127.0.0.1:8766` with `--require-api-backend elasticsearch` and wrote the metrics above.
- Implementation status: Keep as a known-weakness benchmark/process change. No runtime ranking behavior changed, so no API restart was needed.
- Remaining action: Add governed lay alias handling for `water pill`, `pee test`, `belly pain`, `sugar diabetes`, `heart tracing`, `EKG`, `colon scope`, `stomach scope`, and `blood thinner`, plus literal/anatomy/gene drift suppression; then rerun the 13-row lane. Continue the next rotation step with `SQB-005` frozen open-API snapshots unless a release blocker interrupts.

### SQI-2026-06-12-001: Backlog rotation and real short-query expansion probe

- Date: 2026-06-12
- Status: shipped
- Types: `process`, `benchmark`, `audit`
- Weakness found: The prior iteration instructions could keep choosing the first open P0 row and stall the loop on `SQB-002`. Rotating to `SQB-003` exposed that the current live API no longer carries some exact linked/mentioned concepts into main ranked hits for reviewed short searches.
- Benchmark result: The 26-row live SQB-003 expansion probe `SQI-2026-06-12-001_real_short_query_expansion` found 19/26 expected concepts at top 10, 19/26 top-on-target, 19/26 strict top 10, 7 poor rows, 7 wrong-first rows, and 0 configured disallowed concepts at top 10. The blocking short-query lane remains the previously reviewed 20-row set.
- Recommended solution: Make the iteration rule cycle across the first several active backlog rows, and do not promote the three-word short-query candidates until exact linked/mentioned clinical labels are promoted into main ranked hits safely.
- Solution implemented: Added the June 11 daily accomplishment summary, changed the iteration contract and progress-log backlog rule to a rotating top-backlog window, ran the SQB-003 26-row probe, rejected the candidate row promotion, and restored the blocking short-query gate to the 20 reviewed rows.
- Artifacts: `docs/search_quality_daily_accomplishments.html`; `docs/search_quality_progress_log.html`; `docs/search_quality_iterations.md`; `docs/search_quality_iterations.html`; `docs/search_quality_test_suite.md`; `docs/search_quality_experiments.html`; `build/search_quality_experiments/runs/SQI-2026-06-12-001_real_short_query_expansion_sqi-2026-06-12-001-real-short-query-expansion`; `improvements/2026-06-12_real_short_query_rotation_probe.md`.
- Test evidence: `python3 -m py_compile scripts/run_private_real_query_diagnostic.py scripts/run_search_quality_suite.py scripts/run_search_quality_experiment.py` passed. `PYTHONPATH=src:scripts python3 -m pytest tests/test_search_quality_suite.py tests/test_private_real_query_diagnostic.py tests/test_build_real_query_inventory.py -q` passed with 22 tests before the candidate rows were rejected; the focused suite tests were rerun after restoring the 20-row gate. The live 26-row API probe completed against `http://127.0.0.1:8766` with `--require-api-backend elasticsearch` and produced the failed metrics above. HTML/parser checks passed for the touched reports.
- Implementation status: Keep the process change and the failed-probe artifact. Reject the attempted SQB-003 promotion for now; no runtime ranking change shipped, and no API restart was needed.
- Remaining action: Fix exact linked/mentioned label carryover for cases such as `heart failure`, `type 2 diabetes mellitus`, `chronic kidney disease`, `urinary tract infection`, `acute kidney injury`, and `deep vein thrombosis`; then rerun the 26-row candidate batch before promoting any new short-query rows. Continue the next iteration from the rotating backlog window rather than returning automatically to `SQB-002`.

### SQI-2026-06-11-024: Runner timing and bounded API workers

- Date: 2026-06-11
- Status: shipped
- Types: `process`, `benchmark`
- Weakness found: `SQB-013` identified that uncached focused PubMed iterations spend about 140-152 seconds for only seven rows, with almost all wall time inside `/api/search`. The benchmark runner also executed live API requests serially and did not persist per-query timing artifacts.
- Benchmark result: Nonce-suffixed focused PubMed speed probes showed the serial runner at 142.080 seconds with 0 cache hits and 141.989 seconds of summed API response time. Two API workers finished in 140.684 seconds with 0 cache hits and 243.649 seconds of summed API response time. Four workers finished in 142.820 seconds with 0 cache hits and 439.541 seconds of summed API response time. All three probes stayed at 7/7 strict top 10 and 7/7 top-on-target.
- Recommended solution: Remove client-side runner serialization in a bounded way, write per-query timing artifacts, and use the measured local result to choose a conservative default. If wall time does not materially improve, leave the speed backlog open for server-side long-document instrumentation and mitigation.
- Solution implemented: Added `--workers` to `scripts/run_search_quality_experiment.py`, defaulting live API runs to two worker threads while keeping UMLS-only in-process runs serial. The runner now preserves deterministic output order under parallel completion and writes `query_timings.tsv` plus timing summary fields in `metrics.json`.
- Artifacts: `scripts/run_search_quality_experiment.py`; `tests/test_search_quality_experiment_gates.py`; `improvements/2026-06-11_iteration_speed_runner_timing.md`; `build/search_quality_speed_probe/runs/SQI-2026-06-11-024_speed_probe_serial_sqi-2026-06-11-024-focused-pubmed-speed-probe-serial`; `build/search_quality_speed_probe/runs/SQI-2026-06-11-024_speed_probe_workers2_sqi-2026-06-11-024-focused-pubmed-speed-probe-workers-2`; `build/search_quality_speed_probe/runs/SQI-2026-06-11-024_speed_probe_parallel_sqi-2026-06-11-024-focused-pubmed-speed-probe-parallel`; `docs/search_quality_progress_log.html`.
- Test evidence: `python3 -m py_compile scripts/run_search_quality_experiment.py tests/test_search_quality_experiment_gates.py` passed. `PYTHONPATH=src:scripts python3 -m pytest tests/test_search_quality_experiment_gates.py -q` passed with 14 tests. Live nonce probes against `http://127.0.0.1:8766` required the Elasticsearch backend and confirmed 0 cache hits in each speed run.
- Implementation status: Keep as a partial mitigation. The runner no longer serializes API calls, and the timing report now identifies `/api/search` as the dominant local cost. The measured wall-clock improvement is only about 1%, so this does not close `SQB-013`.
- Remaining action: Keep `SQB-013` open. Next add server-side timing for embedding, base KNN, chunk KNN, mention extraction, rank/merge, and compaction, then mitigate the dominant stage with batched/parallel chunk KNN or raw retrieval reuse.

### SQI-2026-06-11-023: Oral vancomycin product accepted for ingredient target

- Date: 2026-06-11
- Status: shipped
- Types: `benchmark`, `long-document`
- Weakness found: The approved PubMed row `pubmed_cdiff_antibiotic_diarrhea_21288078` ranked `C0360373` vancomycin Oral Product first for an abstract that explicitly says `oral vancomycin`, while the benchmark expected `C0042313` vancomycin. The same row still missed `C0343386` Clostridium difficile infection at top 10.
- Benchmark result: The approved PubMed rerun `SQI-2026-06-11-023_pubmed_oral_vancomycin_alternative` moved the lane from 11/13 to 12/13 top-on-target and from 2 to 1 wrong-first rows. It stayed at 9/13 strict top 10 and 53/60 expected concepts at top 10, improved strict top 20 from 9/13 to 10/13, kept 57/60 expected concepts at top 20/top 60, and moved overall score from 75.6 to 76.7. The C. difficile row is now top-on-target and strict at top 20, but remains mixed at top 10 because `C0343386` is still missing there.
- Recommended solution: Treat the oral vancomycin product as an acceptable alternative for the vancomycin ingredient target when the abstract explicitly says `oral vancomycin`, matching the existing policy that specific drug forms can satisfy ingredient targets. Do not count that as satisfying the separate C. difficile infection target.
- Solution implemented: Added `C0042313 -> C0360373` to `config/search_quality_acceptable_cui_alternatives.tsv` and added a focused evaluator regression that proves the oral product fixes top-on-target while preserving the infection miss and mixed verdict.
- Artifacts: `config/search_quality_acceptable_cui_alternatives.tsv`; `tests/test_evidence_vectors.py`; `improvements/2026-06-11_oral_vancomycin_product_alternative.md`; `docs/search_quality_progress_log.html`; `docs/search_quality_experiments.html`; `build/search_quality_experiments/runs/SQI-2026-06-11-023_pubmed_oral_vancomycin_alternative_sqi-2026-06-11-023-oral-vancomycin-product-alternative`; `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-11-023/verification.md`.
- Test evidence: `py_compile` passed for `tests/test_evidence_vectors.py` and `scripts/run_search_quality_experiment.py`. Focused evaluator tests passed with 3 tests. The 13-row approved PubMed rerun showed 12/13 top-on-target, 1 wrong-first row, 9/13 strict top 10, 10/13 strict top 20, and overall score 76.7. The formal SQI-2026-06-11-023 smoke helper passed static, focused, standing clinical API, rotating 50-query, and patient-portal gates.
- Implementation status: Keep. This is a benchmark-equivalence clarification, not a runtime ranking change. It closes the approved-suite wrong-first classification for the oral-vancomycin row while leaving its C. difficile infection top-10 recall miss open.
- Remaining action: Under the rotating backlog rule, revisit `SQB-002` when its turn comes up and fix the remaining approved-suite wrong-first row, `pubmed_status_migrainosus_30198804`, where broad `C0001617` Adrenal Cortex Hormones ranks first above status-migrainosus and migraine anchors.

### SQI-2026-06-11-022: Approved PubMed long-document baseline and miss taxonomy

- Date: 2026-06-11
- Status: shipped
- Types: `audit`, `long-document`, `benchmark`
- Weakness found: `SQB-002 Long-document survival` still used a stale approved PubMed baseline from before the focused 7-row PubMed fixes. The backlog required a fresh 13-abstract run and a miss classification before another long-document implementation change.
- Benchmark result: The live approved PubMed rerun improved from the stale 3/13 rows complete and 44/60 expected concepts at top 10 to 9/13 rows complete at top 10, 53/60 expected concepts at top 10, 57/60 at top 20 and top 60, 11/13 top-on-target, 2 wrong-first rows, 4 mixed rows, 0 poor rows, and overall score 75.6. Runtime was 404.176 seconds.
- Recommended solution: Treat this as a baseline/audit iteration: classify every remaining miss as present by top 20 but lost during first-page merge/rerank, absent evidence/linking, overqualified benchmark target, acceptable-alternative candidate, or wrong-first suppression needed.
- Solution implemented: Reran the full approved PubMed suite against the live Elasticsearch-backed API and classified all four mixed rows. `pubmed_status_migrainosus_30198804` needs first-page preservation plus broad corticosteroid wrong-first suppression; `pubmed_egfr_nsclc_37879444` has PFS at rank 18, absent Osimertinib, and a platinum-versus-regimen equivalence question; `pubmed_cdiff_antibiotic_diarrhea_21288078` has C. difficile infection at rank 16 and an overqualified vancomycin oral-product first result; `pubmed_lupus_preeclampsia_8659509` has an overqualified or unsupported Complement 3 target for title-only hypocomplementemia.
- Artifacts: `improvements/2026-06-11_pubmed_approved_long_document_baseline.md`; `docs/search_quality_progress_log.html`; `docs/search_quality_experiments.html`; `build/search_quality_experiments/runs/SQI-2026-06-11-022_pubmed_approved_baseline_sqi-2026-06-11-022-approved-pubmed-long-document-baseline/metrics.json`; `build/search_quality_experiments/runs/SQI-2026-06-11-022_pubmed_approved_baseline_sqi-2026-06-11-022-approved-pubmed-long-document-baseline/rows.tsv`; `build/search_quality_experiments/runs/SQI-2026-06-11-022_pubmed_approved_baseline_sqi-2026-06-11-022-approved-pubmed-long-document-baseline/payloads/`.
- Test evidence: `PYTHONPATH=src python3 scripts/run_search_quality_experiment.py --label "SQI-2026-06-11-022 approved PubMed long-document baseline" --run-id SQI-2026-06-11-022_pubmed_approved_baseline --run-family probe --queries build/pubmed_literature_benchmark_seed/pubmed_literature_approved_queries.tsv --query-limit 0 --base-url http://127.0.0.1:8766 --require-api-backend elasticsearch --scope umls_evidence --mode balanced --search-system api --top-k 60 --timeout 180 --output-root build/search_quality_experiments --html-report docs/search_quality_experiments.html` completed and regenerated the experiment report. Payload inspection confirmed the miss classes above. HTML parser checks passed for the progress log, iteration ledger, and experiments report; the iteration-ledger JavaScript passed `node --check`; SQI-022 metrics assertions passed; and `git diff --check` passed for touched source/report files. No API restart or broad smoke was needed because no runtime code, ranking rule, benchmark definition, or source data changed.
- Implementation status: Keep. This updates the stale approved PubMed baseline and gives every miss a fix class, but does not close `SQB-002` because two wrong-first rows remain.
- Remaining action: The vancomycin oral-product policy was resolved by SQI-2026-06-11-023. Under the rotating backlog rule, revisit `SQB-002` when its turn comes up and fix `pubmed_status_migrainosus_30198804`, the remaining approved-suite wrong-first row.

### SQI-2026-06-11-021: OUD treatment anchors above broad addiction behavior

- Date: 2026-06-11
- Status: shipped
- Types: `ranking`
- Weakness found: The fresh SQI-2026-06-11-020 rotating smoke found `paragraph_112` as a wrong-first row: broad `C0085281` Addictive Behavior ranked first for an addiction-medicine paragraph that explicitly named opioid use disorder, fentanyl exposure, withdrawal symptoms, buprenorphine/naloxone, and urine drug screen.
- Benchmark result: The SQI-2026-06-11-021 rotating smoke included `paragraph_112` and moved it to top-on-target: `C0015846` fentanyl ranked first, `C1169989` buprenorphine / naloxone second, `C0202274` drug screen urine third, and Addictive Behavior sixth. The row remains mixed because `C4324621` Opioid Use Disorder is still missing at top 10/20. The full rotating smoke passed release gates with 45/50 strict top 10, 49/50 strict top 20, 50/50 top-on-target, 0 wrong-first, 48 good / 2 mixed rows, and overall score 92.9. Patient portal passed with 12/12 top-on-target and 0 wrong-first.
- Recommended solution: Penalize broad addiction-behavior labels only when a query has specific opioid-use-disorder treatment context, while preserving explicit substance, medication, test, and withdrawal anchors.
- Solution implemented: Added `hit_has_broad_addiction_behavior_context` and `query_has_specific_opioid_use_disorder_context` to the clinical-context sense penalty path. Also corrected the existing opioid-specific phrase guard so it does not require the stopword `use` to survive content-token filtering. Added a focused regression proving broad Addictive Behavior is demoted below fentanyl or buprenorphine/naloxone in the OUD treatment paragraph shape.
- Artifacts: `src/qe_evidence_vectors/search_ranking.py`; `tests/test_evidence_vectors.py`; `config/search_quality_wrong_first_noise_ledger.tsv`; `docs/search_quality_wrong_first_noise_ledger.md`; `improvements/2026-06-11_opioid_use_disorder_addiction_behavior_wrong_first.md`; `docs/search_quality_progress_log.html`; `docs/search_quality_experiments.html`; `build/search_quality_experiments/runs/SQI-2026-06-11-021_rotating_50_sqi-2026-06-11-021-automated-50-query-smoke`; `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-11-021/verification.md`.
- Test evidence: `python3 -m py_compile src/qe_evidence_vectors/search_ranking.py tests/test_evidence_vectors.py` passed. Focused ranker tests passed with 3 tests. A live paragraph probe moved Addictive Behavior from first to sixth. The formal SQI-2026-06-11-021 smoke helper passed static, focused, standing clinical, rotating 50-query, and patient-portal gates.
- Implementation status: Keep. This closes WFN-014 and removes the fresh rotating wrong-first row without changing patient-portal current-versus-history behavior.
- Remaining action: Investigate why promoted `C4324621` Opioid Use Disorder is still absent from public top 10/20 for `paragraph_112`, and continue with `C1550014` DailyMed warning-context recall.

### SQI-2026-06-11-020: Generic screening below direct literature targets

- Date: 2026-06-11
- Status: shipped
- Types: `ranking`
- Weakness found: WFN-013 showed a source-specific trust failure: `colonoscopy screening and colorectal cancer literature` ranked broad `C0199230` Screening for cancer first instead of the directly named colonoscopy procedure and colorectal-cancer endpoint.
- Benchmark result: The live source-specific rerun `SQI-2026-06-11-020_source_specific_generic_screening` ranks `C0009378` colonoscopy first, `C0009402` Colorectal Carcinoma second, and `C0199230` Screening for cancer fifth for `pubmed_pmc_lit_02`. The lane now has 14/15 rows complete at top 10, 34/35 expected concepts at top 10, 15/15 top-on-target, 14/15 strict top 10, 14 good / 1 mixed rows, and 0 wrong-first rows. It still fails source-specific blocking gates because `dailymed_label_02` misses `C1550014` and the source-count collapse gate remains tripped.
- Recommended solution: Penalize broad screening concepts only when a screening query also contains direct target anchors that the candidate cannot support, while preserving direct generic screening queries and specific screening concepts.
- Solution implemented: Added `generic_screening_context_penalty` to ranking, score breakdown, and confidence accounting. The rule fires for broad screening labels that match only generic screening/cancer/procedure wording while missing query anchors such as `colonoscopy` or `colorectal`; MRREL-matched and label-supported anchors protect specific screening concepts. Added focused tests for the source-specific wrong-first shape plus direct `cancer screening literature` protection.
- Artifacts: `src/qe_evidence_vectors/search_ranking.py`; `tests/test_evidence_vectors.py`; `docs/search_rule_inventory.md`; `config/search_quality_wrong_first_noise_ledger.tsv`; `docs/search_quality_wrong_first_noise_ledger.md`; `improvements/2026-06-11_generic_screening_over_direct_targets.md`; `docs/search_quality_progress_log.html`; `docs/search_quality_experiments.html`; `build/search_quality_experiments/runs/SQI-2026-06-11-020_source_specific_generic_screening_sqi-2026-06-11-020-generic-screening-direct-target-ranking`; `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-11-020/verification.md`.
- Test evidence: `python3 -m py_compile src/qe_evidence_vectors/search_ranking.py tests/test_evidence_vectors.py` passed. Focused ranker tests passed with 5 tests. A live WFN-013 probe returned colonoscopy, Colorectal Carcinoma, Screening for Colorectal Cancer, Screening procedure, then Screening for cancer. The source-specific rerun had 0 wrong-first rows but remained nonzero because of the known `C1550014` miss/source-count gate. The formal SQI-2026-06-11-020 smoke helper passed static, focused, standing clinical, and rotating 50-query checks; rotating smoke had 45/50 strict top 10, 49/50 strict top 20, 49/50 top-on-target, and 1 wrong-first row in fresh untriaged `paragraph_112`. The helper failed the patient-portal step only on `source_count_no_unexpected_collapse` because current public-output payloads omit top-level source-code `source_contributions`; a direct comparison confirmed patient-portal quality metrics were unchanged from SQI-2026-06-11-019 at 1/12 strict top 10, 6/12 strict top 20, 12/12 top-on-target, and 0 wrong-first rows.
- Implementation status: Keep. This closes WFN-013 and removes the known source-specific wrong-first row; it does not solve the DailyMed warning-context recall miss or the public-output source-count gate artifact.
- Remaining action: Fix `dailymed_label_02` warning-context recall for `C1550014` and investigate the remaining `C4324621` Opioid Use Disorder top-10/20 miss in `paragraph_112`. The wrong-first triage from this run was closed by SQI-2026-06-11-021.

### SQI-2026-06-11-019: Source-specific equivalence triage

- Date: 2026-06-11
- Status: shipped
- Types: `benchmark`, `audit`
- Weakness found: The new source-specific evidence lane failed at 10/15 rows complete at top 10, 30/35 expected concepts at top 10, 5 rows missing expected concepts, and 1 wrong-first row. Review showed four misses were benchmark-equivalence splits rather than search failures: HbA1c measurement/analyte wording, DailyMed adverse-reaction wording, and EGFR receptor/protein versus EGFR gene in PubTator3 relationship queries.
- Benchmark result: After adding reviewed accepted alternatives, `SQI-2026-06-11-019_source_specific_equivalence_triage` improved to 14/15 rows complete at top 10, 34/35 expected concepts at top 10, 13/15 strict top 10, 14/15 top-on-target, 13 good / 2 mixed rows, and 1 wrong-first row. The source-specific suite threshold still fails because `dailymed_label_02` misses `C1550014` warning context and `pubmed_pmc_lit_02` ranks `C0199230` Screening for cancer above colonoscopy and Colorectal Carcinoma.
- Recommended solution: Accept only clinically equivalent source-specific label variants, do not accept broad cancer screening as a substitute for the direct colonoscopy/colorectal-cancer targets, and promote the remaining wrong-first row into the reviewed ledger.
- Solution implemented: Added accepted alternatives for `C0202054` HbA1c measurement to `C0019018` and `C5979904`, `C0041755` adverse reaction to `C0413696` and `C0559546`, and `C0034802` EGFR receptor/protein to `C1414313` EGFR gene. Added a suite regression assertion for those accepted alternatives and opened `WFN-013` for the remaining broad-screening wrong-first row. Updated the progress log and suite documentation to show the lane is improved but still blocking.
- Artifacts: `config/search_quality_acceptable_cui_alternatives.tsv`; `tests/test_search_quality_suite.py`; `config/search_quality_wrong_first_noise_ledger.tsv`; `docs/search_quality_wrong_first_noise_ledger.md`; `docs/search_quality_test_suite.md`; `improvements/2026-06-11_source_specific_equivalence_triage.md`; `docs/search_quality_progress_log.html`; `docs/search_quality_experiments.html`; `build/search_quality_experiments/runs/SQI-2026-06-11-019_source_specific_equivalence_triage_sqi-2026-06-11-019-source-specific-equivalence-triage`; `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-11-019/verification.md`.
- Test evidence: Focused source-specific live rerun improved to 34/35 expected concepts at top 10 and 14/15 rows complete at top 10; focused suite-file tests passed with 3 tests; the formal SQI-2026-06-11-019 smoke helper passed static, focused, standing clinical, rotating 50-query, and patient-portal gates. The rotating 50-query smoke had 45/50 strict top 10, 50/50 strict top 20, 50/50 top-on-target, and 0 wrong-first rows; patient portal stayed at 1/12 strict top 10, 6/12 strict top 20, 12/12 top-on-target, and 0 wrong-first rows.
- Implementation status: Keep. This is a benchmark/audit cleanup, not a ranking fix, and it leaves the source-specific gate correctly blocking.
- Remaining action: Fix `dailymed_label_02` warning-context recall for `C1550014` and `WFN-013`, the generic Screening for cancer wrong-first row, before promoting the source-specific lane as stable.

### SQI-2026-06-11-018: Iteration speed mitigation backlog

- Date: 2026-06-11
- Status: proposed
- Types: `process`, `benchmark`, `long-document`
- Weakness found: The current improvement loop spends too much wall time rerunning targeted PubMed and smoke lanes. Saved run payloads show the expensive path is not report generation: recent uncached focused PubMed runs take about 140-152 seconds for only 7 rows, almost entirely inside `/api/search`.
- Benchmark result: Not a new benchmark run. Existing run artifacts show the 7-row PubMed focused lane repeatedly spends about 20-22 seconds per query when uncached, with several 7-8 chunk abstracts taking about 30-41 seconds individually. Recent 50-query smoke runs spend about 33-40 seconds, and patient-portal smoke spends about 16-18 seconds.
- Recommended solution: Treat iteration speed as a P0 process/runtime backlog item. First add timing breakdowns for embedding, base KNN, chunk KNN, mention extraction, rank/merge, compaction, and report writing. Then ship one bounded mitigation: benchmark runner workers, batched or parallel long-document chunk KNN, raw retrieval caching that survives rerank-only work, or a documented final-only smoke tier when broad gates are unchanged.
- Solution implemented: Not implemented yet. Added `SQB-013 Iteration speed mitigation` to the prioritized backlog as a P0 task without renumbering existing SQB rows.
- Artifacts: `docs/search_quality_progress_log.html`; `docs/search_quality_iterations.md`; `docs/search_quality_iterations.html`; prior saved payloads under `build/search_quality_experiments/runs/*/payloads/`.
- Test evidence: Static documentation update only; no live smoke needed because this does not change runtime behavior, benchmark labels, ranking, source data, or API output.
- Implementation status: Not implemented; P0 backlog item.
- Remaining action: Start with instrumentation so the next mitigation is chosen from measured stage timings rather than inferred totals.

### SQI-2026-06-11-017: Objective-confirmed condition over presenting symptom

- Date: 2026-06-11
- Status: shipped
- Types: `ranking`, `benchmark`
- Weakness found: WFN-012 showed a search-style trust failure: `Search: pleuritic chest pain and dyspnea after long flight. CT angiography showed pulmonary embolism...` ranked `C0008031` Chest Pain first instead of the imaging-confirmed embolism diagnosis.
- Benchmark result: Before the fix, the SQI-2026-06-11-016 full clinical rerun had 1 wrong-first row, `paragraph_135`. After the fix, the focused live probe ranked `C0034065` Pulmonary Embolism first with `objective_confirmed_condition_component` 0.56 and no semantic-context penalty; direct `pleuritic chest pain` and `CT angiography` searches still received no objective-confirmed-condition boost. The formal SQI-2026-06-11-017 rotating gate passed with 46/50 rows complete at top 10, 46/50 strict top 10, 50/50 strict top 20, 50/50 top-on-target, and 0 wrong-first rows; the same rotating seed stayed clean after the accepted-variant benchmark update. The comparable SQI-2026-06-11-011 rotating seed stayed at 0 wrong-first rows. The final full clinical rerun passed gates with 844/874 expected concepts at top 10, 148/168 rows complete at top 10, 148/168 strict top 10, 166/168 strict top 20, 168/168 top-on-target, and 0 wrong-first rows.
- Recommended solution: Add a narrow objective-confirmation rank signal for assertable condition spans immediately following imaging/procedure confirmation wording such as `CT angiography showed pulmonary embolism`, without boosting direct symptom or procedure lookup intent.
- Solution implemented: Added `objective_confirmed_condition_component` to ranking, score breakdown, and confidence support; required same-sentence objective confirmation verbs plus imaging/procedure source tokens; exempted the confirmed condition from the procedure-context semantic penalty; and added focused tests for the pulmonary-embolism wrong-first sentence plus direct symptom/procedure protection. Added `C5395033` Severe aortic valve stenosis as an acceptable alternative for the broader `C0003507` Aortic Valve Stenosis target after the new component surfaced the already-reviewed more-specific concept in `paragraph_73`.
- Artifacts: `src/qe_evidence_vectors/search_ranking.py`; `tests/test_evidence_vectors.py`; `config/search_quality_acceptable_cui_alternatives.tsv`; `docs/search_rule_inventory.md`; `config/search_quality_wrong_first_noise_ledger.tsv`; `docs/search_quality_wrong_first_noise_ledger.md`; `improvements/2026-06-11_objective_confirmed_condition_over_presenting_symptom.md`; `docs/search_quality_progress_log.html`; `docs/search_quality_experiments.html`; `build/search_quality_verification/SQI-2026-06-11-017.md`.
- Test evidence: Focused tests passed with 5 tests; focused ranker slice passed with 9 tests; py_compile passed; focused live API probe ranked Pulmonary Embolism first with `objective_confirmed_condition_component` 0.56; direct `pleuritic chest pain` and `CT angiography` searches kept the new component at 0; the SQI-2026-06-11-017 smoke helper passed static, focused, standing clinical, rotating 50-query, and patient-portal gates; the post-accepted-variant rotating seed check passed with 0 wrong-first rows; the comparable SQI-2026-06-11-011 rotating seed check passed with 0 wrong-first rows; the final full 168-row clinical benchmark rerun passed release gates with 0 wrong-first rows.
- Implementation status: Keep. This closes WFN-012 and leaves no open rows in the current wrong-first ledger.
- Remaining action: Shift the P0 work from known wrong-first fixes to active bad-result mining, long-document survival in the broader PubMed suite, and promotion of the newer lanes into routine gates. Keep WFN-001, WFN-008, WFN-009, WFN-010, WFN-011, WFN-012, cardiology yes/no, and CYP2C19-guided therapy in regression coverage.

### SQI-2026-06-11-016: Reaction diagnosis over trigger exposure

- Date: 2026-06-11
- Status: shipped
- Types: `ranking`
- Weakness found: WFN-009 showed a trigger-over-reaction trust failure: `After a bee sting, the patient developed anaphylaxis...` ranked `C0413120` Bee sting first instead of the acute reaction diagnosis.
- Benchmark result: Before the fix, the SQI-2026-06-11-015 rotating gate had 1 wrong-first row, `paragraph_43`, and the full clinical rerun had 2 wrong-first rows: WFN-009 and WFN-012. After the fix, the focused live probe ranked `C0002792` anaphylaxis first with `reaction_diagnosis_component` 0.62, while direct `bee sting` search still ranked Bee sting first and gave no reaction-diagnosis boost. The SQI-2026-06-11-016 rotating gate passed with 46/50 rows complete at top 10, 46/50 strict top 10, 50/50 strict top 20, 50/50 top-on-target, and 0 wrong-first rows. The comparable SQI-2026-06-11-011 rotating seed stayed at 0 wrong-first rows. The full clinical rerun passed gates with 844/874 expected concepts at top 10, 148/168 rows complete at top 10, 147/168 strict top 10, 167/168 top-on-target, and 1 wrong-first row.
- Recommended solution: Add a narrow reaction-diagnosis rank signal for a central reaction/condition span immediately following `developed` when the same sentence has an earlier `after` or `following` trigger clause, without demoting direct trigger lookups.
- Solution implemented: Added `reaction_diagnosis_component` to ranking, score breakdown, and confidence support; limited it to sentence-bounded condition hits whose local wording ties the developed reaction to an exposure trigger; and gave exact primary-name matches a larger component than alternate labels such as Anaphylactic shock. Added focused tests for the bee-sting/anaphylaxis wrong-first sentence and direct `bee sting` protection.
- Artifacts: `src/qe_evidence_vectors/search_ranking.py`; `tests/test_evidence_vectors.py`; `docs/search_rule_inventory.md`; `config/search_quality_wrong_first_noise_ledger.tsv`; `docs/search_quality_wrong_first_noise_ledger.md`; `improvements/2026-06-11_reaction_diagnosis_over_trigger_exposure.md`; `docs/search_quality_progress_log.html`; `docs/search_quality_experiments.html`; `build/search_quality_verification/SQI-2026-06-11-016.md`.
- Test evidence: Focused tests passed with 4 tests; focused ranker slice passed with 8 tests; py_compile passed; focused live API probe ranked anaphylaxis first with `reaction_diagnosis_component` 0.62; direct `bee sting` search still ranked Bee sting first with no reaction-diagnosis boost; the SQI-2026-06-11-016 smoke helper passed static, focused, standing clinical, rotating 50-query, and patient-portal gates; the comparable SQI-2026-06-11-011 rotating seed check passed with 0 wrong-first rows; the full 168-row clinical benchmark rerun passed release gates.
- Implementation status: Keep. This closes WFN-009 and leaves only WFN-012 open in the current wrong-first ledger.
- Remaining action: Fix WFN-012, confirmed pulmonary embolism over presenting chest-pain symptom in search-style wording. Keep WFN-001, WFN-008, WFN-009, WFN-010, WFN-011, and the protected yes/no/CYP2C19 rows in regression coverage.

### SQI-2026-06-11-015: Active diagnosis over following lab result

- Date: 2026-06-11
- Status: shipped
- Types: `ranking`
- Weakness found: WFN-011 showed an active diagnosis sentence where `A toddler with pica had lead poisoning after an elevated blood lead level` ranked the abnormal blood-lead-result concept first instead of the stated poisoning diagnosis.
- Benchmark result: Before the fix, the SQI-2026-06-11-014 rotating gate still had 2 wrong-first rows, including `paragraph_91`, and the full clinical rerun had 3 wrong-first rows: WFN-009, WFN-011, and WFN-012. After the fix, the focused live probe ranked `C0023176` Lead Poisoning first with `active_diagnosis_component` 0.14, while a direct `elevated blood lead level` query did not boost Lead Poisoning. The SQI-2026-06-11-015 rotating gate passed with 46/50 rows complete at top 10, 45/50 strict top 10, 49/50 strict top 20, 49/50 top-on-target, and 1 wrong-first row. The comparable SQI-2026-06-11-011 rotating seed stayed at 0 wrong-first rows. The full clinical rerun passed gates with 844/874 expected concepts at top 10, 148/168 rows complete at top 10, 146/168 strict top 10, 166/168 top-on-target, and 2 wrong-first rows.
- Recommended solution: Add a narrow active-diagnosis rank signal for assertable disease concepts whose span is immediately preceded by `had`, `has`, `have`, or `having` and immediately followed by `after` or `following`, without boosting standalone lab-result searches.
- Solution implemented: Added `active_diagnosis_component` to ranking, score breakdown, and confidence support; limited it to sentence-bounded multi-token assertable diagnosis hits outside comparator arms; and added focused tests covering the lead-poisoning wrong-first sentence plus the direct blood-lead lab-intent protection query.
- Artifacts: `src/qe_evidence_vectors/search_ranking.py`; `tests/test_evidence_vectors.py`; `docs/search_rule_inventory.md`; `config/search_quality_wrong_first_noise_ledger.tsv`; `docs/search_quality_wrong_first_noise_ledger.md`; `improvements/2026-06-11_active_diagnosis_over_following_lab_result.md`; `docs/search_quality_progress_log.html`; `docs/search_quality_experiments.html`; `build/search_quality_verification/SQI-2026-06-11-015.md`.
- Test evidence: Focused tests passed with 3 tests; focused ranker slice passed with 9 tests; py_compile passed; focused live API probe ranked Lead Poisoning first with `active_diagnosis_component` 0.14; direct `elevated blood lead level` search kept Lead Poisoning from receiving the active-diagnosis boost; the SQI-2026-06-11-015 smoke helper passed static, focused, standing clinical, rotating 50-query, and patient-portal gates; the comparable SQI-2026-06-11-011 rotating seed check passed with 0 wrong-first rows; the full 168-row clinical benchmark rerun passed release gates.
- Implementation status: Keep. This closes WFN-011 and reduces current wrong-first counts, but WFN-009 and WFN-012 remain open.
- Remaining action: Fix WFN-009 first, reaction diagnosis over trigger wording, then WFN-012 for confirmed pulmonary embolism over presenting symptom. Keep WFN-001, WFN-008, WFN-010, WFN-011, and the protected yes/no/CYP2C19 rows in regression coverage.

### SQI-2026-06-11-014: Asserted diagnosis over symptom/test noise

- Date: 2026-06-11
- Status: shipped
- Types: `ranking`
- Weakness found: WFN-008/WFN-010 showed the same trust failure in the current rotating sample and full clinical run: suspected thyrotoxicosis ranked below heat intolerance/suppressed TSH, and genetically confirmed cystic fibrosis ranked below chronic cough.
- Benchmark result: Before the fix, the SQI-2026-06-11-013 rotating gate had 41/50 strict top 10, 47/50 strict top 20, 48/50 top-on-target, and 2 wrong-first rows; the full clinical rerun had 844/874 expected concepts at top 10, 148/168 rows complete at top 10, 143/168 strict top 10, 163/168 top-on-target, and 5 wrong-first rows. After the fix, focused live probes ranked `C0040156` Thyrotoxicosis and `C0010674` Cystic Fibrosis first. The SQI-2026-06-11-014 rotating gate passed with 46/50 rows complete at top 10, 44/50 strict top 10, 48/50 strict top 20, 48/50 top-on-target, and 2 wrong-first rows. The comparable SQI-2026-06-11-011 rotating seed stayed at 0 wrong-first rows. The full clinical rerun passed gates with 844/874 expected concepts at top 10, 148/168 rows complete at top 10, 145/168 strict top 10, 165/168 top-on-target, and 3 wrong-first rows.
- Recommended solution: Add a narrow asserted-diagnosis rank signal for disease concepts whose query span is tied to same-sentence `suspected` or `confirmed` wording, including candidates whose matched span includes the cue itself, without boosting direct test-intent searches.
- Solution implemented: Added `asserted_diagnosis_component` to ranking, score breakdown, and confidence support; limited it to assertable disease semantic types; added a semantic-context exemption for asserted diagnosis hits so nearby lab/test wording does not demote them; added focused tests for suspected thyrotoxicosis, confirmed cystic fibrosis, the gestational diabetes protected row, and direct cystic-fibrosis testing intent.
- Artifacts: `src/qe_evidence_vectors/search_ranking.py`; `tests/test_evidence_vectors.py`; `docs/search_rule_inventory.md`; `config/search_quality_wrong_first_noise_ledger.tsv`; `docs/search_quality_wrong_first_noise_ledger.md`; `improvements/2026-06-11_asserted_diagnosis_over_symptom_test_noise.md`; `docs/search_quality_progress_log.html`; `docs/search_quality_experiments.html`; `build/search_quality_verification/SQI-2026-06-11-014.md`.
- Test evidence: Focused tests passed with 2 tests; focused ranker slice passed with 8 tests; py_compile passed; focused live API probes ranked Thyrotoxicosis first with `asserted_diagnosis_component` 0.38 and Cystic Fibrosis first with `asserted_diagnosis_component` 0.40; direct cystic-fibrosis testing query still ranked `C0428295` Cystic fibrosis sweat test first and gave Cystic Fibrosis no asserted-diagnosis boost; the SQI-2026-06-11-014 smoke helper passed static, focused, standing clinical, rotating 50-query, and patient-portal gates; the comparable SQI-2026-06-11-011 rotating seed check passed with 0 wrong-first rows; the full 168-row clinical benchmark rerun passed release gates.
- Implementation status: Keep. This closes WFN-008/WFN-010 and improves broad wrong-first counts, but no further score increase is warranted beyond returning the product estimate to 68% because WFN-009/WFN-011/WFN-012 remain open.
- Remaining action: Start with WFN-011, diagnosis over abnormal lab-result wording, then WFN-009/WFN-012 for reaction/confirmed condition over trigger or presenting symptom. Keep WFN-001, WFN-008, WFN-010, and the protected yes/no/CYP2C19 rows in regression coverage.

### SQI-2026-06-11-013: Diagnosis statement over test result

- Date: 2026-06-11
- Status: shipped
- Types: `ranking`
- Weakness found: WFN-001/WFN-005 showed the same trust failure in two artifacts: `Gestational diabetes was diagnosed after an abnormal oral glucose tolerance test` ranked a test/result concept first instead of the explicitly diagnosed condition.
- Benchmark result: Baseline SQI-2026-06-11-011 rotating smoke had `paragraph_111` wrong-first with `C1847425` Abnormal oral glucose tolerance first; the older full clinical rerun had `C0017741` Glucose tolerance test first. After the fix, the focused live probe ranked `C0085207` Gestational Diabetes first. The comparable SQI-2026-06-11-011 rotating seed check moved to 42/50 strict success at top 10, 49/50 at top 20, 50/50 top-on-target, and 0 wrong-first rows. The formal SQI-2026-06-11-013 rotating gate on a new sample passed but showed 41/50 strict top 10, 47/50 top 20, 48/50 top-on-target, and 2 wrong-first rows. The current full clinical rerun passed gates with 844/874 expected concepts at top 10, 148/168 rows complete at top 10, 143/168 strict success at top 10, 163/168 top-on-target, and 5 wrong-first rows.
- Recommended solution: Add a narrow diagnosis-statement rank signal for central disease/condition concepts whose query span is the object of wording such as `X was diagnosed` or `diagnosis of X`, without suppressing the supporting test/result concepts or direct test-intent searches.
- Solution implemented: Added `diagnosis_statement_component` to ranking, surfaced it in score breakdown and confidence support, and limited it to central multi-token condition hits tied to diagnosis wording. Added focused tests for the gestational diabetes wrong-first sentence and the direct oral glucose tolerance test protection query.
- Artifacts: `src/qe_evidence_vectors/search_ranking.py`; `tests/test_evidence_vectors.py`; `docs/search_rule_inventory.md`; `config/search_quality_wrong_first_noise_ledger.tsv`; `docs/search_quality_wrong_first_noise_ledger.md`; `improvements/2026-06-11_diagnosis_statement_over_test_result.md`; `docs/search_quality_progress_log.html`; `docs/search_quality_experiments.html`; `build/search_quality_verification/SQI-2026-06-11-013.md`.
- Test evidence: Focused tests passed with 2 tests; focused ranker slice passed with 6 tests; py_compile passed; focused live API probe ranked Gestational Diabetes first with `diagnosis_statement_component` 0.16; the SQI-2026-06-11-013 smoke helper passed static, focused, standing clinical, rotating 50-query, and patient-portal gates; the comparable SQI-2026-06-11-011 rotating seed check passed and had 0 wrong-first rows; the full 168-row clinical benchmark rerun passed release gates.
- Implementation status: Keep. This closes WFN-001/WFN-005 without hiding tests, but no product score increase is warranted because the latest new rotating sample and full clinical rerun still expose current wrong-first rows.
- Remaining action: Start with WFN-008/WFN-010, the suspected-or-confirmed diagnosis over symptom/test class, then re-run the current rotating sample, the comparable SQI-2026-06-11-011 seed, patient portal, and the full clinical benchmark.

### SQI-2026-06-11-012: Wrong-first noise ledger seed

- Date: 2026-06-11
- Status: shipped
- Types: `audit`, `process`
- Weakness found: The progress log's P0 task asked for a compact wrong-first/noise ledger, but the remaining failures still lived in scattered benchmark prose and row artifacts. The next ranking fix needed exact expected top concepts, actual bad concepts, source paths, cause classes, fix classes, and regression queries.
- Benchmark result: Not a benchmark run. The latest rotating gate stayed at 42/50 strict success at top 10, 48/50 at top 20, 49/50 top-on-target, and 1 wrong-first row; the latest full clinical benchmark stayed at 151/168 with 4 wrong-first rows.
- Recommended solution: Seed a reviewed ledger from the latest rotating wrong-first row and the full clinical benchmark's 4 wrong-first rows, then include closed protected rows for the cardiology related-panel yes/no leak and the CYP2C19/clopidogrel pharmacogenomic wrong-first fix.
- Solution implemented: Added a machine-readable TSV and readable audit summary that capture expected top concept, actual bad concept, source artifact path, cause, fix class, regression query, gate, and status. The open rows now group into three reusable classes: diagnosis over test/result, active diagnosis over anatomy, and supported/suspected diagnosis over lab measurement.
- Artifacts: `config/search_quality_wrong_first_noise_ledger.tsv`; `docs/search_quality_wrong_first_noise_ledger.md`; `improvements/2026-06-11_wrong_first_noise_ledger_seed.md`; `docs/search_quality_progress_log.html`; `docs/search_quality_iterations.html`.
- Test evidence: TSV schema check passed for 7 ledger rows; HTML parser checks passed for `docs/search_quality_progress_log.html`, `docs/search_quality_iterations.html`, and `docs/search_quality_experiments.html`; inline JavaScript syntax check passed for `docs/search_quality_iterations.html`.
- Implementation status: Keep. This creates the source-of-truth worklist for the remaining wrong-first fixes without changing ranking behavior.
- Remaining action: Start with WFN-001/WFN-005, the shared gestational-diabetes diagnosis-over-test-result class, then rerun the rotating smoke and full clinical benchmark to confirm the ledger rows close without regressing the protected yes/no and CYP2C19 rows.

### SQI-2026-06-11-011: Related yes/no answer-value suppression

- Date: 2026-06-11
- Status: shipped
- Types: `ranking`, `ui`
- Weakness found: The progress log still called out a trust issue where cardiology queries about ST elevation, RCA occlusion, and PCI could surface a related-panel value concept labeled `no`. Ranked results and semantic views had partial protection, but raw MRREL/research relations and related-bucket construction still needed a source-level guard.
- Benchmark result: Focused cardiology API probes on `http://127.0.0.1:8766` returned 0 standalone `yes`/`no` leaks across hit relations, semantic views, group views, and related buckets. The formal smoke helper passed; the latest rotating 50-query gate produced 42/50 strict success at top 10, 48/50 at top 20, 49/50 top-on-target, and 1 wrong-first result.
- Recommended solution: Suppress only standalone normalized relation labels `yes` and `no` in raw MRREL related concepts, research relations, and related result buckets. Preserve longer clinical concepts such as `No vomiting` and direct ranked searches for `yes` or `no`.
- Solution implemented: Added a shared yes/no relation-value filter in related-concept and research-relation merge paths, added the same guard to semantic related-bucket visibility, and added focused tests for ranked yes/no preservation plus relation-output suppression.
- Artifacts: `src/qe_evidence_vectors/search_related.py`; `src/qe_evidence_vectors/search_semantic_buckets.py`; `tests/test_evidence_vectors.py`; `docs/search_rule_inventory.md`; `improvements/2026-06-11_related_yes_no_answer_value_suppression.md`; `docs/search_quality_progress_log.html`; `docs/search_quality_experiments.html`; `build/search_quality_verification/SQI-2026-06-11-011.md`.
- Test evidence: `python3 -m py_compile src/qe_evidence_vectors/search_related.py src/qe_evidence_vectors/search_semantic_buckets.py tests/test_evidence_vectors.py` passed; focused tests passed with 2 tests; `python3 scripts/build_search_rule_inventory.py` regenerated the inventory; live cardiology related-output probes found 0 standalone `yes`/`no` leaks; the SQI-2026-06-11-011 smoke helper passed static, focused, standing clinical, rotating 50-query, and patient-portal gates.
- Implementation status: Keep. This closes the known related-panel answer-value leak without hiding useful negated clinical labels or direct yes/no searches.
- Remaining action: Continue the P0 wrong-first/noise ledger for the remaining rotating wrong-first row and the full clinical benchmark's 4 wrong-first examples; rerun/classify the broader 13-row approved PubMed suite.

### SQI-2026-06-11-010: PubMed pharmacogenomic response top result

- Date: 2026-06-11
- Status: shipped
- Types: `ranking`, `long-document`
- Weakness found: The focused PubMed CYP2C19/clopidogrel row had every expected CUI at top 10 but still counted as mixed because incidental aspirin ranked first over the explicit pharmacogenomic target and treatment-response concepts.
- Benchmark result: Focused PubMed long-document lane improved from 6 good / 1 mixed row to 7 good / 0 mixed rows, kept 36/36 expected concepts at top 10 and top 20, kept 7/7 rows complete at top 10, moved top-on-target to 7/7, kept wrong-first at 0, and reached overall score 100.0 on the focused slice.
- Recommended solution: Add sentence-bounded pharmacogenomic-response ranking support for directly mentioned CYP/gene, metabolizer/response, and local drug spans when the query has pharmacogenomic response context, without letting a background co-therapy drug inherit context from the next sentence.
- Solution implemented: Added a pharmacogenomic response score component to the ranker, exposed it in score breakdown/confidence support, bounded local context by sentence around the matched span, and added regression tests proving CYP2C19/clopidogrel context beats aspirin while ordinary drug queries do not get the boost.
- Artifacts: `src/qe_evidence_vectors/search_ranking.py`; `tests/test_evidence_vectors.py`; `docs/search_rule_inventory.md`; `improvements/2026-06-11_pubmed_pharmacogenomic_response_top_result.md`; `docs/search_quality_progress_log.html`; `docs/search_quality_experiments.html`; `build/search_quality_experiments/runs/20260611T161508Z_sqi-2026-06-11-010-pubmed-pharmacogenomic-response-top-result-fu`; `build/search_quality_verification/SQI-2026-06-11-010.md`.
- Test evidence: Focused pharmacogenomic tests passed; `python3 -m pytest tests/test_evidence_vectors.py -k "pharmacogenomic or treatment_drug or long_document" -q` passed with 26 tests; `python3 -m py_compile src/qe_evidence_vectors/search_ranking.py scripts/run_search_quality_experiment.py scripts/search_quality_server.py` passed; `python3 scripts/build_search_rule_inventory.py` regenerated the inventory; the focused live PubMed run on `http://127.0.0.1:8766` produced 7/7 good rows, 36/36 expected concepts at top 10 and top 20, and 0 mixed rows; the iteration smoke helper passed focused, standing clinical, rotating 50-query, and patient-portal gates.
- Implementation status: Keep. This closes the focused CYP2C19 wrong-first/mixed row with a reusable context rule, not a CUI-specific aspirin demotion.
- Remaining action: Rerun and classify the broader 13-row approved PubMed long-document suite, and continue the P0 wrong-first/noise ledger with CYP2C19 kept as a protected regression row.

### SQI-2026-06-11-009: PubMed curated lab and condition recall

- Date: 2026-06-11
- Status: shipped
- Types: `ranking`, `data`, `long-document`
- Weakness found: The focused PubMed lupus/preeclampsia row still missed `C0009506` Complement 3 at top 10 even though the paragraph explicitly says `normal C3 and C4 complement levels`. The reviewed active-label row marked `complement C3` as `lab`, but that local field was not preserved for the UMLS `Immunologic Factor` semantic type, so semantic-context ranking treated it like a gene/protein. A loader-only candidate moved Complement 3 to rank 11 but displaced `C0024141` Systemic lupus erythematosus from the first page.
- Benchmark result: Focused PubMed long-document recall improved from 35/36 to 36/36 expected concepts at top 10, from 35/36 to 36/36 at top 20, stayed 36/36 at top 60, moved all-expected-at-10 rows from 6/7 to 7/7, moved strict success at top 10 from 5/7 to 6/7, improved good rows from 5/7 to 6/7, and kept known false positives at 0.
- Recommended solution: Preserve reviewed active-label local fields for UMLS semantic types outside the local-extension map, use `lab` local fields for semantic-context role assignment, and add a bounded curated-exact long-document recall pass for active-label supported lab and high-support condition mentions.
- Solution implemented: Preserved active-label semantic rows with `local_field`, made curated active-label `lab` hits rank as `observation_lab`, added a curated-exact long-document first-page recall pass, added focused positive and protection tests, and regenerated the rule inventory.
- Artifacts: `src/qe_evidence_vectors/search_service.py`; `src/qe_evidence_vectors/search_ranking.py`; `tests/test_evidence_vectors.py`; `docs/search_rule_inventory.md`; `improvements/2026-06-11_pubmed_curated_lab_condition_recall.md`; `docs/search_quality_progress_log.html`; `docs/search_quality_experiments.html`; `build/search_quality_experiments/runs/SQI-2026-06-11-009_pubmed_curated_lab_condition_recall_final_8766_sqi-2026-06-11-009-pubmed-curated-lab-condition-recall-final-876`; `build/search_quality_verification/SQI-2026-06-11-009.md`.
- Test evidence: Focused unit tests for active-label local-field preservation, lab-role ranking, unreviewed immunologic-factor protection, and curated lab/condition first-page recall passed; py_compile passed; active-label supplement validation passed; `python3 scripts/build_search_rule_inventory.py` regenerated the inventory; focused live PubMed long-document run on `http://127.0.0.1:8766` moved Complement 3 to rank 4 and SLE to rank 5 in the lupus row; the iteration smoke helper passed static, focused, standing clinical, rotating 50-query, and patient-portal gates.
- Implementation status: Keep. This fixes a reusable metadata/ranking class without a CUI-specific boost and without accepting a weaker SLE substitution.
- Remaining action: The focused 7-row PubMed lane now has no missing expected concepts at top 10. The CYP2C19 wrong-first/mixed row was closed by SQI-2026-06-11-010; rerun the broader 13-row approved PubMed long-document suite.

### SQI-2026-06-11-008: Structured clinical context bucket prototype

- Date: 2026-06-11
- Status: shipped
- Types: `ui`, `process`
- Weakness found: The search UI grouped concepts by semantic type, but the supplied long stroke note contained role-level structure that the interface did not show: chief concern, active assessment, exam finding, objective data, plan, warning signs, copied-forward old history, repeated handoff text, and follow-up needs.
- Benchmark result: Not a benchmark run; UI/prospectus iteration.
- Recommended solution: Define the first clinical role buckets in a prospectus and add a compact interface prototype that displays bucketed snippets and linked CUI chips below the ranked search results.
- Solution implemented: Added the structured clinical context bucket prospectus and added a client-side Clinical Context panel below the ranked results in the local search UI. The prototype uses section cues and linked concept spans to show chief concern, active assessment, exam/finding, objective-data, plan/treatment, watch-for, older-history, handoff/documentation, and follow-up buckets.
- Artifacts: `docs/structured_clinical_context_buckets_prospectus.md`; `docs/search_quality/app.js`; `docs/search_quality/server.css`; `docs/search_quality_server.html`; `docs/search_quality_iterations.md`; `docs/search_quality_iterations.html`.
- Test evidence: JavaScript syntax check and live/static server smoke for the search UI.
- Implementation status: Keep as a prototype. This is intentionally client-side cueing until the API returns first-class `clinical_context` bucket annotations.
- Remaining action: Promote the supplied stroke note into a structured-context fixture when the API data contract is implemented, then evaluate bucket accuracy separately from CUI recall.

### SQI-2026-06-11-007: PubMed migraine with-or-without-aura aggregate alternative

- Date: 2026-06-11
- Status: shipped
- Types: `benchmark`, `data`, `long-document`
- Weakness found: The focused PubMed status migrainosus row still counted `C0154723` Migraine with Aura and `C0338480` Common Migraine as top-10 misses even though the abstract explicitly says `migraine with or without aura` and the exact aggregate concept `C3808875` was recoverable lower in the result set.
- Benchmark result: Focused PubMed long-document recall improved from 33/36 to 35/36 expected concepts at top 10, stayed 35/36 at top 20 and 36/36 at top 60, moved all-expected-at-10 rows from 5/7 to 6/7, moved strict success at top 10 from 4/7 to 5/7, improved good rows from 4/7 to 5/7, and kept known false positives at 0.
- Recommended solution: Keep the fix specific to the exact aggregate concept named by the abstract: make `C3808875` first-page visible with active-label evidence and count it as a reviewed acceptable alternative for both aura subtype expectations when the phrase is explicit.
- Solution implemented: Added `C0154723 -> C3808875` and `C0338480 -> C3808875` to `config/search_quality_acceptable_cui_alternatives.tsv`, added an active-label supplement row for `migraine with or without aura`, added a focused evaluator regression test for the aggregate alternative, and regenerated the rule inventory.
- Artifacts: `config/search_quality_acceptable_cui_alternatives.tsv`; `config/active_label_supplement.tsv`; `tests/test_evidence_vectors.py`; `docs/search_rule_inventory.md`; `improvements/2026-06-11_pubmed_migraine_with_or_without_aura_alternative.md`; `docs/search_quality_progress_log.html`; `docs/search_quality_experiments.html`; `build/search_quality_experiments/runs/SQI-2026-06-11-007_pubmed_current_baseline_sqi-2026-06-11-007-pubmed-focused-current-baseline`; `build/search_quality_experiments/runs/SQI-2026-06-11-007_pubmed_migraine_with_or_without_aura_final_8766_sqi-2026-06-11-007-pubmed-migraine-aggregate-final-8766`; `build/search_quality_verification/SQI-2026-06-11-007.md`.
- Test evidence: Active-label supplement validation passed; py_compile passed; focused migraine aggregate evaluator and with-or-without phrase tests passed; `python3 scripts/build_search_rule_inventory.py` regenerated the inventory; focused live PubMed long-document run moved `C3808875` to rank 7 and counted accepted alternatives `C0154723=C3808875|C0338480=C3808875`; the iteration smoke helper passed static, focused, standing clinical, rotating 50-query, and patient-portal gates.
- Implementation status: Keep. This corrects the exact-phrase aggregate case without accepting a broad migraine-disorder fallback and without adding a CUI-specific runtime rank boost.
- Remaining action: The remaining focused PubMed work was closed by SQI-2026-06-11-009 and SQI-2026-06-11-010. Rerun the 13-row approved PubMed long-document suite after the focused lane improvements.

### SQI-2026-06-11-006: PubMed antibiotic-associated diarrhea acceptable alternative

- Date: 2026-06-11
- Status: shipped
- Types: `benchmark`, `long-document`
- Weakness found: The focused PubMed C. difficile review row still counted `C0011991` Diarrhea as a top-10 miss even though first-page result `C0578159` Antibiotic-associated diarrhea was present for wording that explicitly links diarrhea to antibiotic exposure and C. difficile infection.
- Benchmark result: Focused PubMed long-document recall improved from 32/36 to 33/36 expected concepts at top 10, stayed 35/36 at top 20 and 36/36 at top 60, moved all-expected-at-10 rows from 4/7 to 5/7, moved strict success at top 10 from 3/7 to 4/7, and kept known false positives at 0.
- Recommended solution: Treat antibiotic-associated diarrhea as a reviewed acceptable alternative for the broader diarrhea symptom target in antibiotic/C. difficile wording, rather than adding a single-token symptom rank boost.
- Solution implemented: Added `C0011991 -> C0578159` to `config/search_quality_acceptable_cui_alternatives.tsv`, added a focused evaluator regression test for the checked-in row, and regenerated the rule inventory.
- Artifacts: `config/search_quality_acceptable_cui_alternatives.tsv`; `tests/test_evidence_vectors.py`; `docs/search_rule_inventory.md`; `improvements/2026-06-11_pubmed_antibiotic_diarrhea_alternative.md`; `docs/search_quality_progress_log.html`; `docs/search_quality_experiments.html`; `build/search_quality_experiments/runs/SQI-2026-06-11-006_pubmed_current_baseline_sqi-2026-06-11-006-pubmed-focused-current-baseline`; `build/search_quality_experiments/runs/SQI-2026-06-11-006_pubmed_antibiotic_diarrhea_alternative_sqi-2026-06-11-006-pubmed-antibiotic-diarrhea-acceptable-alterna`; `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-11-006/verification.md`.
- Test evidence: Focused acceptable-alternative evaluator tests passed; py_compile passed; `python3 scripts/build_search_rule_inventory.py` regenerated the inventory; focused live PubMed long-document run on the full PubMed/PMC-backed server improved to 33/36 top-10 expected concepts with accepted alternative `C0011991=C0578159`; the iteration smoke helper passed static, focused, standing clinical, rotating 50-query, and patient-portal gates.
- Implementation status: Keep. This corrects the benchmark hierarchy for a clinically acceptable first-page specific diarrhea concept without adding a ranker rule.
- Remaining action: Continue the remaining focused PubMed misses (`C0154723`, `C0338480`, and `C0009506`) and rerun the 13-row approved PubMed long-document suite after the focused lane improves further.

### SQI-2026-06-11-005: PubMed osimertinib dose-form acceptable alternative

- Date: 2026-06-11
- Status: shipped
- Types: `benchmark`, `long-document`
- Weakness found: The focused PubMed long-document EGFR/NSCLC row stayed mixed because expected ingredient `C4058811` Osimertinib was outside the first page, even though the first page already contained dose-specific `C4058829` osimertinib 80 MG from explicit osimertinib wording.
- Benchmark result: Focused PubMed long-document recall improved from 31/36 to 32/36 expected concepts at top 10, stayed 35/36 at top 20 and 36/36 at top 60, improved good rows from 3/7 to 4/7, improved expected semantic group recall from 88.9% to 94.4%, and kept known false positives at 0.
- Recommended solution: Treat the dose-specific osimertinib RxNorm product as a reviewed acceptable alternative for the ingredient target in oncology paragraphs that explicitly name osimertinib, instead of adding a runtime CUI-specific boost.
- Solution implemented: Added `C4058811 -> C4058829` to `config/search_quality_acceptable_cui_alternatives.tsv`, added a focused evaluator regression test for the checked-in row, rejected a runtime ranking diagnostic that did not move the metric, and regenerated the rule inventory.
- Artifacts: `config/search_quality_acceptable_cui_alternatives.tsv`; `tests/test_evidence_vectors.py`; `docs/search_rule_inventory.md`; `improvements/2026-06-11_pubmed_osimertinib_dose_form_alternative.md`; `docs/search_quality_progress_log.html`; `docs/search_quality_experiments.html`; `build/search_quality_experiments/runs/SQI-2026-06-11-005_pubmed_current_baseline_sqi-2026-06-11-005-pubmed-focused-current-baseline`; `build/search_quality_experiments/runs/SQI-2026-06-11-005_pubmed_osimertinib_dose_form_alternative_sqi-2026-06-11-005-pubmed-osimertinib-dose-form-acceptable-alter`; `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-11-005/verification.md`.
- Test evidence: Focused acceptable-alternative evaluator tests passed; py_compile passed; `python3 scripts/build_search_rule_inventory.py` regenerated the inventory; focused live PubMed long-document run on the full PubMed/PMC-backed server improved to 32/36 top-10 expected concepts with accepted alternative `C4058811=C4058829`; the iteration smoke helper passed static, focused, standing clinical, rotating 50-query, and patient-portal gates.
- Implementation status: Keep. This corrects the benchmark judgment for a clinically acceptable first-page dose-form hit without adding a ranker rule.
- Remaining action: Continue the remaining focused PubMed misses (`C0154723`, `C0338480`, `C0011991`, and `C0009506`) and rerun the 13-row approved PubMed long-document suite after the focused lane improves further.

### SQI-2026-06-11-004: PubMed long-document post-rerank recall preservation

- Date: 2026-06-11
- Status: shipped
- Types: `ranking`, `long-document`
- Weakness found: The current 7-row PubMed long-document focused slice had fallen to 28/36 expected concepts at top 10, with explicitly mentioned secondary concepts such as `Progression-Free Survival`, `Antibiotic-associated diarrhea`, and systemic lupus stuck just outside the first page after post-merge reranking.
- Benchmark result: Focused PubMed long-document recall improved from 28/36 to 31/36 expected concepts at top 10, from 33/36 to 35/36 at top 20, and stayed 36/36 at top 60. Good rows improved from 2/7 to 3/7, expected semantic group recall at top 10 improved from 83.3% to 88.9%, and known false positives stayed 0 at top 10 and top 20.
- Recommended solution: Preserve bounded long-document first-page recall after the linked-label post-rerank step, while preventing promoted candidates from replacing stronger high-support central concepts already in the first page.
- Solution implemented: Added a post-rerank long-document recall preservation pass in both local and Elasticsearch API paths, tightened long-document replacement protection for high-support top-10 hits, suppressed educational/rank grade concepts (`School Grade`, `Grade three rank`) that leak from adverse-event grade prose, added focused regression tests, and regenerated the rule inventory.
- Artifacts: `src/qe_evidence_vectors/search_execution.py`; `src/qe_evidence_vectors/search_ranking.py`; `src/qe_evidence_vectors/generic_filters.py`; `tests/test_evidence_vectors.py`; `docs/search_rule_inventory.md`; `improvements/2026-06-11_pubmed_long_document_post_rerank_recall.md`; `docs/search_quality_progress_log.html`; `docs/search_quality_experiments.html`; `build/search_quality_experiments/runs/SQI-2026-06-11-004_pubmed_long_document_baseline_sqi-2026-06-11-004-pubmed-long-document-current-baseline`; `build/search_quality_experiments/runs/SQI-2026-06-11-004_pubmed_long_document_post_rerank_recall_sqi-2026-06-11-004-pubmed-long-document-post-rerank-recall-prese`; `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-11-004/verification.md`.
- Test evidence: Focused generic and long-document tests passed; py_compile passed; `python3 scripts/build_search_rule_inventory.py` regenerated the inventory; focused live PubMed long-document run on the full PubMed/PMC-backed server improved to 31/36 top-10 expected concepts; the iteration smoke helper passed static, focused, standing clinical, rotating 50-query, and patient-portal gates.
- Implementation status: Keep. This closes three focused top-10 misses without adding CUI-specific boosts and preserves patient-portal gates.
- Remaining action: Continue the remaining focused PubMed misses (`C0154723`, `C0338480`, `C4058811`, `C0011991`, and `C0009506`) and rerun the 13-row approved PubMed long-document suite after the focused lane improves further.

### SQI-2026-06-11-003: Patient portal too-much generic suppression

- Date: 2026-06-11
- Status: shipped
- Types: `ranking`, `benchmark`
- Weakness found: The patient-portal suite still failed `found_at_10` by one concept: in `portal_02_hypoglycemia_old_diabetes`, expected `C0021641` Insulin was rank 11 while generic prose concept `C3843660` Too much occupied rank 8.
- Benchmark result: Patient-portal suite layer passed, moving expected concepts at top 10 from 73/88 to 74/88, keeping 12/12 top-on-target and 0 top-wrong, and moving Insulin into rank 10 for the hypoglycemia portal row. The rotating 50-query smoke also passed gates with 42/50 strict success at top 10, 48/50 at top 20, 50/50 top-on-target, and 0 top-wrong.
- Recommended solution: Treat standalone `too much` as the same audited generic/prose class as `too little`, while preserving longer clinical phrases such as `too much insulin`.
- Solution implemented: Added `too much` to `BLOCKED_GENERIC_LABELS`, added `C3843660` to `BLOCKED_GENERIC_CUIS`, added regression tests for the standalone concept and longer phrase, and regenerated the rule inventory.
- Artifacts: `src/qe_evidence_vectors/generic_filters.py`; `tests/test_evidence_vectors.py`; `docs/search_rule_inventory.md`; `improvements/2026-06-11_patient_portal_too_much_generic_suppression.md`; `docs/search_quality_progress_log.html`; `docs/search_quality_experiments.html`; `build/search_quality_experiments/runs/SQI-2026-06-11-003_patient_portal_sqi-2026-06-11-003-patient-portal-current-versus-history-lane`; `build/search_quality_suite/SQI-2026-06-11-003-full/suite.md`; `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-11-003/verification.md`.
- Test evidence: Generic-filter focused tests passed; py_compile passed; `python3 scripts/build_search_rule_inventory.py` regenerated the inventory; `python3 scripts/run_search_quality_suite.py --suite-id SQI-2026-06-11-003-full --base-url http://127.0.0.1:8791 --only patient_portal_intent --fail-on any` passed; the iteration smoke helper passed static, focused, standing clinical, rotating 50-query, and patient-portal smoke gates against the full PubMed/PMC-backed server profile.
- Implementation status: Keep. This closes the patient-portal `found_at_10` threshold without a CUI-specific boost and without blocking the full phrase `too much insulin`.
- Remaining action: Patient-portal gates now pass; future portal work should improve the remaining mixed rows toward more full-row top-10 completion without weakening current-intent ranking or source retention.

### SQI-2026-06-11-002: Progress log update requirement

- Date: 2026-06-11
- Status: shipped
- Types: `process`, `ui`
- Weakness found: A shipped iteration updated the iteration ledger and experiment archive but left `docs/search_quality_progress_log.html` describing the prior patient-portal failure as the latest current status.
- Benchmark result: Not a benchmark run; process/report correction.
- Recommended solution: The iteration contract should make the readable progress log a required artifact whenever headline status, latest-result cards, open work, or chronology changes.
- Solution implemented: Added an explicit progress-log update requirement to the sustainable-improvements workflow and this iteration contract, and updated the progress log to reflect `SQI-2026-06-11-001`.
- Artifacts: `docs/search_quality_sustainable_improvements.md`; `docs/search_quality_iterations.md`; `docs/search_quality_iterations.html`; `docs/search_quality_progress_log.html`.
- Test evidence: Static artifact review plus inline JavaScript syntax check for `docs/search_quality_iterations.html`.
- Implementation status: Keep. Future iterations cannot be called shipped while the readable progress log still presents the previous result as current.
- Remaining action: None for the process rule; enforce it on the next iteration.

### SQI-2026-06-11-001: Patient portal evidence-backed label fallback

- Date: 2026-06-11
- Status: shipped
- Types: `ranking`, `benchmark`
- Weakness found: The `patient_portal_intent` lane regressed to 11/12 top-on-target and lost expected PubMed/PMC source presence because evidence-backed hits for the same CUI could be replaced by higher-scoring pure UMLS label fallback hits.
- Recommended solution: For the same CUI, label fallback should improve labels and matched-span metadata without replacing an already evidence-backed hit or dropping its source mix.
- Benchmark result: Focused patient-portal rerun passed gates, restored top-on-target from 11/12 to 12/12, reduced top-wrong from 1 to 0, and restored top-10 source counts to `pmc_oa` 39, `pubmed_bulk` 60, and `pubmed` 6. The stricter suite layer still fails only `found_at_10` with 73 actual versus 74 expected.
- Solution implemented: Updated `SearchRerankMixin.merge_label_fallback` to preserve evidence-backed `umls_label` hits when pure label fallback for the same CUI has a higher fallback score, while still merging labels, source labels, matched-span metadata, and fallback score.
- Artifacts: `src/qe_evidence_vectors/search_rerank.py`; `tests/test_evidence_vectors.py`; `improvements/2026-06-11_patient_portal_evidence_backed_label_fallback.md`; `docs/search_quality_progress_log.html`; `docs/search_quality_experiments.html`; `build/search_quality_experiments/runs/SQI-2026-06-11-001_patient_portal_sqi-2026-06-11-001-patient-portal-evidence-backed-label-fallback/run.json`; `build/search_quality_suite/SQI-2026-06-11-001/suite.md`.
- Test evidence: `python3 -m pytest tests/test_evidence_vectors.py::test_label_fallback_preserves_evidence_backed_umls_label_sources -q` passed; `python3 -m pytest tests/test_evidence_vectors.py -k 'long_document' -q` passed with 15 tests; source-quality and suite threshold unit tests passed; py_compile passed; live patient-portal focused run on `http://127.0.0.1:8790` passed gates; named suite layer records the remaining `found_at_10` threshold gap.
- Implementation status: Keep. This closes the PubMed/PMC source-retention failure without adding a CUI-specific rule.
- Remaining action: Open a separate bounded patient-portal recall pass for the one missing top-10 expected concept needed to move `found_at_10` from 73 to 74, and continue the focused PubMed long-document misses separately.

### SQI-2026-06-10-025: PubMed first-page recall with broad-class cap

- Date: 2026-06-10
- Status: in_progress
- Types: `long-document`, `ranking`, `benchmark`
- Weakness found: The 7-row dev-only PubMed long-document focused slice had improved to 2/7 rows fully found at top 10, but only 27/36 expected concepts were present at top 10 and a broad corticosteroid class concept could outrank the specific expected migraine treatment stack.
- Recommended solution: Promote strongly supported long-document candidates into the first page only when they have direct label/context support, block low-specificity candidates, and cap long-document support for broad pharmacologic class labels so class concepts stay visible without becoming the top result by support alone.
- Benchmark result: Focused PubMed dev slice improved to 3/7 rows fully found at top 10, 30/36 expected concepts at top 10, 33/36 at top 20, 36/36 at top 60, 7/7 top-on-target, 0 top-wrong rows, and 0 known false positives at top 10.
- Solution implemented: Added a bounded first-page recall promotion after long-document diversity selection, added low-specificity and salient multi-token candidate guards, and capped long-document support for broad treatment-class concepts such as `Adrenal Cortex Hormones`.
- Artifacts: `src/qe_evidence_vectors/search_ranking.py`; `tests/test_evidence_vectors.py`; `docs/search_quality_experiments.html`; `build/search_quality_experiments/runs/SQI-2026-06-10-025_pubmed_long_document_first_page_recall_class_cap_sqi-2026-06-10-025-pubmed-long-document-first-page-recall-class-/paragraph_quality_report.md`; `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-10-025/verification.md`.
- Test evidence: `python3 -m pytest tests/test_evidence_vectors.py -k "long_document" -q` passed with 15 tests; the focused API PubMed run produced 3 good / 4 mixed rows with 0 known false positives. The full iteration smoke helper passed static, focused, standing clinical, and rotating 50-query smoke gates, but failed the patient-portal lane because `pmc_oa` and `pubmed_bulk` source counts collapsed against the selected baseline.
- Implementation status: Keep as a measured candidate. The patient-portal source-count blocker was closed by `SQI-2026-06-11-001`, but this long-document iteration still needs release-quality confirmation after the remaining focused PubMed misses are handled.
- Remaining action: Continue the focused PubMed misses: `C0338480`, `C0242792`, `C4058811`, `C0042313`, `C0009506`, and `C0024141`. Keep the separate patient-portal recall threshold follow-up scoped outside this PubMed iteration.

### SQI-2026-06-10-022: Test weakness ledger wording

- Date: 2026-06-10
- Status: shipped
- Types: `process`, `ui`
- Weakness found: The filterable iteration report looked like a backlog and did not make test findings, weaknesses, recommended solutions, or implementation status obvious.
- Recommended solution: The report should directly answer what each manual or Codex-run test found, what evidence exposed it, what solution is recommended, and whether that solution has shipped.
- Benchmark result: Report UI verification passed; this was a report-only fix, not a benchmark run.
- Solution implemented: Renamed the report to a test-and-weakness ledger, replaced backlog-style proposed/completed columns with one documented-finding list, relabeled each entry around weakness/test evidence/recommended solution/implementation status, and added visible benchmark-result/source pointers.
- Artifacts: `docs/search_quality_iterations.html`; `docs/search_quality_iterations.md`.
- Test evidence: Static HTML review and inline JavaScript syntax check.
- Implementation status: Keep.
- Remaining action: Future report changes should preserve the test/weakness framing and avoid presenting the ledger primarily as a backlog.

### SQI-2026-06-10-010: Post-iteration smoke requirement

- Date: 2026-06-10
- Status: shipped
- Types: `process`, `benchmark`
- Weakness found: Smoke testing was not consistently run after each ranking/runtime iteration.
- Recommended solution: Every future iteration should record the smoke decision, and runtime search-quality changes should run the standing smoke before being marked shipped.
- Solution implemented: Added a smoke rule to the iteration contract. Runtime search, source-code, ranking, benchmark-label, judgment, or API behavior changes now require the standing clinical API smoke; broad ranking/runtime or release-quality changes also require the 50-query rotating smoke with gates.
- Artifacts: `docs/search_quality_iterations.md`; `docs/search_quality_iterations.html`.
- Test evidence: Static artifact review. Latest live smoke baseline available from `build/search_quality_experiments/runs/20260610T175715Z_20260610t175715z/metrics.json`.
- Implementation status: Keep. This closes the process gap that allowed targeted tests to substitute for smoke checks.
- Remaining action: Closed by `SQI-2026-06-10-011`; future runtime/ranking iterations should use `--iteration-smoke-gates`.

### SQI-2026-06-10-017: Repeatable process report

- Date: 2026-06-10
- Status: shipped
- Types: `process`
- Weakness found: Repeatable build, serving, evaluation, benchmark, source-acquisition, audit, and reporting workflows were spread across several docs and script entrypoints.
- Recommended solution: A single report should point to each recurring process, the command that starts it, required inputs, expected outputs, and the verification check.
- Solution implemented: Added `docs/repeatable_processes.md` as the consolidated process index and updated the plain-English status doc to point to it.
- Artifacts: `docs/repeatable_processes.md`; `docs/explain_like_im_5.md`; `docs/search_quality_iterations.md`; `docs/search_quality_iterations.html`.
- Test evidence: Static markdown review and HTML inline-script syntax check. No live smoke was needed because this is a documentation/process-only change with no runtime, ranking, label, judgment, benchmark, or API behavior change.
- Implementation status: Keep.
- Remaining action: Keep the report updated whenever a repeatable workflow, canonical artifact, or verification rule changes.

### SQI-2026-06-10-018: Script organization map

- Date: 2026-06-10
- Status: shipped
- Types: `process`
- Weakness found: The `scripts/` directory was flat and hard to scan, but existing docs, tests, imports, and command snippets depend on stable `scripts/<name>.py` paths.
- Recommended solution: Scripts should be easier to navigate without breaking current references.
- Solution implemented: Added a top-level script index plus documentation-only category folders for pipeline, serving, search quality, benchmarks, sources/enrichment, and reports. The canonical executable entrypoints remain at their existing paths.
- Artifacts: `scripts/README.md`; `scripts/pipeline/README.md`; `scripts/serve/README.md`; `scripts/quality/README.md`; `scripts/benchmarks/README.md`; `scripts/sources/README.md`; `scripts/reports/README.md`; `docs/repeatable_processes.md`; `docs/explain_like_im_5.md`; `docs/search_quality_iterations.md`; `docs/search_quality_iterations.html`.
- Test evidence: Static markdown review, script-reference check, HTML inline-script syntax check, and `git diff --check`. No live smoke was needed because this is a documentation/process-only organization change with no runtime, ranking, label, judgment, benchmark, or API behavior change.
- Implementation status: Keep.
- Remaining action: If script implementations are physically moved later, leave compatibility wrappers at the old paths and test the old command paths.

### SQI-2026-06-10-019: Public source-code rows in public output

- Date: 2026-06-10
- Status: shipped
- Types: `source-code`, `ui`
- Weakness found: Return vocabulary searches returned no results for every selected vocabulary under `--public-output-only`, even though `/api/status` reported `build/cui_code_index.sqlite` with 9,112,359 code mappings.
- Recommended solution: Strict source-code row mode should return rows for public allowlisted vocabularies such as RxNorm and LOINC, while non-allowlisted vocabularies remain suppressed in public output mode.
- Solution implemented: The public-output scrubber treated the internal `source_code` marker as a non-public evidence source and dropped every strict vocabulary row. Added a strict source-code public-output path that preserves only allowlisted code rows, keeps source-code identifiers for those rows, and omits concept-hit mapping payloads. The UI now disables only non-allowlisted vocabulary options in public mode instead of forcing the selector to `none`.
- Artifacts: `src/qe_evidence_vectors/public_output.py`; `docs/search_quality/app.js`; `docs/api.md`; `tests/test_public_output.py`; `docs/search_quality_iterations.md`; `docs/search_quality_iterations.html`; `docs/search_quality_experiments.html`; `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-10-019/verification.md`.
- Test evidence: Restarted the public-output search API on port `8766`; live checks returned RxNorm rows for `metformin` and `RXNORM:6809`, LOINC rows for `LNC:4548-4`, and zero rows for non-allowlisted `ICD10CM:E11.9` and `SNOMEDCT_US:44054006`. The iteration smoke helper passed static checks, the targeted 14-test selector, and the standing clinical API smoke; artifacts are in `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-10-019/verification.md` and `.json`.
- Implementation status: Keep. Public output may expose strict source-code rows only for configured public vocabularies, but concept-hit mapping payloads remain scrubbed.
- Remaining action: If SNOMED CT or ICD-10-CM source-code rows are needed in public mode, make that an explicit allowlist/licensing decision instead of changing the default behavior.

### SQI-2026-06-10-020: TREC PM/CDS document-source benchmark lane

- Date: 2026-06-10
- Status: shipped
- Types: `benchmark`, `process`
- Weakness found: External benchmark coverage needed a TREC Precision Medicine or Clinical Decision Support lane like MedMentions, but scored on judged source documents rather than CUIs.
- Recommended solution: The lane should import topics and qrels, resolve judged PubMed and ClinicalTrials.gov IDs against local corpora, report corpus coverage first, and evaluate document/source retrieval separately from CUI retrieval. Judged `relevance > 0` rows are positives; unjudged returned documents are unknown, not false positives.
- Solution implemented: Added a TREC runner workflow that accepts repeated qrels files for abstract plus trial tasks, discovers local corpus artifacts by default, writes normalized topics/qrels/coverage outputs, emits all-judged-positive and resolved-local document-query TSVs, and reports retrieval summaries by source type. Imported NIST TREC 2019 Precision Medicine topics with abstract and trial qrels into `build/trec/precision_medicine_2019`.
- Artifacts: `scripts/run_trec_benchmark.py`; `tests/test_trec_benchmark.py`; `docs/trec_benchmark.md`; `docs/repeatable_processes.md`; `scripts/run_search_quality_experiment.py`; `docs/search_quality_experiments.html`; `build/trec/precision_medicine_2019/trec_precision_medicine_manifest.json`.
- Test evidence: `python3 -m pytest tests/test_trec_benchmark.py -q` passed with 7 tests; `python3 -m py_compile scripts/run_trec_benchmark.py`; official 2019 PM import produced 40 topics, 31,312 judgments, 7,729 judged positives, 511,844 local corpus records scanned, and 74 locally resolved judged positives. A public-output API evaluation of the resolved-local rows produced zero document/source hits because the running public API suppresses underlying PMID/NCT evidence identifiers. A follow-up non-public API run on port `8768` also completed against the 10 resolved-local topic rows and wrote `build/trec/precision_medicine_2019/eval_non_public_20260610/summary.json`; it still found 0/74 expected source documents at rank 10.
- Implementation status: Keep the TREC lane and close the non-public-rerun follow-up. The result shows the next problem is source-document identifier exposure or source-aware document retrieval, not only public-output scrubbing.
- Remaining action: If TREC document/source scoring is resumed, open a new implementation iteration for exposing PMID/NCT identifiers from evidence payloads or adding a source-document retrieval path before rerunning this lane.

### SQI-2026-06-10-021: Code-or-evidence promotion gate

- Date: 2026-06-10
- Status: shipped
- Types: `process`, `data`, `ranking`
- Weakness found: The improvement loop needed an explicit rule for choosing between code changes and evidence procurement, and for discarding failed evidence/code paths.
- Recommended solution: Every future search-quality iteration should name the weakness, choose either a code route or an evidence route, rerun the same benchmark slice, and promote only if the target improves without unacceptable regression.
- Solution implemented: Added a weakness-to-promotion gate to the repeatable process. Failed code changes must be reverted or removed. Failed evidence acquisitions must be rejected from the default/search-ranking path and recorded so the same source/query/scope is not reacquired without a new hypothesis.
- Artifacts: `docs/repeatable_processes.md`; `docs/search_quality_iterations.md`; `docs/search_quality_iterations.html`.
- Test evidence: Docs-only process change; checked Markdown/HTML consistency and inline JavaScript syntax.
- Implementation status: Keep. This makes evidence acquisition conditional on measured search improvement rather than general usefulness.
- Remaining action: Use this gate for the next concrete weakness before acquiring new evidence or merging ranking changes.

### SQI-2026-06-10-011: Automate post-iteration smoke gates

- Date: 2026-06-10
- Status: shipped
- Types: `process`, `benchmark`
- Weakness found: The smoke rule is documented, but still manual.
- Recommended solution: A single command should choose the right smoke tier for a changed iteration and write the verification summary into the report artifacts.
- Solution implemented: Added `--iteration-smoke-gates` to `scripts/run_search_quality_experiment.py`. The helper chooses static/focused checks, standing clinical API smoke, and 50-query rotating smoke with gates from iteration type plus explicit scope flags. It writes JSON and Markdown verification summaries and adds a Post-Iteration Smoke Gates panel to `docs/search_quality_experiments.html`.
- Artifacts: `scripts/run_search_quality_experiment.py`; `tests/test_search_quality_experiment_gates.py`; `docs/search_quality_experiments.html`; `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-10-011/verification.md`; `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-10-011/verification.json`; `build/search_quality_experiments/runs/SQI-2026-06-10-011_rotating_50_sqi-2026-06-10-011-automated-50-query-smoke/metrics.json`.
- Test evidence: `python3 -m py_compile scripts/run_search_quality_experiment.py`; `python3 -m pytest tests/test_search_quality_experiment_gates.py -q` passed with 10 tests; dry-run helper mode wrote planned summaries; live helper mode passed all selected steps against `http://127.0.0.1:8766`. Standing clinical smoke found every expected CUI in top 5; two expected hits remained rank 2. The 50-query rotating smoke passed gates: 44/50 strict success@10, 46/50 strict success@20, 47/50 top on target, 0 known false positives@10/@20, 45 good and 5 mixed.
- Implementation status: Keep.
- Remaining action: Use `--iteration-smoke-gates` for future iteration verification instead of hand-running smoke tiers.

### SQI-2026-06-10-012: Long-document section and chunk merge recall

- Date: 2026-06-10
- Status: shipped; follow-up needed
- Types: `long-document`, `ranking`, `benchmark`
- Weakness found: The focused PubMed long-document slice has all expected concepts at top 10 for only 1 of 7 rows.
- Recommended solution: Important secondary concepts from long abstracts should survive section/chunk linking, merge, and rerank into the first useful result window.
- Solution implemented: Added exact-label long-document support for repeated retrieved labels and tightened long-document diversity replacement so section/chunk-supported concepts can move up without promoting one-off single-token chemical noise. Confirmed focused slice improved recall@10 from 24/36 to 27/36, recall@20 from 30/36 to 34/36, recall@60 from 33/36 to 36/36, all-expected@10 from 1/7 to 2/7, all-expected@20 to 5/7, and kept known false positives at 0. A more aggressive top-10 window swap was tested and rejected after it regressed recall.
- Artifacts: `src/qe_evidence_vectors/search_rerank.py`; `src/qe_evidence_vectors/search_ranking.py`; `tests/test_evidence_vectors.py`; `config/search_quality_pubmed_long_document_slice.tsv`; `build/pubmed_literature_benchmark_seed/pubmed_long_document_focused_queries.tsv`; `build/search_quality_experiments/runs/SQI-2026-06-10-012_pubmed_long_document_focused_confirmed_sqi-2026-06-10-012-pubmed-long-document-focused-slice-confirmed/paragraph_quality_report.md`; `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-10-012-confirmed-all-gates/verification.md`.
- Test evidence: `python3 -m pytest tests/test_evidence_vectors.py -k "long_document" -q` passed with 12 tests in the final smoke helper; confirmed focused API slice produced 2 good / 5 mixed rows with 0 known false positives; `--iteration-smoke-gates --iteration-id SQI-2026-06-10-012-confirmed-all-gates --iteration-type long-document --iteration-type ranking` passed static, focused, standing clinical, rotating 50-query, and patient-portal smoke gates.
- Implementation status: Keep the narrow support/linking changes; do not treat P1 as closed.
- Remaining action: Continue on the remaining long-document misses, especially unretrieved `C0578159`, `C0003537`, `C0009506`, and low-ranked lupus/migraine condition variants, with the same focused slice as the gate.

### SQI-2026-06-10-013: Residual true false-positive cleanup

- Date: 2026-06-10
- Status: shipped
- Types: `ranking`, `audit`, `benchmark`
- Weakness found: The precision audit leaves 11 reviewed true false positives after separating useful extras from real errors.
- Recommended solution: Ranking changes should suppress those true false positives without demoting useful-extra concepts or expected secondary findings.
- Solution implemented: Kept the cleanup bounded to the 11 reviewed true false positives and retained explicit protection for the 58 useful extras. The contextual suppression tests cover the reviewed CUI/query shapes without broad source or semantic-group suppression.
- Artifacts: `config/search_quality_precision_audit_review.tsv`; `config/search_quality_useful_extra_cuis.tsv`; `docs/search_quality_precision_audit.md`; `src/qe_evidence_vectors/search_ranking.py`; `tests/test_precision_audit_review.py`; `tests/test_evidence_vectors.py`.
- Test evidence: `python3 -m pytest tests/test_precision_audit_review.py tests/test_evidence_vectors.py -k "precision_false_positive" -q`; included again in the final focused test batch and final live smoke gate.
- Implementation status: Keep. Useful extras remain protected; avoid adding broad suppression rules from this audit.
- Remaining action: Rebuild the precision audit only when new suspect rows are added.

### SQI-2026-06-10-014: Patient portal benchmark lane

- Date: 2026-06-10
- Status: shipped
- Types: `benchmark`, `ranking`
- Weakness found: Patient portal long-message examples now drive several ranking rules, but they need a dedicated benchmark lane rather than isolated regressions.
- Recommended solution: Active/current visit concepts should rank above old-history context, while old-history medications and diagnoses remain available lower in the result set.
- Solution implemented: Promoted the existing 12 portal rows into the post-iteration smoke helper as `patient_portal_current_history_smoke`. Ranking/benchmark iterations now include this lane by default; `--force-patient-portal-smoke` and `--skip-patient-portal-smoke` provide overrides. Gate-baseline selection now requires matching payload shape, preventing lean public-output portal runs from gating against internal evidence-item captures.
- Artifacts: `config/search_quality_patient_portal_queries.tsv`; `scripts/run_search_quality_experiment.py`; `tests/test_search_quality_experiment_gates.py`; `docs/repeatable_processes.md`; `docs/search_quality_experiments.html`; `build/search_quality_experiments/iteration_smoke_gates/SQI-2026-06-10-012-confirmed-all-gates/verification.md`.
- Test evidence: `python3 -m pytest tests/test_search_quality_experiment_gates.py -q`; final smoke helper passed the patient portal lane with 12/12 top-on-target, 0 top-wrong, 74/88 expected concepts at top 10, and 6/12 rows fully found by top 20.
- Implementation status: Keep. Patient portal current-versus-history behavior is now a regular smoke/report lane.
- Remaining action: Add portal rows only through reviewed current-history cases, not ad hoc copied-forward suppressions.

### SQI-2026-06-10-015: Shadow reranker regression triage

- Date: 2026-06-10
- Status: shipped; diagnostic only
- Types: `ranking`, `audit`, `benchmark`
- Weakness found: The shadow reranker report found wins, but also many regressions, so it is not ready to influence production ranking.
- Recommended solution: ML ranking should be used only after regressions are categorized and the feature/label mix is proven safer than the current ranker.
- Solution implemented: Added regression triage output to the shadow reranker. The refreshed report still has 1,068 judged rows with 355 wins, 425 regressions, and 288 losses; the 425 regressions classify as 415 `model_shape_issue` and 10 `label_gap`. No runtime ranking integration was made.
- Artifacts: `config/search_quality_judgments.tsv`; `scripts/search_quality_shadow_reranker.py`; `tests/test_search_quality_shadow_reranker.py`; `build/search_quality_shadow_reranker/search_quality_shadow_reranker.html`; `build/search_quality_shadow_reranker/shadow_regression_triage.tsv`; `build/search_quality_shadow_reranker/summary.json`.
- Test evidence: `python3 -m pytest tests/test_search_quality_shadow_reranker.py -q`; `python3 scripts/search_quality_shadow_reranker.py train-shadow --features build/search_quality_shadow_reranker/feature_rows.tsv`.
- Implementation status: Keep as diagnosis material only. Do not use the shadow reranker in production ranking.
- Remaining action: Work the largest `model_shape_issue` regressions before adding features or collecting more labels.

### SQI-2026-06-10-016: Historical improvement backfill

- Date: 2026-06-10
- Status: shipped
- Types: `process`, `audit`
- Weakness found: `improvements/` contains many historical May entries that are not individually represented in the iteration report.
- Recommended solution: Historical improvements should be traceable from the current report without pretending they were all reviewed under the new iteration contract.
- Solution implemented: Added a compact historical backfill note that counts the legacy May improvement records by date and category. The old records remain in `improvements/` as pre-contract change notes; they are not retroactively treated as smoke-gated SQI entries.
- Artifacts: `improvements/*.md`; `docs/search_quality_iterations.md`; `docs/search_quality_iterations.html`.
- Test evidence: Counted `improvements/*.md` entries and reviewed the resulting Markdown/HTML report text. No live smoke was needed because this is a documentation/process-only backfill with no runtime, ranking, label, judgment, benchmark, or API behavior change.
- Implementation status: Keep. Historical notes stay traceable without implying they satisfied the newer iteration contract.
- Remaining action: When a legacy note becomes active work again, open a fresh SQI entry and verify it under the current smoke rules instead of editing the historical note in place.

### SQI-2026-06-10-001: Patient portal long-message noise and history

- Date: 2026-06-10
- Status: shipped
- Types: `ranking`, `benchmark`
- Weakness found: A patient portal message about central venous access mixed the active concern with old atrial fibrillation, old ECG, metoprolol, and meta words such as "worried", "instructions", and "result".
- Recommended solution: Current visit concepts should rank first. Old history and old medications should be retained as context but demoted. Generic meta words should not become top biomedical anchors.
- Solution implemented: Added focused tests for portal-message linked concepts, current-vs-history assertion handling, planned/current wording, and watchlist generic fragments.
- Artifacts: `tests/test_evidence_vectors.py`; `src/qe_evidence_vectors/search_assertions.py`; `src/qe_evidence_vectors/search_rerank.py`; `src/qe_evidence_vectors/generic_filters.py`.
- Test evidence: Focused search/ranking tests were run with `pytest -k "linked_concepts or patient_portal_linked_concepts or generic_filter or age_descriptors or old_problem or planned_and_confirmed"`.
- Implementation status: Keep. This is a repeatable error class, not a one-off rule.
- Remaining action: Closed by `SQI-2026-06-10-014`; add future portal rows only through reviewed current-history cases.

### SQI-2026-06-10-002: Rule inventory and watchlist cleanup

- Date: 2026-06-10
- Status: shipped
- Types: `process`, `ranking`, `audit`
- Weakness found: The rule set was becoming hard to reason about, especially generic suppressions such as "Do not" and watchlist labels that are only bad in some contexts.
- Recommended solution: Rules should be organized by class, explained plainly, and protected by examples that show both the intended suppression and the allowed context.
- Solution implemented: Created a rule inventory report and adjusted watchlist behavior so labels such as developing countries, hormones, partial thickness, irregular, and pigmented are not globally blocked when they appear in useful contexts.
- Artifacts: `docs/search_rule_inventory.md`; `scripts/build_search_rule_inventory.py`; `tests/test_evidence_vectors.py`.
- Test evidence: Generic-filter regression tests and rule-inventory generation were run.
- Implementation status: Keep. The inventory is now the review surface for heuristic changes.
- Remaining action: Regenerate the inventory after every rule-class change.

### SQI-2026-06-10-003: Strict source-code output for RxNorm and other vocabularies

- Date: 2026-06-10
- Status: shipped
- Types: `source-code`, `ui`, `ranking`
- Weakness found: Selecting RxNorm returned concept-style results and mixed mappings. A later relation bridge returned drugs that differed from the visible concept results.
- Recommended solution: A specific source vocabulary selection should never fall back to non-source concept rows. It may use concept retrieval internally only to find CUIs, but the response must contain source rows for the requested vocabulary only.
- Solution implemented: Source-code mode now returns strict source atom rows or mapped rows for actual concept candidates. Relation-derived treatment expansion was removed from default source-code mode. Detail hydration now filters `mappings` to the selected source. Result titles now link to UTS source-code pages when a source code is available.
- Artifacts: `src/qe_evidence_vectors/search_execution.py`; `src/qe_evidence_vectors/search_hydration.py`; `src/qe_evidence_vectors/search_quality_http.py`; `docs/search_quality/app.js`; `docs/search_quality_server.html`; `tests/test_evidence_vectors.py`.
- Test evidence: Focused source-code tests, broader focused smoke, `py_compile`, JS syntax check, live API checks on port 8766, and `/api/detail?codes=RXNORM` mapping checks.
- Implementation status: Keep. Therapeutic expansion should be a separate explicit mode, not a side effect of choosing RxNorm.
- Remaining action: Add an explicit "related drugs" or "therapeutic expansion" mode only if there is a reviewed benchmark and clear UI label.

### SQI-2026-06-10-004: PubMed and long-document recall lane

- Date: 2026-06-10
- Status: shipped
- Types: `long-document`, `benchmark`
- Weakness found: Clinical smoke was strong, but PubMed abstract recall was the obvious weak lane in the search-quality experiment report.
- Recommended solution: Long documents should preserve secondary concepts through section/chunk linking, merge, and rerank so important concepts survive long text.
- Solution implemented: Added a reviewed dev-only PubMed long-document slice selector and a materializer that builds an evaluator-ready TSV from the strict PubMed seed files. Ran the first baseline. No section/chunk linking or reranking change was made in this iteration.
- Artifacts: `config/search_quality_pubmed_long_document_slice.tsv`; `scripts/build_pubmed_long_document_slice.py`; `docs/pubmed_literature_benchmark.md`; `docs/search_quality_experiments.html`; `tests/test_pubmed_paragraph_queries.py`; `build/search_quality_experiments/runs/20260610T172821Z_pubmed-long-document-focused-slice/paragraph_quality_report.md`.
- Test evidence: `python3 -m pytest tests/test_pubmed_paragraph_queries.py -q`; `python3 scripts/build_pubmed_long_document_slice.py`; focused API benchmark on port `8766`. Baseline: 7 rows, overall 29.0, Recall@10 24/36, Recall@20 30/36, all expected@10 1/7, top on target 6/7, verdicts 6 mixed and 1 poor.
- Implementation status: Keep. This gives the long-document lane a repeatable input and baseline before changing ranking behavior.
- Remaining action: Closed by `SQI-2026-06-10-012`; remaining long-document misses stay tracked on that focused slice.

### SQI-2026-06-10-005: Precision-audit queue cleanup

- Date: 2026-06-10
- Status: shipped
- Types: `audit`, `benchmark`
- Weakness found: The precision audit queue had a stale planning count of 70 suspect rows, but the current generated queue has 69. Unclassified suspect rows make future ranking changes ambiguous.
- Recommended solution: Every suspect row should be classified as expected, useful-extra, or true false positive before broad ranking changes continue.
- Solution implemented: Reconciled the current raw audit queue against the review ledger. All 69 current suspect rows are classified: 0 expected promotions, 58 useful extras, and 11 true false positives. The 58 useful-extra rows are present in the useful-extra config, leaving the 11 true false positives as the residual ranking/suppression target set.
- Artifacts: `config/search_quality_precision_audit_review.tsv`; `config/search_quality_useful_extra_cuis.tsv`; `docs/search_quality_precision_audit.md`; `scripts/build_precision_audit_report.py`; `tests/test_precision_audit_review.py`; `build/search_quality_live_audit/paragraph_precision_audit.tsv`; `build/search_quality_live_audit_reviewed/paragraph_precision_audit.tsv`.
- Test evidence: `python3 scripts/build_precision_audit_report.py`; `python3 -m pytest tests/test_precision_audit_review.py -q`; `python3 -m py_compile scripts/build_precision_audit_report.py`.
- Implementation status: Keep. The stale count is documented, and the current reproducible queue is fully classified.
- Remaining action: Closed by `SQI-2026-06-10-013`; rebuild the precision audit only when new suspect rows are added.

### SQI-2026-06-10-006: Search-quality iteration report

- Date: 2026-06-10
- Status: shipped
- Types: `process`, `ui`
- Weakness found: Search-quality work had many partially finished threads and needed a repeatable process with user-understandable artifacts.
- Recommended solution: There should be one report that plainly states what happened with each iteration and can be filtered by type.
- Solution implemented: Added this ledger and a filterable HTML report for search-quality iterations going forward.
- Artifacts: `docs/search_quality_iterations.md`; `docs/search_quality_iterations.html`.
- Test evidence: Static artifact review.
- Implementation status: Keep.
- Remaining action: Append every future search-quality iteration here before or immediately after the code/report change lands.

### SQI-2026-06-10-007: Hide confidence labels from search results

- Date: 2026-06-10
- Status: shipped
- Types: `ui`
- Weakness found: Search results showed "high confidence", "medium confidence", and "low confidence" labels that were not requested and only applied to some ranking paths.
- Recommended solution: The primary result list should show rank, relevance score, type, and details without an extra partial confidence vocabulary.
- Solution implemented: Removed confidence badges from compact result rows and removed the confidence chip from result metadata. The backend confidence annotation remains available internally for ranking/debug work.
- Artifacts: `docs/search_quality/app.js`; `docs/search_quality/server.css`; `docs/search_quality_server.html`.
- Test evidence: JS syntax check and live static asset check.
- Implementation status: Keep. The confidence labels were not a clear user-facing contract.
- Remaining action: If confidence is needed later, expose it as an explicit debug/explainability toggle with clear definitions.

### SQI-2026-06-10-008: Two-column iteration report layout

- Date: 2026-06-10
- Status: shipped
- Types: `ui`, `process`
- Weakness found: The report mixed proposed and completed entries in one list, making planned work look too similar to shipped work.
- Recommended solution: Proposed work and completed work should be visually separated while preserving type, status, and text filters.
- Solution implemented: Changed the report view into separate Proposed and Completed columns. Completed means shipped; Proposed means visible work that is not marked shipped.
- Artifacts: `docs/search_quality_iterations.html`; `docs/search_quality_iterations.md`.
- Test evidence: Inline script syntax check and static report review.
- Implementation status: Keep.
- Remaining action: Use the completed column as the shipped history and the proposed column as the queue.

### SQI-2026-06-10-009: Common-word gene symbol guard

- Date: 2026-06-10
- Status: shipped
- Types: `ranking`, `benchmark`
- Weakness found: A patient portal message contained ordinary prose saying "still lists furosemide", which can be normalized to the token `list` and misread as the `LIST` gene.
- Recommended solution: Short/common gene symbols should not surface from ordinary prose morphology. Real gene mentions such as `LIST gene`, `CYP2C19`, `EGFR`, `BRCA1`, or `HLA-B27` should remain available when the query explicitly names the symbol or includes gene/genetic context.
- Solution implemented: Added `list` to the contextless common-word gene-symbol guard and added a patient-portal regression proving that `lists` does not return a `LIST gene` result while explicit `LIST gene variant` still can.
- Artifacts: `src/qe_evidence_vectors/search_ranking.py`; `tests/test_evidence_vectors.py`.
- Test evidence: `python3 -m pytest tests/test_evidence_vectors.py -q -k "contextless_large_gene or contextless_list_gene"`; `python3 -m py_compile src/qe_evidence_vectors/search_ranking.py`.
- Implementation status: Keep. This is a general ambiguity rule for common-word gene symbols, not a patient-message-only suppression.
- Remaining action: If more common-word gene symbols appear, add them only with paired tests showing the ordinary prose failure and the explicit gene-context allowance.

## Historical Improvement Backfill

The `improvements/` directory contains 148 legacy notes from May 2026. They are
useful provenance, but they predate the current SQI contract and should not be
read as individually smoke-gated iterations. When one becomes active work again,
open a new SQI entry, rerun the relevant gate, and link back to the historical
note as background.

Legacy notes by date:

| Date | Count |
| --- | ---: |
| 2026-05-07 | 14 |
| 2026-05-08 | 69 |
| 2026-05-11 | 47 |
| 2026-05-12 | 14 |
| 2026-05-13 | 3 |
| 2026-05-14 | 1 |

Legacy notes by primary thread:

| Thread | Count |
| --- | ---: |
| Ranking, filtering, semantic grouping, or exact/comprehensive search behavior | 65 |
| General search-quality behavior and result presentation | 34 |
| UI controls and report layout | 23 |
| Source, relationship, corpus, or licensing work | 19 |
| Benchmark, audit, query-set, or paragraph-evaluation work | 18 |
| Process, reproducibility, rebuild, API, or documentation work | 11 |
