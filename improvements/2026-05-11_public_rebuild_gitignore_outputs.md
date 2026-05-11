# Public Rebuild Gitignore Outputs

## Change

Added `.gitignore` entries for generated public-rebuild outputs when `scripts/run_public_rebuild.py --out-dir` is pointed outside the already ignored `build/` directory.

Ignored outputs now include public corpus JSONL files, linked evidence JSONL, concept document/vector JSONL files, public SQLite work/index directories, manifests, command plans, server command files, and paragraph evaluation output directories.

## Why This Improves Things

The default `build/` path was already ignored, but external users may choose another output directory while testing reproducibility. These patterns reduce the chance that large generated corpora, licensed-derived indexes, or local rebuild manifests are accidentally committed.

## Verification

- Reviewed `.gitignore` after the change.
- No runtime behavior changed.
