# Wrong-First Noise Ledger Seed

## Problem

The progress log named the next P0 task as a compact wrong-first/noise ledger,
but the remaining failures were still spread across benchmark prose and run
artifacts. That made the next ranking fix less reviewable: each case needed an
expected top concept, actual bad concept, source path, cause, fix class, and
regression query.

## Change

- Added `config/search_quality_wrong_first_noise_ledger.tsv` as the
  machine-readable ledger.
- Added `docs/search_quality_wrong_first_noise_ledger.md` as the readable audit
  summary.
- Seeded the ledger from the latest rotating 50-query smoke and the full
  clinical 168-row rerun.
- Added protected closed rows for the cardiology related-panel yes/no fix and
  the CYP2C19/clopidogrel pharmacogenomic wrong-first fix.

## Result

The open P0 work is now explicit:

- `paragraph_111`: gestational diabetes should outrank abnormal/glucose
  tolerance test concepts.
- `paragraph_11`: acute infarct/stroke problem should outrank MCA anatomy.
- `paragraph_16`: rheumatoid arthritis should outrank rheumatoid factor
  measurement.
- `paragraph_95`: autoimmune hepatitis should outrank smooth muscle antibody
  measurement in the full clinical rerun, pending confirmation on a fresh
  168-row rerun.

This iteration intentionally did not change runtime ranking behavior.

## Verification

- TSV schema/readability check for
  `config/search_quality_wrong_first_noise_ledger.tsv`.
- HTML parser check for `docs/search_quality_progress_log.html`,
  `docs/search_quality_iterations.html`, and `docs/search_quality_experiments.html`.
- Inline JavaScript syntax check for `docs/search_quality_iterations.html`.

## Decision

Keep. The next ranking iteration should start with the shared
diagnosis-over-test-result pattern in WFN-001/WFN-005, then rerun the rotating
and full clinical gates.
