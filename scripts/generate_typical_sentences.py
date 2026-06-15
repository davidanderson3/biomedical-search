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
    ("gastroenterology", "diverticulitis", "acute uncomplicated diverticulitis", "left lower quadrant pain", "localized abdominal tenderness", "computed tomography abdomen", "sigmoid diverticulitis", "amoxicillin clavulanate", "colonoscopy follow-up", "perforation"),
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
    ("psychiatry", "alcohol withdrawal", "alcohol withdrawal syndrome", "tremulousness", "tachycardia", "CIWA assessment", "elevated withdrawal score", "lorazepam", "withdrawal monitoring", "withdrawal seizure"),
    ("infectious disease", "sepsis", "sepsis due to cellulitis", "fever and malaise", "hypotension", "blood culture", "gram positive cocci in clusters", "broad spectrum antibiotics", "source control", "septic shock"),
    ("infectious disease", "osteomyelitis", "diabetic foot osteomyelitis", "foot ulcer drainage", "exposed bone", "foot MRI", "marrow edema concerning for osteomyelitis", "vancomycin", "bone biopsy", "amputation"),
    ("dermatology", "psoriasis", "plaque psoriasis", "itchy rash", "silvery scale", "skin examination", "erythematous plaques on extensor surfaces", "topical corticosteroid", "dermatology follow-up", "joint pain"),
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


