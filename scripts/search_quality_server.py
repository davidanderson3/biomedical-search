#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qe_evidence_vectors.embeddings import DEFAULT_BIOMEDICAL_BERT_MODEL
from qe_evidence_vectors.elastic_client import search_knn
from qe_evidence_vectors.search_quality_http import (
    make_handler,
    parse_bounded_int_param,
    read_judgments,
    write_judgments,
)
from qe_evidence_vectors.search_ranking import (
    label_fallback_anchor_queries,
    rank_hits,
    related_anchor_candidate_matches_query,
)
from qe_evidence_vectors.search_label_scoring import should_suppress_label_fallback_hit
from qe_evidence_vectors.search_semantics import semantic_group_from_types
from qe_evidence_vectors.search_tokens import content_tokens
from qe_evidence_vectors.search_utils import source_mix_from_evidence_items
from qe_evidence_vectors.search_service import (
    LabelFallback,
    SearchIndex as _SearchIndex,
    SearchRecord,
    concept_display_name,
    parse_document_evidence,
)
from scaling_status import plan_status, resolve_path


class SearchIndex(_SearchIndex):
    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("search_knn_func", search_knn)
        super().__init__(*args, **kwargs)


__all__ = [
    "LabelFallback",
    "SearchIndex",
    "SearchRecord",
    "concept_display_name",
    "content_tokens",
    "label_fallback_anchor_queries",
    "parse_bounded_int_param",
    "parse_document_evidence",
    "rank_hits",
    "read_judgments",
    "related_anchor_candidate_matches_query",
    "semantic_group_from_types",
    "should_suppress_label_fallback_hit",
    "search_knn",
    "source_mix_from_evidence_items",
    "write_judgments",
]


