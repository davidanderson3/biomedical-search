# Search Rule Inventory

Generated from the current checkout by `python3 scripts/build_search_rule_inventory.py`.
Use this file as the review surface for heuristic changes: every rule should have a class, a source artifact, and a benchmark or audit artifact that explains why it exists.

## Why This Exists

The search stack is intentionally heuristic, but the rules should not be an unbounded pile of special cases. Keep them in named layers:

1. **Suppress generic/meta concepts** when UMLS exposes ordinary prose as concepts.
2. **Rescue clinical aliases** when a real clinical phrase should map to a known CUI.
3. **Classify assertion/currentness** when a mention is old, negated, uncertain, planned, or active.
4. **Handle patient-message meta language** when the user text contains conversational words that should not outrank clinical entities.
5. **Apply narrow ranking score guards** when a recurring error class cannot be represented as suppression or alias data.
6. **Audit useful extras versus false positives** so ranking changes target real errors.
7. **Guard with benchmark rows** so each improvement is repeatable.

## Rule Classes

| Class | Source | Purpose | Current Size |
| --- | --- | --- | --- |
| generic_meta_suppression | src/qe_evidence_vectors/generic_filters.py | Suppress UMLS concepts that behave like ordinary prose, form labels, or chart metadata instead of biomedical retrieval anchors. | 98 labels; 87 CUIs; 99 query blocks |
| clinical_alias_supplement | config/active_label_supplement.tsv | Add explicit, reviewed clinical phrases for known CUIs when core UMLS labels or default indexing miss the user-facing phrase. | 253 rows; 211 CUIs |
| assertion_context | src/qe_evidence_vectors/search_assertions.py | Classify mentions as current, negated, uncertain, historical, family-history, planned, or confirmed before ranking them. | 56 before-cues; 33 after-cues |
| patient_portal_meta_context | src/qe_evidence_vectors/search_ranking.py | Detect patient portal prose and suppress conversational uncertainty/meta words without suppressing clinical confusion contexts. | 12 context tokens; 8 noise tokens |
| precision_audit_outcomes | config/search_quality_precision_audit_review.tsv | Separate useful secondary concepts from true false positives so future ranking changes have an unambiguous target. | 69 reviewed rows |
| ranking_score_guards | src/qe_evidence_vectors/search_ranking.py | Apply narrow score components or penalties for recurring ranking error classes that cannot be expressed as generic suppression or alias supplementation. | 1 named guards |
| benchmark_guardrails | config/search_quality_paragraph_queries.tsv; config/search_quality_patient_portal_queries.tsv; config/search_quality_useful_extra_cuis.tsv | Keep rule changes measurable through expected CUIs, active/current CUIs, context CUIs, disallowed CUIs, and known useful extras. | 168 paragraph rows; 12 portal rows |

## Plain-Language Rule Guide

### Generic Meta Suppression

This is the hard-stop layer for UMLS labels that are technically concepts but are bad search answers in ordinary use. It catches words and phrases that usually mean the system latched onto prose, chart structure, or a form field instead of a biomedical entity.

- Use for: generic answers such as `Do not`, `Result`, `Instructions`, `Still`, `Unknown`, or `Problem` when they appear as standalone concepts.
- Do not use for: valid longer clinical phrases that contain generic words, such as `Do not resuscitate` or a specific diagnostic result.
- Guardrail: add a benchmark `disallowed_cuis` row or a unit test that proves the bad concept is suppressed while the valid clinical phrase still survives.

### Clinical Alias Supplement

This is the phrase-rescue layer. It adds explicit labels for real clinical phrases when the target CUI is correct but the default UMLS label index or evidence retrieval does not surface the wording users actually type.

- Use for: abbreviations, shorthand, and clinically meaningful phrases such as `Head CT`, `PHQ-9`, or local active-label wording that should resolve to a known CUI.
- Do not use for: current-versus-history interpretation, negation, generic noise, or concepts that need a new CUI rather than another label.
- Guardrail: each row needs a `why`, a semantic type, a field, and context gates for risky short labels or ambiguous aliases.

### Assertion and Currentness Context

This layer interprets the status of a real mention. It decides whether a concept is current, negated, uncertain, historical, family history, planned, or confirmed before ranking penalties are applied.

- Use for: cues like `old`, `another visit`, `history of`, `no evidence of`, `possible`, `planned`, or `confirmed` when they change how a nearby clinical mention should rank.
- Do not use for: suppressing standalone generic concepts or adding missing synonyms.
- Guardrail: add a benchmark row showing active/current CUIs above context CUIs, and add a unit test when the cue is reusable across query types.

