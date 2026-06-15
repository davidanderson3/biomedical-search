# SQI-2026-06-11-022 PubMed approved long-document baseline

## Problem

`SQB-002 Long-document survival` had a stale approved PubMed baseline: the
progress log still cited the 2026-06-10 result at 3/13 rows complete and 44/60
expected concepts at top 10, while the focused 7-row PubMed probe had already
been fixed to 36/36 top-10 recall.

## What changed

No runtime ranking code changed. The approved 13-abstract PubMed suite was
rerun against the live Elasticsearch-backed API, and every remaining mixed row
was classified by fix class.

Current baseline:

- 13 approved PubMed abstracts.
- 9/13 rows complete at top 10.
- 53/60 expected concepts at top 10.
- 57/60 expected concepts at top 20 and top 60.
- 11/13 top-on-target.
- 2 wrong-first rows.
- 4 mixed rows, 0 poor rows.
- Overall score 75.6.
- Runtime 404.176 seconds.

## Miss taxonomy

| Row | Miss or bad first result | Evidence | Fix class |
| --- | --- | --- | --- |
| `pubmed_status_migrainosus_30198804` | `C0154723` Migraine with Aura and `C0338480` Common Migraine are outside top 10; broad `C0001617` Adrenal Cortex Hormones ranks first. | `C3808875` Migraine, with or without aura is rank 12, `C0338480` rank 13, and `C0154723` rank 15. Status Migrainosus is rank 9, NSAIDs rank 2, magnesium sulfate rank 3. | Present by top 20 but lost during first-page merge/rerank; also needs wrong-first suppression for broad corticosteroid class over the disease/treatment anchors. |
| `pubmed_egfr_nsclc_37879444` | `C0242792` Progression-Free Survival is outside top 10; `C4058811` Osimertinib and `C0032207` platinum are absent from top 60. | Progression-Free Survival is rank 18. The abstract explicitly says progression on osimertinib, but neither `C4058811` nor accepted alternative `C4058829` appears in top 60. `C4526551` Carboplatin/Pemetrexed Regimen ranks 5 for the platinum-chemotherapy wording. | Mixed: PFS is present by top 20 but lost during first-page merge/rerank; Osimertinib is an absent candidate/linking miss; platinum likely needs benchmark-equivalence review against the regimen concept. |
| `pubmed_cdiff_antibiotic_diarrhea_21288078` | `C0343386` Clostridium difficile infection is outside top 10; `C0360373` vancomycin Oral Product ranks first. | Vancomycin is rank 2, Diarrhea is rank 9, and Clostridium difficile infection is rank 16. The top result is an overqualified oral-product form of the expected vancomycin anchor. | Present by top 20 but lost during first-page merge/rerank; also needs overqualified medication-form equivalence or suppression so the ingredient and infection anchors are not hidden. |
| `pubmed_lupus_preeclampsia_8659509` | `C0009506` Complement 3 is absent from top 60. | The title-only record says `hypocomplementemia`, not C3/C4. Proteinuria ranks first and no Complement 3 equivalent appears in the public top 60. | Overqualified benchmark target or absent terminology support; review whether the target should be hypocomplementemia, or add curated evidence only if C3 is intentionally implied. |

## Verification

Command:

```sh
PYTHONPATH=src python3 scripts/run_search_quality_experiment.py \
  --label "SQI-2026-06-11-022 approved PubMed long-document baseline" \
  --run-id SQI-2026-06-11-022_pubmed_approved_baseline \
  --run-family probe \
  --queries build/pubmed_literature_benchmark_seed/pubmed_literature_approved_queries.tsv \
  --query-limit 0 \
  --base-url http://127.0.0.1:8766 \
  --require-api-backend elasticsearch \
  --scope umls_evidence \
  --mode balanced \
  --search-system api \
  --top-k 60 \
  --timeout 180 \
  --output-root build/search_quality_experiments \
  --html-report docs/search_quality_experiments.html
```

Artifacts:

- `build/search_quality_experiments/runs/SQI-2026-06-11-022_pubmed_approved_baseline_sqi-2026-06-11-022-approved-pubmed-long-document-baseline/metrics.json`
- `build/search_quality_experiments/runs/SQI-2026-06-11-022_pubmed_approved_baseline_sqi-2026-06-11-022-approved-pubmed-long-document-baseline/rows.tsv`
- `build/search_quality_experiments/runs/SQI-2026-06-11-022_pubmed_approved_baseline_sqi-2026-06-11-022-approved-pubmed-long-document-baseline/payloads/`
- `docs/search_quality_experiments.html`

Post-update checks:

- HTML parser checks passed for `docs/search_quality_progress_log.html`,
  `docs/search_quality_iterations.html`, and
  `docs/search_quality_experiments.html`.
- Extracted `docs/search_quality_iterations.html` JavaScript passed
  `node --check`.
- SQI-022 metrics assertions passed against `metrics.json` and `rows.tsv`.
- `git diff --check` passed for touched source/report files.
- No API restart or broad smoke was needed because no runtime code, ranking
  rule, benchmark definition, or source data changed.

## Next action

Keep `SQB-002` at P0. Start with the two wrong-first rows:

1. Decide whether `C0360373` vancomycin Oral Product should be an acceptable
   alternative for the expected vancomycin anchor or should be demoted below
   the ingredient/infection anchors.
2. Add a narrow broad-corticosteroid class guard for status-migrainosus
   treatment abstracts if it can be protected against direct corticosteroid
   searches.

Then address first-page recall for the top-20 misses and review the two
absent or overqualified targets in the EGFR and hypocomplementemia rows.
