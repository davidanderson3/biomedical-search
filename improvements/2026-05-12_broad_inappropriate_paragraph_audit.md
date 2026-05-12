# Broad/Inappropriate Paragraph Audit

## Problem

The paragraph test set was strong on expected recall but still missed some high-ranking concepts that should never be useful for ordinary clinical paragraph search. Examples included administrative/research artifacts from words like `review`, confirmation-status findings from `confirmed`, broad classes like `Antineoplastic Agents` for antibiotic diarrhea, and ordinary-word artifacts from phrases like `chart review` or `source control`.

Those failures were under-tested because most paragraph checks only asserted that expected concepts appeared. They did not consistently fail when an unrelated but high-ranking result appeared beside the good concepts.

## Change

- Added realistic paragraph tests for medication review, anticoagulation review, antibiotic-associated diarrhea, MRSA sepsis/source control, COPD chart review, and confirmed cellulitis/abscess.
- Added disallowed CUI assertions for known inappropriate concepts, including peer-review/admin-review artifacts, confirmation-status findings, broad bacteria, antineoplastic agents, chart-device artifacts, source/control fragments, and generic comparison/status concepts.
- Added a focused regression test for ordinary-word artifacts in clinical prose.
- Expanded the audited generic suppression list for concepts that behave like prose tokens rather than useful biomedical anchors: `chart [medical device]`, `Source`, `control aspects`, `True Control Status`, `CONTROL veterinary product`, `Greater Than`, `Needs`, `Restart`, and `Intimate`.
- Added a COPD exacerbation acceptable-alternative mapping so the paragraph evaluator does not penalize a more specific COPD exacerbation CUI.

## Results

Baseline on the old 142-paragraph set:

- Paragraphs: 142
- Expected concepts: 711
- Recall@10: 709/711 (99.7%)
- Recall@20: 711/711 (100.0%)
- Known false positives@10: 0/142

After adding the harder paragraphs, before the new suppression:

- Paragraphs: 148
- Expected concepts: 741
- Verdicts: 145 good, 3 mixed
- Recall@10: 738/741 (99.6%)
- Recall@20: 740/741 (99.9%)
- Precision-audit suspect hits: 31 top-10 hits, 0.209 per paragraph

Final after mitigation:

- Paragraphs: 148
- Expected concepts: 743
- Verdicts: 148 good
- Recall@10: 741/743 (99.7%)
- Recall@20: 743/743 (100.0%)
- Known false positives@10: 0/148
- Known false positives@20: 1/148
- Precision-audit suspect hits: 25 top-10 hits, 0.169 per paragraph

The remaining precision-audit suspects are mostly not obvious "never return" artifacts. Many are specific clinical concepts that were not in the expected-CUI list, such as `Atrial fibrillation with rapid ventricular response`, `Tearing Chest Pain`, `Cold foot`, `Recurrent falls`, and `Acute Ischemic Stroke`. These are better handled by expanding expected/useful-extra annotations rather than blanket suppression.

## Verification

```bash
python3 -B -m pytest tests/test_evidence_vectors.py -k "ordinary_word_artifacts or admin_review_when_review_word or generic_prose_status or confirmation_status or broad_bacteria" -q
python3 -B scripts/evaluate_paragraph_quality.py --output-dir build/improvements/2026-05-12_broad_inappropriate_paragraph_eval_final3 --top-k 60
python3 -B scripts/audit_paragraph_precision.py --payloads build/improvements/2026-05-12_broad_inappropriate_paragraph_eval_final3/paragraph_search_payloads.jsonl --output-dir build/improvements/2026-05-12_broad_inappropriate_precision_final3 --top-n 10
```
