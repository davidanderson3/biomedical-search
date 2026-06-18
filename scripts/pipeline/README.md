# Pipeline Script Index

Index-only category. Executable entrypoints remain at `../<script>.py` so
existing command references keep working.

- `../evidence_vectors.py` - main evidence/vector pipeline CLI.
- `../run_public_rebuild.py` - public/shareable rebuild wrapper.
- `../run_existing_data_iteration.py` - existing-data/new-UMLS iteration runner.
- `../reproducibility_manifest.py` - local source and artifact manifest.
- `../source_acquisition_progression.py` - source acquisition progression checks.
- `../check_source_rebuild_delta.py` - source rebuild delta check.
- `../scaling_status.py` - scaling/build status summary.
- `../sitecustomize.py` - local Python startup hook that suppresses urllib3 LibreSSL warnings for direct script runs.
