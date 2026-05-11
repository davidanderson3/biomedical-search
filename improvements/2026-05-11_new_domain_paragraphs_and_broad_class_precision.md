# New Domain Paragraphs and Broad-Class Precision

## Change

Added 10 new paragraph benchmarks covering immunotherapy toxicity, sarcoidosis, endocrine surgery, neonatology, gestational diabetes, addiction medicine, renal vasculitis, prostate oncology, spondyloarthritis, and interstitial lung disease. Calibrated acceptable alternatives for clinically equivalent CUIs such as pulmonary surfactants, low oxygen saturation, fetal macrosomia, buprenorphine-naloxone, withdrawal symptoms, and HLA-B27 antigen measurement.

Added one active label supplement for `fasting glucose -> C0392201` so gestational diabetes paragraphs can retrieve the blood glucose measurement concept from common clinical wording. Added useful-extra annotations for explicit but non-target concepts such as right heart anatomy, post-void residual urine volume, kidney biopsy, inflammatory back pain, HLA-B gene context, and progressive pulmonary fibrosis.

Refined ranking so generic diabetes is demoted in gestational diabetes context, standalone `immune-mediated` and `risks and benefits` modifiers are filtered in richer clinical paragraphs, and broad drug-class words such as `opioid` and `androgen` do not receive exact ingredient-style boosts when they are just components of more specific phrases like `opioid use disorder` or `androgen deprivation therapy`.

## Measured Impact

Before calibration on the expanded 116-paragraph suite:

- `paragraphs`: 116
- `expected_concepts`: 570
- `recall_at_10`: 98.6%
- `verdict_counts`: 112 good, 4 mixed
- calibrated precision audit: 15 suspect top-10 hits

After calibration and ranker changes:

- `paragraphs`: 116
- `expected_concepts`: 570
- `recall_at_10`: 100.0%
- `recall_at_20`: 100.0%
- `queries_all_expected_at_10`: 116/116
- `verdict_counts`: 116 good
- calibrated precision audit: 2 suspect top-10 hits
- visible top-3 nonexpected suspects: 0

## Remaining Issues

Two low-rank audit flags remain: `systemic symptoms` in an influenza paragraph and generic `Diabetes Mellitus` in a gestational diabetes paragraph. Both are already penalized and appear at rank 10, so they are lower priority than adding more domain coverage or improving source-derived relationship evidence.

## Verification

- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py`
- `python3 -m pytest tests/test_evidence_vectors.py -k "broad_drug_classes"`
- `python3 scripts/evaluate_paragraph_quality.py --output-dir build/improvements/2026-05-11_new_domain_paragraphs_classword_fix_after --top-k 60`
- `python3 scripts/audit_paragraph_precision.py --payloads build/improvements/2026-05-11_new_domain_paragraphs_classword_fix_after/paragraph_search_payloads.jsonl --output-dir build/improvements/2026-05-11_new_domain_paragraphs_classword_fix_after --top-n 10`