SHORT_TEMPLATES = [
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
    ("clinical_note", "{treatment} {treatment_past_verb} held temporarily because of concern for {complication}."),
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


LONG_TEMPLATES = [
    (
        "clinical_paragraph",
        "During evaluation for {focus}, the patient described {symptom} and the clinician documented {finding}. "
        "{test} showed {result}, so the plan included {treatment} and close monitoring for {complication}.",
    ),
    (
        "clinical_paragraph",
        "The admission note linked {condition} to recent {symptom}, objective {finding}, and confirmatory {test}. "
        "After {result} was reviewed, the team discussed {procedure} and started {treatment}.",
    ),
    (
        "clinical_paragraph",
        "A follow up visit for {condition} reviewed persistent {symptom}, prior {test} findings, and the current response to {treatment}. "
        "The note asks whether {complication} should change the plan for {procedure}.",
    ),
    (
        "clinical_paragraph",
        "The discharge summary lists {condition} as the main diagnosis, with {symptom} and {finding} supporting the assessment. "
        "It also records {test} evidence of {result}, treatment with {treatment}, and instructions about {complication}.",
    ),
    (
        "clinical_paragraph",
        "Consultation was requested because {symptom} persisted despite treatment for {condition}. "
        "Review of {test} showed {result}, and the consultant recommended {procedure} while watching for {complication}.",
    ),
    (
        "clinical_paragraph",
        "The emergency department note begins with {symptom}, then narrows the differential toward {condition} after {finding} was observed. "
        "{test} demonstrated {result}, prompting {treatment} and referral for {procedure}.",
    ),
    (
        "clinical_paragraph",
        "The problem list contains historical {focus}, but today's assessment focuses on active {condition}. "
        "Current documentation mentions {symptom}, {finding}, {result}, and the need to avoid missing {complication}.",
    ),
    (
        "clinical_paragraph",
        "Nursing documentation reported worsening {symptom} overnight in a patient already known to have {condition}. "
        "Morning rounds reviewed {finding}, ordered {test}, and adjusted {treatment} because {complication} remained a concern.",
    ),
    (
        "clinical_paragraph",
        "The clinician compared prior {focus} records with a new episode of {symptom}. "
        "{test} now shows {result}, making {condition} more likely and leading to discussion of {procedure}.",
    ),
    (
        "clinical_paragraph",
        "Medication reconciliation noted {treatment} for {condition}, but the patient returned with {symptom}. "
        "Because {finding} and {result} were present, the team documented {complication} as a concern.",
    ),
    (
        "clinical_question",
        "In a patient with {condition}, {symptom}, and {finding}, should {test} evidence of {result} change treatment with {treatment} or timing of {procedure}?",
    ),
    (
        "clinical_question",
        "For suspected {focus}, how should the search rank {condition}, {symptom}, {test}, {result}, {treatment}, and possible {complication} from one clinical note?",
    ),
    (
        "clinical_question",
        "The chart says no active {complication}, but it does report {condition}, {symptom}, {finding}, and {result}; which concepts should be returned first?",
    ),
    (
        "clinical_question",
        "When a note describes {symptom} after {procedure} and mentions {treatment} for {condition}, should the search also retrieve {complication}?",
    ),
    (
        "clinical_question",
        "Which biomedical concepts best match this long query: {condition} with {symptom}, {finding}, {test} showing {result}, and management using {treatment}?",
    ),
    (
        "research_abstract_long",
        "A retrospective cohort identified {condition} using mentions of {symptom}, {finding}, and {test} results. "
        "Participants with {result} were compared by exposure to {treatment}, and outcomes included {procedure} and {complication}.",
    ),
    (
        "research_abstract_long",
        "The manuscript describes a computable phenotype for {focus} that requires {condition}, objective {finding}, and {test} evidence of {result}. "
        "Manual review adjudicated treatment with {treatment} and downstream {complication}.",
    ),
    (
        "research_abstract_long",
        "In a multicenter registry, investigators extracted {symptom} from notes and paired it with {test} findings for {condition}. "
        "The analysis evaluated whether {treatment} reduced need for {procedure} or subsequent {complication}.",
    ),
    (
        "research_abstract_long",
        "A pragmatic trial enrolled adults with {condition} and baseline {finding}. "
        "The intervention used {treatment}, the outcome model included {result}, and safety monitoring focused on {complication}.",
    ),
    (
        "research_abstract_long",
        "Natural language processing was used to find {focus} in discharge summaries mentioning {symptom} and {procedure}. "
        "The validation set required {test} evidence of {result} and chart-confirmed {condition}.",
    ),
    (
        "research_abstract_long",
        "A case series described {condition} presenting with {symptom}, {finding}, and abnormal {test}. "
        "Several patients received {treatment}, while follow up documented {procedure} and possible {complication}.",
    ),
    (
        "research_abstract_long",
        "The study separated historical {focus} from active {condition} by requiring recent {symptom}, current {finding}, and {result}. "
        "Sensitivity analyses excluded records where {complication} was only mentioned as a risk.",
    ),
    (
        "research_abstract_long",
        "Investigators compared {procedure} with medical management for {condition}. "
        "Baseline variables included {symptom}, {finding}, {test}, {result}, and current use of {treatment}.",
    ),
    (
        "research_abstract_long",
        "The evidence table summarized {condition}, {test} evidence of {result}, and treatment with {treatment}. "
        "Reviewers also annotated {symptom}, {finding}, planned {procedure}, and observed {complication}.",
    ),
    (
        "research_abstract_long",
        "A prediction model for {complication} incorporated {condition}, reported {symptom}, documented {finding}, and {test} values. "
        "Model explanations highlighted {result}, {treatment}, and prior {procedure}.",
    ),
    (
        "trial_result_query",
        "A posted outcome-results summary for participants with {condition} reported baseline {symptom} and {finding}. "
        "The results table compared {treatment} with usual care for {focus}, with outcomes including {result} and {complication}.",
    ),
    (
        "trial_result_query",
        "Clinical trial results for {focus} listed {test} as an outcome measure and reported {result} after {treatment}. "
        "The evidence should emphasize posted results rather than protocol-only text about {procedure}.",
    ),
    (
        "trial_result_query",
        "In the completed study arm for {condition}, participants receiving {treatment} had follow up assessment of {symptom}. "
        "Reported adverse events included {complication}, and procedure-related outcomes mentioned {procedure}.",
    ),
    (
        "trial_result_query",
        "The results posting described enrollment of patients with {condition}, baseline {finding}, and outcome measurement by {test}. "
        "Search should connect {result}, {treatment}, {focus}, and {complication} without over-weighting eligibility criteria.",
    ),
    (
        "trial_result_query",
        "A trial outcome table for {focus} reported change in {symptom}, confirmatory {test}, and need for {procedure}. "
        "Safety rows included {complication} during treatment with {treatment}.",
    ),
    (
        "drug_label_query",
        "A drug-label style query asks whether {treatment} {treatment_verb} used for {condition} when the patient has {symptom} and {finding}. "
        "The answer should distinguish indication language from warnings about {complication}.",
    ),
    (
        "drug_label_query",
        "Daily medication review mentions {treatment}, active {condition}, recent {test} showing {result}, and concern for {complication}. "
        "Search should retrieve the drug, disease, diagnostic result, and safety concept together.",
    ),
    (
        "drug_label_query",
        "The prescribing note says {treatment} {treatment_past_verb} started after {test} confirmed {result} in the setting of {condition}. "
        "Patient counseling covered recurrent {symptom}, planned {procedure}, and warning signs of {complication}.",
    ),
    (
        "drug_label_query",
        "A warning-focused query combines {treatment} exposure with {symptom}, {finding}, and possible {complication}. "
        "The intended result should not lose the underlying {condition} or the relevant {test}.",
    ),
    (
        "drug_label_query",
        "The adverse reaction review asks whether {complication} occurred after {treatment} for {condition}. "
        "Supporting context includes {symptom}, {finding}, {test}, and {result}.",
    ),
    (
        "lay_language_query",
        "A patient asks about {focus} after being told they have {condition}. "
        "They mention {symptom}, a doctor seeing {finding}, a test showing {result}, and treatment with {treatment}.",
    ),
    (
        "lay_language_query",
        "Plain-language search: what does it mean when someone with {condition} has {symptom}, abnormal {test}, and worry about {complication}?",
    ),
    (
        "lay_language_query",
        "The question uses everyday wording around {symptom} but the record also contains {condition}, {finding}, {result}, and {treatment}. "
        "The search should still map to the clinical concepts.",
    ),
    (
        "lay_language_query",
        "A caregiver wants an explanation of {procedure} for {focus}, including why {test} showed {result} and why {complication} was discussed.",
    ),
    (
        "lay_language_query",
        "Long patient portal message: I have {condition}, keep having {symptom}, was given {treatment}, and my clinician mentioned {complication}; what terms should I search?",
    ),
    (
        "diagnostic_report_query",
        "The diagnostic report for {focus} states that {test} showed {result}. "
        "Clinical history includes {condition}, {symptom}, and {finding}, while recommendations mention {procedure}.",
    ),
    (
        "diagnostic_report_query",
        "Radiology or lab follow up for {condition}: {test} demonstrated {result}, but the report also mentions {complication} as a possible consequence. "
        "The query should keep {focus} central.",
    ),
    (
        "diagnostic_report_query",
        "A results-review note connects {finding} and {result} with symptoms of {symptom}. "
        "The assessment names {condition}, starts {treatment}, and schedules {procedure}.",
    ),
    (
        "diagnostic_report_query",
        "The chart contains a dense diagnostic sentence with {condition}, {test}, {result}, {symptom}, {finding}, {treatment}, and {complication}. "
        "It is meant to test source contribution from longer result-backed queries.",
    ),
    (
        "diagnostic_report_query",
        "Follow up interpretation of {test} for {focus} described {result} and recommended correlation with {symptom}. "
        "The note also documents {condition}, {finding}, and treatment using {treatment}.",
    ),
]


TEMPLATES = SHORT_TEMPLATES + LONG_TEMPLATES
DEFAULT_COUNT = 10000
DEFAULT_FULL_PAGE_OUT = Path("config/full_page_sample_queries.tsv")
DEFAULT_FULL_PAGE_COUNT = len(TOPIC_ROWS) * 5
SHORT_TEMPLATE_COUNT = len(TOPIC_ROWS) * len(SHORT_TEMPLATES)
LONG_VARIANT_SUFFIXES = (
    "The same query variant adds later follow up wording to test ranking stability across longer notes.",
    "A second documentation pass repeats the clinical focus with different surrounding context.",
    "The expanded wording is intentionally redundant so candidate retrieval must preserve the central concepts.",
    "This variant simulates older chart context mixed with a new active assessment.",
)
FULL_PAGE_STYLES = (
    "full_page_clinical",
    "full_page_research",
    "full_page_trial_result",
    "full_page_drug_safety",
    "full_page_lay_language",
)
OUTPUT_FIELDS = [
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate deterministic synthetic clinical and research queries for search testing."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("config/typical_clinical_research_sentences.tsv"),
        help="Output TSV with id, query, expected_cuis, why, style, domain, and expected_focus.",
    )
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT, help="Number of queries to emit.")
    parser.add_argument(
        "--full-page-out",
        type=Path,
        help="Optional TSV path for generated page-length sample queries.",
    )
    parser.add_argument(
        "--full-page-count",
        type=int,
        default=DEFAULT_FULL_PAGE_COUNT,
        help="Number of page-length sample queries to emit when --full-page-out is set.",
    )
    parser.add_argument(
        "--only-full-page",
        action="store_true",
        help="Write only --full-page-out and skip the regular query corpus.",
    )
    return parser.parse_args()