### Patient Portal Meta Context

This layer handles patient-message wording. It recognizes that phrases such as `I am confused`, `I am worried`, `plain language`, or `what diagnosis should I use` describe the user's communication task, not the medical problem.

- Use for: conversational portal-message words that otherwise outrank the active medical issue.
- Do not use for: true clinical confusion, altered mental status, delirium, stroke, hypoglycemia, or other cases where `confused` is itself medically meaningful.
- Guardrail: portal benchmark rows should include active CUIs, context/history CUIs, and disallowed meta CUIs.

### Ranking Score Guards

This layer handles reusable ranking error classes that are too contextual for hard suppression and too behavioral for alias data. A guard should be named, scoped, and visible in score breakdowns.

- Use for: broad but valid concepts that should remain searchable, but should not outrank directly relevant anchors in a specific long-query context.
- Do not use for: missing synonyms, generic prose concepts that should be suppressed outright, or one-off CUI-specific hacks without a repeatable error class.
- Guardrail: add focused tests for both the demotion and the obvious direct-search false positive.

### Precision Audit Outcomes

This is the human judgment ledger for suspect results. It separates useful secondary concepts from true false positives so future score changes are measured against the right target.

- Use for: deciding whether a result that looks extra is actually helpful clinical context or should become a rule candidate.
- Do not use for: silently accepting broad drift without a readable reason.
- Guardrail: every row needs a review class, action, and `why` that a reviewer can understand without reading the ranking code.

### Benchmark Guardrails

This is the repeatability layer. It turns known examples into runnable expectations so heuristic changes can be checked before they become permanent behavior.

- Use for: user-visible failures, long patient messages, paragraph recall cases, PubMed abstracts, and known false positives.
- Do not use for: undocumented anecdotes or one-off checks that cannot be rerun.
- Guardrail: include expected CUIs, disallowed CUIs when relevant, and a short expected-behavior statement for the ranking intent.

## Where to Put a New Rule

| Problem | Preferred Artifact | Required Guardrail |
| --- | --- | --- |
| UMLS concept is generic prose or chart metadata, such as `Do not`, `Result`, or `Instructions`. | `src/qe_evidence_vectors/generic_filters.py` | A focused regression row with `disallowed_cuis`, or a unit test proving a clinical phrase such as DNR still survives. |
| A real clinical phrase is missing or under-ranked, but the target CUI is known. | `config/active_label_supplement.tsv` | `why`, semantic type, field, context gates for risky aliases, and `python3 scripts/validate_active_label_supplement.py`. |
| The mention is current versus old/history, negated, uncertain, planned, or family history. | `src/qe_evidence_vectors/search_assertions.py` | A patient/clinical benchmark row showing active CUIs above context CUIs, plus unit coverage when the cue is reusable. |
| Patient portal prose contains conversational uncertainty or workflow words. | `src/qe_evidence_vectors/search_ranking.py` patient-message meta context | A portal row with active/current CUIs, context CUIs, and disallowed meta CUIs. |
| A valid but broad ranked concept should remain searchable but stop winning in a repeatable context. | `src/qe_evidence_vectors/search_ranking.py` ranking score guard | A focused test for the failing context, a protection test for direct lookup, and a score-breakdown field. |
| A non-primary concept is expected and useful, not a false positive. | `config/search_quality_useful_extra_cuis.tsv` and `config/search_quality_precision_audit_review.tsv` | Audit classification with a human-readable `why`. |
| A new class of user-visible failure needs tracking. | `config/search_quality_*queries.tsv` | Expected CUIs, disallowed CUIs when applicable, and a short expected-behavior statement. |

## Current Generic Suppression

- Blocked labels: 98
- Blocked CUIs: 87
- Blocked exact queries: 99
- Label examples: `abnormal`, `at home`, `at least daily`, `at work`, `chart [medical device]`, `code system type internal`, `control aspects`, `control veterinary product`, `degree or extent`, `disease management`, `do not`, `domestic`, `elevated`, `entity risk aggressive`, `examined`, `extremely limited`, `fluid behavior`, `found down`, ... +80 more
- CUI examples: `C0007963`, `C0022885`, `C0027552`, `C0028678`, `C0033080`, `C0033213`, `C0087111`, `C0150312`, `C0150369`, `C0184511`, `C0205161`, `C0205217`, `C0205250`, `C0205266`, `C0205307`, `C0205396`, `C0225990`, `C0226003`, ... +69 more