DEFAULT_DOCS = (
    ROOT
    / "build"
    / "biomedicine_expanded_literature_mimic_structured_top12_concept_documents.jsonl"
)
DEFAULT_VECTORS = (
    ROOT
    / "build"
    / "biomedicine_expanded_literature_mimic_structured_top12_concept_vectors.lean.hashing.jsonl"
)
DEFAULT_EXTENSION_DOCS = (
    ROOT
    / "build"
    / "new_umls_iterations"
    / "iteration_002_existing_data"
    / "extension_concept_documents.cumulative.jsonl"
)
DEFAULT_EXTENSION_VECTORS = (
    ROOT
    / "build"
    / "new_umls_iterations"
    / "iteration_002_existing_data"
    / "extension_concept_vectors.cumulative.hashing.jsonl"
)
DEFAULT_WIKIPEDIA_DOCS = (
    ROOT / "build" / "wikipedia_enrichment" / "wikipedia_concept_documents.jsonl"
)
DEFAULT_WIKIPEDIA_VECTORS = (
    ROOT / "build" / "wikipedia_enrichment" / "wikipedia_concept_vectors.hashing.jsonl"
)
DEFAULT_DRUG_ENRICHMENT_DOCS = (
    ROOT / "build" / "drug_enrichment" / "drug_enrichment_concept_documents.jsonl"
)
DEFAULT_DRUG_ENRICHMENT_VECTORS = (
    ROOT / "build" / "drug_enrichment" / "drug_enrichment_concept_vectors.hashing.jsonl"
)
DEFAULT_OPEN_IMAGE_DOCS = (
    ROOT / "build" / "open_image_enrichment" / "open_image_concept_documents.jsonl"
)
DEFAULT_OPEN_IMAGE_VECTORS = (
    ROOT / "build" / "open_image_enrichment" / "open_image_concept_vectors.hashing.jsonl"
)
DEFAULT_OPENALEX_CITED_DOCS = (
    ROOT / "build" / "openalex_cited_evidence" / "openalex_top_cited_concept_documents.jsonl"
)
DEFAULT_OPENALEX_CITED_VECTORS = (
    ROOT / "build" / "openalex_cited_evidence" / "openalex_top_cited_concept_vectors.hashing.jsonl"
)
DEFAULT_HTML = ROOT / "docs" / "search_quality_server.html"
DEFAULT_PROGRESS_HTML = ROOT / "docs" / "scaling_progress.html"
DEFAULT_PROGRESS_PLAN = ROOT / "config" / "scaling_chunk_001_gap_topics.plan.json"
DEFAULT_FULL_PROGRESS_PLAN = ROOT / "config" / "full_pipeline.plan.json"
DEFAULT_RELATION_INDEX = ROOT / "build" / "umls_related_concepts.sqlite"
DEFAULT_RELATIONSHIP_EDGE_INDEX = ROOT / "build" / "relationship_edges.sqlite"
DEFAULT_RESEARCH_RELATION_INDEX = ROOT / "build" / "umls_research_relations.sqlite"
DEFAULT_EXTERNAL_CUI_VECTOR_INDEX = ROOT / "build" / "external_cui_vector_neighbors.sqlite"
DEFAULT_DEFINITION_INDEX = ROOT / "build" / "umls_definitions.sqlite"
DEFAULT_CODE_INDEX = ROOT / "build" / "cui_code_index.sqlite"
DEFAULT_SEMANTIC_TYPE_INDEX = ROOT / "build" / "umls_semantic_types.sqlite"
DEFAULT_LABEL_INDEX = ROOT / "build" / "umls_biomedicine_search_label_index.sqlite"
DEFAULT_ACTIVE_LABEL_SUPPLEMENT = ROOT / "config" / "active_label_supplement.tsv"
DEFAULT_ELASTIC_URL = "http://localhost:9200"
DEFAULT_ELASTIC_INDEX = "qe-umls-biomedicine-hashing-current"
DEFAULT_EVIDENCE_DIRS = (
    ROOT / "build" / "profile_evidence_literature_expanded",
    ROOT / "build" / "profile_evidence_mimic_demo_no_drg",
    ROOT / "build" / "profile_evidence_mimic_demo_structured",
    ROOT / "build" / "openalex_cited_evidence" / "evidence",
)
DEFAULT_VECTOR_PATHS = [
    path
    for path in (
        DEFAULT_VECTORS,
        DEFAULT_EXTENSION_VECTORS,
        DEFAULT_WIKIPEDIA_VECTORS,
        DEFAULT_DRUG_ENRICHMENT_VECTORS,
        DEFAULT_OPEN_IMAGE_VECTORS,
        DEFAULT_OPENALEX_CITED_VECTORS,
    )
    if path.exists()
]
DEFAULT_DOC_PATHS = [
    path
    for path in (
        DEFAULT_DOCS,
        DEFAULT_EXTENSION_DOCS,
        DEFAULT_WIKIPEDIA_DOCS,
        DEFAULT_DRUG_ENRICHMENT_DOCS,
        DEFAULT_OPEN_IMAGE_DOCS,
        DEFAULT_OPENALEX_CITED_DOCS,
    )
    if path.exists()
]
DEFAULT_LABEL_INDEXES = [
    path for path in (DEFAULT_LABEL_INDEX,) if path.exists()
]


def default_evidence_paths() -> list[Path]:
    paths: list[Path] = []
    for directory in DEFAULT_EVIDENCE_DIRS:
        if directory.exists():
            paths.extend(sorted(directory.glob("*.jsonl")))
    return paths


