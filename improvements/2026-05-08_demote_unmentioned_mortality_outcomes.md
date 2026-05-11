# Demote Unmentioned Mortality Outcomes

## Problem

The GI bleeding query `He presented with hematemesis and melena after heavy NSAID use. Endoscopy found a bleeding gastric ulcer, and pantoprazole infusion was started before transfusion.` can surface generic mortality concepts such as `Death`. That is clinically plausible as an outcome in some literature, but it is not a concept stated in this note and should not compete with directly mentioned findings, disorders, drugs, or procedures.

## Why It Happened

Mortality concepts can enter through vector similarity or related-result expansion because papers about GI bleeding, transfusion, ulcers, or NSAID complications often discuss mortality. That is useful in a prognostic or outcomes query, but it is noise in a note-like extraction query where `death`, `mortality`, `fatal`, or `survival` are absent.

## Change

Added a mortality-outcome guard in ranking: labels such as `Death`, `Mortality`, `Fatality`, or `Deceased` receive a clinical context penalty unless the query explicitly asks for mortality/death/fatality/survival. Added a semantic-bucket relation filter so generic mortality related items are hidden from related result buckets.

This does not remove death globally. A query like `mortality after upper gastrointestinal bleeding` still allows the mortality concept without this penalty.

## Improvement

For the NSAID/gastric-ulcer bleeding sentence, direct concepts such as `Gastric ulcer` and `Melena` are protected from being outranked by unmentioned mortality. Generic mortality relations are no longer shown as related semantic group items unless they are direct hits in a mortality-focused query.

## Verification

- `python3 -m pytest tests/test_evidence_vectors.py -k 'mortality or semantic_buckets_hide_generic_mortality' -q` passed: 2 passed.
- `python3 -m pytest tests/test_evidence_vectors.py -k 'confirmation_status or mortality or semantic_buckets_hide_generic_mortality or semantic_buckets_hide_weak_ccpss_procedure_associations' -q` passed: 4 passed.
- `PYTHONPYCACHEPREFIX=.pycache_local python3 -m py_compile src/qe_evidence_vectors/search_ranking.py src/qe_evidence_vectors/search_semantic_buckets.py` passed.
