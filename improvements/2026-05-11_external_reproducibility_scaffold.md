# External Reproducibility Scaffold

## Change

- Expanded `scripts/reproducibility_manifest.py` so it inventories local source drops as well as generated artifacts:
  - UMLS `META` files: `MRCONSO.RRF`, `MRSTY.RRF`, `MRREL.RRF`, `MRDEF.RRF`, `MRSAB.RRF`
  - LOINC release files when present locally
  - SNOMED CT release archives when present locally or supplied with `--snomed-zip`
- Added environment metadata, source-input counts, and optional SHA-256 hashing to the manifest.
- Added explicit `--vectors`, `--docs`, and index path overrides to `scripts/evaluate_paragraph_quality.py`.
- Tightened `docs/reproducibility.md` with a public-first build, provenance-index step, source/license boundaries, and an external release checklist.

## Why This Improves Things

External users no longer have to recreate this machine's filenames to evaluate a rebuild. They can rebuild docs/vectors and SQLite indexes in their own `build/public/` directory, point the evaluator at those artifacts, and compare output with the same paragraph benchmark.

The manifest now records the source inputs that determine whether two builds are meaningfully comparable. That is especially important because UMLS, LOINC, SNOMED CT, external CUI vectors, and clinical data cannot all be redistributed with the repo.

## Verification

- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile scripts/reproducibility_manifest.py scripts/evaluate_paragraph_quality.py`
- `python3 scripts/reproducibility_manifest.py --hash-small-files --small-file-limit 1000000 --out build/reproducibility_manifest_smoke.json`
  - listed artifacts: 24
  - present artifacts: 24
  - source inputs listed: 6
  - source inputs present: 6
- `python3 scripts/evaluate_paragraph_quality.py --help` confirms explicit artifact and index path overrides are available.

## Remaining Gap

This makes the build auditable and easier to reproduce, but it does not yet provide a one-command public rebuild. The next sustainable improvement would be a small wrapper script or make target that runs the public-first build steps and writes a manifest at the end.
