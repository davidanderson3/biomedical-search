from __future__ import annotations

import gzip
import json
import re
import sys
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from qe_evidence_vectors.documents import build_documents
from qe_evidence_vectors.drug_enrichment import (
    build_drug_enrichment_documents,
    is_ehr_like_source,
    load_drug_target_specs,
)
from qe_evidence_vectors.document_sqlite import build_documents_sqlite
from qe_evidence_vectors.compact_vectors import iter_compact_vectors, write_compact_vectors
from qe_evidence_vectors.code_index import CodeIndex, build_code_index, looks_like_code, parse_system_code
from qe_evidence_vectors.definition_index import DefinitionIndex, build_definition_index
from qe_evidence_vectors.elastic_client import build_knn_search_body, resolve_bulk_paths
from qe_evidence_vectors.elastic_export import elastic_mapping, write_elastic_bulk, write_elastic_bulk_sharded
from qe_evidence_vectors.embeddings import HashingEmbedder, embed_documents
from qe_evidence_vectors.extension_concepts import (
    build_extension_concept_artifacts,
    concept_from_payload,
    stable_extension_id,
)
from qe_evidence_vectors.corpus import merge_corpus_documents, read_tabular_corpus
from qe_evidence_vectors.evidence import filter_evidence_records
from qe_evidence_vectors.external_cui_vectors import (
    ExternalCuiVectorIndex,
    build_external_cui_vector_index,
    iter_external_cui_vectors,
)
from qe_evidence_vectors.compat import silence_urllib3_libressl_warning
from qe_evidence_vectors import fetchers
from qe_evidence_vectors.active_label_supplement import (
    validate_active_label_supplement_file,
    validate_active_label_supplement_rows,
)
from qe_evidence_vectors.fetchers import (
    PubMedTopic,
    add_ncbi_api_key,
    fetch_europepmc_topic_documents,
    fetch_pmc_oa_topic_documents,
    fetch_pubmed_topic_documents,
    pmc_oa_article_to_document,
    pmc_open_access_query,
    read_pubmed_topics,
    resolve_ncbi_api_key,
)
from qe_evidence_vectors.generic_filters import is_blocked_generic_concept
from qe_evidence_vectors.label_index import LabelIndex, build_label_index
from qe_evidence_vectors.linker import link_corpus_to_evidence
from qe_evidence_vectors.mimic_notes import iter_mimic_note_documents, write_mimic_note_corpora
from qe_evidence_vectors.mimic_structured import iter_mimic_structured_documents
from qe_evidence_vectors.open_image_enrichment import (
    ConceptImageTarget,
    build_open_image_documents,
    image_match_score,
    is_open_license,
)
from qe_evidence_vectors.ohdsi_mining import mine_public_ohdsi_artifacts
from qe_evidence_vectors.procedure_bundles import (
    build_procedure_bundle_artifacts,
    validate_private_cpt_adapter,
)
from qe_evidence_vectors.profile_workflow import (
    build_profile_indexes,
    link_profile_shards,
    profile_index_path,
    safe_profile_name,
)
from qe_evidence_vectors.search_denial import denial_scope_token_lists
from qe_evidence_vectors.search_ranking import direct_query_span
from qe_evidence_vectors.text import normalized_key
from qe_evidence_vectors.pubmed_bulk import (
    baseline_file_name,
    iter_pubmed_bulk_documents,
    parse_md5_payload,
    recent_baseline_files,
)
from qe_evidence_vectors.provenance_index import ProvenanceIndex, build_provenance_index
from qe_evidence_vectors.relation_index import RelationIndex, build_relation_index, display_label
from qe_evidence_vectors.relationship_edge_index import (
    RelationshipEdgeIndex,
    build_relationship_edge_index,
)
from qe_evidence_vectors.research_relations import ResearchRelationIndex, build_research_relation_index
from qe_evidence_vectors.schema import EvidenceRecord, iter_jsonl, write_jsonl
from qe_evidence_vectors.schema import ConceptDocument, CorpusDocument
from qe_evidence_vectors.search import search_vectors
from qe_evidence_vectors.semantic_type_index import SemanticTypeIndex, build_semantic_type_index
from qe_evidence_vectors.semantic_profiles import biomedicine_profile_names, resolve_profiles
from qe_evidence_vectors.search_semantic_buckets import (
    SEMANTIC_RESULT_BUCKETS,
    hit_matches_semantic_bucket,
    related_result_buckets_for_response,
    relation_visible_in_semantic_bucket,
    semantic_result_buckets_for_response,
)
from qe_evidence_vectors.trie_linker import LabelTrie, link_document_to_evidence_trie
from qe_evidence_vectors.universal_relationship import universal_relationship_edge
from qe_evidence_vectors.wikipedia_enrichment import build_wikipedia_documents
from scaling_status import chunk_number, plan_status
from scaling_status import artifact_status
import search_quality_server
import compare_umls_api
from search_quality_server import (
    API_VERSION,
    LabelFallback,
    OPENAPI_SPEC,
    SearchIndex,
    api_error,
    concept_display_name,
    content_tokens,
    label_fallback_anchor_queries,
    parse_bounded_int_param,
    rank_hits,
    read_judgments,
    related_anchor_candidate_matches_query,
    semantic_group_from_types,
    should_suppress_label_fallback_hit,
    source_mix_from_evidence_items,
    write_judgments,
)
from evaluate_search_api import QuerySpec, read_query_specs, summarize_search_response
from evaluate_paragraph_quality import (
    judge_quality as judge_paragraph_quality,
    read_acceptable_alternatives,
)
from audit_paragraph_precision import (
    audit_payloads as audit_paragraph_precision_payloads,
    read_useful_extra_cuis,
)


def test_libressl_urllib3_warning_is_suppressed_globally() -> None:
    with warnings.catch_warnings(record=True) as caught:
        silence_urllib3_libressl_warning()
        warnings.warn(
            "urllib3 v2 only supports OpenSSL 1.1.1+, currently the ssl module is compiled with LibreSSL",
            UserWarning,
        )
    assert not caught


def test_search_quality_api_exports_documented_contract() -> None:
    assert API_VERSION
    assert OPENAPI_SPEC["openapi"].startswith("3.")
    assert OPENAPI_SPEC["info"]["version"] == API_VERSION
    paths = OPENAPI_SPEC["paths"]
    for path in [
        "/api/health",
        "/api/status",
        "/api/search",
        "/api/resolve",
        "/api/detail",
        "/api/related",
        "/api/judgments",
        "/api/openapi.json",
    ]:
        assert path in paths

    search_params = {
        param["name"]
        for param in paths["/api/search"]["get"]["parameters"]
    }
    assert {"q", "k", "mode", "include_related", "semantic_bucket"} <= search_params
    assert api_error("missing_parameter", "missing q", status=400) == {
        "error": {
            "code": "missing_parameter",
            "message": "missing q",
            "status": 400,
        }
    }


def test_scaling_status_reports_weighted_effort_progress(tmp_path: Path) -> None:
    done = tmp_path / "done.marker"
    done.write_text("done\n", encoding="utf-8")
    plan = {
        "chunk_id": "test_pipeline",
        "steps": [
            {
                "id": "fetch_literature",
                "label": "Fetch PubMed and Europe PMC topic corpora",
                "artifacts": [{"path": str(done), "kind": "file"}],
            },
            {
                "id": "full_pubmed_bulk_ingest",
                "label": "Full PubMed baseline/update bulk ingest",
                "artifacts": [{"path": str(tmp_path / "missing.marker"), "kind": "file"}],
            },
        ],
    }
    status = plan_status(plan)
    assert status["progress_fraction"] == 0.5
    assert status["weighted_progress_fraction"] < status["progress_fraction"]
    assert status["completed_effort_weight"] == 3.0
    assert status["total_effort_weight"] == 43.0


def test_scaling_status_explains_human_progress_and_step_rationale(tmp_path: Path) -> None:
    done = tmp_path / "labels.sqlite"
    done.write_text("done\n", encoding="utf-8")
    plan = {
        "chunk_id": "test_pipeline",
        "steps": [
            {
                "id": "umls_profile_indexes",
                "label": "Build UMLS semantic profile and search label indexes",
                "artifacts": [{"path": str(done), "kind": "file"}],
            },
            {
                "id": "full_pubmed_bulk_ingest",
                "label": "Full PubMed baseline/update bulk ingest",
                "status_if_incomplete": "planned",
                "artifacts": [{"path": str(tmp_path / "missing.marker"), "kind": "file"}],
            },
        ],
    }
    status = plan_status(plan)

    assert "human_summary" in status
    assert status["human_summary"]["left"][0]["label"] == "Full PubMed baseline/update bulk ingest"
    assert "PubMed coverage" in status["human_summary"]["left"][0]["why"]
    assert status["steps"][0]["phase"] == "Foundation"
    assert status["steps"][0]["why"]
    assert any(phase["phase"] == "Evidence acquisition" for phase in status["phase_summary"])


def test_scaling_status_extracts_configured_chunk_number() -> None:
    assert chunk_number("scaling_chunk_005_diagnostics_procedures_devices") == "005"
    assert chunk_number("full_pipeline") is None


def test_search_quality_judgments_round_trip_csv(tmp_path: Path) -> None:
    path = tmp_path / "search_quality_judgments.csv"
    count = write_judgments(
        path,
        [
            {
                "query": "septic shock vasopressors",
                "doc_id": "C0036983:pubmed_clinical_context",
                "cui": "C0036983",
                "view": "pubmed_clinical_context",
                "score": 0.81,
                "grade": "relevant",
                "labels": ["Septic shock", "Shock, Septic"],
            }
        ],
    )
    rows = read_judgments(path)
    assert count == 1
    assert rows[0]["query"] == "septic shock vasopressors"
    assert rows[0]["labels"] == ["Septic shock", "Shock, Septic"]


def test_search_quality_judgments_reject_invalid_grades(tmp_path: Path) -> None:
    path = tmp_path / "search_quality_judgments.csv"
    count = write_judgments(
        path,
        [
            {
                "query": "sepsis vasopressors",
                "doc_id": "C0243026:umls_label",
                "cui": "C0243026",
                "view": "umls_label",
                "score": 1.1,
                "grade": "maybe",
                "labels": ["Sepsis"],
            },
            {
                "query": "sepsis vasopressors",
                "doc_id": "C0036983:pubmed_clinical_context",
                "cui": "C0036983",
                "view": "pubmed_clinical_context",
                "score": 0.9,
                "grade": "Relevant",
                "labels": ["Septic shock"],
            },
        ],
    )
    rows = read_judgments(path)

    assert count == 1
    assert len(rows) == 1
    assert rows[0]["grade"] == "relevant"
    assert rows[0]["doc_id"] == "C0036983:pubmed_clinical_context"


def test_quality_review_artifact_requires_real_judgment_rows(tmp_path: Path) -> None:
    path = tmp_path / "search_quality_judgments.csv"
    path.write_text("query,doc_id,cui,view,score,grade,labels\n", encoding="utf-8")
    empty_status = artifact_status({"path": str(path), "kind": "file"})

    path.write_text(
        "query,doc_id,cui,view,score,grade,labels\n"
        "sepsis vasopressors,C0243026:umls_label,C0243026,umls_label,1.1,relevant,Sepsis\n",
        encoding="utf-8",
    )
    reviewed_status = artifact_status({"path": str(path), "kind": "file"})

    assert empty_status.kind == "csv"
    assert empty_status.rows == 0
    assert not empty_status.complete
    assert reviewed_status.rows == 1
    assert reviewed_status.complete


def test_quality_review_artifact_requires_valid_judgment_grade(tmp_path: Path) -> None:
    path = tmp_path / "search_quality_judgments.csv"
    path.write_text(
        "query,doc_id,cui,view,score,grade,labels\n"
        "sepsis vasopressors,C0243026:umls_label,C0243026,umls_label,1.1,maybe,Sepsis\n",
        encoding="utf-8",
    )
    invalid_status = artifact_status({"path": str(path), "kind": "file"})

    path.write_text(
        "query,doc_id,cui,view,score,grade,labels\n"
        "sepsis vasopressors,C0243026:umls_label,C0243026,umls_label,1.1,partial,Sepsis\n",
        encoding="utf-8",
    )
    valid_status = artifact_status({"path": str(path), "kind": "file"})

    assert invalid_status.kind == "csv"
    assert invalid_status.rows == 0
    assert not invalid_status.complete
    assert valid_status.rows == 1
    assert valid_status.complete


def test_quality_review_step_requires_nonempty_judgment_csv(tmp_path: Path) -> None:
    path = tmp_path / "search_quality_judgments.csv"
    path.write_text("query,doc_id,cui,view,score,grade,labels\n", encoding="utf-8")
    plan = {
        "chunk_id": "test_quality_gate",
        "steps": [
            {
                "id": "quality_review",
                "label": "Review search quality before merge",
                "artifacts": [{"path": str(path), "kind": "file"}],
            }
        ],
    }

    status = plan_status(plan)

    assert status["completed_steps"] == 0
    assert status["steps"][0]["artifacts"][0]["kind"] == "csv"
    assert status["steps"][0]["status"] == "pending"


def test_search_quality_limit_parser_accepts_common_aliases_and_bounds() -> None:
    assert parse_bounded_int_param({"top_k": ["3"]}, "k", "top_k", "limit", default=10) == (3, None)
    assert parse_bounded_int_param({"limit": ["250"]}, "k", "top_k", "limit", default=10) == (100, None)
    assert parse_bounded_int_param({"k": ["0"]}, "k", "top_k", "limit", default=10) == (1, None)
    assert parse_bounded_int_param({}, "k", "top_k", "limit", default=10) == (10, None)


def test_search_quality_limit_parser_reports_invalid_values() -> None:
    value, error = parse_bounded_int_param({"k": ["many"]}, "k", "top_k", "limit", default=10)
    assert value is None
    assert error == "k must be an integer"


def test_umls_api_comparison_reads_tsv_query_specs(tmp_path: Path) -> None:
    queries = tmp_path / "queries.tsv"
    queries.write_text(
        "id\tquery\tsearch_type\tsabs\texpected_cuis\twhy\n"
        "chest_pain\tchest pain\twords\tSNOMEDCT_US\tC0008031|C2926613\tdenied symptom\n",
        encoding="utf-8",
    )

    specs = compare_umls_api.read_query_specs(queries)

    assert specs == [
        compare_umls_api.QuerySpec(
            query_id="chest_pain",
            query="chest pain",
            search_type="words",
            sabs="SNOMEDCT_US",
            expected_cuis=("C0008031", "C2926613"),
            why="denied symptom",
        )
    ]


def test_umls_api_comparison_filters_none_and_compares_cui_overlap() -> None:
    spec = compare_umls_api.QuerySpec(
        query_id="chest_pain",
        query="chest pain",
        expected_cuis=("C0008031",),
    )
    local_payload = {
        "hits": [
            {"cui": "C0008031", "name": "Chest Pain", "rank_score": 1.2},
            {"cui": "C0013404", "name": "Dyspnea", "rank_score": 0.8},
        ]
    }
    umls_payload = {
        "result": {
            "results": [
                {"ui": "NONE", "name": "NO RESULTS"},
                {"ui": "C0013404", "name": "Dyspnea", "rootSource": "MSH"},
                {"ui": "C0008031", "name": "Chest Pain", "rootSource": "SNOMEDCT_US"},
            ]
        }
    }

    row = compare_umls_api.compare_payloads(
        spec,
        local_payload,
        umls_payload,
        compare_top_n=2,
        show_hits=2,
    )

    assert row["local_top_cui"] == "C0008031"
    assert row["umls_top_cui"] == "C0013404"
    assert row["local_top_in_umls_rank"] == "2"
    assert row["umls_top_in_local_rank"] == "2"
    assert row["expected_local_rank"] == "1"
    assert row["expected_umls_rank"] == "2"
    assert row["overlap_at_n"] == "2/2"
    assert row["overlap_cuis"] == "C0008031|C0013404"


def test_label_fallback_finds_single_token_umls_label(tmp_path: Path) -> None:
    mrconso = tmp_path / "MRCONSO.RRF"
    mrsty = tmp_path / "MRSTY.RRF"
    mrconso.write_text(
        "C0003611|ENG|P|L1|PF|S1|Y|A1|||D001|MSH|MH|D001|Appendectomy|0|N||\n"
        "C0524832|ENG|P|L2|PF|S2|Y|A2|||D002|MSH|MH|D002|Thoracic Surgical Procedure|0|N||\n",
        encoding="utf-8",
    )
    mrsty.write_text(
        "C0003611|T061|A1.4.1.2.1|Therapeutic or Preventive Procedure|AT1|\n"
        "C0524832|T061|A1.4.1.2.1|Therapeutic or Preventive Procedure|AT1|\n",
        encoding="utf-8",
    )
    index_path = tmp_path / "search_labels.sqlite"
    build_label_index(
        mrconso_path=mrconso,
        mrsty_path=mrsty,
        semantic_profiles=["procedures-devices"],
        out_path=index_path,
        min_tokens=1,
        replace=True,
    )
    fallback = LabelFallback([index_path])
    hits = fallback.search("appendectomy surgical procedure", limit=5)
    assert hits[0]["cui"] == "C0003611"
    assert hits[0]["view"] == "umls_label"


def test_search_index_uses_loaded_extension_labels_as_fallback(tmp_path: Path) -> None:
    docs_path = tmp_path / "docs.jsonl"
    vectors_path = tmp_path / "vectors.jsonl"
    write_jsonl(
        docs_path,
        [
            {
                "doc_id": "C0000001:base",
                "cui": "C0000001",
                "view": "clinical_context",
                "text": "Generic electroencephalogram procedure evidence.",
                "evidence_count": 1,
                "sources": ["test"],
                "labels": ["Electroencephalography"],
            },
            {
                "doc_id": "NEW6052703:extension_concept",
                "cui": "NEW6052703",
                "view": "extension_concept",
                "text": "Preferred label: epileptiform discharges.",
                "evidence_count": 2,
                "sources": ["existing_concept_documents"],
                "labels": ["epileptiform discharges"],
            },
        ],
    )
    write_jsonl(
        vectors_path,
        [
            {
                "doc_id": "C0000001:base",
                "cui": "C0000001",
                "view": "clinical_context",
                "vector": [1.0, 0.0],
                "metadata": {
                    "labels": ["Electroencephalography"],
                    "sources": ["test"],
                    "evidence_count": 1,
                },
            },
            {
                "doc_id": "NEW6052703:extension_concept",
                "cui": "NEW6052703",
                "view": "extension_concept",
                "vector": [0.0, 1.0],
                "metadata": {
                    "labels": ["epileptiform discharges"],
                    "sources": ["existing_concept_documents"],
                    "evidence_count": 2,
                },
            },
        ],
    )

    index = SearchIndex(
        vector_paths=[vectors_path],
        doc_paths=[docs_path],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=2,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
    )

    label_hits = index.extension_label_fallback_hits("EEG captured epileptiform discharges", limit=5)
    result = index.search("EEG captured epileptiform discharges", top_k=1, include_related=False)

    assert label_hits[0]["cui"] == "NEW6052703"
    assert result["hits"][0]["cui"] == "NEW6052703"
    assert "extension_label" in result["hits"][0]["sources"]


def test_search_index_uses_loaded_extension_semantic_types(tmp_path: Path) -> None:
    docs_path = tmp_path / "docs.jsonl"
    vectors_path = tmp_path / "vectors.jsonl"
    write_jsonl(
        docs_path,
        [
            {
                "doc_id": "NEW6052703:extension_concept",
                "cui": "NEW6052703",
                "view": "extension_concept",
                "text": "Preferred label: epileptiform discharges.",
                "evidence_count": 2,
                "sources": ["existing_concept_documents"],
                "labels": ["epileptiform discharges"],
                "metadata": {
                    "concept_origin": "extension",
                    "semantic_type": "Finding",
                    "field": "result",
                },
            },
            {
                "doc_id": "NEW1692186:extension_concept",
                "cui": "NEW1692186",
                "view": "extension_concept",
                "text": "Preferred label: poorly controlled type 2 diabetes mellitus.",
                "evidence_count": 2,
                "sources": ["existing_concept_documents"],
                "labels": ["poorly controlled type 2 diabetes mellitus"],
                "metadata": {
                    "concept_origin": "extension",
                    "semantic_type": "Clinical Concept",
                    "field": "condition",
                },
            },
        ],
    )
    write_jsonl(
        vectors_path,
        [
            {
                "doc_id": "NEW6052703:extension_concept",
                "cui": "NEW6052703",
                "view": "extension_concept",
                "vector": [1.0, 0.0],
                "metadata": {"labels": ["epileptiform discharges"]},
            },
            {
                "doc_id": "NEW1692186:extension_concept",
                "cui": "NEW1692186",
                "view": "extension_concept",
                "vector": [0.0, 1.0],
                "metadata": {"labels": ["poorly controlled type 2 diabetes mellitus"]},
            },
        ],
    )

    index = SearchIndex(
        vector_paths=[vectors_path],
        doc_paths=[docs_path],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=2,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
    )
    finding_types = index.semantic_types_for_cui("NEW6052703")
    clinical_concept_types = index.semantic_types_for_cui("NEW1692186")
    finding_hit = index.hit_from_record(index.best_record_for_cui("NEW6052703"), score=1.0)
    clinical_concept_hit = index.hit_from_record(index.best_record_for_cui("NEW1692186"), score=1.0)

    assert finding_types[0]["name"] == "Finding"
    assert finding_types[0]["source"] == "local_extension"
    assert finding_hit["semantic_group"] == "DISO"
    assert clinical_concept_types[0]["name"] == "Disease or Syndrome"
    assert clinical_concept_types[0]["local_semantic_type"] == "Clinical Concept"
    assert clinical_concept_hit["semantic_group"] == "DISO"


def test_label_fallback_hydrates_semantic_group_and_skips_low_value_actions(tmp_path: Path) -> None:
    mrconso = tmp_path / "MRCONSO.RRF"
    mrsty = tmp_path / "MRSTY.RRF"
    mrconso.write_text(
        "C0007561|ENG|P|L1|PF|S1|Y|A1|||D001|MTH|PN|D001|ceftriaxone|0|N||\n"
        "C1272689|ENG|P|L2|PF|S2|Y|A2|||D002|MTH|PN|D002|Started|0|N||\n",
        encoding="utf-8",
    )
    mrsty.write_text(
        "C0007561|T121|A1.4.1.1.1|Pharmacologic Substance|AT1|\n",
        encoding="utf-8",
    )
    label_index = tmp_path / "labels.sqlite"
    semantic_type_index = tmp_path / "semantic_types.sqlite"
    build_label_index(mrconso_path=mrconso, out_path=label_index, replace=True)
    build_semantic_type_index(mrsty_path=mrsty, out_path=semantic_type_index, replace=True)

    index = SearchIndex(
        vector_paths=[],
        doc_paths=[],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        label_index_paths=[label_index],
        semantic_type_index_path=semantic_type_index,
    )
    result = index.search("ceftriaxone was started", top_k=5, include_related=False)

    assert result["hits"][0]["cui"] == "C0007561"
    assert result["hits"][0]["semantic_group"] == "CHEM"
    assert result["hits"][0]["score_breakdown"]["exact_span_component"] > 0
    assert "C1272689" not in {hit["cui"] for hit in result["hits"]}


def test_search_api_filters_results_by_custom_semantic_bucket(tmp_path: Path) -> None:
    mrconso = tmp_path / "MRCONSO.RRF"
    mrsty = tmp_path / "MRSTY.RRF"
    mrconso.write_text(
        "C0007561|ENG|P|L1|PF|S1|Y|A1|||D001|MTH|PN|D001|ceftriaxone|0|N||\n"
        "C0004626|ENG|P|L2|PF|S2|Y|A2|||D002|MTH|PN|D002|bacterial pneumonia|0|N||\n",
        encoding="utf-8",
    )
    mrsty.write_text(
        "C0007561|T121|A1.4.1.1.1|Pharmacologic Substance|AT1|\n"
        "C0004626|T047|B2.2.1.2.1|Disease or Syndrome|AT2|\n",
        encoding="utf-8",
    )
    label_index = tmp_path / "labels.sqlite"
    semantic_type_index = tmp_path / "semantic_types.sqlite"
    build_label_index(mrconso_path=mrconso, out_path=label_index, replace=True)
    build_semantic_type_index(mrsty_path=mrsty, out_path=semantic_type_index, replace=True)
    index = SearchIndex(
        vector_paths=[],
        doc_paths=[],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        label_index_paths=[label_index],
        semantic_type_index_path=semantic_type_index,
    )

    all_result = index.search("ceftriaxone for bacterial pneumonia", top_k=5, include_related=False)
    drug_result = index.search(
        "ceftriaxone for bacterial pneumonia",
        top_k=5,
        include_related=False,
        semantic_bucket_keys=["CHEM"],
    )
    disorder_result = index.search(
        "ceftriaxone for bacterial pneumonia",
        top_k=5,
        include_related=False,
        semantic_bucket_keys=["DISO_DISEASE"],
    )

    assert {"C0007561", "C0004626"} <= {hit["cui"] for hit in all_result["hits"]}
    assert [hit["cui"] for hit in drug_result["hits"]] == ["C0007561"]
    assert [group["key"] for group in drug_result["semantic_result_buckets"]] == ["CHEM"]
    assert drug_result["semantic_bucket_filter"] == ["CHEM"]
    assert [hit["cui"] for hit in disorder_result["hits"]] == ["C0004626"]
    assert [group["key"] for group in disorder_result["semantic_result_buckets"]] == ["DISO_DISEASE"]


def test_search_modes_filter_exact_hits_and_expand_comprehensive_pool(tmp_path: Path) -> None:
    index = SearchIndex(
        vector_paths=[],
        doc_paths=[],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        candidate_pool_min=40,
        candidate_pool_multiplier=1,
    )

    semantic_only = {
        "cui": "C0000001",
        "name": "Semantic-only vector neighbor",
        "match_type": "semantic_vector",
        "score_breakdown": {
            "vector_component": 0.12,
            "exact_span_component": 0.0,
        },
    }
    exact_label = {
        "cui": "C0000002",
        "name": "Blood culture",
        "match_type": "umls_label",
        "matched_query_span": "blood culture",
        "score_breakdown": {
            "exact_span_component": 0.20,
        },
    }

    assert index.filter_hits_by_search_mode(
        [semantic_only, exact_label],
        search_mode="exact",
    ) == [exact_label]
    assert index.filter_hits_by_search_mode(
        [semantic_only, exact_label],
        search_mode="comprehensive",
    ) == [semantic_only, exact_label]
    assert index.rerank_candidate_pool_size(20, search_mode="comprehensive") >= 120
    assert index.rerank_candidate_pool_size(20, search_mode="comprehensive") > index.rerank_candidate_pool_size(
        20,
        search_mode="balanced",
    )

    exact_result = index.search("anything", top_k=5, include_related=False, search_mode="exact")
    assert exact_result["search_mode"] == "exact"
    assert exact_result["scoring"]["search_mode"] == "exact"

    with pytest.raises(ValueError, match="search mode"):
        index.search("anything", top_k=5, include_related=False, search_mode="loose")


def test_search_api_rejects_unknown_semantic_bucket_filter(tmp_path: Path) -> None:
    index = SearchIndex(
        vector_paths=[],
        doc_paths=[],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
    )

    try:
        index.search("anything", top_k=5, include_related=False, semantic_bucket_keys=["NOT_A_BUCKET"])
    except ValueError as exc:
        assert "unknown semantic bucket filter" in str(exc)
    else:
        raise AssertionError("expected unknown semantic bucket filter to raise")


def test_label_fallback_allows_short_biomedical_acronyms(tmp_path: Path) -> None:
    mrconso = tmp_path / "MRCONSO.RRF"
    mrsty = tmp_path / "MRSTY.RRF"
    mrconso.write_text(
        "C0034802|ENG|P|L1|PF|S1|Y|A1|||D001|MTH|PN|D001|EGFR|0|N||\n"
        "C0525032|ENG|P|L2|PF|S2|Y|A2|||D002|MTH|PN|D002|INR|0|N||\n"
        "C9990001|ENG|P|L2|PF|S2|Y|A2|||D002|MTH|PN|D002|and|0|N||\n",
        encoding="utf-8",
    )
    mrsty.write_text(
        "C0034802|T116|A1.4.1.2.1.7|Amino Acid, Peptide, or Protein|AT1|\n"
        "C0525032|T033|A2.2|Finding|AT2|\n",
        encoding="utf-8",
    )
    label_index = tmp_path / "labels.sqlite"
    semantic_type_index = tmp_path / "semantic_types.sqlite"
    build_label_index(
        mrconso_path=mrconso,
        out_path=label_index,
        replace=True,
        min_tokens=1,
        min_chars=2,
    )
    build_semantic_type_index(mrsty_path=mrsty, out_path=semantic_type_index, replace=True)
    index = SearchIndex(
        vector_paths=[],
        doc_paths=[],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        label_index_paths=[label_index],
        semantic_type_index_path=semantic_type_index,
    )

    result = index.search("EGFR mutated lung cancer", top_k=5, include_related=False)

    assert result["hits"][0]["cui"] == "C0034802"
    assert result["hits"][0]["semantic_group"] == "GENE"

    assert ("inr", 1, 1) in list(LabelFallback([]).query_spans(["inr"]))


def test_active_label_supplement_recovers_profile_excluded_existing_cui(tmp_path: Path) -> None:
    mrsty = tmp_path / "MRSTY.RRF"
    mrsty.write_text(
        "C0877453|T042|B1.1.2|Organ or Tissue Function|AT1|\n",
        encoding="utf-8",
    )
    semantic_type_index = tmp_path / "semantic_types.sqlite"
    build_semantic_type_index(mrsty_path=mrsty, out_path=semantic_type_index, replace=True)
    supplement = tmp_path / "active_label_supplement.tsv"
    supplement.write_text(
        "cui\tlabel\tispref\tsab\ttty\tsemantic_type\tfield\twhy\n"
        "C0877453\tAcute cellular rejection\tY\tMTH\tPT\tFinding\tcondition\tprofile excluded\n",
        encoding="utf-8",
    )
    index = SearchIndex(
        vector_paths=[],
        doc_paths=[],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        semantic_type_index_path=semantic_type_index,
        active_label_supplement_path=supplement,
    )

    result = index.search("Kidney biopsy showed acute cellular rejection.", top_k=5, include_related=False)

    assert result["hits"][0]["cui"] == "C0877453"
    assert result["hits"][0]["semantic_group"] == "DISO"
    assert result["hits"][0]["semantic_types"][0]["source"] == "active_label_supplement"
    assert "active_label_supplement" in result["hits"][0]["sources"]


def test_active_label_supplement_allows_curated_short_single_token(tmp_path: Path) -> None:
    mrsty = tmp_path / "MRSTY.RRF"
    mrsty.write_text(
        "C0009421|T047|B2.2.1.2.1|Disease or Syndrome|AT1|\n",
        encoding="utf-8",
    )
    semantic_type_index = tmp_path / "semantic_types.sqlite"
    build_semantic_type_index(mrsty_path=mrsty, out_path=semantic_type_index, replace=True)
    supplement = tmp_path / "active_label_supplement.tsv"
    supplement.write_text(
        "cui\tlabel\tispref\tsab\ttty\tsemantic_type\tfield\twhy\n"
        "C0009421\tComa\tY\tMTH\tPT\tDisease or Syndrome\tcondition\tcurated short token\n",
        encoding="utf-8",
    )
    index = SearchIndex(
        vector_paths=[],
        doc_paths=[],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        semantic_type_index_path=semantic_type_index,
        active_label_supplement_path=supplement,
    )

    result = index.search("Coma after fentanyl overdose.", top_k=5, include_related=False)

    assert result["hits"][0]["cui"] == "C0009421"
    assert result["hits"][0]["matched_query_span"] == "coma"
    assert "active_label_supplement" in result["hits"][0]["sources"]


def test_active_label_supplement_context_gates_ambiguous_specialist_abbreviations(tmp_path: Path) -> None:
    supplement = tmp_path / "active_label_supplement.tsv"
    supplement.write_text(
        "cui\tlabel\tispref\tsab\ttty\tsemantic_type\tfield\twhy\tspecialty\tcontext_any\tblock_any\n"
        "C0003873\tRA\tN\tMTH\tAB\tDisease or Syndrome\tcondition\t"
        "rheumatology abbreviation\trheumatology\tarthritis|synovitis|methotrexate\t"
        "right atrium|right atrial|room air\n",
        encoding="utf-8",
    )
    index = SearchIndex(
        vector_paths=[],
        doc_paths=[],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        active_label_supplement_path=supplement,
    )

    rheum_result = index.search("RA flare with synovitis treated with methotrexate.", top_k=5, include_related=False)
    cardiac_result = index.search("RA pressure was estimated from the right atrium tracing.", top_k=5, include_related=False)

    assert rheum_result["hits"][0]["cui"] == "C0003873"
    assert rheum_result["hits"][0]["matched_query_span"] == "ra"
    assert "active_label_supplement" in rheum_result["hits"][0]["sources"]
    assert "C0003873" not in {hit["cui"] for hit in cardiac_result["hits"]}


def test_active_label_supplement_expanded_specialist_abbreviations_are_context_gated(tmp_path: Path) -> None:
    supplement = tmp_path / "active_label_supplement.tsv"
    supplement.write_text(
        "cui\tlabel\tispref\tsab\ttty\tsemantic_type\tfield\twhy\tspecialty\tcontext_any\tblock_any\n"
        "C1536220\tSTEMI\tN\tMTH\tAB\tDisease or Syndrome\tcondition\t"
        "cardiology abbreviation\tcardiology\tmyocardial infarction|st elevation|pci\t"
        "non st|non-st|nstemi\n"
        "C0024141\tSLE\tN\tMTH\tAB\tDisease or Syndrome\tcondition\t"
        "rheumatology abbreviation\trheumatology\tlupus|nephritis|proteinuria\t\n"
        "C0024485\tMRI\tN\tMTH\tAB\tDiagnostic Procedure\tprocedure\t"
        "radiology abbreviation\tradiology\tbrain|spine|infarct|osteomyelitis|imaging\t\n"
        "C0018932\tBRBPR\tN\tMTH\tAB\tFinding\tfinding\t"
        "gastroenterology abbreviation\tgastroenterology\trectal|bleeding|hematochezia\t\n",
        encoding="utf-8",
    )
    index = SearchIndex(
        vector_paths=[],
        doc_paths=[],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        active_label_supplement_path=supplement,
    )

    assert index.search(
        "STEMI with ST elevation myocardial infarction treated with PCI.",
        top_k=5,
        include_related=False,
    )["hits"][0]["cui"] == "C1536220"
    assert index.search(
        "SLE with lupus nephritis and proteinuria.",
        top_k=5,
        include_related=False,
    )["hits"][0]["cui"] == "C0024141"
    assert index.search(
        "Brain MRI showed acute infarct.",
        top_k=5,
        include_related=False,
    )["hits"][0]["cui"] == "C0024485"
    assert index.search(
        "BRBPR with rectal bleeding.",
        top_k=5,
        include_related=False,
    )["hits"][0]["cui"] == "C0018932"

    blocked_result = index.search(
        "STEMI was considered but non ST elevation myocardial infarction was diagnosed.",
        top_k=5,
        include_related=False,
    )
    assert "C1536220" not in {hit["cui"] for hit in blocked_result["hits"]}


def test_active_label_supplement_file_passes_sustainability_validation() -> None:
    issues = validate_active_label_supplement_file(ROOT / "config" / "active_label_supplement.tsv")
    assert issues == []


def test_active_label_supplement_validation_rejects_unsafe_nonpreferred_abbreviation() -> None:
    rows = [
        {
            "cui": "C0000001",
            "label": "ABC",
            "ispref": "N",
            "sab": "MTH",
            "tty": "AB",
            "semantic_type": "Disease or Syndrome",
            "field": "condition",
            "why": "A deliberately underspecified abbreviation for validation.",
            "specialty": "",
            "context_any": "",
            "block_any": "",
        }
    ]

    issues = validate_active_label_supplement_rows(rows)

    assert any("requires context_any" in issue for issue in issues)


def test_ranker_keeps_curated_memory_loss_anchor_visible() -> None:
    query = (
        "Neurology evaluated Alzheimer disease with progressive memory loss and dementia. "
        "The Mini-Mental State Examination score declined, and donepezil was started."
    )
    memory_loss = {
        "cui": "C0751295",
        "name": "Memory Loss",
        "labels": ["Memory Loss"],
        "score": 1.05,
        "match_type": "umls_label",
        "matched_query_span": "memory loss",
        "sources": ["active_label_supplement"],
        "evidence_count": 0,
        "semantic_types": [{"name": "Finding"}],
    }
    memory_observations = {
        "cui": "C0700327",
        "name": "Memory observations",
        "labels": ["Memory observations"],
        "score": 1.3,
        "match_type": "umls_label",
        "matched_query_span": "memory",
        "sources": ["umls_label"],
        "evidence_count": 1,
        "semantic_types": [{"name": "Finding"}],
    }
    response_declined = {
        "cui": "C1709925",
        "name": "Response Declined",
        "labels": ["Response Declined"],
        "score": 0.76,
        "match_type": "umls_label",
        "matched_query_span": "declined",
        "sources": ["umls_label"],
        "evidence_count": 0,
        "semantic_types": [{"name": "Finding"}],
    }
    dementia = {
        "cui": "C0497327",
        "name": "Dementia",
        "labels": ["Dementia"],
        "score": 1.0,
        "match_type": "umls_label",
        "matched_query_span": "dementia",
        "sources": ["umls_label"],
        "evidence_count": 7,
        "semantic_types": [{"name": "Mental or Behavioral Dysfunction"}],
    }

    ranked = rank_hits(
        query,
        [memory_observations, response_declined, dementia, memory_loss],
        top_k=4,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert ordered_cuis.index("C0751295") < ordered_cuis.index("C0700327")
    assert ordered_cuis.index("C0751295") < ordered_cuis.index("C1709925")
    memory_loss_hit = next(hit for hit in ranked if hit["cui"] == "C0751295")
    assert memory_loss_hit["score_breakdown"]["curated_exact_label_component"] > 0


def test_ranker_keeps_curated_explicit_single_token_symptom_and_drug_anchors_visible() -> None:
    query = (
        "Emergency department evaluation showed fever, dysuria, and flank pain. "
        "Urinalysis had nitrites and pyuria, urine culture grew Escherichia coli, "
        "and ceftriaxone was given for acute pyelonephritis."
    )
    dysuria = {
        "cui": "C0013428",
        "name": "Dysuria",
        "labels": ["Dysuria"],
        "score": 0.85,
        "match_type": "umls_label",
        "matched_query_span": "dysuria",
        "sources": ["active_label_supplement"],
        "evidence_count": 0,
        "semantic_types": [{"name": "Sign or Symptom"}],
    }
    evaluation = {
        "cui": "C0220825",
        "name": "Evaluation",
        "labels": ["Evaluation"],
        "score": 0.9,
        "match_type": "umls_label",
        "matched_query_span": "evaluation",
        "sources": ["umls_label"],
        "evidence_count": 1,
        "semantic_types": [{"name": "Health Care Activity"}],
    }
    fever = {
        "cui": "C0015967",
        "name": "Fever",
        "labels": ["Fever"],
        "score": 0.95,
        "match_type": "umls_label",
        "matched_query_span": "fever",
        "sources": ["umls_label"],
        "evidence_count": 10,
        "semantic_types": [{"name": "Sign or Symptom"}],
    }
    pyelonephritis = {
        "cui": "C0520575",
        "name": "Acute pyelonephritis",
        "labels": ["Acute pyelonephritis"],
        "score": 0.9,
        "match_type": "umls_label",
        "matched_query_span": "acute pyelonephritis",
        "sources": ["umls_label"],
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }

    ranked = rank_hits(query, [evaluation, fever, pyelonephritis, dysuria], top_k=4)
    ordered_cuis = [hit["cui"] for hit in ranked]
    assert ordered_cuis.index("C0013428") < ordered_cuis.index("C0220825")
    dysuria_hit = next(hit for hit in ranked if hit["cui"] == "C0013428")
    assert dysuria_hit["score_breakdown"]["curated_exact_label_component"] >= 0.30

    withdrawal_query = (
        "A hospitalized patient developed alcohol withdrawal syndrome with tremor, "
        "seizure, and hallucinations concerning for delirium tremens."
    )
    tremor = {
        "cui": "C0040822",
        "name": "Tremor",
        "labels": ["Tremor"],
        "score": 0.85,
        "match_type": "umls_label",
        "matched_query_span": "tremor",
        "sources": ["active_label_supplement"],
        "evidence_count": 0,
        "semantic_types": [{"name": "Sign or Symptom"}],
    }
    hallucinations = {
        "cui": "C0018524",
        "name": "Hallucinations",
        "labels": ["Hallucinations"],
        "score": 1.0,
        "match_type": "umls_label",
        "matched_query_span": "hallucinations",
        "sources": ["umls_label"],
        "evidence_count": 14,
        "semantic_types": [{"name": "Mental Process"}],
    }
    syndrome = {
        "cui": "C0236663",
        "name": "Alcohol withdrawal syndrome",
        "labels": ["Alcohol withdrawal syndrome"],
        "score": 0.95,
        "match_type": "umls_label",
        "matched_query_span": "alcohol withdrawal syndrome",
        "sources": ["umls_label"],
        "evidence_count": 10,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    withdrawal_ranked = rank_hits(withdrawal_query, [hallucinations, syndrome, tremor], top_k=3)
    assert "C0040822" in [hit["cui"] for hit in withdrawal_ranked]

    sepsis_query = "Septic shock required norepinephrine and lactate monitoring."
    norepinephrine = {
        "cui": "C0028351",
        "name": "norepinephrine",
        "labels": ["norepinephrine"],
        "score": 1.05,
        "match_type": "umls_label",
        "matched_query_span": "norepinephrine",
        "matched_sab": "MTH",
        "matched_tty": "PN",
        "sources": ["active_label_supplement"],
        "evidence_count": 0,
        "semantic_types": [{"name": "Pharmacologic Substance"}],
    }
    sepsis = {
        "cui": "C0036983",
        "name": "Septic Shock",
        "labels": ["Septic Shock"],
        "score": 0.82,
        "evidence_count": 40,
        "semantic_types": [{"name": "Disease or Syndrome"}],
        "evidence_items": [{"text": "Septic shock management includes lactate and norepinephrine."}],
    }
    lactate = {
        "cui": "C0202115",
        "name": "Lactic acid measurement",
        "labels": ["Lactate", "Lactic acid measurement"],
        "score": 1.34,
        "match_type": "umls_label",
        "matched_label": "Lactate",
        "matched_query_span": "lactate",
        "evidence_count": 26,
        "semantic_types": [{"name": "Laboratory Procedure"}],
    }
    sepsis_ranked = rank_hits(sepsis_query, [sepsis, lactate, norepinephrine], top_k=3)
    assert "C0028351" in [hit["cui"] for hit in sepsis_ranked]


def test_ranker_demotes_emergency_setting_concept_and_keeps_seizure_anchor_visible() -> None:
    pyelonephritis_query = (
        "Emergency department evaluation showed fever, dysuria, and flank pain. "
        "Urinalysis had nitrites and pyuria, urine culture grew Escherichia coli, "
        "and ceftriaxone was given for acute pyelonephritis."
    )
    dysuria = {
        "cui": "C0013428",
        "name": "Dysuria",
        "labels": ["Dysuria"],
        "score": 0.85,
        "match_type": "umls_label",
        "matched_query_span": "dysuria",
        "sources": ["active_label_supplement"],
        "evidence_count": 0,
        "semantic_types": [{"name": "Sign or Symptom"}],
    }
    emergency = {
        "cui": "C2745965",
        "name": "Emergencies [Disease/Finding]",
        "labels": ["Emergencies [Disease/Finding]"],
        "score": 1.34,
        "match_type": "umls_label",
        "matched_query_span": "emergency",
        "sources": ["umls_label"],
        "evidence_count": 0,
        "semantic_types": [{"name": "Finding"}],
    }

    ranked = rank_hits(pyelonephritis_query, [emergency, dysuria], top_k=2)
    emergency_hit = next(hit for hit in ranked if hit["cui"] == "C2745965")
    assert emergency_hit["score_breakdown"]["clinical_context_sense_penalty"] >= 0.42
    assert ranked[0]["cui"] == "C0013428"

    withdrawal_query = (
        "A hospitalized patient developed alcohol withdrawal syndrome with tremor, "
        "seizure, and hallucinations concerning for delirium tremens."
    )
    seizure = {
        "cui": "C0036572",
        "name": "Seizures",
        "labels": ["Seizure", "Seizures"],
        "score": 1.05,
        "match_type": "umls_label",
        "matched_query_span": "seizure",
        "sources": ["active_label_supplement"],
        "evidence_count": 0,
        "semantic_types": [{"name": "Sign or Symptom"}],
    }
    fluids = {
        "cui": "C0016286",
        "name": "Fluid Therapy",
        "labels": ["Fluid Therapy"],
        "score": 1.34,
        "match_type": "umls_label",
        "matched_query_span": "fluids",
        "sources": ["umls_label"],
        "evidence_count": 1,
        "semantic_types": [{"name": "Therapeutic or Preventive Procedure"}],
    }

    withdrawal_ranked = rank_hits(withdrawal_query, [fluids, seizure], top_k=2)
    assert withdrawal_ranked[0]["cui"] == "C0036572"


def test_ranker_keeps_specific_right_heart_catheterization_anchor_visible() -> None:
    query = (
        "Pulmonary hypertension caused progressive dyspnea with tricuspid regurgitation "
        "on echocardiography. Right heart catheterization confirmed elevated pressures, "
        "and sildenafil was started."
    )
    right_heart_catheterization = {
        "cui": "C0189896",
        "name": "Catheterization of right heart",
        "labels": ["right heart catheterization", "Catheterization of right heart"],
        "score": 1.34,
        "match_type": "umls_label",
        "matched_query_span": "right heart catheterization",
        "sources": ["active_label_supplement", "umls_label"],
        "evidence_count": 6,
        "semantic_types": [{"name": "Diagnostic Procedure"}],
    }
    generic_catheterization = {
        "cui": "C0018795",
        "name": "Cardiac Catheterization Procedures",
        "labels": ["Cardiac Catheterization Procedures"],
        "score": 1.34,
        "match_type": "umls_label",
        "matched_query_span": "heart catheterization",
        "sources": ["umls_label"],
        "evidence_count": 3,
        "semantic_types": [{"name": "Diagnostic Procedure"}],
    }

    ranked = rank_hits(
        query,
        [generic_catheterization, right_heart_catheterization],
        top_k=2,
    )

    assert ranked[0]["cui"] == "C0189896"
    specific_hit = next(hit for hit in ranked if hit["cui"] == "C0189896")
    assert specific_hit["score_breakdown"]["curated_exact_label_component"] > 0


def test_active_label_supplement_merges_with_existing_umls_label_hit(tmp_path: Path) -> None:
    mrconso = tmp_path / "MRCONSO.RRF"
    mrsty = tmp_path / "MRSTY.RRF"
    mrconso.write_text(
        "C0030794|ENG|P|L1|PF|S1|Y|A1|||D001|MTH|PN|D001|Pelvic Pain|0|N||\n",
        encoding="utf-8",
    )
    mrsty.write_text(
        "C0030794|T184|A2.2.2|Sign or Symptom|AT1|\n",
        encoding="utf-8",
    )
    supplement = tmp_path / "active_label_supplement.tsv"
    supplement.write_text(
        "cui\tlabel\tispref\tsab\ttty\tsemantic_type\tfield\twhy\n"
        "C0030794\tPelvic pain\tY\tMTH\tPT\tSign or Symptom\tfinding\texact clinical anchor\n",
        encoding="utf-8",
    )
    label_index = tmp_path / "labels.sqlite"
    semantic_type_index = tmp_path / "semantic_types.sqlite"
    build_label_index(mrconso_path=mrconso, out_path=label_index, replace=True, min_tokens=1, min_chars=2)
    build_semantic_type_index(mrsty_path=mrsty, out_path=semantic_type_index, replace=True)
    index = SearchIndex(
        vector_paths=[],
        doc_paths=[],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        label_index_paths=[label_index],
        semantic_type_index_path=semantic_type_index,
        active_label_supplement_path=supplement,
    )

    result = index.search(
        "Gynecology diagnosed pelvic inflammatory disease after pelvic pain and adnexal tenderness.",
        top_k=5,
        include_related=False,
    )

    hit = next(item for item in result["hits"] if item["cui"] == "C0030794")
    assert "active_label_supplement" in hit["sources"]
    assert hit["score_breakdown"]["curated_exact_label_component"] > 0


def test_ranker_keeps_curated_single_token_active_label_supplement() -> None:
    ranked = rank_hits(
        "Coma after fentanyl overdose with respiratory depression.",
        [
            {
                "cui": "C0579142",
                "name": "Opioid Overdose",
                "labels": ["Opioid Overdose"],
                "score": 0.82,
                "evidence_count": 20,
                "semantic_types": [{"name": "Injury or Poisoning"}],
            },
            {
                "cui": "C0015846",
                "name": "fentanyl",
                "labels": ["fentanyl"],
                "score": 0.82,
                "evidence_count": 10,
                "semantic_types": [{"name": "Pharmacologic Substance"}],
            },
            {
                "cui": "C0235063",
                "name": "Respiratory Depression",
                "labels": ["Respiratory Depression"],
                "score": 0.82,
                "evidence_count": 8,
                "semantic_types": [{"name": "Pathologic Function"}],
            },
            {
                "cui": "C0009421",
                "name": "Coma",
                "labels": ["Coma"],
                "score": 0.85,
                "match_type": "umls_label",
                "matched_label": "Coma",
                "matched_query_span": "coma",
                "sources": ["active_label_supplement"],
                "evidence_count": 0,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
        ],
        top_k=4,
    )

    coma = next(hit for hit in ranked if hit["cui"] == "C0009421")
    assert coma["score_breakdown"]["curated_exact_label_component"] > 0
    assert "C0009421" in [hit["cui"] for hit in ranked]


def test_ranker_prioritizes_curated_exact_label_when_anchor_diversity_fills_results() -> None:
    ranked = rank_hits(
        "Anaphylaxis with urticaria angioedema and wheezing after bee sting.",
        [
            {
                "cui": "C0002994",
                "name": "Angioedema",
                "labels": ["Angioedema"],
                "score": 0.92,
                "evidence_count": 20,
                "semantic_types": [{"name": "Pathologic Function"}],
            },
            {
                "cui": "C0002792",
                "name": "anaphylaxis",
                "labels": ["anaphylaxis"],
                "score": 0.92,
                "evidence_count": 20,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0413120",
                "name": "Bee sting",
                "labels": ["Bee sting"],
                "score": 0.92,
                "evidence_count": 20,
                "semantic_types": [{"name": "Injury or Poisoning"}],
            },
            {
                "cui": "C0043144",
                "name": "Wheezing",
                "labels": ["Wheezing"],
                "score": 0.92,
                "evidence_count": 20,
                "semantic_types": [{"name": "Sign or Symptom"}],
            },
            {
                "cui": "C0042109",
                "name": "Urticaria",
                "labels": ["Urticaria"],
                "score": 0.85,
                "match_type": "umls_label",
                "matched_label": "Urticaria",
                "matched_query_span": "urticaria",
                "sources": ["active_label_supplement"],
                "evidence_count": 0,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
        ],
        top_k=5,
    )

    urticaria = next(hit for hit in ranked if hit["cui"] == "C0042109")
    assert urticaria["score_breakdown"]["curated_exact_label_component"] > 0
    assert ranked.index(urticaria) < 4


def test_ranker_prefers_curated_multi_token_specific_label_over_generic_label() -> None:
    ranked = rank_hits(
        "Heavy alcohol use preceded acute pancreatitis with severe abdominal pain.",
        [
            {
                "cui": "C0030305",
                "name": "Pancreatitis",
                "labels": ["Pancreatitis"],
                "score": 1.34,
                "match_type": "umls_label",
                "matched_label": "Pancreatitis",
                "matched_query_span": "pancreatitis",
                "sources": ["umls_label"],
                "evidence_count": 2,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0001339",
                "name": "Pancreatitis, Acute",
                "labels": ["acute pancreatitis"],
                "score": 1.34,
                "match_type": "umls_label",
                "matched_label": "acute pancreatitis",
                "matched_query_span": "acute pancreatitis",
                "sources": ["active_label_supplement"],
                "evidence_count": 0,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
        ],
        top_k=2,
    )

    assert ranked[0]["cui"] == "C0001339"
    assert ranked[0]["score_breakdown"]["curated_exact_label_component"] == 0.22


def test_ranker_gives_curated_exact_credit_to_lab_procedure_anchor() -> None:
    ranked = rank_hits(
        "Diabetic ketoacidosis had high blood glucose, serum ketones, and metabolic acidosis.",
        [
            {
                "cui": "C0202110",
                "name": "Ketone bodies measurement, quantitative",
                "labels": ["Ketones", "Ketone bodies measurement, quantitative"],
                "score": 1.34,
                "match_type": "umls_label",
                "matched_label": "Ketones",
                "matched_query_span": "ketones",
                "sources": ["active_label_supplement", "pubmed", "umls_label"],
                "evidence_count": 2,
                "semantic_types": [{"name": "Laboratory Procedure"}],
                "semantic_group": "OBS",
            },
            {
                "cui": "C0205248",
                "name": "Granular",
                "labels": ["Granular"],
                "score": 1.34,
                "match_type": "umls_label",
                "matched_label": "Granular",
                "matched_query_span": "granular",
                "sources": ["umls_label"],
                "evidence_count": 0,
                "semantic_types": [{"name": "Qualitative Concept"}],
                "semantic_group": "OTHER",
            },
        ],
        top_k=2,
    )

    ketones = next(hit for hit in ranked if hit["cui"] == "C0202110")
    assert ketones["score_breakdown"]["exact_span_component"] > 0
    assert ketones["score_breakdown"]["curated_exact_label_component"] > 0


def test_ranker_gives_small_credit_to_two_token_local_extension_phrase() -> None:
    ranked = rank_hits(
        "Plaque psoriasis had silvery scale on extensor surfaces.",
        [
            {
                "cui": "NEW4386596",
                "name": "silvery scale",
                "labels": ["silvery scale"],
                "score": 0.9,
                "match_type": "umls_label",
                "matched_label": "silvery scale",
                "matched_query_span": "silvery scale",
                "sources": ["extension_label"],
                "evidence_count": 1,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
        ],
        top_k=1,
    )

    assert ranked[0]["score_breakdown"]["local_extension_phrase_component"] == 0.04


def test_ranker_prefers_exact_pharmacologic_ingredient_over_same_label_measurement() -> None:
    ranked = rank_hits(
        "Empiric ceftriaxone and vancomycin were administered for bacterial meningitis.",
        [
            {
                "cui": "C0489941",
                "name": "Vancomycin measurement",
                "labels": ["Vancomycin measurement", "Vancomycin"],
                "score": 1.34,
                "match_type": "umls_label",
                "matched_label": "Vancomycin",
                "matched_query_span": "vancomycin",
                "matched_sab": "CPT",
                "matched_tty": "PT",
                "evidence_count": 0,
                "semantic_types": [{"name": "Laboratory Procedure"}],
            },
            {
                "cui": "C0042313",
                "name": "vancomycin",
                "labels": ["vancomycin"],
                "score": 1.34,
                "match_type": "umls_label",
                "matched_label": "vancomycin",
                "matched_query_span": "vancomycin",
                "matched_sab": "RXNORM",
                "matched_tty": "IN",
                "evidence_count": 0,
                "semantic_types": [{"name": "Antibiotic"}],
            },
            {
                "cui": "C0085437",
                "name": "Meningitis, Bacterial",
                "labels": ["Bacterial meningitis"],
                "score": 1.0,
                "match_type": "umls_label",
                "matched_label": "bacterial meningitis",
                "matched_query_span": "bacterial meningitis",
                "evidence_count": 4,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
        ],
        top_k=3,
    )

    cuis = [hit["cui"] for hit in ranked]
    assert cuis.index("C0042313") < cuis.index("C0489941")
    drug = next(hit for hit in ranked if hit["cui"] == "C0042313")
    assert drug["score_breakdown"]["exact_pharmacologic_component"] > 0


def test_ranker_does_not_apply_drug_boost_to_endogenous_lab_analytes() -> None:
    ranked = rank_hits(
        "Rising creatinine levels were reviewed.",
        [
            {
                "cui": "C0010294",
                "name": "creatinine",
                "labels": ["creatinine"],
                "score": 1.34,
                "match_type": "umls_label",
                "matched_label": "creatinine",
                "matched_query_span": "creatinine",
                "matched_sab": "MTH",
                "matched_tty": "PN",
                "evidence_count": 0,
                "semantic_types": [{"name": "Biologically Active Substance"}],
            },
            {
                "cui": "C0201975",
                "name": "Creatinine measurement",
                "labels": ["Creatinine measurement", "Creatinine"],
                "score": 1.34,
                "match_type": "umls_label",
                "matched_label": "Creatinine",
                "matched_query_span": "creatinine",
                "matched_sab": "LNC",
                "matched_tty": "CN",
                "evidence_count": 4,
                "semantic_types": [{"name": "Laboratory Procedure"}],
            },
        ],
        top_k=2,
    )

    analyte = next(hit for hit in ranked if hit["cui"] == "C0010294")
    assert analyte["score_breakdown"]["exact_pharmacologic_component"] == 0
    assert ranked[0]["cui"] == "C0201975"


def test_ranker_keeps_exact_missed_dose_drug_when_lab_span_already_covered() -> None:
    ranked = rank_hits(
        "Tacrolimus trough levels decreased after missed doses.",
        [
            {
                "cui": "C5149388",
                "name": "Tacrolimus^trough",
                "labels": ["Tacrolimus trough"],
                "score": 1.1,
                "match_type": "umls_label",
                "matched_label": "Tacrolimus trough",
                "matched_query_span": "tacrolimus trough",
                "evidence_count": 2,
                "semantic_types": [{"name": "Laboratory or Test Result"}],
            },
            {
                "cui": "C0085149",
                "name": "tacrolimus",
                "labels": ["tacrolimus"],
                "score": 1.34,
                "match_type": "umls_label",
                "matched_label": "tacrolimus",
                "matched_query_span": "tacrolimus",
                "matched_sab": "RXNORM",
                "matched_tty": "IN",
                "evidence_count": 0,
                "semantic_types": [{"name": "Pharmacologic Substance"}],
            },
            {
                "cui": "C0442797",
                "name": "Decreasing",
                "labels": ["Decreased"],
                "score": 1.34,
                "match_type": "umls_label",
                "matched_label": "decreased",
                "matched_query_span": "decreased",
                "evidence_count": 0,
                "semantic_types": [{"name": "Finding"}],
            },
        ],
        top_k=3,
    )

    assert [hit["cui"] for hit in ranked[:2]] == ["C5149388", "C0085149"]


def test_code_index_builds_and_resolves_source_codes(tmp_path: Path) -> None:
    mrconso = tmp_path / "MRCONSO.RRF"
    mrconso.write_text(
        "C0004238|ENG|P|L1|PF|S1|Y|A1||SCUI1|SDUI1|ICD10CM|PT|I48.91|Unspecified atrial fibrillation|0|N||\n"
        "C0004238|ENG|P|L2|PF|S2|N|A2||SCUI2|SDUI2|MSH|MH|D001281|Atrial Fibrillation|0|N||\n",
        encoding="utf-8",
    )
    index_path = tmp_path / "cui_code_index.sqlite"
    count = build_code_index(mrconso_path=mrconso, out_path=index_path, replace=True)
    index = CodeIndex(index_path)
    code_rows = index.lookup_code("I48.91", sab="ICD10")
    cui_rows = index.lookup_cui("C0004238", sabs=["ICD10CM"])
    preferred_label = index.preferred_label("C0004238")
    index.close()

    assert count == 2
    assert parse_system_code("icd10:I48.91") == ("ICD10CM", "I48.91")
    assert looks_like_code("I48.91")
    assert code_rows[0]["cui"] == "C0004238"
    assert code_rows[0]["sab"] == "ICD10CM"
    assert cui_rows[0]["code"] == "I48.91"
    assert preferred_label == "Unspecified atrial fibrillation"


def test_code_index_dedupes_same_source_code_across_term_types(tmp_path: Path) -> None:
    mrconso = tmp_path / "MRCONSO.RRF"
    mrconso.write_text(
        "C0018801|ENG|P|L1|PF|S1|N|A1||703272007||SNOMEDCT_US|FN|703272007|Heart failure with reduced ejection fraction (disorder)|0|N||\n"
        "C0018801|ENG|P|L2|PF|S2|N|A2||703272007||SNOMEDCT_US|SY|703272007|HFrEF - heart failure with reduced ejection fraction|0|N||\n"
        "C0018801|ENG|P|L3|PF|S3|Y|A3||703272007||SNOMEDCT_US|PT|703272007|Heart failure with reduced ejection fraction|0|N||\n"
        "C0018801|ENG|P|L4|PF|S4|Y|A4||10078289||MDR|LLT|10078289|Heart failure with reduced ejection fraction|0|N||\n"
        "C0018801|ENG|P|L5|PF|S5|N|A5||10078289||MDR|PT|10078289|Heart failure with reduced ejection fraction|0|N||\n",
        encoding="utf-8",
    )
    index_path = tmp_path / "cui_code_index.sqlite"
    build_code_index(mrconso_path=mrconso, out_path=index_path, replace=True)
    index = CodeIndex(index_path)
    rows = index.lookup_cui("C0018801")
    preferred_label = index.preferred_label("C0018801")
    snomed = [row for row in rows if row["sab"] == "SNOMEDCT_US" and row["code"] == "703272007"]
    meddra = [row for row in rows if row["sab"] == "MDR" and row["code"] == "10078289"]
    index.close()

    assert len(snomed) == 1
    assert snomed[0]["tty"] == "PT"
    assert len(meddra) == 1
    assert meddra[0]["tty"] == "PT"
    assert preferred_label == "Heart failure with reduced ejection fraction"


def test_semantic_type_index_builds_and_resolves_cui_types(tmp_path: Path) -> None:
    mrsty = tmp_path / "MRSTY.RRF"
    mrsty.write_text(
        "C0004238|T047|B2.2.1.2.1|Disease or Syndrome|AT1|\n"
        "C0004238|T033|A1.2.3|Finding|AT2|\n",
        encoding="utf-8",
    )
    index_path = tmp_path / "semantic_types.sqlite"
    count = build_semantic_type_index(mrsty_path=mrsty, out_path=index_path, replace=True)
    index = SemanticTypeIndex(index_path)
    rows = index.lookup("C0004238")
    index.close()

    assert count == 2
    assert rows[0]["tui"] == "T033"
    assert rows[0]["name"] == "Finding"
    assert rows[1]["name"] == "Disease or Syndrome"


def test_concept_display_name_prefers_human_readable_label() -> None:
    assert (
        concept_display_name(
            [
                "Chest pain:Find:Pt:^Patient:Ord",
                "Chest pain",
                "Chest pain:Finding:To identify measures at a point in time:^Patient:Ordinal",
            ],
            fallback="C2926613",
        )
        == "Chest pain"
    )


def test_search_index_prefers_loinc_lc_for_clinical_attribute_names(tmp_path: Path) -> None:
    mrconso = tmp_path / "MRCONSO.RRF"
    mrsty = tmp_path / "MRSTY.RRF"
    mrconso.write_text(
        "C4050434|ENG|P|L1|PF|S1|N|A1|||80276-9|LNC|LC|80276-9|Heart sounds|0|N||\n"
        "C4050434|ENG|P|L2|PF|S2|N|A2|||80276-9|LNC|LN|80276-9|Heart sounds:Find:Pt:Heart:Nom|0|N||\n"
        "C4050434|ENG|P|L4|PF|S4|Y|A4|||80276-9|LNC|OSN|80276-9|Heart sounds|0|N||\n"
        "C4050434|ENG|P|L3|PF|S3|Y|A3||||MTH|PN|PN1|Heart sounds:Find:Pt:Heart:Nom|0|N||\n",
        encoding="utf-8",
    )
    mrsty.write_text(
        "C4050434|T201|A2.3.1|Clinical Attribute|AT1|\n",
        encoding="utf-8",
    )
    docs = build_documents(
        [
            EvidenceRecord(
                "e1",
                "C4050434",
                "heart sounds normal",
                "mimic",
                "clinical_attribute_context",
                2,
            )
        ]
    )
    docs_path = tmp_path / "docs.jsonl"
    vectors_path = tmp_path / "vectors.jsonl"
    code_path = tmp_path / "codes.sqlite"
    semantic_type_path = tmp_path / "semantic_types.sqlite"
    write_jsonl(docs_path, docs)
    write_jsonl(vectors_path, embed_documents(docs, HashingEmbedder(dim=16)))
    build_code_index(mrconso_path=mrconso, out_path=code_path, replace=True)
    build_semantic_type_index(mrsty_path=mrsty, out_path=semantic_type_path, replace=True)

    index = SearchIndex(
        vector_paths=[vectors_path],
        doc_paths=[docs_path],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        code_index_path=code_path,
        semantic_type_index_path=semantic_type_path,
    )
    hit = index.hit_from_record(index.best_record_for_cui("C4050434"), score=1.0)

    assert index.preferred_label_for_cui("C4050434") == "Heart sounds"
    assert hit["name"] == "Heart sounds"
    assert hit["labels"][0] == "Heart sounds"


def test_definition_index_builds_and_searches_mrdef(tmp_path: Path) -> None:
    docs = tmp_path / "docs.jsonl"
    write_jsonl(
        docs,
        [
            {"doc_id": "C0000001:literature", "cui": "C0000001", "labels": ["Sterility"]},
            {"doc_id": "C0000002:literature", "cui": "C0000002", "labels": ["Ignored"]},
        ],
    )
    mrdef = tmp_path / "MRDEF.RRF"
    mrdef.write_text(
        "\n".join(
            [
                "C0000001|A1|AT1|SAT1|MSH|Sterile condition with absence of infection or viable microorganisms.|N|",
                "C0000001|A2|AT2|SAT2|NCI|Duplicate lower priority definition.|N|",
                "C0000002|A3|AT3|SAT3|MSH|Suppressed definition should not be indexed.|Y|",
                "C0000003|A4|AT4|SAT4|MSH|Outside the document CUI set.|N|",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    index_path = tmp_path / "definitions.sqlite"

    stats = build_definition_index(
        mrdef_path=mrdef,
        out_path=index_path,
        doc_paths=[docs],
        max_definitions_per_cui=1,
        replace=True,
    )
    index = DefinitionIndex(index_path)
    definitions = index.lookup("C0000001")
    matches = index.search("absence of infection sterile", limit=5)
    index.close()

    assert stats["definitions_indexed"] == 1
    assert definitions[0]["source"] == "MSH"
    assert "absence of infection" in definitions[0]["definition"]
    assert matches[0]["cui"] == "C0000001"


def test_query_ranker_uses_bounded_definition_signal() -> None:
    ranked = rank_hits(
        "absence of infection sterile",
        [
            {
                "cui": "C0000001",
                "name": "Sterility",
                "labels": ["Sterility"],
                "score": 0.9,
                "match_type": "umls_definition",
                "evidence_count": 0,
                "definitions": [
                    {
                        "source": "MSH",
                        "definition": "Sterile condition with absence of infection or viable microorganisms.",
                    }
                ],
            },
            {
                "cui": "C0000002",
                "name": "Administrative procedure",
                "labels": ["Administrative procedure"],
                "score": 0.9,
                "evidence_count": 0,
            },
        ],
        top_k=2,
    )

    assert ranked[0]["cui"] == "C0000001"
    assert ranked[0]["score_breakdown"]["retrieval_kind"] == "umls_definition"
    assert ranked[0]["score_breakdown"]["definition_component"] > 0


def test_query_ranker_uses_mrrel_relation_signal() -> None:
    ranked = rank_hits(
        "diabetes retinal screening",
        [
            {
                "cui": "C0011849",
                "name": "Diabetes Mellitus",
                "labels": ["Diabetes Mellitus"],
                "score": 0.79,
                "evidence_count": 4,
                "semantic_types": [{"name": "Disease or Syndrome"}],
                "evidence_items": [],
                "mrrel_component": 0.14,
                "mrrel_matched_tokens": ["retinal", "screening"],
                "mrrel_signal_reasons": [
                    {
                        "cui": "C0099999",
                        "label": "Retinal Screening",
                        "category": "procedure_test",
                        "rank_source": "research_mrrel",
                    }
                ],
            },
            {
                "cui": "C9999998",
                "name": "Diabetes care",
                "labels": ["Diabetes care"],
                "score": 0.79,
                "evidence_count": 4,
                "semantic_types": [{"name": "Health Care Activity"}],
                "evidence_items": [],
            },
        ],
        top_k=2,
    )

    assert ranked[0]["cui"] == "C0011849"
    assert ranked[0]["score_breakdown"]["mrrel_component"] == 0.14
    assert ranked[0]["score_breakdown"]["mrrel_matched_tokens"] == ["retinal", "screening"]
    assert ranked[0]["score_breakdown"]["mrrel_signal_reasons"][0]["rank_source"] == "research_mrrel"


def test_query_ranker_drops_unanchored_low_signal_fillers() -> None:
    ranked = rank_hits(
        "migraine",
        [
            {
                "cui": "C0149931",
                "name": "Migraine Disorders",
                "labels": ["Migraine Disorders", "Migraine"],
                "score": 1.34,
                "match_type": "umls_label",
                "evidence_count": 8,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0154723",
                "name": "Migraine with Aura",
                "labels": ["Migraine with Aura"],
                "score": 0.62,
                "evidence_count": 5,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C1549530",
                "name": "Body site - Chest Tube",
                "labels": ["Body site - Chest Tube", "Chest Tube"],
                "score": 0.13,
                "evidence_count": 1,
                "semantic_types": [{"name": "Body Location or Region"}],
            },
        ],
        top_k=3,
    )

    assert [hit["cui"] for hit in ranked] == ["C0149931", "C0154723"]
    chest_tube = {
        "cui": "C1549530",
        "name": "Body site - Chest Tube",
        "labels": ["Body site - Chest Tube", "Chest Tube"],
        "score": 0.13,
        "evidence_count": 1,
        "semantic_types": [{"name": "Body Location or Region"}],
    }
    ranked_chest_tube = rank_hits("migraine", [chest_tube], top_k=1)
    assert ranked_chest_tube[0]["score_breakdown"]["lexical_fallback_used"]


def test_query_ranker_demotes_broad_qualifier_fragments() -> None:
    ranked = rank_hits(
        "The patient has worsening memory loss and difficulty managing medications.",
        [
            {
                "cui": "C0002622",
                "name": "Amnesia",
                "labels": ["Amnesia", "Memory loss"],
                "score": 1.10,
                "match_type": "umls_label",
                "matched_label": "Memory loss",
                "matched_query_span": "memory loss",
                "evidence_count": 0,
                "semantic_types": [{"name": "Mental or Behavioral Dysfunction"}],
            },
            {
                "cui": "C0332218",
                "name": "Difficult (qualifier value)",
                "labels": ["Difficult (qualifier value)", "Difficult", "difficulty with"],
                "score": 0.40,
                "evidence_count": 1,
                "semantic_types": [{"name": "Finding"}],
                "evidence_items": [
                    {
                        "text": "worsening memory loss and difficulty managing medications",
                    }
                ],
            },
            {
                "cui": "C0332271",
                "name": "Worsening (qualifier value)",
                "labels": ["Worsening (qualifier value)", "Worsening"],
                "score": 1.34,
                "match_type": "umls_label",
                "matched_label": "Worsening",
                "matched_query_span": "worsening",
                "evidence_count": 0,
                "semantic_types": [{"name": "Qualitative Concept"}],
            },
            {
                "cui": "C0013227",
                "name": "Pharmaceutical Preparations",
                "labels": ["Pharmaceutical Preparations", "medications", "DRUG"],
                "score": 1.19,
                "match_type": "umls_label",
                "matched_label": "medications",
                "matched_query_span": "medications",
                "evidence_count": 3,
                "semantic_types": [{"name": "Pharmacologic Substance"}],
            },
        ],
        top_k=4,
    )

    assert ranked[0]["cui"] == "C0002622"
    assert "C0332218" not in [hit["cui"] for hit in ranked]
    difficult = rank_hits(
        "The patient has worsening memory loss and difficulty managing medications.",
        [
            {
                "cui": "C0332218",
                "name": "Difficult (qualifier value)",
                "labels": ["Difficult (qualifier value)", "Difficult", "difficulty with"],
                "score": 0.40,
                "evidence_count": 1,
                "semantic_types": [{"name": "Finding"}],
                "evidence_items": [
                    {
                        "text": "worsening memory loss and difficulty managing medications",
                    }
                ],
            }
        ],
        top_k=1,
    )[0]
    worsening = next(hit for hit in ranked if hit["cui"] == "C0332271")
    assert difficult["score_breakdown"]["lexical_fallback_used"]
    assert difficult["score_breakdown"]["generic_penalty"] > 0
    assert difficult["score_breakdown"]["evidence_context_component"] == 0.0
    assert worsening["score_breakdown"]["generic_penalty"] > 0
    pharmaceutical = next(hit for hit in ranked if hit["cui"] == "C0013227")
    assert pharmaceutical["score_breakdown"]["generic_penalty"] > 0
    assert pharmaceutical["score_breakdown"]["lexical_fallback_used"]


def test_query_ranker_respects_drug_answer_type_with_definitions() -> None:
    ranked = rank_hits(
        "drug used to prevent blood clots",
        [
            {
                "cui": "C0302148",
                "name": "Blood Clot",
                "labels": ["Blood Clot"],
                "score": 1.14,
                "match_type": "umls_label",
                "evidence_count": 12,
                "semantic_types": [{"name": "Pathologic Function"}],
                "definitions": [
                    {
                        "source": "NCI",
                        "definition": "A blood clot can prevent normal blood flow.",
                    }
                ],
            },
            {
                "cui": "C0003280",
                "name": "Anticoagulants",
                "labels": ["Anticoagulants"],
                "score": 0.76,
                "evidence_count": 12,
                "semantic_types": [{"name": "Pharmacologic Substance"}],
                "definitions": [
                    {
                        "source": "MSH",
                        "definition": "Agents that prevent blood clotting.",
                    }
                ],
            },
        ],
        top_k=2,
    )

    assert ranked[0]["cui"] == "C0003280"
    assert ranked[0]["score_breakdown"]["semantic_component"] > 0
    assert ranked[1]["score_breakdown"]["role_mismatch_penalty"] > 0


def test_query_ranker_promotes_specific_noncontiguous_label_match() -> None:
    ranked = rank_hits(
        "Patient reports intermittent chest pain worsening with exertion over past week",
        [
            {
                "cui": "C2926613",
                "name": "Chest pain",
                "labels": ["Chest pain"],
                "score": 1.1,
                "match_type": "umls_label",
                "evidence_count": 323,
            },
            {
                "cui": "C0232288",
                "name": "Chest pain on exertion",
                "labels": ["Chest pain on exertion", "Exertional chest pain"],
                "score": 0.82597,
                "evidence_count": 2,
            },
        ],
        top_k=2,
    )

    assert ranked[0]["cui"] == "C0232288"
    assert ranked[0]["score_breakdown"]["retrieval_kind"] == "semantic_vector"
    assert ranked[0]["score_breakdown"]["lexical_component"] > 0


def test_query_ranker_demotes_generic_zero_evidence_charting_phrase() -> None:
    ranked = rank_hits(
        "Patient advised to maintain hydration rest and return if symptoms worsen",
        [
            {
                "cui": "C0418832",
                "name": "Patient advised to",
                "labels": ["Patient advised to"],
                "score": 1.165455,
                "match_type": "umls_label",
                "evidence_count": 0,
            },
            {
                "cui": "C1321013",
                "name": "Hydration",
                "labels": ["Hydration"],
                "score": 0.758636,
                "match_type": "umls_label",
                "evidence_count": 4,
            },
        ],
        top_k=2,
    )

    assert ranked[0]["cui"] == "C1321013"


def test_query_ranker_prefers_exact_primary_name_over_broad_synonym_tie() -> None:
    ranked = rank_hits(
        "Imaging studies suggest possible infection requiring further diagnostic evaluation and follow up",
        [
            {
                "cui": "C0009450",
                "name": "Communicable Diseases",
                "labels": ["Communicable Diseases", "Infection"],
                "score": 0.76375,
                "evidence_count": 1908,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C3714514",
                "name": "Infection",
                "labels": ["Infection"],
                "score": 0.76375,
                "evidence_count": 15,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
        ],
        top_k=2,
    )

    assert ranked[0]["cui"] == "C3714514"
    assert ranked[0]["score_breakdown"]["primary_name_component"] > 0


def test_query_ranker_favors_exact_primary_name_over_exact_broad_synonym() -> None:
    ranked = rank_hits(
        "heart failure",
        [
            {
                "cui": "C0018801",
                "name": "Heart failure",
                "labels": ["Heart failure"],
                "score": 0.72,
                "match_type": "umls_label",
                "evidence_count": 0,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C9999999",
                "name": "Heart failure disease family",
                "labels": ["Heart failure disease family", "Heart failure"],
                "score": 0.95,
                "evidence_count": 1000,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
        ],
        top_k=2,
    )

    assert ranked[0]["cui"] == "C0018801"
    assert ranked[0]["score_breakdown"]["exact_label_component"] > 0
    assert ranked[0]["score_breakdown"]["exact_primary_name_component"] > 0
    assert ranked[1]["score_breakdown"]["exact_label_component"] > 0
    assert ranked[1]["score_breakdown"]["exact_primary_name_component"] == 0.0


def test_query_ranker_does_not_boost_generic_exact_labels() -> None:
    ranked = rank_hits(
        "diagnostic evaluation",
        [
            {
                "cui": "C0000001",
                "name": "Diagnostic evaluation",
                "labels": ["Diagnostic evaluation"],
                "score": 1.2,
                "match_type": "umls_label",
                "evidence_count": 0,
            }
        ],
        top_k=1,
    )

    assert ranked[0]["score_breakdown"]["exact_label_component"] == 0.0
    assert ranked[0]["score_breakdown"]["exact_primary_name_component"] == 0.0
    assert ranked[0]["score_breakdown"]["generic_penalty"] > 0


def test_query_ranker_penalizes_missing_numeric_specificity() -> None:
    ranked = rank_hits(
        "poorly controlled type 2 diabetes hba1c",
        [
            {
                "cui": "C1320657",
                "name": "Diabetes type",
                "labels": ["Diabetes type", "type diabetes"],
                "score": 0.82,
                "evidence_count": 1,
                "semantic_types": [{"name": "Finding"}],
            },
            {
                "cui": "C0011860",
                "name": "Diabetes Mellitus, Type 2",
                "labels": ["Diabetes Mellitus, Type 2", "Type 2 Diabetes Mellitus"],
                "score": 0.72,
                "evidence_count": 1,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0011849",
                "name": "Diabetes Mellitus",
                "labels": ["Diabetes Mellitus"],
                "score": 0.95,
                "evidence_count": 120,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
        ],
        top_k=3,
    )

    assert ranked[0]["cui"] == "C0011860"
    generic = next(hit for hit in ranked if hit["cui"] == "C1320657")
    broad = next(hit for hit in ranked if hit["cui"] == "C0011849")
    specific = next(hit for hit in ranked if hit["cui"] == "C0011860")
    assert generic["score_breakdown"]["numeric_specificity_penalty"] > 0
    assert broad["score_breakdown"]["numeric_specificity_penalty"] > 0
    assert specific["score_breakdown"]["numeric_specificity_penalty"] == 0.0


def test_query_ranker_does_not_promote_modifier_only_numeric_match() -> None:
    ranked = rank_hits(
        "poorly controlled type 2 diabetes hba1c",
        [
            {
                "cui": "C4014362",
                "name": "Type 2 diabetes mellitus (T2D)",
                "labels": ["Type 2 diabetes mellitus (T2D)"],
                "score": 0.72,
                "evidence_count": 1,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0011849",
                "name": "Diabetes Mellitus",
                "labels": ["Diabetes Mellitus"],
                "score": 0.95,
                "evidence_count": 120,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0745117",
                "name": "Controlled hypertension",
                "labels": ["Controlled hypertension"],
                "score": 0.90,
                "evidence_count": 50,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0019018",
                "name": "Glycosylated hemoglobin A",
                "labels": ["Glycosylated hemoglobin A", "HbA1c", "Hemoglobin A1c"],
                "score": 0.80,
                "evidence_count": 35,
                "semantic_types": [{"name": "Amino Acid, Peptide, or Protein"}],
            },
        ],
        top_k=4,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert ordered_cuis.index("C0011849") < ordered_cuis.index("C0745117")
    assert ordered_cuis.index("C4014362") < ordered_cuis.index("C0745117")
    controlled = next(hit for hit in ranked if hit["cui"] == "C0745117")
    assert controlled["score_breakdown"]["lexical_component"] < 0.5


def test_query_ranker_penalizes_numeric_context_without_substantive_anchor() -> None:
    ranked = rank_hits(
        "poorly controlled type 2 diabetes hba1c",
        [
            {
                "cui": "C4014362",
                "name": "Type 2 diabetes mellitus (T2D)",
                "labels": ["Type 2 diabetes mellitus (T2D)"],
                "score": 0.72,
                "evidence_count": 1,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0242633",
                "name": "T-helper cell type 2",
                "labels": ["T-helper cell type 2", "Type 2 T-helper cell"],
                "score": 0.72,
                "evidence_count": 40,
                "semantic_types": [{"name": "Cell"}],
            },
            {
                "cui": "C0390423",
                "name": "Angiotensin II Receptor, Type 2",
                "labels": ["Angiotensin II Receptor, Type 2"],
                "score": 0.72,
                "evidence_count": 40,
                "semantic_types": [{"name": "Amino Acid, Peptide, or Protein"}],
            },
        ],
        top_k=3,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert ordered_cuis[0] == "C4014362"
    helper_cell = next(hit for hit in ranked if hit["cui"] == "C0242633")
    receptor = next(hit for hit in ranked if hit["cui"] == "C0390423")
    specific = next(hit for hit in ranked if hit["cui"] == "C4014362")
    assert helper_cell["score_breakdown"]["numeric_context_fragment_penalty"] > 0
    assert receptor["score_breakdown"]["numeric_context_fragment_penalty"] > 0
    assert helper_cell["score_breakdown"]["specificity_component"] == 0.0
    assert specific["score_breakdown"]["numeric_context_fragment_penalty"] == 0.0


def test_query_ranker_does_not_double_count_vector_for_lexical_fallback() -> None:
    ranked = rank_hits(
        "nocturnal chest pressure",
        [
            {
                "cui": "C0000001",
                "name": "Cardiac neoplasm",
                "labels": ["Cardiac neoplasm"],
                "score": 0.90,
                "evidence_count": 10,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0000002",
                "name": "Chest pressure",
                "labels": ["Chest pressure"],
                "score": 0.72,
                "evidence_count": 1,
                "semantic_types": [{"name": "Sign or Symptom"}],
            },
        ],
        top_k=2,
    )

    vector_only = next(hit for hit in ranked if hit["cui"] == "C0000001")
    breakdown = vector_only["score_breakdown"]
    assert breakdown["lexical_fallback_used"]
    assert breakdown["lexical_component"] == 0.24
    assert breakdown["vector_component"] == 0.12
    assert breakdown["rank_score"] == 0.40


def test_query_ranker_prefers_direct_infection_over_followup_and_broad_bucket() -> None:
    ranked = rank_hits(
        "Imaging studies suggest possible infection requiring further diagnostic evaluation and follow up",
        [
            {
                "cui": "C0589120",
                "name": "Follow-up status",
                "labels": ["Follow-up status"],
                "score": 1.1175,
                "match_type": "umls_label",
                "evidence_count": 10,
                "semantic_types": [{"name": "Finding"}],
                "evidence_items": [{"text": "infection diagnostic evaluation follow up"}],
            },
            {
                "cui": "C0009450",
                "name": "Communicable Diseases",
                "labels": ["Communicable Diseases", "Infection"],
                "score": 1.34,
                "match_type": "umls_label",
                "evidence_count": 1908,
                "semantic_types": [{"name": "Disease or Syndrome"}],
                "evidence_items": [{"text": "infection requiring follow up"}],
            },
            {
                "cui": "C3714514",
                "name": "Infection",
                "labels": ["Infection"],
                "score": 1.34,
                "match_type": "umls_label",
                "evidence_count": 15,
                "semantic_types": [{"name": "Pathologic Function"}],
                "evidence_items": [{"text": "possible infection on imaging"}],
            },
        ],
        top_k=3,
    )

    assert ranked[0]["cui"] == "C3714514"
    broad = next(hit for hit in ranked if hit["cui"] == "C0009450")
    assert ranked[0]["score_breakdown"]["semantic_component"] > broad["score_breakdown"]["semantic_component"]


def test_query_ranker_demotes_generic_infection_when_specific_sti_anchors_are_present() -> None:
    ranked = rank_hits(
        (
            "Urethritis testing was positive for gonorrhea and chlamydia infection. "
            "Ceftriaxone was administered in clinic."
        ),
        [
            {
                "cui": "C3714514",
                "name": "Infection",
                "labels": ["Infection"],
                "score": 1.0,
                "match_type": "umls_label",
                "evidence_count": 20,
                "semantic_types": [{"name": "Pathologic Function"}],
                "evidence_items": [{"text": "infection"}],
            },
            {
                "cui": "C0008149",
                "name": "Chlamydia Infections",
                "labels": ["Chlamydia infection", "Chlamydia Infections"],
                "score": 0.94,
                "match_type": "umls_label",
                "evidence_count": 12,
                "semantic_types": [{"name": "Disease or Syndrome"}],
                "evidence_items": [{"text": "chlamydia infection"}],
            },
            {
                "cui": "C0018081",
                "name": "Gonorrhea",
                "labels": ["Gonorrhea"],
                "score": 0.92,
                "match_type": "umls_label",
                "evidence_count": 12,
                "semantic_types": [{"name": "Disease or Syndrome"}],
                "evidence_items": [{"text": "gonorrhea infection"}],
            },
        ],
        top_k=3,
    )

    generic = next(hit for hit in ranked if hit["cui"] == "C3714514")
    assert generic["score_breakdown"]["clinical_context_sense_penalty"] > 0
    assert ranked[0]["cui"] in {"C0008149", "C0018081"}
    assert ranked.index(generic) > 0


def test_query_ranker_filters_broad_viral_disease_when_specific_context_is_present() -> None:
    virus_diseases = {
        "cui": "C0042769",
        "name": "Virus Diseases",
        "labels": ["Virus Diseases", "Viral illness"],
        "score": 1.05,
        "match_type": "umls_label",
        "matched_label": "Viral illness",
        "matched_query_span": "viral illness",
        "evidence_count": 20,
        "semantic_group": "DISO",
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    copd = {
        "cui": "C0024117",
        "name": "Chronic obstructive pulmonary disease",
        "labels": ["Chronic obstructive pulmonary disease", "COPD"],
        "score": 0.94,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_group": "DISO",
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    copd_exacerbation = {
        "cui": "C0740304",
        "name": "COPD exacerbation",
        "labels": ["COPD exacerbation"],
        "score": 0.92,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_group": "DISO",
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    bk_nephropathy = {
        "cui": "C1697878",
        "name": "BK virus nephropathy",
        "labels": ["BK virus nephropathy"],
        "score": 0.9,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_group": "DISO",
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }

    copd_ranked = rank_hits(
        "COPD exacerbation occurred after a viral illness with worsening dyspnea.",
        [virus_diseases, copd, copd_exacerbation],
        top_k=3,
    )
    copd_ordered = [hit["cui"] for hit in copd_ranked]
    assert "C0024117" in copd_ordered
    assert "C0740304" in copd_ordered
    assert "C0042769" not in copd_ordered

    bk_ranked = rank_hits(
        "BK viral load rose and biopsy confirmed BK virus nephropathy.",
        [virus_diseases, bk_nephropathy],
        top_k=2,
    )
    assert bk_ranked[0]["cui"] == "C1697878"
    assert "C0042769" not in [hit["cui"] for hit in bk_ranked]

    direct_broad = rank_hits("viral illness", [virus_diseases], top_k=1)
    assert direct_broad[0]["cui"] == "C0042769"


def test_query_ranker_demotes_history_context_when_query_is_active_condition() -> None:
    active = {
        "cui": "C0004096",
        "name": "Asthma",
        "labels": ["Asthma"],
        "score": 0.95,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    history = {
        "cui": "C0455544",
        "name": "H/O: asthma",
        "labels": ["H/O: asthma", "History of asthma"],
        "score": 1.0,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Finding"}],
    }

    ranked = rank_hits("asthma albuterol wheezing", [history, active], top_k=2)
    history_hit = next(hit for hit in ranked if hit["cui"] == "C0455544")
    assert history_hit["score_breakdown"]["clinical_context_sense_penalty"] > 0
    assert ranked[0]["cui"] == "C0004096"

    history_query_ranked = rank_hits("past history of asthma", [history, active], top_k=2)
    history_query_hit = next(hit for hit in history_query_ranked if hit["cui"] == "C0455544")
    assert history_query_hit["score_breakdown"]["clinical_context_sense_penalty"] == 0.0


def test_query_ranker_demotes_susceptibility_context_when_query_is_active_condition() -> None:
    active = {
        "cui": "C0004096",
        "name": "Asthma",
        "labels": ["Asthma"],
        "score": 0.95,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    susceptibility = {
        "cui": "C1869116",
        "name": "ASTHMA, SUSCEPTIBILITY TO",
        "labels": ["ASTHMA, SUSCEPTIBILITY TO"],
        "score": 1.0,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Finding"}],
    }

    ranked = rank_hits("asthma albuterol wheezing", [susceptibility, active], top_k=2)
    susceptibility_hit = next(hit for hit in ranked if hit["cui"] == "C1869116")
    assert susceptibility_hit["score_breakdown"]["clinical_context_sense_penalty"] > 0
    assert ranked[0]["cui"] == "C0004096"

    genetics_ranked = rank_hits("asthma susceptibility gene", [susceptibility, active], top_k=2)
    genetics_hit = next(hit for hit in genetics_ranked if hit["cui"] == "C1869116")
    assert genetics_hit["score_breakdown"]["clinical_context_sense_penalty"] == 0.0


def test_query_ranker_demotes_resistant_organism_when_query_is_drug_context() -> None:
    drug = {
        "cui": "C0042313",
        "name": "vancomycin",
        "labels": ["vancomycin"],
        "score": 0.95,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Antibiotic"}],
    }
    resistant_organism = {
        "cui": "C1265175",
        "name": "Vancomycin-Resistant Enterococci",
        "labels": ["Vancomycin-Resistant Enterococci"],
        "score": 1.0,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Bacterium"}],
    }

    ranked = rank_hits(
        "diabetic foot osteomyelitis vancomycin bone biopsy",
        [resistant_organism, drug],
        top_k=2,
    )
    organism_hit = next(hit for hit in ranked if hit["cui"] == "C1265175")
    assert organism_hit["score_breakdown"]["clinical_context_sense_penalty"] > 0
    assert ranked[0]["cui"] == "C0042313"

    organism_query_ranked = rank_hits(
        "vancomycin resistant enterococci culture",
        [resistant_organism, drug],
        top_k=2,
    )
    organism_query_hit = next(hit for hit in organism_query_ranked if hit["cui"] == "C1265175")
    assert organism_query_hit["score_breakdown"]["clinical_context_sense_penalty"] == 0.0


def test_query_ranker_demotes_broad_bacteria_when_query_has_specific_infection_context() -> None:
    broad_bacteria = {
        "cui": "C0004611",
        "name": "Bacteria",
        "labels": ["Bacteria"],
        "score": 1.0,
        "match_type": "umls_label",
        "matched_label": "Bacteria",
        "matched_query_span": "bacteria",
        "evidence_count": 12,
        "semantic_types": [{"name": "Bacterium"}],
    }
    bacterial_pneumonia = {
        "cui": "C0004626",
        "name": "Bacterial pneumonia",
        "labels": ["Bacterial pneumonia"],
        "score": 0.95,
        "match_type": "umls_label",
        "matched_label": "Bacterial pneumonia",
        "matched_query_span": "bacterial pneumonia",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }

    ranked = rank_hits(
        "Sputum culture supported bacterial pneumonia and ceftriaxone was started.",
        [broad_bacteria, bacterial_pneumonia],
        top_k=2,
    )
    assert all(hit["cui"] != "C0004611" for hit in ranked)
    assert ranked[0]["cui"] == "C0004626"

    direct_ranked = rank_hits("bacteria", [broad_bacteria, bacterial_pneumonia], top_k=2)
    direct_bacteria_hit = next(hit for hit in direct_ranked if hit["cui"] == "C0004611")
    assert direct_bacteria_hit["score_breakdown"]["clinical_context_sense_penalty"] == 0.0
    assert direct_ranked[0]["cui"] == "C0004611"


def test_query_ranker_demotes_staging_context_when_query_is_active_condition() -> None:
    active = {
        "cui": "C0007131",
        "name": "Non-Small Cell Lung Carcinoma",
        "labels": ["Non-Small Cell Lung Carcinoma"],
        "score": 0.95,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Neoplastic Process"}],
    }
    staging = {
        "cui": "C0280217",
        "name": "stage, non-small cell lung cancer",
        "labels": ["stage, non-small cell lung cancer"],
        "score": 1.0,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Neoplastic Process"}],
    }

    ranked = rank_hits(
        "egfr mutated non small cell lung cancer osimertinib",
        [staging, active],
        top_k=2,
    )
    staging_hit = next(hit for hit in ranked if hit["cui"] == "C0280217")
    assert staging_hit["score_breakdown"]["clinical_context_sense_penalty"] > 0
    assert ranked[0]["cui"] == "C0007131"

    staging_query_ranked = rank_hits(
        "stage non small cell lung cancer",
        [staging, active],
        top_k=2,
    )
    staging_query_hit = next(hit for hit in staging_query_ranked if hit["cui"] == "C0280217")
    assert staging_query_hit["score_breakdown"]["clinical_context_sense_penalty"] == 0.0


def test_query_ranker_demotes_generic_mutation_context_when_specific_context_present() -> None:
    active = {
        "cui": "C0007131",
        "name": "Non-Small Cell Lung Carcinoma",
        "labels": ["Non-Small Cell Lung Carcinoma"],
        "score": 0.95,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Neoplastic Process"}],
    }
    mutation = {
        "cui": "C1705285",
        "name": "Mutation Abnormality",
        "labels": ["Mutation Abnormality"],
        "score": 1.0,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Cell or Molecular Dysfunction"}],
    }

    ranked = rank_hits(
        "egfr mutated non small cell lung cancer osimertinib",
        [mutation, active],
        top_k=2,
    )
    mutation_hit = next(hit for hit in ranked if hit["cui"] == "C1705285")
    assert mutation_hit["score_breakdown"]["clinical_context_sense_penalty"] > 0
    assert ranked[0]["cui"] == "C0007131"

    generic_query_ranked = rank_hits("mutation abnormality", [mutation, active], top_k=2)
    generic_query_hit = next(hit for hit in generic_query_ranked if hit["cui"] == "C1705285")
    assert generic_query_hit["score_breakdown"]["clinical_context_sense_penalty"] == 0.0


def test_query_ranker_demotes_broad_thromboembolism_fragment_for_specific_query() -> None:
    specific = {
        "cui": "C0034065",
        "name": "Pulmonary Embolism",
        "labels": ["Pulmonary Embolism"],
        "score": 0.95,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Pathologic Function"}],
    }
    broad = {
        "cui": "C1704212",
        "name": "Embolus",
        "labels": ["Embolus"],
        "score": 1.0,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Finding"}],
    }

    ranked = rank_hits(
        "pulmonary embolism apixaban right heart strain",
        [broad, specific],
        top_k=2,
    )
    broad_hit = next(hit for hit in ranked if hit["cui"] == "C1704212")
    assert broad_hit["score_breakdown"]["clinical_context_sense_penalty"] > 0
    assert ranked[0]["cui"] == "C0034065"

    broad_query_ranked = rank_hits("embolus", [broad, specific], top_k=2)
    broad_query_hit = next(hit for hit in broad_query_ranked if hit["cui"] == "C1704212")
    assert broad_query_hit["score_breakdown"]["clinical_context_sense_penalty"] == 0.0


def test_query_ranker_demotes_generic_prose_status_concepts_in_clinical_context() -> None:
    pyelonephritis = {
        "cui": "C0520575",
        "name": "Acute pyelonephritis",
        "labels": ["Acute pyelonephritis"],
        "score": 0.95,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    ceftriaxone = {
        "cui": "C0007561",
        "name": "ceftriaxone",
        "labels": ["ceftriaxone"],
        "score": 0.9,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Antibiotic"}],
    }
    administration = {
        "cui": "C1533734",
        "name": "Administration (procedure)",
        "labels": ["Administration (procedure)"],
        "score": 1.05,
        "match_type": "umls_label",
        "evidence_count": 20,
        "semantic_types": [{"name": "Therapeutic or Preventive Procedure"}],
    }
    confirmation = {
        "cui": "C0750484",
        "name": "Confirmation",
        "labels": ["Confirmation"],
        "score": 1.0,
        "match_type": "umls_label",
        "evidence_count": 20,
        "semantic_types": [{"name": "Finding"}],
    }

    ranked = rank_hits(
        "urine culture confirmed acute pyelonephritis and ceftriaxone was administered",
        [administration, confirmation, pyelonephritis, ceftriaxone],
        top_k=4,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert "C0520575" in ordered_cuis
    assert "C0007561" in ordered_cuis
    assert "C1533734" not in ordered_cuis
    assert "C0750484" not in ordered_cuis

    status_query_ranked = rank_hits("confirmation documented", [confirmation], top_k=1)
    assert (
        status_query_ranked[0]["score_breakdown"]["clinical_context_sense_penalty"]
        == 0.0
    )


def test_query_ranker_demotes_admin_review_when_review_word_is_clinical_prose() -> None:
    peer_review = {
        "cui": "C0030768",
        "name": "Peer Review",
        "labels": ["Peer Review", "reviewed"],
        "score": 1.08,
        "match_type": "umls_label",
        "matched_label": "reviewed",
        "matched_query_span": "reviewed",
        "evidence_count": 20,
        "semantic_types": [{"name": "Intellectual Product"}],
    }
    warfarin = {
        "cui": "C0043031",
        "name": "Warfarin",
        "labels": ["Warfarin"],
        "score": 0.94,
        "match_type": "umls_label",
        "matched_label": "Warfarin",
        "matched_query_span": "warfarin",
        "evidence_count": 12,
        "semantic_types": [{"name": "Clinical Drug"}],
    }
    inr = {
        "cui": "C0525032",
        "name": "International Normalized Ratio",
        "labels": ["INR", "International Normalized Ratio"],
        "score": 0.92,
        "match_type": "umls_label",
        "matched_label": "INR",
        "matched_query_span": "INR",
        "evidence_count": 12,
        "semantic_types": [{"name": "Finding"}],
    }

    ranked = rank_hits(
        "Anticoagulation clinic reviewed supratherapeutic INR after warfarin dose changes.",
        [peer_review, warfarin, inr],
        top_k=3,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert ordered_cuis[:2] == ["C0043031", "C0525032"]
    assert "C0030768" not in ordered_cuis


def test_query_ranker_suppresses_ordinary_word_artifacts_in_clinical_prose() -> None:
    chart_device = {
        "cui": "C0007963",
        "name": "chart [medical device]",
        "labels": ["chart [medical device]", "chart"],
        "score": 1.08,
        "match_type": "umls_label",
        "matched_label": "chart",
        "matched_query_span": "chart",
        "evidence_count": 20,
        "semantic_types": [{"name": "Medical Device"}],
    }
    source = {
        "cui": "C0449416",
        "name": "Source",
        "labels": ["Source"],
        "score": 1.06,
        "match_type": "umls_label",
        "matched_label": "Source",
        "matched_query_span": "source",
        "evidence_count": 20,
        "semantic_types": [{"name": "Finding"}],
    }
    true_control_status = {
        "cui": "C3274648",
        "name": "True Control Status",
        "labels": ["True Control Status", "control"],
        "score": 1.07,
        "match_type": "umls_label",
        "matched_label": "control",
        "matched_query_span": "control",
        "evidence_count": 20,
        "semantic_types": [{"name": "Finding"}],
    }
    control_aspects = {
        "cui": "C0243148",
        "name": "control aspects",
        "labels": ["control aspects", "control"],
        "score": 1.05,
        "match_type": "umls_label",
        "matched_label": "control",
        "matched_query_span": "control",
        "evidence_count": 20,
        "semantic_types": [{"name": "Qualitative Concept"}],
    }
    copd = {
        "cui": "C0024117",
        "name": "Chronic Obstructive Airway Disease",
        "labels": ["Chronic obstructive pulmonary disease"],
        "score": 0.94,
        "match_type": "umls_label",
        "matched_label": "Chronic obstructive pulmonary disease",
        "matched_query_span": "chronic obstructive pulmonary disease",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    sepsis = {
        "cui": "C0243026",
        "name": "Sepsis",
        "labels": ["Sepsis"],
        "score": 0.92,
        "match_type": "umls_label",
        "matched_label": "Sepsis",
        "matched_query_span": "sepsis",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }

    ranked = rank_hits(
        "Chart review described chronic obstructive pulmonary disease while source control was planned for sepsis.",
        [chart_device, source, true_control_status, control_aspects, copd, sepsis],
        top_k=6,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert ordered_cuis == ["C0024117", "C0243026"]
    assert is_blocked_generic_concept("C0007963", "chart [medical device]")
    assert is_blocked_generic_concept("C0449416", "Source")
    assert is_blocked_generic_concept("C3274648", "True Control Status")
    assert is_blocked_generic_concept("C0243148", "control aspects")


def test_query_ranker_strongly_demotes_confirmation_status_in_clinical_context() -> None:
    cellulitis = {
        "cui": "C0007642",
        "name": "Cellulitis",
        "labels": ["Cellulitis", "lower leg cellulitis"],
        "score": 0.92,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    abscess = {
        "cui": "C0000833",
        "name": "Abscess",
        "labels": ["Abscess", "fluctuant abscess"],
        "score": 0.9,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    fluid_collection = {
        "cui": "C0232201",
        "name": "Fluid collection",
        "labels": ["Fluid collection"],
        "score": 0.88,
        "match_type": "umls_label",
        "evidence_count": 8,
        "semantic_types": [{"name": "Finding"}],
    }
    confirmation = {
        "cui": "C0750484",
        "name": "Confirmation",
        "labels": ["Confirmation", "Confirmed"],
        "score": 1.05,
        "match_type": "umls_label",
        "evidence_count": 20,
        "semantic_types": [{"name": "Finding"}],
    }
    not_confirmed = {
        "cui": "C0205420",
        "name": "Not confirmed",
        "labels": ["Not confirmed"],
        "score": 1.02,
        "match_type": "umls_label",
        "evidence_count": 20,
        "semantic_types": [{"name": "Finding"}],
    }

    ranked = rank_hits(
        (
            "Exam showed lower leg cellulitis with a fluctuant abscess. "
            "Ultrasonography confirmed a fluid collection, incision and drainage was performed, "
            "and cephalexin was prescribed after discharge."
        ),
        [confirmation, not_confirmed, cellulitis, abscess, fluid_collection],
        top_k=5,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    for clinical_cui in {"C0007642", "C0000833", "C0232201"}:
        assert clinical_cui in ordered_cuis
    assert "C0750484" not in ordered_cuis
    assert "C0205420" not in ordered_cuis

    direct_status_ranked = rank_hits("not confirmed", [not_confirmed], top_k=1)
    assert (
        direct_status_ranked[0]["score_breakdown"]["clinical_context_sense_penalty"]
        == 0.0
    )


def test_query_ranker_filters_admin_review_artifacts_in_clinical_context() -> None:
    hiv = {
        "cui": "C0019693",
        "name": "HIV infection",
        "labels": ["HIV infection"],
        "score": 0.95,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    viral_load = {
        "cui": "C0376705",
        "name": "Viral load",
        "labels": ["Viral load"],
        "score": 0.92,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Laboratory or Test Result"}],
    }
    peer_review = {
        "cui": "C0030768",
        "name": "Peer Review",
        "labels": ["Peer Review", "peer reviewed", "peer reviews"],
        "score": 1.08,
        "match_type": "umls_label",
        "matched_label": "peer reviewed",
        "evidence_count": 20,
        "semantic_types": [{"name": "Intellectual Product"}],
    }
    reviewed_by = {
        "cui": "C1709941",
        "name": "Reviewed By",
        "labels": ["Reviewed By"],
        "score": 1.04,
        "match_type": "umls_label",
        "matched_label": "Reviewed By",
        "evidence_count": 20,
        "semantic_types": [{"name": "Clinical Attribute"}],
    }
    not_reviewed = {
        "cui": "C3846076",
        "name": "Not reviewed",
        "labels": ["Not reviewed"],
        "score": 1.02,
        "match_type": "umls_label",
        "matched_label": "Not reviewed",
        "evidence_count": 20,
        "semantic_types": [{"name": "Finding"}],
    }
    chart_review = {
        "cui": "C0541653",
        "name": "Medical Chart Review",
        "labels": ["Medical Chart Review", "Chart Review"],
        "score": 1.0,
        "match_type": "umls_label",
        "matched_label": "Chart Review",
        "evidence_count": 20,
        "semantic_types": [{"name": "Health Care Activity"}],
    }

    ranked = rank_hits(
        (
            "The HIV infection visit reviewed viral load, CD4 lymphocyte count, "
            "and adherence to tenofovir."
        ),
        [peer_review, reviewed_by, not_reviewed, chart_review, hiv, viral_load],
        top_k=6,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert "C0019693" in ordered_cuis
    assert "C0376705" in ordered_cuis
    assert "C0030768" not in ordered_cuis
    assert "C1709941" not in ordered_cuis
    assert "C3846076" not in ordered_cuis
    assert "C0541653" not in ordered_cuis

    direct_peer_review = rank_hits("peer review", [peer_review], top_k=1)
    assert direct_peer_review[0]["cui"] == "C0030768"
    direct_chart_review = rank_hits("chart review", [chart_review], top_k=1)
    assert direct_chart_review[0]["cui"] == "C0541653"


def test_query_ranker_filters_standalone_immune_mediated_modifier_in_clinical_context() -> None:
    modifier = {
        "cui": "C4330477",
        "name": "Immune-mediated",
        "labels": ["Immune-mediated"],
        "score": 1.1,
        "match_type": "umls_label",
        "evidence_count": 20,
        "semantic_types": [{"name": "Qualitative Concept"}],
    }
    colitis = {
        "cui": "C4761223",
        "name": "Immune-mediated colitis",
        "labels": ["Immune-mediated colitis"],
        "score": 1.0,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    diarrhea = {
        "cui": "C0011991",
        "name": "Diarrhea",
        "labels": ["Diarrhea", "watery diarrhea"],
        "score": 0.95,
        "match_type": "umls_label",
        "evidence_count": 10,
        "semantic_types": [{"name": "Sign or Symptom"}],
    }

    ranked = rank_hits(
        "Pembrolizumab caused immune-mediated colitis with watery diarrhea.",
        [modifier, colitis, diarrhea],
        top_k=3,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert "C4761223" in ordered_cuis
    assert "C0011991" in ordered_cuis
    assert "C4330477" not in ordered_cuis

    direct_modifier = rank_hits("immune-mediated", [modifier], top_k=1)
    assert direct_modifier[0]["score_breakdown"]["clinical_context_sense_penalty"] == 0.0


def test_query_ranker_filters_risks_and_benefits_when_benefit_is_prose_context() -> None:
    hearing_loss = {
        "cui": "C1384666",
        "name": "Hearing Loss",
        "labels": ["Hearing Loss", "progressive hearing loss"],
        "score": 0.92,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Finding"}],
    }
    cochlear_implant = {
        "cui": "C0009199",
        "name": "Cochlear implant",
        "labels": ["Cochlear implant"],
        "score": 0.9,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Medical Device"}],
    }
    risks_and_benefits = {
        "cui": "C0687742",
        "name": "Risks and Benefits",
        "labels": ["Risks and Benefits"],
        "score": 1.05,
        "match_type": "umls_label",
        "evidence_count": 20,
        "semantic_types": [{"name": "Qualitative Concept"}],
    }

    ranked = rank_hits(
        "Audiology evaluated progressive hearing loss after hearing aids provided limited benefit.",
        [risks_and_benefits, hearing_loss, cochlear_implant],
        top_k=3,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert "C1384666" in ordered_cuis
    assert "C0687742" not in ordered_cuis

    direct_context = rank_hits("risks and benefits", [risks_and_benefits], top_k=1)
    assert direct_context[0]["score_breakdown"]["clinical_context_sense_penalty"] == 0.0


def test_query_ranker_filters_systemic_symptoms_when_specific_symptoms_are_present() -> None:
    fever = {
        "cui": "C0015967",
        "name": "Fever",
        "labels": ["Fever"],
        "score": 0.9,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Sign or Symptom"}],
    }
    cough = {
        "cui": "C0010200",
        "name": "Cough",
        "labels": ["Cough"],
        "score": 0.88,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Sign or Symptom"}],
    }
    systemic_symptoms = {
        "cui": "C2039684",
        "name": "systemic symptoms",
        "labels": ["systemic symptoms"],
        "score": 1.05,
        "match_type": "umls_label",
        "evidence_count": 20,
        "semantic_types": [{"name": "Sign or Symptom"}],
    }
    general_symptom = {
        "cui": "C0159028",
        "name": "General symptom",
        "labels": ["General symptom"],
        "score": 1.04,
        "match_type": "umls_label",
        "evidence_count": 20,
        "semantic_types": [{"name": "Sign or Symptom"}],
    }
    no_respiratory_symptoms = {
        "cui": "C0425443",
        "name": "No respiratory symptoms",
        "labels": ["No respiratory symptoms"],
        "score": 1.03,
        "match_type": "umls_label",
        "evidence_count": 20,
        "semantic_types": [{"name": "Finding"}],
    }
    multiple_symptoms = {
        "cui": "C0231217",
        "name": "Multiple symptoms",
        "labels": ["Multiple symptoms"],
        "score": 1.02,
        "match_type": "umls_label",
        "evidence_count": 20,
        "semantic_types": [{"name": "Sign or Symptom"}],
    }
    respiratory_symptoms = {
        "cui": "C9998001",
        "name": "Respiratory symptoms",
        "labels": ["Respiratory symptoms"],
        "score": 1.01,
        "match_type": "umls_label",
        "evidence_count": 20,
        "semantic_types": [{"name": "Sign or Symptom"}],
    }
    distressing_symptoms = {
        "cui": "C4060677",
        "name": "Distressing symptoms",
        "labels": ["Distressing symptoms"],
        "score": 1.0,
        "match_type": "umls_label",
        "evidence_count": 20,
        "semantic_types": [{"name": "Sign or Symptom"}],
    }
    signs_and_symptoms = {
        "cui": "C9998002",
        "name": "Signs and symptoms",
        "labels": ["Signs and symptoms"],
        "score": 0.99,
        "match_type": "umls_label",
        "evidence_count": 20,
        "semantic_types": [{"name": "Sign or Symptom"}],
    }

    ranked = rank_hits(
        "The patient developed fever, cough, myalgia, and a positive rapid test.",
        [
            systemic_symptoms,
            general_symptom,
            no_respiratory_symptoms,
            multiple_symptoms,
            respiratory_symptoms,
            distressing_symptoms,
            signs_and_symptoms,
            fever,
            cough,
        ],
        top_k=4,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert "C0015967" in ordered_cuis
    assert "C0010200" in ordered_cuis
    assert "C2039684" not in ordered_cuis
    assert "C0159028" not in ordered_cuis
    assert "C0425443" not in ordered_cuis
    assert "C0231217" not in ordered_cuis
    assert "C9998001" not in ordered_cuis
    assert "C4060677" not in ordered_cuis
    assert "C9998002" not in ordered_cuis

    direct_context = rank_hits("systemic symptoms", [systemic_symptoms], top_k=1)
    assert direct_context[0]["score_breakdown"]["clinical_context_sense_penalty"] == 0.0
    direct_general = rank_hits("general symptom", [general_symptom], top_k=1)
    assert direct_general[0]["score_breakdown"]["clinical_context_sense_penalty"] == 0.0
    direct_negated = rank_hits("no respiratory symptoms", [no_respiratory_symptoms], top_k=1)
    assert direct_negated[0]["score_breakdown"]["clinical_context_sense_penalty"] == 0.0
    direct_multiple = rank_hits("multiple symptoms", [multiple_symptoms], top_k=1)
    assert direct_multiple[0]["score_breakdown"]["clinical_context_sense_penalty"] == 0.0
    direct_respiratory = rank_hits("respiratory symptoms", [respiratory_symptoms], top_k=1)
    assert direct_respiratory[0]["score_breakdown"]["clinical_context_sense_penalty"] == 0.0
    direct_distressing = rank_hits("distressing symptoms", [distressing_symptoms], top_k=1)
    assert direct_distressing[0]["score_breakdown"]["clinical_context_sense_penalty"] == 0.0
    direct_signs = rank_hits("signs and symptoms", [signs_and_symptoms], top_k=1)
    assert direct_signs[0]["score_breakdown"]["clinical_context_sense_penalty"] == 0.0


def test_query_ranker_filters_yes_no_answer_findings_in_clinical_context() -> None:
    fever = {
        "cui": "C0015967",
        "name": "Fever",
        "labels": ["Fever"],
        "score": 0.92,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Sign or Symptom"}],
    }
    cough = {
        "cui": "C0010200",
        "name": "Cough",
        "labels": ["Cough"],
        "score": 0.9,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Sign or Symptom"}],
    }
    yes_finding = {
        "cui": "C0205421",
        "name": "Yes",
        "labels": ["Yes"],
        "score": 1.05,
        "match_type": "umls_label",
        "matched_label": "Yes",
        "evidence_count": 20,
        "semantic_types": [{"name": "Finding"}],
    }
    no_finding = {
        "cui": "C0205422",
        "name": "No",
        "labels": ["No"],
        "score": 1.04,
        "match_type": "umls_label",
        "matched_label": "No",
        "evidence_count": 20,
        "semantic_types": [{"name": "Finding"}],
    }

    ranked = rank_hits(
        "No fever was reported, but cough persisted and the rapid influenza test was positive.",
        [yes_finding, no_finding, fever, cough],
        top_k=4,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert "C0015967" in ordered_cuis
    assert "C0010200" in ordered_cuis
    assert "C0205421" not in ordered_cuis
    assert "C0205422" not in ordered_cuis

    direct_yes = rank_hits("yes", [yes_finding], top_k=1)
    assert direct_yes[0]["score_breakdown"]["clinical_context_sense_penalty"] == 0.0
    direct_no = rank_hits("no", [no_finding], top_k=1)
    assert direct_no[0]["score_breakdown"]["clinical_context_sense_penalty"] == 0.0


def test_query_ranker_uses_primary_label_for_generic_status_noise() -> None:
    cellulitis = {
        "cui": "C0007642",
        "name": "Cellulitis",
        "labels": ["Cellulitis", "lower leg cellulitis"],
        "score": 0.92,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    abscess = {
        "cui": "C0000833",
        "name": "Abscess",
        "labels": ["Abscess", "fluctuant abscess"],
        "score": 0.9,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    drainage = {
        "cui": "C0184661",
        "name": "Incision and drainage",
        "labels": ["Incision and drainage"],
        "score": 0.88,
        "match_type": "umls_label",
        "evidence_count": 8,
        "semantic_types": [{"name": "Therapeutic or Preventive Procedure"}],
    }
    cephalexin = {
        "cui": "C0007716",
        "name": "Cephalexin",
        "labels": ["Cephalexin"],
        "score": 0.88,
        "match_type": "umls_label",
        "evidence_count": 8,
        "semantic_types": [{"name": "Antibiotic"}],
    }
    confirmation = {
        "cui": "C0750484",
        "name": "Confirmation",
        "labels": ["Confirmation", "Laboratory-confirmed finding"],
        "score": 1.05,
        "match_type": "umls_label",
        "matched_label": "Confirmation",
        "evidence_count": 20,
        "semantic_types": [{"name": "Finding"}],
    }
    response_declined = {
        "cui": "C1709925",
        "name": "Response Declined",
        "labels": ["Response Declined", "Treatment response declined"],
        "score": 1.0,
        "match_type": "umls_label",
        "matched_label": "Response Declined",
        "evidence_count": 10,
        "semantic_types": [{"name": "Finding"}],
    }
    evaluation = {
        "cui": "C0220825",
        "name": "Evaluation",
        "labels": ["Evaluation", "Clinical evaluation activity"],
        "score": 0.98,
        "match_type": "umls_label",
        "matched_label": "Evaluation",
        "evidence_count": 10,
        "semantic_types": [{"name": "Health Care Activity"}],
    }

    ranked = rank_hits(
        (
            "Exam showed lower leg cellulitis with a fluctuant abscess. "
            "Ultrasonography confirmed a fluid collection, incision and drainage was performed, "
            "and cephalexin was prescribed after discharge."
        ),
        [confirmation, response_declined, evaluation, cellulitis, abscess, drainage, cephalexin],
        top_k=7,
    )

    by_cui = {hit["cui"]: hit for hit in ranked}
    ordered_cuis = [hit["cui"] for hit in ranked]
    for clinical_cui in {"C0007642", "C0000833", "C0184661", "C0007716"}:
        assert clinical_cui in by_cui
    assert "C0750484" not in ordered_cuis
    assert "C1709925" not in ordered_cuis
    assert "C0220825" not in ordered_cuis

    direct_status_ranked = rank_hits("response declined", [response_declined], top_k=1)
    assert (
        direct_status_ranked[0]["score_breakdown"]["clinical_context_sense_penalty"]
        == 0.0
    )


def test_query_ranker_suppresses_low_value_admin_status_fragments() -> None:
    osteomyelitis = {
        "cui": "C0029443",
        "name": "Osteomyelitis",
        "labels": ["Osteomyelitis", "diabetic foot osteomyelitis"],
        "score": 0.94,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    bone_biopsy = {
        "cui": "C0203221",
        "name": "Bone biopsy",
        "labels": ["Bone biopsy"],
        "score": 0.9,
        "match_type": "umls_label",
        "evidence_count": 8,
        "semantic_types": [{"name": "Diagnostic Procedure"}],
    }
    amputation = {
        "cui": "C0002692",
        "name": "Amputation",
        "labels": ["Amputation"],
        "score": 0.9,
        "match_type": "umls_label",
        "evidence_count": 8,
        "semantic_types": [{"name": "Therapeutic or Preventive Procedure"}],
    }
    positive = {
        "cui": "C1446409",
        "name": "Positive",
        "labels": ["Positive"],
        "score": 1.05,
        "match_type": "umls_label",
        "matched_label": "Positive",
        "evidence_count": 20,
        "semantic_types": [{"name": "Finding"}],
    }
    patient_discharge = {
        "cui": "C0030685",
        "name": "Patient Discharge",
        "labels": ["Patient Discharge"],
        "score": 1.0,
        "match_type": "umls_label",
        "matched_label": "Patient Discharge",
        "evidence_count": 10,
        "semantic_types": [{"name": "Health Care Activity"}],
    }
    discharge_summary = {
        "cui": "C0801840",
        "name": "Discharge summary",
        "labels": ["Discharge summary"],
        "score": 0.99,
        "match_type": "umls_label",
        "matched_label": "Discharge summary",
        "evidence_count": 10,
        "semantic_types": [{"name": "Clinical Attribute"}],
    }
    living_alone = {
        "cui": "C0439044",
        "name": "Living Alone",
        "labels": ["Living Alone"],
        "score": 0.98,
        "match_type": "semantic_vector",
        "evidence_count": 10,
        "semantic_types": [{"name": "Finding"}],
    }
    high = {
        "cui": "C0205250",
        "name": "High",
        "labels": ["High"],
        "score": 0.97,
        "match_type": "umls_label",
        "matched_label": "High",
        "evidence_count": 10,
        "semantic_types": [{"name": "Quantitative Concept"}],
    }

    ranked = rank_hits(
        (
            "The cohort study compared patients receiving vancomycin for diabetic foot "
            "osteomyelitis. Exposed bone and positive bone biopsy were associated with "
            "higher amputation risk after discharge."
        ),
        [
            positive,
            patient_discharge,
            discharge_summary,
            living_alone,
            high,
            osteomyelitis,
            bone_biopsy,
            amputation,
        ],
        top_k=8,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert "C0029443" in ordered_cuis
    assert "C0203221" in ordered_cuis
    assert "C0002692" in ordered_cuis
    assert "C1446409" not in ordered_cuis
    assert "C0030685" not in ordered_cuis
    assert "C0801840" not in ordered_cuis
    assert "C0439044" not in ordered_cuis
    assert "C0205250" not in ordered_cuis

    direct_positive = rank_hits("positive", [positive], top_k=1)
    assert direct_positive[0]["cui"] == "C1446409"
    direct_discharge_summary = rank_hits("discharge summary", [discharge_summary], top_k=1)
    assert direct_discharge_summary[0]["cui"] == "C0801840"


def test_query_ranker_filters_prescribed_medications_admin_noise() -> None:
    sleep_apnea = {
        "cui": "C0520679",
        "name": "Obstructive sleep apnea",
        "labels": ["Obstructive sleep apnea"],
        "score": 0.94,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_group": "DISO",
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    cpap = {
        "cui": "C0199451",
        "name": "Continuous positive airway pressure",
        "labels": ["Continuous positive airway pressure", "CPAP"],
        "score": 0.92,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_group": "PROC",
        "semantic_types": [{"name": "Therapeutic or Preventive Procedure"}],
    }
    prescribed_medications = {
        "cui": "C3202967",
        "name": "Prescribed medications",
        "labels": ["Prescribed medications"],
        "score": 1.05,
        "match_type": "semantic_vector",
        "evidence_count": 20,
        "semantic_group": "OBS",
        "semantic_types": [{"name": "Clinical Attribute"}],
    }

    ranked = rank_hits(
        (
            "A patient with obstructive sleep apnea had polysomnography, and "
            "continuous positive airway pressure was prescribed."
        ),
        [prescribed_medications, sleep_apnea, cpap],
        top_k=3,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert "C0520679" in ordered_cuis
    assert "C0199451" in ordered_cuis
    assert "C3202967" not in ordered_cuis

    direct_admin = rank_hits("prescribed medications", [prescribed_medications], top_k=1)
    assert direct_admin[0]["cui"] == "C3202967"


def test_query_ranker_filters_low_value_units_ordinals_and_status_artifacts() -> None:
    urinary_retention = {
        "cui": "C5700171",
        "name": "Urinary retention",
        "labels": ["Urinary retention"],
        "score": 0.94,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_group": "DISO",
        "semantic_types": [{"name": "Finding"}],
    }
    neonatal_jaundice = {
        "cui": "C0022353",
        "name": "Neonatal jaundice",
        "labels": ["Neonatal jaundice"],
        "score": 0.92,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_group": "DISO",
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    burn = {
        "cui": "C0006434",
        "name": "Burn injury",
        "labels": ["Burn injury"],
        "score": 0.9,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_group": "DISO",
        "semantic_types": [{"name": "Injury or Poisoning"}],
    }
    artifacts = [
        {
            "cui": "C0439390",
            "name": "Milliliter per Second",
            "labels": ["Milliliter per Second"],
            "score": 1.05,
            "match_type": "semantic_vector",
            "evidence_count": 20,
            "semantic_group": "OTHER",
            "semantic_types": [{"name": "Quantitative Concept"}],
        },
        {
            "cui": "C4517839",
            "name": "Sixty Four",
            "labels": ["Sixty Four"],
            "score": 1.04,
            "match_type": "semantic_vector",
            "evidence_count": 20,
            "semantic_group": "OTHER",
            "semantic_types": [{"name": "Quantitative Concept"}],
        },
        {
            "cui": "C0205436",
            "name": "Second - ordinal",
            "labels": ["Second - ordinal", "Second"],
            "score": 1.03,
            "match_type": "umls_label",
            "matched_label": "Second",
            "matched_query_span": "second",
            "evidence_count": 20,
            "semantic_group": "OTHER",
            "semantic_types": [{"name": "Quantitative Concept"}],
        },
        {
            "cui": "C2348168",
            "name": "Second Unit of Plane Angle",
            "labels": ["Second Unit of Plane Angle", "Second"],
            "score": 1.025,
            "match_type": "umls_label",
            "matched_label": "Second",
            "matched_query_span": "second",
            "evidence_count": 20,
            "semantic_group": "OTHER",
            "semantic_types": [{"name": "Quantitative Concept"}],
        },
        {
            "cui": "C1543244",
            "name": "Wound status",
            "labels": ["Wound status"],
            "score": 1.02,
            "match_type": "semantic_vector",
            "evidence_count": 20,
            "semantic_group": "OBS",
            "semantic_types": [{"name": "Clinical Attribute"}],
        },
        {
            "cui": "C1519814",
            "name": "Update",
            "labels": ["Update", "Updated"],
            "score": 1.01,
            "match_type": "umls_label",
            "matched_label": "Updated",
            "matched_query_span": "updated",
            "evidence_count": 20,
            "semantic_group": "OTHER",
            "semantic_types": [{"name": "Qualitative Concept"}],
        },
        {
            "cui": "C1619815",
            "name": "Pending - Day type",
            "labels": ["Pending - Day type", "Pending"],
            "score": 1.0,
            "match_type": "umls_label",
            "matched_label": "Pending",
            "matched_query_span": "pending",
            "evidence_count": 20,
            "semantic_group": "OTHER",
            "semantic_types": [{"name": "Qualitative Concept"}],
        },
        {
            "cui": "C3891813",
            "name": "Had No Pain",
            "labels": ["Had No Pain", "No Pain"],
            "score": 0.99,
            "match_type": "umls_label",
            "matched_label": "No Pain",
            "matched_query_span": "no pain",
            "evidence_count": 20,
            "semantic_group": "DISO",
            "semantic_types": [{"name": "Finding"}],
        },
        {
            "cui": "C3476546",
            "name": "Symptoms score",
            "labels": ["Symptoms score"],
            "score": 0.98,
            "match_type": "semantic_vector",
            "evidence_count": 20,
            "semantic_group": "DISO",
            "semantic_types": [{"name": "Finding"}],
        },
        {
            "cui": "C0814225",
            "name": "Benefit",
            "labels": ["Benefit"],
            "score": 0.97,
            "match_type": "umls_label",
            "matched_label": "Benefit",
            "matched_query_span": "benefit",
            "evidence_count": 20,
            "semantic_group": "OTHER",
            "semantic_types": [{"name": "Quantitative Concept"}],
        },
    ]

    ranked = rank_hits(
        (
            "Bladder scan showed 800 mL post void residual during urinary retention. "
            "No pain was documented after computed tomography angiography ruled out embolus. "
            "A newborn developed neonatal jaundice on the second day of life. "
            "A partial thickness burn wound was dressed, vaccine status was updated, "
            "and cultures were pending. Symptoms began yesterday, and hearing aids provided limited benefit."
        ),
        [*artifacts, urinary_retention, neonatal_jaundice, burn],
        top_k=12,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert "C5700171" in ordered_cuis
    assert "C0022353" in ordered_cuis
    assert "C0006434" in ordered_cuis
    for artifact_cui in {
        "C0439390",
        "C4517839",
        "C0205436",
        "C2348168",
        "C1543244",
        "C1519814",
        "C1619815",
        "C3891813",
        "C3476546",
        "C0814225",
    }:
        assert artifact_cui not in ordered_cuis

    direct_second = rank_hits("second ordinal", [artifacts[2]], top_k=1)
    assert direct_second[0]["cui"] == "C0205436"
    direct_pending = rank_hits("pending day type", [artifacts[6]], top_k=1)
    assert direct_pending[0]["cui"] == "C1619815"


def test_query_ranker_filters_broad_family_and_admin_category_artifacts() -> None:
    lung_cancer = {
        "cui": "C0007131",
        "name": "Non-Small Cell Lung Carcinoma",
        "labels": ["Non-Small Cell Lung Carcinoma", "non small cell lung cancer"],
        "score": 0.94,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_group": "DISO",
        "semantic_types": [{"name": "Neoplastic Process"}],
    }
    b12_deficiency = {
        "cui": "C0042847",
        "name": "Vitamin B12 deficiency",
        "labels": ["Vitamin B12 deficiency"],
        "score": 0.92,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_group": "DISO",
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    thyroid_nodule = {
        "cui": "C0040137",
        "name": "Thyroid nodule",
        "labels": ["Thyroid nodule"],
        "score": 0.9,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_group": "DISO",
        "semantic_types": [{"name": "Finding"}],
    }
    artifacts = [
        {
            "cui": "C0027651",
            "name": "Neoplasms",
            "labels": ["Neoplasms", "Oncology"],
            "score": 1.05,
            "match_type": "umls_label",
            "matched_label": "Oncology",
            "matched_query_span": "oncology",
            "evidence_count": 20,
            "semantic_group": "DISO",
            "semantic_types": [{"name": "Neoplastic Process"}],
        },
        {
            "cui": "C0042890",
            "name": "Vitamins",
            "labels": ["Vitamins", "Vitamin"],
            "score": 1.04,
            "match_type": "umls_label",
            "matched_label": "Vitamin",
            "matched_query_span": "vitamin",
            "evidence_count": 20,
            "semantic_group": "CHEM",
            "semantic_types": [{"name": "Vitamin"}],
        },
        {
            "cui": "C0040135",
            "name": "Thyroid Hormones",
            "labels": ["Thyroid Hormones", "Hormone, Thyroid"],
            "score": 1.03,
            "match_type": "umls_label",
            "matched_label": "Hormone, Thyroid",
            "matched_query_span": "thyroid hormone",
            "evidence_count": 20,
            "semantic_group": "OTHER",
            "semantic_types": [{"name": "Hormone"}],
        },
        {
            "cui": "C0039401",
            "name": "Education (procedure)",
            "labels": ["Education (procedure)", "Teaching"],
            "score": 1.02,
            "match_type": "umls_label",
            "matched_label": "Teaching",
            "matched_query_span": "teaching",
            "evidence_count": 20,
            "semantic_group": "OTHER",
            "semantic_types": [{"name": "Educational Activity"}],
        },
        {
            "cui": "C0012655",
            "name": "Disease susceptibility",
            "labels": ["Disease susceptibility", "susceptibilities"],
            "score": 1.01,
            "match_type": "umls_label",
            "matched_label": "susceptibilities",
            "matched_query_span": "susceptibilities",
            "evidence_count": 20,
            "semantic_group": "OBS",
            "semantic_types": [{"name": "Clinical Attribute"}],
        },
    ]

    ranked = rank_hits(
        (
            "The oncology trial enrolled patients with EGFR mutated non small cell lung cancer. "
            "The patient had vitamin B12 deficiency and a thyroid nodule with normal thyroid "
            "stimulating hormone. Discharge teaching was provided while susceptibilities were pending."
        ),
        [*artifacts, lung_cancer, b12_deficiency, thyroid_nodule],
        top_k=8,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert "C0007131" in ordered_cuis
    assert "C0042847" in ordered_cuis
    assert "C0040137" in ordered_cuis
    for artifact_cui in {"C0027651", "C0042890", "C0040135", "C0039401", "C0012655"}:
        assert artifact_cui not in ordered_cuis

    direct_neoplasm = rank_hits("neoplasms", [artifacts[0]], top_k=1)
    assert direct_neoplasm[0]["cui"] == "C0027651"
    direct_vitamin = rank_hits("vitamins", [artifacts[1]], top_k=1)
    assert direct_vitamin[0]["cui"] == "C0042890"


def test_query_ranker_suppresses_low_value_other_group_fillers() -> None:
    thyrotoxicosis = {
        "cui": "C0040156",
        "name": "Thyrotoxicosis",
        "labels": ["Thyrotoxicosis"],
        "score": 0.94,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_group": "DISO",
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    coronary_stenosis = {
        "cui": "C0242231",
        "name": "Coronary artery stenosis",
        "labels": ["Coronary artery stenosis", "coronary stenosis"],
        "score": 0.92,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_group": "DISO",
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    glucose_measurement = {
        "cui": "C0392201",
        "name": "Glucose measurement",
        "labels": ["Glucose measurement", "serum glucose"],
        "score": 0.9,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_group": "OBS",
        "semantic_types": [{"name": "Laboratory Procedure"}],
    }
    suspected_diagnosis = {
        "cui": "C0332147",
        "name": "Suspected diagnosis",
        "labels": ["Suspected diagnosis", "Suspected"],
        "score": 1.05,
        "match_type": "umls_label",
        "matched_label": "Suspected",
        "matched_query_span": "suspected",
        "evidence_count": 20,
        "semantic_group": "OTHER",
        "semantic_types": [{"name": "Finding"}],
    }
    critical = {
        "cui": "C1511545",
        "name": "Critical",
        "labels": ["Critical"],
        "score": 1.04,
        "match_type": "umls_label",
        "matched_label": "Critical",
        "matched_query_span": "critical",
        "evidence_count": 20,
        "semantic_group": "OTHER",
        "semantic_types": [{"name": "Qualitative Concept"}],
    }
    mg_dl = {
        "cui": "C0439269",
        "name": "mg/dL",
        "labels": ["mg/dL"],
        "score": 1.03,
        "match_type": "umls_label",
        "matched_label": "mg/dL",
        "matched_query_span": "mg/dL",
        "evidence_count": 20,
        "semantic_group": "OTHER",
        "semantic_types": [{"name": "Quantitative Concept"}],
    }

    ranked = rank_hits(
        (
            "He was admitted with suspected thyrotoxicosis, critical coronary stenosis, "
            "and serum glucose 240 mg/dL."
        ),
        [
            suspected_diagnosis,
            critical,
            mg_dl,
            thyrotoxicosis,
            coronary_stenosis,
            glucose_measurement,
        ],
        top_k=6,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert "C0040156" in ordered_cuis
    assert "C0242231" in ordered_cuis
    assert "C0392201" in ordered_cuis
    assert "C0332147" not in ordered_cuis
    assert "C1511545" not in ordered_cuis
    assert "C0439269" not in ordered_cuis

    direct_suspected = rank_hits("suspected diagnosis", [suspected_diagnosis], top_k=1)
    assert direct_suspected[0]["cui"] == "C0332147"
    direct_critical = rank_hits("critical", [critical], top_k=1)
    assert direct_critical[0]["cui"] == "C1511545"
    direct_mg_dl = rank_hits("mg/dL", [mg_dl], top_k=1)
    assert direct_mg_dl[0]["cui"] == "C0439269"


def test_query_ranker_keeps_specific_oncology_endpoint_terms() -> None:
    lung_cancer = {
        "cui": "C0007131",
        "name": "Non-Small Cell Lung Carcinoma",
        "labels": ["Non-Small Cell Lung Carcinoma", "non small cell lung cancer"],
        "score": 0.94,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_group": "DISO",
        "semantic_types": [{"name": "Neoplastic Process"}],
    }
    egfr = {
        "cui": "C1414313",
        "name": "EGFR gene",
        "labels": ["EGFR gene", "EGFR"],
        "score": 0.92,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_group": "GENE",
        "semantic_types": [{"name": "Gene or Genome"}],
    }
    osimertinib = {
        "cui": "C4058811",
        "name": "osimertinib",
        "labels": ["osimertinib"],
        "score": 0.9,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_group": "CHEM",
        "semantic_types": [{"name": "Pharmacologic Substance"}],
    }
    progression_free_survival = {
        "cui": "C0242792",
        "name": "Progression-Free Survival",
        "labels": ["Progression-Free Survival", "progression free survival"],
        "score": 1.05,
        "match_type": "umls_label",
        "matched_label": "progression free survival",
        "matched_query_span": "progression free survival",
        "evidence_count": 20,
        "semantic_group": "DISO",
        "semantic_types": [{"name": "Finding"}],
    }

    ranked = rank_hits(
        (
            "The oncology trial enrolled patients with EGFR mutated non small cell lung cancer. "
            "Osimertinib improved progression free survival compared with platinum chemotherapy."
        ),
        [progression_free_survival, lung_cancer, egfr, osimertinib],
        top_k=4,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert "C0242792" in ordered_cuis
    assert "C0007131" in ordered_cuis
    assert "C1414313" in ordered_cuis
    assert "C4058811" in ordered_cuis


def test_query_ranker_filters_contextual_false_positive_anchor_concepts() -> None:
    acute_kidney_injury = {
        "cui": "C2609414",
        "name": "Acute kidney injury",
        "labels": ["Acute kidney injury"],
        "score": 0.94,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    urinalysis = {
        "cui": "C0042014",
        "name": "Urinalysis",
        "labels": ["Urinalysis"],
        "score": 0.9,
        "match_type": "umls_label",
        "evidence_count": 10,
        "semantic_types": [{"name": "Laboratory Procedure"}],
    }
    baseline_cement = {
        "cui": "C0168634",
        "name": "BaseLine dental cement",
        "labels": ["BaseLine dental cement"],
        "score": 1.03,
        "match_type": "umls_label",
        "matched_label": "baseline",
        "evidence_count": 10,
        "semantic_types": [{"name": "Pharmacologic Substance"}],
    }
    orthopedic_cast = {
        "cui": "C0179686",
        "name": "Orthopedic Cast",
        "labels": ["Orthopedic Cast", "Casts"],
        "score": 1.02,
        "match_type": "umls_label",
        "matched_label": "Casts",
        "evidence_count": 10,
        "semantic_group": "DEVI",
        "semantic_types": [{"name": "Medical Device"}],
    }

    ranked = rank_hits(
        (
            "After intravenous contrast exposure, creatinine increased from baseline and "
            "urine output declined. Nephrology diagnosed acute kidney injury, reviewed "
            "urinalysis with granular casts, and recommended isotonic fluids."
        ),
        [baseline_cement, orthopedic_cast, acute_kidney_injury, urinalysis],
        top_k=4,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert "C2609414" in ordered_cuis
    assert "C0042014" in ordered_cuis
    assert "C0168634" not in ordered_cuis
    assert "C0179686" not in ordered_cuis

    direct_baseline_cement = rank_hits("baseline dental cement", [baseline_cement], top_k=1)
    assert direct_baseline_cement[0]["cui"] == "C0168634"
    direct_orthopedic_cast = rank_hits("orthopedic cast", [orthopedic_cast], top_k=1)
    assert direct_orthopedic_cast[0]["cui"] == "C0179686"


def test_query_ranker_demotes_respiratory_aspiration_in_orthopedic_joint_context() -> None:
    joint_aspiration = {
        "cui": "C0204854",
        "name": "Joint aspiration",
        "labels": ["aspirated", "Joint aspiration"],
        "score": 0.90,
        "match_type": "umls_label",
        "matched_label": "aspirated",
        "matched_query_span": "aspirated",
        "sources": ["active_label_supplement"],
        "evidence_count": 0,
        "semantic_group": "PROC",
        "semantic_types": [{"name": "Therapeutic or Preventive Procedure"}],
    }
    respiratory_aspiration = {
        "cui": "C1720922",
        "name": "Respiratory Aspiration",
        "labels": ["Respiratory Aspiration", "aspirated"],
        "score": 1.02,
        "match_type": "umls_label",
        "matched_label": "aspirated",
        "matched_query_span": "aspirated",
        "evidence_count": 12,
        "semantic_group": "DISO",
        "semantic_types": [{"name": "Injury or Poisoning"}],
    }

    ranked = rank_hits(
        "Orthopedics aspirated a painful knee arthroplasty and sent synovial culture.",
        [respiratory_aspiration, joint_aspiration],
        top_k=2,
    )

    respiratory = next(hit for hit in ranked if hit["cui"] == "C1720922")
    assert respiratory["score_breakdown"]["clinical_context_sense_penalty"] > 0
    assert ranked[0]["cui"] == "C0204854"


def test_query_ranker_filters_contextual_device_and_extract_false_positives() -> None:
    ultrasonography = {
        "cui": "C0041618",
        "name": "Ultrasonography",
        "labels": ["Ultrasonography", "Ultrasound"],
        "score": 0.92,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Diagnostic Procedure"}],
    }
    ultrasound_device = {
        "cui": "C1875843",
        "name": "ultrasound device",
        "labels": ["ultrasound device"],
        "score": 1.03,
        "match_type": "umls_label",
        "matched_label": "ULTRASOUND",
        "evidence_count": 10,
        "semantic_group": "DEVI",
        "semantic_types": [{"name": "Medical Device"}],
    }
    cirrhosis = {
        "cui": "C0023890",
        "name": "Liver Cirrhosis",
        "labels": ["Cirrhosis", "Liver cirrhosis"],
        "score": 0.94,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    liver_extract = {
        "cui": "C0023899",
        "name": "liver extract",
        "labels": ["liver extract"],
        "score": 1.02,
        "match_type": "umls_label",
        "matched_label": "LIVER",
        "evidence_count": 10,
        "semantic_types": [{"name": "Pharmacologic Substance"}],
    }

    ranked = rank_hits(
        "Right upper quadrant ultrasound showed cirrhosis of the liver.",
        [ultrasound_device, liver_extract, ultrasonography, cirrhosis],
        top_k=4,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert "C0041618" in ordered_cuis
    assert "C0023890" in ordered_cuis
    assert "C1875843" not in ordered_cuis
    assert "C0023899" not in ordered_cuis

    direct_ultrasound_device = rank_hits("ultrasound device", [ultrasound_device], top_k=1)
    assert direct_ultrasound_device[0]["cui"] == "C1875843"
    direct_liver_extract = rank_hits("liver extract", [liver_extract], top_k=1)
    assert direct_liver_extract[0]["cui"] == "C0023899"


def test_query_ranker_filters_cough_medicine_homonym_in_symptom_context() -> None:
    influenza = {
        "cui": "C0021400",
        "name": "Influenza",
        "labels": ["Influenza"],
        "score": 0.94,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    cough = {
        "cui": "C0010200",
        "name": "Cough",
        "labels": ["Cough"],
        "score": 0.9,
        "match_type": "umls_label",
        "matched_label": "Cough",
        "evidence_count": 12,
        "semantic_types": [{"name": "Sign or Symptom"}],
    }
    cough_guaifenesin = {
        "cui": "C3815497",
        "name": "Cough (guaifenesin)",
        "labels": ["Cough (guaifenesin)", "Cough"],
        "score": 1.04,
        "match_type": "umls_label",
        "matched_label": "Cough",
        "evidence_count": 10,
        "semantic_types": [{"name": "Pharmacologic Substance"}],
    }

    ranked = rank_hits(
        "The patient developed influenza with fever, cough, and myalgia.",
        [cough_guaifenesin, influenza, cough],
        top_k=3,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert "C0021400" in ordered_cuis
    assert "C0010200" in ordered_cuis
    assert "C3815497" not in ordered_cuis

    direct_drug = rank_hits("cough guaifenesin", [cough_guaifenesin], top_k=1)
    assert direct_drug[0]["cui"] == "C3815497"


def test_query_ranker_filters_low_value_context_status_results() -> None:
    migraine = {
        "cui": "C0149931",
        "name": "Migraine Disorders",
        "labels": ["Migraine", "Migraine Disorders"],
        "score": 0.9,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    photophobia = {
        "cui": "C0085636",
        "name": "Photophobia",
        "labels": ["Photophobia"],
        "score": 0.88,
        "match_type": "umls_label",
        "evidence_count": 8,
        "semantic_types": [{"name": "Sign or Symptom"}],
    }
    negative = {
        "cui": "C0205160",
        "name": "Negative",
        "labels": ["Negative"],
        "score": 1.04,
        "match_type": "umls_label",
        "matched_label": "Negative",
        "evidence_count": 20,
        "semantic_types": [{"name": "Finding"}],
    }
    recurrent_condition = {
        "cui": "C5980458",
        "name": "Recurrent Condition",
        "labels": ["Recurrent Condition"],
        "score": 1.03,
        "match_type": "umls_label",
        "matched_label": "Recurrent Condition",
        "evidence_count": 20,
        "semantic_types": [{"name": "Finding"}],
    }
    attack = {
        "cui": "C1304680",
        "name": "Attack (finding)",
        "labels": ["Attack (finding)"],
        "score": 1.02,
        "match_type": "umls_label",
        "matched_label": "Attack (finding)",
        "evidence_count": 20,
        "semantic_types": [{"name": "Finding"}],
    }
    negative_predictive_value = {
        "cui": "C5551885",
        "name": "Negative predictive value",
        "labels": ["Negative predictive value"],
        "score": 1.01,
        "match_type": "semantic_vector",
        "evidence_count": 20,
        "semantic_types": [{"name": "Finding"}],
    }
    incidence_proportion = {
        "cui": "C0683920",
        "name": "Incidence Proportion",
        "labels": ["Incidence Proportion", "attack rate"],
        "score": 1.0,
        "match_type": "semantic_vector",
        "evidence_count": 20,
        "semantic_types": [{"name": "Quantitative Concept"}],
    }
    absence_of_necrosis = {
        "cui": "C2749404",
        "name": "Absence of necrosis",
        "labels": ["Absence of necrosis", "Necrosis Negative", "Negative for Necrosis"],
        "score": 0.99,
        "match_type": "semantic_vector",
        "evidence_count": 20,
        "semantic_types": [{"name": "Finding"}],
    }
    recurrent_tonsillitis = {
        "cui": "C0740402",
        "name": "Recurrent tonsillitis",
        "labels": ["Recurrent tonsillitis"],
        "score": 0.98,
        "match_type": "semantic_vector",
        "evidence_count": 20,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    positive_finding = {
        "cui": "C1514241",
        "name": "Positive Finding",
        "labels": ["Positive Finding"],
        "score": 0.97,
        "match_type": "umls_label",
        "matched_label": "Positive Finding",
        "evidence_count": 20,
        "semantic_types": [{"name": "Finding"}],
    }

    ranked = rank_hits(
        (
            "A patient with recurrent migraine reported photophobia and unilateral headache. "
            "Computed tomography was negative, and sumatriptan relieved the acute attack."
        ),
        [
            negative,
            recurrent_condition,
            attack,
            negative_predictive_value,
            incidence_proportion,
            absence_of_necrosis,
            recurrent_tonsillitis,
            positive_finding,
            migraine,
            photophobia,
        ],
        top_k=10,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert "C0149931" in ordered_cuis
    assert "C0085636" in ordered_cuis
    assert "C0205160" not in ordered_cuis
    assert "C5980458" not in ordered_cuis
    assert "C1304680" not in ordered_cuis
    assert "C5551885" not in ordered_cuis
    assert "C0683920" not in ordered_cuis
    assert "C2749404" not in ordered_cuis
    assert "C0740402" not in ordered_cuis
    assert "C1514241" not in ordered_cuis

    direct_negative = rank_hits("negative", [negative], top_k=1)
    assert direct_negative[0]["cui"] == "C0205160"
    direct_recurrent = rank_hits("recurrent condition", [recurrent_condition], top_k=1)
    assert direct_recurrent[0]["cui"] == "C5980458"
    direct_negative_predictive_value = rank_hits(
        "negative predictive value",
        [negative_predictive_value],
        top_k=1,
    )
    assert direct_negative_predictive_value[0]["cui"] == "C5551885"
    direct_attack_rate = rank_hits("attack rate", [incidence_proportion], top_k=1)
    assert direct_attack_rate[0]["cui"] == "C0683920"
    direct_absence = rank_hits("absence of necrosis", [absence_of_necrosis], top_k=1)
    assert direct_absence[0]["cui"] == "C2749404"
    direct_tonsillitis = rank_hits("recurrent tonsillitis", [recurrent_tonsillitis], top_k=1)
    assert direct_tonsillitis[0]["cui"] == "C0740402"


def test_query_ranker_filters_low_value_procedure_fragments() -> None:
    migraine = {
        "cui": "C0149931",
        "name": "Migraine Disorders",
        "labels": ["Migraine"],
        "score": 0.9,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    ct_head = {
        "cui": "C0040405",
        "name": "X-Ray Computed Tomography",
        "labels": ["Computed Tomography", "CT"],
        "score": 0.88,
        "match_type": "umls_label",
        "matched_query_span": "computed tomography",
        "evidence_count": 8,
        "semantic_types": [{"name": "Diagnostic Procedure"}],
    }
    tomography = {
        "cui": "C0040395",
        "name": "tomography",
        "labels": ["tomography", "Diagnostic tomography"],
        "score": 1.05,
        "match_type": "umls_label",
        "matched_query_span": "tomography",
        "evidence_count": 20,
        "semantic_types": [{"name": "Diagnostic Procedure"}],
    }
    computed = {
        "cui": "C1441526",
        "name": "Computed (procedure)",
        "labels": ["Computed (procedure)", "Computed"],
        "score": 1.03,
        "match_type": "umls_label",
        "matched_query_span": "computed",
        "evidence_count": 20,
        "semantic_types": [{"name": "Therapeutic or Preventive Procedure"}],
    }
    preventive_pharmacotherapy = {
        "cui": "C2114396",
        "name": "preventive medicine services pharmacotherapy prescribed",
        "labels": ["preventive medicine services pharmacotherapy prescribed", "pharmacotherapy prescribed"],
        "score": 1.02,
        "match_type": "semantic_vector",
        "evidence_count": 20,
        "semantic_types": [{"name": "Therapeutic or Preventive Procedure"}],
    }
    covid_testing = {
        "cui": "C5244026",
        "name": "COVID-19 Testing",
        "labels": ["COVID-19 Testing"],
        "score": 1.01,
        "match_type": "semantic_vector",
        "evidence_count": 20,
        "semantic_types": [{"name": "Diagnostic Procedure"}],
    }

    ranked = rank_hits(
        "A patient with migraine had computed tomography of the head before treatment.",
        [tomography, computed, preventive_pharmacotherapy, covid_testing, migraine, ct_head],
        top_k=6,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert "C0149931" in ordered_cuis
    assert "C0040405" in ordered_cuis
    assert "C0040395" not in ordered_cuis
    assert "C1441526" not in ordered_cuis
    assert "C2114396" not in ordered_cuis
    assert "C5244026" not in ordered_cuis

    gonorrhea = {
        "cui": "C0018081",
        "name": "Gonorrhea",
        "labels": ["Gonorrhea"],
        "score": 0.9,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    sti_ranked = rank_hits(
        "Urethritis testing was positive for gonorrhea and chlamydia infection.",
        [covid_testing, gonorrhea],
        top_k=2,
    )
    sti_ordered = [hit["cui"] for hit in sti_ranked]
    assert "C0018081" in sti_ordered
    assert "C5244026" not in sti_ordered

    cta = {
        "cui": "C1536105",
        "name": "Computed Tomography Angiography",
        "labels": ["Computed Tomography Angiography"],
        "score": 0.95,
        "match_type": "umls_label",
        "matched_query_span": "computed tomography angiography",
        "evidence_count": 10,
        "semantic_types": [{"name": "Diagnostic Procedure"}],
    }
    direct_specific = rank_hits("computed tomography angiography", [cta], top_k=1)
    assert direct_specific[0]["cui"] == "C1536105"
    direct_covid_testing = rank_hits("covid 19 testing", [covid_testing], top_k=1)
    assert direct_covid_testing[0]["cui"] == "C5244026"


def test_query_ranker_demotes_mortality_outcome_when_not_mentioned() -> None:
    gastric_ulcer = {
        "cui": "C0038358",
        "name": "Gastric ulcer",
        "labels": ["Gastric ulcer"],
        "score": 0.9,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    melena = {
        "cui": "C0025222",
        "name": "Melena",
        "labels": ["Melena"],
        "score": 0.88,
        "match_type": "umls_label",
        "evidence_count": 8,
        "semantic_types": [{"name": "Finding"}],
    }
    death = {
        "cui": "C0011065",
        "name": "Death",
        "labels": ["Death", "Mortality"],
        "score": 1.05,
        "match_type": "vector",
        "evidence_count": 30,
        "semantic_types": [{"name": "Finding"}],
    }

    ranked = rank_hits(
        (
            "He presented with hematemesis and melena after heavy NSAID use. "
            "Endoscopy found a bleeding gastric ulcer, and pantoprazole infusion "
            "was started before transfusion."
        ),
        [death, gastric_ulcer, melena],
        top_k=3,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert "C0038358" in ordered_cuis
    assert "C0025222" in ordered_cuis
    assert "C0011065" not in ordered_cuis

    mortality_ranked = rank_hits("mortality after upper gastrointestinal bleeding", [death], top_k=1)
    assert mortality_ranked[0]["score_breakdown"]["clinical_context_sense_penalty"] == 0.0


def test_query_ranker_disambiguates_cervical_gynecology_from_spine_context() -> None:
    cervical_motion_tenderness = {
        "cui": "C0234233",
        "name": "Cervical motion tenderness",
        "labels": ["Cervical motion tenderness"],
        "score": 0.92,
        "match_type": "umls_label",
        "evidence_count": 4,
        "semantic_types": [{"name": "Finding"}],
    }
    cervical_spine = {
        "cui": "C0728985",
        "name": "Cervical spine",
        "labels": ["Cervical spine"],
        "score": 1.03,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Body Part, Organ, or Organ Component"}],
    }
    pelvic_inflammatory_disease = {
        "cui": "C0242172",
        "name": "Pelvic inflammatory disease",
        "labels": ["Pelvic inflammatory disease"],
        "score": 0.88,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }

    ranked = rank_hits(
        "Exam showed cervical motion tenderness with pelvic inflammatory disease.",
        [cervical_spine, cervical_motion_tenderness, pelvic_inflammatory_disease],
        top_k=3,
    )

    spine_hit = next(hit for hit in ranked if hit["cui"] == "C0728985")
    assert spine_hit["score_breakdown"]["clinical_context_sense_penalty"] >= 0.42
    ordered_cuis = [hit["cui"] for hit in ranked]
    assert ordered_cuis.index("C0234233") < ordered_cuis.index("C0728985")
    assert ordered_cuis.index("C0242172") < ordered_cuis.index("C0728985")


def test_query_ranker_disambiguates_cervical_spine_from_gynecology_context() -> None:
    cervical_stenosis = {
        "cui": "C0158252",
        "name": "Cervical spinal stenosis",
        "labels": ["Cervical spinal stenosis"],
        "score": 0.93,
        "match_type": "umls_label",
        "evidence_count": 8,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    cervical_cancer = {
        "cui": "C0007847",
        "name": "Cervical cancer",
        "labels": ["Cervical cancer"],
        "score": 1.03,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Neoplastic Process"}],
    }
    cervical_vertebrae = {
        "cui": "C0007864",
        "name": "Cervical vertebrae",
        "labels": ["Cervical vertebrae"],
        "score": 0.88,
        "match_type": "umls_label",
        "evidence_count": 8,
        "semantic_types": [{"name": "Body Part, Organ, or Organ Component"}],
    }

    ranked = rank_hits(
        "MRI showed cervical spine stenosis with neck pain.",
        [cervical_cancer, cervical_stenosis, cervical_vertebrae],
        top_k=3,
    )

    cancer_hit = next(hit for hit in ranked if hit["cui"] == "C0007847")
    assert cancer_hit["score_breakdown"]["clinical_context_sense_penalty"] >= 0.42
    ordered_cuis = [hit["cui"] for hit in ranked]
    assert ordered_cuis.index("C0158252") < ordered_cuis.index("C0007847")
    assert ordered_cuis.index("C0007864") < ordered_cuis.index("C0007847")


def test_semantic_buckets_hide_generic_mortality_related_noise() -> None:
    finding_bucket = next(bucket for bucket in SEMANTIC_RESULT_BUCKETS if bucket["key"] == "DISO_FINDING")
    death_relation = {
        "cui": "C0011065",
        "label": "Death",
        "category": "phenotype",
        "semantic_type": "finding",
        "relation_group": "phenotype",
        "relation": "external_embedding",
        "rela": "embedding similarity",
        "source": "BioConceptVec",
    }
    bleeding_relation = {
        **death_relation,
        "cui": "C0019080",
        "label": "Bleeding",
    }

    assert not relation_visible_in_semantic_bucket(death_relation, finding_bucket, "DISO")
    assert relation_visible_in_semantic_bucket(bleeding_relation, finding_bucket, "DISO")


def test_query_ranker_demotes_device_alert_and_sleep_metadata_noise() -> None:
    nstemi = {
        "cui": "C4255010",
        "name": "Non-ST Elevated Myocardial Infarction",
        "labels": ["Non-ST Elevated Myocardial Infarction"],
        "score": 0.9,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    coronary_stenosis = {
        "cui": "C0242231",
        "name": "Coronary Stenosis",
        "labels": ["Coronary Stenosis"],
        "score": 0.88,
        "match_type": "umls_label",
        "evidence_count": 10,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    device_alert = {
        "cui": "C1551396",
        "name": "DeviceAlertLevel - Critical",
        "labels": ["DeviceAlertLevel - Critical"],
        "score": 1.08,
        "match_type": "umls_label",
        "evidence_count": 10,
        "semantic_types": [{"name": "Finding"}],
    }
    wake_after_sleep = {
        "cui": "C4744894",
        "name": "Wake After Sleep Onset",
        "labels": ["Wake After Sleep Onset"],
        "score": 1.02,
        "match_type": "umls_label",
        "evidence_count": 10,
        "semantic_types": [{"name": "Diagnostic Procedure"}],
    }

    ranked = rank_hits(
        "critical coronary stenosis after non ST elevation myocardial infarction",
        [device_alert, wake_after_sleep, nstemi, coronary_stenosis],
        top_k=4,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert ordered_cuis.index("C4255010") < ordered_cuis.index("C1551396")
    assert ordered_cuis.index("C0242231") < ordered_cuis.index("C4744894")
    device_alert_hit = next(hit for hit in ranked if hit["cui"] == "C1551396")
    sleep_metric_hit = next(hit for hit in ranked if hit["cui"] == "C4744894")
    assert device_alert_hit["score_breakdown"]["clinical_context_sense_penalty"] > 0
    assert sleep_metric_hit["score_breakdown"]["clinical_context_sense_penalty"] > 0

    device_query_ranked = rank_hits("critical device alert level", [device_alert], top_k=1)
    sleep_query_ranked = rank_hits("wake after sleep onset", [wake_after_sleep], top_k=1)
    assert (
        device_query_ranked[0]["score_breakdown"]["clinical_context_sense_penalty"]
        == 0.0
    )
    assert (
        sleep_query_ranked[0]["score_breakdown"]["clinical_context_sense_penalty"]
        == 0.0
    )


def test_query_ranker_promotes_composite_lab_result_over_result_parts() -> None:
    composite_result = {
        "cui": "C2098283",
        "name": "urine culture Escherichia coli",
        "labels": ["urine culture Escherichia coli"],
        "score": 0.78,
        "match_type": "umls_label",
        "evidence_count": 8,
        "semantic_types": [{"name": "Laboratory or Test Result"}],
    }
    urine_culture = {
        "cui": "C0430404",
        "name": "Urine culture",
        "labels": ["Urine culture"],
        "score": 0.95,
        "match_type": "umls_label",
        "evidence_count": 20,
        "semantic_types": [{"name": "Laboratory Procedure"}],
    }
    escherichia_coli = {
        "cui": "C0014834",
        "name": "Escherichia coli",
        "labels": ["Escherichia coli"],
        "score": 0.95,
        "match_type": "umls_label",
        "evidence_count": 20,
        "semantic_types": [{"name": "Bacterium"}],
    }
    pyelonephritis = {
        "cui": "C0520575",
        "name": "Acute pyelonephritis",
        "labels": ["Acute pyelonephritis"],
        "score": 0.9,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }

    ranked = rank_hits(
        "urine culture grew Escherichia coli and ceftriaxone was given for acute pyelonephritis",
        [urine_culture, escherichia_coli, pyelonephritis, composite_result],
        top_k=4,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert ordered_cuis.index("C2098283") < ordered_cuis.index("C0430404")
    assert ordered_cuis.index("C2098283") < ordered_cuis.index("C0014834")
    composite_hit = next(hit for hit in ranked if hit["cui"] == "C2098283")
    urine_culture_hit = next(hit for hit in ranked if hit["cui"] == "C0430404")
    assert composite_hit["score_breakdown"]["lab_result_composite_component"] > 0
    assert urine_culture_hit["score_breakdown"]["lab_result_composite_component"] == 0.0


def test_query_ranker_demotes_new_diagnosis_and_developed_status_noise() -> None:
    multiple_sclerosis = {
        "cui": "C0026769",
        "name": "Multiple Sclerosis",
        "labels": ["Multiple Sclerosis"],
        "score": 0.9,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    optic_neuritis = {
        "cui": "C0029134",
        "name": "Optic Neuritis",
        "labels": ["Optic Neuritis"],
        "score": 0.88,
        "match_type": "umls_label",
        "evidence_count": 10,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    to_be_developed = {
        "cui": "C4540784",
        "name": "To be developed",
        "labels": ["To be developed"],
        "score": 1.05,
        "match_type": "umls_label",
        "evidence_count": 10,
        "semantic_types": [{"name": "Finding"}],
    }
    newly_diagnosed = {
        "cui": "C1518321",
        "name": "Newly Diagnosed",
        "labels": ["Newly Diagnosed"],
        "score": 1.0,
        "match_type": "umls_label",
        "evidence_count": 10,
        "semantic_types": [{"name": "Qualitative Concept"}],
    }

    ranked = rank_hits(
        "patient developed optic neuritis with newly diagnosed multiple sclerosis",
        [to_be_developed, newly_diagnosed, multiple_sclerosis, optic_neuritis],
        top_k=4,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert ordered_cuis.index("C0026769") < ordered_cuis.index("C4540784")
    assert ordered_cuis.index("C0029134") < ordered_cuis.index("C1518321")
    developed_hit = next(hit for hit in ranked if hit["cui"] == "C4540784")
    diagnosed_hit = next(hit for hit in ranked if hit["cui"] == "C1518321")
    assert developed_hit["score_breakdown"]["clinical_context_sense_penalty"] > 0
    assert diagnosed_hit["score_breakdown"]["clinical_context_sense_penalty"] > 0

    status_query_ranked = rank_hits("newly diagnosed", [newly_diagnosed], top_k=1)
    assert (
        status_query_ranked[0]["score_breakdown"]["clinical_context_sense_penalty"]
        == 0.0
    )


def test_query_ranker_demotes_prior_and_periprocedural_context_for_active_condition() -> None:
    active = {
        "cui": "C0155626",
        "name": "Acute myocardial infarction",
        "labels": ["Acute myocardial infarction"],
        "score": 0.95,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    old = {
        "cui": "C0155668",
        "name": "Old myocardial infarction",
        "labels": ["Old myocardial infarction"],
        "score": 1.0,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Finding"}],
    }
    periprocedural = {
        "cui": "C4324584",
        "name": "Periprocedural myocardial infarction",
        "labels": ["Periprocedural myocardial infarction"],
        "score": 1.0,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    recent = {
        "cui": "C1998297",
        "name": "Recent myocardial infarction",
        "labels": ["Recent myocardial infarction"],
        "score": 1.0,
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Finding"}],
    }

    ranked = rank_hits(
        "acute myocardial infarction troponin",
        [old, periprocedural, recent, active],
        top_k=4,
    )
    old_hit = next(hit for hit in ranked if hit["cui"] == "C0155668")
    periprocedural_hit = next(hit for hit in ranked if hit["cui"] == "C4324584")
    recent_hit = next(hit for hit in ranked if hit["cui"] == "C1998297")
    assert old_hit["score_breakdown"]["clinical_context_sense_penalty"] > 0
    assert periprocedural_hit["score_breakdown"]["clinical_context_sense_penalty"] > 0
    assert recent_hit["score_breakdown"]["clinical_context_sense_penalty"] > 0
    assert ranked[0]["cui"] == "C0155626"

    prior_query_ranked = rank_hits("old myocardial infarction", [old, active], top_k=2)
    prior_query_hit = next(hit for hit in prior_query_ranked if hit["cui"] == "C0155668")
    assert prior_query_hit["score_breakdown"]["clinical_context_sense_penalty"] == 0.0

    procedural_query_ranked = rank_hits(
        "periprocedural myocardial infarction",
        [periprocedural, active],
        top_k=2,
    )
    procedural_query_hit = next(hit for hit in procedural_query_ranked if hit["cui"] == "C4324584")
    assert procedural_query_hit["score_breakdown"]["clinical_context_sense_penalty"] == 0.0

    recent_query_ranked = rank_hits("recent myocardial infarction", [recent, active], top_k=2)
    recent_query_hit = next(hit for hit in recent_query_ranked if hit["cui"] == "C1998297")
    assert recent_query_hit["score_breakdown"]["clinical_context_sense_penalty"] == 0.0


def test_query_ranker_demotes_broad_conditions_when_specific_condition_is_present() -> None:
    ranked = rank_hits(
        "acute confusion likely due to urinary tract infection",
        [
            {
                "cui": "C0042029",
                "name": "Urinary tract infection",
                "labels": ["Urinary tract infection"],
                "score": 1.0,
                "match_type": "umls_label",
                "evidence_count": 20,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0242147",
                "name": "Acute urinary tract infection",
                "labels": ["Acute urinary tract infection"],
                "score": 0.9,
                "match_type": "umls_label",
                "evidence_count": 5,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0009450",
                "name": "Communicable Diseases",
                "labels": ["Communicable Diseases", "Infection"],
                "score": 1.2,
                "match_type": "umls_label",
                "evidence_count": 1000,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0275518",
                "name": "Acute infectious disease",
                "labels": ["Acute infectious disease"],
                "score": 1.1,
                "evidence_count": 100,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0339901",
                "name": "Acute respiratory infections",
                "labels": ["Acute respiratory infections"],
                "score": 1.1,
                "evidence_count": 100,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0332148",
                "name": "Probable diagnosis",
                "labels": ["Probable diagnosis"],
                "score": 1.0,
                "match_type": "umls_label",
                "evidence_count": 10,
                "semantic_types": [{"name": "Finding"}],
            },
        ],
        top_k=6,
    )

    ordered = [hit["cui"] for hit in ranked]
    assert ordered[:2] == ["C0242147", "C0042029"]
    communicable = next(hit for hit in ranked if hit["cui"] == "C0009450")
    acute_infectious = next(hit for hit in ranked if hit["cui"] == "C0275518")
    acute_respiratory = next(hit for hit in ranked if hit["cui"] == "C0339901")
    probable = next(hit for hit in ranked if hit["cui"] == "C0332148")
    assert communicable["score_breakdown"]["generic_penalty"] > 0
    assert communicable["score_breakdown"]["relative_specificity_penalty"] > 0
    assert acute_infectious["score_breakdown"]["broad_label_penalty"] > 0
    assert acute_respiratory["score_breakdown"]["clinical_context_sense_penalty"] > 0
    assert probable["score_breakdown"]["generic_penalty"] > 0
    assert ordered.index("C0009450") > ordered.index("C0042029")


def test_query_ranker_ignores_self_synonym_fragments_for_specificity() -> None:
    ranked = rank_hits(
        "computed tomography angiography showed pulmonary embolism",
        [
            {
                "cui": "C1536105",
                "name": "Computed Tomography Angiography",
                "labels": ["Computed Tomography Angiography", "Angiography"],
                "score": 0.95,
                "evidence_count": 10,
                "semantic_types": [{"name": "Diagnostic Procedure"}],
            },
            {
                "cui": "C0040405",
                "name": "X-Ray Computed Tomography",
                "labels": ["X-Ray Computed Tomography"],
                "score": 0.95,
                "evidence_count": 10,
                "semantic_types": [{"name": "Diagnostic Procedure"}],
            },
        ],
        top_k=2,
    )

    cta = next(hit for hit in ranked if hit["cui"] == "C1536105")
    assert cta["score_breakdown"]["relative_specificity_penalty"] == 0.0
    assert ranked[0]["cui"] == "C1536105"


def test_query_ranker_prefers_non_st_mi_when_non_st_context_is_present() -> None:
    ranked = rank_hits(
        "coronary angiography after non ST elevation myocardial infarction",
        [
            {
                "cui": "C1536220",
                "name": "ST segment elevation myocardial infarction",
                "labels": ["ST segment elevation myocardial infarction", "STEMI"],
                "score": 1.0,
                "evidence_count": 10,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C4255010",
                "name": "Non-ST Elevated Myocardial Infarction",
                "labels": ["Non-ST Elevated Myocardial Infarction", "Non ST Elevation Myocardial Infarction"],
                "score": 0.95,
                "evidence_count": 10,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
        ],
        top_k=2,
    )

    stemi = next(hit for hit in ranked if hit["cui"] == "C1536220")
    assert stemi["score_breakdown"]["clinical_context_sense_penalty"] > 0
    assert ranked[0]["cui"] == "C4255010"


def test_query_ranker_preserves_poorly_controlled_diabetes_qualifier() -> None:
    ranked = rank_hits(
        "poorly controlled type 2 diabetes mellitus with foot ulcer",
        [
            {
                "cui": "C0011860",
                "name": "Diabetes Mellitus, Non-Insulin-Dependent",
                "labels": ["Diabetes Mellitus, Non-Insulin-Dependent", "Type 2 Diabetes Mellitus"],
                "score": 1.0,
                "evidence_count": 10,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "NEW1692186",
                "name": "poorly controlled type 2 diabetes mellitus",
                "labels": ["poorly controlled type 2 diabetes mellitus"],
                "score": 0.95,
                "evidence_count": 5,
                "semantic_types": [],
            },
        ],
        top_k=2,
    )

    broad = next(hit for hit in ranked if hit["cui"] == "C0011860")
    assert broad["score_breakdown"]["clinical_context_sense_penalty"] > 0
    assert ranked[0]["cui"] == "NEW1692186"


def test_query_ranker_demotes_generic_diabetes_in_gestational_context() -> None:
    ranked = rank_hits(
        "Gestational diabetes was diagnosed after an abnormal oral glucose tolerance test.",
        [
            {
                "cui": "C0011849",
                "name": "Diabetes Mellitus",
                "labels": ["Diabetes Mellitus"],
                "score": 1.05,
                "evidence_count": 20,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0011860",
                "name": "Diabetes Mellitus, Non-Insulin-Dependent",
                "labels": ["Diabetes Mellitus, Non-Insulin-Dependent", "Type 2 Diabetes Mellitus"],
                "score": 1.0,
                "evidence_count": 20,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0085207",
                "name": "Gestational Diabetes",
                "labels": ["Gestational Diabetes", "Gestational diabetes mellitus"],
                "score": 0.96,
                "evidence_count": 20,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
        ],
        top_k=3,
    )

    generic = next(hit for hit in ranked if hit["cui"] == "C0011849")
    type_2 = next(hit for hit in ranked if hit["cui"] == "C0011860")
    gestational = next(hit for hit in ranked if hit["cui"] == "C0085207")
    assert generic["score_breakdown"]["clinical_context_sense_penalty"] >= 0.90
    assert type_2["score_breakdown"]["clinical_context_sense_penalty"] >= 0.90
    assert gestational["score_breakdown"]["clinical_context_sense_penalty"] == 0.0
    assert ranked[0]["cui"] == "C0085207"

    direct_diabetes = rank_hits(
        "diabetes mellitus",
        [
            {
                "cui": "C0011849",
                "name": "Diabetes Mellitus",
                "labels": ["Diabetes Mellitus"],
                "score": 1.0,
                "evidence_count": 20,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            }
        ],
        top_k=1,
    )
    assert direct_diabetes[0]["score_breakdown"]["clinical_context_sense_penalty"] == 0.0


def test_query_ranker_demotes_broad_drug_classes_inside_specific_phrases() -> None:
    opioid_ranked = rank_hits(
        "opioid use disorder with fentanyl use and withdrawal symptoms",
        [
            {
                "cui": "C0242402",
                "name": "Opioids",
                "labels": ["Opioids"],
                "score": 1.08,
                "evidence_count": 20,
                "semantic_types": [{"name": "Pharmacologic Substance"}],
            },
            {
                "cui": "C4324621",
                "name": "Opioid Use Disorder",
                "labels": ["Opioid Use Disorder"],
                "score": 0.95,
                "evidence_count": 12,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
        ],
        top_k=2,
    )

    opioid_class = next(hit for hit in opioid_ranked if hit["cui"] == "C0242402")
    assert opioid_class["score_breakdown"]["clinical_context_sense_penalty"] > 0
    assert opioid_class["score_breakdown"]["exact_pharmacologic_component"] == 0.0
    assert opioid_ranked[0]["cui"] == "C4324621"

    androgen_ranked = rank_hits(
        "androgen deprivation therapy for prostate cancer",
        [
            {
                "cui": "C0002844",
                "name": "Androgens",
                "labels": ["Androgens", "Androgen"],
                "score": 1.08,
                "evidence_count": 20,
                "semantic_types": [{"name": "Hormone"}, {"name": "Pharmacologic Substance"}],
            },
            {
                "cui": "C0085272",
                "name": "Androgen deprivation therapy",
                "labels": ["Androgen deprivation therapy"],
                "score": 0.95,
                "evidence_count": 12,
                "semantic_types": [{"name": "Therapeutic or Preventive Procedure"}],
            },
        ],
        top_k=2,
    )

    androgen_class = next(hit for hit in androgen_ranked if hit["cui"] == "C0002844")
    assert androgen_class["score_breakdown"]["clinical_context_sense_penalty"] > 0
    assert androgen_class["score_breakdown"]["exact_pharmacologic_component"] == 0.0
    assert androgen_ranked[0]["cui"] == "C0085272"


def test_query_ranker_demotes_oncology_drug_classes_for_antibiotic_diarrhea_context() -> None:
    ranked = rank_hits(
        "He reports watery diarrhea after recent antibiotic use.",
        [
            {
                "cui": "C0578159",
                "name": "Antibiotic-associated diarrhea",
                "labels": ["Antibiotic-associated diarrhea", "diarrhea after antibiotic use"],
                "score": 0.95,
                "evidence_count": 7,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0003392",
                "name": "Antineoplastic Agents",
                "labels": ["Antineoplastic Agents", "Antineoplastic Agent"],
                "score": 1.08,
                "evidence_count": 20,
                "semantic_types": [{"name": "Pharmacologic Substance"}],
            },
            {
                "cui": "C0362063",
                "name": "Other prophylactic chemotherapy",
                "labels": ["Other prophylactic chemotherapy", "prophylactic antibiotic"],
                "score": 1.08,
                "evidence_count": 20,
                "semantic_types": [{"name": "Finding"}],
            },
            {
                "cui": "C5197734",
                "name": "Enhanced Recovery After Surgery",
                "labels": ["Enhanced Recovery After Surgery"],
                "score": 1.08,
                "evidence_count": 20,
                "semantic_types": [{"name": "Therapeutic or Preventive Procedure"}],
            },
        ],
        top_k=4,
    )

    chemotherapy = next(hit for hit in ranked if hit["cui"] == "C0362063")
    assert chemotherapy["score_breakdown"]["clinical_context_sense_penalty"] > 0
    assert all(hit["cui"] != "C0003392" for hit in ranked)
    assert all(hit["cui"] != "C5197734" for hit in ranked)
    assert ranked[0]["cui"] == "C0578159"


def test_query_ranker_demotes_autopsy_performed_for_unrelated_procedure_context() -> None:
    autopsy_query = rank_hits(
        "Autopsy was performed",
        [
            {
                "cui": "C4274690",
                "name": "Autopsy was performed",
                "labels": ["Autopsy was performed", "Autopsy performed"],
                "score": 0.95,
                "evidence_count": 5,
                "semantic_types": [{"name": "Finding"}],
            },
            {
                "cui": "C1550369",
                "name": "Performed By",
                "labels": ["Performed By"],
                "score": 0.95,
                "evidence_count": 5,
                "semantic_types": [{"name": "Conceptual Entity"}],
            },
        ],
        top_k=2,
    )
    procedure_query = rank_hits(
        "Paracentesis was performed for tense ascites",
        [
            {
                "cui": "C0034115",
                "name": "Paracentesis",
                "labels": ["Paracentesis"],
                "score": 0.90,
                "evidence_count": 5,
                "semantic_types": [{"name": "Therapeutic or Preventive Procedure"}],
            },
            {
                "cui": "C4274690",
                "name": "Autopsy was performed",
                "labels": ["Autopsy was performed", "Autopsy performed"],
                "score": 0.95,
                "evidence_count": 5,
                "semantic_types": [{"name": "Finding"}],
            },
        ],
        top_k=2,
    )

    autopsy = next(hit for hit in autopsy_query if hit["cui"] == "C4274690")
    unrelated = next(hit for hit in procedure_query if hit["cui"] == "C4274690")
    assert autopsy_query[0]["cui"] == "C4274690"
    assert procedure_query[0]["cui"] == "C0034115"
    assert autopsy["score_breakdown"]["lexical_component"] > unrelated["score_breakdown"]["lexical_component"]


def test_query_ranker_uses_first_sentence_as_primary_paragraph_intent() -> None:
    ranked = rank_hits(
        (
            "Computed tomography angiography showed acute pulmonary embolism with right heart strain. "
            "The patient was started on apixaban after venous duplex ultrasound confirmed acute deep vein thrombosis."
        ),
        [
            {
                "cui": "C0034065",
                "name": "Pulmonary Embolism",
                "labels": ["Pulmonary Embolism"],
                "score": 0.95,
                "evidence_count": 10,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0149871",
                "name": "Deep Vein Thrombosis",
                "labels": ["Deep Vein Thrombosis"],
                "score": 0.95,
                "evidence_count": 10,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
        ],
        top_k=2,
    )

    pulmonary_embolism = next(hit for hit in ranked if hit["cui"] == "C0034065")
    dvt = next(hit for hit in ranked if hit["cui"] == "C0149871")
    assert pulmonary_embolism["score_breakdown"]["first_statement_component"] > 0
    assert dvt["score_breakdown"]["first_statement_component"] == 0.0
    assert ranked[0]["cui"] == "C0034065"


def test_query_ranker_prefers_first_sentence_single_token_condition_over_culture_organism() -> None:
    ranked = rank_hits(
        (
            "Fever and a new murmur raised concern for endocarditis. "
            "Blood culture grew Staphylococcus aureus, transesophageal echocardiography showed vegetation."
        ),
        [
            {
                "cui": "C0038172",
                "name": "Staphylococcus aureus",
                "labels": ["Staphylococcus aureus"],
                "score": 1.0,
                "evidence_count": 25,
                "semantic_types": [{"name": "Bacterium"}],
            },
            {
                "cui": "C0014118",
                "name": "Endocarditis",
                "labels": ["Endocarditis"],
                "score": 0.90,
                "evidence_count": 8,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
        ],
        top_k=2,
    )

    endocarditis = next(hit for hit in ranked if hit["cui"] == "C0014118")
    organism = next(hit for hit in ranked if hit["cui"] == "C0038172")
    assert endocarditis["score_breakdown"]["first_statement_component"] > 0
    assert organism["score_breakdown"]["organism_support_penalty"] > 0
    assert ranked[0]["cui"] == "C0014118"


def test_query_ranker_prefers_first_sentence_multiword_condition_over_component_symptom() -> None:
    dental_abscess = {
        "cui": "C0518988",
        "name": "Dental abscess",
        "labels": ["Dental abscess"],
        "score": 0.9,
        "matched_query_span": "dental abscess",
        "match_type": "umls_label",
        "sources": ["active_label_supplement"],
        "evidence_count": 8,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    toothache = {
        "cui": "C0040460",
        "name": "Toothache",
        "labels": ["Toothache", "tooth pain"],
        "score": 0.95,
        "matched_query_span": "tooth pain",
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Sign or Symptom"}],
    }
    abscess = {
        "cui": "C0000833",
        "name": "Abscess",
        "labels": ["Abscess"],
        "score": 0.95,
        "matched_query_span": "abscess",
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }

    ranked = rank_hits(
        (
            "A dental abscess caused facial swelling and severe tooth pain. "
            "Dentistry performed incision and drainage."
        ),
        [toothache, abscess, dental_abscess],
        top_k=3,
    )

    by_cui = {hit["cui"]: hit for hit in ranked}
    assert by_cui["C0518988"]["score_breakdown"]["first_statement_component"] > by_cui[
        "C0040460"
    ]["score_breakdown"]["first_statement_component"]
    assert by_cui["C0000833"]["score_breakdown"]["relative_specificity_penalty"] == 0
    assert ranked[0]["cui"] == "C0518988"


def test_query_ranker_prefers_central_multiword_disease_over_single_token_component() -> None:
    peripheral_arterial_disease = {
        "cui": "C1704436",
        "name": "Peripheral Arterial Diseases",
        "labels": ["Peripheral arterial disease"],
        "score": 0.9,
        "matched_query_span": "peripheral arterial disease",
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    claudication = {
        "cui": "C0021775",
        "name": "Intermittent Claudication",
        "labels": ["Intermittent Claudication", "Claudication"],
        "score": 0.95,
        "matched_query_span": "claudication",
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }

    ranked = rank_hits(
        (
            "Vascular clinic evaluated peripheral arterial disease with exertional calf "
            "claudication. Ankle brachial index was abnormal."
        ),
        [claudication, peripheral_arterial_disease],
        top_k=2,
    )

    by_cui = {hit["cui"]: hit for hit in ranked}
    assert by_cui["C1704436"]["score_breakdown"]["first_statement_component"] > by_cui[
        "C0021775"
    ]["score_breakdown"]["first_statement_component"]
    assert ranked[0]["cui"] == "C1704436"


def test_query_ranker_preserves_exact_single_token_condition_when_specific_phrase_exists() -> None:
    autoimmune_hepatitis = {
        "cui": "C4721555",
        "name": "Autoimmune hepatitis",
        "labels": ["Autoimmune hepatitis"],
        "score": 0.9,
        "matched_query_span": "autoimmune hepatitis",
        "match_type": "umls_label",
        "sources": ["active_label_supplement"],
        "evidence_count": 8,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    hepatitis = {
        "cui": "C0019158",
        "name": "Hepatitis",
        "labels": ["Hepatitis"],
        "score": 0.95,
        "matched_query_span": "hepatitis",
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }

    ranked = rank_hits(
        "Hepatology suspected autoimmune hepatitis after elevated transaminases.",
        [hepatitis, autoimmune_hepatitis],
        top_k=2,
    )

    hepatitis_hit = next(hit for hit in ranked if hit["cui"] == "C0019158")
    assert hepatitis_hit["score_breakdown"]["relative_specificity_penalty"] == 0
    assert ranked[0]["cui"] == "C4721555"


def test_anchor_diversity_does_not_let_relation_tokens_cover_direct_concepts() -> None:
    sumatriptan = {
        "cui": "C0075632",
        "name": "sumatriptan",
        "labels": ["sumatriptan"],
        "score": 1.0,
        "matched_query_span": "sumatriptan",
        "match_type": "umls_label",
        "evidence_count": 20,
        "semantic_types": [{"name": "Pharmacologic Substance"}],
        "mrrel_matched_tokens": ["migraine", "sumatriptan"],
    }
    migraine = {
        "cui": "C0149931",
        "name": "Migraine Disorders",
        "labels": ["Migraine", "Migraine Disorders"],
        "score": 0.9,
        "matched_query_span": "migraine",
        "match_type": "umls_label",
        "evidence_count": 15,
        "semantic_types": [{"name": "Disease or Syndrome"}],
    }
    photophobia = {
        "cui": "C0085636",
        "name": "Photophobia",
        "labels": ["Photophobia"],
        "score": 0.95,
        "matched_query_span": "photophobia",
        "match_type": "umls_label",
        "evidence_count": 12,
        "semantic_types": [{"name": "Sign or Symptom"}],
    }

    ranked = rank_hits(
        (
            "A patient with recurrent migraine reported photophobia and unilateral headache. "
            "Sumatriptan relieved the attack."
        ),
        [sumatriptan, photophobia, migraine],
        top_k=3,
    )

    top_two = [hit["cui"] for hit in ranked[:2]]
    assert "C0075632" in top_two
    assert "C0149931" in top_two
    assert [hit["cui"] for hit in ranked].index("C0149931") < [hit["cui"] for hit in ranked].index("C0085636")


def test_query_ranker_demotes_comparator_arm_concepts_in_cohort_paragraphs() -> None:
    ranked = rank_hits(
        (
            "The cohort study compared patients receiving vancomycin for diabetic foot osteomyelitis "
            "with patients treated for soft tissue infection alone."
        ),
        [
            {
                "cui": "NEW1037705",
                "name": "diabetic foot osteomyelitis",
                "labels": ["diabetic foot osteomyelitis"],
                "score": 0.90,
                "evidence_count": 5,
                "semantic_types": [],
            },
            {
                "cui": "C0149778",
                "name": "Soft Tissue Infection",
                "labels": ["Soft Tissue Infection"],
                "score": 0.95,
                "evidence_count": 10,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
        ],
        top_k=2,
    )

    diabetic_foot_osteomyelitis = next(hit for hit in ranked if hit["cui"] == "NEW1037705")
    soft_tissue_infection = next(hit for hit in ranked if hit["cui"] == "C0149778")
    assert diabetic_foot_osteomyelitis["score_breakdown"]["local_extension_phrase_component"] > 0
    assert soft_tissue_infection["score_breakdown"]["comparator_arm_penalty"] > 0
    assert ranked[0]["cui"] == "NEW1037705"


def test_query_ranker_penalizes_wrong_sense_alert_and_memory_fragments() -> None:
    exam_ranked = rank_hits(
        "The patient is alert and oriented to person place and time",
        [
            {
                "cui": "C5890168",
                "name": "Alert",
                "labels": ["Alert"],
                "score": 0.8,
                "evidence_count": 2,
                "semantic_types": [{"name": "Clinical Attribute"}],
            },
            {
                "cui": "C0718338",
                "name": "Alert brand of caffeine",
                "labels": ["Alert brand of caffeine", "Alert"],
                "score": 0.9,
                "evidence_count": 5,
                "semantic_types": [{"name": "Organic Chemical"}, {"name": "Pharmacologic Substance"}],
            },
        ],
        top_k=2,
    )
    assert exam_ranked[0]["cui"] == "C5890168"
    caffeine = next(hit for hit in exam_ranked if hit["cui"] == "C0718338")
    assert caffeine["score_breakdown"]["clinical_context_sense_penalty"] > 0

    memory_ranked = rank_hits(
        "The patient has worsening memory loss and difficulty managing medications",
        [
            {
                "cui": "C0002622",
                "name": "Amnesia",
                "labels": ["Amnesia", "Memory loss"],
                "score": 1.0,
                "match_type": "umls_label",
                "evidence_count": 1,
                "semantic_types": [{"name": "Mental or Behavioral Dysfunction"}],
            },
            {
                "cui": "C0682638",
                "name": "Memory B Cells",
                "labels": ["Memory B Cells"],
                "score": 1.0,
                "evidence_count": 20,
                "semantic_types": [{"name": "Cell"}],
            },
        ],
        top_k=2,
    )
    assert memory_ranked[0]["cui"] == "C0002622"
    memory_cells = next(hit for hit in memory_ranked if hit["cui"] == "C0682638")
    assert memory_cells["score_breakdown"]["clinical_context_sense_penalty"] > 0


def test_query_ranker_extends_denial_scope_through_loss_of_consciousness() -> None:
    ranked = rank_hits(
        "No head strike or loss of consciousness was reported",
        [
            {
                "cui": "C0041657",
                "name": "Unconscious State",
                "labels": ["Unconscious State"],
                "score": 1.0,
                "match_type": "umls_label",
                "evidence_count": 30,
                "semantic_types": [{"name": "Finding"}],
            },
            {
                "cui": "C999001",
                "name": "No loss of consciousness",
                "labels": ["No loss of consciousness"],
                "score": 0.8,
                "match_type": "umls_label",
                "evidence_count": 1,
                "semantic_types": [{"name": "Finding"}],
            },
            {
                "cui": "C1399724",
                "name": "absence; head",
                "labels": ["absence; head", "head; absent"],
                "score": 1.1,
                "match_type": "umls_label",
                "evidence_count": 0,
                "semantic_types": [{"name": "Acquired Abnormality"}],
            },
        ],
        top_k=3,
    )

    assert ranked[0]["cui"] == "C999001"
    unconscious = next(hit for hit in ranked if hit["cui"] == "C0041657")
    absent_head = next(hit for hit in ranked if hit["cui"] == "C1399724")
    assert unconscious["score_breakdown"]["denied_positive_finding_penalty"] > 0
    assert absent_head["score_breakdown"]["negated_finding_component"] == 0.0


def test_query_ranker_penalizes_unrelated_therapy_in_transition_context() -> None:
    ranked = rank_hits(
        "Physical therapy recommends discharge to skilled nursing facility",
        [
            {
                "cui": "C0949766",
                "name": "Physical therapy",
                "labels": ["Physical therapy"],
                "score": 1.0,
                "match_type": "umls_label",
                "evidence_count": 10,
                "semantic_types": [{"name": "Therapeutic or Preventive Procedure"}],
            },
            {
                "cui": "C0012622",
                "name": "Discharge Planning",
                "labels": ["Discharge Planning"],
                "score": 0.8,
                "evidence_count": 5,
                "semantic_types": [{"name": "Health Care Activity"}],
            },
            {
                "cui": "C0087111",
                "name": "Therapeutic procedure",
                "labels": ["Therapeutic procedure"],
                "score": 1.1,
                "evidence_count": 100,
                "semantic_types": [{"name": "Therapeutic or Preventive Procedure"}],
            },
            {
                "cui": "C0279025",
                "name": "Hormone Therapy",
                "labels": ["Hormone Therapy"],
                "score": 1.0,
                "evidence_count": 100,
                "semantic_types": [{"name": "Therapeutic or Preventive Procedure"}],
            },
            {
                "cui": "C4704819",
                "name": "Facilities Utilization",
                "labels": ["Facilities Utilization"],
                "score": 0.9,
                "evidence_count": 20,
                "semantic_types": [{"name": "Quantitative Concept"}],
            },
        ],
        top_k=5,
    )

    ordered = [hit["cui"] for hit in ranked]
    assert ordered.index("C0949766") < ordered.index("C0087111")
    assert ordered.index("C0012622") < ordered.index("C0279025")
    therapeutic = next(hit for hit in ranked if hit["cui"] == "C0087111")
    hormone = next(hit for hit in ranked if hit["cui"] == "C0279025")
    facilities = next(hit for hit in ranked if hit["cui"] == "C4704819")
    assert therapeutic["score_breakdown"]["generic_penalty"] > 0
    assert hormone["score_breakdown"]["clinical_context_sense_penalty"] > 0
    assert facilities["score_breakdown"]["generic_penalty"] > 0


def test_query_ranker_promotes_sepsis_over_single_component_treatment_matches() -> None:
    ranked = rank_hits(
        "sepsis vasopressors antibiotics",
        [
            {
                "cui": "C0003232",
                "name": "Antibiotics",
                "labels": ["Antibiotics"],
                "score": 0.75,
                "match_type": "umls_label",
                "evidence_count": 5,
                "semantic_types": [{"name": "Antibiotic"}],
            },
            {
                "cui": "C0243026",
                "name": "Sepsis",
                "labels": ["Sepsis", "Septicemia", "Systemic infection"],
                "score": 0.795,
                "match_type": "umls_label",
                "evidence_count": 39,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0042397",
                "name": "Vasoconstrictor Agents",
                "labels": ["Vasoconstrictor Agents", "vasopressors"],
                "score": 0.795,
                "match_type": "umls_label",
                "evidence_count": 4,
                "semantic_types": [{"name": "Pharmacologic Substance"}],
            },
            {
                "cui": "C0036690",
                "name": "Septicemia",
                "labels": ["Septicemia", "Sepsis"],
                "score": 0.795,
                "match_type": "umls_label",
                "evidence_count": 0,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
        ],
        top_k=4,
    )

    assert content_tokens("sepsis") == ["sepsis"]
    assert ranked[0]["cui"] == "C0243026"
    assert ranked[0]["score_breakdown"]["semantic_component"] > 0
    assert ranked[2]["cui"] == "C0042397"
    assert ranked[3]["score_breakdown"]["semantic_component"] == 0.0


def test_zero_evidence_disambiguated_homonym_label_fallback_is_suppressed() -> None:
    assert should_suppress_label_fallback_hit(
        {
            "name": "Sepsis <Sepsidae>",
            "labels": ["Sepsis <Sepsidae>"],
            "evidence_count": 0,
        }
    )
    assert not should_suppress_label_fallback_hit(
        {
            "name": "Sepsis <Sepsidae>",
            "labels": ["Sepsis <Sepsidae>"],
            "evidence_count": 2,
        }
    )


def test_query_ranker_filters_weak_zero_evidence_component_fallback_when_evidence_exists() -> None:
    ranked = rank_hits(
        "sepsis vasopressors antibiotics",
        [
            {
                "cui": "C0243026",
                "name": "Sepsis",
                "labels": ["Sepsis"],
                "score": 0.795,
                "match_type": "umls_label",
                "matched_query_span": "sepsis",
                "evidence_count": 39,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0003232",
                "name": "Antibiotics",
                "labels": ["Antibiotics"],
                "score": 0.75,
                "match_type": "umls_label",
                "matched_query_span": "antibiotics",
                "evidence_count": 5,
                "semantic_types": [{"name": "Antibiotic"}],
            },
            {
                "cui": "C0042397",
                "name": "Vasoconstrictor Agents",
                "labels": ["Vasoconstrictor Agents", "vasopressors"],
                "score": 0.795,
                "match_type": "umls_label",
                "matched_query_span": "vasopressors",
                "evidence_count": 4,
            },
            {
                "cui": "C3540706",
                "name": "Antibiotic throat preparations",
                "labels": ["Antibiotic throat preparations"],
                "score": 0.76,
                "match_type": "umls_label",
                "matched_query_span": "antibiotics",
                "evidence_count": 0,
            },
            {
                "cui": "C0015967",
                "name": "Fever",
                "labels": ["Fever"],
                "score": 0.73,
                "evidence_count": 8,
            },
        ],
        top_k=4,
    )

    assert "C3540706" not in [hit["cui"] for hit in ranked]
    assert ranked[-1]["cui"] == "C0015967"


def test_query_ranker_keeps_strong_zero_evidence_exact_label_fallback() -> None:
    ranked = rank_hits(
        "appendectomy surgical procedure",
        [
            {
                "cui": "C0003611",
                "name": "Appendectomy",
                "labels": ["Appendectomy"],
                "score": 1.34,
                "match_type": "umls_label",
                "matched_query_span": "appendectomy",
                "evidence_count": 0,
            },
            {
                "cui": "C0221082",
                "name": "Surgical Complication",
                "labels": ["Surgical Complication"],
                "score": 0.81,
                "evidence_count": 20,
            },
            {
                "cui": "C0040071",
                "name": "Thymectomy",
                "labels": ["Thymectomy"],
                "score": 0.78,
                "evidence_count": 1,
            },
            {
                "cui": "C0190119",
                "name": "Replacement of tricuspid valve",
                "labels": ["Replacement of tricuspid valve"],
                "score": 0.76,
                "evidence_count": 3,
            },
        ],
        top_k=3,
    )

    assert ranked[0]["cui"] == "C0003611"
    assert ranked[0]["evidence_count"] == 0


def test_query_ranker_demotes_procedure_siblings_when_specific_procedure_present() -> None:
    ranked = rank_hits(
        "appendectomy surgical procedure",
        [
            {
                "cui": "C0003611",
                "name": "Appendectomy",
                "labels": ["Appendectomy"],
                "score": 1.34,
                "match_type": "umls_label",
                "matched_query_span": "appendectomy",
                "evidence_count": 0,
                "semantic_types": [{"name": "Therapeutic or Preventive Procedure"}],
            },
            {
                "cui": "C0184893",
                "name": "Emergency operation",
                "labels": ["Emergency operation"],
                "score": 0.86,
                "evidence_count": 20,
                "semantic_types": [{"name": "Therapeutic or Preventive Procedure"}],
            },
            {
                "cui": "C0009558",
                "name": "Completion pneumonectomy",
                "labels": ["Completion pneumonectomy (procedure)"],
                "score": 0.86,
                "evidence_count": 30,
                "semantic_types": [{"name": "Therapeutic or Preventive Procedure"}],
            },
            {
                "cui": "C0040071",
                "name": "Thymectomy",
                "labels": ["Thymectomy"],
                "score": 0.86,
                "evidence_count": 25,
                "semantic_types": [{"name": "Therapeutic or Preventive Procedure"}],
            },
        ],
        top_k=4,
    )

    assert ranked[0]["cui"] == "C0003611"
    procedure_siblings = {hit["cui"]: hit for hit in ranked if hit["cui"] != "C0003611"}
    assert procedure_siblings["C0009558"]["score_breakdown"]["role_mismatch_penalty"] > 0
    assert procedure_siblings["C0040071"]["score_breakdown"]["role_mismatch_penalty"] > 0
    assert procedure_siblings["C0009558"]["score_breakdown"]["lexical_fallback_used"]


def test_related_anchor_candidates_must_share_specific_procedure_anchor() -> None:
    seed = {
        "cui": "C0003611",
        "name": "Appendectomy",
        "labels": ["Appendectomy"],
        "score": 1.34,
        "match_type": "umls_label",
        "semantic_types": [{"name": "Therapeutic or Preventive Procedure"}],
    }
    assert related_anchor_candidate_matches_query(
        query_tokens=content_tokens("appendectomy surgical procedure"),
        seed_hit=seed,
        candidate_hit={
            "cui": "C0372525",
            "name": "Laparoscopic appendectomy",
            "labels": ["Laparoscopic appendectomy"],
            "semantic_types": [{"name": "Therapeutic or Preventive Procedure"}],
        },
    )
    assert not related_anchor_candidate_matches_query(
        query_tokens=content_tokens("appendectomy surgical procedure"),
        seed_hit=seed,
        candidate_hit={
            "cui": "C0009558",
            "name": "Completion pneumonectomy",
            "labels": ["Completion pneumonectomy (procedure)"],
            "semantic_types": [{"name": "Therapeutic or Preventive Procedure"}],
        },
    )


def test_query_ranker_prefers_specific_brca_breast_cancer_anchors_over_generic_risk() -> None:
    ranked = rank_hits(
        "brca1 breast cancer risk",
        [
            {
                "cui": "C0006826",
                "name": "Cancer Risk",
                "labels": ["Cancer Risk"],
                "score": 0.83,
                "evidence_count": 200,
                "semantic_types": [{"name": "Finding"}],
            },
            {
                "cui": "C0678222",
                "name": "Breast Cancer",
                "labels": ["Breast Cancer", "Malignant neoplasm of breast"],
                "score": 0.82,
                "evidence_count": 50,
                "semantic_types": [{"name": "Neoplastic Process"}],
            },
            {
                "cui": "C1414461",
                "name": "BRCA1",
                "labels": ["BRCA1", "BRCA1 gene"],
                "score": 0.78,
                "evidence_count": 8,
                "semantic_types": [{"name": "Gene or Genome"}],
            },
            {
                "cui": "C0006141",
                "name": "Breast",
                "labels": ["Breast"],
                "score": 0.82,
                "evidence_count": 90,
                "semantic_types": [{"name": "Body Part, Organ, or Organ Component"}],
            },
        ],
        top_k=4,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert ordered_cuis.index("C0678222") < ordered_cuis.index("C0006826")
    assert ordered_cuis.index("C1414461") < ordered_cuis.index("C0006826")
    cancer_risk = next(hit for hit in ranked if hit["cui"] == "C0006826")
    assert cancer_risk["score_breakdown"]["generic_fragment_penalty"] > 0
    breast_anatomy = next(hit for hit in ranked if hit["cui"] == "C0006141")
    assert breast_anatomy["score_breakdown"]["semantic_fragment_penalty"] > 0


def test_query_ranker_prefers_lab_measurement_over_anatomy_fragment() -> None:
    ranked = rank_hits(
        "high troponin after myocardial infarction",
        [
            {
                "cui": "C0027061",
                "name": "Myocardium",
                "labels": ["Myocardium", "Myocardial tissue"],
                "score": 0.795,
                "match_type": "umls_label",
                "matched_query_span": "myocardial",
                "evidence_count": 20,
                "semantic_types": [{"name": "Tissue"}],
            },
            {
                "cui": "C0523952",
                "name": "Troponin measurement",
                "labels": ["Troponin measurement"],
                "score": 0.795,
                "match_type": "umls_label",
                "matched_query_span": "troponin",
                "evidence_count": 5,
                "semantic_types": [{"name": "Laboratory Procedure"}],
            },
            {
                "cui": "C0041199",
                "name": "Troponin",
                "labels": ["Troponin"],
                "score": 0.795,
                "match_type": "umls_label",
                "matched_query_span": "troponin",
                "evidence_count": 10,
                "semantic_types": [{"name": "Amino Acid, Peptide, or Protein"}],
            },
        ],
        top_k=3,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert ordered_cuis.index("C0523952") < ordered_cuis.index("C0027061")
    myocardium = next(hit for hit in ranked if hit["cui"] == "C0027061")
    assert myocardium["score_breakdown"]["semantic_fragment_penalty"] > 0


def test_query_ranker_demotes_standalone_modifier_finding_fragments() -> None:
    ranked = rank_hits(
        "heart failure with reduced ejection fraction",
        [
            {
                "cui": "C3839346",
                "name": "Heart failure with reduced ejection fraction",
                "labels": ["Heart failure with reduced ejection fraction"],
                "score": 0.82,
                "match_type": "umls_label",
                "evidence_count": 25,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C4022792",
                "name": "Reduced left ventricular ejection fraction",
                "labels": ["Reduced left ventricular ejection fraction"],
                "score": 0.82,
                "match_type": "umls_label",
                "evidence_count": 20,
                "semantic_types": [{"name": "Finding"}],
            },
            {
                "cui": "C0392756",
                "name": "Reduced",
                "labels": [
                    "Reduced",
                    "Reduced (qualifier value)",
                    "Decrease",
                    "Decreased",
                    "Reduction",
                ],
                "score": 0.82,
                "match_type": "umls_label",
                "evidence_count": 20,
                "semantic_types": [{"name": "Finding"}],
            },
        ],
        top_k=3,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert ordered_cuis.index("C3839346") < ordered_cuis.index("C0392756")
    assert ordered_cuis.index("C4022792") < ordered_cuis.index("C0392756")
    reduced = next(hit for hit in ranked if hit["cui"] == "C0392756")
    specific_finding = next(hit for hit in ranked if hit["cui"] == "C4022792")
    assert reduced["score_breakdown"]["semantic_fragment_penalty"] >= 0.5
    assert specific_finding["score_breakdown"]["semantic_fragment_penalty"] == 0.0


def test_query_ranker_promotes_uncovered_anchor_before_duplicate_component() -> None:
    ranked = rank_hits(
        "sepsis lactate vasopressor",
        [
            {
                "cui": "C0243026",
                "name": "Sepsis",
                "labels": ["Sepsis"],
                "score": 0.795,
                "match_type": "umls_label",
                "evidence_count": 30,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0036690",
                "name": "Septicemia",
                "labels": ["Septicemia", "Sepsis"],
                "score": 0.795,
                "match_type": "umls_label",
                "evidence_count": 25,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0202115",
                "name": "Lactic acid measurement",
                "labels": ["Lactate", "Lactic acid measurement"],
                "score": 0.795,
                "match_type": "umls_label",
                "evidence_count": 10,
            },
            {
                "cui": "C0042397",
                "name": "Vasoconstrictor Agents",
                "labels": ["Vasopressor", "Vasoconstrictor Agents"],
                "score": 0.795,
                "match_type": "umls_label",
                "evidence_count": 8,
            },
        ],
        top_k=4,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert ordered_cuis.index("C0202115") < ordered_cuis.index("C0036690")
    assert ordered_cuis.index("C0042397") < ordered_cuis.index("C0036690")


def test_query_ranker_promotes_composite_context_over_zero_evidence_duplicates() -> None:
    ranked = rank_hits(
        "sepsis lactate vasopressor",
        [
            {
                "cui": "C0243026",
                "name": "Sepsis",
                "labels": ["Sepsis"],
                "score": 1.34,
                "match_type": "umls_label",
                "evidence_count": 30,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0202115",
                "name": "Lactic acid measurement",
                "labels": ["Lactate", "Lactic acid measurement"],
                "score": 1.34,
                "match_type": "umls_label",
                "evidence_count": 10,
            },
            {
                "cui": "C0036690",
                "name": "Septicemia",
                "labels": ["Septicemia", "Sepsis"],
                "score": 1.06,
                "match_type": "umls_label",
                "evidence_count": 2,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0042397",
                "name": "Vasoconstrictor Agents",
                "labels": ["Vasopressor", "Vasoconstrictor Agents"],
                "score": 1.34,
                "match_type": "umls_label",
                "evidence_count": 8,
            },
            {
                "cui": "C0036983",
                "name": "Septic Shock",
                "labels": ["Septic Shock"],
                "score": 0.815,
                "evidence_count": 40,
                "semantic_types": [{"name": "Disease or Syndrome"}],
                "evidence_items": [
                    {
                        "text": (
                            "Septic shock management includes lactate measurement "
                            "and early vasopressor support."
                        )
                    }
                ],
            },
            {
                "cui": "C2938913",
                "name": "Distributive shock",
                "labels": ["Distributive shock"],
                "score": 0.815,
                "evidence_count": 4,
                "semantic_types": [{"name": "Pathologic Function"}],
                "evidence_items": [
                    {"text": "Distributive shock in sepsis requires early vasopressor support."}
                ],
            },
            {
                "cui": "C4285806",
                "name": "Clostridial sepsis",
                "labels": ["Clostridial sepsis"],
                "score": 0.831,
                "evidence_count": 1,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0022924",
                "name": "Lactates",
                "labels": ["Lactates", "lactate"],
                "score": 1.34,
                "match_type": "umls_label",
                "evidence_count": 0,
            },
            {
                "cui": "C0376261",
                "name": "lactate",
                "labels": ["lactate"],
                "score": 1.34,
                "match_type": "umls_label",
                "evidence_count": 0,
            },
        ],
        top_k=8,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    top_five = ordered_cuis[:5]
    assert ordered_cuis[0] == "C0036983"
    assert "C0036983" in ordered_cuis
    assert ordered_cuis.index("C2938913") < ordered_cuis.index("C0202115")
    assert ordered_cuis.index("C2938913") < ordered_cuis.index("C0042397")
    assert ordered_cuis.index("C2938913") < ordered_cuis.index("C4285806")
    assert "C0202115" not in top_five
    assert "C0042397" not in top_five
    septic_shock = next(hit for hit in ranked if hit["cui"] == "C0036983")
    distributive_shock = next(hit for hit in ranked if hit["cui"] == "C2938913")
    assert septic_shock["score_breakdown"]["evidence_context_component"] > 0
    assert septic_shock["score_breakdown"]["composite_intent_component"] > 0
    assert distributive_shock["score_breakdown"]["composite_intent_component"] >= 0.26
    lactate = next(hit for hit in ranked if hit["cui"] == "C0202115")
    assert lactate["score_breakdown"]["composite_component_penalty"] > 0
    vasopressor = next(hit for hit in ranked if hit["cui"] == "C0042397")
    assert vasopressor["score_breakdown"]["composite_component_penalty"] > 0
    clostridial = next(hit for hit in ranked if hit["cui"] == "C4285806")
    assert clostridial["score_breakdown"]["sepsis_subtype_penalty"] > 0


def test_query_ranker_keeps_explicit_sepsis_treatment_and_monitoring_anchors() -> None:
    ranked = rank_hits(
        "Septic shock required norepinephrine and lactate monitoring.",
        [
            {
                "cui": "C0036983",
                "name": "Septic Shock",
                "labels": ["Septic Shock"],
                "score": 0.82,
                "evidence_count": 40,
                "semantic_types": [{"name": "Disease or Syndrome"}],
                "evidence_items": [
                    {"text": "Septic shock management includes lactate and norepinephrine."}
                ],
            },
            {
                "cui": "C0202115",
                "name": "Lactic acid measurement",
                "labels": ["Lactate", "Lactic acid measurement"],
                "score": 1.34,
                "match_type": "umls_label",
                "matched_label": "Lactate",
                "matched_query_span": "lactate",
                "evidence_count": 26,
                "semantic_types": [{"name": "Laboratory Procedure"}],
            },
            {
                "cui": "C0028351",
                "name": "norepinephrine",
                "labels": ["norepinephrine"],
                "score": 1.34,
                "match_type": "umls_label",
                "matched_label": "norepinephrine",
                "matched_query_span": "norepinephrine",
                "matched_sab": "RXNORM",
                "matched_tty": "IN",
                "evidence_count": 0,
                "semantic_types": [{"name": "Pharmacologic Substance"}],
            },
            {
                "cui": "C0243026",
                "name": "Sepsis",
                "labels": ["Sepsis"],
                "score": 1.34,
                "match_type": "umls_label",
                "matched_label": "Sepsis",
                "matched_query_span": "septic",
                "evidence_count": 30,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0036974",
                "name": "Shock",
                "labels": ["Shock"],
                "score": 1.34,
                "match_type": "umls_label",
                "matched_label": "Shock",
                "matched_query_span": "shock",
                "evidence_count": 12,
                "semantic_types": [{"name": "Pathologic Function"}],
            },
        ],
        top_k=5,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert "C0202115" in ordered_cuis[:5]
    assert "C0028351" in ordered_cuis[:5]
    lactate = next(hit for hit in ranked if hit["cui"] == "C0202115")
    norepinephrine = next(hit for hit in ranked if hit["cui"] == "C0028351")
    assert lactate["score_breakdown"]["composite_component_penalty"] == 0.0
    assert norepinephrine["score_breakdown"]["composite_component_penalty"] == 0.0


def test_query_ranker_does_not_penalize_diabetic_foot_ulcer_as_generic_diabetes() -> None:
    ranked = rank_hits(
        "Poorly controlled type 2 diabetes mellitus with diabetic foot ulcer.",
        [
            {
                "cui": "C0011860",
                "name": "Diabetes Mellitus, Type 2",
                "labels": ["Diabetes Mellitus, Type 2"],
                "score": 0.82,
                "evidence_count": 50,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C1456868",
                "name": "Diabetic foot ulcer",
                "labels": [
                    "Diabetic foot ulcer",
                    "diabetes mellitus foot ulcer",
                ],
                "score": 0.70,
                "evidence_count": 20,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
        ],
        top_k=2,
    )

    diabetic_foot_ulcer = next(hit for hit in ranked if hit["cui"] == "C1456868")
    generic_diabetes = next(hit for hit in ranked if hit["cui"] == "C0011860")
    assert diabetic_foot_ulcer["score_breakdown"]["clinical_context_sense_penalty"] == 0.0
    assert generic_diabetes["score_breakdown"]["clinical_context_sense_penalty"] > 0
    assert ranked.index(diabetic_foot_ulcer) < ranked.index(generic_diabetes)


def test_query_ranker_demotes_laterality_only_fragments() -> None:
    ranked = rank_hits(
        "Sudden left sided weakness with persistent neurologic deficit.",
        [
            {
                "cui": "C3842774",
                "name": "Both left and right",
                "labels": ["Both left and right"],
                "score": 0.82,
                "evidence_count": 10,
                "semantic_types": [{"name": "Finding"}],
            },
            {
                "cui": "C0521654",
                "name": "Neurologic Deficits",
                "labels": ["neurologic deficit"],
                "score": 0.70,
                "evidence_count": 30,
                "semantic_types": [{"name": "Finding"}],
            },
            {
                "cui": "C0457436",
                "name": "Left hemiparesis",
                "labels": ["Left hemiparesis", "left sided weakness"],
                "score": 0.70,
                "evidence_count": 20,
                "semantic_types": [{"name": "Sign or Symptom"}],
            },
        ],
        top_k=3,
    )

    laterality = next(hit for hit in ranked if hit["cui"] == "C3842774")
    neurologic_deficit = next(hit for hit in ranked if hit["cui"] == "C0521654")
    left_hemiparesis = next(hit for hit in ranked if hit["cui"] == "C0457436")
    assert laterality["score_breakdown"]["semantic_fragment_penalty"] > 0
    assert ranked.index(neurologic_deficit) < ranked.index(laterality)
    assert ranked.index(left_hemiparesis) < ranked.index(laterality)


def test_query_ranker_demotes_drug_brand_fragments_without_drug_context() -> None:
    ranked = rank_hits(
        "Daytime somnolence with sleep apnea.",
        [
            {
                "cui": "C1654656",
                "name": "Daytime brand of acetaminophen/dextromethorphan/phenylephrine",
                "labels": ["Daytime brand of acetaminophen/dextromethorphan/phenylephrine"],
                "score": 0.82,
                "evidence_count": 8,
                "semantic_types": [{"name": "Clinical Drug"}],
            },
            {
                "cui": "C2219848",
                "name": "Daytime Somnolence",
                "labels": ["Daytime Somnolence"],
                "score": 0.70,
                "evidence_count": 20,
                "semantic_types": [{"name": "Sign or Symptom"}],
            },
        ],
        top_k=2,
    )

    brand = next(hit for hit in ranked if hit["cui"] == "C1654656")
    somnolence = next(hit for hit in ranked if hit["cui"] == "C2219848")
    assert brand["score_breakdown"]["clinical_context_sense_penalty"] > 0
    assert ranked.index(somnolence) < ranked.index(brand)


def test_query_ranker_demotes_vaccine_when_paragraph_is_about_infection() -> None:
    ranked = rank_hits(
        "During influenza season, the patient developed fever cough myalgia and a positive rapid test.",
        [
            {
                "cui": "C0021403",
                "name": "Influenza virus vaccine",
                "labels": ["Influenza virus vaccine", "Influenza vaccines"],
                "score": 1.0,
                "evidence_count": 40,
                "semantic_types": [{"name": "Pharmacologic Substance"}, {"name": "Immunologic Factor"}],
            },
            {
                "cui": "C0021400",
                "name": "Influenza",
                "labels": ["Influenza", "flu"],
                "score": 1.0,
                "evidence_count": 12,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
        ],
        top_k=2,
    )

    vaccine = next(hit for hit in ranked if hit["cui"] == "C0021403")
    assert vaccine["score_breakdown"]["clinical_context_sense_penalty"] > 0
    assert vaccine["score_breakdown"]["semantic_fragment_penalty"] > 0
    assert ranked[0]["cui"] == "C0021400"


def test_query_ranker_fills_with_matched_evidence_before_no_anchor_fallback() -> None:
    ranked = rank_hits(
        "asthma wheezing inhaled corticosteroid",
        [
            {
                "cui": "C0004096",
                "name": "Asthma",
                "labels": ["Asthma"],
                "score": 1.34,
                "match_type": "umls_label",
                "evidence_count": 40,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0001617",
                "name": "Adrenal Cortex Hormones",
                "labels": ["Corticosteroid", "Adrenal Cortex Hormones"],
                "score": 1.34,
                "match_type": "umls_label",
                "evidence_count": 34,
            },
            {
                "cui": "C0043144",
                "name": "Wheezing",
                "labels": ["Wheezing"],
                "score": 1.34,
                "match_type": "umls_label",
                "evidence_count": 0,
            },
            {
                "cui": "C2065042",
                "name": "inhaled beclomethasone",
                "labels": ["inhaled beclomethasone"],
                "score": 0.84,
                "evidence_count": 1,
            },
            {
                "cui": "C0264408",
                "name": "Childhood asthma",
                "labels": ["Childhood asthma"],
                "score": 0.80,
                "evidence_count": 53,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0543495",
                "name": "albuterol sulfate",
                "labels": ["albuterol sulfate"],
                "score": 0.84,
                "evidence_count": 5,
            },
        ],
        top_k=5,
    )

    ordered_cuis = [hit["cui"] for hit in ranked]
    assert "C0264408" in ordered_cuis
    assert "C0543495" not in ordered_cuis


def test_query_ranker_keeps_role_terms_when_the_specific_anchor_matches() -> None:
    ranked = rank_hits(
        "lactate measurement",
        [
            {
                "cui": "C0022948",
                "name": "Lactate measurement",
                "labels": ["Lactate measurement"],
                "score": 0.82,
                "evidence_count": 5,
                "semantic_types": [{"name": "Laboratory Procedure"}],
            },
            {
                "cui": "C0022947",
                "name": "Lactate dehydrogenase",
                "labels": ["Lactate dehydrogenase"],
                "score": 0.82,
                "evidence_count": 20,
                "semantic_types": [{"name": "Enzyme"}],
            },
            {
                "cui": "C0202057",
                "name": "Blood pressure measurement",
                "labels": ["Blood pressure measurement"],
                "score": 0.84,
                "evidence_count": 40,
                "semantic_types": [{"name": "Diagnostic Procedure"}],
            },
        ],
        top_k=3,
    )

    assert ranked[0]["cui"] == "C0022948"
    assert ranked[0]["score_breakdown"]["role_mismatch_penalty"] == 0.0
    assert ranked[-1]["cui"] == "C0202057"


def test_query_ranker_demotes_action_concept_for_observed_state_query() -> None:
    ranked = rank_hits(
        "No evidence of acute distress vital signs stable and within normal limits",
        [
            {
                "cui": "C0518766",
                "name": "Vital signs",
                "labels": ["Vital signs"],
                "score": 0.82,
                "evidence_count": 20,
                "semantic_types": [{"name": "Finding"}],
            },
            {
                "cui": "C0543467",
                "name": "Taking vital signs",
                "labels": ["Taking vital signs"],
                "score": 0.90,
                "evidence_count": 120,
                "semantic_types": [{"name": "Health Care Activity"}],
            },
            {
                "cui": "C0442807",
                "name": "Normal limits",
                "labels": ["Normal limits"],
                "score": 0.81,
                "evidence_count": 8,
                "semantic_types": [{"name": "Finding"}],
            },
        ],
        top_k=3,
    )

    ordered = [hit["cui"] for hit in ranked]
    assert ordered.index("C0518766") < ordered.index("C0543467")
    vital_signs = next(hit for hit in ranked if hit["cui"] == "C0518766")
    assert vital_signs["score_breakdown"]["denied_positive_finding_penalty"] == 0.0
    taking_vitals = next(hit for hit in ranked if hit["cui"] == "C0543467")
    assert taking_vitals["score_breakdown"]["action_observation_penalty"] > 0


def test_query_ranker_boosts_negated_findings_in_denial_context() -> None:
    ranked = rank_hits(
        "Denies nausea vomiting fever chills or recent unintentional weight loss",
        [
            {
                "cui": "C2363736",
                "name": "Unintentional weight loss",
                "labels": ["Unintentional weight loss"],
                "score": 1.175,
                "match_type": "umls_label",
                "evidence_count": 200,
            },
            {
                "cui": "C4528142",
                "name": "No Weight Loss",
                "labels": ["No Weight Loss"],
                "score": 0.833405,
                "evidence_count": 92,
            },
        ],
        top_k=2,
    )

    assert ranked[0]["cui"] == "C4528142"
    assert ranked[0]["score_breakdown"]["negated_finding_component"] > 0


def test_label_fallback_queries_add_negated_denial_spans() -> None:
    anchors = label_fallback_anchor_queries("denies chest pain shortness of breath fever")

    assert "denies" not in anchors
    assert "no chest pain" in anchors
    assert "no shortness of breath" in anchors

    scoped_anchors = label_fallback_anchor_queries("normal neurological exam no focal deficits")
    assert "no focal deficits" in scoped_anchors
    assert "no normal neurological exam" not in scoped_anchors


def test_label_fallback_queries_keep_denied_weight_loss_span() -> None:
    anchors = label_fallback_anchor_queries(
        "Denies nausea vomiting fever chills or recent unintentional weight loss"
    )

    assert "no weight loss" in anchors
    assert "weight loss absent" in anchors


def test_label_fallback_queries_expand_with_or_without_anchor() -> None:
    anchors = label_fallback_anchor_queries(
        "Status migrainosus is a complication of migraine with or without aura"
    )

    assert "migraine with aura" in anchors
    assert "migraine without aura" in anchors


def test_direct_query_span_matches_with_or_without_variants() -> None:
    query = "Status migrainosus is a complication of migraine with or without aura"

    with_aura = direct_query_span(query, "Migraine with Aura")
    without_aura = direct_query_span(query, "Migraine without Aura")

    assert with_aura is not None
    assert without_aura is not None
    assert with_aura[2] == "migraine with or without aura"
    assert without_aura[2] == "migraine with or without aura"


def test_with_or_without_phrase_is_not_denial_scope() -> None:
    tokens = normalized_key(
        "Status migrainosus is a complication of migraine with or without aura"
    ).split()

    assert denial_scope_token_lists(tokens) == []


def test_query_ranker_attaches_assertion_context_to_mentions() -> None:
    pe_ranked = rank_hits(
        "No evidence of pulmonary embolism on computed tomography angiography.",
        [
            {
                "cui": "C0034065",
                "name": "Pulmonary Embolism",
                "labels": ["Pulmonary Embolism"],
                "score": 1.1,
                "match_type": "umls_label",
                "matched_label": "Pulmonary Embolism",
                "matched_query_span": "pulmonary embolism",
                "evidence_count": 50,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            }
        ],
        top_k=1,
    )
    pe = pe_ranked[0]
    assert pe["assertion"]["status"] == "negated"
    assert pe["score_breakdown"]["denied_positive_finding_penalty"] > 0

    meningitis_ranked = rank_hits(
        "Rule out meningitis; lumbar puncture was ordered.",
        [
            {
                "cui": "C0025289",
                "name": "Meningitis",
                "labels": ["Meningitis"],
                "score": 1.0,
                "match_type": "umls_label",
                "matched_label": "Meningitis",
                "matched_query_span": "meningitis",
                "evidence_count": 30,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            }
        ],
        top_k=1,
    )
    meningitis = meningitis_ranked[0]
    assert meningitis["assertion"]["status"] == "uncertain"
    assert meningitis["score_breakdown"]["assertion_context_penalty"] > 0

    neurologic_ranked = rank_hits(
        "Prior stroke with current facial droop.",
        [
            {
                "cui": "C0038454",
                "name": "Stroke",
                "labels": ["Stroke"],
                "score": 1.0,
                "match_type": "umls_label",
                "matched_label": "Stroke",
                "matched_query_span": "stroke",
                "evidence_count": 30,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0427055",
                "name": "Facial droop",
                "labels": ["Facial droop"],
                "score": 0.96,
                "match_type": "umls_label",
                "matched_label": "Facial droop",
                "matched_query_span": "facial droop",
                "evidence_count": 30,
                "semantic_types": [{"name": "Sign or Symptom"}],
            },
        ],
        top_k=2,
    )
    stroke = next(hit for hit in neurologic_ranked if hit["cui"] == "C0038454")
    facial_droop = next(hit for hit in neurologic_ranked if hit["cui"] == "C0427055")
    assert stroke["assertion"]["status"] == "historical"
    assert stroke["score_breakdown"]["assertion_context_penalty"] > 0
    assert facial_droop["assertion"]["status"] == "current"
    assert facial_droop["score_breakdown"]["assertion_context_penalty"] == 0.0


def test_query_ranker_marks_planned_and_confirmed_assertions() -> None:
    planned_ranked = rank_hits(
        "Endoscopy was planned for melena.",
        [
            {
                "cui": "C0014245",
                "name": "Endoscopy",
                "labels": ["Endoscopy"],
                "score": 1.0,
                "match_type": "umls_label",
                "matched_label": "Endoscopy",
                "matched_query_span": "Endoscopy",
                "evidence_count": 30,
                "semantic_types": [{"name": "Diagnostic Procedure"}],
            }
        ],
        top_k=1,
    )
    endoscopy = planned_ranked[0]
    assert endoscopy["assertion"]["status"] == "planned"
    assert endoscopy["score_breakdown"]["assertion_context_penalty"] > 0

    confirmed_ranked = rank_hits(
        "Blood culture grew MRSA.",
        [
            {
                "cui": "C1265292",
                "name": "Methicillin-Resistant Staphylococcus aureus",
                "labels": ["MRSA", "Methicillin-Resistant Staphylococcus aureus"],
                "score": 1.0,
                "match_type": "umls_label",
                "matched_label": "MRSA",
                "matched_query_span": "MRSA",
                "evidence_count": 30,
                "semantic_types": [{"name": "Bacterium"}],
            }
        ],
        top_k=1,
    )
    mrsa = confirmed_ranked[0]
    assert mrsa["assertion"]["status"] == "confirmed"
    assert mrsa["score_breakdown"]["assertion_context_penalty"] == 0.0


def test_query_ranker_penalizes_positive_findings_in_denial_context() -> None:
    ranked = rank_hits(
        "denies chest pain shortness of breath fever",
        [
            {
                "cui": "C0008031",
                "name": "Chest Pain",
                "labels": ["Chest Pain"],
                "score": 1.18,
                "match_type": "umls_label",
                "evidence_count": 300,
                "semantic_types": [{"name": "Sign or Symptom"}],
            },
            {
                "cui": "C0013404",
                "name": "Dyspnea",
                "labels": ["Dyspnea", "Shortness of breath"],
                "score": 1.16,
                "match_type": "umls_label",
                "evidence_count": 280,
                "semantic_types": [{"name": "Sign or Symptom"}],
            },
            {
                "cui": "C4054349",
                "name": "No Shortness of Breath",
                "labels": ["No Shortness of Breath"],
                "score": 0.92,
                "match_type": "umls_label",
                "evidence_count": 10,
                "semantic_types": [{"name": "Finding"}],
            },
            {
                "cui": "C0015967",
                "name": "Fever",
                "labels": ["Fever"],
                "score": 1.12,
                "match_type": "umls_label",
                "evidence_count": 240,
                "semantic_types": [{"name": "Finding"}],
            },
            {
                "cui": "C0011311",
                "name": "Dengue Fever",
                "labels": ["Dengue Fever"],
                "score": 0.82,
                "evidence_count": 20,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
        ],
        top_k=5,
    )

    ordered = [hit["cui"] for hit in ranked]
    assert ordered[0] == "C4054349"
    no_shortness = ranked[0]
    chest_pain = next(hit for hit in ranked if hit["cui"] == "C0008031")
    dyspnea = next(hit for hit in ranked if hit["cui"] == "C0013404")
    dengue_fever = next(hit for hit in ranked if hit["cui"] == "C0011311")
    assert no_shortness["score_breakdown"]["negated_finding_component"] > 0
    assert chest_pain["score_breakdown"]["denied_positive_finding_penalty"] >= 0.5
    assert dyspnea["score_breakdown"]["denied_positive_finding_penalty"] >= 0.5
    assert dengue_fever["score_breakdown"]["denied_positive_finding_penalty"] >= 0.4
    assert chest_pain["score_breakdown"]["primary_name_component"] == 0.0
    assert chest_pain["score_breakdown"]["semantic_component"] == 0.0
    assert chest_pain["score_breakdown"]["specificity_component"] == 0.0
    assert dyspnea["score_breakdown"]["specificity_component"] == 0.0
    assert dengue_fever["score_breakdown"]["specificity_component"] == 0.0


def test_query_ranker_penalizes_denied_clinical_attribute_findings() -> None:
    ranked = rank_hits(
        "denies chest pain shortness of breath fever",
        [
            {
                "cui": "C2926613",
                "name": "Chest pain:Find:Pt:^Patient:Ord",
                "labels": ["Chest pain", "Chest pain:Finding:To identify measures at a point in time:^Patient:Ordinal"],
                "score": 1.1,
                "evidence_count": 100,
                "semantic_types": [{"name": "Clinical Attribute"}],
            },
            {
                "cui": "C4054349",
                "name": "No Shortness of Breath",
                "labels": ["No Shortness of Breath"],
                "score": 0.92,
                "evidence_count": 10,
                "semantic_types": [{"name": "Finding"}],
            },
        ],
        top_k=2,
    )

    observed_chest_pain = next(hit for hit in ranked if hit["cui"] == "C2926613")
    assert observed_chest_pain["score_breakdown"]["denied_positive_finding_penalty"] >= 0.5
    assert observed_chest_pain["score_breakdown"]["specificity_component"] == 0.0


def test_query_ranker_demotes_nonfinding_concepts_matching_denied_context() -> None:
    ranked = rank_hits(
        "denies chest pain shortness of breath fever",
        [
            {
                "cui": "C0451615",
                "name": "Pain relief",
                "labels": ["Pain relief", "Pain relief (procedure)"],
                "score": 0.82,
                "evidence_count": 20,
                "semantic_types": [{"name": "Therapeutic or Preventive Procedure"}],
            },
            {
                "cui": "C2926613",
                "name": "Chest pain:Find:Pt:^Patient:Ord",
                "labels": ["Chest pain"],
                "score": 0.82,
                "evidence_count": 20,
                "semantic_types": [{"name": "Clinical Attribute"}],
            },
            {
                "cui": "C0848168",
                "name": "No chest pain",
                "labels": ["No chest pain"],
                "score": 0.82,
                "evidence_count": 1,
                "semantic_types": [{"name": "Finding"}],
            },
        ],
        top_k=3,
    )

    pain_relief = next(hit for hit in ranked if hit["cui"] == "C0451615")
    chest_pain = next(hit for hit in ranked if hit["cui"] == "C2926613")
    no_chest_pain = next(hit for hit in ranked if hit["cui"] == "C0848168")
    assert pain_relief["score_breakdown"]["denied_context_mismatch_penalty"] > 0
    assert chest_pain["score_breakdown"]["denied_context_mismatch_penalty"] == 0.0
    assert no_chest_pain["score_breakdown"]["denied_context_mismatch_penalty"] == 0.0
    assert ranked.index(no_chest_pain) < ranked.index(pain_relief)


def test_query_ranker_scopes_denial_penalty_to_negated_phrase() -> None:
    ranked = rank_hits(
        "Neurological exam normal cranial nerves intact no focal deficits observed",
        [
            {
                "cui": "C3266627",
                "name": "Normal cranial nerves",
                "labels": ["Normal cranial nerves"],
                "score": 1.18,
                "match_type": "umls_label",
                "evidence_count": 25,
                "semantic_types": [{"name": "Finding"}],
            },
            {
                "cui": "C0746857",
                "name": "Focal Neurologic Deficits",
                "labels": ["Focal Neurologic Deficits"],
                "score": 1.10,
                "match_type": "umls_label",
                "evidence_count": 20,
                "semantic_types": [{"name": "Finding"}],
            },
        ],
        top_k=2,
    )

    normal_cranial = next(hit for hit in ranked if hit["cui"] == "C3266627")
    focal_deficits = next(hit for hit in ranked if hit["cui"] == "C0746857")
    assert normal_cranial["score_breakdown"]["denied_positive_finding_penalty"] == 0.0
    assert focal_deficits["score_breakdown"]["denied_positive_finding_penalty"] >= 0.5


def test_query_ranker_demotes_physical_exam_boilerplate_fragments() -> None:
    ranked = rank_hits(
        (
            "On physical exam, the patient is alert and oriented to person, place, and time. "
            "Heart sounds are regular without murmurs, and lungs are clear to auscultation "
            "bilaterally. No peripheral edema noted."
        ),
        [
            {
                "cui": "C4050434",
                "name": "Heart sounds:Find:Pt:Heart:Nom",
                "labels": ["Heart sounds", "Heart sounds:Find:Pt:Heart:Nom"],
                "score": 1.0,
                "evidence_count": 20,
                "semantic_types": [{"name": "Clinical Attribute"}],
            },
            {
                "cui": "C0018799",
                "name": "Heart Diseases",
                "labels": ["Heart Diseases"],
                "score": 1.0,
                "evidence_count": 20,
                "semantic_types": [{"name": "Disease or Syndrome"}],
            },
            {
                "cui": "C0024121",
                "name": "Lung Neoplasms",
                "labels": ["Lung Neoplasms"],
                "score": 1.0,
                "evidence_count": 20,
                "semantic_types": [{"name": "Neoplastic Process"}],
            },
            {
                "cui": "C5381944",
                "name": "No time",
                "labels": ["No time"],
                "score": 1.0,
                "evidence_count": 20,
                "semantic_types": [{"name": "Finding"}],
            },
            {
                "cui": "C5444207",
                "name": "In Person",
                "labels": ["In Person"],
                "score": 1.0,
                "evidence_count": 20,
                "semantic_types": [{"name": "Qualitative Concept"}],
            },
            {
                "cui": "C2243091",
                "name": "regular exercise (treatment)",
                "labels": ["regular exercise"],
                "score": 1.0,
                "evidence_count": 20,
                "semantic_types": [{"name": "Therapeutic or Preventive Procedure"}],
            },
            {
                "cui": "C2230284",
                "name": "auscultation of heart sounds",
                "labels": ["auscultation of heart sounds"],
                "score": 1.0,
                "evidence_count": 20,
                "semantic_types": [{"name": "Diagnostic Procedure"}],
            },
        ],
        top_k=7,
    )

    ordered = [hit["cui"] for hit in ranked]
    assert ordered.index("C4050434") < ordered.index("C0018799")
    assert ordered.index("C4050434") < ordered.index("C0024121")
    heart_disease = next(hit for hit in ranked if hit["cui"] == "C0018799")
    lung_neoplasm = next(hit for hit in ranked if hit["cui"] == "C0024121")
    no_time = next(hit for hit in ranked if hit["cui"] == "C5381944")
    in_person = next(hit for hit in ranked if hit["cui"] == "C5444207")
    regular_exercise = next(hit for hit in ranked if hit["cui"] == "C2243091")
    auscultation = next(hit for hit in ranked if hit["cui"] == "C2230284")
    assert heart_disease["score_breakdown"]["normal_exam_fragment_penalty"] > 0
    assert lung_neoplasm["score_breakdown"]["normal_exam_fragment_penalty"] > 0
    assert no_time["score_breakdown"]["generic_penalty"] > 0
    assert in_person["score_breakdown"]["generic_penalty"] > 0
    assert regular_exercise["score_breakdown"]["generic_fragment_penalty"] > 0
    assert auscultation["score_breakdown"]["denied_context_mismatch_penalty"] == 0.0


def test_source_mix_summarizes_visible_evidence_sources() -> None:
    mix = source_mix_from_evidence_items(
        [
            {
                "text": "patient with chest pain",
                "sources": [
                    {"source": "pubmed", "label": "PubMed PMID:1"},
                    {"source": "pmc_oa", "label": "PMC OA PMC1"},
                ],
            },
            {
                "text": "clinical note chest pain",
                "sources": [{"source": "mimic_iv_note_discharge", "label": "MIMIC note"}],
            },
        ],
        declared_sources=["pubmed", "pmc_oa", "mimic_iv_note_discharge", "europepmc"],
        evidence_count=12,
    )

    counts = {item["source"]: item["sample_refs"] for item in mix["items"]}
    assert mix["sample_refs"] == 3
    assert mix["evidence_count"] == 12
    assert counts["pubmed"] == 1
    assert counts["pmc_oa"] == 1
    assert counts["mimic_iv_note_discharge"] == 1
    assert counts["europepmc"] == 0


def test_evaluate_search_api_reads_query_tsv_and_summarizes_payload(tmp_path: Path) -> None:
    queries = tmp_path / "queries.tsv"
    queries.write_text(
        "id\tquery\texpected_cuis\twhy\tdisallowed_cuis\n"
        "chest\tchest pain on exertion\tC0232288|C2926613\tSpecific symptom\tC0000001|C0000002\n",
        encoding="utf-8",
    )
    specs = read_query_specs(queries)
    row = summarize_search_response(
        specs[0],
        {
            "hits": [
                {
                    "cui": "C0232288",
                    "name": "Chest pain on exertion",
                    "rank_score": 1.2,
                    "score": 0.83,
                    "semantic_types": [{"name": "Sign or Symptom", "tui": "T184"}],
                    "source_mix": {"items": [{"source": "mimic_iv_note_discharge", "sample_refs": 2}]},
                    "score_breakdown": {
                        "lexical_component": 0.95,
                        "vector_component": 0.07,
                        "evidence_component": 0.04,
                        "specificity_component": 0.12,
                    },
                }
            ]
        },
        show_hits=3,
    )

    assert specs == [
        QuerySpec(
            query_id="chest",
            query="chest pain on exertion",
            expected_cuis=["C0232288", "C2926613"],
            disallowed_cuis=["C0000001", "C0000002"],
            why="Specific symptom",
        )
    ]
    assert row["expected_rank"] == "1"
    assert row["top_cui"] == "C0232288"
    assert row["top_semantic_types"] == "Sign or Symptom T184"
    assert row["top_sources"] == "mimic_iv_note_discharge:2"


def test_paragraph_evaluator_counts_acceptable_cui_alternatives(tmp_path: Path) -> None:
    alternatives_path = tmp_path / "alternatives.tsv"
    alternatives_path.write_text(
        "expected_cui\tacceptable_cui\tlabel\twhy\n"
        "C0004096\tC0349790\tExacerbation of asthma\tMore specific asthma concept\n"
        "C0035473\tC0276447\tRhinovirus infection\tClinically acceptable infection concept\n",
        encoding="utf-8",
    )
    alternatives = read_acceptable_alternatives(alternatives_path)
    spec = QuerySpec(
        query_id="asthma",
        query="Asthma exacerbation triggered by rhinovirus.",
        expected_cuis=["C0004096", "C0035473"],
    )

    row = judge_paragraph_quality(
        spec,
        [
            {
                "cui": "C0349790",
                "name": "Exacerbation of asthma",
                "semantic_group": "DISO",
                "rank_score": 1.7,
            },
            {
                "cui": "C0276447",
                "name": "Rhinovirus infection",
                "semantic_group": "DISO",
                "rank_score": 1.3,
            },
        ],
        acceptable_alternatives=alternatives,
    )

    assert row["found_at_10"] == 2
    assert row["missing_at_10"] == ""
    assert row["accepted_alternatives_at_10"] == "C0004096=C0349790|C0035473=C0276447"
    assert row["verdict"] == "good"


def test_paragraph_evaluator_flags_configured_false_positives() -> None:
    spec = QuerySpec(
        query_id="antibiotic_diarrhea",
        query="He reports watery diarrhea after recent antibiotic use.",
        expected_cuis=["C0578159", "C0011991", "C0003232"],
        disallowed_cuis=["C0003392"],
    )

    row = judge_paragraph_quality(
        spec,
        [
            {
                "cui": "C0578159",
                "name": "Antibiotic-associated diarrhea",
                "semantic_group": "DISO",
                "rank_score": 1.7,
            },
            {
                "cui": "C0011991",
                "name": "Diarrhea",
                "semantic_group": "DISO",
                "rank_score": 1.6,
            },
            {
                "cui": "C0003232",
                "name": "Antibiotics",
                "semantic_group": "CHEM",
                "rank_score": 1.5,
            },
            {
                "cui": "C0003392",
                "name": "Antineoplastic Agents",
                "semantic_group": "CHEM",
                "rank_score": 1.4,
            },
        ],
    )

    assert row["disallowed_at_10"] == "C0003392"
    assert row["verdict"] == "mixed"


def test_paragraph_precision_audit_excludes_configured_useful_extras(tmp_path: Path) -> None:
    queries_path = tmp_path / "queries.tsv"
    queries_path.write_text(
        "id\tquery\texpected_cuis\twhy\n"
        "heart_failure\tHeart failure with leg edema.\tC0018801\tCore disease\n",
        encoding="utf-8",
    )
    payloads_path = tmp_path / "payloads.jsonl"
    payloads_path.write_text(
        json.dumps(
            {
                "id": "heart_failure",
                "query": "Heart failure with leg edema.",
                "response": {
                    "hits": [
                        {
                            "cui": "C0235886",
                            "name": "Leg edema",
                            "semantic_group": "DISO",
                            "semantic_types": [{"name": "Pathologic Function"}],
                            "rank_score": 1.6,
                            "matched_label": "Leg edema",
                            "matched_query_span": "leg edema",
                        },
                        {
                            "cui": "C0018801",
                            "name": "Heart failure",
                            "semantic_group": "DISO",
                            "semantic_types": [{"name": "Disease or Syndrome"}],
                            "rank_score": 1.5,
                            "matched_label": "Heart failure",
                            "matched_query_span": "heart failure",
                        },
                    ]
                },
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    useful_extras_path = tmp_path / "useful_extras.tsv"
    useful_extras_path.write_text(
        "id\tcui\tlabel\twhy\n"
        "heart_failure\tC0235886\tLeg edema\tExplicit useful extra finding\n",
        encoding="utf-8",
    )

    assert read_useful_extra_cuis(useful_extras_path) == {"heart_failure": {"C0235886"}}
    rows, metrics = audit_paragraph_precision_payloads(
        query_path=queries_path,
        payload_path=payloads_path,
        alternatives_path=tmp_path / "missing_alternatives.tsv",
        useful_extras_path=useful_extras_path,
        top_n=2,
    )

    assert rows == []
    assert metrics["nonexpected_top_n_hits"] == 1
    assert metrics["useful_extra_top_n_hits"] == 1
    assert metrics["suspect_top_n_hits"] == 0


def test_search_index_resolves_cui_and_code_before_ann(tmp_path: Path) -> None:
    mrconso = tmp_path / "MRCONSO.RRF"
    mrsty = tmp_path / "MRSTY.RRF"
    mrconso.write_text(
        "C0004238|ENG|P|L1|PF|S1|Y|A1||SCUI1|SDUI1|ICD10CM|PT|I48.91|Unspecified atrial fibrillation|0|N||\n"
        "C0004238|ENG|S|L2|PF|S2|Y|A2||SCUI2|SDUI2|MSH|MH|D001281|Atrial Fibrillation|0|N||\n",
        encoding="utf-8",
    )
    mrsty.write_text(
        "C0004238|T047|B2.2.1.2.1|Disease or Syndrome|AT1|\n",
        encoding="utf-8",
    )
    code_index = tmp_path / "cui_code_index.sqlite"
    semantic_type_index = tmp_path / "semantic_types.sqlite"
    build_code_index(mrconso_path=mrconso, out_path=code_index, replace=True)
    build_semantic_type_index(mrsty_path=mrsty, out_path=semantic_type_index, replace=True)
    documents = build_documents(
        [EvidenceRecord("e1", "C0004238", "patient with a fib", "notes", "clinical_snippet", 2)]
    )
    vectors = embed_documents(documents, HashingEmbedder(dim=16))
    docs_path = tmp_path / "docs.jsonl"
    vectors_path = tmp_path / "vectors.jsonl"
    write_jsonl(docs_path, documents)
    write_jsonl(vectors_path, vectors)

    index = SearchIndex(
        vector_paths=[vectors_path],
        doc_paths=[docs_path],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        code_index_path=code_index,
        semantic_type_index_path=semantic_type_index,
    )
    cui_result = index.search("C0004238", top_k=5)
    code_result = index.search("ICD10:I48.91", top_k=5)

    assert cui_result["backend"] == "resolver"
    assert cui_result["hits"][0]["cui"] == "C0004238"
    assert cui_result["hits"][0]["name"] == "Unspecified atrial fibrillation"
    assert cui_result["hits"][0]["evidence_count"] == 1
    assert cui_result["hits"][0]["semantic_types"][0]["name"] == "Disease or Syndrome"
    assert code_result["backend"] == "resolver"
    assert code_result["input_type"] == "system_code"
    assert code_result["hits"][0]["cui"] == "C0004238"
    assert code_result["hits"][0]["mappings"][0]["code"] == "I48.91"


def test_search_index_falls_back_to_local_vectors_when_elasticsearch_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    documents = build_documents(
        [EvidenceRecord("e1", "C0004238", "atrial fibrillation anticoagulation", "notes", "clinical_snippet", 2)]
    )
    docs_path = tmp_path / "docs.jsonl"
    vectors_path = tmp_path / "vectors.jsonl"
    write_jsonl(docs_path, documents)
    write_jsonl(vectors_path, embed_documents(documents, HashingEmbedder(dim=16)))

    def fail_search_knn(*args, **kwargs):
        raise OSError("elasticsearch down")

    monkeypatch.setattr(search_quality_server, "search_knn", fail_search_knn)
    index = SearchIndex(
        vector_paths=[vectors_path],
        doc_paths=[docs_path],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        elastic_url="http://localhost:9200",
        elastic_index="missing-index",
    )
    result = index.search("atrial fibrillation", top_k=1)

    assert result["backend"] == "local_fallback"
    assert result["requested_backend"] == "elasticsearch"
    assert "elasticsearch unavailable" in result["fallback_reason"]
    assert result["hits"][0]["cui"] == "C0004238"


def test_code_resolution_adds_evidence_bearing_label_broadened_candidate(tmp_path: Path) -> None:
    mrconso = tmp_path / "MRCONSO.RRF"
    mrconso.write_text(
        "C3264374|ENG|P|L1|PF|S1|Y|A1||SCUI1|SDUI1|ICD10CM|PT|I48.91|Unspecified atrial fibrillation|0|N||\n"
        "C0004238|ENG|P|L2|PF|S2|Y|A2||SCUI2|SDUI2|MSH|MH|D001281|Atrial Fibrillation|0|N||\n"
        "C0205370|ENG|P|L3|PF|S3|Y|A3||SCUI3|SDUI3|MTH|PT|NOCODE|Unspecified|0|N||\n",
        encoding="utf-8",
    )
    code_index = tmp_path / "cui_code_index.sqlite"
    label_index = tmp_path / "labels.sqlite"
    build_code_index(mrconso_path=mrconso, out_path=code_index, replace=True)
    build_label_index(
        mrconso_path=mrconso,
        out_path=label_index,
        min_tokens=1,
        replace=True,
    )
    documents = build_documents(
        [
            EvidenceRecord(
                "e1",
                "C0004238",
                "atrial fibrillation anticoagulation",
                "pubmed",
                "pubmed_clinical_context",
                2,
            ),
            EvidenceRecord(
                "e2",
                "C0205370",
                "unspecified qualifier",
                "pubmed",
                "pubmed_clinical_context",
                2,
            )
        ],
        mrconso_path=mrconso,
    )
    docs_path = tmp_path / "docs.jsonl"
    vectors_path = tmp_path / "vectors.jsonl"
    write_jsonl(docs_path, documents)
    write_jsonl(vectors_path, embed_documents(documents, HashingEmbedder(dim=16)))

    index = SearchIndex(
        vector_paths=[vectors_path],
        doc_paths=[docs_path],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        code_index_path=code_index,
        label_index_paths=[label_index],
    )
    resolution = index.resolve("ICD10CM:I48.91", limit=5)
    result = index.search("ICD10CM:I48.91", top_k=5)

    assert resolution["candidates"][0]["cui"] == "C3264374"
    assert resolution["candidates"][0]["has_evidence"] is False
    assert resolution["candidates"][1]["cui"] == "C0004238"
    assert resolution["candidates"][1]["source"] == "system_code_label_broadened"
    assert resolution["candidates"][1]["has_evidence"] is True
    assert resolution["candidates"][1]["broadened_from_cui"] == "C3264374"
    assert "C0205370" not in [candidate["cui"] for candidate in resolution["candidates"]]
    assert result["hits"][1]["cui"] == "C0004238"
    assert result["hits"][1]["broadened_from_label"] == "Unspecified atrial fibrillation"
    assert result["hits"][1]["evidence_count"] == 1


def test_label_fallback_hydrates_with_best_evidence_document(tmp_path: Path) -> None:
    mrconso = tmp_path / "MRCONSO.RRF"
    mrsty = tmp_path / "MRSTY.RRF"
    mrconso.write_text(
        "C0003611|ENG|P|L1|PF|S1|Y|A1|||D001|MSH|MH|D001|Appendectomy|0|N||\n",
        encoding="utf-8",
    )
    mrsty.write_text(
        "C0003611|T061|A1.4.1.2.1|Therapeutic or Preventive Procedure|AT1|\n",
        encoding="utf-8",
    )
    label_index = tmp_path / "labels.sqlite"
    build_label_index(
        mrconso_path=mrconso,
        mrsty_path=mrsty,
        semantic_profiles=["procedures-devices"],
        out_path=label_index,
        min_tokens=1,
        replace=True,
    )
    documents = build_documents(
        [EvidenceRecord("e1", "C0003611", "appendectomy for acute appendicitis", "pubmed", "pubmed_procedures_context", 3)]
    )
    vectors = embed_documents(documents, HashingEmbedder(dim=16))
    docs_path = tmp_path / "docs.jsonl"
    vectors_path = tmp_path / "vectors.jsonl"
    write_jsonl(docs_path, documents)
    write_jsonl(vectors_path, vectors)
    index = SearchIndex(
        vector_paths=[vectors_path],
        doc_paths=[docs_path],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        label_index_paths=[label_index],
    )
    result = index.search("appendectomy surgical procedure", top_k=5)

    assert result["hits"][0]["cui"] == "C0003611"
    assert result["hits"][0]["match_type"] == "umls_label"
    assert result["hits"][0]["evidence_count"] == 1
    assert result["hits"][0]["view"] == "pubmed_procedures_context"
    assert result["hits"][0]["evidence_items"][0]["text"] == "appendectomy for acute appendicitis"


def test_wikipedia_enrichment_builds_document_with_source_relations() -> None:
    documents = build_wikipedia_documents(
        [
            {
                "cui": "C4508938",
                "title": "Oliceridine",
                "url": "https://en.wikipedia.org/wiki/Oliceridine",
                "accessed": "2026-05-07",
                "labels": ["oliceridine", "Olinvyk"],
                "summary": "Oliceridine is an intravenous opioid analgesic.",
                "evidence": ["Oliceridine is used for acute pain by intravenous injection."],
                "relations": [
                    {
                        "cui": "C0184567",
                        "label": "Acute onset pain",
                        "category": "condition",
                        "relation_group": "treatment",
                        "relation": "indicated_for",
                    }
                ],
            }
        ]
    )

    document = documents[0]
    assert document.doc_id == "C4508938:wikipedia_summary"
    assert document.sources == ["wikipedia"]
    assert document.evidence_count == 1
    assert document.metadata["source_url"] == "https://en.wikipedia.org/wiki/Oliceridine"
    assert document.metadata["relations"][0]["cui"] == "C0184567"
    assert "Open literature evidence:" in document.text


def test_open_image_document_metadata_surfaces_on_main_hit(tmp_path: Path) -> None:
    target = ConceptImageTarget(cui="C0149931", labels=("Migraine Disorders", "migraine"))
    image = {
        "source": "wikimedia_commons",
        "title": "File:Migraine.jpg",
        "source_url": "https://commons.wikimedia.org/wiki/File:Migraine.jpg",
        "image_url": "https://upload.wikimedia.org/wikipedia/commons/example/Migraine.jpg",
        "thumbnail_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/example/Migraine.jpg",
        "mime": "image/jpeg",
        "width": 640,
        "height": 480,
        "license": "CC BY-SA 4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "attribution": "Example photographer",
        "source_kind": "wikidata_p18",
    }
    image_document = build_open_image_documents(
        [target],
        images_by_cui={"C0149931": [image]},
    )[0]
    main_document = ConceptDocument(
        doc_id="C0149931:pubmed_clinical_context",
        cui="C0149931",
        view="pubmed_clinical_context",
        text=(
            "CUI: C0149931\n"
            "Evidence view: pubmed_clinical_context\n"
            "UMLS labels:\n"
            "- Migraine Disorders\n"
            "Real-world evidence:\n"
            "- Migraine causes headache and photophobia. (weight 1)\n"
            "- Migraine may respond to triptan therapy. (weight 1)"
        ),
        evidence_count=2,
        sources=["pubmed"],
        labels=["Migraine Disorders"],
    )
    documents = [main_document, image_document]
    docs_path = tmp_path / "docs.jsonl"
    vectors_path = tmp_path / "vectors.jsonl"
    write_jsonl(docs_path, documents)
    write_jsonl(
        vectors_path,
        embed_documents(documents, HashingEmbedder(dim=16), include_document_metadata=True),
    )
    index = SearchIndex(
        vector_paths=[vectors_path],
        doc_paths=[docs_path],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
    )

    hit = index.hit_from_record(index.best_record_for_cui("C0149931"), score=1.0)

    assert hit["doc_id"] == "C0149931:pubmed_clinical_context"
    assert hit["images"][0]["title"] == "File:Migraine.jpg"
    assert hit["images"][0]["license"] == "CC BY-SA 4.0"
    assert "Open-license images:" in image_document.text


def test_open_image_license_and_match_filtering() -> None:
    assert is_open_license({"license": "CC BY-SA 4.0"})
    assert is_open_license({"license": "Public domain"})
    assert not is_open_license({"license": "Fair use"})
    assert image_match_score(
        ["sumatriptan"],
        {"title": "File:Sumatriptan structure.svg", "description": ""},
    ) >= 0.78
    assert image_match_score(
        ["heart failure"],
        {"title": "File:Heart failure diagram.jpg", "description": ""},
    ) >= 0.78
    assert image_match_score(
        ["heart failure"],
        {"title": "File:Healthy kidney.jpg", "description": ""},
    ) < 0.78


def test_drug_enrichment_builds_mapping_and_literature_document(tmp_path: Path) -> None:
    mrconso = tmp_path / "MRCONSO.RRF"
    code_index_path = tmp_path / "codes.sqlite"
    corpus_path = tmp_path / "corpus.jsonl"
    mrconso.write_text(
        "C4508938|ENG|P|L1|PF|S1|Y|A1|||2392230|RXNORM|IN|2392230|oliceridine|0|N||\n"
        "C4508938|ENG|S|L2|PF|S2|N|A2|||DB14881|DRUGBANK|IN|DB14881|Oliceridine|0|N||\n"
        "C4508938|ENG|S|L3|PF|S3|N|A3|||N02AX07|ATC|IN|N02AX07|oliceridine|0|N||\n",
        encoding="utf-8",
    )
    build_code_index(mrconso_path=mrconso, out_path=code_index_path, replace=True)
    write_jsonl(
        corpus_path,
        [
            {
                "doc_id": "PMID:1",
                "source": "pubmed_bulk",
                "title": "Oliceridine after surgery",
                "text": (
                    "Oliceridine after surgery. Oliceridine reduced postoperative pain "
                    "scores without increasing respiratory adverse reactions."
                ),
                "metadata": {
                    "pmid": "1",
                    "doi": "10.1000/test",
                    "publication_year": "2026",
                    "publication_types": ["Clinical Trial", "Journal Article"],
                },
            }
        ],
    )

    documents = build_drug_enrichment_documents(
        target_cuis=["C4508938"],
        code_index_path=code_index_path,
        corpus_paths=[corpus_path],
        max_mentions_per_cui=10,
    )

    assert len(documents) == 1
    document = documents[0]
    assert document.doc_id == "C4508938:drug_enrichment"
    assert document.view == "drug_enrichment"
    assert document.evidence_count == 1
    assert document.labels[0] == "oliceridine"
    assert {row["sab"] for row in document.metadata["mappings"]} == {
        "ATC",
        "DRUGBANK",
        "RXNORM",
    }
    assert document.metadata["mention_sources"][0]["pmid"] == "1"
    assert "Open literature evidence:" in document.text
    assert "PMID:1" in document.text

    docs_path = tmp_path / "drug_docs.jsonl"
    vectors_path = tmp_path / "drug_vectors.jsonl"
    write_jsonl(docs_path, documents)
    write_jsonl(
        vectors_path,
        embed_documents(documents, HashingEmbedder(dim=16), include_document_metadata=True),
    )
    index = SearchIndex(
        vector_paths=[vectors_path],
        doc_paths=[docs_path],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
    )
    hit = index.hit_from_record(index.best_record_for_cui("C4508938"), score=1.0)
    assert hit["evidence_items"][0]["sources"][0]["pmid"] == "1"


def test_drug_enrichment_extracts_literature_relation_metadata(tmp_path: Path) -> None:
    targets_path = tmp_path / "targets.txt"
    mrconso = tmp_path / "MRCONSO.RRF"
    code_index_path = tmp_path / "codes.sqlite"
    corpus_path = tmp_path / "corpus.jsonl"
    targets_path.write_text("C0025598  metformin|Glucophage\n", encoding="utf-8")
    mrconso.write_text(
        "C0025598|ENG|P|L1|PF|S1|Y|A1|||6809|RXNORM|IN|6809|metformin|0|N||\n"
        "C0025598|ENG|S|L2|PF|S2|N|A2|||DB00331|DRUGBANK|IN|DB00331|Metformin|0|N||\n",
        encoding="utf-8",
    )
    build_code_index(mrconso_path=mrconso, out_path=code_index_path, replace=True)
    write_jsonl(
        corpus_path,
        [
            {
                "doc_id": "PMID:2",
                "source": "pubmed_bulk",
                "title": "Glucophage and type 2 diabetes mellitus",
                "text": (
                    "Glucophage therapy is used for type 2 diabetes mellitus "
                    "and improves glycemic control as measured by HbA1c."
                ),
                "metadata": {"pmid": "2", "publication_year": "2025"},
            }
        ],
    )

    specs = load_drug_target_specs(targets_path)
    documents = build_drug_enrichment_documents(
        target_cuis=[spec.cui for spec in specs],
        target_aliases_by_cui={spec.cui: spec.aliases for spec in specs},
        code_index_path=code_index_path,
        corpus_paths=[corpus_path],
        max_mentions_per_cui=10,
    )

    assert len(documents) == 1
    document = documents[0]
    assert "Glucophage" in document.labels
    assert "Literature-derived CUI relationships:" in document.text
    relation_targets = {row["cui"]: row for row in document.metadata["relations"]}
    assert relation_targets["C0011860"]["relation"] == "indicated_for"
    assert relation_targets["C0011860"]["supporting_pmids"] == ["2"]
    assert relation_targets["C5392125"]["relation"] == "affects"

    docs_path = tmp_path / "drug_docs.jsonl"
    vectors_path = tmp_path / "drug_vectors.jsonl"
    write_jsonl(docs_path, documents)
    write_jsonl(
        vectors_path,
        embed_documents(documents, HashingEmbedder(dim=16), include_document_metadata=True),
    )
    index = SearchIndex(
        vector_paths=[vectors_path],
        doc_paths=[docs_path],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
    )
    relations = index.research_relations_for_cui("C0025598")
    diabetes_relation = next(row for row in relations if row["cui"] == "C0011860")
    assert diabetes_relation["source"] == "local_literature"
    assert diabetes_relation["support_count"] == 1


def test_drug_enrichment_extracts_sumatriptan_migraine_relation(tmp_path: Path) -> None:
    mrconso = tmp_path / "MRCONSO.RRF"
    code_index_path = tmp_path / "codes.sqlite"
    corpus_path = tmp_path / "corpus.jsonl"
    mrconso.write_text(
        "C0075632|ENG|P|L1|PF|S1|Y|A1|||37418|RXNORM|IN|37418|sumatriptan|0|N||\n"
        "C0075632|ENG|S|L2|PF|S2|N|A2|||DB00669|DRUGBANK|IN|DB00669|Sumatriptan|0|N||\n",
        encoding="utf-8",
    )
    build_code_index(mrconso_path=mrconso, out_path=code_index_path, replace=True)
    write_jsonl(
        corpus_path,
        [
            {
                "doc_id": "PMID:3",
                "source": "pubmed_bulk",
                "title": "Sumatriptan for acute migraine",
                "text": (
                    "Sumatriptan is a triptan used for acute migraine headache "
                    "and is also studied in cluster headache."
                ),
                "metadata": {"pmid": "3", "publication_year": "2025"},
            }
        ],
    )

    documents = build_drug_enrichment_documents(
        target_cuis=["C0075632"],
        target_aliases_by_cui={"C0075632": ["Imitrex"]},
        code_index_path=code_index_path,
        corpus_paths=[corpus_path],
        max_mentions_per_cui=10,
    )

    assert len(documents) == 1
    relation_targets = {row["cui"]: row for row in documents[0].metadata["relations"]}
    assert relation_targets["C0149931"]["relation"] == "indicated_for"
    assert relation_targets["C0149931"]["supporting_pmids"] == ["3"]
    assert relation_targets["C1567966"]["relation"] == "has_drug_class"
    assert relation_targets["C0009088"]["relation"] == "used_for"


def test_drug_enrichment_skips_ehr_like_corpus_sources(tmp_path: Path) -> None:
    mrconso = tmp_path / "MRCONSO.RRF"
    code_index_path = tmp_path / "codes.sqlite"
    open_corpus_path = tmp_path / "pubmed_corpus.jsonl"
    ehr_corpus_path = tmp_path / "mimic_demo_corpus.jsonl"
    mrconso.write_text(
        "C1831808|ENG|P|L1|PF|S1|Y|A1|||1012554|RXNORM|IN|1012554|apixaban|0|N||\n",
        encoding="utf-8",
    )
    build_code_index(mrconso_path=mrconso, out_path=code_index_path, replace=True)
    write_jsonl(
        open_corpus_path,
        [
            {
                "doc_id": "PMID:4",
                "source": "pubmed_bulk",
                "title": "Apixaban and atrial fibrillation",
                "text": "Apixaban is an anticoagulant used for atrial fibrillation.",
                "metadata": {"pmid": "4", "publication_year": "2025"},
            }
        ],
    )
    write_jsonl(
        ehr_corpus_path,
        [
            {
                "doc_id": "MIMIC:1",
                "source": "mimic_demo",
                "title": "Apixaban note",
                "text": "Apixaban appeared in a clinical note.",
                "metadata": {"source": "mimic_demo"},
            }
        ],
    )

    assert is_ehr_like_source(ehr_corpus_path)

    documents = build_drug_enrichment_documents(
        target_cuis=["C1831808"],
        code_index_path=code_index_path,
        corpus_paths=[ehr_corpus_path, open_corpus_path],
        max_mentions_per_cui=10,
    )

    assert len(documents) == 1
    document = documents[0]
    assert document.evidence_count == 1
    assert document.metadata["mention_sources"][0]["source"] == "pubmed_bulk"
    assert document.metadata["mention_sources"][0]["pmid"] == "4"
    assert "no_mimic_no_ehr" in document.metadata["source_policy"]


def test_drug_enrichment_extracts_common_open_drug_relations(tmp_path: Path) -> None:
    mrconso = tmp_path / "MRCONSO.RRF"
    code_index_path = tmp_path / "codes.sqlite"
    corpus_path = tmp_path / "corpus.jsonl"
    mrconso.write_text(
        "C1831808|ENG|P|L1|PF|S1|Y|A1|||1012554|RXNORM|IN|1012554|apixaban|0|N||\n"
        "C0529793|ENG|P|L2|PF|S2|Y|A2|||136411|RXNORM|IN|136411|sildenafil|0|N||\n",
        encoding="utf-8",
    )
    build_code_index(mrconso_path=mrconso, out_path=code_index_path, replace=True)
    write_jsonl(
        corpus_path,
        [
            {
                "doc_id": "PMID:5",
                "source": "pubmed_bulk",
                "title": "Apixaban for atrial fibrillation",
                "text": (
                    "Apixaban is a direct oral anticoagulant used for nonvalvular "
                    "atrial fibrillation and venous thromboembolism; bleeding is "
                    "a safety outcome."
                ),
                "metadata": {"pmid": "5", "publication_year": "2025"},
            },
            {
                "doc_id": "PMID:6",
                "source": "pubmed_bulk",
                "title": "Sildenafil in pulmonary hypertension",
                "text": "Sildenafil is used in pulmonary arterial hypertension.",
                "metadata": {"pmid": "6", "publication_year": "2024"},
            },
        ],
    )

    documents = build_drug_enrichment_documents(
        target_cuis=["C1831808", "C0529793"],
        code_index_path=code_index_path,
        corpus_paths=[corpus_path],
        max_mentions_per_cui=10,
    )

    relations_by_cui = {
        document.cui: {row["cui"]: row for row in document.metadata["relations"]}
        for document in documents
    }
    assert relations_by_cui["C1831808"]["C0003280"]["relation"] == "has_drug_class"
    assert relations_by_cui["C1831808"]["C0004238"]["relation"] == "used_for"
    assert relations_by_cui["C1831808"]["C0042487"]["relation"] == "prevents_or_treats"
    assert relations_by_cui["C1831808"]["C0019080"]["relation"] == "may_cause"
    assert relations_by_cui["C0529793"]["C0020542"]["relation"] == "used_for"


def test_document_metadata_relations_surface_as_research_relations(tmp_path: Path) -> None:
    documents = [
        ConceptDocument(
            doc_id="C4508938:wikipedia_summary",
            cui="C4508938",
            view="wikipedia_summary",
            text=(
                "CUI: C4508938\n"
                "Evidence view: wikipedia_summary\n"
                "UMLS labels:\n"
                "- oliceridine\n"
                "Real-world evidence:\n"
                "- Oliceridine is used for acute pain. (weight 1)"
            ),
            evidence_count=1,
            sources=["wikipedia"],
            labels=["oliceridine"],
            metadata={
                "source": "wikipedia",
                "source_title": "Oliceridine",
                "source_url": "https://en.wikipedia.org/wiki/Oliceridine",
                "relations": [
                    {
                        "cui": "C0184567",
                        "label": "Acute onset pain",
                        "category": "condition",
                        "relation_group": "treatment",
                        "relation": "indicated_for",
                        "rela": "used for acute pain",
                    }
                ]
            },
        )
    ]
    docs_path = tmp_path / "docs.jsonl"
    vectors_path = tmp_path / "vectors.jsonl"
    write_jsonl(docs_path, documents)
    write_jsonl(
        vectors_path,
        embed_documents(documents, HashingEmbedder(dim=16), include_document_metadata=True),
    )
    index = SearchIndex(
        vector_paths=[vectors_path],
        doc_paths=[docs_path],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
    )

    relations = index.research_relations_for_cui("C4508938")
    assert relations[0]["cui"] == "C0184567"
    assert relations[0]["source"] == "wikipedia"
    assert relations[0]["category"] == "condition"
    assert relations[0]["relation_group"] == "treatment"
    assert relations[0]["edge"]["subject"] == "C4508938"
    assert relations[0]["edge"]["object"] == "C0184567"
    assert relations[0]["edge"]["type"] == "treats"
    assert isinstance(relations[0]["edge"]["strength"], float)
    assert relations[0]["edge"]["evidence"] == {
        "method": "literature_mined",
        "provenance": "wikipedia",
    }
    assert isinstance(relations[0]["edge"]["context"], dict)
    assert isinstance(relations[0]["edge"]["confidence"], float)
    reverse_relations = index.research_relations_for_cui("C0184567")
    assert reverse_relations[0]["cui"] == "C4508938"
    assert reverse_relations[0]["source"] == "wikipedia"
    assert reverse_relations[0]["relation"] == "has_indicated_treatment"
    assert reverse_relations[0]["edge"]["subject"] == "C0184567"
    assert reverse_relations[0]["edge"]["object"] == "C4508938"
    hit = index.hit_from_record(index.best_record_for_cui("C4508938"), score=1.0)
    assert hit["evidence_items"][0]["sources"][0]["source"] == "wikipedia"
    assert hit["evidence_items"][0]["sources"][0]["url"] == "https://en.wikipedia.org/wiki/Oliceridine"


def test_metadata_relations_are_aggregated_across_documents_for_same_cui(tmp_path: Path) -> None:
    documents = [
        ConceptDocument(
            doc_id="C4508938:wikipedia_summary",
            cui="C4508938",
            view="wikipedia_summary",
            text=(
                "CUI: C4508938\n"
                "Evidence view: wikipedia_summary\n"
                "UMLS labels:\n"
                "- oliceridine\n"
                "Real-world evidence:\n"
                "- Oliceridine is used for acute pain. (weight 1)"
            ),
            evidence_count=1,
            sources=["wikipedia"],
            labels=["oliceridine"],
            metadata={
                "source": "wikipedia",
                "relations": [
                    {
                        "cui": "C0184567",
                        "label": "Acute onset pain",
                        "category": "condition",
                        "relation_group": "treatment",
                        "relation": "indicated_for",
                    }
                ],
            },
        ),
        ConceptDocument(
            doc_id="C4508938:drug_enrichment",
            cui="C4508938",
            view="drug_enrichment",
            text=(
                "CUI: C4508938\n"
                "Evidence view: drug_enrichment\n"
                "UMLS labels:\n"
                "- oliceridine\n"
                "Real-world evidence:\n"
                "- PMID:1: oliceridine postoperative analgesia (weight 2)\n"
                "- PMID:2: oliceridine and respiratory safety (weight 2)"
            ),
            evidence_count=2,
            sources=["pubmed_bulk", "RXNORM"],
            labels=["oliceridine"],
            metadata={"document_builder": "drug_enrichment"},
        ),
    ]
    docs_path = tmp_path / "docs.jsonl"
    vectors_path = tmp_path / "vectors.jsonl"
    write_jsonl(docs_path, documents)
    write_jsonl(
        vectors_path,
        embed_documents(documents, HashingEmbedder(dim=16), include_document_metadata=True),
    )
    index = SearchIndex(
        vector_paths=[vectors_path],
        doc_paths=[docs_path],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
    )

    assert index.best_record_for_cui("C4508938").view == "drug_enrichment"
    relations = index.research_relations_for_cui("C4508938")
    reverse_relations = index.research_relations_for_cui("C0184567")

    assert relations[0]["cui"] == "C0184567"
    assert relations[0]["source"] == "wikipedia"
    assert reverse_relations[0]["cui"] == "C4508938"
    assert reverse_relations[0]["relation"] == "has_indicated_treatment"


def test_search_index_filters_zero_evidence_homonym_label_fallback(tmp_path: Path) -> None:
    mrconso = tmp_path / "MRCONSO.RRF"
    mrconso.write_text(
        "C0243026|ENG|P|L1|PF|S1|Y|A1|||D001|MSH|MH|D001|Sepsis|0|N||\n"
        "C1090821|ENG|P|L2|PF|S2|Y|A2|||D002|MSH|MH|D002|Sepsis <Sepsidae>|0|N||\n",
        encoding="utf-8",
    )
    label_index = tmp_path / "labels.sqlite"
    build_label_index(
        mrconso_path=mrconso,
        out_path=label_index,
        min_tokens=1,
        replace=True,
    )
    documents = build_documents(
        [
            EvidenceRecord(
                "e1",
                "C0243026",
                "sepsis requiring antibiotics and vasopressors",
                "pmc_oa",
                "pmc_oa_clinical_context",
                2,
            )
        ],
        mrconso_path=mrconso,
    )
    docs_path = tmp_path / "docs.jsonl"
    vectors_path = tmp_path / "vectors.jsonl"
    write_jsonl(docs_path, documents)
    write_jsonl(vectors_path, embed_documents(documents, HashingEmbedder(dim=16)))

    index = SearchIndex(
        vector_paths=[vectors_path],
        doc_paths=[docs_path],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        label_index_paths=[label_index],
    )
    result = index.search("sepsis vasopressors antibiotics", top_k=5)

    assert result["hits"][0]["cui"] == "C0243026"
    assert "C1090821" not in [hit["cui"] for hit in result["hits"]]


def test_relation_index_builds_restricted_related_concepts(tmp_path: Path) -> None:
    mrrel = tmp_path / "MRREL.RRF"
    mrconso = tmp_path / "MRCONSO.RRF"
    docs = tmp_path / "docs.jsonl"
    out = tmp_path / "relations.sqlite"
    write_jsonl(
        docs,
        [
            {
                "doc_id": "C0004238:pubmed_clinical_context",
                "cui": "C0004238",
                "view": "pubmed_clinical_context",
                "text": "",
                "evidence_count": 0,
                "sources": [],
                "labels": [],
            }
        ],
    )
    mrrel.write_text(
        "C0004238|A1|SCUI|PAR|C0003811|A2|SCUI|isa|R1||MSH|MSH||Y|N||\n"
        "C0011849|A3|SCUI|RO|C0004238|A4|SCUI|associated_with|R2||NCI|NCI||Y|N||\n"
        "C0004238|A5|SCUI|RO|C9999999|A6|SCUI|noise|R3||MSH|MSH||Y|Y||\n",
        encoding="utf-8",
    )
    mrconso.write_text(
        "C0003811|ENG|P|L1|PF|S1|Y|A1|||D001|MSH|MH|D001|Cardiac Arrhythmia|0|N||\n"
        "C0011849|ENG|P|L2|PF|S2|Y|A2|||D002|MSH|MH|D002|Diabetes Mellitus|0|N||\n",
        encoding="utf-8",
    )
    stats = build_relation_index(
        mrrel_path=mrrel,
        mrconso_path=mrconso,
        doc_paths=[docs],
        out_path=out,
        max_relations_per_cui=4,
    )
    index = RelationIndex(out)
    related = index.lookup("C0004238", limit=4)
    index.close()

    assert stats["source_cuis"] == 1
    assert stats["relations"] == 2
    assert [item["cui"] for item in related] == ["C0003811", "C0011849"]
    assert related[0]["label"] == "Cardiac Arrhythmia"
    assert related[0]["rela"] == "isa"
    assert related[0]["edge"]["subject"] == "C0004238"
    assert related[0]["edge"]["object"] == "C0003811"
    assert related[0]["edge"]["type"] == "is_a"
    assert related[0]["edge"]["evidence"]["method"] == "curated"
    assert related[0]["edge"]["directionality"] == "subject_to_object"
    assert related[1]["direction"] == "incoming"
    assert related[1]["edge"]["type"] == "associated_with"
    assert related[1]["edge"]["directionality"] == "bidirectional"


def test_search_related_normalizes_target_side_relation_rows(tmp_path: Path) -> None:
    mrrel = tmp_path / "MRREL.RRF"
    mrconso = tmp_path / "MRCONSO.RRF"
    relation_docs = tmp_path / "relation_docs.jsonl"
    docs_path = tmp_path / "docs.jsonl"
    vectors_path = tmp_path / "vectors.jsonl"
    relation_path = tmp_path / "relations.sqlite"
    mrrel.write_text(
        "C0011849|A1|SCUI|RO|C0004238|A2|SCUI|associated_with|R1||NCI|NCI||Y|N||\n",
        encoding="utf-8",
    )
    mrconso.write_text(
        "C0011849|ENG|P|L1|PF|S1|Y|A1|||D001|MSH|MH|D001|Diabetes Mellitus|0|N||\n"
        "C0004238|ENG|P|L2|PF|S2|Y|A2|||D002|MSH|MH|D002|Atrial Fibrillation|0|N||\n",
        encoding="utf-8",
    )
    write_jsonl(
        relation_docs,
        [
            {
                "doc_id": "C0011849:clinical",
                "cui": "C0011849",
                "view": "clinical",
                "text": "",
                "evidence_count": 0,
                "sources": [],
                "labels": ["Diabetes Mellitus"],
            }
        ],
    )
    documents = build_documents(
        [
            EvidenceRecord("e1", "C0004238", "atrial fibrillation", "notes", "clinical_snippet", 1),
            EvidenceRecord("e2", "C0011849", "diabetes mellitus", "notes", "clinical_snippet", 1),
        ],
        mrconso_path=mrconso,
    )
    write_jsonl(docs_path, documents)
    write_jsonl(vectors_path, embed_documents(documents, HashingEmbedder(dim=16)))
    build_relation_index(
        mrrel_path=mrrel,
        mrconso_path=mrconso,
        doc_paths=[relation_docs],
        out_path=relation_path,
        max_relations_per_cui=4,
    )
    index = SearchIndex(
        vector_paths=[vectors_path],
        doc_paths=[docs_path],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        relation_index_path=relation_path,
    )

    related = index.related_concepts_for_cui("C0004238")

    assert related[0]["cui"] == "C0011849"
    assert related[0]["label"] == "Diabetes Mellitus"
    assert related[0]["direction"] == "bidirectional"
    assert related[0]["edge"]["subject"] == "C0004238"
    assert related[0]["edge"]["object"] == "C0011849"
    assert related[0]["edge"]["type"] == "associated_with"
    assert related[0]["edge"]["directionality"] == "bidirectional"


def test_research_relation_index_builds_cross_semantic_links(tmp_path: Path) -> None:
    mrrel = tmp_path / "MRREL.RRF"
    mrconso = tmp_path / "MRCONSO.RRF"
    mrsty = tmp_path / "MRSTY.RRF"
    docs = tmp_path / "docs.jsonl"
    out = tmp_path / "research_relations.sqlite"
    write_jsonl(
        docs,
        [
            {
                "doc_id": "C0010674:clinical",
                "cui": "C0010674",
                "view": "clinical",
                "text": "",
                "evidence_count": 0,
                "sources": [],
                "labels": ["Cystic Fibrosis"],
            },
            {
                "doc_id": "C0056889:gene",
                "cui": "C0056889",
                "view": "gene",
                "text": "",
                "evidence_count": 0,
                "sources": [],
                "labels": ["CFTR Protein"],
            },
        ],
    )
    mrrel.write_text(
        "C0010674|A1|SCUI|RO|C0056889|A2|SCUI||R1||MSH|MSH||Y|N||\n"
        "C0010674|A3|SCUI|RO|C0003232|A4|SCUI|may_treat|R2||MED-RT|MED-RT||Y|N||\n"
        "C0010674|A5|SCUI|RO|C0003611|A6|SCUI|associated_procedure_of|R3||SNOMEDCT_US|SNOMEDCT_US||Y|N||\n"
        "C0010674|A7|SCUI|PAR|C0024109|A8|SCUI|isa|R4||MSH|MSH||Y|N||\n",
        encoding="utf-8",
    )
    mrconso.write_text(
        "C0056889|ENG|P|L1|PF|S1|Y|A1|||D001|MSH|MH|D001|CFTR Protein|0|N||\n"
        "C0003232|ENG|P|L2|PF|S2|Y|A2|||D002|RXNORM|IN|D002|Amoxicillin|0|N||\n"
        "C0003611|ENG|P|L3|PF|S3|Y|A3|||D003|MSH|MH|D003|Appendectomy|0|N||\n"
        "C0024109|ENG|P|L4|PF|S4|Y|A4|||D004|MSH|MH|D004|Lung|0|N||\n",
        encoding="utf-8",
    )
    mrsty.write_text(
        "C0010674|T047|B2.2.1.2.1|Disease or Syndrome|AT1|\n"
        "C0056889|T116|A1.4.1.2.3|Amino Acid, Peptide, or Protein|AT2|\n"
        "C0003232|T195|A1.4.1.1.3|Antibiotic|AT3|\n"
        "C0003611|T061|B1.3.1.2|Therapeutic or Preventive Procedure|AT4|\n"
        "C0024109|T023|A1.2.3|Body Part, Organ, or Organ Component|AT5|\n",
        encoding="utf-8",
    )
    stats = build_research_relation_index(
        mrrel_path=mrrel,
        mrconso_path=mrconso,
        mrsty_path=mrsty,
        doc_paths=[docs],
        out_path=out,
        max_relations_per_category=4,
    )
    index = ResearchRelationIndex(out)
    disease_links = index.lookup("C0010674", limit_per_category=4)
    gene_links = index.lookup("C0056889", limit_per_category=4)
    index.close()

    assert stats["sources_with_relations"] == 2
    assert stats["relations"] == 4
    assert {item["category"] for item in disease_links} == {
        "gene_protein",
        "drug_chemical",
        "procedure_test",
    }
    assert {item["cui"] for item in disease_links} == {"C0056889", "C0003232", "C0003611"}
    assert "C0024109" not in {item["cui"] for item in disease_links}
    assert next(item for item in disease_links if item["cui"] == "C0056889")["relation_group"] == "genetic_association"
    assert next(item for item in disease_links if item["cui"] == "C0003232")["relation_group"] == "treatment"
    drug_link = next(item for item in disease_links if item["cui"] == "C0003232")
    assert drug_link["edge"]["subject"] == "C0010674"
    assert drug_link["edge"]["object"] == "C0003232"
    assert drug_link["edge"]["type"] == "treats"
    assert next(item for item in disease_links if item["cui"] == "C0003611")["label"] == "Appendectomy"
    assert gene_links[0]["cui"] == "C0010674"
    assert gene_links[0]["category"] == "condition"
    assert gene_links[0]["edge"]["type"] == "associated_with"


def test_search_research_relations_normalizes_target_side_rows(tmp_path: Path) -> None:
    mrrel = tmp_path / "MRREL.RRF"
    mrconso = tmp_path / "MRCONSO.RRF"
    mrsty = tmp_path / "MRSTY.RRF"
    relation_docs = tmp_path / "relation_docs.jsonl"
    docs_path = tmp_path / "docs.jsonl"
    vectors_path = tmp_path / "vectors.jsonl"
    research_relation_path = tmp_path / "research_relations.sqlite"
    semantic_type_path = tmp_path / "semantic_types.sqlite"
    mrrel.write_text(
        "C0184567|A1|SCUI|RO|C4508938|A2|SCUI|may_be_prevented_by|R1||MED-RT|MED-RT||Y|N||\n",
        encoding="utf-8",
    )
    mrconso.write_text(
        "C0184567|ENG|P|L1|PF|S1|Y|A1|||D001|MSH|MH|D001|Acute pain|0|N||\n"
        "C4508938|ENG|P|L2|PF|S2|Y|A2|||D002|RXNORM|IN|2392230|oliceridine|0|N||\n",
        encoding="utf-8",
    )
    mrsty.write_text(
        "C0184567|T184|A2.2.2|Sign or Symptom|AT1|\n"
        "C4508938|T121|A1.4.1.1.1|Pharmacologic Substance|AT2|\n",
        encoding="utf-8",
    )
    write_jsonl(
        relation_docs,
        [
            {
                "doc_id": "C0184567:clinical",
                "cui": "C0184567",
                "view": "clinical",
                "text": "",
                "evidence_count": 0,
                "sources": [],
                "labels": ["Acute pain"],
            }
        ],
    )
    documents = [
        ConceptDocument(
            doc_id="C0184567:clinical",
            cui="C0184567",
            view="clinical",
            text="CUI: C0184567\nEvidence view: clinical\nUMLS labels:\n- Acute pain",
            evidence_count=0,
            sources=[],
            labels=["Acute pain"],
        ),
        ConceptDocument(
            doc_id="C4508938:wikipedia_summary",
            cui="C4508938",
            view="wikipedia_summary",
            text="CUI: C4508938\nEvidence view: wikipedia_summary\nUMLS labels:\n- oliceridine",
            evidence_count=0,
            sources=["wikipedia"],
            labels=["oliceridine"],
        ),
    ]
    write_jsonl(docs_path, documents)
    write_jsonl(vectors_path, embed_documents(documents, HashingEmbedder(dim=16)))
    build_research_relation_index(
        mrrel_path=mrrel,
        mrconso_path=mrconso,
        mrsty_path=mrsty,
        doc_paths=[relation_docs],
        out_path=research_relation_path,
        max_relations_per_category=4,
    )
    build_semantic_type_index(mrsty_path=mrsty, out_path=semantic_type_path, replace=True)
    index = SearchIndex(
        vector_paths=[vectors_path],
        doc_paths=[docs_path],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        semantic_type_index_path=semantic_type_path,
        research_relation_index_path=research_relation_path,
    )

    relations = index.research_relations_for_cui("C4508938")

    assert relations[0]["cui"] == "C0184567"
    assert relations[0]["label"] == "Acute pain"
    assert relations[0]["category"] == "condition"
    assert relations[0]["relation"] == "may_prevent"
    assert relations[0]["direction"] == "bidirectional"
    assert relations[0]["edge"]["subject"] == "C4508938"
    assert relations[0]["edge"]["object"] == "C0184567"
    assert relations[0]["edge"]["type"] == "treats"
    assert relations[0]["edge"]["directionality"] == "bidirectional"


def test_drug_rollup_relations_from_adjacent_drug_concepts(tmp_path: Path) -> None:
    mrrel = tmp_path / "MRREL.RRF"
    mrconso = tmp_path / "MRCONSO.RRF"
    mrsty = tmp_path / "MRSTY.RRF"
    docs_path = tmp_path / "docs.jsonl"
    vectors_path = tmp_path / "vectors.jsonl"
    relation_path = tmp_path / "relations.sqlite"
    research_relation_path = tmp_path / "research_relations.sqlite"
    semantic_type_path = tmp_path / "semantic_types.sqlite"
    code_path = tmp_path / "codes.sqlite"
    mrconso.write_text(
        "C9000001|ENG|P|L1|PF|S1|Y|A1|||111|RXNORM|IN|111|testformin|0|N||\n"
        "C9000002|ENG|P|L2|PF|S2|Y|A2|||222|RXNORM|PIN|222|testformin hydrochloride|0|N||\n"
        "C9000003|ENG|P|L3|PF|S3|Y|A3|||333|RXNORM|SCD|333|testformin 500 MG Oral Tablet|0|N||\n"
        "C9000004|ENG|P|L4|PF|S4|Y|A4|||444|SNOMEDCT_US|PT|444|Testformin therapy|0|N||\n"
        "C9000005|ENG|P|L5|PF|S5|Y|A5|||555|SNOMEDCT_US|PT|555|Testformin measurement|0|N||\n"
        "C9000101|ENG|P|L6|PF|S6|Y|A6|||666|HGNC|ACR|666|AMPK protein|0|N||\n"
        "C9000102|ENG|P|L7|PF|S7|Y|A7|||777|MSH|MH|777|Type 2 Diabetes Mellitus|0|N||\n"
        "C9000103|ENG|P|L8|PF|S8|Y|A8|||888|MSH|MH|888|Diabetes Mellitus|0|N||\n"
        "C9000104|ENG|P|L9|PF|S9|Y|A9|||999|MSH|MH|999|Metabolic acidosis|0|N||\n",
        encoding="utf-8",
    )
    mrsty.write_text(
        "C9000001|T121|A1.4.1.1.1|Pharmacologic Substance|AT1|\n"
        "C9000002|T109|A1.4.1.2.1|Organic Chemical|AT2|\n"
        "C9000003|T200|A1.3.3|Clinical Drug|AT3|\n"
        "C9000004|T061|B1.3.1.2.2|Therapeutic or Preventive Procedure|AT4|\n"
        "C9000005|T059|B1.3.1.2.1|Laboratory Procedure|AT5|\n"
        "C9000101|T116|A1.4.1.2.3|Amino Acid, Peptide, or Protein|AT6|\n"
        "C9000102|T047|B2.2.1.2.1|Disease or Syndrome|AT7|\n"
        "C9000103|T047|B2.2.1.2.1|Disease or Syndrome|AT8|\n"
        "C9000104|T046|B2.2.1.2|Pathologic Function|AT9|\n",
        encoding="utf-8",
    )
    mrrel.write_text(
        "C9000002|A1|SCUI|PAR|C9000001|A2|SCUI|isa|R1||SNOMEDCT_US|SNOMEDCT_US||Y|N||\n"
        "C9000003|A3|SCUI|RO|C9000001|A4|SCUI|has_ingredient|R2||SNOMEDCT_US|SNOMEDCT_US||Y|N||\n"
        "C9000004|A5|SCUI|RO|C9000001|A6|SCUI|direct_substance_of|R3||SNOMEDCT_US|SNOMEDCT_US||Y|N||\n"
        "C9000005|A7|SCUI|RO|C9000001|A8|SCUI|component_of|R4||SNOMEDCT_US|SNOMEDCT_US||Y|N||\n"
        "C9000002|A9|SCUI|RO|C9000101|A10|SCUI|gene_plays_role_in_process|R5||NCI|NCI||Y|N||\n"
        "C9000003|A11|SCUI|RO|C9000102|A12|SCUI|may_treat|R6||MED-RT|MED-RT||Y|N||\n"
        "C9000004|A13|SCUI|RO|C9000103|A14|SCUI|associated_procedure_of|R7||SNOMEDCT_US|SNOMEDCT_US||Y|N||\n"
        "C9000005|A15|SCUI|RO|C9000104|A16|SCUI|interprets|R8||LNC|LNC||Y|N||\n",
        encoding="utf-8",
    )
    documents = [
        ConceptDocument(
            doc_id=f"{cui}:test",
            cui=cui,
            view="test",
            text=f"CUI: {cui}\nEvidence view: test\nUMLS labels:\n- {label}",
            evidence_count=0,
            sources=[],
            labels=[label],
        )
        for cui, label in [
            ("C9000001", "testformin"),
            ("C9000002", "testformin hydrochloride"),
            ("C9000003", "testformin 500 MG Oral Tablet"),
            ("C9000004", "Testformin therapy"),
            ("C9000005", "Testformin measurement"),
        ]
    ]
    write_jsonl(docs_path, documents)
    write_jsonl(vectors_path, embed_documents(documents, HashingEmbedder(dim=16)))
    build_code_index(mrconso_path=mrconso, out_path=code_path, replace=True)
    build_semantic_type_index(mrsty_path=mrsty, out_path=semantic_type_path, replace=True)
    build_relation_index(
        mrrel_path=mrrel,
        mrconso_path=mrconso,
        doc_paths=[docs_path],
        out_path=relation_path,
        max_relations_per_cui=8,
    )
    build_research_relation_index(
        mrrel_path=mrrel,
        mrconso_path=mrconso,
        mrsty_path=mrsty,
        doc_paths=[docs_path],
        out_path=research_relation_path,
        max_relations_per_category=8,
    )
    index = SearchIndex(
        vector_paths=[vectors_path],
        doc_paths=[docs_path],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        code_index_path=code_path,
        semantic_type_index_path=semantic_type_path,
        relation_index_path=relation_path,
        research_relation_index_path=research_relation_path,
    )

    relations = index.research_relations_for_cui("C9000001")
    by_cui = {relation["cui"]: relation for relation in relations}

    assert by_cui["C9000101"]["rollup"] is True
    assert by_cui["C9000101"]["rollup_source_cui"] == "C9000002"
    assert by_cui["C9000101"]["rollup_role"] == "salt_or_precise_ingredient"
    assert by_cui["C9000101"]["edge"]["subject"] == "C9000001"
    assert by_cui["C9000101"]["edge"]["object"] == "C9000101"
    assert by_cui["C9000101"]["edge"]["context"]["rollup"]["via_cui"] == "C9000002"
    assert by_cui["C9000102"]["rollup_source_cui"] == "C9000003"
    assert by_cui["C9000102"]["rollup_role"] == "clinical_drug"
    assert by_cui["C9000103"]["rollup_source_cui"] == "C9000004"
    assert by_cui["C9000103"]["rollup_role"] == "therapy"
    assert by_cui["C9000104"]["rollup_source_cui"] == "C9000005"
    assert by_cui["C9000104"]["rollup_role"] == "measurement"


def test_research_relation_index_adds_hpo_gene_disease_phenotype_links(tmp_path: Path) -> None:
    mrrel = tmp_path / "MRREL.RRF"
    mrconso = tmp_path / "MRCONSO.RRF"
    mrsty = tmp_path / "MRSTY.RRF"
    hpo_obo = tmp_path / "hp.obo"
    phenotype_hpoa = tmp_path / "phenotype.hpoa"
    genes_to_phenotype = tmp_path / "genes_to_phenotype.txt"
    docs = tmp_path / "docs.jsonl"
    out = tmp_path / "research_relations.sqlite"
    write_jsonl(
        docs,
        [
            {
                "doc_id": "C0024796:clinical",
                "cui": "C0024796",
                "view": "clinical",
                "text": "",
                "evidence_count": 0,
                "sources": [],
                "labels": ["Marfan Syndrome"],
            },
            {
                "doc_id": "C1414156:gene",
                "cui": "C1414156",
                "view": "gene",
                "text": "",
                "evidence_count": 0,
                "sources": [],
                "labels": ["FBN1 gene"],
            },
        ],
    )
    mrrel.write_text("", encoding="utf-8")
    mrconso.write_text(
        "C0024796|ENG|P|L1|PF|S1|Y|A1|||154700|OMIM|PT|154700|MARFAN SYNDROME|0|N||\n"
        "C1414156|ENG|P|L2|PF|S2|Y|A2|||HGNC:3603|HGNC|ACR|HGNC:3603|FBN1|0|N||\n"
        "C1414156|ENG|P|L3|PF|S3|Y|A3|||HGNC:3603|HGNC|MTH_ACR|HGNC:3603|FBN1 gene|0|N||\n",
        encoding="utf-8",
    )
    mrsty.write_text(
        "C0024796|T047|B2.2.1.2.1|Disease or Syndrome|AT1|\n"
        "C1414156|T028|A1.2.3.4|Gene or Genome|AT2|\n"
        "C1234567|T033|A2.2|Finding|AT3|\n",
        encoding="utf-8",
    )
    hpo_obo.write_text(
        "[Term]\n"
        "id: HP:0001519\n"
        "name: Disproportionate tall stature\n"
        "xref: UMLS:C1234567\n",
        encoding="utf-8",
    )
    phenotype_hpoa.write_text(
        "database_id\tdisease_name\tqualifier\thpo_id\treference\tevidence\tonset\tfrequency\tsex\tmodifier\taspect\tbiocuration\n"
        "OMIM:154700\tMarfan syndrome\t\tHP:0001519\tPMID:1\tPCS\t\t1/2\t\t\tP\tHPO:test[2026-01-01]\n",
        encoding="utf-8",
    )
    genes_to_phenotype.write_text(
        "ncbi_gene_id\tgene_symbol\thpo_id\thpo_name\tfrequency\tdisease_id\n"
        "2200\tFBN1\tHP:0001519\tDisproportionate tall stature\t1/2\tOMIM:154700\n",
        encoding="utf-8",
    )

    stats = build_research_relation_index(
        mrrel_path=mrrel,
        mrconso_path=mrconso,
        mrsty_path=mrsty,
        doc_paths=[docs],
        out_path=out,
        max_relations_per_category=4,
        hpo_obo_path=hpo_obo,
        hpo_phenotype_annotations_path=phenotype_hpoa,
        hpo_genes_to_phenotype_path=genes_to_phenotype,
    )
    index = ResearchRelationIndex(out)
    disease_links = index.lookup("C0024796", limit_per_category=4)
    gene_links = index.lookup("C1414156", limit_per_category=4)
    index.close()

    assert stats["hpo_relations"] == 4
    assert next(item for item in disease_links if item["category"] == "gene_protein")["label"] == "FBN1"
    disease_phenotypes = [item for item in disease_links if item["category"] == "phenotype"]
    assert disease_phenotypes[0]["label"] == "Disproportionate tall stature"
    assert disease_phenotypes[0]["source"] == "HPO"
    assert next(item for item in gene_links if item["category"] == "condition")["label"] == "MARFAN SYNDROME"
    assert next(item for item in gene_links if item["category"] == "phenotype")["cui"] == "C1234567"


def test_related_bundle_returns_graph_vector_neighbors_and_mappings(tmp_path: Path) -> None:
    mrrel = tmp_path / "MRREL.RRF"
    mrconso = tmp_path / "MRCONSO.RRF"
    mrsty = tmp_path / "MRSTY.RRF"
    mrconso.write_text(
        "C0004238|ENG|P|L1|PF|S1|Y|A1||SCUI1|SDUI1|ICD10CM|PT|I48.91|Atrial fibrillation|0|N||\n"
        "C0003811|ENG|P|L2|PF|S2|Y|A2|||D002|MSH|MH|D002|Cardiac Arrhythmia|0|N||\n"
        "C0011849|ENG|P|L3|PF|S3|Y|A3|||D003|MSH|MH|D003|Diabetes Mellitus|0|N||\n"
        "C0003611|ENG|P|L4|PF|S4|Y|A4|||D004|MSH|MH|D004|Catheter Ablation|0|N||\n"
        "C0099999|ENG|P|L5|PF|S5|Y|A5|||D005|MSH|MH|D005|Retinal Screening|0|N||\n",
        encoding="utf-8",
    )
    mrrel.write_text(
        "C0004238|A1|SCUI|PAR|C0003811|A2|SCUI|isa|R1||MSH|MSH||Y|N||\n"
        "C0004238|A3|SCUI|RO|C0003611|A4|SCUI|associated_procedure_of|R2||SNOMEDCT_US|SNOMEDCT_US||Y|N||\n"
        "C0011849|A3|SCUI|RO|C0003611|A4|SCUI|associated_procedure_of|R3||SNOMEDCT_US|SNOMEDCT_US||Y|N||\n"
        "C0011849|A3|SCUI|RO|C0099999|A5|SCUI|associated_procedure_of|R4||SNOMEDCT_US|SNOMEDCT_US||Y|N||\n",
        encoding="utf-8",
    )
    mrsty.write_text(
        "C0004238|T047|B2.2.1.2.1|Disease or Syndrome|AT1|\n"
        "C0003811|T047|B2.2.1.2.1|Disease or Syndrome|AT2|\n"
        "C0011849|T047|B2.2.1.2.1|Disease or Syndrome|AT3|\n"
        "C0003611|T061|B1.3.1.2|Therapeutic or Preventive Procedure|AT4|\n"
        "C0099999|T060|B1.3.1.1|Diagnostic Procedure|AT5|\n",
        encoding="utf-8",
    )
    documents = build_documents(
        [
            EvidenceRecord("e1", "C0004238", "atrial fibrillation anticoagulation", "pubmed", "pubmed_clinical_context", 2),
            EvidenceRecord("e2", "C0011849", "diabetes mellitus hba1c", "pubmed", "pubmed_clinical_context", 2),
        ]
    )
    docs_path = tmp_path / "docs.jsonl"
    vectors_path = tmp_path / "vectors.jsonl"
    relation_path = tmp_path / "relations.sqlite"
    research_relation_path = tmp_path / "research_relations.sqlite"
    semantic_type_path = tmp_path / "semantic_types.sqlite"
    code_path = tmp_path / "codes.sqlite"
    write_jsonl(docs_path, documents)
    write_jsonl(vectors_path, embed_documents(documents, HashingEmbedder(dim=16)))
    build_relation_index(
        mrrel_path=mrrel,
        mrconso_path=mrconso,
        doc_paths=[docs_path],
        out_path=relation_path,
        max_relations_per_cui=4,
    )
    build_research_relation_index(
        mrrel_path=mrrel,
        mrconso_path=mrconso,
        mrsty_path=mrsty,
        doc_paths=[docs_path],
        out_path=research_relation_path,
        max_relations_per_category=4,
    )
    build_semantic_type_index(mrsty_path=mrsty, out_path=semantic_type_path, replace=True)
    build_code_index(mrconso_path=mrconso, out_path=code_path, replace=True)
    index = SearchIndex(
        vector_paths=[vectors_path],
        doc_paths=[docs_path],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        code_index_path=code_path,
        semantic_type_index_path=semantic_type_path,
        relation_index_path=relation_path,
        research_relation_index_path=research_relation_path,
    )
    bundle = index.related_bundle("C0004238", top_k=5, mapping_sabs=["ICD10CM"])
    hit = index.hit_from_record(index.best_record_for_cui("C0004238"), score=1.0)
    diabetes_hit = index.hit_from_record(index.best_record_for_cui("C0011849"), score=0.9)
    index.attach_related_concepts([hit, diabetes_hit])
    lightweight_metadata = index.semantic_response_metadata([hit], include_related=False)
    search_result = index.search("diabetes retinal screening procedure", top_k=2, include_related=False)
    diabetes_search_hit = next(item for item in search_result["hits"] if item["cui"] == "C0011849")

    assert bundle["mrrel_neighbors"][0]["cui"] == "C0003811"
    assert bundle["related_source"] == "evidence_vectors"
    assert bundle["related_concepts"][0]["cui"] == "C0011849"
    assert bundle["related_concepts"][0]["relation"] == "evidence_vector"
    assert bundle["evidence_vector_neighbors"][0]["cui"] == "C0011849"
    assert bundle["mappings"][0]["code"] == "I48.91"
    assert bundle["research_relations"][0]["cui"] == "C0003611"
    assert bundle["research_relations"][0]["category"] == "procedure_test"
    assert hit["related_source"] == "mrrel"
    assert hit["mrrel_related_concepts"][0]["cui"] == "C0003811"
    assert hit["related_concepts"][0]["cui"] == "C0003811"
    assert hit["research_relations"][0]["cui"] == "C0003611"
    assert semantic_group_from_types(hit["semantic_types"]) == "DISO"
    assert lightweight_metadata["semantic_views"] == []
    assert lightweight_metadata["semantic_view_sources"] == []
    assert lightweight_metadata["semantic_group_views"] == []
    assert all(
        item.get("kind") != "relation"
        for bucket in lightweight_metadata["semantic_result_buckets"]
        for item in bucket.get("items", [])
    )
    assert search_result["semantic_views"] == []
    assert search_result["semantic_view_sources"] == []
    assert search_result["semantic_group_views"] == []
    assert all(
        item.get("kind") != "relation"
        for bucket in search_result["semantic_result_buckets"]
        for item in bucket.get("items", [])
    )
    assert diabetes_search_hit["score_breakdown"]["mrrel_component"] > 0
    assert diabetes_search_hit["score_breakdown"]["mrrel_signal_reasons"][0]["cui"] == "C0099999"

    views = index.semantic_views_for_hits([hit])
    assert views[0]["source_semantic_group"] == "DISO"
    assert views[0]["source_semantic_group_label"] == "Disorders"
    assert views[0]["category"] == "procedure_test"
    assert views[0]["semantic_group"] == "PROC"
    assert views[0]["semantic_group_label"] == "Procedures"
    assert views[0]["title"] == "Procedures"
    assert views[0]["items"][0]["cui"] == "C0003611"

    response = index.search("C0004238", top_k=1)
    assert response["top_semantic_group"] == "DISO"
    assert response["top_semantic_group_label"] == "Disorders"
    assert response["semantic_views"][0]["category"] == "procedure_test"
    assert response["semantic_view_sources"][0]["source_cui"] == "C0004238"
    assert response["semantic_view_sources"][0]["views"][0]["category"] == "procedure_test"

    sections = index.semantic_view_sources_for_hits([hit, diabetes_hit], source_limit=10)
    assert [section["rank"] for section in sections] == [1, 2]
    assert sections[0]["source_cui"] == "C0004238"
    assert sections[1]["source_cui"] == "C0011849"
    assert sections[1]["views"][0]["semantic_group"] == "PROC"

    group_views = index.semantic_group_views_from_sources(sections)
    assert group_views[0]["semantic_group"] == "PROC"
    assert group_views[0]["source_ranks"] == [1, 2]
    assert {item["source_rank"] for item in group_views[0]["items"]} == {1, 2}
    assert {item["cui"] for item in group_views[0]["items"]} == {"C0003611", "C0099999"}


def test_semantic_buckets_hide_weak_ccpss_procedure_associations() -> None:
    proc_bucket = next(bucket for bucket in SEMANTIC_RESULT_BUCKETS if bucket["key"] == "PROC")
    gene_bucket = next(bucket for bucket in SEMANTIC_RESULT_BUCKETS if bucket["key"] == "GENE")
    weak_relation = {
        "cui": "C0002688",
        "label": "AMPUTATION",
        "source": "CCPSS",
        "relation": "RQ",
        "rela": "clinically_associated_with",
        "relation_group": "procedure_or_test",
        "source_name": "Congestive heart failure",
    }
    overlapping_relation = {
        **weak_relation,
        "cui": "C1272198",
        "label": "Heart failure screen",
    }
    strong_relation = {
        **weak_relation,
        "source": "SNOMEDCT_US",
        "rela": "focus_of",
    }
    weak_gene_relation = {
        **weak_relation,
        "cui": "C0019045",
        "label": "Hemoglobin SS",
        "rela": "inverse clinically associated with",
        "semantic_type": "amino acid, peptide, or protein",
        "source_name": "Pancreatitis, Acute",
    }

    assert not relation_visible_in_semantic_bucket(weak_relation, proc_bucket, "PROC")
    assert relation_visible_in_semantic_bucket(overlapping_relation, proc_bucket, "PROC")
    assert relation_visible_in_semantic_bucket(strong_relation, proc_bucket, "PROC")
    assert not relation_visible_in_semantic_bucket(weak_gene_relation, gene_bucket, "CHEM")


def test_semantic_result_buckets_threshold_then_sort_by_best_global_score() -> None:
    hits = [
        {
            "cui": "C0004057",
            "doc_id": "C0004057:drug",
            "name": "Aspirin",
            "semantic_group": "CHEM",
            "semantic_types": [{"name": "Pharmacologic Substance"}],
            "rank_score": 0.64,
            "score_breakdown": {"rank_score": 0.64},
        },
        {
            "cui": "C0011849",
            "doc_id": "C0011849:condition",
            "name": "Diabetes mellitus",
            "semantic_group": "DISO",
            "semantic_types": [{"name": "Disease or Syndrome"}],
            "rank_score": 0.63,
            "score_breakdown": {"rank_score": 0.63},
        },
        {
            "cui": "C0000001",
            "doc_id": "C0000001:finding",
            "name": "Low signal symptom",
            "semantic_group": "FIND",
            "semantic_types": [{"name": "Sign or Symptom"}],
            "rank_score": 0.10,
            "score_breakdown": {"rank_score": 0.10},
        },
    ]

    groups = semantic_result_buckets_for_response(hits, [])

    assert [group["key"] for group in groups] == ["CHEM", "DISO_DISEASE"]
    assert groups[0]["bestRelevance"] == 0.64
    assert all(item["kind"] == "hit" for group in groups for item in group["items"])
    assert "DISO_FINDING" not in {group["key"] for group in groups}


def test_related_result_buckets_are_separate_and_require_stronger_evidence() -> None:
    hits = [
        {
            "cui": "C0011849",
            "doc_id": "C0011849:condition",
            "name": "Diabetes mellitus",
            "semantic_group": "DISO",
            "semantic_types": [{"name": "Disease or Syndrome"}],
            "rank_score": 0.70,
            "score_breakdown": {"rank_score": 0.70},
        }
    ]
    semantic_group_views = [
        {
            "semantic_group": "PROC",
            "items": [
                {
                    "cui": "C0003611",
                    "label": "Appendectomy",
                    "semantic_type": "Therapeutic or Preventive Procedure",
                    "edge": {"strength": 0.76, "confidence": 0.82},
                },
                {
                    "cui": "C0002688",
                    "label": "Weak procedure neighbor",
                    "semantic_type": "Therapeutic or Preventive Procedure",
                    "edge": {"strength": 0.41, "confidence": 0.82},
                },
            ],
        }
    ]

    semantic_groups = semantic_result_buckets_for_response(hits, semantic_group_views)
    related_groups = related_result_buckets_for_response(semantic_group_views)

    assert all(
        item["kind"] == "hit"
        for group in semantic_groups
        for item in group["items"]
    )
    assert [group["key"] for group in related_groups] == ["PROC"]
    assert [item["relation"]["cui"] for item in related_groups[0]["items"]] == ["C0003611"]


def test_observation_related_items_share_existing_observation_bucket_key() -> None:
    hits = [
        {
            "cui": "C0202115",
            "doc_id": "C0202115:lab",
            "name": "Lactate",
            "semantic_group": "OBS",
            "semantic_types": [{"name": "Laboratory Procedure"}],
            "rank_score": 0.91,
            "score_breakdown": {"rank_score": 0.91},
        }
    ]
    semantic_group_views = [
        {
            "semantic_group": "OBS",
            "items": [
                {
                    "cui": "C0392201",
                    "label": "Blood glucose",
                    "semantic_type": "Laboratory Procedure",
                    "edge": {"strength": 0.82, "confidence": 0.71},
                }
            ],
        }
    ]

    semantic_groups = semantic_result_buckets_for_response(hits, semantic_group_views)
    related_groups = related_result_buckets_for_response(semantic_group_views)

    assert [group["key"] for group in semantic_groups] == ["CLIN_ATTR"]
    assert [group["key"] for group in related_groups] == ["CLIN_ATTR"]


def test_semantic_buckets_route_proteins_to_gene_bucket_not_drugs() -> None:
    chem_bucket = next(bucket for bucket in SEMANTIC_RESULT_BUCKETS if bucket["key"] == "CHEM")
    gene_bucket = next(bucket for bucket in SEMANTIC_RESULT_BUCKETS if bucket["key"] == "GENE")
    protein_hit = {
        "cui": "C0259275",
        "name": "BRCA1 Protein",
        "semantic_group": "CHEM",
        "semantic_types": [{"name": "Amino Acid, Peptide, or Protein"}],
    }
    drug_hit = {
        "cui": "C0004057",
        "semantic_group": "CHEM",
        "semantic_types": [{"name": "Pharmacologic Substance"}],
    }
    peptide_drug_hit = {
        "cui": "C0042313",
        "name": "vancomycin",
        "semantic_group": "CHEM",
        "semantic_types": [{"name": "Amino Acid, Peptide, or Protein"}],
    }
    protein_relation = {
        "cui": "C0259275",
        "label": "BRCA1 Protein",
        "category": "gene_protein",
        "semantic_type": "amino acid, peptide, or protein",
    }
    peptide_drug_relation = {
        "cui": "C0205997",
        "label": "Streptogramins",
        "category": "drug_chemical",
        "semantic_type": "amino acid, peptide, or protein",
    }
    fusion_protein_relation = {
        "cui": "C0004891",
        "label": "Fusion Proteins, bcr-abl",
        "category": "drug_chemical",
        "semantic_type": "amino acid, peptide, or protein",
    }
    exon_relation = {
        "cui": "C0015295",
        "label": "Exons",
        "category": "drug_chemical",
        "semantic_type": "nucleic acid, nucleoside, or nucleotide",
    }
    dosage_form_relation = {
        "cui": "C1337602",
        "label": "Enteric Coated Tablet Dosage Form",
        "category": "drug_chemical",
        "semantic_type": "biomedical or dental material",
    }
    clinical_drug_formulation_relation = {
        "cui": "C0989074",
        "label": "potassium chloride 20 MEQ",
        "category": "drug_chemical",
        "semantic_type": "clinical drug",
    }
    ingredient_relation = {
        "cui": "C0022665",
        "label": "potassium chloride",
        "category": "drug_chemical",
        "semantic_type": "organic chemical",
    }
    broad_chemical_hit = {
        "cui": "C0038774",
        "name": "Sulfates, Inorganic",
        "semantic_group": "CHEM",
        "semantic_types": [{"name": "Inorganic Chemical"}],
    }
    active_drug_hit = {
        "cui": "C0024480",
        "name": "magnesium sulfate",
        "semantic_group": "CHEM",
        "semantic_types": [{"name": "Pharmacologic Substance"}],
    }

    assert not hit_matches_semantic_bucket(protein_hit, chem_bucket)
    assert hit_matches_semantic_bucket(protein_hit, gene_bucket)
    assert hit_matches_semantic_bucket(drug_hit, chem_bucket)
    assert hit_matches_semantic_bucket(peptide_drug_hit, chem_bucket)
    assert not hit_matches_semantic_bucket(peptide_drug_hit, gene_bucket)
    assert not relation_visible_in_semantic_bucket(protein_relation, chem_bucket, "CHEM")
    assert relation_visible_in_semantic_bucket(protein_relation, gene_bucket, "CHEM")
    assert relation_visible_in_semantic_bucket(peptide_drug_relation, chem_bucket, "CHEM")
    assert not relation_visible_in_semantic_bucket(peptide_drug_relation, gene_bucket, "CHEM")
    assert not relation_visible_in_semantic_bucket(fusion_protein_relation, chem_bucket, "CHEM")
    assert relation_visible_in_semantic_bucket(fusion_protein_relation, gene_bucket, "CHEM")
    assert not relation_visible_in_semantic_bucket(exon_relation, chem_bucket, "CHEM")
    assert relation_visible_in_semantic_bucket(exon_relation, gene_bucket, "CHEM")
    assert not relation_visible_in_semantic_bucket(dosage_form_relation, chem_bucket, "CHEM")
    assert not relation_visible_in_semantic_bucket(clinical_drug_formulation_relation, chem_bucket, "CHEM")
    assert relation_visible_in_semantic_bucket(ingredient_relation, chem_bucket, "CHEM")
    assert not hit_matches_semantic_bucket(broad_chemical_hit, chem_bucket)
    assert hit_matches_semantic_bucket(active_drug_hit, chem_bucket)


def test_semantic_buckets_route_lab_procedures_to_observations_not_procedures() -> None:
    proc_bucket = next(bucket for bucket in SEMANTIC_RESULT_BUCKETS if bucket["key"] == "PROC")
    observation_bucket = next(bucket for bucket in SEMANTIC_RESULT_BUCKETS if bucket["key"] == "CLIN_ATTR")
    lab_hit = {
        "cui": "C0474680",
        "semantic_group": "PROC",
        "semantic_types": [{"name": "Laboratory Procedure"}],
    }
    diagnostic_measurement_hit = {
        "cui": "C0489482",
        "name": "Ejection fraction measurement",
        "semantic_group": "PROC",
        "semantic_types": [{"name": "Diagnostic Procedure"}],
    }
    diagnostic_procedure_hit = {
        "cui": "C0005558",
        "name": "Biopsy",
        "semantic_group": "PROC",
        "semantic_types": [{"name": "Diagnostic Procedure"}],
    }
    therapeutic_hit = {
        "cui": "C0021430",
        "semantic_group": "PROC",
        "semantic_types": [{"name": "Therapeutic or Preventive Procedure"}],
    }
    lab_relation = {
        "cui": "C0202054",
        "label": "Glycated Hemoglobin Measurement",
        "semantic_type": "laboratory procedure",
    }
    diagnostic_measurement_relation = {
        "cui": "C0262923",
        "label": "Urine protein test",
        "semantic_type": "diagnostic procedure",
    }
    weak_ccpss_lab_relation = {
        "cui": "C0741817",
        "label": "BUN MG DL CR MG DL",
        "source": "CCPSS",
        "rela": "clinically_associated_with",
        "semantic_type": "laboratory procedure",
        "source_name": "Acute myocardial infarction",
    }

    assert not hit_matches_semantic_bucket(lab_hit, proc_bucket)
    assert hit_matches_semantic_bucket(lab_hit, observation_bucket)
    assert not hit_matches_semantic_bucket(diagnostic_measurement_hit, proc_bucket)
    assert hit_matches_semantic_bucket(diagnostic_measurement_hit, observation_bucket)
    assert hit_matches_semantic_bucket(diagnostic_procedure_hit, proc_bucket)
    assert not hit_matches_semantic_bucket(diagnostic_procedure_hit, observation_bucket)
    assert hit_matches_semantic_bucket(therapeutic_hit, proc_bucket)
    assert not relation_visible_in_semantic_bucket(lab_relation, proc_bucket, "PROC")
    assert relation_visible_in_semantic_bucket(lab_relation, observation_bucket, "PROC")
    assert not relation_visible_in_semantic_bucket(diagnostic_measurement_relation, proc_bucket, "PROC")
    assert relation_visible_in_semantic_bucket(diagnostic_measurement_relation, observation_bucket, "PROC")
    assert not relation_visible_in_semantic_bucket(weak_ccpss_lab_relation, observation_bucket, "PROC")


def test_external_cui_vectors_parse_json_and_csv_overlap_only(tmp_path: Path) -> None:
    json_path = tmp_path / "bioconceptvec.json"
    csv_path = tmp_path / "cui2vec.csv"
    json_path.write_text(
        '{"C0004238":[1,0,0],"UMLS:C0011849":[0.9,0.1,0],"MESH:D000001":[0,1,0]}',
        encoding="utf-8",
    )
    csv_path.write_text(
        "cui,x1,x2,x3\n"
        "C0004238,1,0,0\n"
        "not-a-cui,0,1,0\n"
        "UMLS:C0003611,0,0.9,0.1\n",
        encoding="utf-8",
    )

    json_records = list(iter_external_cui_vectors(json_path))
    assert [(record.identifier, record.cui) for record in json_records] == [
        ("C0004238", "C0004238"),
        ("UMLS:C0011849", "C0011849"),
        ("MESH:D000001", ""),
    ]
    assert [record.cui for record in iter_external_cui_vectors(csv_path)] == ["C0004238", "C0003611"]


def test_external_cui_vector_index_feeds_related_bundle_and_semantic_views(tmp_path: Path) -> None:
    external_vectors = tmp_path / "external.json"
    external_vectors.write_text(
        '{"C0004238":[1,0,0],"Disease_MESH_D003":[0.95,0.05,0],"Procedure_MESH_D004":[0,1,0],"MESH:D000001":[-1,0,0]}',
        encoding="utf-8",
    )
    mrconso = tmp_path / "MRCONSO.RRF"
    mrconso.write_text(
        "C0004238|ENG|P|L1|PF|S1|Y|A1||SCUI1|SDUI1|ICD10CM|PT|I48.91|Atrial fibrillation|0|N||\n"
        "C0011849|ENG|P|L2|PF|S2|Y|A2|||D003|MSH|MH|D003|Diabetes Mellitus|0|N||\n"
        "C0003611|ENG|P|L3|PF|S3|Y|A3|||D004|MSH|MH|D004|Catheter Ablation|0|N||\n"
        "C0000699|ENG|P|L4|PF|S4|Y|A4|||D000001|MSH|MH|D000001|Calcimycin|0|N||\n",
        encoding="utf-8",
    )
    mrsty = tmp_path / "MRSTY.RRF"
    mrsty.write_text(
        "C0004238|T047|B2.2.1.2.1|Disease or Syndrome|AT1|\n"
        "C0011849|T047|B2.2.1.2.1|Disease or Syndrome|AT2|\n"
        "C0003611|T061|B1.3.1.2|Therapeutic or Preventive Procedure|AT3|\n",
        encoding="utf-8",
    )
    documents = build_documents(
        [
            EvidenceRecord("e1", "C0004238", "atrial fibrillation anticoagulation", "pubmed", "pubmed_clinical_context", 2),
        ]
    )
    docs_path = tmp_path / "docs.jsonl"
    vectors_path = tmp_path / "vectors.jsonl"
    code_path = tmp_path / "codes.sqlite"
    external_index_path = tmp_path / "external.sqlite"
    semantic_type_path = tmp_path / "semantic_types.sqlite"
    write_jsonl(docs_path, documents)
    write_jsonl(vectors_path, embed_documents(documents, HashingEmbedder(dim=16)))
    build_code_index(mrconso_path=mrconso, out_path=code_path, replace=True)
    stats = build_external_cui_vector_index(
        inputs=[(external_vectors, "BioConceptVec", "json")],
        doc_paths=[docs_path],
        code_index_path=code_path,
        out_path=external_index_path,
        top_k=2,
        replace=True,
    )
    build_semantic_type_index(mrsty_path=mrsty, out_path=semantic_type_path, replace=True)

    external_index = ExternalCuiVectorIndex(external_index_path)
    external_neighbors = external_index.lookup("C0004238", limit_per_source=2)
    external_index.close()
    index = SearchIndex(
        vector_paths=[vectors_path],
        doc_paths=[docs_path],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        semantic_type_index_path=semantic_type_path,
        external_cui_vector_index_path=external_index_path,
    )
    bundle = index.related_bundle("C0004238", top_k=2)
    hit = index.hit_from_record(index.best_record_for_cui("C0004238"), score=1.0)
    index.attach_related_concepts([hit])
    views = index.semantic_views_for_hit(hit)

    assert stats["neighbors"] == 2
    assert external_neighbors[0]["cui"] == "C0011849"
    assert bundle["related_source"] == "external_embeddings"
    assert bundle["external_embedding_neighbors"][0]["source"] == "BioConceptVec"
    assert hit["external_embedding_neighbors"][0]["cui"] == "C0011849"
    assert hit["related_concepts"][0]["relation"] == "external_embedding"
    assert hit["external_embedding_neighbors"][0]["edge"]["type"] == "associated_with"
    assert hit["external_embedding_neighbors"][0]["edge"]["strength"] > 0.99
    assert hit["external_embedding_neighbors"][0]["edge"]["evidence"]["method"] == "co_occurrence"
    assert {view["category"] for view in views} == {"condition", "procedure_test"}


def test_semantic_group_from_types_routes_common_research_views() -> None:
    assert semantic_group_from_types([{"name": "Disease or Syndrome"}]) == "DISO"
    assert semantic_group_from_types([{"name": "Clinical Drug"}]) == "CHEM"
    assert semantic_group_from_types([{"name": "Gene or Genome"}]) == "GENE"
    assert semantic_group_from_types([{"name": "Clinical Attribute"}]) == "OBS"
    assert semantic_group_from_types([{"name": "Laboratory Procedure"}]) == "OBS"
    assert semantic_group_from_types([{"name": "Laboratory or Test Result"}]) == "OBS"
    assert semantic_group_from_types([{"name": "Diagnostic Procedure"}]) == "PROC"
    assert semantic_group_from_types([{"name": "Medical Device"}]) == "DEVI"
    assert semantic_group_from_types([{"name": "Bacterium"}]) == "LIVB"
    assert semantic_group_from_types([{"name": "Body Part, Organ, or Organ Component"}]) == "ANAT"


def test_relation_index_display_label_normalizes_semicolon_inversion() -> None:
    assert display_label("failure; heart") == "heart failure"
    assert display_label("Heart failure") == "Heart failure"


def test_universal_relationship_edge_has_required_attributes() -> None:
    edge = universal_relationship_edge(
        subject_cui="C4508938",
        object_cui="C0184567",
        relation="indicated_for",
        rela="used for acute pain",
        relation_group="treatment",
        source="wikipedia",
        direction="outgoing",
        row={
            "rank": 1,
            "supporting_pmids": ["1", "2"],
            "clinical_setting": "inpatient",
        },
    )

    assert edge["subject"] == "C4508938"
    assert edge["object"] == "C0184567"
    assert edge["type"] == "treats"
    assert edge["directionality"] == "subject_to_object"
    assert isinstance(edge["strength"], float)
    assert edge["strength_metric"] == "normalized_score"
    assert edge["evidence"]["method"] == "literature_mined"
    assert edge["evidence"]["provenance"] == "wikipedia"
    assert edge["evidence"]["support_count"] == 2
    assert edge["context"] == {"clinical_setting": "inpatient"}
    assert isinstance(edge["confidence"], float)


def test_ohdsi_mining_atlas_cohort_json_emits_likely_indication(tmp_path: Path) -> None:
    mapping = tmp_path / "omop_cui_map.csv"
    mapping.write_text(
        "concept_id,cui,vocabulary_id,concept_code\n"
        "100,C0025598,RxNorm,6809\n"
        "200,C0011860,SNOMED,44054006\n",
        encoding="utf-8",
    )
    atlas = tmp_path / "atlas_metformin.json"
    atlas.write_text(
        json.dumps(
            {
                "id": 101,
                "name": "Metformin new users with type 2 diabetes",
                "ConceptSets": [
                    {
                        "id": 0,
                        "name": "Metformin",
                        "expression": {
                            "items": [
                                {
                                    "concept": {
                                        "CONCEPT_ID": 100,
                                        "CONCEPT_NAME": "metformin",
                                        "DOMAIN_ID": "Drug",
                                        "VOCABULARY_ID": "RxNorm",
                                        "CONCEPT_CODE": "6809",
                                    }
                                }
                            ]
                        },
                    },
                    {
                        "id": 1,
                        "name": "Type 2 diabetes",
                        "expression": {
                            "items": [
                                {
                                    "concept": {
                                        "CONCEPT_ID": 200,
                                        "CONCEPT_NAME": "type 2 diabetes mellitus",
                                        "DOMAIN_ID": "Condition",
                                        "VOCABULARY_ID": "SNOMED",
                                        "CONCEPT_CODE": "44054006",
                                    }
                                }
                            ]
                        },
                    },
                ],
                "PrimaryCriteria": {"CriteriaList": [{"DrugExposure": {"CodesetId": 0}}]},
                "InclusionRules": [
                    {
                        "id": 7,
                        "name": "T2D before index",
                        "expression": {
                            "CriteriaList": [
                                {"Criteria": {"ConditionOccurrence": {"CodesetId": 1}}}
                            ]
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = mine_public_ohdsi_artifacts(atlas_paths=[atlas], omop_cui_map_path=mapping)

    rows = [row for row in result.edges if row["relationship_type"] == "likely_indication"]
    assert len(rows) == 1
    row = rows[0]
    assert row["source_class"] == "atlas_cohort_json"
    assert row["subject_cui"] == "C0025598"
    assert row["object_cui"] == "C0011860"
    assert row["edge"]["strength_metric"] == "cohort_rule_score"
    assert row["edge"]["evidence"]["method"] == "curated"
    assert result.cohort_targets["101"].drug_concepts[0].cui == "C0025598"


def test_ohdsi_mining_cohort_diagnostics_adds_prevalence_and_temporal_precedence(tmp_path: Path) -> None:
    mapping = tmp_path / "omop_cui_map.csv"
    mapping.write_text(
        "concept_id,cui,vocabulary_id,concept_code\n"
        "100,C0025598,RxNorm,6809\n"
        "200,C0011860,SNOMED,44054006\n",
        encoding="utf-8",
    )
    atlas = tmp_path / "atlas_metformin.json"
    atlas.write_text(
        json.dumps(
            {
                "id": 101,
                "name": "Metformin cohort",
                "ConceptSets": [
                    {
                        "id": 0,
                        "name": "Metformin",
                        "expression": {
                            "items": [
                                {
                                    "concept": {
                                        "CONCEPT_ID": 100,
                                        "CONCEPT_NAME": "metformin",
                                    }
                                }
                            ]
                        },
                    }
                ],
                "PrimaryCriteria": {"CriteriaList": [{"DrugExposure": {"CodesetId": 0}}]},
            }
        ),
        encoding="utf-8",
    )
    diagnostics = tmp_path / "cohort_diagnostics.csv"
    diagnostics.write_text(
        "cohort_id,concept_id,prevalence,count,cohort_count,time_window\n"
        "101,200,0.73,730,1000,baseline before index\n",
        encoding="utf-8",
    )

    result = mine_public_ohdsi_artifacts(
        atlas_paths=[atlas],
        cohort_diagnostics_paths=[diagnostics],
        omop_cui_map_path=mapping,
    )

    prevalence_edges = [
        row
        for row in result.edges
        if row["source_class"] == "cohort_diagnostics"
        and row["subject_cui"] == "C0025598"
        and row["object_cui"] == "C0011860"
    ]
    temporal_edges = [
        row
        for row in result.edges
        if row["source_class"] == "cohort_diagnostics_temporal"
        and row["subject_cui"] == "C0011860"
        and row["object_cui"] == "C0025598"
    ]
    assert prevalence_edges
    assert prevalence_edges[0]["edge"]["strength"] == 0.73
    assert prevalence_edges[0]["edge"]["strength_metric"] == "conditional_prevalence"
    assert prevalence_edges[0]["edge"]["evidence"]["conditional_prevalence"] == 0.73
    assert temporal_edges
    assert temporal_edges[0]["edge"]["type"] == "precedes"
    assert temporal_edges[0]["edge"]["strength_metric"] == "temporal_precedence_score"


def test_ohdsi_mining_estimation_and_plp_edges_are_quantitative_and_noncausal(tmp_path: Path) -> None:
    estimation = tmp_path / "estimation.csv"
    estimation.write_text(
        "exposure_cui,outcome_cui,hazard_ratio,lower_95,upper_95,target_count\n"
        "C0025598,C0004238,1.42,1.18,1.71,2500\n",
        encoding="utf-8",
    )
    plp = tmp_path / "plp.csv"
    plp.write_text(
        "feature_cui,outcome_cui,importance,auc,external_validation\n"
        "C0011860,C0004238,0.22,0.81,true\n",
        encoding="utf-8",
    )

    result = mine_public_ohdsi_artifacts(
        estimation_result_paths=[estimation],
        plp_output_paths=[plp],
    )

    risk_edges = [row for row in result.edges if row["relationship_type"] == "increases_risk_of"]
    assert risk_edges
    risk_edge = risk_edges[0]["edge"]
    assert risk_edge["strength_metric"] == "hazard_ratio_normalized"
    assert risk_edge["evidence"]["quantitative"]["estimate"] == 1.42
    assert risk_edge["evidence"]["quantitative"]["lower_95"] == 1.18
    assert risk_edge["confidence"] > 0.7

    plp_edges = [row for row in result.edges if row["relationship_type"] == "predicts"]
    assert plp_edges
    plp_edge = plp_edges[0]["edge"]
    assert plp_edge["context"]["noncausal"] is True
    assert plp_edge["evidence"]["method"] == "prediction_model"
    assert plp_edge["evidence"]["quantitative"]["feature_importance"] == 0.22


def test_ohdsi_mining_rejects_patient_level_rows(tmp_path: Path) -> None:
    diagnostics = tmp_path / "patient_level.csv"
    diagnostics.write_text(
        "personId,cohort_id,concept_id,prevalence\n"
        "1,101,200,0.8\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="patient-level fields"):
        mine_public_ohdsi_artifacts(cohort_diagnostics_paths=[diagnostics])


def test_relationship_edge_index_loads_mined_universal_edges(tmp_path: Path) -> None:
    edges = tmp_path / "ohdsi_edges.jsonl"
    out = tmp_path / "relationship_edges.sqlite"
    write_jsonl(
        edges,
        [
            {
                "source_class": "cohort_diagnostics",
                "subject_cui": "C0025598",
                "subject_label": "metformin",
                "object_cui": "C0011860",
                "object_label": "type 2 diabetes mellitus",
                "relationship_type": "likely_indication",
                "edge": {
                    "subject": "C0025598",
                    "object": "C0011860",
                    "type": "likely_indication",
                    "strength": 0.73,
                    "strength_metric": "conditional_prevalence",
                    "directionality": "subject_to_object",
                    "evidence": {
                        "method": "temporal_analysis",
                        "provenance": "ohdsi_cohort_diagnostics",
                    },
                    "context": {"cohort_id": "101"},
                    "confidence": 0.81,
                },
            }
        ],
    )

    stats = build_relationship_edge_index(edge_paths=[edges], out_path=out, replace=True)
    index = RelationshipEdgeIndex(out)
    outgoing = index.lookup("C0025598")
    incoming = index.lookup_incoming("C0011860")
    index.close()

    assert stats["edges"] == 1
    assert outgoing[0]["cui"] == "C0011860"
    assert outgoing[0]["relationship_type"] == "likely_indication"
    assert outgoing[0]["edge"]["strength"] == 0.73
    assert incoming[0]["cui"] == "C0025598"
    assert incoming[0]["edge"]["confidence"] == 0.81


def test_search_index_uses_relationship_edge_index_in_semantic_views(tmp_path: Path) -> None:
    docs = tmp_path / "docs.jsonl"
    vectors = tmp_path / "vectors.jsonl"
    mrsty = tmp_path / "MRSTY.RRF"
    semantic_type_path = tmp_path / "semantic_types.sqlite"
    edge_jsonl = tmp_path / "edges.jsonl"
    edge_index = tmp_path / "relationship_edges.sqlite"
    write_jsonl(
        docs,
        [
            {
                "doc_id": "C0025598:drug",
                "cui": "C0025598",
                "view": "drug",
                "text": "CUI: C0025598\nUMLS labels:\n- Metformin",
                "evidence_count": 1,
                "sources": ["rxnorm"],
                "labels": ["Metformin"],
                "metadata": {"labels": ["Metformin"], "sources": ["rxnorm"], "evidence_count": 1},
            },
            {
                "doc_id": "C0011860:condition",
                "cui": "C0011860",
                "view": "condition",
                "text": "CUI: C0011860\nUMLS labels:\n- Type 2 diabetes mellitus",
                "evidence_count": 1,
                "sources": ["mesh"],
                "labels": ["Type 2 diabetes mellitus"],
                "metadata": {
                    "labels": ["Type 2 diabetes mellitus"],
                    "sources": ["mesh"],
                    "evidence_count": 1,
                },
            },
        ],
    )
    write_jsonl(
        vectors,
        [
            {
                "doc_id": "C0025598:drug",
                "cui": "C0025598",
                "view": "drug",
                "vector": [1.0] + [0.0] * 15,
                "text": "Metformin",
                "metadata": {},
            },
            {
                "doc_id": "C0011860:condition",
                "cui": "C0011860",
                "view": "condition",
                "vector": [0.0, 1.0] + [0.0] * 14,
                "text": "Type 2 diabetes mellitus",
                "metadata": {},
            },
        ],
    )
    mrsty.write_text(
        "C0025598|T121|A1.4.1.1.1|Pharmacologic Substance|AT1|\n"
        "C0011860|T047|B2.2.1.2.1|Disease or Syndrome|AT2|\n",
        encoding="utf-8",
    )
    build_semantic_type_index(mrsty_path=mrsty, out_path=semantic_type_path, replace=True)
    write_jsonl(
        edge_jsonl,
        [
            {
                "source_class": "atlas_cohort_json",
                "subject_cui": "C0025598",
                "subject_label": "metformin",
                "object_cui": "C0011860",
                "object_label": "type 2 diabetes mellitus",
                "relationship_type": "likely_indication",
                "edge": {
                    "subject": "C0025598",
                    "object": "C0011860",
                    "type": "likely_indication",
                    "strength": 0.72,
                    "strength_metric": "cohort_rule_score",
                    "directionality": "subject_to_object",
                    "evidence": {
                        "method": "curated",
                        "provenance": "atlas_cohort_definition",
                    },
                    "context": {"cohort_id": "101"},
                    "confidence": 0.78,
                },
            }
        ],
    )
    build_relationship_edge_index(edge_paths=[edge_jsonl], out_path=edge_index, replace=True)
    index = SearchIndex(
        vector_paths=[vectors],
        doc_paths=[docs],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        semantic_type_index_path=semantic_type_path,
        relationship_edge_index_path=edge_index,
    )

    relations = index.research_relations_for_cui("C0025598")
    relation = next(item for item in relations if item["cui"] == "C0011860")
    hit = index.hit_from_record(index.best_record_for_cui("C0025598"), score=0.5)
    index.attach_mrrel_rank_signals("metformin diabetes", [hit])

    assert relation["category"] == "condition"
    assert relation["relation"] == "likely_indication"
    assert relation["edge"]["strength"] == 0.72
    assert hit["mrrel_component"] == 0.0
    assert index.status()["relationship_edge_links"] == 1
    assert index.status()["relationship_edges_rank"] is False

    rank_index = SearchIndex(
        vector_paths=[vectors],
        doc_paths=[docs],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        semantic_type_index_path=semantic_type_path,
        relationship_edge_index_path=edge_index,
        relationship_edges_rank=True,
    )
    rank_hit = rank_index.hit_from_record(rank_index.best_record_for_cui("C0025598"), score=0.5)
    rank_index.attach_mrrel_rank_signals("metformin diabetes", [rank_hit])
    assert rank_hit["mrrel_component"] > 0
    assert rank_hit["mrrel_signal_reasons"][0]["cui"] == "C0011860"
    assert rank_index.status()["relationship_edges_rank"] is True


def test_procedure_bundle_builder_structures_ultrasound_cvc(tmp_path: Path) -> None:
    input_path = tmp_path / "procedure_bundles.jsonl"
    out_concepts = tmp_path / "procedure_concepts.jsonl"
    out_relations = tmp_path / "procedure_relations.jsonl"
    out_registry = tmp_path / "procedure_registry.jsonl"
    write_jsonl(
        input_path,
        [
            {
                "preferred_label": "ultrasound-guided central venous catheter placement",
                "open_anchors": [
                    {
                        "cui": "C0184661",
                        "label": "Central Venous Catheterization",
                        "source": "MSH",
                    }
                ],
                "broader": [{"cui": "C0007437", "label": "Catheterization", "source": "MSH"}],
                "target_anatomy": [{"cui": "C0042449", "label": "Veins", "source": "MSH"}],
                "modality_anchors": [{"cui": "C0041618", "label": "Ultrasonography", "source": "MSH"}],
                "device_anchors": [{"cui": "C0085590", "label": "Catheters", "source": "MSH"}],
                "evidence": [
                    {
                        "text": "Procedure note documented ultrasound-guided central venous catheter placement.",
                        "source": "example_open_note",
                    }
                ],
            }
        ],
    )

    stats = build_procedure_bundle_artifacts(
        input_path=input_path,
        out_concepts=out_concepts,
        out_relations=out_relations,
        out_registry=out_registry,
    )
    concepts = list(iter_jsonl(out_concepts))
    relations = list(iter_jsonl(out_relations))

    assert stats == {"bundles": 1, "concepts": 1, "relations": 6, "registry_rows": 1}
    concept = concepts[0]
    assert re.fullmatch(r"NEW\d{7}", concept["concept_id"])
    assert concept["semantic_type"] == "Therapeutic or Preventive Procedure"
    attrs = concept["metadata"]["procedure_attributes"]
    assert attrs["action"] == "placement"
    assert attrs["modality"] == "ultrasound"
    assert attrs["anatomy_route"] == "central venous"
    assert attrs["device"] == "catheter"
    assert attrs["intent"] == "therapeutic/supportive"
    assert any(row["relation"] == "RB" and row["target_cui"] == "C0007437" for row in relations)
    assert any(row["relation"] == "RN" and row["source_cui"] == "C0007437" for row in relations)
    assert any(row["rela"] == "target_anatomy" and row["target_cui"] == "C0042449" for row in relations)


def test_procedure_bundle_builder_endoscopic_biopsy_relations(tmp_path: Path) -> None:
    input_path = tmp_path / "procedure_bundles.jsonl"
    out_concepts = tmp_path / "procedure_concepts.jsonl"
    out_relations = tmp_path / "procedure_relations.jsonl"
    write_jsonl(
        input_path,
        [
            {
                "preferred_label": "endoscopic biopsy of gastric ulcer",
                "broader": [{"cui": "C0005558", "label": "Biopsy", "source": "MSH"}],
                "target_anatomy": [{"cui": "C0038351", "label": "Stomach", "source": "MSH"}],
                "related": [{"cui": "C0017168", "label": "Gastric Ulcer", "source": "MSH"}],
            }
        ],
    )

    build_procedure_bundle_artifacts(
        input_path=input_path,
        out_concepts=out_concepts,
        out_relations=out_relations,
    )
    concept = list(iter_jsonl(out_concepts))[0]
    relations = list(iter_jsonl(out_relations))

    assert concept["semantic_type"] == "Diagnostic Procedure"
    assert concept["metadata"]["procedure_attributes"]["action"] == "biopsy"
    assert concept["metadata"]["procedure_attributes"]["approach"] == "endoscopic"
    assert concept["broader_cuis"] == ["C0005558"]
    assert any(row["relation"] == "RB" and row["target_label"] == "Biopsy" for row in relations)
    assert any(row["rela"] == "target_anatomy" and row["target_label"] == "Stomach" for row in relations)
    assert any(row["rela"] == "related_open_anchor" and row["target_label"] == "Gastric Ulcer" for row in relations)


def test_procedure_bundle_builder_allows_snomed_by_default(tmp_path: Path) -> None:
    input_path = tmp_path / "procedure_bundles.jsonl"
    out_concepts = tmp_path / "procedure_concepts.jsonl"
    out_relations = tmp_path / "procedure_relations.jsonl"
    write_jsonl(
        input_path,
        [
            {
                "preferred_label": "ultrasound-guided central venous catheter placement",
                "open_anchors": [
                    {
                        "cui": "C0184661",
                        "label": "Central venous catheter placement",
                        "source": "SNOMEDCT_US",
                        "code": "123456",
                    }
                ],
            }
        ],
    )

    build_procedure_bundle_artifacts(
        input_path=input_path,
        out_concepts=out_concepts,
        out_relations=out_relations,
    )
    concept = list(iter_jsonl(out_concepts))[0]

    assert concept["metadata"]["open_anchors"][0]["source"] == "SNOMEDCT_US"

    with pytest.raises(ValueError, match="SNOMED CT content"):
        build_procedure_bundle_artifacts(
            input_path=input_path,
            out_concepts=out_concepts,
            out_relations=out_relations,
            allow_snomed=False,
        )


def test_procedure_bundle_public_builder_rejects_cpt_content(tmp_path: Path) -> None:
    input_path = tmp_path / "procedure_bundles.jsonl"
    out_concepts = tmp_path / "procedure_concepts.jsonl"
    out_relations = tmp_path / "procedure_relations.jsonl"
    write_jsonl(
        input_path,
        [
            {
                "preferred_label": "licensed local procedure",
                "open_anchors": [
                    {
                        "cui": "NEW0000001",
                        "source": "CPT",
                        "code": "99999",
                        "descriptor": "licensed CPT descriptor must not ship",
                    }
                ],
            }
        ],
    )

    with pytest.raises(ValueError, match="CPT content"):
        build_procedure_bundle_artifacts(
            input_path=input_path,
            out_concepts=out_concepts,
            out_relations=out_relations,
        )


def test_private_cpt_adapter_is_code_only(tmp_path: Path) -> None:
    adapter = tmp_path / "private_cpt_adapter.csv"
    adapter.write_text(
        "procedure_bundle_id,private_code_system,private_code\n"
        "NEW1234567,CPT,99999\n",
        encoding="utf-8",
    )
    assert validate_private_cpt_adapter(adapter) == {"private_cpt_adapter_rows": 1}

    bad_adapter = tmp_path / "bad_private_cpt_adapter.csv"
    bad_adapter.write_text(
        "procedure_bundle_id,private_code_system,private_code,long_descriptor\n"
        "NEW1234567,CPT,99999,descriptor must stay private\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="descriptor-like fields"):
        validate_private_cpt_adapter(bad_adapter)


def test_label_fallback_scores_single_term_rescues_but_not_components() -> None:
    rescue_score = LabelFallback.label_score(
        token_count=1,
        query_content_tokens=1,
        span_content_tokens=1,
        unique_cui_count=1,
        is_preferred=True,
    )
    component_score = LabelFallback.label_score(
        token_count=1,
        query_content_tokens=3,
        span_content_tokens=1,
        unique_cui_count=1,
        is_preferred=True,
    )
    assert rescue_score > 1.0
    assert component_score < 0.8


def test_generic_umls_labels_are_suppressed_from_label_index(tmp_path: Path) -> None:
    mrconso = tmp_path / "MRCONSO.RRF"
    mrconso.write_text(
        "C4489374|ENG|P|L1|PF|S1|Y|A1|||D001|NCI|PT|D001|Extremely Limited|0|N||\n"
        "C0036983|ENG|P|L2|PF|S2|Y|A2|||D002|MSH|MH|D002|Septic shock|0|N||\n",
        encoding="utf-8",
    )
    index_path = tmp_path / "labels.sqlite"
    count = build_label_index(mrconso_path=mrconso, out_path=index_path, replace=True)
    assert count == 1
    with LabelIndex(index_path) as index:
        assert index.lookup("extremely limited") == []
        assert index.lookup("septic shock")


def test_generic_filter_blocks_known_bad_concepts() -> None:
    assert is_blocked_generic_concept("C4489374", "Extremely Limited")
    assert is_blocked_generic_concept("C0683954", "Study Results")
    assert not is_blocked_generic_concept("C0036983", "Septic shock")


def test_extension_concept_ids_are_provisional_and_stable() -> None:
    concept_id = stable_extension_id(
        "post-viral exertional intolerance phenotype",
        semantic_type="Finding",
    )
    assert concept_id == stable_extension_id(
        "Post Viral Exertional Intolerance Phenotype",
        semantic_type="finding",
    )
    assert re.fullmatch(r"NEW\d{7}", concept_id)
    assert not concept_id.startswith("C")


def test_extension_concept_rejects_official_cui_shape() -> None:
    with pytest.raises(ValueError, match="official UMLS CUI"):
        concept_from_payload(
            {
                "concept_id": "c1234567",
                "preferred_label": "new candidate concept",
            }
        )


def test_build_extension_concept_artifacts(tmp_path: Path) -> None:
    input_path = tmp_path / "extension_candidates.jsonl"
    out_docs = tmp_path / "extension_docs.jsonl"
    out_evidence = tmp_path / "extension_evidence.jsonl"
    out_registry = tmp_path / "extension_registry.jsonl"
    evidence_text = "Patients described persistent exertional intolerance after infection."
    write_jsonl(
        input_path,
        [
            {
                "preferred_label": "post-viral exertional intolerance phenotype",
                "aliases": ["post viral exertional intolerance", "Post-viral exertional intolerance phenotype"],
                "semantic_type": "Finding",
                "definition": "Persistent exertional intolerance after viral illness.",
                "status": "reviewed",
                "broader_cuis": ["C0012634"],
                "close_match_cuis": ["C5203670"],
                "evidence": [
                    {
                        "text": evidence_text,
                        "source": "pmc_oa",
                        "weight": 1.0,
                        "metadata": {"pmcid": "PMC1"},
                    },
                    {
                        "text": evidence_text,
                        "source": "pubmed_bulk",
                        "weight": 2.0,
                        "metadata": {"pmid": "41800001"},
                    },
                ],
                "metadata": {"reviewer": "unit-test"},
            },
            {
                "preferred_label": "unreviewed extension candidate",
                "status": "candidate",
                "evidence": [{"text": "Candidate evidence should be filtered out."}],
            },
        ],
    )
    doc_count, evidence_count = build_extension_concept_artifacts(
        input_path=input_path,
        out_docs=out_docs,
        out_evidence=out_evidence,
        out_registry=out_registry,
        include_status={"reviewed"},
    )
    docs = list(iter_jsonl(out_docs))
    evidence = list(iter_jsonl(out_evidence))
    registry = list(iter_jsonl(out_registry))

    assert doc_count == 1
    assert evidence_count == 2
    assert re.fullmatch(r"NEW\d{7}", docs[0]["cui"])
    assert docs[0]["view"] == "extension_concept"
    assert docs[0]["metadata"]["concept_origin"] == "extension"
    assert docs[0]["metadata"]["status"] == "reviewed"
    assert docs[0]["metadata"]["broader_cuis"] == ["C0012634"]
    assert docs[0]["text"].count(evidence_text) == 1
    assert evidence[0]["cui"] == docs[0]["cui"]
    assert evidence[0]["metadata"]["extension_concept_id"] == docs[0]["cui"]
    assert registry[0]["concept_id"] == docs[0]["cui"]
    assert registry[0]["evidence_count"] == 2


def test_builds_separate_evidence_views() -> None:
    evidence = [
        EvidenceRecord("e1", "C0004238", "a fib", "log", "failed_query", 5),
        EvidenceRecord("e2", "C0004238", "patient has a fib", "notes", "clinical_snippet", 1),
    ]
    documents = build_documents(evidence)
    views = {document.view for document in documents}
    assert views == {"query_language", "prose_evidence"}


def test_hashing_search_finds_query_evidence() -> None:
    evidence = [
        EvidenceRecord("e1", "C0004238", "a fib", "log", "failed_query", 5),
        EvidenceRecord("e2", "C0011849", "sugar disease", "log", "failed_query", 4),
    ]
    documents = build_documents(evidence)
    embedder = HashingEmbedder(dim=128)
    vectors = embed_documents(documents, embedder)
    hits = search_vectors(vectors, "a fib", embedder, top_k=2)
    assert hits[0].cui == "C0004238"


def test_vector_metadata_does_not_duplicate_document_by_default() -> None:
    evidence = [EvidenceRecord("e1", "C0004238", "a fib", "log", "failed_query", 5)]
    documents = build_documents(evidence)
    vectors = embed_documents(documents, HashingEmbedder(dim=8))
    assert "document" not in vectors[0].metadata
    assert vectors[0].metadata["evidence_count"] == 1


def test_embed_can_omit_text_and_round_vectors() -> None:
    evidence = [EvidenceRecord("e1", "C0004238", "a fib", "log", "failed_query", 5)]
    documents = build_documents(evidence)
    vectors = embed_documents(
        documents,
        HashingEmbedder(dim=8),
        omit_text=True,
        vector_precision=3,
    )
    assert vectors[0].text == ""
    assert all(value == round(value, 3) for value in vectors[0].vector)


def test_provenance_index_returns_pubmed_sources(tmp_path: Path) -> None:
    evidence_path = tmp_path / "evidence.jsonl"
    displayed = EvidenceRecord(
        "e1",
        "C0036983",
        "vasopressor therapy for septic shock",
        "pubmed",
        "pubmed_clinical_context",
        1,
        {"pmid": "12345", "corpus_doc_id": "pubmed:12345", "matched_label": "Septic shock"},
    )
    write_jsonl(
        evidence_path,
        [
            displayed,
            EvidenceRecord(
                "e2",
                "C0036983",
                "non-displayed source text",
                "pubmed",
                "pubmed_clinical_context",
                1,
                {"pmid": "67890", "corpus_doc_id": "pubmed:67890"},
            ),
        ],
    )
    docs_path = tmp_path / "docs.jsonl"
    write_jsonl(docs_path, build_documents([displayed]))
    sqlite_path = tmp_path / "provenance.sqlite"
    stats = build_provenance_index(
        evidence_paths=[evidence_path],
        sqlite_path=sqlite_path,
        document_paths=[docs_path],
        replace=True,
    )
    index = ProvenanceIndex(sqlite_path)
    sources = index.lookup_sources(
        "C0036983:pubmed_clinical_context",
        "vasopressor therapy for septic shock",
    )
    assert stats["source_refs"] == 1
    assert stats["skipped_not_in_documents"] == 1
    assert sources[0]["label"] == "PubMed PMID:12345"
    assert sources[0]["url"] == "https://pubmed.ncbi.nlm.nih.gov/12345/"


def test_provenance_index_returns_pmc_oa_sources(tmp_path: Path) -> None:
    evidence_path = tmp_path / "evidence.jsonl"
    displayed = EvidenceRecord(
        "e1",
        "C0036983",
        "vasopressor therapy for septic shock",
        "pmc_oa",
        "pmc_oa_clinical_context",
        1,
        {
            "pmcid": "PMC123456",
            "pmid": "41800002",
            "doi": "10.2/example",
            "license": "CC BY",
            "corpus_doc_id": "PMCID:PMC123456",
            "matched_label": "Septic shock",
        },
    )
    write_jsonl(evidence_path, [displayed])
    docs_path = tmp_path / "docs.jsonl"
    write_jsonl(docs_path, build_documents([displayed]))
    sqlite_path = tmp_path / "provenance.sqlite"
    build_provenance_index(
        evidence_paths=[evidence_path],
        sqlite_path=sqlite_path,
        document_paths=[docs_path],
        replace=True,
    )
    index = ProvenanceIndex(sqlite_path)
    sources = index.lookup_sources(
        "C0036983:pmc_oa_clinical_context",
        "vasopressor therapy for septic shock",
    )
    assert sources[0]["label"] == "PMC OA PMC123456"
    assert sources[0]["url"] == "https://pmc.ncbi.nlm.nih.gov/articles/PMC123456/"
    assert sources[0]["license"] == "CC BY"


def test_compact_vectors_round_trip_metadata_and_float32(tmp_path: Path) -> None:
    documents = build_documents([EvidenceRecord("e1", "C0004238", "a fib", "log", "failed_query", 5)])
    vectors = embed_documents(documents, HashingEmbedder(dim=8))
    vectors_path = tmp_path / "vectors.jsonl"
    write_jsonl(vectors_path, vectors)

    manifest = write_compact_vectors(vectors_path=vectors_path, out_prefix=tmp_path / "vectors")
    compact = list(iter_compact_vectors(manifest["vectors"].replace(".vectors.f32", ".manifest.json")))

    assert manifest["count"] == 1
    assert manifest["dims"] == 8
    assert compact[0].doc_id == vectors[0].doc_id
    assert compact[0].cui == vectors[0].cui
    assert len(compact[0].vector) == 8


def test_elastic_export_bulk_and_mapping(tmp_path: Path) -> None:
    evidence = [EvidenceRecord("e1", "C0004238", "a fib", "log", "failed_query", 5)]
    documents = build_documents(evidence)
    vectors = embed_documents(documents, HashingEmbedder(dim=8))
    vectors_path = tmp_path / "vectors.jsonl"
    write_jsonl(vectors_path, vectors)
    bulk_path = tmp_path / "bulk.ndjson"
    count = write_elastic_bulk(bulk_path, vectors_path, index="concept-vectors")
    lines = bulk_path.read_text(encoding="utf-8").splitlines()
    mapping = elastic_mapping(dims=8)
    assert count == 1
    assert len(lines) == 2
    assert '"_index":"concept-vectors"' in lines[0]
    assert '"vector"' in lines[1]
    assert '"sources":["log"]' in lines[1]
    assert mapping["mappings"]["properties"]["vector"]["dims"] == 8


def test_elastic_export_sharded_bulk(tmp_path: Path) -> None:
    evidence = [
        EvidenceRecord("e1", "C0004238", "a fib", "log", "failed_query", 5),
        EvidenceRecord("e2", "C0011849", "sugar disease", "log", "failed_query", 4),
    ]
    vectors = embed_documents(build_documents(evidence), HashingEmbedder(dim=8))
    vectors_path = tmp_path / "vectors.jsonl"
    write_jsonl(vectors_path, vectors)
    count, paths = write_elastic_bulk_sharded(
        tmp_path / "bulk.ndjson",
        vectors_path,
        index="concept-vectors",
        docs_per_file=1,
    )
    assert count == 2
    assert len(paths) == 2
    assert all(path.read_bytes().endswith(b"\n") for path in paths)


def test_elastic_client_helpers_resolve_parts_and_build_knn(tmp_path: Path) -> None:
    (tmp_path / "bulk.part-000001.ndjson").write_text("{}\n", encoding="utf-8")
    (tmp_path / "bulk.part-000002.ndjson").write_text("{}\n", encoding="utf-8")
    paths = resolve_bulk_paths([tmp_path / "bulk.ndjson"])
    body = build_knn_search_body(vector=[0.1, 0.2], k=5, num_candidates=25)
    assert [path.name for path in paths] == ["bulk.part-000001.ndjson", "bulk.part-000002.ndjson"]
    assert body["knn"]["k"] == 5
    assert body["knn"]["num_candidates"] == 25


def test_sqlite_document_builder_matches_views(tmp_path: Path) -> None:
    evidence_path = tmp_path / "evidence.jsonl"
    write_jsonl(
        evidence_path,
        [
            EvidenceRecord("e1", "C0004238", "a fib", "log", "failed_query", 5),
            EvidenceRecord("e2", "C0004238", "a fib", "log", "failed_query", 2),
            EvidenceRecord("e3", "C0004238", "patient has a fib", "notes", "clinical_snippet", 1),
            EvidenceRecord("e4", "C9999999", "admin code", "mimic_demo_drg", "context", 1),
        ],
    )
    out_path = tmp_path / "docs.jsonl"
    evidence_count, doc_count = build_documents_sqlite(
        evidence_paths=[evidence_path],
        out_path=out_path,
        sqlite_path=tmp_path / "docs.sqlite",
        exclude_source={"mimic_demo_drg"},
        replace=True,
    )
    assert evidence_count == 3
    assert doc_count == 2
    payload = out_path.read_text(encoding="utf-8")
    assert "query_language" in payload
    assert "prose_evidence" in payload
    assert "mimic_demo_drg" not in payload


def test_ncbi_api_key_defaults_to_env(monkeypatch) -> None:
    monkeypatch.setenv("NCBI", "test-key")
    params = {"db": "pubmed"}
    add_ncbi_api_key(params)
    assert resolve_ncbi_api_key() == "test-key"
    assert params["api_key"] == "test-key"


def test_ncbi_api_key_falls_back_to_apikey_env(monkeypatch) -> None:
    monkeypatch.delenv("NCBI", raising=False)
    monkeypatch.setenv("APIKEY", "fallback-key")
    params = {"db": "pubmed"}
    add_ncbi_api_key(params)
    assert resolve_ncbi_api_key() == "fallback-key"
    assert params["api_key"] == "fallback-key"


def test_read_pubmed_topics_tsv(tmp_path: Path) -> None:
    topics_path = tmp_path / "topics.tsv"
    topics_path.write_text(
        "topic\tterm\tretmax\n"
        "cardio\tatrial fibrillation\t25\n"
        "infectious\tpneumonia\t\n",
        encoding="utf-8",
    )
    topics = read_pubmed_topics(topics_path, default_retmax=10)
    assert topics == [
        PubMedTopic("cardio", "atrial fibrillation", 25),
        PubMedTopic("infectious", "pneumonia", 10),
    ]


def test_pubmed_bulk_recent_files_are_high_numbered_first(tmp_path: Path) -> None:
    files = recent_baseline_files(year=2026, latest_number=1334, count=3, out_dir=tmp_path)
    assert [file.name for file in files] == [
        "pubmed26n1334.xml.gz",
        "pubmed26n1333.xml.gz",
        "pubmed26n1332.xml.gz",
    ]
    assert baseline_file_name(2026, 1) == "pubmed26n0001.xml.gz"


def test_pubmed_bulk_parser_streams_article_documents(tmp_path: Path) -> None:
    xml_path = tmp_path / "pubmed26n1334.xml"
    xml_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation Status="Publisher">
      <PMID>41800001</PMID>
      <Article>
        <Journal>
          <JournalIssue><PubDate><Year>2026</Year></PubDate></JournalIssue>
          <Title>Example Journal</Title>
        </Journal>
        <ArticleTitle>Recent sepsis evidence</ArticleTitle>
        <Abstract><AbstractText>Vasopressors and lactate clearance are discussed.</AbstractText></Abstract>
        <PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList><ArticleId IdType="doi">10.1/example</ArticleId></ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
""",
        encoding="utf-8",
    )
    documents = list(iter_pubmed_bulk_documents([xml_path]))
    assert len(documents) == 1
    assert documents[0].doc_id == "PMID:41800001"
    assert documents[0].source == "pubmed_bulk"
    assert "lactate clearance" in documents[0].text
    assert documents[0].metadata["publication_year"] == "2026"
    assert documents[0].metadata["doi"] == "10.1/example"


def test_pmc_oa_article_parser_builds_full_text_document() -> None:
    root = ET.fromstring(
        """<?xml version="1.0" encoding="UTF-8"?>
<article>
  <front>
    <journal-meta>
      <journal-title-group><journal-title>Example Open Journal</journal-title></journal-title-group>
    </journal-meta>
    <article-meta>
      <article-id pub-id-type="pmc">123456</article-id>
      <article-id pub-id-type="pmid">41800002</article-id>
      <article-id pub-id-type="doi">10.2/example</article-id>
      <title-group><article-title>Open access sepsis evidence</article-title></title-group>
      <pub-date><year>2026</year></pub-date>
      <permissions><license license-type="CC BY"/></permissions>
      <abstract><p>Abstract mentions septic shock and lactate.</p></abstract>
    </article-meta>
  </front>
  <body>
    <sec>
      <title>Results</title>
      <p>Patients with septic shock received vasopressors in the intensive care unit.</p>
    </sec>
  </body>
</article>
"""
    )
    document = pmc_oa_article_to_document(root, query="septic shock")

    assert document is not None
    assert document.doc_id == "PMCID:PMC123456"
    assert document.source == "pmc_oa"
    assert document.title == "Open access sepsis evidence"
    assert "vasopressors" in document.text
    assert document.metadata["pmcid"] == "PMC123456"
    assert document.metadata["pmid"] == "41800002"
    assert document.metadata["doi"] == "10.2/example"
    assert document.metadata["license"] == "CC BY"
    assert document.metadata["source_url"] == "https://pmc.ncbi.nlm.nih.gov/articles/PMC123456/"


def test_pmc_oa_query_adds_open_access_filter() -> None:
    assert pmc_open_access_query("asthma") == "(asthma) AND open_access[filter]"


def test_pubmed_bulk_md5_parser() -> None:
    assert parse_md5_payload("MD5 (pubmed26n1334.xml.gz) = ABCDEF1234567890ABCDEF1234567890") == (
        "abcdef1234567890abcdef1234567890"
    )


def test_fetch_pubmed_topic_documents_dedupes_pmids(monkeypatch) -> None:
    def fake_fetch_pubmed_documents(**kwargs):
        term = kwargs["term"]
        if term == "first":
            yield CorpusDocument("PMID:1", "pubmed", "same", metadata={"pmid": "1", "query": term})
            yield CorpusDocument("PMID:2", "pubmed", "unique", metadata={"pmid": "2", "query": term})
        else:
            yield CorpusDocument("PMID:1", "pubmed", "same again", metadata={"pmid": "1", "query": term})
            yield CorpusDocument("PMID:3", "pubmed", "third", metadata={"pmid": "3", "query": term})

    monkeypatch.setattr(fetchers, "fetch_pubmed_documents", fake_fetch_pubmed_documents)
    documents = list(
        fetch_pubmed_topic_documents(
            [PubMedTopic("one", "first"), PubMedTopic("two", "second")],
            default_retmax=10,
        )
    )
    assert [document.doc_id for document in documents] == ["PMID:1", "PMID:2", "PMID:3"]
    assert documents[0].metadata["topic"] == "one"
    assert documents[-1].metadata["topic"] == "two"


def test_fetch_europepmc_topic_documents_dedupes_pmids(monkeypatch) -> None:
    def fake_fetch_europepmc_documents(**kwargs):
        query = kwargs["query"]
        if query == "first":
            yield CorpusDocument("EUROPEPMC:MED:1", "europepmc", "same", metadata={"pmid": "1", "query": query})
            yield CorpusDocument("EUROPEPMC:MED:2", "europepmc", "unique", metadata={"pmid": "2", "query": query})
        else:
            yield CorpusDocument("EUROPEPMC:MED:1", "europepmc", "same again", metadata={"pmid": "1", "query": query})
            yield CorpusDocument("EUROPEPMC:PMC:3", "europepmc", "third", metadata={"pmcid": "PMC3", "query": query})

    monkeypatch.setattr(fetchers, "fetch_europepmc_documents", fake_fetch_europepmc_documents)
    documents = list(
        fetch_europepmc_topic_documents(
            [PubMedTopic("one", "first"), PubMedTopic("two", "second")],
            default_max_records=10,
        )
    )
    assert [document.doc_id for document in documents] == [
        "EUROPEPMC:MED:1",
        "EUROPEPMC:MED:2",
        "EUROPEPMC:PMC:3",
    ]
    assert documents[-1].metadata["topic"] == "two"


def test_fetch_pmc_oa_topic_documents_dedupes_pmcids(monkeypatch) -> None:
    def fake_fetch_pmc_oa_documents(**kwargs):
        query = kwargs["query"]
        if query == "first":
            yield CorpusDocument("PMCID:PMC1", "pmc_oa", "same", metadata={"pmcid": "PMC1", "query": query})
            yield CorpusDocument("PMCID:PMC2", "pmc_oa", "unique", metadata={"pmcid": "PMC2", "query": query})
        else:
            yield CorpusDocument("PMCID:PMC1", "pmc_oa", "same again", metadata={"pmcid": "PMC1", "query": query})
            yield CorpusDocument("PMCID:PMC3", "pmc_oa", "third", metadata={"pmcid": "PMC3", "query": query})

    monkeypatch.setattr(fetchers, "fetch_pmc_oa_documents", fake_fetch_pmc_oa_documents)
    documents = list(
        fetch_pmc_oa_topic_documents(
            [PubMedTopic("one", "first"), PubMedTopic("two", "second")],
            default_max_records=10,
        )
    )
    assert [document.doc_id for document in documents] == [
        "PMCID:PMC1",
        "PMCID:PMC2",
        "PMCID:PMC3",
    ]
    assert documents[0].metadata["topic"] == "one"
    assert documents[-1].metadata["topic"] == "two"


def test_merge_corpus_documents_dedupes_cross_source_pmids(tmp_path: Path) -> None:
    pubmed_path = tmp_path / "pubmed.jsonl"
    europepmc_path = tmp_path / "europepmc.jsonl"
    write_jsonl(
        pubmed_path,
        [
            CorpusDocument(
                "PMID:1",
                "pubmed",
                "pubmed text",
                title="Shared abstract title",
                metadata={"pmid": "1"},
            )
        ],
    )
    write_jsonl(
        europepmc_path,
        [
            CorpusDocument(
                "EUROPEPMC:MED:1",
                "europepmc",
                "duplicate text",
                title="Shared abstract title",
                metadata={"pmid": "1"},
            ),
            CorpusDocument(
                "EUROPEPMC:MED:2",
                "europepmc",
                "new text",
                title="Different abstract title",
                metadata={"pmid": "2"},
            ),
        ],
    )
    documents = list(merge_corpus_documents([pubmed_path, europepmc_path]))
    assert [document.doc_id for document in documents] == ["PMID:1", "EUROPEPMC:MED:2"]


def test_filter_evidence_excludes_source() -> None:
    records = [
        EvidenceRecord("e1", "C1", "clinical text", "mimic_demo_microbiology", "context"),
        EvidenceRecord("e2", "C2", "admin text", "mimic_demo_drg", "context"),
    ]
    filtered = list(filter_evidence_records(records, exclude_source={"mimic_demo_drg"}))
    assert [record.evidence_id for record in filtered] == ["e1"]


def test_semantic_profiles_resolve() -> None:
    assert resolve_profiles(["all-biomedicine"]) is None
    clinical = resolve_profiles(["clinical"])
    assert clinical is not None
    assert "Disease or Syndrome" in clinical
    assert "all-biomedicine" not in biomedicine_profile_names()
    assert safe_profile_name("chemicals-drugs") == "chemicals_drugs"


def test_profile_workflow_builds_and_links_shards(tmp_path: Path) -> None:
    mrconso = tmp_path / "MRCONSO.RRF"
    mrconso.write_text(
        "C0004238|ENG|P|L1|PF|S1|Y|A1|||D001|MSH|MH|D001|Atrial Fibrillation|0|N||\n"
        "C0004057|ENG|P|L2|PF|S2|Y|A2|||D002|MSH|MH|D002|Aspirin|0|N||\n",
        encoding="utf-8",
    )
    mrsty = tmp_path / "MRSTY.RRF"
    mrsty.write_text(
        "C0004238|T047|A1.2.2|Disease or Syndrome|AT1||\n"
        "C0004057|T121|A1.4.1.1.1|Pharmacologic Substance|AT2||\n",
        encoding="utf-8",
    )
    index_dir = tmp_path / "indexes"
    results = build_profile_indexes(
        mrconso_path=mrconso,
        mrsty_path=mrsty,
        out_dir=index_dir,
        profiles=["clinical", "chemicals-drugs"],
        replace=True,
        min_tokens=1,
    )
    assert [result.profile for result in results] == ["clinical", "chemicals-drugs"]
    assert profile_index_path(index_dir, "chemicals-drugs").exists()

    corpus_path = tmp_path / "corpus.jsonl"
    write_jsonl(
        corpus_path,
        [
            {
                "doc_id": "doc1",
                "source": "pubmed",
                "title": "",
                "text": "Atrial fibrillation and aspirin were both discussed.",
                "metadata": {},
            }
        ],
    )
    link_results = link_profile_shards(
        corpus_paths=[corpus_path],
        index_dir=index_dir,
        out_dir=tmp_path / "evidence",
        profiles=["clinical", "chemicals-drugs"],
        run_name="test",
        max_label_tokens=3,
        materialize_corpus=True,
    )
    assert [result.evidence_count for result in link_results] == [1, 1]
    clinical_text = link_results[0].evidence_path.read_text(encoding="utf-8")
    chemicals_text = link_results[1].evidence_path.read_text(encoding="utf-8")
    assert "pubmed_clinical_context" in clinical_text
    assert "pubmed_chemicals_drugs_context" in chemicals_text


def test_tabular_corpus_ingest(tmp_path: Path) -> None:
    path = tmp_path / "triage.tsv"
    path.write_text(
        "subject_id\tstay_id\tchiefcomplaint\n"
        "1\t10\tpalpitations and a fib\n",
        encoding="utf-8",
    )
    documents = list(
        read_tabular_corpus(
            path,
            source="mimic_iv_ed_triage",
            text_columns=["chiefcomplaint"],
            id_columns=["subject_id", "stay_id"],
        )
    )
    assert len(documents) == 1
    assert documents[0].source == "mimic_iv_ed_triage"
    assert documents[0].text == "palpitations and a fib"


def test_mimic_note_ingest_preserves_note_metadata(tmp_path: Path) -> None:
    root = tmp_path / "mimic-iv-note"
    note_dir = root / "note"
    note_dir.mkdir(parents=True)
    discharge_path = note_dir / "discharge.csv.gz"
    with gzip.open(discharge_path, "wt", encoding="utf-8", newline="") as handle:
        handle.write("note_id,subject_id,hadm_id,note_type,note_seq,charttime,storetime,text\n")
        handle.write(
            'D-1,100,200,DS,1,2120-01-02 03:04:00,2120-01-02 04:05:00,'
            '"Patient reports chest pain.\nWorse with exertion."\n'
        )

    documents = list(
        iter_mimic_note_documents(
            discharge_path,
            note_kind="discharge",
            source="mimic_iv_note_discharge",
        )
    )
    assert len(documents) == 1
    assert documents[0].doc_id == "MIMIC_NOTE:D-1"
    assert documents[0].source == "mimic_iv_note_discharge"
    assert documents[0].title == "discharge note DS"
    assert documents[0].text == "Patient reports chest pain. Worse with exertion."
    assert documents[0].metadata["note_id"] == "D-1"
    assert documents[0].metadata["table"] == "discharge.csv.gz"

    results = write_mimic_note_corpora(
        root=root,
        out_dir=tmp_path / "out",
        note_kinds=["discharge"],
        max_discharge_rows=1,
    )
    assert len(results) == 1
    assert results[0].count == 1
    assert results[0].path.name == "mimic_iv_note_discharge_corpus.jsonl"


def test_mimic_structured_ingest_groups_dictionary_items(tmp_path: Path) -> None:
    root = tmp_path / "mimic"
    (root / "hosp").mkdir(parents=True)
    (root / "icu").mkdir(parents=True)
    (root / "hosp" / "d_labitems.csv").write_text(
        "itemid,label,fluid,category\n"
        "51301,White Blood Cells,Blood,Hematology\n",
        encoding="utf-8",
    )
    (root / "hosp" / "labevents.csv").write_text(
        "labevent_id,subject_id,hadm_id,specimen_id,itemid,order_provider_id,charttime,storetime,value,valuenum,valueuom,ref_range_lower,ref_range_upper,flag,priority,comments\n"
        "1,1,2,3,51301,,t,t,20.3,20.3,K/uL,4,10,abnormal,ROUTINE,\n"
        "2,1,2,3,51301,,t,t,8.1,8.1,K/uL,4,10,,ROUTINE,\n",
        encoding="utf-8",
    )
    (root / "icu" / "d_items.csv").write_text(
        "itemid,label,abbreviation,linksto,category,unitname,param_type,lownormalvalue,highnormalvalue\n"
        "220045,Heart Rate,HR,chartevents,Routine Vital Signs,bpm,Numeric,,\n",
        encoding="utf-8",
    )
    (root / "icu" / "chartevents.csv").write_text(
        "subject_id,hadm_id,stay_id,caregiver_id,charttime,storetime,itemid,value,valuenum,valueuom,warning\n"
        "1,2,3,4,t,t,220045,110,110,bpm,1\n",
        encoding="utf-8",
    )
    for name in [
        "datetimeevents.csv",
        "outputevents.csv",
        "inputevents.csv",
        "ingredientevents.csv",
        "procedureevents.csv",
    ]:
        (root / "icu" / name).write_text("itemid,value,valueuom\n", encoding="utf-8")
    (root / "hosp" / "pharmacy.csv").write_text(
        "subject_id,hadm_id,pharmacy_id,poe_id,starttime,stoptime,medication,proc_type,status,entertime,verifiedtime,route,frequency,disp_sched,infusion_type,sliding_scale,lockout_interval,basal_rate,one_hr_max,doses_per_24_hrs,duration,duration_interval,expiration_value,expiration_unit,expirationdate,dispensation,fill_quantity\n",
        encoding="utf-8",
    )

    documents = list(iter_mimic_structured_documents(root))
    texts = "\n".join(document.text for document in documents)
    assert len(documents) == 2
    assert "White Blood Cells" in texts
    assert "20.3 K/uL" in texts
    assert "Heart Rate" in texts
    assert "warning" in texts


def test_mimic_structured_ingest_reads_gzip_and_custom_source_prefix(tmp_path: Path) -> None:
    root = tmp_path / "mimic"
    (root / "hosp").mkdir(parents=True)
    (root / "icu").mkdir(parents=True)
    with gzip.open(root / "hosp" / "d_labitems.csv.gz", "wt", encoding="utf-8", newline="") as handle:
        handle.write("itemid,label,fluid,category\n51301,White Blood Cells,Blood,Hematology\n")
    with gzip.open(root / "hosp" / "labevents.csv.gz", "wt", encoding="utf-8", newline="") as handle:
        handle.write(
            "labevent_id,subject_id,hadm_id,specimen_id,itemid,charttime,value,valueuom,flag,priority\n"
            "1,1,2,3,51301,t,20.3,K/uL,abnormal,ROUTINE\n"
        )
    with gzip.open(root / "icu" / "d_items.csv.gz", "wt", encoding="utf-8", newline="") as handle:
        handle.write("itemid,label,category,unitname,param_type\n220045,Heart Rate,Routine Vital Signs,bpm,Numeric\n")
    documents = list(
        iter_mimic_structured_documents(
            root,
            sources={"mimic_iv_labevents"},
            source_prefix="mimic_iv",
        )
    )
    assert len(documents) == 1
    assert documents[0].source == "mimic_iv_labevents"
    assert "White Blood Cells" in documents[0].text
    assert "20.3 K/uL" in documents[0].text


def test_mimic_structured_ingest_can_coordinate_admission_notes(tmp_path: Path) -> None:
    root = tmp_path / "mimic"
    (root / "hosp").mkdir(parents=True)
    (root / "icu").mkdir(parents=True)
    (root / "hosp" / "d_labitems.csv").write_text(
        "itemid,label,fluid,category\n"
        "51301,White Blood Cells,Blood,Hematology\n",
        encoding="utf-8",
    )
    (root / "hosp" / "labevents.csv").write_text(
        "labevent_id,subject_id,hadm_id,specimen_id,itemid,charttime,value,valueuom,flag,priority\n"
        "1,1,2,3,51301,t,20.3,K/uL,abnormal,ROUTINE\n"
        "2,1,2,3,51301,t,21.0,K/uL,abnormal,ROUTINE\n",
        encoding="utf-8",
    )
    (root / "icu" / "d_items.csv").write_text(
        "itemid,label,category,unitname,param_type\n",
        encoding="utf-8",
    )
    for name in [
        "chartevents.csv",
        "datetimeevents.csv",
        "outputevents.csv",
        "inputevents.csv",
        "ingredientevents.csv",
        "procedureevents.csv",
    ]:
        (root / "icu" / name).write_text("itemid,value,valueuom,hadm_id\n", encoding="utf-8")
    (root / "hosp" / "pharmacy.csv").write_text(
        "subject_id,hadm_id,pharmacy_id,medication,route,frequency,status,proc_type\n",
        encoding="utf-8",
    )
    note_corpus = tmp_path / "notes.jsonl"
    write_jsonl(
        note_corpus,
        [
            {
                "doc_id": "MIMIC_NOTE:D-1",
                "source": "mimic_iv_note_discharge",
                "title": "discharge note DS",
                "text": "Patient treated for pneumonia with leukocytosis and antibiotics.",
                "metadata": {
                    "note_id": "D-1",
                    "hadm_id": "2",
                    "note_kind": "discharge",
                    "note_type": "DS",
                },
            }
        ],
    )

    documents = list(
        iter_mimic_structured_documents(
            root,
            sources={"mimic_demo_labevents"},
            note_corpus_paths=[note_corpus],
            max_note_examples_per_group=1,
        )
    )

    assert len(documents) == 1
    assert "Admission-level MIMIC note coordination" in documents[0].text
    assert "not direct assertions about the structured item" in documents[0].text
    assert "pneumonia with leukocytosis" in documents[0].text
    assert documents[0].metadata["coordinated_note_admission_count"] == 1
    assert documents[0].metadata["coordinated_note_count"] == 1


def test_label_index_links_corpus_context(tmp_path: Path) -> None:
    mrconso = tmp_path / "MRCONSO.RRF"
    mrconso.write_text(
        "C0004238|ENG|P|L1|PF|S1|Y|A1|||D001|MSH|MH|D001|Atrial Fibrillation|0|N||\n"
        "C0011849|ENG|P|L2|PF|S2|Y|A2|||D002|MSH|MH|D002|Diabetes Mellitus|0|N||\n",
        encoding="utf-8",
    )
    index_path = tmp_path / "labels.sqlite"
    count = build_label_index(mrconso_path=mrconso, out_path=index_path, replace=True)
    assert count == 2

    from qe_evidence_vectors.schema import CorpusDocument

    document = CorpusDocument(
        doc_id="PMID:1",
        source="pubmed",
        title="Atrial fibrillation in practice",
        text="Patients often call atrial fibrillation a fib during visits.",
        metadata={"pmid": "1"},
    )
    with LabelIndex(index_path) as index:
        evidence = link_corpus_to_evidence([document], index)
    assert len(evidence) >= 1
    assert evidence[0].cui == "C0004238"
    assert "a fib" in evidence[0].text


def test_trie_linker_links_corpus_context(tmp_path: Path) -> None:
    mrconso = tmp_path / "MRCONSO.RRF"
    mrconso.write_text(
        "C0004238|ENG|P|L1|PF|S1|Y|A1|||D001|MSH|MH|D001|Atrial Fibrillation|0|N||\n"
        "C0011849|ENG|P|L2|PF|S2|Y|A2|||D002|MSH|MH|D002|Diabetes Mellitus|0|N||\n",
        encoding="utf-8",
    )
    index_path = tmp_path / "labels.sqlite"
    build_label_index(mrconso_path=mrconso, out_path=index_path, replace=True)

    from qe_evidence_vectors.schema import CorpusDocument

    document = CorpusDocument(
        doc_id="PMID:1",
        source="pubmed",
        title="Atrial fibrillation in practice",
        text="Patients often call atrial fibrillation a fib during visits.",
        metadata={"pmid": "1"},
    )
    trie = LabelTrie.from_sqlite(index_path)
    evidence = list(link_document_to_evidence_trie(document, trie))
    assert len(evidence) >= 1
    assert evidence[0].cui == "C0004238"
    assert "a fib" in evidence[0].text


def test_trie_linker_evidence_tag_separates_views(tmp_path: Path) -> None:
    mrconso = tmp_path / "MRCONSO.RRF"
    mrconso.write_text(
        "C0004238|ENG|P|L1|PF|S1|Y|A1|||D001|MSH|MH|D001|Atrial Fibrillation|0|N||\n",
        encoding="utf-8",
    )
    index_path = tmp_path / "labels.sqlite"
    build_label_index(mrconso_path=mrconso, out_path=index_path, replace=True)

    from qe_evidence_vectors.schema import CorpusDocument

    document = CorpusDocument(
        doc_id="PMID:1",
        source="pubmed",
        title="",
        text="atrial fibrillation",
    )
    trie = LabelTrie.from_sqlite(index_path)
    evidence = list(link_document_to_evidence_trie(document, trie, evidence_tag="clinical"))
    assert evidence[0].evidence_type == "pubmed_clinical_context"
