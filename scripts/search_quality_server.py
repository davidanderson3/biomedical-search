#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qe_evidence_vectors.embeddings import DEFAULT_BIOMEDICAL_BERT_MODEL
from qe_evidence_vectors.elastic_client import search_knn
from qe_evidence_vectors.search_quality_http import (
    API_VERSION,
    OPENAPI_SPEC,
    api_error,
    make_handler,
    parse_bounded_int_param,
    read_judgments,
    delete_judgment,
    upsert_judgment,
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
    "API_VERSION",
    "LabelFallback",
    "OPENAPI_SPEC",
    "SearchIndex",
    "SearchRecord",
    "api_error",
    "concept_display_name",
    "content_tokens",
    "label_fallback_anchor_queries",
    "parse_bounded_int_param",
    "parse_document_evidence",
    "rank_hits",
    "read_judgments",
    "delete_judgment",
    "upsert_judgment",
    "related_anchor_candidate_matches_query",
    "semantic_group_from_types",
    "should_suppress_label_fallback_hit",
    "search_knn",
    "source_mix_from_evidence_items",
    "write_judgments",
]


DEFAULT_DOCS = ROOT / "build" / "public" / "public_concept_documents.jsonl"
DEFAULT_VECTORS = ROOT / "build" / "public" / "public_concept_vectors.hashing.jsonl"
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
DEFAULT_PERMITTED_SOURCE_DOCS = (
    ROOT / "build" / "public" / "permitted_sources_concept_documents.jsonl"
)
DEFAULT_PERMITTED_SOURCE_VECTORS = (
    ROOT / "build" / "public" / "permitted_sources_concept_vectors.hashing.jsonl"
)
DEFAULT_HTML = ROOT / "docs" / "search_quality_server.html"
DEFAULT_PRODUCT_HTML = ROOT / "web" / "search_quality_product.html"
DEFAULT_PROGRESS_HTML = ROOT / "docs" / "scaling_progress.html"
DEFAULT_SOURCE_DASHBOARD_HTML = ROOT / "docs" / "source_evidence_dashboard.html"
DEFAULT_PROGRESS_PLAN = ROOT / "config" / "scaling_chunk_001_gap_topics.plan.json"
DEFAULT_FULL_PROGRESS_PLAN = ROOT / "config" / "full_pipeline.plan.json"
DEFAULT_RELATION_INDEX = ROOT / "build" / "umls_related_concepts.sqlite"
DEFAULT_RELATIONSHIP_EDGE_INDEX = ROOT / "build" / "relationship_edges.sqlite"
DEFAULT_RESEARCH_RELATION_INDEX = ROOT / "build" / "umls_research_relations.sqlite"
DEFAULT_EXTERNAL_CUI_VECTOR_INDEX = ROOT / "build" / "external_cui_vector_neighbors.sqlite"
DEFAULT_DEFINITION_INDEX = ROOT / "build" / "umls_definitions.sqlite"
DEFAULT_CODE_INDEX = ROOT / "build" / "cui_code_index.runtime.sqlite"
DEFAULT_SEMANTIC_TYPE_INDEX = ROOT / "build" / "umls_semantic_types.sqlite"
DEFAULT_LABEL_INDEX = ROOT / "build" / "umls_biomedicine_search_label_index.sqlite"
DEFAULT_ACTIVE_LABEL_SUPPLEMENT = ROOT / "config" / "active_label_supplement.tsv"
DEFAULT_DISPLAY_NAME_OVERRIDES = ROOT / "config" / "display_name_overrides.tsv"
DEFAULT_ELASTIC_URL = "http://localhost:9200"
DEFAULT_ELASTIC_INDEX = "qe-umls-biomedicine-hashing-current"
DEFAULT_EVIDENCE_DIRS = (
    ROOT / "build" / "profile_evidence_literature_expanded",
    ROOT / "build" / "openalex_cited_evidence" / "evidence",
    ROOT / "build" / "public" / "permitted_source_profile_evidence",
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
        DEFAULT_PERMITTED_SOURCE_VECTORS,
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
        DEFAULT_PERMITTED_SOURCE_DOCS,
    )
    if path.exists()
]
DEFAULT_LABEL_INDEXES = [
    path for path in (DEFAULT_LABEL_INDEX,) if path.exists()
]
DEFAULT_UMLS_SEARCH_LABEL_INDEXES: list[Path] = []


def default_evidence_paths() -> list[Path]:
    paths: list[Path] = []
    for directory in DEFAULT_EVIDENCE_DIRS:
        if directory.exists():
            paths.extend(sorted(directory.glob("*.jsonl")))
    return paths


