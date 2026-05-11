# Broader paragraph coverage

## Why

The paragraph benchmark was strong on the existing 80 clinical examples, but it was concentrated around common adult inpatient medicine. I added a broader test slice to expose weak areas before more ranking changes are made.

## Added Coverage

Added 16 paragraphs to `config/search_quality_paragraph_queries.tsv` and `docs/search_quality/paragraphs.json`:

- Toxicology: acetaminophen overdose, acute liver failure, acetylcysteine.
- Neonatology: neonatal jaundice, bilirubin, phototherapy.
- Dental/oral infection: dental abscess, incision and drainage, amoxicillin-clavulanate.
- Burns: second-degree burn, silver sulfadiazine, tetanus vaccine.
- Dermatologic oncology: cutaneous melanoma, skin biopsy, sentinel lymph node biopsy, pembrolizumab.
- Hematologic oncology: acute myeloid leukemia, bone marrow biopsy, cytarabine.
- Genetics/pulmonology: cystic fibrosis, pancreatic insufficiency, sweat chloride test, ivacaftor.
- Obstetrics: postpartum hemorrhage, uterine atony, oxytocin, transfusion.
- Vascular medicine: peripheral arterial disease, ankle-brachial index, cilostazol.
- Psychiatry: bipolar disorder, mania, lithium, valproate.
- Environmental pediatrics: lead poisoning, blood lead level, chelation therapy.
- Audiology/devices: hearing loss, audiometry, cochlear implant.
- Wound care: pressure ulcer, sacral ulcer, wound debridement.
- Critical care: acute respiratory distress syndrome, mechanical ventilation, prone positioning.
- Autoimmune liver disease: autoimmune hepatitis, antinuclear antibodies, smooth muscle antibody, prednisone.
- Gynecology: endometriosis, dysmenorrhea, laparoscopy.

## Follow-up Cleanup

- Added active-label supplement anchors for central exact concepts exposed by the new paragraphs: acetaminophen overdose, phototherapy, dental abscess, skin biopsy, sentinel lymph node biopsy, ivacaftor, cochlear implant, sacral pressure ulcer, and prednisone.
- Corrected the dental paragraph expected CUI from generic `C0184661` (`Procedure`) to `C0152277` (`Incision and drainage`).

## Result

Initial expanded benchmark:

- Paragraphs: `96`
- Expected concepts: `467`
- Recall@10: `457/467` (`0.9786`)
- Recall@20: `462/467` (`0.9893`)
- Verdicts: `86 good`, `9 mixed`, `1 poor`

After anchor cleanup:

- Recall@10: `466/467` (`0.9979`)
- Recall@20: `467/467` (`1.0`)
- Recall@5: `349/467` to `357/467`
- Verdicts: `91 good`, `5 mixed`, `0 poor`
- Expected semantic group recall@10: `1.0`

## Remaining Gaps

The remaining mixed cases have all expected concepts in the top 10, but top-ranked results are not always ideal:

- Dental abscess paragraph ranks `Toothache` above `Dental abscess`.
- Peripheral arterial disease paragraph ranks `Intermittent Claudication` above the central disease.
- Lead poisoning paragraph ranks `Blood lead level above reference range` above `Lead Poisoning`.
- ARDS paragraph ranks well overall but includes generic/improvement/tidal-volume concepts ahead of some desired procedure concepts.
- Autoimmune hepatitis paragraph incorrectly ranks generic `Hepatitis A` and `Hepatitis` above `Autoimmune hepatitis`.

## Verification

- `python3 scripts/validate_active_label_supplement.py`
- `python3 -m pytest tests/test_evidence_vectors.py -k 'active_label_supplement_file_passes_sustainability_validation or active_label_supplement_validation_rejects_unsafe_nonpreferred_abbreviation' -q`
- `python3 scripts/evaluate_paragraph_quality.py --output-dir build/improvements/2026-05-08_added_broader_paragraphs_after_anchor_cleanup --top-k 60`
