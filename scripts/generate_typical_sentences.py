#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path


TOPIC_FIELDS = [
    "domain",
    "focus",
    "condition",
    "symptom",
    "finding",
    "test",
    "result",
    "treatment",
    "procedure",
    "complication",
]


TOPIC_ROWS = [
    ("cardiology", "atrial fibrillation", "atrial fibrillation", "palpitations", "irregularly irregular rhythm", "electrocardiogram", "atrial fibrillation with rapid ventricular response", "metoprolol", "electrical cardioversion", "stroke risk"),
    ("cardiology", "heart failure", "heart failure with reduced ejection fraction", "orthopnea", "bibasilar crackles", "echocardiogram", "reduced ejection fraction", "furosemide", "diuresis", "volume overload"),
    ("cardiology", "acute coronary syndrome", "non ST elevation myocardial infarction", "substernal chest pressure", "elevated troponin", "coronary angiography", "critical coronary stenosis", "heparin infusion", "percutaneous coronary intervention", "recurrent ischemia"),
    ("pulmonary", "pneumonia", "community acquired pneumonia", "productive cough", "right lower lobe crackles", "chest radiograph", "right lower lobe infiltrate", "ceftriaxone and azithromycin", "sputum culture", "hypoxemia"),
    ("pulmonary", "asthma exacerbation", "asthma", "wheezing", "prolonged expiratory phase", "peak flow measurement", "reduced peak expiratory flow", "albuterol nebulizer", "spirometry", "respiratory distress"),
    ("pulmonary", "pulmonary embolism", "acute pulmonary embolism", "pleuritic chest pain", "unilateral leg swelling", "computed tomography angiography", "segmental pulmonary embolus", "apixaban", "venous duplex ultrasound", "right heart strain"),
    ("gastroenterology", "diverticulitis", "acute uncomplicated diverticulitis", "left lower quadrant pain", "localized abdominal tenderness", "computed tomography abdomen", "sigmoid diverticulitis", "amoxicillin clavulanate", "colonoscopy follow up", "perforation"),
    ("gastroenterology", "gastrointestinal bleeding", "upper gastrointestinal bleeding", "melena", "orthostatic hypotension", "upper endoscopy", "bleeding gastric ulcer", "intravenous pantoprazole", "endoscopic hemostasis", "acute blood loss anemia"),
    ("gastroenterology", "clostridioides difficile infection", "clostridioides difficile colitis", "watery diarrhea", "diffuse abdominal cramping", "stool toxin assay", "positive C difficile toxin", "oral vancomycin", "contact isolation", "toxic megacolon"),
    ("endocrinology", "type 2 diabetes", "poorly controlled type 2 diabetes mellitus", "polyuria", "elevated hemoglobin A1c", "hemoglobin A1c", "A1c above goal", "metformin and insulin glargine", "diabetes education", "diabetic neuropathy"),
    ("endocrinology", "hypoglycemia", "insulin associated hypoglycemia", "diaphoresis and tremor", "low fingerstick glucose", "point of care glucose", "glucose of 48 mg per dL", "oral glucose", "insulin dose adjustment", "loss of consciousness"),
    ("endocrinology", "thyrotoxicosis", "hyperthyroidism", "heat intolerance", "fine tremor", "thyroid stimulating hormone", "suppressed TSH", "methimazole", "thyroid uptake scan", "atrial arrhythmia"),
    ("nephrology", "acute kidney injury", "acute kidney injury", "decreased urine output", "rising creatinine", "basic metabolic panel", "creatinine above baseline", "intravenous fluids", "renal ultrasound", "electrolyte abnormality"),
    ("nephrology", "chronic kidney disease", "stage three chronic kidney disease", "fatigue", "albuminuria", "urine albumin creatinine ratio", "elevated albumin creatinine ratio", "blood pressure control", "nephrology referral", "progressive renal disease"),
    ("nephrology", "hyperkalemia", "hyperkalemia", "muscle weakness", "peaked T waves", "serum potassium", "potassium of 6.2 mmol per L", "calcium gluconate", "repeat potassium measurement", "cardiac arrhythmia"),
    ("urology", "urinary tract infection", "acute cystitis", "dysuria", "suprapubic tenderness", "urinalysis", "positive leukocyte esterase", "nitrofurantoin", "urine culture", "pyelonephritis"),
    ("urology", "benign prostatic hyperplasia", "benign prostatic hyperplasia", "weak urinary stream", "enlarged prostate", "post void residual", "elevated residual urine volume", "tamsulosin", "prostate examination", "urinary retention"),
    ("neurology", "ischemic stroke", "acute ischemic stroke", "left sided weakness", "facial droop", "brain MRI", "acute infarct in right MCA territory", "aspirin and statin", "thrombolysis evaluation", "persistent neurologic deficit"),
    ("neurology", "seizure", "generalized tonic clonic seizure", "postictal confusion", "tongue biting", "electroencephalogram", "epileptiform discharges", "levetiracetam", "seizure precautions", "status epilepticus"),
    ("neurology", "migraine", "migraine headache", "photophobia", "normal neurologic examination", "head CT", "no acute intracranial process", "sumatriptan", "headache diary", "medication overuse headache"),
    ("psychiatry", "major depression", "major depressive disorder", "low mood", "flat affect", "PHQ 9 questionnaire", "severe depressive symptoms", "sertraline", "behavioral health referral", "suicidal ideation"),
    ("psychiatry", "alcohol withdrawal", "alcohol withdrawal syndrome", "tremulousness", "tachycardia", "CIWA assessment", "elevated withdrawal score", "lorazepam", "withdrawal monitoring", "seizure risk"),
    ("infectious disease", "sepsis", "sepsis due to cellulitis", "fever and malaise", "hypotension", "blood culture", "gram positive cocci in clusters", "broad spectrum antibiotics", "source control", "septic shock"),
    ("infectious disease", "osteomyelitis", "diabetic foot osteomyelitis", "foot ulcer drainage", "exposed bone", "foot MRI", "marrow edema concerning for osteomyelitis", "vancomycin", "bone biopsy", "amputation risk"),
    ("dermatology", "psoriasis", "plaque psoriasis", "itchy rash", "silvery scale", "skin examination", "erythematous plaques on extensor surfaces", "topical corticosteroid", "dermatology follow up", "joint pain"),
    ("dermatology", "herpes zoster", "herpes zoster", "burning dermatomal pain", "vesicular rash", "clinical skin examination", "unilateral dermatomal vesicles", "valacyclovir", "pain control", "postherpetic neuralgia"),
    ("musculoskeletal", "osteoarthritis", "knee osteoarthritis", "knee pain with stairs", "crepitus", "knee radiograph", "tricompartmental degenerative changes", "acetaminophen", "intra articular steroid injection", "limited mobility"),
    ("musculoskeletal", "hip fracture", "femoral neck fracture", "inability to bear weight", "shortened externally rotated leg", "hip radiograph", "displaced femoral neck fracture", "pain control", "operative fixation", "delirium"),
    ("rheumatology", "rheumatoid arthritis", "rheumatoid arthritis", "morning hand stiffness", "synovitis of MCP joints", "anti CCP antibody", "positive anti CCP antibody", "methotrexate", "rheumatology evaluation", "joint erosion"),
    ("rheumatology", "gout flare", "acute gout flare", "first toe pain", "podagra", "serum uric acid", "elevated uric acid", "colchicine", "joint aspiration", "recurrent flare"),
    ("hematology", "iron deficiency anemia", "iron deficiency anemia", "fatigue", "microcytosis", "iron studies", "low ferritin", "oral iron", "colonoscopy evaluation", "symptomatic anemia"),
    ("hematology", "deep vein thrombosis", "acute deep vein thrombosis", "calf pain", "unilateral leg edema", "venous duplex ultrasound", "femoral vein thrombosis", "anticoagulation", "compression ultrasound", "pulmonary embolism"),
    ("obstetrics", "preeclampsia", "preeclampsia", "headache in pregnancy", "elevated blood pressure", "urine protein creatinine ratio", "proteinuria", "magnesium sulfate", "fetal monitoring", "eclampsia"),
    ("gynecology", "pelvic inflammatory disease", "pelvic inflammatory disease", "pelvic pain", "cervical motion tenderness", "nucleic acid amplification test", "positive chlamydia test", "ceftriaxone and doxycycline", "pelvic ultrasound", "tubo ovarian abscess"),
    ("oncology", "breast cancer", "invasive ductal carcinoma", "palpable breast mass", "axillary lymphadenopathy", "mammography", "spiculated breast lesion", "neoadjuvant chemotherapy", "core needle biopsy", "metastatic disease"),
    ("oncology", "lung nodule", "solitary pulmonary nodule", "chronic cough", "incidental lung nodule", "chest CT", "spiculated upper lobe nodule", "smoking cessation counseling", "CT guided biopsy", "lung cancer"),
    ("otolaryngology", "acute otitis media", "acute otitis media", "ear pain", "bulging tympanic membrane", "otoscopy", "middle ear effusion", "amoxicillin", "hearing assessment", "tympanic membrane perforation"),
    ("ophthalmology", "diabetic retinopathy", "diabetic retinopathy", "blurred vision", "retinal hemorrhages", "dilated eye examination", "nonproliferative diabetic retinopathy", "glycemic control", "retinal photography", "vision loss"),
    ("critical care", "acute respiratory failure", "acute hypoxemic respiratory failure", "severe dyspnea", "increased work of breathing", "arterial blood gas", "low PaO2", "high flow nasal cannula", "endotracheal intubation", "respiratory arrest"),
    ("procedures", "central venous catheter placement", "need for central venous access", "poor peripheral access", "ultrasound guided venous access", "procedure note", "right internal jugular central line placed", "sterile technique", "central line insertion", "line associated infection"),
]


