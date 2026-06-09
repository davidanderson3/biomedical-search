# Source Contribution Report

Generated: 2026-05-13

This report summarizes the source inventory currently present in local build
artifacts. Sources differ by integration state: some are already materialized in
the permitted public/source-subset add-on pack under `build/public`, some are
broader literature or enrichment layers, and some are relation/index or licensed
local index sources. Those are status differences, not separate source classes.

Permission-required clinician references such as Merck/MSD, AAFP, Medscape, BMJ
Best Practice, NICE CKS, Patient.info, GPnotebook, and WikEM remain excluded from
the default public corpus.

## Current Aggregate

The current permitted-source aggregate contains:

- `81,484` concept documents in `build/public/permitted_sources_concept_documents.jsonl`
- `81,484` hashing vectors in `build/public/permitted_sources_concept_vectors.hashing.jsonl`
- `566,444` linked evidence signals feeding the current concept documents/vectors
- `48,249` source records across the currently integrated source-subset builds

There is also an older broad evidence artifact,
`build/public/permitted_sources_evidence.jsonl`, with `79,650` evidence signals
for the first four sources only. The current concept/vector pack is better represented by the
profile-sharded evidence for the original four sources plus the newer
`source_subsets/*/*_evidence.jsonl` files.

This is not the whole repository source inventory. It is the smaller public
reference/source-subset pack that can be loaded alongside the larger literature
and local builds described below.

Think of the counts as three pipeline stages:

- **Source records** are the raw items fetched from a source, such as one article
  abstract, ontology term, clinical trial, drug label, reference page, image
  record, or structured local record.
- **Linked evidence / relation signals** are the useful CUI-linked matches
  extracted from those raw items. One source record can produce many signals.
- **Retrieval records** are the final searchable concept documents or index
  records. These are what the search layer can retrieve directly; many evidence
  signals can be rolled into one retrieval record.

Example: one DailyMed drug label is one source record. It can produce many
linked signals for indications, adverse effects, warnings, and contraindications.
Those signals are then grouped into concept-level retrieval records and vectors.

## Source Inventory And Contribution

All source layers and tracked source candidates are listed in one table. The
comparable takeaway column explains how to read each row. For sources integrated
into the public pack, it reports the share of
`permitted_sources_concept_documents.jsonl` and matching vectors attributable to
that source. For broader local layers, it says they are outside the public
add-on pack instead of treating them as directly comparable public-pack shares.

