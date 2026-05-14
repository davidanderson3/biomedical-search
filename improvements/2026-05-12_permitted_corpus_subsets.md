# Permitted Corpus Subsets

Added bounded public corpus fetchers for ClinicalTrials.gov, MedlinePlus,
MedlinePlus Genetics, and DailyMed.

- ClinicalTrials.gov contributes trial-design language: conditions,
  interventions, eligibility criteria, outcomes, and study populations.
- MedlinePlus contributes patient-facing language, lay synonyms, topic groups,
  and consumer health descriptions.
- MedlinePlus Genetics contributes gene, genetic condition, chromosome,
  inheritance, synonym, and related-condition language. The fetcher accepts the
  public XML URL or a local downloaded XML file.
- DailyMed contributes public SPL drug-label language: indications,
  contraindications, warnings, adverse reactions, interactions, populations,
  and pharmacology. It supports bounded drug-name lookup, direct SPL set IDs,
  and set ID extraction from local UMLS `MRSAT.RRF`.

All sources emit the existing corpus JSONL shape, so they flow through the same
profile-shard UMLS linker, document builder, provenance index, and public
rebuild path. The public rebuild defaults to small subsets and exposes flags to
skip or expand them.

The default build uses multiword semantic-profile shards for corpus linking
rather than one broad untyped label index. The shared linker now rejects labels
with function words at the phrase edge and matches embedded inside larger
hyphenated terms, which avoids examples such as `A-DNA` from "a DNA" and
`beta-alanine` from `N-carbamyl-beta-alanine`.