def resolve_evidence_paths(evidence_arg: list[Path] | None) -> list[Path]:
    """Resolve CLI evidence paths, treating a bare --evidence as the documented default."""
    if not evidence_arg:
        return default_evidence_paths()
    return list(evidence_arg)


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
            "Defaults to the current public literature and OpenAlex evidence shard directories."
        ),
    )
    parser.add_argument(
        "--provenance-index",
        type=Path,
        help=(
            "Packaged SQLite provenance index. "
            "When supplied, evidence sources are looked up on demand instead of loaded from JSONL."
        ),
    )
    parser.add_argument(
        "--html",
        type=Path,
        default=DEFAULT_HTML,
        help="Review workbench HTML served at /review.",
    )
    parser.add_argument(
        "--product-html",
        type=Path,
        default=DEFAULT_PRODUCT_HTML,
        help="Product search HTML served at /.",
    )
    parser.add_argument("--progress-html", type=Path, default=DEFAULT_PROGRESS_HTML)
    parser.add_argument("--source-dashboard-html", type=Path, default=DEFAULT_SOURCE_DASHBOARD_HTML)
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
        choices=["hashing", "hashing-idf", "sentence-transformers", "transformers-cls", "bert-cls", "sapbert"],
        default="hashing",
    )
    parser.add_argument(
        "--model",
        help=(
            "Embedding model for query vectors. For transformers-cls/sapbert, "
            f"defaults to {DEFAULT_BIOMEDICAL_BERT_MODEL}."
        ),
    )
    parser.add_argument("--idf-path", type=Path, help="Hashing IDF JSON for --provider hashing-idf.")
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
        "--require-elasticsearch",
        action="store_true",
        help=(
            "Fail startup and /api/search instead of falling back to local vector scan "
            "when Elasticsearch is missing or unavailable."
        ),
    )
    parser.add_argument(
        "--elastic-exclude-source-prefix",
        action="append",
        default=None,
        help=(
            "Exclude Elasticsearch hits whose sources start with this prefix before "
            "kNN candidate selection. Repeatable. Defaults to no source-prefix exclusions."
        ),
    )
    parser.add_argument(
        "--no-default-elastic-source-exclusions",
        action="store_true",
        help="Do not apply the default Elasticsearch source-prefix exclusions.",
    )
    parser.add_argument(
        "--label-index",
        type=Path,
        action="append",
        default=DEFAULT_LABEL_INDEXES,
        help="Optional SQLite UMLS label index used as an exact-label fallback.",
    )
    parser.add_argument(
        "--umls-search-label-index",
        type=Path,
        action="append",
        default=DEFAULT_UMLS_SEARCH_LABEL_INDEXES,
        help=(
            "Optional full MRCONSO-derived label index used only by the UMLS /search "
            "compatibility endpoint."
        ),
    )
    parser.add_argument("--label-max-tokens", type=int, default=8)
    parser.add_argument(
        "--label-fallback-limit",
        type=int,
        default=120,
        help="Maximum UMLS label fallback candidates hydrated per search. Use 0 for the old uncapped behavior.",
    )
    parser.add_argument(
        "--definition-fallback-limit",
        type=int,
        default=80,
        help="Maximum UMLS definition fallback candidates hydrated per search. Use 0 for the old uncapped behavior.",
    )
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
        "--display-name-overrides",
        type=Path,
        default=DEFAULT_DISPLAY_NAME_OVERRIDES if DEFAULT_DISPLAY_NAME_OVERRIDES.exists() else None,
        help=(
            "Optional TSV/CSV of CUI to display label overrides. This is a lightweight way "
            "to fix poor CUI preferred names without rebuilding UMLS indexes."
        ),
    )
    parser.add_argument(
        "--code-index",
        type=Path,
        default=DEFAULT_CODE_INDEX if DEFAULT_CODE_INDEX.exists() else None,
        help=(
            "Optional compact runtime SQLite CUI/code index. Defaults to "
            "build/cui_code_index.runtime.sqlite when that file exists."
        ),
    )
    parser.add_argument(
        "--semantic-type-index",
        type=Path,
        default=DEFAULT_SEMANTIC_TYPE_INDEX if DEFAULT_SEMANTIC_TYPE_INDEX.exists() else None,
        help=(
            "Optional SQLite MRSTY semantic type index. Defaults to "
            "build/umls_semantic_types.sqlite when that file exists."
        ),
    )
    parser.add_argument(
        "--relation-index",
        type=Path,
        default=DEFAULT_RELATION_INDEX if DEFAULT_RELATION_INDEX.exists() else None,
        help=(
            "Optional SQLite related-concepts index. Defaults to "
            "build/umls_related_concepts.sqlite when that file exists."
        ),
    )
    parser.add_argument(
        "--research-relation-index",
        type=Path,
        default=DEFAULT_RESEARCH_RELATION_INDEX if DEFAULT_RESEARCH_RELATION_INDEX.exists() else None,
        help=(
            "Optional SQLite cross-semantic research relation index. Defaults to "
            "build/umls_research_relations.sqlite when that file exists."
        ),
    )
    parser.add_argument(
        "--relationship-edge-index",
        type=Path,
        default=DEFAULT_RELATIONSHIP_EDGE_INDEX if DEFAULT_RELATIONSHIP_EDGE_INDEX.exists() else None,
        help=(
            "Optional SQLite universal relationship-edge index. Defaults to "
            "build/relationship_edges.sqlite when that file exists."
        ),
    )
    parser.add_argument(
        "--external-cui-vector-index",
        type=Path,
        help=(
            "Opt-in SQLite BioConceptVec/cui2vec neighbor index. These external "
            "embedding neighbors are association signals, not source evidence, and "
            "are not loaded by default."
        ),
    )
    parser.add_argument(
        "--definition-index",
        type=Path,
        default=DEFAULT_DEFINITION_INDEX if DEFAULT_DEFINITION_INDEX.exists() else None,
        help=(
            "Optional SQLite MRDEF definition index. Defaults to "
            "build/umls_definitions.sqlite when that file exists."
        ),
    )
    parser.add_argument("--related-limit", type=int, default=8)
    parser.add_argument(
        "--related-source-limit",
        type=int,
        default=8,
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
    parser.add_argument(
        "--public-output-only",
        action="store_true",
        help=(
            "Filter public API responses so source-vocabulary content is returned only from "
            "the configured public display source allowlist. Restricted content can still be "
            "used internally for retrieval and ranking."
        ),
    )
    parser.add_argument(
        "--public-output-source",
        action="append",
        default=None,
        help=(
            "Source abbreviation allowed in public display output. Repeatable. Defaults to "
            "the built-in conservative public display allowlist. Only used with "
            "--public-output-only unless an allowlist file is supplied."
        ),
    )
    parser.add_argument(
        "--public-output-source-allowlist",
        type=Path,
        help=(
            "Optional newline/comma/TSV source abbreviation allowlist for public display "
            "output. Only source-derived labels, definitions, and MRREL relations from "
            "these sources may be returned."
        ),
    )
    parser.add_argument(
        "--public-ui-only",
        action="store_true",
        help=(
            "Expose only the public search website and public API."
        ),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    return parser.parse_args()


def require_elasticsearch_available(base_url: str, index: str) -> None:
    if not base_url or not index:
        raise SystemExit("--require-elasticsearch requires --elastic-url and --elastic-index")
    quoted_index = urllib.parse.quote(index, safe=",*")
    url = f"{base_url.rstrip('/')}/{quoted_index}/_count"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            if response.status >= 400:
                raise SystemExit(f"Elasticsearch check failed: HTTP {response.status} from {url}")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Elasticsearch check failed: HTTP {exc.code} from {url}") from exc
    except (OSError, urllib.error.URLError) as exc:
        raise SystemExit(f"Elasticsearch check failed for {url}: {exc}") from exc


def install_progress(message: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[install {timestamp}] {message}", flush=True)


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
    if args.display_name_overrides and not args.display_name_overrides.exists():
        raise SystemExit(f"missing display name overrides file: {args.display_name_overrides}")
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
    if args.public_output_source_allowlist and not args.public_output_source_allowlist.exists():
        raise SystemExit(
            f"missing public output source allowlist file: {args.public_output_source_allowlist}"
        )
    if args.provider == "hashing-idf":
        if not args.idf_path:
            raise SystemExit("--provider hashing-idf requires --idf-path")
        if not args.idf_path.exists():
            raise SystemExit(f"missing hashing IDF file: {args.idf_path}")
    if not args.product_html.exists():
        raise SystemExit(f"missing product HTML file: {args.product_html}")
    if not args.public_ui_only:
        if not args.html.exists():
            raise SystemExit(f"missing HTML file: {args.html}")
        if not args.progress_html.exists():
            raise SystemExit(f"missing progress HTML file: {args.progress_html}")
        if not args.progress_plan.exists():
            raise SystemExit(f"missing progress plan file: {args.progress_plan}")
        if not args.full_progress_plan.exists():
            raise SystemExit(f"missing full progress plan file: {args.full_progress_plan}")
    if args.require_elasticsearch:
        require_elasticsearch_available(args.elastic_url, args.elastic_index)
    if args.public_ui_only:
        judgments_path = args.judgments_out or (ROOT / "build" / "public_search_judgments_disabled.csv")
    else:
        judgments_path = args.judgments_out or quality_judgment_path(args.progress_plan)
    evidence_paths = resolve_evidence_paths(args.evidence)
    elastic_exclude_source_prefixes = []
    elastic_exclude_source_prefixes.extend(args.elastic_exclude_source_prefix or [])
    if args.elastic_url and args.elastic_index:
        install_progress(
            "Loading result details for the website. "
            "Elasticsearch will do the fast searching; this app is loading the names, "
            "definitions, codes, and source links that appear in results."
        )
    else:
        install_progress(
            "Loading search files directly. "
            "This can take longer because the app searches the files directly instead of using Elasticsearch."
        )
    index = SearchIndex(
        vector_paths=list(args.vectors),
        doc_paths=list(args.docs),
        evidence_paths=evidence_paths,
        provenance_index_path=args.provenance_index,
        provider=args.provider,
        model=args.model,
        dim=args.dim,
        idf_path=args.idf_path,
        local_files_only=args.local_files_only,
        max_seq_length=args.max_seq_length,
        device=args.device,
        elastic_url=args.elastic_url,
        elastic_index=args.elastic_index,
        elastic_num_candidates=args.elastic_num_candidates,
        require_elasticsearch=args.require_elasticsearch,
        elastic_exclude_source_prefixes=elastic_exclude_source_prefixes,
        label_index_paths=list(args.label_index),
        umls_search_label_index_paths=list(args.umls_search_label_index),
        label_max_tokens=args.label_max_tokens,
        label_fallback_limit=args.label_fallback_limit,
        definition_fallback_limit=args.definition_fallback_limit,
        code_index_path=args.code_index,
        semantic_type_index_path=args.semantic_type_index,
        relation_index_path=args.relation_index,
        relationship_edge_index_path=args.relationship_edge_index,
        research_relation_index_path=args.research_relation_index,
        external_cui_vector_index_path=args.external_cui_vector_index,
        definition_index_path=args.definition_index,
        active_label_supplement_path=args.active_label_supplement,
        display_name_overrides_path=args.display_name_overrides,
        related_limit=args.related_limit,
        related_source_limit=args.related_source_limit,
        expensive_related_source_limit=args.expensive_related_source_limit,
        query_cache_size=args.query_cache_size,
        candidate_pool_multiplier=args.candidate_pool_multiplier,
        candidate_pool_min=args.candidate_pool_min,
        relationship_edges_rank=args.rank_relationship_edges,
        public_output_only=args.public_output_only,
        public_output_sources=args.public_output_source,
        public_output_source_allowlist_path=args.public_output_source_allowlist,
        progress=install_progress,
    )
    install_progress("Final check: counting loaded names, definitions, codes, and source details.")
    index_status = index.status()
    print(
        f"Finished loading search data: {len(index.records):,} searchable medical records "
        f"from {len(index.vector_paths):,} files, "
        f"{index.docs_count:,} result documents from {len(index.doc_paths):,} files, "
        f"{index.provenance_count:,} source links, "
        f"{index_status['related_concept_links']:,} related term links, "
        f"{index_status['relationship_edge_links']:,} relationship links, "
        f"{index_status['external_embedding_links']:,} external similarity links, "
        f"and {index_status['definition_rows']:,} definitions "
        f"in {index.load_seconds:.1f}s"
    )
    server = ThreadingHTTPServer(
        (args.host, args.port),
        make_handler(
            index,
            args.html,
            args.progress_html,
            args.source_dashboard_html if args.source_dashboard_html.exists() else None,
            args.progress_plan,
            args.full_progress_plan,
            judgments_path,
            product_html_path=args.product_html,
            plan_status_func=plan_status,
            resolve_path_func=resolve_path,
            expose_builder_tools=not args.public_ui_only,
        ),
    )
    print(f"Website ready: http://{args.host}:{args.port}/")
    if not args.public_ui_only:
        print(f"Review page: http://{args.host}:{args.port}/review")
        print(f"Progress page: http://{args.host}:{args.port}/progress")
        if args.source_dashboard_html.exists():
            print(f"Source details page: http://{args.host}:{args.port}/source-dashboard")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