def sentence_case_boundaries(query: str) -> str:
    chars = list(query)
    capitalize_next = True
    for index, char in enumerate(chars):
        if capitalize_next and char.isalpha():
            chars[index] = char.upper()
            capitalize_next = False
        elif char in ".?!":
            capitalize_next = True
        elif capitalize_next and not char.isspace() and char not in "'\"([":
            capitalize_next = False
    return "".join(chars)


def query_for_pass(template: str, topic: dict, *, pass_index: int, sentence_case: bool = False) -> str:
    query = template.format(**topic)
    if sentence_case:
        query = sentence_case_boundaries(query)
    if pass_index <= 0:
        return query
    suffix = LONG_VARIANT_SUFFIXES[(pass_index - 1) % len(LONG_VARIANT_SUFFIXES)]
    return f"{query} {suffix}"


def compact_query(parts: list[str]) -> str:
    return " ".join(" ".join(part.split()) for part in parts if part.strip())


def agreement_verb(phrase: str) -> str:
    lower = phrase.lower()
    if " and " in lower:
        return "are"
    if lower in {"intravenous fluids", "broad spectrum antibiotics", "seizure precautions"}:
        return "are"
    return "is"


def past_agreement_verb(phrase: str) -> str:
    return "were" if agreement_verb(phrase) == "are" else "was"


