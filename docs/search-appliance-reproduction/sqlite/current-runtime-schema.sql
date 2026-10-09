-- Logical DDL for the current UMLS Search SQLite runtime stores.
--
-- The running appliance keeps these table groups in separate database files.
-- This combined file is documentation and can also create a consolidated test
-- database. It is not the recommended Elasticsearch-only serving design.

CREATE TABLE code_mappings (
    atom_id INTEGER PRIMARY KEY,
    cui TEXT NOT NULL,
    sab TEXT NOT NULL,
    code TEXT NOT NULL,
    aui TEXT NOT NULL DEFAULT '',
    scui TEXT NOT NULL,
    sdui TEXT NOT NULL,
    tty TEXT NOT NULL,
    label TEXT NOT NULL,
    ispref TEXT NOT NULL,
    suppress TEXT NOT NULL
);
CREATE INDEX idx_code_mappings_cui ON code_mappings(cui);
CREATE INDEX idx_code_mappings_sab_code ON code_mappings(sab, code COLLATE NOCASE);
CREATE INDEX idx_code_mappings_code ON code_mappings(code COLLATE NOCASE);
CREATE INDEX idx_code_mappings_aui ON code_mappings(aui COLLATE NOCASE);
CREATE INDEX idx_code_mappings_scui ON code_mappings(scui COLLATE NOCASE);
CREATE INDEX idx_code_mappings_sdui ON code_mappings(sdui COLLATE NOCASE);

CREATE TABLE preferred_terms (
    cui TEXT,
    label TEXT,
    sab TEXT,
    code TEXT,
    tty TEXT,
    suppress TEXT
);
CREATE INDEX idx_preferred_terms_cui ON preferred_terms(cui);

CREATE TABLE search_labels (
    norm TEXT NOT NULL,
    atom_id INTEGER NOT NULL
);
CREATE INDEX idx_search_labels_norm ON search_labels(norm);

CREATE TABLE legacy_identifier_mappings (
    cui TEXT,
    identifier_type TEXT,
    identifier TEXT,
    sab TEXT,
    code TEXT,
    aui TEXT,
    scui TEXT,
    sdui TEXT,
    tty TEXT,
    label TEXT,
    ispref TEXT,
    suppress TEXT,
    last_release TEXT
);
CREATE INDEX idx_legacy_identifier_mappings_identifier
    ON legacy_identifier_mappings(identifier_type, identifier COLLATE NOCASE);
CREATE INDEX idx_legacy_identifier_mappings_sab_identifier
    ON legacy_identifier_mappings(sab, identifier_type, identifier COLLATE NOCASE);
CREATE INDEX idx_legacy_identifier_mappings_cui
    ON legacy_identifier_mappings(cui);
CREATE INDEX idx_legacy_identifier_mappings_sab_code
    ON legacy_identifier_mappings(sab, code COLLATE NOCASE);

CREATE TABLE labels (
    norm TEXT NOT NULL,
    cui TEXT NOT NULL,
    label TEXT NOT NULL,
    sab TEXT NOT NULL,
    tty TEXT NOT NULL,
    ispref TEXT NOT NULL,
    suppress TEXT NOT NULL
);
CREATE INDEX idx_labels_norm ON labels(norm);
CREATE INDEX idx_labels_cui ON labels(cui);

CREATE TABLE semantic_types (
    cui TEXT NOT NULL,
    tui TEXT NOT NULL,
    stn TEXT NOT NULL,
    sty TEXT NOT NULL,
    atui TEXT NOT NULL,
    PRIMARY KEY (cui, tui, atui)
) WITHOUT ROWID;
CREATE INDEX idx_semantic_types_cui ON semantic_types(cui);

CREATE TABLE concept_definitions (
    cui TEXT NOT NULL,
    source TEXT NOT NULL,
    definition TEXT NOT NULL,
    rank INTEGER NOT NULL
);
CREATE INDEX idx_concept_definitions_cui_rank
    ON concept_definitions(cui, rank);
CREATE VIRTUAL TABLE concept_definition_fts
USING fts5(
    cui UNINDEXED,
    source UNINDEXED,
    definition_rank UNINDEXED,
    definition,
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TABLE related_concepts (
    source_cui TEXT NOT NULL,
    target_cui TEXT NOT NULL,
    relation TEXT NOT NULL,
    rela TEXT NOT NULL,
    sab TEXT NOT NULL,
    direction TEXT NOT NULL,
    label TEXT NOT NULL,
    rank INTEGER NOT NULL
);
CREATE INDEX idx_related_source_rank
    ON related_concepts(source_cui, rank);

CREATE TABLE research_relations (
    source_cui TEXT NOT NULL,
    target_cui TEXT NOT NULL,
    category TEXT NOT NULL,
    relation_group TEXT NOT NULL,
    relation TEXT NOT NULL,
    rela TEXT NOT NULL,
    sab TEXT NOT NULL,
    direction TEXT NOT NULL,
    label TEXT NOT NULL,
    source_semantic_type TEXT NOT NULL,
    target_semantic_type TEXT NOT NULL,
    rank INTEGER NOT NULL
);
CREATE INDEX idx_research_relations_source_category_rank
    ON research_relations(source_cui, category, rank);
CREATE INDEX idx_research_relations_source_rank
    ON research_relations(source_cui, rank);

CREATE TABLE relationship_edges (
    source_cui TEXT NOT NULL,
    target_cui TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    relation TEXT NOT NULL,
    rela TEXT NOT NULL,
    relation_group TEXT NOT NULL,
    source TEXT NOT NULL,
    source_class TEXT NOT NULL,
    direction TEXT NOT NULL,
    label TEXT NOT NULL,
    source_label TEXT NOT NULL,
    strength REAL NOT NULL,
    confidence REAL NOT NULL,
    edge_json TEXT NOT NULL,
    context_json TEXT NOT NULL,
    rank INTEGER NOT NULL
);
CREATE INDEX idx_relationship_edges_source_rank
    ON relationship_edges(source_cui, rank);
CREATE INDEX idx_relationship_edges_target_rank
    ON relationship_edges(target_cui, rank);

CREATE TABLE provenance (
    doc_id TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    citation_hash TEXT NOT NULL,
    rank INTEGER NOT NULL,
    citation_json TEXT NOT NULL,
    PRIMARY KEY (doc_id, text_hash, citation_hash)
) WITHOUT ROWID;

CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
