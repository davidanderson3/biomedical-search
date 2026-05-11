# New UMLS Iteration Loop

Last updated: 2026-05-06

This file defines the operating loop for building a broadly useful biomedical
search interface and vector store on top of an open UMLS seed plus local
`NEW#######` extension concepts.

## Product Goal

Build a search system that clinicians, researchers, and terminology maintainers
can use for real biomedical language. The system must be:

- Broadly useful: handles common clinical notes, research abstracts, source
  codes, LOINC observations, abbreviations, procedures, findings, therapies, and
  relationship-oriented queries.
- Updatable: every run has a manifest, stable inputs, versioned outputs, and a
  clear release decision.
- Extensible: new `NEW#######` concepts, aliases, evidence, and MTH-style
  broader/narrower assertions can be added without rebuilding everything.
- Documentable: each concept and index change has enough provenance for a person
  to understand why it exists and how it was produced.

## Current Decisions

- Base UMLS subset: use source vocabularies identified in `MRSAB.RRF` as
  UMLS restriction level 0 / category 0. Each run must persist the selected SABs
  and UMLS release when those files are part of the run.
- LOINC: use UMLS level-0 LOINC content where present and direct LOINC files
  supplied separately. Preserve raw codes/names and produce clearer clinical
  observation display names as a product layer, not as proof that a new concept
  exists.
- New local CUIs: use `NEW#######` identifiers. These are local product CUIs,
  not NLM-assigned UMLS CUIs.
- Weak-area focus: clinically relevant missing or poorly bounded concepts,
  especially observations/results, phenotypes, procedures, clinician shorthand,
  treatment response, safety/toxicity patterns, and procedure concepts weakened
  by the absence of CPT in the open subset.
- Evaluation: Codex/LLM evaluation is part of the loop. Human feedback is useful
  but not required before creating a local CUI.
- Threshold policy: start conservative, then lower thresholds only when the last
  iteration shows acceptable precision and good duplicate control.
- Synthetic query corpus: use several thousand typical clinical and research
  sentences for repeatable search pressure. Current set:
  `config/typical_clinical_research_sentences.tsv`.

## Progress Metrics

Every iteration should report the same percentages so we can see whether the
system is getting better:

- Query-term coverage: pre-existing exact coverage, extension coverage, new
  CUI coverage, deferred terms, and unresolved clinically relevant gaps.
- Search quality: top-1 relevance, expected CUI recall at 5/10/20/60,
  semantic-group coverage, weighted precision at 5, MRR, and the most common
  failure categories.
- Result usefulness: paragraph-level `good` / `mixed` / `poor` judgments that
  answer whether the returned concepts are clinically useful, not merely
  present somewhere in the payload.
- Vector-store freshness: changed concept documents, changed vectors, loaded
  vector count, alias/index version, and whether old vectors were retired.
- Concept growth: new CUIs, carried-forward CUIs, rejected duplicates, semantic
  equivalence guards, and concepts needing review.
- Relationship growth: MTH `RB`/`RN` rows, close matches, related anchors, and
  relation assertions needing spot check.
- LOINC usefulness: direct LOINC exact matches, observation display-name rows,
  and terms rescued by LOINC-derived naming.
- Documentation completeness: manifest, report, candidate review, relation
  review, search payloads, and test summary present for the run.

## Efficient Iteration Contract

Each iteration has one primary purpose. Do not mix too many goals in one pass.
Good purposes are:

- Improve coverage in one weak slice, such as clinical results or procedures.
- Add a batch of high-confidence concepts.
- Improve LOINC display-name normalization.
- Load an extension vector shard into the search alias.
- Fix a ranking or provenance failure found by evaluation.
- Refactor the pipeline after repeated changes.

The default cadence is:

1. Carry forward prior extension concepts as existing coverage.
2. Run the same query set to measure regression.
3. Identify the biggest remaining gap by slot/domain.
4. Add only changes that directly improve that gap.
5. Rebuild the smallest affected artifacts.
6. Re-run tests and write a release decision.

## Iteration Steps

1. Freeze the run manifest.
   Record input artifacts, prior extension registries, UMLS/LOINC versions,
   PubMed shards, restricted-data boundaries, embedding model, vector index
   names, thresholds, and code revision when available.

2. Load known concept coverage.
   Load the level-0 UMLS label index, code resolver index, direct LOINC lookup,
   and all promoted `NEW#######` concepts from prior iterations.

3. Normalize candidate language.
   Normalize clinical/research sentences, failed queries, LOINC observation
   names, and evidence snippets. Before CUI creation, check exact labels, source
   codes, direct LOINC names, prior extension labels, and curated semantic
   equivalence guards.