| Source | Status | Source records | Linked evidence / relation signals | Retrieval records | Comparable takeaway | Contribution |
| --- | --- | ---: | ---: | ---: | --- | --- |
| Human Phenotype Ontology | Integrated concept/vector pack | `19,389` | `138,554` | `30,439` | In the public pack, this source supplies `37.4%` of searchable retrieval records and `24.5%` of linked evidence signals. Density: `7.1` signals per source record. | Phenotype labels, definitions, synonyms, UMLS/SNOMED/NCIT/MEDDRA-style xrefs, parent terms, and HPO relationship text. Adds direct phenotype retrieval and exposes xref language that UMLS does not retain as a full native crosswalk. |
| Mondo Disease Ontology | Integrated concept/vector pack | `27,990` | `381,816` | `40,486` | In the public pack, this source supplies `49.7%` of searchable retrieval records and `67.4%` of linked evidence signals. Density: `13.6` signals per source record. | Harmonized disease labels, definitions, synonyms, xrefs, and hierarchy text. |
| NCBI Bookshelf / NLM LitArch OA | Integrated concept/vector pack | `49` | `19,775` | `2,652` | In the public pack, this source supplies `3.3%` of searchable retrieval records and `3.5%` of linked evidence signals. Density: `403.6` signals per source record. | Open-access guideline/report/book-chapter language; current subset covers adult obesity evaluation/treatment and asthma diagnosis/management reports. |
| MedlinePlus Genetics | Integrated concept/vector pack | `500` | `12,900` | `3,116` | In the public pack, this source supplies `3.8%` of searchable retrieval records and `2.3%` of linked evidence signals. Density: `25.8` signals per source record. | Genetic conditions, phenotypes, inheritance language, related genes/chromosomes, consumer-readable disease descriptions. |
| MedlinePlus | Integrated concept/vector pack | `250` | `6,696` | `2,118` | In the public pack, this source supplies `2.6%` of searchable retrieval records and `1.2%` of linked evidence signals. Density: `26.8` signals per source record. | Lay symptom names, condition summaries, test names, patient-facing aliases, topic groupings. |
| ClinicalTrials.gov | Integrated concept/vector pack | `50` | `3,271` | `1,417` | In the public pack, this source supplies `1.7%` of searchable retrieval records and `0.6%` of linked evidence signals. Density: `65.4` signals per source record. | Trial-design language: conditions, interventions, eligibility criteria, outcomes, populations, phases, status. |
| DailyMed | Integrated concept/vector pack | `10` | `1,695` | `555` | In the public pack, this source supplies `0.7%` of searchable retrieval records and `0.3%` of linked evidence signals. Density: `169.5` signals per source record. | Drug-label language: indications, dosage, contraindications, warnings, adverse reactions, interactions, use in populations, clinical pharmacology. |
| NCI | Integrated concept/vector pack | `3` | `639` | `258` | In the public pack, this source supplies `0.3%` of searchable retrieval records and `0.1%` of linked evidence signals. Density: `213.0` signals per source record. | Cancer diagnosis, treatment modality, risk-factor, testing, biopsy, imaging, and oncology workup language. |
| NIDDK | Integrated concept/vector pack | `3` | `542` | `239` | In the public pack, this source supplies `0.3%` of searchable retrieval records and `0.1%` of linked evidence signals. Density: `180.7` signals per source record. | Diabetes, kidney disease, digestive disease, endocrine/nutrition education, complications, tests, management terms. |
| FDA | Integrated concept/vector pack | `2` | `232` | `105` | In the public pack, this source supplies `0.1%` of searchable retrieval records and `0.04%` of linked evidence signals. Density: `116.0` signals per source record. | Drug-safety and consumer/professional drug-information language; labeling, recalls, warnings, and safety infrastructure terms. |
| CDC | Integrated concept/vector pack | `3` | `324` | `99` | In the public pack, this source supplies `0.1%` of searchable retrieval records and `0.06%` of linked evidence signals. Density: `108.0` signals per source record. | Public-health and prevention language; current subset covers diabetes, influenza, and sepsis. |
| PubMed abstracts and recent-bulk literature | Broader corpus/vector layer | `467,556` | Profile evidence counted below | `398,654` compact vectors | Outside the public add-on pack; contributes to the local literature vector layer. | Core biomedical research prose, abstracts, disease/drug/procedure language, and current literature phrasing. |
| Europe PMC abstracts | Broader corpus layer | `41,839` | Profile evidence counted below | `0` standalone vectors | Outside the public add-on pack; contributes to the local literature corpus layer. | Additional literature coverage and abstracts that overlap with, extend, or complement PubMed. |
| PMC Open Access full text | Broader corpus/evidence layer | `2,397` | `545,863` | `0` standalone vectors | Outside the public add-on pack. In the common-clinical profile, density is `227.7` evidence signals per source record. | Open full-text article context, longer methods/results/discussion prose, and dense co-mention evidence. |
| Literature profile evidence | Broader evidence layer | Derived from PubMed / Europe PMC | `236,894` biomedicine; `427,573` expanded | Feeds broader concept builds | Outside the public add-on pack; profile-sharded evidence for broader local retrieval builds. | Profile-sharded CUI evidence derived from PubMed/Europe PMC literature. |
| cui2vec | External CUI embedding-neighbor index | `30,207` source CUIs | `241,656` neighbor edges | `56,264` target CUIs | External neighbor index, not source text. Density: `8.0` neighbor edges per source CUI. | Distributional CUI-CUI similarity signal derived from external biomedical embeddings. Useful for related-concept expansion and weak association discovery, not direct textual evidence. |
| BioConceptVec | External CUI embedding-neighbor index | `17,104` source CUIs | `136,832` neighbor edges | `55,097` target CUIs | External neighbor index, not source text. Density: `8.0` neighbor edges per source CUI. | Distributional biomedical concept-neighbor signal. Complements UMLS relations and local corpus evidence with embedding-based associations from a third-party vector source. |
| OpenAlex top-cited evidence | Enrichment concept/vector layer | `124` | `2,340` | `878` concept docs/vectors | Outside the public add-on pack. In the enrichment layer, density is `18.9` evidence signals per source record. | High-citation metadata and abstracts for high-impact clinical, diagnostic, drug, genomic, and procedure topics. |
| Drug enrichment | Enrichment concept/vector layer | `27` target drug CUIs | Code-index and literature signals | `27` concept docs/vectors | Outside the public add-on pack; one retrieval record per targeted drug concept. | Open literature plus RxNorm/ATC/MTHSPL/DrugBank code-index signals for targeted drug concepts. |
| Wikipedia enrichment | Enrichment concept/vector layer | `2` selected concepts | `0` linked evidence signals | `2` concept docs/vectors | Outside the public add-on pack; one retrieval record per selected concept. | Open encyclopedia text for selected concepts where license-compatible. |
| Wikimedia/open image enrichment | Enrichment metadata layer | `37` image records | `37` image provenance signals | `21` image-enriched concept docs/vectors | Outside the public add-on pack; metadata enrichment, not primary clinical evidence. | Visual/media metadata and image provenance for selected concepts; useful for UI enrichment, not primary clinical reasoning. |
| HPO native annotations and xrefs | Relation/index source | `19,944` OBO terms; `612,062` annotation records | `58,976` relation signals | `0` vector docs | Outside the public vector pack; opt-in relation/index contribution rather than searchable public vectors. | Disease-to-phenotype, gene-to-phenotype, disease-to-gene, and gene-to-disease links using HPO annotations plus HPO UMLS xrefs and OMIM/ORPHA/DECIPHER mappings. Treat annotation-derived artifacts as opt-in for redistribution because upstream disease annotations may carry source-specific reuse caveats. |
| UMLS-derived local indexes | Licensed identity/index source | `84,972` definitions | `9,112,359` code mappings; `483,677` related-concept records; `3,876,927` semantic-type records | `0` public vectors | Licensed local index contribution; not public vector content or source text. | CUI identity backbone, code resolution, source-vocabulary labels, definitions, semantic type routing, and relation expansion. |
| Permission-required clinician references | Tracked restricted/candidate sources | `0` public/default source records | `0` public/default evidence signals | `0` public/default concept docs/vectors | No public/default contribution until permission, licensed content, or a compliant reuse strategy exists. | Potential clinician-reference contribution remains zero unless a deployment has permission, licensed content, or a compliant reuse strategy. |