def topic_with_grammar(topic: dict) -> dict:
    return {
        **topic,
        "treatment_verb": agreement_verb(topic["treatment"]),
        "treatment_past_verb": past_agreement_verb(topic["treatment"]),
        "procedure_verb": agreement_verb(topic["procedure"]),
    }


def full_page_sections(topic: dict, companion: dict, *, style: str, variant_index: int) -> list[str]:
    background = (
        f"Older history: the prior problem list still includes {companion['condition']} and prior "
        f"{companion['treatment']}. The current visit says there is no active issue related to "
        f"{companion['complication']}, "
        f"and the team is not making a new care decision about {companion['focus']} today."
    )
    carry_forward = (
        "Medication lists, nursing notes, patient instructions, old test results, family history, scheduling "
        "text, and follow-up reminders appear alongside the active assessment. These repeated phrases restate the "
        "active problem in different words while also adding routine chart language such as assessment, plan, "
        "review, education, and return precautions."
    )
    if variant_index:
        carry_forward += (
            " A later chart update adds another brief update after phone triage, using different wording for "
            "the same active concern."
        )

    if style == "full_page_clinical":
        return [
            (
                f"Chief concern: the patient came in with worsening {topic['symptom']}. "
                f"The active assessment is {topic['condition']}. On exam or bedside review, the clinician "
                f"documented {topic['finding']}."
            ),
            (
                f"Objective data: the team reviewed the available {topic['test']} information during this visit; "
                f"it showed {topic['result']}. "
                f"The same result is repeated in the emergency department note, consultant note, and discharge "
                f"summary because the care team is trying to keep {topic['focus']} visible across handoffs."
            ),
            (
                f"Plan: the care plan documents {topic['treatment']} for the active problem. The team discussed "
                f"{topic['procedure']} and reviewed warning signs of {topic['complication']}. The medication "
                "list, nursing handoff, and patient instructions all use slightly different wording for the "
                "same active issue."
            ),
            background,
            carry_forward,
            (
                f"Discharge instructions: call urgently if symptoms such as {topic['symptom']} return, if findings "
                f"such as {topic['finding']} are worsening, or if there are signs concerning for "
                f"{topic['complication']}. Follow-up is arranged to review {topic['test']} findings, management "
                f"involving {topic['treatment']}, and whether "
                f"{topic['procedure']} {agreement_verb(topic['procedure'])} still needed."
            ),
        ]

    if style == "full_page_research":
        return [
            (
                f"Abstract: this retrospective cohort studied records involving {topic['condition']}. Cases were found "
                f"from clinical notes describing {topic['symptom']}, clinician-recorded {topic['finding']}, and "
                f"{topic['test']} reports showing {topic['result']}."
            ),
            (
                f"Methods: reviewers treated {topic['treatment']} and {topic['procedure']} as supporting care "
                f"signals when they appeared close to the active {topic['focus']} episode. They separated active "
                "events from family history, resolved disease, negated symptoms, eligibility criteria, and broad "
                "outcome wording."
            ),
            (
                f"Results: records with stronger evidence had more mentions of {topic['symptom']} and "
                f"{topic['finding']}, more confirmed {topic['result']}, and more documented {topic['complication']}. "
                f"Several tables repeat {topic['condition']}, {topic['test']}, {topic['treatment']}, and "
                f"{topic['procedure']} because the manuscript includes baseline features, exposure definitions, "
                "and outcome summaries."
            ),
            background,
            carry_forward,
            (
                f"Discussion: the authors describe {topic['focus']} as a practical documentation problem, because "
                f"plain-language descriptions, clinician shorthand, diagnostic reports, treatments, procedures, "
                f"and outcomes can all point to the same episode of {topic['condition']}."
            ),
        ]

    if style == "full_page_trial_result":
        return [
            (
                f"Results summary: a completed study enrolled patients who had {topic['condition']} and baseline "
                f"{topic['symptom']}. Enrollment notes mention screening, follow-up, withdrawal, and safety review."
            ),
            (
                f"Baseline characteristics included {topic['finding']} and prior evaluation with "
                f"{topic['test']}. Reported outcomes included {topic['result']}, use of {topic['treatment']}, "
                f"and whether {topic['procedure']} occurred during follow-up."
            ),
            (
                f"Adverse events and outcomes included {topic['complication']} along with repeat mentions of "
                f"{topic['condition']} and {topic['focus']}. Protocol details described eligibility, dates, "
                "arms, contacts, and outcome measure names."
            ),
            background,
            carry_forward,
            (
                f"Clinical summary: participants with {topic['symptom']} and {topic['finding']} were followed "
                f"after {topic['test']} confirmed {topic['result']}. The report keeps the active "
                f"{topic['focus']} episode separate from old history and administrative trial details."
            ),
        ]

    if style == "full_page_drug_safety":
        return [
            (
                f"Care-safety review: {topic['treatment']} {agreement_verb(topic['treatment'])} documented for the active "
                f"problem of {topic['condition']} in a patient reporting {topic['symptom']} with "
                f"{topic['finding']}."
            ),
            (
                f"Diagnostic support: {topic['test']} showed {topic['result']}. The clinician connected that "
                f"finding to {topic['focus']} before documenting {topic['treatment']}, possible {topic['procedure']}, "
                f"and counseling about {topic['complication']}."
            ),
            (
                "Safety wording: the medication list includes old prescriptions, current orders, allergies, "
                "side-effect counseling, and nursing reminders. Some warnings are general, while the current "
                f"episode specifically links {topic['condition']}, {topic['symptom']}, {topic['finding']}, "
                f"{topic['test']}, and {topic['result']}."
            ),
            background,
            carry_forward,
            (
                f"Patient counseling: the instructions explain when to seek care for {topic['complication']}, "
                f"why the care plan includes {topic['treatment']}, and why the team may still need "
                f"{topic['procedure']}. "
                "The note combines order review, clinician assessment, and discharge teaching."
            ),
        ]

    return [
        (
            f"Patient portal message: Hi, I am confused about my visit summary. It says I may have "
            f"{topic['condition']}, and I came in because of {topic['symptom']}. I also saw the words "
            f"{topic['finding']} and {topic['result']} in the note."
        ),
        (
            f"Can you explain whether the {topic['test']} result is why you are concerned about "
            f"{topic['focus']}? I was told {topic['treatment']} might be part of the plan, and I am not sure "
            f"whether {topic['procedure']} {agreement_verb(topic['procedure'])} something I need now or only if things do not improve."
        ),
        (
            f"I am also worried because the instructions mention watching for {topic['complication']}. "
            f"Please tell me what symptoms should make me call right away, and whether {topic['symptom']} or "
            f"{topic['finding']} would mean the {topic['focus']} problem is getting worse."
        ),
        (
            f"My portal still shows an older problem, {companion['condition']}, and an old {companion['test']} "
            f"result from another visit. It also still lists {companion['treatment']}. I do not know if that old "
            f"information affects the new {topic['focus']} plan or if it is just part of my history."
        ),
        (
            f"I am trying to sort out which words matter most: {topic['condition']}, {topic['test']}, "
            f"{topic['result']}, {topic['treatment']}, {topic['procedure']}, and {topic['complication']}. "
            f"I do not want to confuse the old {companion['focus']} history with the new concern from this visit."
        ),
        (
            f"Could someone reply in plain language with what diagnosis I should use when scheduling follow-up, "
            f"what the next step is, and whether I should mention {topic['symptom']}, {topic['finding']}, "
            f"or {topic['result']} when I call?"
        ),
    ]


