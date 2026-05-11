# One-Command Public Rebuild

## Change

- Added `scripts/run_public_rebuild.py`, an orchestrator for the public-first reproducible build path.
- Added `requirements-public.txt`, intentionally empty except for comments because the hashing rebuild path uses the Python standard library.
- Updated `docs/reproducibility.md` and `README.md` to point external users at the wrapper.

## What The Wrapper Does

The wrapper runs the public rebuild in this order:

1. Fetch PubMed, Europe PMC, and PMC Open Access topic corpora.
2. Build UMLS-derived label, code, and semantic type indexes from local licensed `META` files.
3. Link public corpus text to CUIs.
4. Build public concept documents.
5. Embed concept documents, defaulting to deterministic hashing vectors.
6. Build provenance, MRREL relation, research relation, and MRDEF definition indexes.
7. Run paragraph quality evaluation and precision audit.
8. Write a reproducibility manifest and a reusable server command.

It excludes MIMIC and other real EHR data.

## Why This Improves Things

External users can now run one command instead of manually copying a long sequence of commands from the docs:

```sh
python3 scripts/run_public_rebuild.py --umls-meta /path/to/UMLS/META --out-dir build/public --provider hashing
```

The `--dry-run` mode prints the exact build plan without network calls or file writes, which makes the process reviewable and easier to debug.

## Verification

- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile scripts/run_public_rebuild.py scripts/reproducibility_manifest.py scripts/evaluate_paragraph_quality.py`
- `python3 scripts/run_public_rebuild.py --umls-meta /tmp/UMLS/META --out-dir build/public_dry_run --provider hashing --dry-run`
- `python3 scripts/run_public_rebuild.py --umls-meta /tmp/UMLS/META --out-dir build/public_dry_run --provider sapbert --dry-run`
- `python3 -m pip install -r requirements-public.txt --dry-run`

## Remaining Gap

This was not a full public rebuild because that would require network fetches and a local licensed UMLS `META` directory. The next check should run the wrapper with a small `--max-docs` smoke build against a real local UMLS release.
