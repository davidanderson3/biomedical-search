# Search Quality Test Suite

This is the repeatable suite for the current search app. Its job is to catch
weaknesses, verify fixes on the same examples, and prevent regressions.

## Run It

Start the search API first in one terminal:

```sh
PORT=8766 scripts/start_search_quality_server.sh
```

Then run the suite in another terminal:

```sh
python3 scripts/run_search_quality_suite.py --base-url http://127.0.0.1:8766
```

Dry-run the suite plan without calling the API:

```sh
python3 scripts/run_search_quality_suite.py --dry-run
```

Suite outputs are written under `build/search_quality_suite/<suite-id>/`.
Benchmark run artifacts still go under `build/search_quality_experiments/runs/`.
Each suite report records the layer result, the weakness it is meant to catch,
the recommended solution, and whether that layer is blocking.

## Current Layers

| Layer | Role | Blocking? | What It Catches |
| --- | --- | --- | --- |
| `unit_static_regressions` | code regression guard | yes | Unit/static failures before live benchmark results are trusted. |
| `coverage_representativeness_audit` | static concept-target coverage audit | no, known weakness | Expected and disallowed CUIs concentrating in a few semantic groups or source files even when the suite is otherwise green. |
| `real_short_query_regression` | real short-query guard | yes | Simple high-demand searches such as `hypertension`, `heart failure`, and `type 2 diabetes mellitus` failing despite being reviewed safe queries. |
| `full_clinical_benchmark` | broad coverage baseline | yes | Regression from the current 168-example clinical suite. |
| `cycling_clinical_regression` | rotating regression guard | yes | Failures hidden by a fixed smoke set. |
| `clinical_text_type_variety` | realistic clinical text format probe | no, known weakness | Whether discharge summaries, radiology reports, pathology reports, operative notes, nursing notes, lab flowsheets, medication administration records, therapy notes, home health notes, telephone triage, consult notes, and prior authorization text still map to the expected concepts. |
| `consumer_lay_language` | consumer lay-language probe | no, known weakness | Terse patient wording such as `water pill`, `pee test`, `belly pain`, `sugar diabetes`, `heart tracing`, scopes, and `blood thinner` drifting to literal/noise concepts. |
| `patient_portal_intent` | current-vs-history workflow guard | yes | Copied-forward history outranking the current portal concern, plus evidence-source loss. |
| `pubmed_approved_long_documents` | held-out long-document weakness probe | no, known weakness | Long PubMed abstracts dropping secondary concepts or ranking the wrong concept first. |
| `precision_safety` | wrong-result and reviewed precision guard | yes | Recall changes promoting reviewed false positives, disallowed IDs, or bad source contributions. |
| `external_embedding_neighbor_probe` | opt-in external embedding-neighbor probe | no | CUI2Vec/BioConceptVec staying measurable as bounded association signals without becoming default source evidence. |
| `source_specific_evidence` | core source-specific evidence guard | yes | DailyMed, MedlinePlus, or PubMed/PMC evidence behavior quietly regressing. |
| `pubmed_focused_long_documents` | fast long-document tuning probe | no, known weakness | Whether long-document fixes improve the same focused PubMed failures. |

The suite definition is `config/search_quality_suite.json`.

## Holistic View

The best current suite is not one giant score. It is a set of lanes with
different jobs:

- Real short queries protect the obvious product experience: common medical
  terms should return the expected concept.
- Full clinical and cycling clinical runs protect broad judged coverage.
- Coverage representativeness audits show which CUIs the tests actually assert,
  so green runs are not mistaken for proof of prevalence-weighted clinical
  coverage.
- Realistic note-format probes test clinical text that looks more like source
  documents than polished benchmark paragraphs.
- Patient messages protect current-user intent against copied-forward history.
- PubMed long-document runs intentionally expose the strongest open weakness.
- Precision and source-specific lanes keep recall fixes from hiding wrong results
  or source regressions.
- CUI2Vec and BioConceptVec stay in the loop as opt-in association-signal
  probes. They are not source text, not trusted evidence, and not loaded by the
  default search server unless explicitly requested.

Document-retrieval benchmarks are not active suite layers for this app. The
current product returns medical concepts with evidence, so source quality is
tested through source-specific concept searches and evidence-source checks.

Every search-quality loop should improve this suite, not only the app. In this
project, "run a loop" and "do an iteration" mean the same thing: run tests,
find a weakness, mitigate it, rerun the same checks, record how long it took,
and document what changed in the tests. A loop should add a focused regression
test, refine a benchmark row, promote a repeated miss into a suite lane, tighten
a threshold, or explicitly document why the existing tests already cover the
weakness.

## Expected Status Today

The suite is not expected to be fully green yet. That is intentional:

- The static layer is green in this worktree. The latest static-only suite run is
  `build/search_quality_suite/SQS-20260615-static-guard-green/suite.md`
  with 413 passed and 1 skipped.
- The coverage representativeness audit is a nonblocking known-weakness layer.
  The latest audit found 609 unique target CUIs and 2,210 target mentions, with
  Disorders at 48.3% of target mentions and thin Anatomy, Phenomena, and
  Physiology coverage. This is not a prevalence-weighted target model yet; it is
  the repeatable measurement that should drive the next representative coverage
  work.
- The real short-query and core source-specific evidence lanes are now first-class
  suite layers. The real short-query lane remains at the 20 reviewed rows that
  passed on 2026-06-11; the 2026-06-12 three-word expansion probe found new
  exact-mention carryover failures and was not promoted. The source-specific
  lane is intentionally narrowed to DailyMed, MedlinePlus, and PubMed/PMC and
  passed on 2026-06-15 with 9/9 rows complete, 20/20 expected CUIs at top 10,
  and 0 wrong-first rows after the DailyMed warning-context fix. ClinicalTrials.gov
  posted outcomes are opt-in only, and PubTator3 stays a sampled relation-candidate
  stub unless a measured gap validates it against PubMed/PMC.
- The external embedding-neighbor probe keeps CUI2Vec and BioConceptVec in the
  measured loop as opt-in subset candidates with drift guards. SapBERT remains
  the active query/document embedding baseline.
- The consumer lay-language lane is now a first-class known-weakness probe. It
  covers reviewed patient wording such as `water pill`, `pee test`, `belly
  pain`, `sugar diabetes`, `heart tracing`, `colon scope`, `stomach scope`, and
  `blood thinner`, with explicit disallowed literal-drift CUIs where relevant.
  Governed active-label supplement aliases now cover the main lay phrases, but
  the live Elasticsearch-backed lane still needs a fresh rerun before its
  expected status changes from the 5/13 baseline.
- The clinical text type variety probe is intentionally nonblocking until it has
  a stable green baseline. The first live run was 5/12 rows fully found at top
  10, 52/60 expected concepts found, 7 rows missing at least one expected
  concept, and 0 wrong first results. It is strict: all 12 English-only
  note-format rows and 60 expected concepts must be found at top 10 before it
  turns green.
- The patient-portal layer is blocking and should fail until the 11/12 regression
  and missing evidence-source issue are fixed.
- The PubMed layers are marked as known weaknesses, so they report failure without
  blocking the default `--fail-on blocking` exit mode.

Use `--fail-on any` when you want known weaknesses to make the command fail too.
Use `--only <layer-id>` to rerun one layer after fixing a specific weakness.
