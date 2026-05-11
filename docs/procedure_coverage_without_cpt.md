# Procedure Coverage Without CPT

## Position

Do not ingest, distribute, display, or derive local public concepts directly from CPT codes or CPT descriptors in the open UMLS 2.0 layer. CPT is maintained by the AMA and requires licensing for many uses. The open product should treat CPT as an optional private adapter that can be loaded only inside a licensed deployment, never as shipped content.

## Product Strategy

Use a procedure abstraction layer instead of CPT itself:

```text
procedure bundle -> open vocabulary anchors -> evidence-backed aliases -> optional private CPT mapping
```

The public layer should store:

- open/source-allowed procedure concepts and labels
- local `NEW#######` procedure concepts when clinically useful procedure ideas are missing
- evidence-derived aliases from literature and open reference sources
- structured procedure attributes
- mappings to open or permitted source codes

The public layer should not store:

- CPT codes
- CPT descriptors
- CPT long descriptors
- CPT short descriptors
- public CPT-to-local crosswalks
- generated concepts that are only paraphrases of CPT descriptors

## Replacement Sources

Use these as the public procedure backbone, subject to each source's license:

- MeSH procedure headings for literature-facing procedures.
- LOINC for observations, panels, surveys, laboratory procedures, and clinical measurements.
- ICD-10-PCS for inpatient procedural granularity where applicable.
- HCPCS Level II for non-CPT products, supplies, devices, ambulance services, DMEPOS, and similar non-physician-service billing concepts where licensing permits.
- SNOMED CT procedures are allowed by default in the local procedure-bundle path; deployments that cannot include SNOMED CT can opt out.
- NCI/NCIt, HPO, and other allowed biomedical vocabularies for oncology, genetics, phenotyping, and research procedures.
- Literature-mined and guideline/open-reference text for common clinical procedure names.

## Procedure Bundle Model

Represent procedures with structured attributes so the system can be granular without copying CPT:

- action: excision, drainage, imaging, biopsy, injection, repair, replacement, measurement
- target anatomy: stomach, colon, knee, coronary artery, breast, kidney
- approach/route: open, percutaneous, endoscopic, laparoscopic, transcatheter
- modality: ultrasound, CT, MRI, fluoroscopy, echocardiography
- intent: diagnostic, therapeutic, screening, surveillance, palliative
- specimen/substance/device: tissue, fluid, stent, catheter, contrast, graft
- laterality/site qualifiers: left/right, proximal/distal, segment/level
- acuity/context: emergency, elective, postoperative, inpatient, outpatient

Examples:

```text
incision and drainage of skin abscess
endoscopic biopsy of gastric ulcer
ultrasound-guided central venous catheter placement
percutaneous coronary intervention with stent placement
right heart catheterization for pulmonary hypertension
```

Each bundle can resolve to one or more open anchors and have broader/narrower relations:

```text
endoscopic biopsy of gastric ulcer -> broader -> endoscopy
endoscopic biopsy of gastric ulcer -> broader -> biopsy
endoscopic biopsy of gastric ulcer -> target_anatomy -> stomach
endoscopic biopsy of gastric ulcer -> evaluates -> gastric ulcer
```

## Search Behavior

For procedure queries, return clinically meaningful procedure bundles, not billing-level fragments. Prefer:

1. exact open-source CUI/procedure labels
2. evidence-backed local `NEW#######` procedure concepts
3. composed procedure bundles from action + anatomy + approach + modality
4. broader open concepts when no granular concept exists

Avoid default top results that are only generic actions, modifiers, or billing-like fragments:

```text
procedure
service
repair
diagnostic
operation
consultation
```

Those can remain in details or broader/narrower context, but should not dominate the Procedures bucket.

## Optional CPT Adapter

For a licensed deployment, support CPT as a private plugin:

- user supplies CPT files or licensed API access locally
- mappings stay outside the public repository and public vector store
- public artifacts contain only local/open concept IDs, not CPT descriptors
- runtime can resolve local procedure bundles to CPT for authorized users
- logs and exported results must avoid leaking CPT descriptors unless the deployment license allows it

The public system can include an interface like:

```text
procedure_bundle_id -> private_code_system -> private_code
```

but the public build should leave the private side empty.

## Practical Next Steps

1. Build procedure-bundle extraction from clinical/research text using action, anatomy, approach, modality, and intent.
2. Create `NEW#######` procedure concepts only when the procedure is clinically useful and not adequately covered by allowed sources.
3. Add broader/narrower relations between granular procedure bundles and open procedure anchors.
4. In ranking, penalize generic procedure fragments unless they exactly match a short query.
5. Add an optional private CPT adapter interface without shipping CPT content.

## Implemented Local Builder

The repository now includes a public procedure-bundle builder at `scripts/build_procedure_bundles.py`. It reads local JSONL/JSON/CSV/TSV rows and emits:

- extension concept JSONL for `NEW#######` procedure concepts
- relation JSONL for broader/narrower, target anatomy, modality, device, specimen, related, and close-match links
- an optional registry JSONL with extracted bundle attributes

Example:

```sh
python3 scripts/build_procedure_bundles.py \
  --input config/procedure_bundles.jsonl \
  --out-concepts build/procedure_bundle_concepts.jsonl \
  --out-relations build/procedure_bundle_relations.jsonl \
  --out-registry build/procedure_bundle_registry.jsonl
```

Input rows can provide a preferred label, aliases, evidence, open anchors, broader anchors, target anatomy, modality anchors, device anchors, specimen anchors, and related anchors. If structured attributes are not supplied, the builder infers a first-pass bundle from the label:

```json
{
  "preferred_label": "ultrasound-guided central venous catheter placement",
  "broader": [{"cui": "C0007437", "label": "Catheterization", "source": "MSH"}],
  "target_anatomy": [{"cui": "C0042449", "label": "Veins", "source": "MSH"}],
  "modality_anchors": [{"cui": "C0041618", "label": "Ultrasonography", "source": "MSH"}],
  "device_anchors": [{"cui": "C0085590", "label": "Catheters", "source": "MSH"}]
}
```

The builder rejects CPT/CPT4 content in public bundles. SNOMED CT anchors are allowed by default; use `--no-snomed` only for deployments that need to reject them. A private CPT adapter can be validated with `--private-cpt-adapter`, but it must be code-only and is never copied into public outputs.
