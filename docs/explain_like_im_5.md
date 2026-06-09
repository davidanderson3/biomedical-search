# Explain It Like I Am 5

Last updated: 2026-05-27

We are building a smarter way to search medical ideas.

## The Big Idea

UMLS is like a giant medical dictionary. It gives each medical idea a special
ID, called a CUI. That part is very useful, so we keep it.

Sometimes we may find a real medical idea that the dictionary does not have a
good card for yet. In that case, we can make a temporary local card with its own
`NEW#######` ID. That card is not an official UMLS ID. It says: this idea may
deserve its own place, here is the evidence, and here are the closest UMLS ideas
we know about.

But a dictionary is not always enough. People do not always search using the
exact dictionary name. Doctors, researchers, and patients use different words.
They use abbreviations. They describe things in context.

So this project adds a smart search layer on top of UMLS.

## What We Are Making

For each UMLS idea, we collect real examples of how people talk about it in
biomedical text. Then we turn those examples into a number pattern using a
biomedical AI model called SapBERT.

When someone searches, we turn their search into a number pattern too. Then we
look for UMLS ideas with similar patterns.

That means search can find ideas by meaning, not just by exact words.

## Where The Examples Come From

Right now we use:

- PubMed articles
- Europe PMC articles
- PubMed bulk-download test files

Credentialed clinical corpora are not part of the public release artifacts.

## Why We Are Not Just Adding Synonyms

Adding synonyms sounds simple, but it does not solve the main problem.

A good search engine can already handle many easy differences:

- capital letters
- plural words
- punctuation
- word order

The harder problem is meaning. For example, a search might describe a disease,
a lab test, a procedure, and a drug together. A synonym list is not very good at
understanding that. A biomedical vector search is better for that kind of
language.

## What Happens Step By Step

1. Start with UMLS concepts.
2. Collect biomedical text from real sources.
3. Find UMLS concepts mentioned in that text.
4. Build a short evidence page for each concept.
5. If UMLS is missing a useful idea, create a reviewed temporary local concept
   with evidence.
6. Turn each evidence page into a SapBERT vector.
7. Put those vectors into Elasticsearch.
8. Search with vectors.
9. Show evidence for each result.
10. Let a person mark results as relevant, partial, or wrong.
11. Use those judgments to decide whether the search is improving.
12. When a new UMLS release arrives, compare which concept cards changed.
13. Reuse old SapBERT vectors for concept cards whose searchable text did not
    change, and rebuild only the rest.

## What The Label Fallback Does

Sometimes a UMLS concept has a good official label but not enough evidence yet.
For example, `Appendectomy` should still be easy to find.

The label fallback checks UMLS names at search time. It helps exact missing
labels appear in results, but it is tuned so tiny pieces of a big query do not
take over the ranking.

## Where We Are Now

The current local system has:

- five topic-based evidence chunks
- one small PubMed bulk-download pilot
- eight larger two-file PubMed bulk pilots loaded and reviewed
- a first incremental UMLS update tool that fingerprints MRCONSO atoms by CUI
  and lists only the changed CUIs between two releases
- a vector reuse planner that separates unchanged concept documents from the
  smaller set that needs SapBERT embedding
- a new way to create local `NEW#######` concepts when UMLS is missing a
  useful idea
- SapBERT vectors loaded into Elasticsearch
- a smaller source lookup database for the testing page
- a small related-concepts database so a result can show nearby UMLS ideas
- a relationship-edge database path for mined public aggregate relationships
- compact vector files for the current SapBERT vectors
- a local search testing web page
- saved search-quality judgments
- a progress page

Current scale:

- 535,683 vector search documents in the cumulative Elasticsearch alias
- 533,540 vector records loaded in the latest assessment-server review run
- 516,028 concept document rows represented by tracked artifacts
- 1,531,116 source references that the testing page can show
- 483,677 related-concept links for the testing page
- 10,093,683 raw linked evidence rows behind the current server/provenance set

Last reviewed quality check:

- 8 test searches
- 40 judged results
- 8 of 8 searches have a fully relevant first result
- mean weighted P@5 is 0.750
- mean MRR is 1.0

All eight loaded PubMed bulk pilots have now passed the small quality check.
The latest reviewed 1321/1320 sample matches the previous 1323/1322 sample:
8 of 8 searches have a fully relevant first result, mean weighted P@5 is 0.750,
and mean MRR is 1.0. I also ran a harder 10-query mixed clinical smoke check:
all 10 searches had a relevant first result, but the lower ranks still had more
generic or denied-positive noise, so mean weighted P@5 was 0.570.

The testing page used to take about 134 seconds to start because it loaded
evidence references directly from many files. Now it uses a smaller lookup
database; restart it after new ingests so the page sees the latest files.

No temporary local concepts are in the search index yet. The tool for creating
them is ready, so the next time we find a real missing idea, we can add it with
evidence and test whether search gets better.

The testing page also shows related concepts now. If a result is a heart failure
idea, the page can show nearby ideas from the UMLS relationship file, such as
broader heart failure concepts or more specific subtypes.

It also has a researcher-focused relationship view. For a disease, it can show
linked drugs, genes or proteins, procedures or tests, and HPO phenotype features,
so reviewers can quickly inspect useful cross-type connections.

It can also load mined relationship edges from public aggregate artifacts. That
means a source like an OHDSI cohort definition can say, with evidence and a
numeric confidence score, that a drug is likely used for a condition. Those
relationships are kept separate from patient-level data and can show up in the
same related-result area when the relationship-edge database has been built.
The local build now also has a small curated seed edge set for common drug
indications, lab/observation context, and procedure-bundle attributes while the
larger public mining pipeline is expanded.

For procedure concepts, the builder can use SNOMED CT anchors by default while
still blocking CPT codes and CPT descriptors from public outputs.

The next step is to keep the same careful chunking for much more PubMed data.
The review results also say we should improve the benchmark and reduce
lower-rank noisy procedure, anatomy, follow-up, and broad disease matches.

## What Good Looks Like

The system is good when:

- it finds the right UMLS concept for real biomedical searches
- it can explain results with evidence
- it tracks where the evidence came from
- it improves when we add more real-world text
- it does not blindly add noisy data
- it can represent a truly missing medical idea without pretending it is an
  official UMLS CUI
- every release has search-quality checks

## What We Need To Keep Updating

Whenever the pipeline changes, update this file and the technical document.

Update:

- what data sources we are using
- what step we are on
- the current quality numbers
- what the next step is
- any important problems or limitations
