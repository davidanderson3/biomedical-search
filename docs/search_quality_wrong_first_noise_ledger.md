# Wrong-First and Noise Ledger

This ledger is the actionable worklist for user-visible trust failures: cases
where the first result is not the clinical target, plus protected rows for noise
classes that were already closed and should not regress.

Machine-readable rows live in
`config/search_quality_wrong_first_noise_ledger.tsv`.

## Current Snapshot

- Seeded: 2026-06-11, SQI-2026-06-11-012.
- Updated: 2026-06-11, SQI-2026-06-11-021.
- Source artifacts: latest rotating smoke
  `SQI-2026-06-11-021_rotating_50_sqi-2026-06-11-021-automated-50-query-smoke`,
  full clinical rerun
  `SQI-2026-06-11-017_full_clinical_objective_condition_alt_sqi-2026-06-11-017-full-clinical-objective-confirmed-condition-a`,
  and source-specific lane
  `SQI-2026-06-11-020_source_specific_generic_screening_sqi-2026-06-11-020-generic-screening-direct-target-ranking`.
- Open observations: 0 reviewed wrong-first rows. The latest source-specific
  lane, latest full clinical benchmark, and latest rotating smoke have no
  reviewed wrong-first examples.
- Closed observations: 11 rows from the original ledger are no longer
  wrong-first on current checks; WFN-013 was closed by SQI-2026-06-11-020 and
  WFN-014 was closed by SQI-2026-06-11-021.
- Protected closed rows: 2 rows for the related-panel yes/no leak and the
  CYP2C19/clopidogrel pharmacogenomic wrong-first fix.

## Open Wrong-First Rows

No reviewed wrong-first rows are currently open.

## Closed Current Rows

| ID | Query ID | Closed behavior | Evidence |
| --- | --- | --- | --- |
| WFN-001 | `paragraph_111` | Gestational Diabetes now outranks Abnormal oral glucose tolerance. | SQI-2026-06-11-013 focused live probe and comparable SQI-2026-06-11-011 rotating seed check. |
| WFN-002 | `paragraph_11` | Structure of right middle cerebral artery is no longer first. | Current full clinical rerun is top-on-target, with Facial Paresis first. |
| WFN-003 | `paragraph_16` | Rheumatoid Factor Measurement is no longer first. | Current full clinical rerun is top-on-target, with Rheumatoid Factor first and Rheumatoid Arthritis at rank 5. |
| WFN-004 | `paragraph_95` | Autoimmune hepatitis now ranks first. | Current full clinical rerun ranks Autoimmune hepatitis first, though the row still has a top-10 miss. |
| WFN-005 | `paragraph_111` | Gestational Diabetes now outranks Glucose tolerance test in the full clinical row. | Current full clinical rerun ranks Gestational Diabetes first with `diagnosis_statement_component` 0.16. |
| WFN-008 | `paragraph_05` | Thyrotoxicosis now outranks heat intolerance and suppressed TSH when the note says `suspected thyrotoxicosis`. | SQI-2026-06-11-014 focused live probe, rotating smoke, and full clinical rerun rank Thyrotoxicosis first with `asserted_diagnosis_component` 0.38. |
| WFN-009 | `paragraph_43` | Anaphylaxis now outranks the bee-sting trigger when the note says the patient developed anaphylaxis after the sting. | SQI-2026-06-11-016 focused live probe, rotating smoke, and full clinical rerun rank Anaphylaxis first with `reaction_diagnosis_component` 0.62; direct `bee sting` search does not boost Anaphylaxis. |
| WFN-010 | `paragraph_87` | Cystic Fibrosis now outranks Chronic Cough when genetic testing confirmed cystic fibrosis. | SQI-2026-06-11-014 focused live probe, rotating smoke, and full clinical rerun rank Cystic Fibrosis first with `asserted_diagnosis_component` 0.40. |
| WFN-011 | `paragraph_91` | Lead Poisoning now outranks Blood lead level above reference range when the sentence says the toddler had lead poisoning after the elevated level. | SQI-2026-06-11-015 focused live probe, rotating smoke, and full clinical rerun rank Lead Poisoning first with `active_diagnosis_component` 0.14; direct `elevated blood lead level` search does not boost Lead Poisoning. |
| WFN-012 | `paragraph_135` | Pulmonary Embolism now outranks Chest Pain when CT angiography shows the embolism in search-style wording. | SQI-2026-06-11-017 focused live probe and full clinical rerun rank Pulmonary Embolism first with `objective_confirmed_condition_component` 0.56; direct `pleuritic chest pain` and `CT angiography` searches do not receive the boost. |
| WFN-013 | `pubmed_pmc_lit_02` | Colonoscopy and Colorectal Carcinoma now outrank broad Screening for cancer in the source-specific literature query. | SQI-2026-06-11-020 source-specific rerun ranks `C0009378` colonoscopy first, `C0009402` Colorectal Carcinoma second, and `C0199230` Screening for cancer fifth; the lane has 0 wrong-first rows. |
| WFN-014 | `paragraph_112` | Explicit opioid-use-disorder treatment anchors now outrank broad Addictive Behavior. | SQI-2026-06-11-021 rotating smoke ranks `C0015846` fentanyl first, `C1169989` buprenorphine / naloxone second, `C0202274` drug screen urine third, and `C0085281` Addictive Behavior sixth; `C4324621` remains a separate recall follow-up. |

## Protected Closed Rows

| ID | Protected behavior | Previous bad result | Gate |
| --- | --- | --- | --- |
| WFN-006 | Cardiology related output must not expose standalone `yes` or `no` answer-value relation labels. | Standalone `no` appeared through related-panel relation paths. | Focused cardiology related-output probes, rotating smoke, and patient-message smoke from SQI-2026-06-11-011. |
| WFN-007 | Pharmacogenomic target/response context should beat incidental background therapy. | Aspirin ranked ahead of the CYP2C19/clopidogrel response target. | Focused PubMed 7-row lane, rotating smoke, and patient-message smoke from SQI-2026-06-11-010. |

## Next Fix Order

1. Add or repair DailyMed warning-context evidence for `C1550014`, the only remaining source-specific top-10 miss.
2. Investigate why promoted `C4324621` Opioid Use Disorder remains absent from the public top 10/20 for `paragraph_112` even though the wrong-first behavior is closed.
3. Keep WFN-001, WFN-006, WFN-007, WFN-008, WFN-009, WFN-010, WFN-011, WFN-012, WFN-013, and WFN-014 in smoke coverage as protected regressions.