def quality_judgment_path(progress_plan_path: Path) -> Path:
    plan = json.loads(resolve_path(str(progress_plan_path)).read_text(encoding="utf-8"))
    for step in plan.get("steps", []):
        if step.get("id") != "quality_review":
            continue
        for artifact in step.get("artifacts", []):
            path = artifact.get("path")
            if path:
                return resolve_path(path)
    return ROOT / "build" / "scaling_runs" / "search_quality_judgments.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Serve a local search-quality UI backed by built vector artifacts."
    )
    parser.add_argument("--vectors", type=Path, nargs="+", default=DEFAULT_VECTOR_PATHS)
    parser.add_argument("--docs", type=Path, nargs="+", default=DEFAULT_DOC_PATHS)
    parser.add_argument(
        "--evidence",
        type=Path,
        nargs="*",
        default=None,
        help=(
            "Evidence JSONL files used to annotate evidence bullets with provenance. "
            "Defaults to the current literature and MIMIC evidence shard directories."
        ),
    )
    parser.add_argument(
        "--provenance-index",
        type=Path,
        help=(
            "SQLite provenance index built with evidence_vectors.py build-provenance-index. "
            "When supplied, evidence sources are looked up on demand instead of loaded from JSONL."
        ),
    )
    parser.add_argument("--html", type=Path, default=DEFAULT_HTML)
    parser.add_argument("--progress-html", type=Path, default=DEFAULT_PROGRESS_HTML)
    parser.add_argument("--progress-plan", type=Path, default=DEFAULT_PROGRESS_PLAN)
    parser.add_argument("--full-progress-plan", type=Path, default=DEFAULT_FULL_PROGRESS_PLAN)
    parser.add_argument(
        "--judgments-out",
        type=Path,
        help=(
            "CSV path for persisted UI judgments. Defaults to the quality_review "
            "artifact in --progress-plan."
        ),
    )
    parser.add_argument("--dim", type=int, default=384)
    parser.add_argument(
        "--provider",
        choices=["hashing", "sentence-transformers", "transformers-cls", "bert-cls", "sapbert"],
        default="hashing",
    )
    parser.add_argument(
        "--model",
        help=(
            "Embedding model for query vectors. For transformers-cls/sapbert, "
            f"defaults to {DEFAULT_BIOMEDICAL_BERT_MODEL}."
        ),
    )
    parser.add_argument("--local-files-only", action="store_true")
    parser.add_argument("--max-seq-length", type=int)
    parser.add_argument("--device", default="auto")
    parser.add_argument(
        "--elastic-url",
        default=DEFAULT_ELASTIC_URL,
        help="Use Elasticsearch kNN for /api/search. Pass an empty value to force local vector scan.",
    )
    parser.add_argument(
        "--elastic-index",
        default=DEFAULT_ELASTIC_INDEX,
        help="Elasticsearch index or alias name for /api/search.",
    )
    parser.add_argument("--elastic-num-candidates", type=int, default=100)
    parser.add_argument(
        "--label-index",
        type=Path,
        action="append",
        default=DEFAULT_LABEL_INDEXES,
        help="Optional SQLite UMLS label index used as an exact-label fallback.",
    )
    parser.add_argument("--label-max-tokens", type=int, default=8)
    parser.add_argument(
        "--active-label-supplement",
        type=Path,
        default=DEFAULT_ACTIVE_LABEL_SUPPLEMENT if DEFAULT_ACTIVE_LABEL_SUPPLEMENT.exists() else None,
        help=(
            "Optional TSV of curated existing-CUI labels that should be active even when "
            "the default semantic-profile label index excludes them."
        ),
    )
    parser.add_argument(
        "--code-index",
        type=Path,
        default=DEFAULT_CODE_INDEX if DEFAULT_CODE_INDEX.exists() else None,
        help=(
            "Optional SQLite CUI/code index built with evidence_vectors.py build-code-index. "
            "Defaults to build/cui_code_index.sqlite when that file exists."
        ),
    )
    parser.add_argument(
        "--semantic-type-index",
        type=Path,
        default=DEFAULT_SEMANTIC_TYPE_INDEX if DEFAULT_SEMANTIC_TYPE_INDEX.exists() else None,
        help=(
            "Optional SQLite MRSTY semantic type index built with "
            "evidence_vectors.py build-semantic-type-index. Defaults to "
            "build/umls_semantic_types.sqlite when that file exists."
        ),
    )
    parser.add_argument(
        "--relation-index",
        type=Path,
        default=DEFAULT_RELATION_INDEX if DEFAULT_RELATION_INDEX.exists() else None,
        help=(
            "Optional SQLite related-concepts index built with "
            "evidence_vectors.py build-relation-index. Defaults to "
            "build/umls_related_concepts.sqlite when that file exists."
        ),
    )
    parser.add_argument(
        "--research-relation-index",
        type=Path,
        default=DEFAULT_RESEARCH_RELATION_INDEX if DEFAULT_RESEARCH_RELATION_INDEX.exists() else None,
        help=(
            "Optional SQLite cross-semantic research relation index built with "
            "evidence_vectors.py build-research-relation-index. Defaults to "
            "build/umls_research_relations.sqlite when that file exists."
        ),
    )
    parser.add_argument(
        "--relationship-edge-index",
        type=Path,
        default=DEFAULT_RELATIONSHIP_EDGE_INDEX if DEFAULT_RELATIONSHIP_EDGE_INDEX.exists() else None,
        help=(
            "Optional SQLite universal relationship-edge index built with "
            "evidence_vectors.py build-relationship-edge-index. Defaults to "
            "build/relationship_edges.sqlite when that file exists."
        ),
    )
    parser.add_argument(
        "--external-cui-vector-index",
        type=Path,
        default=DEFAULT_EXTERNAL_CUI_VECTOR_INDEX if DEFAULT_EXTERNAL_CUI_VECTOR_INDEX.exists() else None,
        help=(
            "Optional SQLite BioConceptVec/cui2vec neighbor index built with "
            "evidence_vectors.py build-external-cui-vector-index. Defaults to "
            "build/external_cui_vector_neighbors.sqlite when that file exists."
        ),
    )
    parser.add_argument(
        "--definition-index",
        type=Path,
        default=DEFAULT_DEFINITION_INDEX if DEFAULT_DEFINITION_INDEX.exists() else None,
        help=(
            "Optional SQLite MRDEF definition index built with "
            "evidence_vectors.py build-definition-index. Defaults to "
            "build/umls_definitions.sqlite when that file exists."
        ),
    )
    parser.add_argument("--related-limit", type=int, default=8)
    parser.add_argument(
        "--related-source-limit",
        type=int,
        default=16,
        help=(
            "Maximum number of returned hits used as sources for related semantic views. "
            "Keeps related=1 from doing relation lookups for every returned result."
        ),
    )
    parser.add_argument(
        "--expensive-related-source-limit",
        type=int,
        default=0,
        help=(
            "Maximum number of returned hits used for expensive evidence-vector related "
            "neighbor scans. Defaults to 0 because the local backend brute-force scans "
            "vectors; MRREL/research/external relations still use --related-source-limit."
        ),
    )
    parser.add_argument(
        "--query-cache-size",
        type=int,
        default=128,
        help="Maximum repeated /api/search responses to cache in memory. Use 0 to disable.",
    )
    parser.add_argument(
        "--candidate-pool-multiplier",
        type=int,
        default=1,
        help=(
            "Number of vector candidates per requested result to hydrate before reranking. "
            "Lower values are faster; higher values give the reranker more recall."
        ),
    )
    parser.add_argument(
        "--candidate-pool-min",
        type=int,
        default=40,
        help="Minimum vector candidate pool size before reranking.",
    )
    parser.add_argument(
        "--rank-relationship-edges",
        action="store_true",
        help=(
            "Use mined universal relationship edges as ranking signals. By default they are loaded "
            "for related/semantic views but not used to rerank concept hits."
        ),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for path in args.vectors:
        if not path.exists():
            raise SystemExit(f"missing vector file: {path}")
    for path in args.docs:
        if not path.exists():
            raise SystemExit(f"missing concept document file: {path}")
    for path in args.label_index:
        if not path.exists():
            raise SystemExit(f"missing label index file: {path}")
    if args.code_index and not args.code_index.exists():
        raise SystemExit(f"missing code index file: {args.code_index}")
    if args.active_label_supplement and not args.active_label_supplement.exists():
        raise SystemExit(f"missing active label supplement file: {args.active_label_supplement}")
    if args.semantic_type_index and not args.semantic_type_index.exists():
        raise SystemExit(f"missing semantic type index file: {args.semantic_type_index}")
    if args.relation_index and not args.relation_index.exists():
        raise SystemExit(f"missing relation index file: {args.relation_index}")
    if args.research_relation_index and not args.research_relation_index.exists():
        raise SystemExit(f"missing research relation index file: {args.research_relation_index}")
    if args.relationship_edge_index and not args.relationship_edge_index.exists():
        raise SystemExit(f"missing relationship edge index file: {args.relationship_edge_index}")
    if args.external_cui_vector_index and not args.external_cui_vector_index.exists():
        raise SystemExit(f"missing external CUI vector index file: {args.external_cui_vector_index}")
    if args.definition_index and not args.definition_index.exists():
        raise SystemExit(f"missing definition index file: {args.definition_index}")
    if args.provenance_index and not args.provenance_index.exists():
        raise SystemExit(f"missing provenance index file: {args.provenance_index}")
    if not args.html.exists():
        raise SystemExit(f"missing HTML file: {args.html}")
    if not args.progress_html.exists():
        raise SystemExit(f"missing progress HTML file: {args.progress_html}")
    if not args.progress_plan.exists():
        raise SystemExit(f"missing progress plan file: {args.progress_plan}")
    if not args.full_progress_plan.exists():
        raise SystemExit(f"missing full progress plan file: {args.full_progress_plan}")
    judgments_path = args.judgments_out or quality_judgment_path(args.progress_plan)
    evidence_paths = list(args.evidence) if args.evidence is not None else default_evidence_paths()
    print("Loading search index...")
    index = SearchIndex(
        vector_paths=list(args.vectors),
        doc_paths=list(args.docs),
        evidence_paths=evidence_paths,
        provenance_index_path=args.provenance_index,
        provider=args.provider,
        model=args.model,
        dim=args.dim,
        local_files_only=args.local_files_only,
        max_seq_length=args.max_seq_length,
        device=args.device,
        elastic_url=args.elastic_url,
        elastic_index=args.elastic_index,
        elastic_num_candidates=args.elastic_num_candidates,
        label_index_paths=list(args.label_index),
        label_max_tokens=args.label_max_tokens,
        code_index_path=args.code_index,
        semantic_type_index_path=args.semantic_type_index,
        relation_index_path=args.relation_index,
        relationship_edge_index_path=args.relationship_edge_index,
        research_relation_index_path=args.research_relation_index,
        external_cui_vector_index_path=args.external_cui_vector_index,
        definition_index_path=args.definition_index,
        active_label_supplement_path=args.active_label_supplement,
        related_limit=args.related_limit,
        related_source_limit=args.related_source_limit,
        expensive_related_source_limit=args.expensive_related_source_limit,
        query_cache_size=args.query_cache_size,
        candidate_pool_multiplier=args.candidate_pool_multiplier,
        candidate_pool_min=args.candidate_pool_min,
        relationship_edges_rank=args.rank_relationship_edges,
    )
    print(
        f"Loaded {len(index.records):,} vectors from {len(index.vector_paths):,} files "
        f"and {index.docs_count:,} docs from {len(index.doc_paths):,} files "
        f"with {index.provenance_count:,} evidence source refs "
        f"and {index.status()['related_concept_links']:,} related-concept links "
        f"plus {index.status()['relationship_edge_links']:,} mined relationship edges "
        f"plus {index.status()['external_embedding_links']:,} external embedding links "
        f"and {index.status()['definition_rows']:,} MRDEF definitions "
        f"in {index.load_seconds:.1f}s"
    )
    server = ThreadingHTTPServer(
        (args.host, args.port),
        make_handler(
            index,
            args.html,
            args.progress_html,
            args.progress_plan,
            args.full_progress_plan,
            judgments_path,
            plan_status_func=plan_status,
            resolve_path_func=resolve_path,
        ),
    )
    print(f"Open http://{args.host}:{args.port}/")
    print(f"Progress dashboard http://{args.host}:{args.port}/progress")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