Representative combined concept-document builds include
`build/biomedicine_scaled_top12_concept_documents.jsonl` with `21,998` concept
documents. These are broader local build products and are separate from the
public permitted-source add-on pack.

## Subset Selection Rationale

The current subsets are seed slices, not claims that these are the only useful
records in each source. They were chosen to keep the public build license-safe,
reproducible, and small enough to rebuild quickly while covering retrieval gaps
that UMLS labels and literature alone do not handle well.

| Source | Current subset rule | Why this slice was chosen | What it intentionally omits |
| --- | --- | --- | --- |
| Human Phenotype Ontology | Current non-obsolete HPO OBO terms from `hp.obo`. | The ontology is compact enough to include broadly, and phenotype labels/synonyms/xrefs are a major gap in plain UMLS label retrieval. | Obsolete terms by default. Annotation-derived disease/gene phenotype relationships remain opt-in until upstream annotation reuse terms are reviewed. |
| Mondo Disease Ontology | Current MONDO OBO term corpus from `mondo.obo`; linked and vectorized into the public concept pack. | MONDO gives normalized disease names, synonyms, definitions, xrefs, and hierarchy in a license-compatible form. | Obsolete terms by default. Native MONDO xref and hierarchy semantics are still not a separate first-class relation graph. |
| MedlinePlus | Bounded English health-topic XML subset from the current MedlinePlus feed. | It adds patient-facing language, common symptom terms, aliases, tests, and topic groupings that users actually type. | Spanish topics and the full health-topic feed are omitted from the current bounded public pack. |
| MedlinePlus Genetics | Bounded set from the current MedlinePlus Genetics / GHR summaries XML. | It gives rare-disease and genetics language, including gene symbols, inheritance, chromosomes, and phenotype descriptions. | The current bounded slice is not exhaustive genetics coverage. |
| ClinicalTrials.gov | Query seed: `cancer OR diabetes OR migraine OR sepsis OR pneumonia`, bounded by record count. | Those conditions exercise common clinical domains and produce useful trial language for interventions, eligibility, outcomes, phases, and populations. | It is not a representative sample of all trials and is not evidence that interventions work. |
| DailyMed | One bounded label per seed drug: metformin, insulin, osimertinib, sumatriptan, pantoprazole, cephalexin, amoxicillin, warfarin, semaglutide, and acetaminophen. | The list covers common chronic medications, antibiotics, anticoagulation, migraine therapy, oncology therapy, OTC analgesics, and high-value label sections such as warnings and contraindications. | It omits the full DailyMed label universe, duplicate manufacturer labels, and most drug classes. |
| NCBI Bookshelf / NLM LitArch OA | Open Access LitArch packages matched by guideline/report terms; current records come from one obesity evidence report and two asthma expert panel reports. | This is the safest route to long-form guideline/report language because package licenses are preserved and non-OA Bookshelf material is avoided. | StatPearls and other Bookshelf titles with restrictive or uncertain reuse terms are omitted, as are most specialties. |
| NCI | Default public pages for cancer diagnosis, treatment types, and risk factors. | These pages add practical oncology workup, treatment-modality, and risk-factor language from a reusable government source. | Broader PDQ, dictionary, and cancer-specific pages are not yet included. |
| CDC | Default public pages for diabetes, influenza, and sepsis. | These cover high-volume public-health and clinical topics with prevention, symptom, testing, and care language. | Most CDC condition pages, vaccine pages, outbreak pages, and data reports are omitted. |
| FDA | Default public pages for drug safety/availability and consumer/patient drug information. | The goal is general drug-safety vocabulary and FDA-facing medication information without relying only on individual SPL labels. | Product-specific safety communications, recalls, approvals, and device pages are omitted. |
| NIDDK | Default public pages for diabetes overview, kidney disease, and digestive diseases. | These pages fill endocrine, kidney, and GI education gaps with reusable NIH institute content. | Deeper NIDDK subtopic pages and non-default institute pages are omitted. |
| PubMed, Europe PMC, and PMC OA | Topic-driven literature chunks focused on biomedicine, common clinical problems, drug safety, abbreviation language, diagnostics, procedures, and devices. | The chunks target search-quality gaps and current biomedical phrasing while keeping local indexing tractable. | They are not a systematic literature review or a complete biomedical literature corpus. |
| OpenAlex top-cited evidence | Six broad clinical/biomedical queries over a recent five-year window, filtered to high-citation works. | This adds high-impact literature metadata and abstracts for common clinical, diagnostic, drug, genomic, and procedure topics. | Lower-cited papers, older classics outside the window, and niche topic areas are underrepresented. |
| Drug enrichment | Twenty-seven target drug CUIs with open literature plus RxNorm, ATC, MTHSPL, and DrugBank mapping signals. | The targets were chosen to improve known drug-query gaps and to preserve code-vocabulary signals around common and high-impact medications. | It is not a comprehensive drug ontology or complete formulary expansion. |
| Wikipedia and Wikimedia/open images | Selected concepts and image targets from local enrichment configs, with compatible source/license metadata. | These layers are meant for UI enrichment and occasional open encyclopedia context, not primary clinical reasoning. | They intentionally avoid broad scraping and do not attempt comprehensive medical coverage. |
| cui2vec and BioConceptVec | Locally available external CUI-neighbor indexes with bounded nearest-neighbor rows. | They add distributional related-concept recall when curated relations or text evidence are sparse. | They are not textual evidence and should be treated as association signals, not curated clinical facts. |
| UMLS-derived local indexes | Licensed local indexes for code mappings, definitions, semantic types, and related concepts. | These provide the identity backbone needed to resolve labels, codes, CUIs, and semantic routing. | They are not redistributable public source text and do not replace source-specific evidence. |
| Permission-required clinician references | No public/default records. | They are tracked because they would be useful for clinician-style differential diagnosis and management language. | They remain excluded until a deployment has permission, licensed content, or a compliant source-specific reuse strategy. |

