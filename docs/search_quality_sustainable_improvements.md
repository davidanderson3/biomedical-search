# Sustainable Search Quality Improvements

This project should improve search quality without turning into an unreviewable pile of one-off fixes. Prefer durable changes in this order:

1. Improve source coverage or structured evidence when a concept class is broadly underrepresented.
2. Add or revise semantic bucket/profile configuration when the problem is display, grouping, or source routing.
3. Add active-label supplement rows only when an existing CUI is known, the phrase is explicitly useful in clinical/research text, and default indexing or ranking loses it.
4. Add ranker rules only for reusable error classes, not for a single CUI unless the same pattern is expected to recur.
5. Add new CUIs only when the concept is clinically relevant and not represented by an existing UMLS concept or acceptable alternative.

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

For every improvement:

1. Identify the failure from a stored benchmark, user example, or focused query.
2. Make the smallest durable change.
3. Add or update tests.
4. Run focused evaluation for the affected rows when practical.
5. Document the measured effect in `improvements/`.
6. Periodically run the full paragraph benchmark to catch regressions outside the focused set.

Use focused evaluation for known misses:

```sh
python3 scripts/evaluate_paragraph_quality.py --queries /path/to/focused_queries.tsv --output-dir build/improvements/<run_name> --top-k 60
```

Use the full benchmark periodically:

```sh
python3 scripts/evaluate_paragraph_quality.py --output-dir build/improvements/<run_name> --top-k 60
```
