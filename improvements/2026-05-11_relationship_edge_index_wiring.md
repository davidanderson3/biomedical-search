# Relationship Edge Index Wiring

## Change

Wired mined universal relationship-edge JSONL into the default search path. The new `RelationshipEdgeIndex` builder converts mined JSONL rows, including OHDSI aggregate edges, into `build/relationship_edges.sqlite`. The search-quality server now auto-loads that SQLite index when present, exposes edge counts in status, merges outgoing and incoming mined edges into related semantic views, and lets mined edges contribute to relationship-based reranking. The full-pipeline progress plan now tracks `build/relationship_edges.sqlite` as a search-serving artifact.

## Improvement

Before this change, mined OHDSI/procedure relationship JSONL could be generated but did not appear in the interface unless converted into another document-derived relation path. After this change, aggregate edges such as `Drug -> likely_indication -> Condition` are queryable as relationship rows with preserved `strength`, `confidence`, evidence provenance, and structured context. This makes the universal edge model usable by the existing semantic-group UI, related-result evidence gates, and query reranker.

## Verification

Added tests for SQLite edge indexing and search integration. The focused tests confirm that a mined `metformin -> likely_indication -> type 2 diabetes mellitus` edge is indexed, can be looked up in both directions, appears in `research_relations_for_cui`, and contributes to server status counts.

## Remaining Limitations

The edge index only makes already-mined JSONL visible. It does not fetch new OHDSI artifacts, resolve unresolved OMOP concepts, or rebuild `build/relationship_edges.sqlite` automatically after mining. The rebuild remains an explicit pipeline step so source selection and licensing can stay reviewable.