## Count Choice And Expansion Guidance

The counts are current artifact counts, not targets chosen to make sources
numerically equal. They come from different extraction rules: complete ontology
slices, bounded seed pulls, topic/profile-filtered literature, external index
caps, or licensed local indexes. A useful expansion should be driven by measured
retrieval gaps, clear reuse terms, and evaluation gains rather than by row size
alone.

## Measured Source-Aware Acquisition Policy

The implemented acquisition policy is now executable instead of only advisory.
It reads `paragraph_quality_summary.tsv` files, joins benchmark query specs for
expected CUIs, infers review-only candidate false positives from high-ranking
non-expected hits, and creates expected-CUI association pairs. When relation
indexes are available, those association pairs are filtered against existing
UMLS/MRREL, research-relation, and relationship-edge indexes so the queue
emphasizes associations not already available from local UMLS-derived sources.
All acquisition scores are prevalence-weighted: the planner starts with measured
failure weight, then applies a bounded prevalence/commonness multiplier before
ranking source actions and relationship-edge work. It also ranks pair-level
association candidates by expected utility: measured failure weight, novelty,
relation clarity, sourceability, text proximity, and the same prevalence prior
for common conditions, lab tests, procedures, and drugs. By default the CLI loads
`config/source_acquisition_prevalence_priors.tsv` when present. A custom
prevalence TSV can extend or override that prior with a
`cui` plus `prevalence_weight`/`utility_weight`/`commonness`/`priority`/`weight`
column; use `--no-default-prevalence-prior` to run with heuristic commonness
only. When `build/umls_biomedicine_search_label_index.sqlite` exists, it is used
by default for acquisition labeling because measured source builds need broad
drug, gene, condition, lab, procedure, and synonym coverage.

Run it with:

```sh
python3 scripts/evidence_vectors.py plan-source-acquisition \
  --quality-summary build/improvements/<run>/paragraph_quality_summary.tsv \
  --out-json build/source_acquisition/plan.json \
  --out-tsv build/source_acquisition/recommendations.tsv \
  --out-associations-tsv build/source_acquisition/association_candidates.tsv \
  --out-association-review-tsv build/source_acquisition/association_review.tsv \
  --out-bundle-dir build/source_acquisition/bundle \
  --out-md build/source_acquisition/plan.md
```

The output is a review queue and acquisition bundle, not an automatic corpus
merge. Recommendations include the source, action, seed, measured query evidence,
missing CUIs, configured and candidate disallowed CUIs, unavailable association
pairs, ranked association evidence candidates, and a suggested next command. The
bundle also writes source seed TSVs, literature topic TSVs, review templates, and
a command checklist for the highest-utility acquisition actions. This keeps
acquisition tied to measured search failures and missing associations while
preserving human review before corpus changes. The TSV/JSON outputs include raw
failure weight, weighted failure weight, prevalence score, and prevalence
multiplier so ranking decisions are inspectable.