Rule of thumb: add a generic suppression only when the concept is not useful as a standalone biomedical answer. If a longer clinical phrase is valid, protect it separately in a benchmark row.

## Current Clinical Alias Supplement

- Rows: 253
- Unique CUIs: 211
- Rows with `context_any`: 206
- Rows with `block_any`: 15

Field counts:

| Field | Rows |
| --- | --- |
| condition | 88 |
| finding | 46 |
| procedure | 37 |
| drug | 33 |
| lab | 23 |
| drug_alias | 14 |
| gene | 5 |
| context | 4 |
| organism | 2 |
| assessment | 1 |

Top semantic type counts:

| Semantic Type | Rows |
| --- | --- |
| Disease or Syndrome | 73 |
| Pharmacologic Substance | 44 |
| Finding | 34 |
| Diagnostic Procedure | 21 |
| Sign or Symptom | 18 |
| Therapeutic or Preventive Procedure | 16 |
| Laboratory Procedure | 10 |
| Pathologic Function | 6 |
| Gene or Genome | 5 |
| Immunologic Factor | 4 |
| Clinical Concept | 3 |
| Neoplastic Process | 3 |

## Current Assertion and Currentness Cues

Before-cue counts:

| Status | Cue Count |
| --- | --- |
| negated | 8 |
| uncertain | 12 |
| historical | 11 |
| family_history | 8 |
| planned | 7 |
| confirmed | 10 |

After-cue counts:

| Status | Cue Count |
| --- | --- |
| negated | 4 |
| uncertain | 4 |
| historical | 5 |
| family_history | 0 |
| planned | 15 |
| confirmed | 5 |

Chart-history cues: `another visit`, `from another visit`, `old`, `old problem`, `older`, `older problem`, `still list`, `still lists`

Rule of thumb: currentness belongs here when it changes how a real clinical mention should be interpreted. Generic words belong in suppression; missing synonyms belong in the active-label supplement.

## Current Patient Portal Meta Layer

- Context tokens: `call`, `explain`, `instruction`, `language`, `message`, `plain`, `portal`, `reply`, `scheduling`, `sort`, `summary`, `visit`
- Self tokens: `i`, `me`, `my`
- Noise tokens: `concern`, `concerned`, `confuse`, `confused`, `confusion`, `sure`, `worried`, `worry`
- Clinical confusion exception tokens: `altered`, `delirium`, `diaphoretic`, `encephalopathy`, `fall`, `febrile`, `fever`, `glucose`, `head`, `hypoglycemia`, `injury`, `lethargic`, `mental`, `sepsis`, `status`, `stroke`, `unresponsive`, `weak`, ... +1 more

Rule of thumb: this layer should require patient-message context before suppressing words like `confused` or `worried`, and it should exempt clinical confusion contexts such as hypoglycemia, delirium, or stroke.

## Current Ranking Score Guards

| Guard | Purpose | Scope | Guardrail |
| --- | --- | --- | --- |
| broad_corticosteroid_class_penalty | Demote broad steroid/corticosteroid class hits in long treatment-review queries when multiple non-class anchors show the abstract is about a condition and its treatment options. | Penalty 0.18; min query tokens 12; matched spans `corticosteroid`, `corticosteroids`, `steroid`, `steroids` | tests/test_evidence_vectors.py::test_ranker_demotes_broad_corticosteroid_class_in_long_status_review |

Rule of thumb: score guards should be visible in `score_breakdown`, limited by context, and backed by a positive test plus a direct-search protection test.

## Current Audit and Benchmark Guardrails

| Artifact | Rows / Values |
| --- | --- |
| Precision audit review rows | 69 |
| Known useful extra CUI rows | 111 |
| Paragraph benchmark rows | 168 |
| Paragraph rows with disallowed CUIs | 26 |
| Patient portal benchmark rows | 12 |
| Patient portal rows with disallowed CUIs | 12 |
| Patient portal active CUI values | 65 |
| Patient portal context CUI values | 23 |

Precision audit review classes:

| Review Class | Rows |
| --- | --- |
| useful_extra | 58 |
| true_false_positive | 11 |

Precision audit actions:

| Action | Rows |
| --- | --- |
| add_useful_extra | 58 |
| keep_rule_candidate | 11 |

## Review Standard

A new heuristic is sustainable when all of these are true:

1. It has a named class from this inventory.
2. The rule source is the narrowest artifact that can express it.
3. The `why` is readable by someone who did not write the code.
4. It has a focused query, disallowed CUI, useful-extra audit row, or unit test.
5. The full clinical smoke is run when the rule can affect broad ranking behavior.
