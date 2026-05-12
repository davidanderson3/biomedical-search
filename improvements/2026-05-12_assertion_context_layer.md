# Assertion Context Layer

## Problem

The search ranker already handled some denial behavior, but result metadata did not consistently expose whether a concept mention was current, negated, uncertain, historical, family-history, planned, or confirmed. That made paragraph results easier to misread in cases such as `no pulmonary embolism`, `rule out meningitis`, `prior stroke with current facial droop`, and planned-but-not-yet-performed procedures.

The goal was not a full NLP assertion engine. The useful next step was a lightweight ConText-style layer that annotates and modestly down-ranks non-current mentions without hiding clinically relevant concepts.

## Change

- Added `src/qe_evidence_vectors/search_assertions.py` with scoped cue detection for:
  - `current`
  - `negated`
  - `uncertain`
  - `historical`
  - `family_history`
  - `planned`
  - `confirmed`
- Attached `assertion` metadata to ranked hits and mirrored it into `score_breakdown.assertion`.
- Added `assertion_context_penalty` for uncertain, historical, and planned mentions where the semantic type makes that distinction meaningful.
- Preserved existing denial-specific penalties for positive findings in negated spans.
- Added scope guards so historical/planned cues do not leak across terms like `current`, `acute`, `confirmed`, or across contrastive boundaries.
- Added UI display support so non-current assertion status appears as a result chip and in signal deductions.

## Results

Focused regression tests:

- Negated: `No evidence of pulmonary embolism...` marks pulmonary embolism as `negated`.
- Uncertain: `Rule out meningitis...` marks meningitis as `uncertain` and applies an assertion-context penalty.
- Historical/current split: `Prior stroke with current facial droop` marks stroke as `historical` and facial droop as `current`.
- Planned: `Endoscopy was planned...` marks endoscopy as `planned`.
- Confirmed: `Blood culture grew MRSA` marks MRSA as `confirmed`.

Full paragraph evaluation after tuning:

- Paragraphs: 148
- Expected concepts: 743
- Verdicts: 148 good
- Recall@5: 567/743 (76.3%)
- Recall@10: 741/743 (99.7%)
- Recall@20: 743/743 (100.0%)
- Known false positives@10: 0/148

Precision audit:

- Suspect top-10 hits: 27
- Suspect hits per paragraph: 0.182

The precision-audit increase is not from new obvious false positives. The top additions include useful but unannotated clinical concepts such as `levetiracetam` and `Fecal occult blood: positive`, which should be handled by expected/useful-extra annotations rather than suppression.

## Verification

```bash
python3 -B -m pytest tests/test_evidence_vectors.py -k "assertion_context or planned_and_confirmed_assertions or positive_findings_in_denial_context or ordinary_word_artifacts or admin_review_when_review_word" -q
PYTHONPYCACHEPREFIX=/private/tmp/query-expansion-pycache python3 -m py_compile src/qe_evidence_vectors/search_assertions.py src/qe_evidence_vectors/search_ranking.py src/qe_evidence_vectors/search_types.py src/qe_evidence_vectors/search_hydration.py
python3 -B scripts/evaluate_paragraph_quality.py --output-dir build/improvements/2026-05-12_assertion_context_paragraph_eval_final --top-k 60
python3 -B scripts/audit_paragraph_precision.py --payloads build/improvements/2026-05-12_assertion_context_paragraph_eval_final/paragraph_search_payloads.jsonl --output-dir build/improvements/2026-05-12_assertion_context_precision_final --top-n 10
```
