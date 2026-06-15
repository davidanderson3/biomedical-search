# Search Quality Precision Audit Review

This report closes SQI-2026-06-10-005. It classifies the visible precision-audit queue so future ranking work can distinguish useful secondary concepts from true false positives.

## Source Artifacts

- Review ledger: `config/search_quality_precision_audit_review.tsv`
- Applied useful extras: `config/search_quality_useful_extra_cuis.tsv`
- Current raw audit queue: `build/search_quality_live_audit/paragraph_precision_audit.tsv`
- Post-review residual audit: `build/search_quality_live_audit_reviewed/paragraph_precision_audit.tsv`

## Classification Summary

| Class | Rows | Meaning |
| --- | --- | --- |
| expected | 0 | Central enough to promote into the expected CUI set. |
| useful_extra | 58 | Explicitly useful secondary concept; should not count as a false positive. |
| true_false_positive | 11 | Wrong, misleading, overbroad, contradictory, or metadata-like result. |

| Action | Rows |
| --- | --- |
| add_useful_extra | 58 |
| keep_rule_candidate | 11 |

## Queue Reconciliation

- Reviewed rows: 69
- Current raw suspect rows: 69
- Post-review residual suspect rows: 11
- Useful-extra review rows missing from useful-extra config: 0
- Current raw suspect rows missing review classification: 0
- Reviewed rows not present in current raw queue: 0

Earlier planning text referred to 70 suspect rows. The current generated raw audit queue contains 69 rows, and all 69 have review classifications. This report records the current reproducible state rather than preserving the stale count.

## Residual True False Positives

| Query | CUI | Label | Why |
| --- | --- | --- | --- |
| paragraph_08 | C2926613 | Chest pain | Generic clinical-attribute chest pain duplicate; paragraph denies pleuritic chest pain and tests pulmonary embolus/right-heart strain. |
| paragraph_15 | C1369672 | Oncology Note | Note-type artifact from oncology note text; not a biomedical concept to reward. |
| paragraph_36 | C0004936 | Mental disorders | Unanchored broad mental-disorders vector drift; specific depression, insomnia, and suicidal ideation concepts are useful targets. |
| paragraph_49 | C0235304 | Acid indigestion | Unanchored acid-indigestion drift in GERD, Barrett, and dysphagia paragraph. |
| paragraph_61 | C0021403 | Influenza virus vaccine | Vaccine concept from influenza infection wording; infection paragraph should not surface vaccine as a top result. |
| paragraph_69 | C2707266 | Vision | Generic clinical-attribute vision concept; cataract, blurred vision, and procedure concepts carry useful meaning. |
| paragraph_80 | C0272078 | Hemoglobin SS disease without crisis | Contradictory unanchored sickle-cell-without-crisis subtype in vaso-occlusive crisis paragraph. |
| paragraph_94 | C0231832 | Respiratory rate | Respiratory-rate attribute is a broad fragment from respiratory wording, not a target ARDS or ventilation concept. |
| paragraph_135 | C2926613 | Chest pain | Generic clinical-attribute chest pain duplicate; disease/symptom CUI carries useful pleuritic chest pain meaning. |
| paragraph_141 | C0740441 | Acute diarrhea | Unanchored acute-diarrhea vector drift; base diarrhea and antibiotic-associated diarrhea are already expected or acceptable. |
| paragraph_141 | C3842347 | Diarrhea/constipation | Unanchored diarrhea-constipation aggregate drift; base diarrhea is already expected. |

## Verification

- The review ledger uses only allowed classes: `expected`, `useful_extra`, and `true_false_positive`.
- Every `useful_extra` review row is present in `config/search_quality_useful_extra_cuis.tsv`.
- The current raw audit queue is fully covered by the review ledger.
- The post-review residual audit contains the 11 true-false-positive candidates.

## Next

Keep these 11 residual false positives as ranking/suppression targets. Do not tune ranking against useful-extra rows as though they were false positives.
