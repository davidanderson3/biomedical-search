# SNOMED Default Procedure Bundles

## Change

Procedure-bundle builds now allow SNOMED CT anchors by default. The CLI keeps `--allow-snomed` as a compatible no-op/default flag and adds `--no-snomed` for deployments that need to reject SNOMED CT anchors.

## Improvement

This removes unnecessary friction from the procedure coverage path. SNOMED-backed procedure anchors can now be used in local procedure bundles without remembering a special flag, while CPT/CPT4 content is still rejected from public bundle outputs.

## Verification

Added a test that builds a procedure bundle with a `SNOMEDCT_US` anchor using default settings and confirms the anchor is retained. The same test verifies that setting `allow_snomed=False` still rejects SNOMED CT content.

## Remaining Limitations

This changes only the procedure-bundle validation default. It does not import new SNOMED files, alter UMLS licensing policy, or allow CPT descriptors into public artifacts.