TEMPLATES = [
    ("clinical_note", "Patient reports {symptom} during evaluation for {condition}."),
    ("clinical_note", "History includes {condition} treated with {treatment}."),
    ("clinical_note", "{test} showed {result} while assessing {focus}."),
    ("clinical_note", "Exam was notable for {finding} in the setting of {condition}."),
    ("clinical_note", "Assessment favored {condition} because of {symptom} and {finding}."),
    ("clinical_note", "Plan includes {treatment} with follow up for {focus}."),
    ("clinical_note", "The team discussed {procedure} after confirming {result}."),
    ("clinical_note", "No evidence of {complication} was found during evaluation for {focus}."),
    ("clinical_note", "The patient returned with worsening {symptom} despite {treatment}."),
    ("clinical_note", "Discharge instructions reviewed warning signs of {complication}."),
    ("clinical_note", "Clinical impression was {condition} with associated {finding}."),
    ("clinical_note", "Symptoms improved after {treatment}, but {finding} persisted."),
    ("clinical_note", "The note documents {focus}, {symptom}, and planned {procedure}."),
    ("clinical_note", "Prior records mention {condition} complicated by {complication}."),
    ("clinical_note", "Consult requested for {focus} after {test} reported {result}."),
    ("clinical_note", "Medication list was reconciled before starting {treatment} for {condition}."),
    ("clinical_note", "The patient denied {symptom}, although {test} later showed {result}."),
    ("clinical_note", "Monitoring continued because {condition} can progress to {complication}."),
    ("clinical_note", "Procedure history includes {procedure} related to {focus}."),
    ("clinical_note", "Problem list updated to include {condition} after review of {test}."),
    ("clinical_note", "Nursing note described {symptom} and new {finding}."),
    ("clinical_note", "Follow up testing for {focus} included {test}."),
    ("clinical_note", "The clinician recommended {procedure} if {symptom} recurs."),
    ("clinical_note", "{treatment} was held temporarily because of concern for {complication}."),
    ("clinical_note", "The visit focused on counseling for {condition} and prevention of {complication}."),
    ("clinical_note", "Physical examination did not reproduce {symptom}, but {finding} was present."),
    ("clinical_note", "The patient was observed overnight after {procedure} for {focus}."),
    ("clinical_note", "Care coordination note lists {focus} as the active clinical concern."),
    ("clinical_note", "Family history was reviewed because of concern for {condition}."),
    ("clinical_note", "A repeat {test} was ordered to monitor {result}."),
    ("clinical_note", "The differential diagnosis included {condition} and other causes of {symptom}."),
    ("clinical_note", "Patient education covered {treatment}, {procedure}, and symptoms of {complication}."),
    ("clinical_note", "The inpatient team escalated care when {finding} worsened."),
    ("clinical_note", "Outpatient follow up was arranged after treatment for {condition}."),
    ("clinical_note", "The referral question asked whether {symptom} represented {focus}."),
    ("clinical_note", "Clinical documentation linked {result} to suspected {condition}."),
    ("clinical_note", "The procedure note states that {procedure} was performed for {focus}."),
    ("clinical_note", "Risk assessment considered {complication} in the context of {condition}."),
    ("clinical_note", "The clinician compared current {test} findings with prior {focus} records."),
    ("clinical_note", "The chart summary describes {condition}, current {treatment}, and residual {symptom}."),
    ("research_abstract", "In a cohort of patients with {condition}, {result} was associated with {complication}."),
    ("research_abstract", "The study evaluated {treatment} for reducing {symptom} in {focus}."),
    ("research_abstract", "Investigators used {test} to identify {result} among participants with {condition}."),
    ("research_abstract", "Rates of {complication} were compared before and after {procedure}."),
    ("research_abstract", "A case series described {condition} presenting with {symptom} and {finding}."),
    ("research_abstract", "The primary endpoint measured improvement in {focus} after {treatment}."),
    ("research_abstract", "Secondary analyses examined whether {finding} predicted {complication}."),
    ("research_abstract", "Eligibility criteria required evidence of {condition} on {test}."),
    ("research_abstract", "The intervention combined {treatment} with protocolized {procedure}."),
    ("research_abstract", "Researchers excluded subjects with active {complication}."),
    ("research_abstract", "Baseline characteristics included {symptom}, {finding}, and prior {procedure}."),
    ("research_abstract", "The trial reported fewer episodes of {complication} after {treatment}."),
    ("research_abstract", "Machine learning features included {test} results and mentions of {symptom}."),
    ("research_abstract", "The registry captured longitudinal outcomes after {procedure} for {focus}."),
    ("research_abstract", "Phenotyping rules identified {condition} from {result} and medication exposure."),
    ("research_abstract", "Clinical notes were searched for {symptom} as a marker of {focus}."),
    ("research_abstract", "The analysis linked {finding} to subsequent diagnosis of {condition}."),
    ("research_abstract", "A pragmatic trial compared usual care with {treatment} for {focus}."),
    ("research_abstract", "Safety monitoring focused on {complication} during treatment with {treatment}."),
    ("research_abstract", "Outcome adjudicators reviewed {test} evidence for {condition}."),
    ("research_abstract", "Subgroup analysis evaluated patients with severe {symptom}."),
    ("research_abstract", "The manuscript defines {focus} using {test}, {result}, and treatment history."),
    ("research_abstract", "Natural language processing extracted mentions of {condition} from discharge summaries."),
    ("research_abstract", "The validation set included records with {finding} and confirmed {result}."),
    ("research_abstract", "Comparative effectiveness analyses assessed {procedure} versus medical therapy."),
    ("research_abstract", "The authors reported that {treatment} reduced recurrence of {symptom}."),
    ("research_abstract", "Risk models incorporated {condition}, {result}, and prior {complication}."),
    ("research_abstract", "Chart review confirmed {focus} when {test} showed {result}."),
    ("research_abstract", "Researchers measured time from {symptom} onset to {procedure}."),
    ("research_abstract", "The phenotype algorithm required both {finding} and {treatment}."),
    ("research_abstract", "Sensitivity analyses removed encounters with possible {complication}."),
    ("research_abstract", "Patients receiving {treatment} were matched to controls with {condition}."),
    ("research_abstract", "The observational study tracked {focus} progression using repeated {test}."),
    ("research_abstract", "Clinical endpoints included {complication}, persistent {symptom}, and need for {procedure}."),
    ("research_abstract", "The paper describes a computable phenotype for {condition}."),
    ("research_abstract", "Investigators evaluated whether {result} improved detection of {focus}."),
    ("research_abstract", "The cohort entry date was the first record of {test} showing {result}."),
    ("research_abstract", "The study separated active {condition} from historical {focus}."),
    ("research_abstract", "Manual annotation labeled sentences mentioning {symptom} and {procedure}."),
    ("research_abstract", "The evidence table summarized {treatment}, {test}, and observed {complication}."),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate deterministic synthetic clinical and research sentences for search testing."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("config/typical_clinical_research_sentences.tsv"),
        help="Output TSV with id, query, expected_cuis, why, style, domain, and expected_focus.",
    )
    parser.add_argument("--count", type=int, default=3200, help="Number of sentences to emit.")
    return parser.parse_args()