4. Search and evaluate.
   Run the stable query set through the current search interface when available.
   Save payloads and grade the output using the same rubric: relevant, partial,
   wrong, unsupported, missing concept, bad label, bad semantic type, bad
   ranking, or provenance problem.
   Also assign each paragraph a `good`, `mixed`, or `poor` verdict. `Good`
   means the central concepts from the main semantic groups are visible in the
   first page and the top result is clinically on target. `Mixed` means the
   right concepts are recoverable but ranking, semantic typing, or omissions
   would slow a reviewer down. `Poor` means a central concept is absent from
   the first useful result window or the returned set has the wrong clinical
   focus.

5. Mine unresolved gaps.
   For unresolved terms, require both query pressure and evidence support. Favor
   concepts that are clinically useful as search targets, relation nodes, or
   result filters.

6. Compare against existing concepts.
   Reject spelling, punctuation, word-order, acronym-expansion, and obvious
   semantic-equivalent variants. Record close-match and broader anchors when the
   existing concept is useful but insufficient.

7. Promote high-confidence `NEW#######` concepts.
   Emit preferred label, aliases, semantic type, definition, evidence, source
   provenance, anchors, status, rationale, and iteration metadata.

8. Update relationships.
   Add MTH `RB`/`RN` broader/narrower rows only where the hierarchy is clear.
   Use close-match anchors for near-equivalents or adjacent concepts that should
   not be asserted as hierarchy.

9. Rebuild affected vector/search artifacts.
   Build concept documents and vectors for changed concepts. Load them into a
   versioned vector index or extension shard. Move aliases only after evaluation
   passes.

10. Document the run.
    Write the manifest, report, term evaluation, candidate review, relation
    quality file, vector/reindex decision, test output, and next-step notes.

11. Refactor periodically.
    Every few iterations, clean repeated code, add tests around new behavior,
    and update the technical pipeline docs.

## Release Gates

An iteration can be released to the active search interface only when:

- Existing high-value queries do not regress.
- New or changed concepts have concept documents and vectors.
- The search alias or extension shard can be rolled back.
- The manifest says exactly which artifacts were loaded.
- Candidate and relation review artifacts exist.
- Tests covering changed code pass.

If a run creates concepts but does not load them into the active vector store,
the report must say so explicitly.

## Minimum Output Per Iteration

- Input manifest
- Prior-extension coverage record
- Corpus/evidence artifact manifest
- Term evaluation TSV/JSONL
- Candidate review TSV/Markdown
- Promoted `NEW#######` concept registry
- Extension concept documents and evidence JSONL
- MTH relation JSONL/SQLite when relations are emitted
- Search payload archive when a live search interface is evaluated
- Vector/reindex/release decision note
- Test summary

## Promotion Threshold

Create a new local CUI only when most of the following are true:

- The candidate is clinically useful as a search target, result, or relation
  node.
- Evidence appears across repeated examples or multiple independent source
  contexts.
- The concept boundary is more specific than a generic phrase but broader than a
  one-off sentence.
- Existing level-0 UMLS, direct LOINC, and prior `NEW#######` concepts do not
  represent the idea cleanly.
- A preferred label and short definition can be written without contorting the
  evidence.
- At least one broader, related, or close-match anchor can be recorded when a
  reasonable anchor exists.
- Adding the concept should improve retrieval or coverage in a known weak area.

Lower thresholds only for a named weak slice and only after adding duplicate
guards for the variants found in the previous run.

## Explicit Non-Goals

- Do not create new CUIs for capitalization, punctuation, pluralization, word
  order, spelling-only variants, or trivial modifiers.
- Do not create a local CUI when a semantic-equivalent level-0 concept already
  covers the phrase well enough for search.
- Do not treat direct LOINC display-name cleanup as proof that a new clinical
  concept exists.
- Do not publish `NEW#######` concepts as official NLM UMLS CUIs.
- Do not mix restricted clinical text into public artifacts.

## Completed Iterations

- `iteration_001_existing_data`: existing-data-only pass using generated
  clinical/research sentences, the current UMLS label/code indexes, direct
  LOINC 2.82, five public topic concept-document chunks, and the latest reviewed
  PubMed bulk shard. It created 10 high-support local `NEW#######` concepts
  after treating exact code-resolver matches such as `diuresis` as existing
  coverage. It also emits local MTH `RB`/`RN` broader/narrower assertions where
  a defensible broader UMLS anchor exists and writes direct LOINC display-name
  artifacts for the clinical-observation naming pass. Report:
  `build/new_umls_iterations/iteration_001_existing_data/iteration_report.md`.
