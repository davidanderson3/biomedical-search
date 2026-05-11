# Curated Relationship Seed Edges

## Change

Added a small, explicit curated relationship seed file at `config/curated_relationship_edges.jsonl` and built the default serving index at `build/relationship_edges.sqlite`. The seed currently contains 28 universal relationship edges covering high-value examples across drug indications, disease-observation links, diagnostic/lab context, and procedure-bundle attributes.

The default relationship-edge index now gives the interface concrete relationship rows to display and rerank from, rather than only having the infrastructure waiting for mined OHDSI/procedure JSONL. I also normalized procedure seed relation labels so they display as readable values such as `uses_device`, `target_anatomy`, `uses_modality`, and `has_broader_concept`, not raw `RO`/`RB`.

## Improvement

This makes the edge pipeline immediately useful for common gaps:

- `sumatriptan -> likely_indication -> migraine`
- `pantoprazole -> likely_indication -> gastric ulcer`
- `apixaban -> likely_indication -> atrial fibrillation/deep vein thrombosis/pulmonary embolism`
- `heart failure with reduced ejection fraction -> has_observation -> ejection fraction`
- `central venous catheter placement -> uses_device -> catheter`
- `central venous catheter placement -> target_anatomy -> veins`
- `endoscopic biopsy -> has_broader_concept -> biopsy`

The paragraph benchmark remained strong after the new relationship index was loaded by default: 96 paragraphs, 467 expected concepts, recall@10 99.1%, recall@20 99.8%, recall@60 100.0%, and 94 good / 2 mixed verdicts. That means the seed relationship layer did not introduce broad ranking damage in the current paragraph set.

## Verification

- Built `build/relationship_edges.sqlite` from 28 valid JSONL rows.
- Smoke lookup confirmed `C0075632` sumatriptan returns migraine with strength 0.90 and confidence 0.88.
- Smoke lookup confirmed `C0398275` central venous catheter placement returns catheter, central venous catheterization, veins, and ultrasonography with readable relation labels.
- `python3 -m py_compile` passed for the touched relationship/search modules and scripts.
- `node --check docs/search_quality/app.js` passed.
- Focused pytest selection passed: 5 passed, 209 deselected.
- Paragraph evaluation wrote results to `build/improvements/2026-05-11_curated_relationship_edges_eval/`.

## Remaining Limitations

This is a seed layer, not broad mined evidence. It improves representative high-value cases and validates the edge path, but it does not replace mining public aggregate OHDSI artifacts, expanding procedure bundles at scale, or adding source-specific confidence calibration. Future iterations should grow this with source-derived rows and keep curated rows limited to benchmark-critical clinical relationships.
