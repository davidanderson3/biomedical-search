# Search Quality Script Index

Index-only category. Executable entrypoints remain at `../<script>.py` so
existing command references keep working.

- `../run_search_quality_suite.py` - repeatable suite runner for static checks,
  full clinical coverage, rotating regression samples, portal intent, and
  PubMed long-document weakness probes.
- `../run_search_quality_experiment.py` - experiments, report updates, and
  post-iteration smoke gates.
- `../evaluate_search_api.py` - standing clinical API smoke and search
  evaluation.
- `../run_search_regression_benchmark.py` - regression benchmark runner.
- `../evaluate_paragraph_quality.py` - paragraph quality evaluation.
- `../audit_paragraph_precision.py` - visible precision-audit queue generation.
- `../build_precision_audit_report.py` - reviewed precision-audit report.
- `../analyze_search_judgments.py` - canonical judgment file analysis.
- `../search_quality_shadow_reranker.py` - feature extraction, shadow reranker,
  and current-vs-ML rank report.
- `../build_search_rule_inventory.py` - heuristic/rule inventory report.
- `../validate_active_label_supplement.py` - active-label supplement validation.