- `iteration_002_existing_data`: existing-data-only pass that carries forward
  the 10 promoted iteration 001 concepts as local coverage, adds curated
  semantic-equivalent guards for obvious variants, modestly lowers the support
  threshold for the next weak-slice pass, and creates 3 additional
  `NEW#######` concepts. It writes both incremental and cumulative extension
  concept artifacts so downstream vector indexing can load only the delta or the
  full current local extension layer. Report:
  `build/new_umls_iterations/iteration_002_existing_data/iteration_report.md`.
- `iteration_003_search_quality`: existing-data-only search-quality pass that
  embeds and loads the 13 cumulative local extension concepts into the active
  search path, adds deterministic label fallback for loaded `NEW#######`
  concepts, and fixes ranking failures found by the paragraph tests. It creates
  no new CUIs. Report:
  `build/new_umls_iterations/iteration_003_search_quality/iteration_report.md`.
- `iteration_004_search_quality_intent`: existing-data-only search-quality pass
  that adds paragraph-intent ranking signals, demotes comparator-arm concepts in
  cohort/comparative-study wording, and fixes structured-statement linking for
  repeated phrase occurrences. It creates no new CUIs. Report:
  `build/new_umls_iterations/iteration_004_search_quality_intent/iteration_report.md`.
- `iteration_005_semantic_types_and_quality`: existing-data-only pass that
  hydrates semantic types for promoted `NEW#######` CUIs, enables default UMLS
  label fallback, expands the paragraph benchmark to 20 examples, and adds
  explicit `good` / `mixed` / `poor` usefulness evaluation. It creates no new
  CUIs. Report:
  `build/new_umls_iterations/iteration_005_semantic_types_and_quality/iteration_report.md`.
- `iteration_006_exact_mentions`: existing-data-only pass that improves
  first-page exact-mention handling, suppresses low-value single-token label
  artifacts, and preserves semantic grouping for label-only fallback hits. It
  improves the stable paragraph benchmark to 11 `good`, 9 `mixed`, and 0
  `poor` outputs. It creates no new CUIs. Report:
  `build/new_umls_iterations/iteration_006_exact_mentions/iteration_report.md`.
- `iteration_007_more_paragraphs`: existing-data-only pass that expands the
  paragraph benchmark from 20 to 32 examples, adds short biomedical acronym
  handling, and narrows exact medication ranking so administered drugs stay
  visible without treating lab analytes as drugs. It corrects benchmark targets
  where the sentence wording pointed to an existing alternative CUI and improves
  the expanded benchmark to 25 `good`, 7 `mixed`, and 0 `poor` outputs. It
  creates no new CUIs. Report:
  `build/new_umls_iterations/iteration_007_more_paragraphs/iteration_report.md`.
- `iteration_008_label_supplement_alternatives`: existing-data-only pass that
  adds a curated active-label supplement for existing CUIs hidden by the active
  semantic-profile label index and adds acceptable-CUI alternative scoring to
  the paragraph evaluator. It recovers `C0877453` acute cellular rejection
  without creating a duplicate local CUI and improves the expanded benchmark to
  27 `good`, 5 `mixed`, and 0 `poor` outputs. It creates no new CUIs. Report:
  `build/new_umls_iterations/iteration_008_label_supplement_alternatives/iteration_report.md`.
- `iteration_009_sepsis_components`: existing-data-only pass that keeps
  explicit septic-shock treatment/monitoring component anchors visible, demotes
  drug-brand labels in non-drug contexts, and treats laterality-only labels as
  fragments. It improves the expanded benchmark to 28 `good`, 4 `mixed`, and 0
  `poor` outputs with 97.0% recall@10 and 100.0% recall@60. It creates no new
  CUIs. Report:
  `build/new_umls_iterations/iteration_009_sepsis_components/iteration_report.md`.
- `iteration_010_more_paragraphs`: existing-data-only pass that expands the
  paragraph benchmark from 32 to 80 examples, updates the web interface example
  list, adds short clinical acronym handling and active-label supplement rows
  for fragile existing CUIs, and tunes ranking so vaccine concepts do not
  outrank infection concepts without vaccination intent. It improves the
  80-paragraph benchmark from 45 `good`, 35 `mixed`, and 0 `poor` outputs to
  68 `good`, 12 `mixed`, and 0 `poor` outputs with 96.6% recall@10 and 99.0%
  recall@60. It creates no new CUIs. Report:
  `build/new_umls_iterations/iteration_010_more_paragraphs/iteration_report.md`.
