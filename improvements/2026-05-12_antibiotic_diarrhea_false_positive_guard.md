# Antibiotic Diarrhea False-Positive Guard

## Problem

The search `He reports watery diarrhea after recent antibiotic use.` could show unrelated broad oncology/drug concepts such as `Antineoplastic Agents`, plus unrelated temporal phrase matches such as `Enhanced Recovery After Surgery`. The issue was not that these concepts were text mentions. They were entering through broad vector/relation evidence and weak lexical anchors, while the paragraph benchmark mostly measured recall of expected CUIs and did not fail when a known bad CUI appeared in the first page.

## Change

- Added active labels for `C0578159` antibiotic-associated diarrhea using common patient/search wording: `diarrhea after antibiotic use` and `watery diarrhea after antibiotic use`.
- Added an antibiotic-diarrhea context penalty for oncology treatment/drug-class labels such as antineoplastic/chemotherapy unless the query also has oncology context.
- Treated temporal/pronoun terms such as `after`, `before`, `while`, `he`, `she`, `they`, and `their` as low-specificity rank anchors so unrelated concepts cannot satisfy coverage just because the query contains prose timing.
- Extended paragraph evaluation TSV support with optional `disallowed_cuis`, and added the antibiotic-diarrhea paragraph with disallowed `C0003392`, `C0362063`, and `C5197734`.

## Result

Targeted query after the change:

- `Antibiotics`, `Diarrhea`, `Watery diarrhoea`, and `Antibiotic-associated diarrhea` are the top useful results.
- The configured false positives are absent from the top 20.

Full paragraph evaluation with UI-sized candidate pool:

- 141 paragraphs, 705 expected concepts.
- Recall@10: 702/705 (99.6%).
- Recall@20: 705/705 (100.0%).
- Known false positives@10: 0/141.
- Known false positives@20: 0/141.
- Verdicts: 140 good, 1 mixed. The remaining mixed row is `paragraph_130` because `Blood culture` is at rank 11 rather than top 10.

## Verification

- `python3 scripts/evaluate_paragraph_quality.py --queries /private/tmp/antibiotic_diarrhea.tsv --output-dir build/improvements/2026-05-12_antibiotic_diarrhea_after_low_specificity --top-k 60 --candidate-pool-multiplier 3 --candidate-pool-min 50`
- `python3 scripts/evaluate_paragraph_quality.py --output-dir build/improvements/2026-05-12_antibiotic_diarrhea_full_final --top-k 60 --candidate-pool-multiplier 3 --candidate-pool-min 50`
- `python3 -B -m pytest tests/test_evidence_vectors.py -k "antibiotic_diarrhea or false_positives or reads_query_tsv or active_label_supplement" -q`
- `PYTHONPYCACHEPREFIX=/private/tmp/query-expansion-pycache python3 -m py_compile src/qe_evidence_vectors/search_ranking.py scripts/evaluate_paragraph_quality.py scripts/evaluate_search_api.py`

The full `tests/test_evidence_vectors.py` suite was also run, but it still has unrelated existing failures in older ranker/cutoff and fixture expectations. The changed-path focused tests pass.
