# Opioid-use-disorder context over broad addiction behavior

## Problem

The SQI-2026-06-11-020 rotating smoke found `paragraph_112` as a fresh
wrong-first row. The query explicitly described opioid-use-disorder treatment
after fentanyl use, withdrawal symptoms, buprenorphine/naloxone initiation, and
a urine drug screen, but the first result was broad `C0085281` Addictive
Behavior because it matched the specialty word `addiction`.

## Change

Added a narrow clinical-context sense penalty for broad addiction-behavior
labels when the query has specific opioid-use-disorder, fentanyl/withdrawal, or
buprenorphine/naloxone context. The rule does not suppress addiction concepts
globally; it only prevents broad behavior labels from outranking the explicit
substance, treatment, testing, and withdrawal anchors in this context.

## Verification

- Focused ranker tests: 3 passed.
- Live paragraph probe: `C1169989` buprenorphine/naloxone ranked first and
  `C0085281` Addictive Behavior moved to rank 6.
- SQI-2026-06-11-021 smoke helper passed static, focused, standing clinical,
  rotating 50-query, and patient-portal gates.
- The SQI-2026-06-11-021 rotating smoke included `paragraph_112`; it now ranks
  `C0015846` fentanyl first and has 0 wrong-first rows overall.

## Remaining Gap

`C4324621` Opioid Use Disorder is still missing at top 10/20 for the public
search payload even though linked-concept promotion reports it. Treat that as a
separate active-label/public-result recall issue, not as closed by this ranking
fix.