Approved review rows can be converted into indexable universal relationship-edge
JSONL only after the reviewer supplies supporting evidence and marks
`review_decision` as approved:

```sh
python3 scripts/evidence_vectors.py build-reviewed-association-edges \
  --review build/source_acquisition/association_review.tsv \
  --out build/source_acquisition/reviewed_relationship_edges.jsonl
```

### Live acquisition test result

The first measured acquisition pass showed why acquisition has to be tested, not
just queued. A narrow clinical label index produced fewer useful anchors and
slightly reduced focused recall@10. Rebuilding with
`build/umls_biomedicine_search_label_index.sqlite` fixed the coverage issue for
drug, gene, oncology, lab, and disease labels.

Current staged acquisition artifacts are under
`build/source_acquisition/acquired_biomedicine/`,
`build/source_acquisition/acquired_round2/`,
`build/source_acquisition/acquired_round3/`, and
`build/source_acquisition/acquired_round4/`. The tested evidence includes
DailyMed labels, NCI reference pages, MedlinePlus Genetics gene summaries,
expanded PubMed association topics, a focused severe-hypoglycemia PubMed slice,
and a corrected default-ambiguity DailyMed clopidogrel/osimertinib slice.

The progression is now reproducible from
`config/source_acquisition_progression.tsv`:

```sh
python3 scripts/source_acquisition_progression.py --fail-on-regression
```

This writes `build/source_acquisition/progression_manifest.json` and
`build/source_acquisition/progression_report.md`. The manifest records each
stage's hypothesis, source scope, benchmark metrics, artifact inventory, small
file hashes, decision, and deterministic gate result. Gates compare each stage
with the previous retained stage in the same group; rejected diagnostic stages
are recorded without lowering the next gate. Group summaries keep the final
delta against the original baseline.
On a fresh GitHub clone before historical `build/` artifacts exist, run the
same command with `--allow-missing-stage-metrics` to inspect the ledger shape
without requiring local metric files.

Measured results on the six source-acquisition benchmark rows
(`paragraph_156`-`paragraph_161`):

| Run | Verdicts | Recall@5 | Recall@10 | Recall@20 | Disallowed@10 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 5 good / 1 mixed | 25/35 | 34/35 | 34/35 | 0/6 |
| Acquired evidence | 6 good / 0 mixed | 24/35 | 34/35 | 35/35 | 0/6 |

The gain comes mainly from paragraph_161, where acquired oncology evidence moves
brain-metastasis coverage into the useful window. The remaining top-10 miss is
paragraph_156's accepted severe-hypoglycemia concept; it is present by rank 20,
so the remaining work is ranking/crowding rather than evidence absence.

### Recent missing high-citation articles

Round 5 acquired a candidate OpenAlex shard of recent highly cited articles that
were missing from the existing OpenAlex cited layer and local recent PubMed bulk
corpora. The reproducible query set is
`config/openalex_missing_high_citation_queries.tsv`; the build used a five-year
window ending 2026-05-14, a minimum citation count of 500, and exclusion against
the existing OpenAlex corpus plus recent PubMed bulk corpora. It selected `72`
missing articles from `718` deduplicated candidates, removed `604` below the
citation floor and `42` already represented articles, then built `1,289`
evidence records and `552` concept vectors under
`build/source_acquisition/acquired_round5/openalex_missing_high_citation/`.

This shard is not promoted into the default path yet. It is neutral on the
accepted six-row acquisition benchmark (`6` good, `34/35` recall@10, `35/35`
recall@20, no disallowed@10), but the full default 161-row benchmark regressed
slightly from `144` good / `17` mixed and `831/835` recall@10 to `143` good /
`18` mixed and `830/835` recall@10. It remains useful candidate evidence, but
needs source-aware routing/filtering before broad default inclusion.

**Ontology weighting note:** HPO and MONDO now dominate the public
concept-document count because the build includes broad non-obsolete ontology
term sets while most other public sources are still small seed slices. That is
reasonable for phenotype and disease recall, but it should not automatically
mean ontology records get most of the ranking weight. General clinical retrieval
should use source-aware caps, boosts, or query-type routing so ontology terms do
not crowd out drug labels, guidelines, trials, patient education, literature, or
government health pages.