def iter_rows(count: int):
    emitted = 0
    topics = [dict(zip(TOPIC_FIELDS, row)) for row in TOPIC_ROWS]
    while emitted < count:
        pass_index = emitted // (len(topics) * len(TEMPLATES))
        for style, template in TEMPLATES:
            for topic_index, topic in enumerate(topics, start=1):
                if emitted >= count:
                    return
                sentence = template.format(**topic)
                if pass_index:
                    sentence = sentence.replace(".", f" during follow up interval {pass_index + 1}.")
                emitted += 1
                yield {
                    "id": f"synthetic_{emitted:05d}",
                    "query": sentence,
                    "expected_cuis": "",
                    "why": (
                        f"Synthetic {style.replace('_', ' ')} sentence for {topic['focus']}; "
                        "expected CUI is intentionally blank until judged."
                    ),
                    "style": style,
                    "domain": topic["domain"],
                    "expected_focus": topic["focus"],
                    "synthetic": "true",
                    "topic_index": str(topic_index),
                }


def main() -> int:
    args = parse_args()
    if args.count <= 0:
        raise SystemExit("--count must be positive")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "id",
        "query",
        "expected_cuis",
        "why",
        "style",
        "domain",
        "expected_focus",
        "synthetic",
        "topic_index",
    ]
    with args.out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(iter_rows(args.count))
    print(f"Wrote {args.count:,} synthetic sentences to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
