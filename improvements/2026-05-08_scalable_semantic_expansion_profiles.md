# Scalable Semantic Expansion Profiles

## Request

Implement scaling of the semantic expansion rules, replacing one-off hand-coded rules with something easier to extend.

## Change

Moved semantic expansion rules into `docs/search_quality/expansion_profiles.json` and added a generic browser-side loader in `docs/search_quality/app.js`.

The profile schema supports:

- target bucket or semantic group
- regex trigger patterns
- one or more inferred concepts
- source labels and rank metadata

The local HTTP server now serves the profile JSON at `/search_quality_expansion_profiles.json`, so new expansion profiles can be added without editing JavaScript logic.

Also made the first search wait for the profile load promise before rendering results. That avoids a race where a fast first search could miss expansion rules.

## Measured Effect

Query: `heart failure with reduced ejection fraction`

Direct retrieval still found only one anatomy result:

- `C0018787` `Heart`

The data-driven expansion profiles added three anatomy concepts:

- `C0225897` `Left Ventricle`
- `C0225899` `Myocardium of left ventricle`
- `C0018827` `Cardiac Ventricle`

Displayed anatomy count stayed at 4 after moving from hard-coded JavaScript rules to JSON profiles.

## Scaling Impact

Before:

- expansion logic was embedded in JavaScript as `ANATOMY_EXPANSION_RULES`
- adding another expansion required editing app logic
- the implementation was anatomy-specific

After:

- zero remaining `ANATOMY_EXPANSION_RULES` or `inferredAnatomyBucketItems` references
- one generic `inferredSemanticBucketItems()` path handles expansion for any semantic group
- current profile file contains 2 profiles and 3 inferred concept rows
- adding a new rule is now a data edit in `docs/search_quality/expansion_profiles.json`

## Verification

- `node --check docs/search_quality/app.js` passed.
- `python3 -m json.tool docs/search_quality/expansion_profiles.json` passed.
- `env PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_quality_http.py` passed.
- Confirmed the running server serves `/search_quality_expansion_profiles.json`.
- Confirmed served JavaScript contains `semanticExpansionProfilesReady` and `inferredSemanticBucketItems()`.
- Confirmed old hard-coded anatomy rule names are absent from both source and served JavaScript.

## Not Improved

This change improves maintainability and extensibility, not search speed. The HFrEF API run used for this check took about 48 seconds, which reinforces that query-time retrieval speed still needs a separate optimization pass.