| Source | Why this count | Keep building? | Best next expansion |
| --- | --- | --- | --- |
| Human Phenotype Ontology | The count is the current non-obsolete HPO term set, so it is already a broad ontology slice rather than a hand-picked cap. | Yes, as a refreshed baseline; not as an uncapped ranking weight. | Refresh releases, add reviewed annotation/xref relation packs separately, and calibrate HPO boosts against non-phenotype sources. |
| Mondo Disease Ontology | The count reflects the current linked/vectorized MONDO corpus; it is now a broad ontology slice rather than a hand-picked cap. | Yes, as a refreshed baseline; not as an uncapped ranking weight. | Refresh releases, add explicit MONDO xref/hierarchy relation indexes, and calibrate disease-ontology boosts against other clinical sources. |
| MedlinePlus | The current count is a bounded English topic slice chosen for rebuild speed and common patient-language coverage. | Yes. | Move toward the full English feed first; add Spanish as a separate bilingual retrieval decision. |
| MedlinePlus Genetics | The bounded slice gives dense rare-disease and genetics language without making the public pack large on the first pass. | Yes. | Expand toward the full Genetics feed while monitoring duplicate concept merges and gene-symbol ambiguity. |
| ClinicalTrials.gov | The count comes from a small seed query over common conditions, meant to capture trial wording without flooding the corpus. | Selective. | Add condition seeds from query logs and keep trial text clearly separated from treatment-efficacy evidence. |
| DailyMed | The ten labels were seed drugs chosen to cover common, high-impact, and safety-sensitive medication classes. | Yes, high priority. | Expand to top prescribed, high-risk, and high-query medications, then de-duplicate manufacturer label variants. |
| NCBI Bookshelf / NLM LitArch OA | The count reflects license-compatible OA packages that matched guideline/report terms in the current pass. | Yes, high priority. | Add more OA reports and guidelines after preserving package license metadata and excluding uncertain titles. |
| NCI | The three-page count is a public-domain oncology smoke test for diagnosis, treatment, and risk-factor language. | Yes. | Add public cancer topic, PDQ, dictionary, staging, testing, and treatment pages in controlled batches. |
| CDC | The three-page count is a public-health seed slice for high-volume topics and prevention/testing language. | Yes. | Add high-volume condition, vaccine, outbreak, testing, and prevention pages with page-level provenance. |
| FDA | The two-page count seeds general drug-safety vocabulary without pulling broad product-specific notices yet. | Yes. | Add recalls, approvals, device, safety communication, and consumer drug pages by product class with dedupe. |
| NIDDK | The three-page count seeds endocrine, kidney, nutrition, and digestive disease language from reusable institute pages. | Yes. | Add deeper diabetes complication, CKD, digestive disease, endocrine, and nutrition pages. |
| PubMed abstracts and recent-bulk literature | The large count is the result of local topic/profile filters over available literature, not an intended share of the public pack. | Yes, evaluation-driven. | Expand where query failures show missing current terminology; avoid bulk growth that does not improve retrieval metrics. |
| Europe PMC abstracts | The count is the staged Europe PMC complement to PubMed after local filters and availability checks. | Selective. | Use it to fill coverage gaps and de-duplicate aggressively by DOI, PMID, title, and concept evidence. |
| PMC Open Access full text | The count is smaller because only OA full-text records are included, but each full-text article can produce many evidence signals. | Selective, with license checks. | Expand OA full-text subsets by topic and tune chunking so long papers do not dominate concept evidence. |
| Literature profile evidence | The evidence counts are generated outputs from CUI-linking profile shards over the broader literature corpus. | Yes, as a build product. | Tune profile queries, linking thresholds, and evidence weighting against held-out retrieval examples. |
| cui2vec | The count reflects the local external embedding index and a bounded neighbor fan-out of about eight edges per source CUI. | Keep as support signal. | Tune top-k, weights, and filters; do not treat embedding neighbors as textual clinical evidence. |
| BioConceptVec | The count reflects the available BioConceptVec CUI coverage with the same bounded neighbor fan-out. | Keep as support signal. | Use it to supplement sparse concepts and compare its neighbors against curated relations before boosting. |
| OpenAlex top-cited evidence | The count comes from six broad recent queries filtered to highly cited works, so it favors broad signal over exhaustive coverage. | Yes, selectively. | Expand query topics and time windows where high-level evidence metadata improves ranking or snippets. |
| Drug enrichment | The 27 target CUIs were selected to address known drug-query gaps and preserve code-vocabulary links around priority medications. | Yes, high priority. | Expand by drug class and query frequency while preserving RxNorm, ATC, MTHSPL, and DrugBank provenance. |
| Wikipedia enrichment | The two selected concepts keep encyclopedia text supplemental rather than a primary clinical source. | Low priority. | Add only where open encyclopedia context fills nonclinical background gaps that source evidence misses. |
| Wikimedia/open image enrichment | The image count is based on selected visual targets with compatible license/provenance metadata. | Optional. | Expand for concepts where visual media materially helps the UI and the license metadata is clear. |
| HPO native annotations and xrefs | The relation count comes from staged HPO annotation and xref artifacts, not from public text vectorization. | Yes, after reuse review. | Publish as an opt-in relation pack rather than blending all annotation-derived signals into default text vectors. |
| UMLS-derived local indexes | The counts are licensed local identity, code, semantic-type, definition, and relation indexes, not redistributable public text. | Yes, for licensed deployments. | Keep refreshed and improve CUI/code resolution, semantic routing, and provenance-aware relation expansion. |
| Permission-required clinician references | The count is zero because these sources are excluded until permission, licensed content, or a compliant reuse strategy exists. | Only with permission. | Add as a separate licensed deployment pack if rights are cleared; keep the public default at zero. |