def iter_full_page_rows(count: int):
    topics = [dict(zip(TOPIC_FIELDS, row)) for row in TOPIC_ROWS]
    emitted = 0
    while emitted < count:
        variant_index = emitted // (len(topics) * len(FULL_PAGE_STYLES))
        for style in FULL_PAGE_STYLES:
            for topic_index, topic in enumerate(topics, start=1):
                if emitted >= count:
                    return
                companion = topics[(topic_index + variant_index * 7) % len(topics)]
                emitted += 1
                yield {
                    "id": f"full_page_{emitted:04d}",
                    "query": compact_query(
                        full_page_sections(topic, companion, style=style, variant_index=variant_index)
                    ),
                    "expected_cuis": "",
                    "why": (
                        f"Synthetic long-form {style.removeprefix('full_page_').replace('_', ' ')} sample for {topic['focus']}; "
                        "expected CUI is intentionally blank until judged."
                    ),
                    "style": style,
                    "domain": topic["domain"],
                    "expected_focus": topic["focus"],
                    "synthetic": "true",
                    "topic_index": str(topic_index),
                }


def iter_rows(count: int):
    emitted = 0
    topics = [topic_with_grammar(dict(zip(TOPIC_FIELDS, row))) for row in TOPIC_ROWS]
    for style, template in SHORT_TEMPLATES:
        for topic_index, topic in enumerate(topics, start=1):
            if emitted >= count:
                return
            emitted += 1
            yield {
                "id": f"synthetic_{emitted:05d}",
                "query": query_for_pass(template, topic, pass_index=0),
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
    long_emitted = 0
    while emitted < count:
        pass_index = long_emitted // (len(topics) * len(LONG_TEMPLATES))
        for style, template in LONG_TEMPLATES:
            for topic_index, topic in enumerate(topics, start=1):
                if emitted >= count:
                    return
                query = query_for_pass(template, topic, pass_index=pass_index, sentence_case=True)
                emitted += 1
                long_emitted += 1
                yield {
                    "id": f"synthetic_{emitted:05d}",
                    "query": query,
                    "expected_cuis": "",
                    "why": (
                        f"Synthetic {style.replace('_', ' ')} for {topic['focus']}; "
                        "expected CUI is intentionally blank until judged."
                    ),
                    "style": style,
                    "domain": topic["domain"],
                    "expected_focus": topic["focus"],
                    "synthetic": "true",
                    "topic_index": str(topic_index),
                }


def write_query_tsv(path: Path, rows) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def main() -> int:
    args = parse_args()
    if args.count <= 0:
        raise SystemExit("--count must be positive")
    if args.full_page_count <= 0:
        raise SystemExit("--full-page-count must be positive")
    if args.only_full_page and not args.full_page_out:
        args.full_page_out = DEFAULT_FULL_PAGE_OUT
    if not args.only_full_page:
        count = write_query_tsv(args.out, iter_rows(args.count))
        print(f"Wrote {count:,} synthetic queries to {args.out}")
    if args.full_page_out:
        count = write_query_tsv(args.full_page_out, iter_full_page_rows(args.full_page_count))
        print(f"Wrote {count:,} long-form synthetic queries to {args.full_page_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
