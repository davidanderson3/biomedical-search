# Sustainable Search Quality Improvements

This project should improve search quality without turning into an unreviewable pile of one-off fixes. Prefer durable changes in this order:

1. Improve source coverage or structured evidence when a concept class is broadly underrepresented.
2. Add or revise semantic bucket/profile configuration when the problem is display, grouping, or source routing.
3. Add active-label supplement rows only when an existing CUI is known, the phrase is explicitly useful in clinical/research text, and default indexing or ranking loses it.
4. Add ranker rules only for reusable error classes, not for a single CUI unless the same pattern is expected to recur.
5. Add new CUIs only when the concept is clinically relevant and not represented by an existing UMLS concept or acceptable alternative.

## Rule Inventory

Use `docs/search_rule_inventory.md` as the review surface for heuristic
changes. Regenerate it whenever you add, remove, or reclassify suppression
rules, assertion cues, portal meta-language rules, benchmark rows, precision
audit rows, or active-label supplement rows:

```sh
python3 scripts/build_search_rule_inventory.py
```

The inventory explains each rule class and answers three questions before a
new rule lands:

- Which rule class does this belong to?
- What should this class handle, and what should it not handle?
- Which benchmark row, audit row, or unit test explains why it exists?

## Active Label Supplement Rules

`config/active_label_supplement.tsv` is a high-leverage but high-risk file. Each row must include:

- A valid existing or new CUI.
- A clear `semantic_type` and local `field`.
- A `why` value explaining the clinical/retrieval reason.
- `context_any` for non-preferred short labels, abbreviations, and risky aliases unless the row is a drug roll-up alias.
- `block_any` when a known wrong expansion is likely, such as `STEMI` versus `NSTEMI`.

Validate the file after edits:

```sh
python3 scripts/validate_active_label_supplement.py
```

The unit suite also checks this validation so unsafe rows fail fast:

```sh
python3 -m pytest tests/test_evidence_vectors.py -k active_label_supplement -q
```

## Ranking Rule Rules

Ranker changes should be pattern-based. A good rule names an error class, such as:

- generic status words outranking clinical entities,
- care-setting words such as `emergency department` becoming disease/finding concepts,
- ambiguous surface forms such as `cervical`,
- broad related concepts leaking into semantic group cards.

Each ranking rule should have at least one positive test and one protection against the obvious false positive.

## Evaluation Loop

When the request is "run a loop" or "do an iteration", use this process.

Daily preflight: if this is the first iteration started on a new calendar day,
summarize the previous day's shipped improvements in lay language before
choosing the next failure. Add that summary to
`docs/search_quality_daily_accomplishments.html` so the daily log explains what
changed without requiring the reader to understand CUI IDs, benchmark internals,
or iteration numbers. Keep `docs/search_quality_progress_log.html` linked to
that daily-accomplishments file. If the previous day already has a
plain-language summary, leave it in place and continue.

For every improvement:

1. Identify the failure from a stored benchmark, user example, or focused query.
2. State the hypothesis and expected measurable movement before changing code or evidence.
3. Make the smallest durable change.
4. Add or update tests.
5. Improve the test suite itself: add a missing focused test, refine an existing
   benchmark row, promote a recurring miss into a suite lane, tighten a
   threshold, or explicitly record why no test change was appropriate.
6. Run focused evaluation for the affected rows when practical.
7. Document the measured effect in `improvements/`, including the exact query file, output directory, command, before/after metrics, test-suite change, and decision.
8. Periodically run the full paragraph benchmark to catch regressions outside the focused set.

Record every bounded search-quality pass in `docs/search_quality_iterations.md`.
Use `docs/search_quality_iterations.html` as the filterable review surface by
iteration type, status, and text search. Also update
`docs/search_quality_progress_log.html` in the same iteration whenever the
headline status, latest-result cards, open-work list, or readable chronology
changes. Do not mark an iteration shipped while the progress log still describes
the previous result as current.

Refresh the backlog in `docs/search_quality_progress_log.html` on every
iteration. Move completed items out, add new weaknesses discovered during the
work, update priorities when evidence changes, and explicitly leave it unchanged
only when the current backlog is still accurate after the iteration.

Track the whole-product quality percentage in
`docs/search_quality_progress_log.html#whole-product-quality`. Update the score
history whenever a shipped iteration changes user-visible behavior, a major
benchmark/smoke signal, source transparency, or a top known quality risk. The
score should use the documented rubric: coverage and recall, precision and
trust, UX/workflow fit, test/process reliability, and evidence/source
transparency. Do not raise the percentage for a narrow recall win if visible
noise, wrong-first behavior, or source trust gets worse.

Track evidence approval status in `docs/search_quality_evidence_buckets.html`.
When an iteration acquires evidence, tests a source shard, promotes an
acquisition, rejects a source path, adds source-specific benchmark rows, or
changes source routing, update the bucket page in the same iteration. A build
artifact existing under `build/` does not mean the evidence is approved; it must
be bucketed as promoted, tested-neutral, rejected, configured-pending,
benchmarked-not-ready, inventory-only, or diagnostic.

Use focused evaluation for known misses:

```sh
python3 scripts/evaluate_paragraph_quality.py --queries /path/to/focused_queries.tsv --output-dir build/improvements/<run_name> --top-k 60
```

Use the full benchmark periodically:

```sh
python3 scripts/evaluate_paragraph_quality.py --output-dir build/improvements/<run_name> --top-k 60
```

## Progression Records

Source-acquisition work has an executable progression ledger:

```sh
python3 scripts/source_acquisition_progression.py --fail-on-regression
```

This reads `config/source_acquisition_progression.tsv` and writes
`build/source_acquisition/progression_manifest.json` plus
`build/source_acquisition/progression_report.md`. Treat this as the model for
other result-improvement progressions: every retained stage should have a
hypothesis, artifact inventory, measured metrics, a deterministic gate, and a
decision. Rejected diagnostic stages may be recorded for learning, but they
must not lower the reference bar for the next accepted or neutral stage.