## Implementation Status

"Fully implemented" depends on the layer being discussed. In this report, the
strongest implementation state is inclusion in the public
`permitted_sources_concept_documents.jsonl` and matching vector pack. Several
other sources are implemented locally or staged as relation indexes, but they
are not fully integrated into that public pack.

| Source or layer | Public concept/vector pack? | Current implementation state | What is not fully implemented |
| --- | --- | --- | --- |
| HPO term documents | Yes | Implemented as public concept documents/vectors from non-obsolete HPO terms. | Ranking normalization is still a policy/evaluation decision; HPO annotation-derived relations remain separate. |
| MedlinePlus, MedlinePlus Genetics, ClinicalTrials.gov, DailyMed, NCBI Bookshelf / NLM LitArch OA, NCI, CDC, FDA, NIDDK | Yes | Implemented in the public pack as bounded seed subsets. | These are not full-source imports. They need broader source coverage, dedupe, and evaluation before being considered complete. |
| Mondo Disease Ontology | Yes | Implemented as public concept documents/vectors from non-obsolete MONDO terms. | Ranking normalization and native MONDO xref/hierarchy relation indexes are still separate follow-up work. |
| PubMed, Europe PMC, PMC OA, and literature profile evidence | No | Implemented as broader local corpus/evidence/vector build products. | Not part of the public permitted-source add-on pack; Europe PMC and PMC OA are not standalone public vectors in this report. |
| OpenAlex, drug enrichment, Wikipedia, and Wikimedia/open images | No | Implemented as enrichment or metadata layers outside the public add-on pack. | Not broadly integrated into the default public concept/vector aggregate. |
| cui2vec and BioConceptVec | No | Implemented as external neighbor indexes. | They are not source text, not public evidence documents, and should only support ranking/expansion with source-aware weighting. |
| HPO native annotations and xrefs | No | Staged as relation/index signals. | Not part of the public vector pack by default; annotation reuse terms need review before public redistribution. |
| UMLS-derived local indexes | No | Implemented as licensed local identity/code/definition/semantic-type indexes. | Not redistributable public source text and not public vectors. |
| Permission-required clinician references | No | Not implemented in the public/default corpus. | They remain zero until rights, licensing, or a compliant source-specific reuse strategy exists. |

## Source Roles

**MedlinePlus** helps bridge user and patient language to CUIs. It is strong for
plain-English symptoms, disease summaries, common diagnostic tests, and “also
called” labels. It is less detailed than clinician references but useful for
query expansion because users often search in consumer language.

**MedlinePlus Genetics** adds structured genetics coverage that general health
topic pages lack. It contributes gene symbols, condition names, inheritance and
phenotype language, related chromosomes, and cross-database identifiers.

**Human Phenotype Ontology** is present in two different ways. The source-subset
pack now includes HPO term documents with labels, synonyms, definitions, xrefs,
parents, and relationship text. Separately, the research-relation index uses
staged HPO annotation files to add `has_phenotype`, `gene_has_phenotype`,
`gene_associated_with_disease`, and `disease_has_associated_gene` links. This is
the part that UMLS alone does not provide.

**cui2vec and BioConceptVec** contribute external embedding-neighbor signals,
not source text. They are useful for recall-oriented related-concept expansion
and exploratory associations, but should be treated as co-occurrence or
distributional support rather than curated clinical knowledge.

**DailyMed** contributes high-quality drug-label text. It is particularly useful
for drug to indication, drug to adverse effect, drug to contraindication, drug
interaction, pregnancy/lactation/population, and clinical pharmacology contexts.

**ClinicalTrials.gov** contributes structured research and eligibility language.
It is useful for connecting diseases, interventions, populations, biomarkers,
procedures, and outcomes, but should not be interpreted as evidence that an
intervention is effective.

**NCBI Bookshelf / NLM LitArch Open Access** is the closest currently integrated
open source to long-form guideline text. The implementation uses the NLM LitArch
Open Access FTP file list and tarball packages, preserving package license
metadata. The current bounded fetch selected:

- `21` documents from *Clinical Guidelines on the Identification, Evaluation,
  and Treatment of Overweight and Obesity in Adults: The Evidence Report*
- `12` documents from *Expert Panel Report 2: Guidelines for the Diagnosis and
  Management of Asthma*
- `16` documents from *Expert Panel Report 3: Guidelines for the Diagnosis and
  Management of Asthma*

**NCI, CDC, FDA, and NIDDK reference pages** fill practical government-reference
gaps. They add curated public-domain or mostly reusable disease, diagnostic,
treatment, drug-safety, and public-health language without relying on
copyrighted clinician manuals.

## Semantic Coverage

For the original profile-sharded permitted-source bundle
(`clinicaltrials_gov`, `medlineplus`, `medlineplus_genetics`, `dailymed`), the
profile evidence distribution is:

