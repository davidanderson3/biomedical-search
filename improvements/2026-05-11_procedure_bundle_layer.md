# Procedure Bundle Layer

Implemented a public procedure-bundle builder that creates granular `NEW#######` procedure concepts without using CPT content. The builder uses open/permitted anchors supplied locally, extracts structured attributes from procedure labels, and emits broader/narrower and attribute relations.

What improved:

- Added `src/qe_evidence_vectors/procedure_bundles.py` for structured procedure concepts with `action`, `anatomy_route`, `approach`, `modality`, `intent`, `device`, `specimen`, and qualifiers.
- Added `scripts/build_procedure_bundles.py` to generate extension-concept JSONL, relation JSONL, and an optional registry from local procedure bundle rows.
- Added MTH-style broader/narrower relation output, plus `target_anatomy`, `uses_modality`, `uses_device`, `uses_specimen`, `related_open_anchor`, and `close_match` relations.
- Public bundle inputs reject CPT/CPT4 content and descriptor-like leakage.
- SNOMED CT anchors are blocked by default and require an explicit licensed-deployment flag.
- Added a descriptor-free private CPT adapter validator so licensed users can map local bundles to CPT locally without shipping CPT codes, descriptors, or public crosswalks.

What did not improve yet:

- This does not automatically discover procedure bundles from PubMed or other corpora; it builds from supplied local rows.
- The bundle concepts and relation JSONL are not yet wired into the default search-index build.
- The attribute extractor is intentionally conservative and rule-based; it should be expanded as we review more procedure search failures.
