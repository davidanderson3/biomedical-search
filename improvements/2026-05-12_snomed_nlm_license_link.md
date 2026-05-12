# SNOMED NLM License Link

## Change

Updated the SNOMED CT clickthrough to link directly to the NLM SNOMED CT Affiliate License Agreement:

https://www.nlm.nih.gov/research/umls/knowledge_sources/metathesaurus/release/license_agreement_snomed.html

The acknowledgement wording now names the linked NLM agreement, and the browser acknowledgement key was bumped from `qe_snomed_license_ack_v1` to `qe_snomed_license_ack_v2` so users who accepted the earlier generic wording see the corrected license reference once.

## Result

Verification passed:

- `node --check docs/search_quality/app.js`
- Source HTML contains the NLM SNOMED CT Affiliate License Agreement link.
- Served page at `http://127.0.0.1:8766/` contains the NLM link.
- Served JS contains `qe_snomed_license_ack_v2`.

## Impact

This is a licensing/notice correction only. It does not change search behavior, ranking, or indexed content.