| Profile | Evidence signals | Strongest contributing sources |
| --- | ---: | --- |
| Clinical | 14,382 | MedlinePlus Genetics, MedlinePlus, ClinicalTrials.gov |
| Procedures / devices | 2,818 | MedlinePlus, ClinicalTrials.gov, DailyMed |
| Labs / measurements | 2,587 | MedlinePlus, MedlinePlus Genetics, ClinicalTrials.gov |
| Anatomy | 2,384 | MedlinePlus Genetics, MedlinePlus |
| Chemicals / drugs | 1,318 | MedlinePlus, MedlinePlus Genetics, ClinicalTrials.gov, DailyMed |
| Genes / proteins | 903 | MedlinePlus Genetics |
| Organisms | 170 | MedlinePlus, ClinicalTrials.gov |

The newer source-subset builds (`hpo`, `ncbi_bookshelf_oa`, `nci`, `cdc`, `fda`,
`niddk`) are currently linked through the source-subset path rather than the
profile-sharded path, so their concept-document views appear as source-specific
views such as `hpo_hpo_context`, `ncbi_bookshelf_oa_ncbi_bookshelf_oa_context`,
and `nci_nci_context`.

The current local research-relation index also contains `58,976` HPO-derived
relation signals: `24,945` `has_phenotype`, `24,052` `gene_has_phenotype`, `6,392`
`gene_associated_with_disease`, and `3,587` `disease_has_associated_gene`.

## Licensing And Access Boundary

Public/default sources:

- MedlinePlus and MedlinePlus Genetics: public NLM XML feeds.
- DailyMed: public SPL label service.
- ClinicalTrials.gov: public API.
- NCI, CDC, FDA, NIDDK: reusable government pages with page-level caveats.
- NCBI Bookshelf / NLM LitArch OA: only the Open Access subset, fetched through
  the NLM LitArch FTP route; package-level licenses are preserved.
- HPO and MONDO: public OBO ontology sources with attribution/version metadata.
  HPO annotation-derived phenotype relationships are useful but should remain
  opt-in for redistributable builds until upstream annotation-source terms are
  reviewed.

Restricted/candidate sources:

- Merck/MSD Manual Professional, AAFP, Medscape, BMJ Best Practice, NICE CKS,
  StatPearls outside the NLM LitArch OA subset, Patient.info Professional,
  GPnotebook, and WikEM remain policy-tracked but blocked from the public
  rebuild unless a deployment has permission, licensed content, or a compliant
  source-specific reuse strategy.

## Practical Implications

The broader current source mix is good for:

- symptom and patient-language expansion
- genetics/phenotype expansion
- rare-disease phenotype, disease-gene, and gene-phenotype relationships
- drug safety and drug-label relationships
- trial eligibility/intervention/outcome language
- large-scale literature-backed biomedical co-mention and context evidence
- external embedding-neighbor expansion from cui2vec and BioConceptVec
- open full-text article evidence where PMC OA coverage exists
- public-domain oncology, diabetes, kidney, digestive, infectious disease, and
  drug-safety reference language
- some guideline-style reasoning from open Bookshelf packages

The broader current source mix is weaker for:

- broad clinician-style differential diagnosis across all specialties
- up-to-date management recommendations outside the selected open packages
- physical exam maneuvers and practical diagnostic algorithms not present in
  government pages or selected Bookshelf titles
- explicit symptom-to-disease differential tables comparable to paid clinician
  tools
- fully actionable HPO/MONDO xref graph edges beyond the subset currently
  materialized through UMLS CUI mappings and text metadata

Search test:

Ultimately, we are trying to find what we are looking for. The purpose of the
UMLS - whether you call it interoperability, NLP, a crosswalk, or a thesaurus -
is to find the right concepts.

Find the right concepts. How do we test whether the UMLS can find the right
concepts? The best test is to search. If we focus on search instead of synonymy,
we will be closer to real use cases, because every use case involves search of
some kind or another: identifying the right identifier, string, or concept.

## Recommended Next Steps

1. Add explicit HPO/MONDO xref and hierarchy indexes so native xrefs such as
   SNOMEDCT_US, NCIT, MEDDRA, OMIM, Orphanet, and MONDO are first-class
   relationship/code-crosswalk edges rather than only corpus metadata/text; do
   not add a duplicate Orphanet fetch while UMLS carries the source-code
   coverage.
2. Expand Bookshelf OA with explicit accession IDs for high-value clinical
   guideline/report titles after checking each package license.
3. Rebuild the newer HPO/NCI/CDC/FDA/NIDDK/Bookshelf source subsets through
   profile-sharded linking so their views align with the original permitted
   source profiles.
4. Add ClinVar/ClinGen/CIViC/CPIC for variant interpretation and
   pharmacogenomic relationships.
5. Add WHO guideline/publication ingestion only after preserving per-publication
   license metadata.
6. Add a generated source-contribution command so this report can be refreshed
   from artifacts rather than maintained manually.
